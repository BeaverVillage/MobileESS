"""Exclusive repair ownership and evidence-gated, persistent retry requests.

The guardian owns an OS lock across separate Codex commands. Its lifetime is
independent of a CLI shell; an optional persistent owner PID is checked using
its creation time. A lease never expires merely because an hour elapsed.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import uuid

import psutil


REQUIRED_FAILURE = ('date', 'arm', 'failed_stage', 'failure_class',
                    'original_attempt_id', 'original_source_SHA',
                    'original_native_runtime')
REQUIRED_VALIDATION = ('regression_PASS', 'original_matrix_domain_PASS',
                       'original_physical_integer_PASS', 'original_objective_PASS',
                       'independent_validation_PASS')
B3_STAGES = ('A1', 'M1', 'A2', 'M2')


def _measured(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def b3_stage_accounting(result, *, day, source, previous=None):
    """Check four cumulative stage ledgers without imposing an aggregate cap.

    The worker seals explicit NOT_ENTERED states. A missing or interrupted
    ledger is never inferred to have cost zero. Prior calls are compared as
    exact prefixes, so a retry cannot drop or count them a second time.
    """
    runtime = result.get('stage_native_runtime')
    counts = result.get('stage_native_calls')
    states = result.get('stage_native_accounting')
    ledgers = result.get('stage_native_ledger_receipts')
    identities = result.get('stage_native_ledger_identity_receipts')
    if (not all(isinstance(value, dict) for value in (runtime, counts, states, ledgers, identities))
            or any(set(value) != set(B3_STAGES) for value in (runtime, counts, states))
            or not set(ledgers).issubset(B3_STAGES) or set(identities) != set(ledgers)):
        raise PermissionError('B3_COMPLETE_STAGE_NATIVE_ACCOUNTING_REQUIRED')
    if (any(states[stage] not in ('MEASURED', 'NOT_ENTERED') or not _measured(runtime[stage])
            or type(counts[stage]) is not int or counts[stage] < 0 for stage in B3_STAGES)
            or result.get('native_runtime_state') not in (None, 'KNOWN')):
        raise PermissionError('UNKNOWN_NATIVE_RUNTIME_NO_AUTOMATIC_RETRY')
    prior_roots = []
    request_receipt = result.get('request')
    if request_receipt:
        if record(request_receipt['path']) != request_receipt:
            raise PermissionError('B3_ACCOUNTING_REQUEST_RECEIPT_SHA_DRIFT')
        prior_roots = [Path(value).resolve() / 'PIPELINE' for value in read(request_receipt['path']).get('previous_attempts', [])]
    calls = {}
    for stage in B3_STAGES:
        if states[stage] == 'NOT_ENTERED':
            if runtime[stage] != 0 or counts[stage] != 0 or stage in ledgers:
                raise PermissionError('B3_NOT_ENTERED_STAGE_ACCOUNTING_DRIFT')
            calls[stage] = []
        else:
            if stage not in ledgers or record(ledgers[stage]['path']) != ledgers[stage] or record(identities[stage]['path']) != identities[stage]:
                raise PermissionError('B3_STAGE_LEDGER_RECEIPT_SHA_DRIFT')
            path = Path(ledgers[stage]['path']).resolve()
            if (path.name != 'NATIVE_RUNTIME_LEDGER.json' or path.parent.name != stage
                    or path.parent.parent.name != 'PIPELINE'
                    or Path(identities[stage]['path']).resolve() != path.with_name('NATIVE_RUNTIME_LEDGER_IDENTITY.json')):
                raise PermissionError('B3_STAGE_LEDGER_PATH_IDENTITY_DRIFT')
            ledger, identity_doc = read(path), read(identities[stage]['path'])
            source_matches = identity_doc.get('source_sha') == source or (
                _sha(identity_doc.get('source_sha'), 64) and any(path.is_relative_to(value) for value in prior_roots))
            if (identity_doc.get('stage') != stage or identity_doc.get('day') != day
                    or not source_matches or identity_doc.get('native_limit_seconds') != 5400
                    or not _sha(identity_doc.get('input_sha'), 64)):
                raise PermissionError('B3_STAGE_LEDGER_SCIENTIFIC_IDENTITY_DRIFT')
            rows = ledger.get('calls')
            if (not isinstance(rows, list) or ledger.get('inflight') is not None or ledger.get('quarantined')
                    or ledger.get('actual_cumulative_Native_Runtime') == 'UNKNOWN'
                    or any(row.get('runtime_unavailable') or row.get('entered_native') is not True
                           or not _measured(row.get('Native_Runtime')) for row in rows)):
                raise PermissionError('UNKNOWN_NATIVE_RUNTIME_NO_AUTOMATIC_RETRY')
            if (ledger.get('Native_ceiling_seconds') != 5400 or ledger.get('wall_ceiling_seconds') is not None
                    or ledger.get('P2_calls') != 0 or ledger.get('budget_basis') != 'MEASURED_NATIVE_RUNTIME_ONLY'
                    or not _measured(ledger.get('measured_Native_Runtime'))
                    or not math.isclose(sum(row['Native_Runtime'] for row in rows), runtime[stage], rel_tol=0, abs_tol=1e-9)
                    or ledger['measured_Native_Runtime'] != runtime[stage] or len(rows) != counts[stage]):
                raise PermissionError('B3_STAGE_MEASURED_NATIVE_ACCOUNTING_DRIFT')
            calls[stage] = rows
        if previous is not None:
            prior = previous['calls'][stage]
            if calls[stage][:len(prior)] != prior or runtime[stage] < previous['runtime'][stage]:
                raise PermissionError('B3_CUMULATIVE_STAGE_NATIVE_PREFIX_REQUIRED')
    if (not _measured(result.get('Native_Runtime'))
            or not math.isclose(sum(runtime.values()), result['Native_Runtime'], rel_tol=0, abs_tol=1e-9)):
        raise PermissionError('B3_AGGREGATE_STAGE_NATIVE_ACCOUNTING_DRIFT')
    return dict(runtime=runtime, calls=calls, counts=counts, states=states,
                ledgers=ledgers, identities=identities, total=result['Native_Runtime'])


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                        allow_nan=False) + '\n', encoding='utf8')
        from v42_pr134_b1.common import replace_file
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def record(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def identity(pid=None):
    proc = psutil.Process(pid or os.getpid())
    return dict(PID=proc.pid, created=proc.create_time(), command=proc.cmdline())


def alive(owner):
    try:
        proc = psutil.Process(owner['PID'])
        return (proc.create_time() == owner['created']
                and proc.cmdline() == owner['command'] and proc.is_running())
    except (KeyError, psutil.Error):
        return False


class LeaseBusy(RuntimeError):
    pass


class HeartbeatObservationDeferred(RuntimeError):
    """An owned volatile heartbeat could not be read; no evidence was admitted."""
    def __init__(self, path, error):
        self.observation = dict(path=str(Path(path).resolve()), error=repr(error),
            reason=str(error), errno=error.errno, winerror=getattr(error, 'winerror', None),
            error_class=type(error).__name__,
            cause_classification=('WINDOWS_SHARING_OR_LOCK_VIOLATION' if getattr(error, 'winerror', None) in (32, 33)
                                  else 'WINDOWS_ACCESS_DENIED_CAUSE_UNRESOLVED'))
        super().__init__('OWNED_WORKER_HEARTBEAT_READ_DEFERRED:' + self.observation['reason'])


class HeartbeatObservationRead(dict):
    """A row result with a real, owned heartbeat read; no persisted evidence flag."""
    pass


class SourceBlocked(PermissionError):
    """A shared source or environment failure blocks future Native admission."""


def common_failure(error):
    """Only shared integrity/environment evidence can stop the whole sweep."""
    if isinstance(error, SourceBlocked) or getattr(error, 'failure_scope', None) in ('SOURCE_GLOBAL', 'ENVIRONMENT_GLOBAL'):
        return True
    # CalledProcessError.__str__ embeds the complete verifier program. Its
    # source-integrity error labels are code, not evidence of this failure.
    detail = (str(getattr(error, 'stderr', '') or '')+'\n'+str(getattr(error, 'stdout', '') or '')) if isinstance(error,subprocess.CalledProcessError) else str(error)
    tokens = ('GLOBAL_SOURCE_INTEGRITY_FAILURE', 'GLOBAL_ENVIRONMENT_FAILURE', 'COMMON_ENVIRONMENT_FAILURE',
        'B3_SOURCE_SEAL_', 'B3_DECLARED_SOURCE_SEAL_', 'B3_DECLARED_SOURCE_SHA_DRIFT',
        'B3_SCIENTIFIC_RUN_ID_BINDING_DRIFT',
        'COMPLETE_B3_SOURCE_SEAL_REQUIRED', 'SOURCE_SEAL_IDENTITY_DRIFT', 'SOURCE_SEAL_FILE_DRIFT',
        'ORIGINAL_SCIENCE_SOURCE_DRIFT', 'CANONICAL_INPUT_PROVENANCE_SOURCE_DRIFT',
        'V19_SOURCE_OR_POLICY_SEAL_DRIFT', 'V19_ORIGINAL_SCIENTIFIC_SOURCE_DRIFT',
        'B2_DEPLOYMENT_MANIFEST_RECEIPT_DRIFT', 'B2_DEPLOYMENT_RUN_OR_CODE_ROOT_DRIFT',
        'RECOVERY_CHECKOUT_COMMIT_DRIFT', 'RECOVERY_IMMUTABLE_CHECKOUT_REQUIRED', 'RECOVERY_SOURCE_FILES_DRIFT')
    return any(token in detail for token in tokens) or (
        isinstance(error, (ModuleNotFoundError, ImportError)) or
        isinstance(error, subprocess.CalledProcessError) and ('ModuleNotFoundError' in detail or 'ImportError:' in detail))


@contextmanager
def os_lock(path):
    """Lock ownership is the open descriptor, never a stale JSON or PID alone."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a+b')
    acquired = False
    try:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise LeaseBusy('REPAIR_OS_LEASE_BUSY:' + str(path)) from exc
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


@contextmanager
def repair_lease(root, *, token=None, owner=None):
    root = Path(root).resolve()
    token = token or uuid.uuid4().hex
    with os_lock(root / 'REPAIR.lock'):
        lease = dict(token=token, guardian=identity(), owner=owner,
                     acquired_UTC=now(), heartbeat_UTC=now(), state='ACTIVE',
                     automatic_time_expiry=False)
        atomic(root / 'REPAIR_LEASE.json', lease)
        try:
            yield lease
        finally:
            lease.update(state='RELEASED', released_UTC=now())
            atomic(root / 'repair_leases' / (token + '.json'), lease)
            atomic(root / 'REPAIR_LEASE.json', lease)


def assert_lease(root, token):
    lease = read(Path(root) / 'REPAIR_LEASE.json', {})
    if (lease.get('state') != 'ACTIVE' or lease.get('token') != token
            or not alive(lease.get('guardian', {}))):
        raise PermissionError('LIVE_REPAIR_LEASE_REQUIRED')
    # A live PID receipt is cross-checked against the actual OS lock.
    try:
        with os_lock(Path(root) / 'REPAIR.lock'):
            pass
    except LeaseBusy:
        return lease
    raise PermissionError('REPAIR_RECEIPT_WITHOUT_OS_LOCK')


def guard(root, token, *, owner=None):
    """Background guardian: no solver control, CPU affinity or memory policy."""
    root = Path(root).resolve()
    try:
        with repair_lease(root, token=token, owner=owner) as lease:
            atomic(root / 'repair_leases' / (token + '.ready.json'), lease)
            while True:
                release = read(root / 'repair_leases' / (token + '.end.json'), {})
                if release.get('token') == token:
                    lease['release_reason'] = 'EXPLICIT_REPAIR_END'
                    break
                if owner is not None and not alive(owner):
                    lease['release_reason'] = 'PERSISTENT_OWNER_PROCESS_EXITED'
                    break
                lease['heartbeat_UTC'] = now()
                atomic(root / 'REPAIR_LEASE.json', lease)
                time.sleep(2)
    except BaseException as exc:
        atomic(root / 'repair_leases' / (token + '.error.json'),
               dict(token=token, error=repr(exc), UTC=now()))
        raise


def begin(root, *, owner_pid=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    owner = identity(owner_pid) if owner_pid is not None else None
    command = [sys.executable.replace('pythonw.exe', 'python.exe'), '-B', '-X',
               'utf8', '-m', 'v42_autonomous.recovery', 'guard', '--root',
               str(root), '--token', token]
    if owner is not None:
        owner_path = root / 'repair_leases' / (token + '.owner.json')
        atomic(owner_path, owner)
        command.extend(['--owner-file', str(owner_path)])
    kwargs = dict(cwd=str(Path(__file__).resolve().parents[1]),
                  stdin=subprocess.DEVNULL, close_fds=True)
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    with (root / 'repair.guard.stdout.log').open('ab') as out, \
            (root / 'repair.guard.stderr.log').open('ab') as err:
        subprocess.Popen(command, stdout=out, stderr=err, **kwargs)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        ready = read(root / 'repair_leases' / (token + '.ready.json'))
        if ready is not None:
            assert_lease(root, token)
            return ready
        error = read(root / 'repair_leases' / (token + '.error.json'))
        if error is not None:
            raise LeaseBusy(error['error'])
        time.sleep(.05)
    raise RuntimeError('REPAIR_GUARDIAN_START_NOT_VERIFIED:' + token)


def end(root, token):
    assert_lease(root, token)
    atomic(Path(root) / 'repair_leases' / (token + '.end.json'),
           dict(token=token, UTC=now()))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        released = read(Path(root) / 'repair_leases' / (token + '.json'))
        if released is not None and released.get('state') == 'RELEASED':
            return released
        time.sleep(.05)
    raise RuntimeError('REPAIR_RELEASE_NOT_VERIFIED')


def queue(root):
    return read(Path(root) / 'RECOVERY_QUEUE.json',
                dict(schema='V42_RECOVERY_QUEUE_V1', entries=[], UTC=now()))


def _sha(value, length):
    return (isinstance(value, str) and len(value) == length
            and all(char in '0123456789abcdef' for char in value.lower()))


def zero_start_authorization(root, packet):
    if packet.get('restart_from_zero') is not True:
        return None
    receipt=packet.get('reset_authorization')
    if (not receipt or Path(receipt['path']).resolve()!=Path(root).resolve()/'USER_ZERO_START_RETRY_AUTHORIZATION.json'
            or record(receipt['path'])!=receipt):
        raise PermissionError('RETRY_ZERO_START_USER_AUTHORIZATION_REQUIRED')
    document=read(receipt['path'])
    if (document.get('schema')!='V42_USER_AUTHORIZED_ZERO_START_RETRY_V1'
            or Path(document.get('campaign_root','')).resolve()!=Path(root).resolve()
            or document.get('scope')!='VERIFIED_SOURCE_REPAIR_FRESH_DATE_RETRY'
            or document.get('user_instruction')!='해결하고 재실행할 때는 0초부터 처음부터 다시 돌려야돼. 알지?'
            or document.get('restart_from_zero') is not True or document.get('native_budget_seconds')!=5400
            or document.get('B3_native_budget_per_stage_seconds')!=5400
            or document.get('previous_checkpoint_reuse') is not False
            or document.get('previous_native_budget_carry') is not False
            or document.get('old_attempts_and_accounting_preserved') is not True):
        raise PermissionError('RETRY_ZERO_START_USER_AUTHORIZATION_REQUIRED')
    return receipt


def enqueue(root, failure, repair, *, lease_token, supersede_queue_id=None):
    """Only a new, verified repair can create a dispatchable retry request.

    UNKNOWN runtime is preserved but never silently converted to a new budget.
    Exhausted or quarantined failures stay terminal; a separate accounting
    adjudication must establish a measured budget before this API can retry.
    """
    root = Path(root).resolve()
    assert_lease(root, lease_token)
    if any(key not in failure for key in REQUIRED_FAILURE):
        raise ValueError('RECOVERY_ORIGINAL_FAILURE_IDENTITY_REQUIRED')
    if (failure['arm'] not in ('B2', 'B3')
            or failure['date'] not in {f'2025-05-{n:02d}' for n in range(1, 32)}):
        raise ValueError('RECOVERY_ARM_OR_DATE_INVALID')
    reset=zero_start_authorization(root,repair)
    consumed = failure['original_native_runtime']
    if reset is None and (isinstance(consumed, bool) or not isinstance(consumed, (int, float))
            or not math.isfinite(consumed) or consumed < 0
            or failure.get('budget_basis') == 'CONSERVATIVE_LOST_CALL_WINDOW'
            or failure.get('runtime_unknown') or failure.get('quarantined')):
        raise PermissionError('UNKNOWN_NATIVE_RUNTIME_NO_AUTOMATIC_RETRY')
    if reset is not None and not (_measured(consumed) or consumed is None or consumed=='UNKNOWN'):
        raise ValueError('RECOVERY_ORIGINAL_HISTORICAL_RUNTIME_REQUIRED')
    limit = failure.get('native_budget_seconds', 5400)
    if isinstance(limit, bool) or limit != 5400:
        raise ValueError('RECOVERY_NATIVE_BUDGET_REQUIRED')
    if reset is None and failure['arm'] == 'B2' and consumed >= limit:
        raise PermissionError('EXHAUSTED_NATIVE_BUDGET_NO_AUTOMATIC_RETRY')
    original_receipts = {}
    receipt_names = ('original_result_receipt', 'original_ledger_receipt') if (reset is None and failure['arm'] == 'B2') or failure.get('original_ledger_receipt') else ('original_result_receipt',)
    for name in receipt_names:
        receipt = failure.get(name)
        if not receipt or record(receipt['path']) != receipt:
            raise PermissionError('ORIGINAL_FAILURE_RECEIPT_REQUIRED:' + name)
        original_receipts[name] = receipt
    original_result = read(original_receipts['original_result_receipt']['path'])
    ledger = read(original_receipts['original_ledger_receipt']['path']) if reset is None and 'original_ledger_receipt' in original_receipts else {}
    reported=original_result.get('Native_Runtime')
    if original_result.get('PASS') is True or (reported!=consumed and not (
            reset is not None and reported in (None,'UNKNOWN') and consumed in (None,'UNKNOWN'))):
        raise PermissionError('ORIGINAL_MEASURED_FAILURE_BUDGET_REQUIRED')
    stage_accounting = None
    if reset is not None:
        if failure['arm']=='B3':
            stage_receipts=original_result.get('stage_native_ledger_receipts',{})
            identity_receipts=original_result.get('stage_native_ledger_identity_receipts',{})
            if any(record(item['path'])!=item for item in (*stage_receipts.values(),*identity_receipts.values())):
                raise PermissionError('B3_HISTORICAL_STAGE_LEDGER_RECEIPT_SHA_DRIFT')
    elif failure['arm'] == 'B3':
        stage_accounting = b3_stage_accounting(original_result, day=failure['date'], source=failure['original_source_SHA'])
        if (failure['failed_stage'] not in (*B3_STAGES, 'ADMISSION', 'PLANNING_FREEZE', 'ACTUAL', 'VALIDATION')
                or original_result.get('failed_stage') != failure['failed_stage']
                or ('original_ledger_receipt' in original_receipts and
                    original_receipts['original_ledger_receipt'] not in stage_accounting['ledgers'].values())):
            raise PermissionError('B3_ORIGINAL_FAILED_STAGE_IDENTITY_REQUIRED')
        if any(value >= limit for value in stage_accounting['runtime'].values()):
            raise PermissionError('EXHAUSTED_NATIVE_BUDGET_NO_AUTOMATIC_RETRY')
    else:
        measured = ledger.get('measured_Native_Runtime', ledger.get('measured_native_runtime'))
        if (measured != consumed or ledger.get('inflight') is not None
                or ledger.get('quarantined') or ledger.get('actual_cumulative_Native_Runtime') == 'UNKNOWN'
                or any(call.get('runtime_unavailable') for call in ledger.get('calls', []))):
            raise PermissionError('ORIGINAL_MEASURED_FAILURE_BUDGET_REQUIRED')
    commit, source = repair.get('repair_commit_SHA'), repair.get('repair_source_SHA')
    if (not _sha(commit, 40) or not _sha(source, 64)
            or source == failure['original_source_SHA'] or not repair.get('repair_reason')):
        raise PermissionError('VERIFIED_NEW_REPAIR_SOURCE_REQUIRED')
    receipt = repair.get('validation_receipt', {})
    if not receipt.get('path') or record(receipt['path']) != receipt:
        raise PermissionError('RECOVERY_VALIDATION_RECEIPT_SHA_DRIFT')
    validation = read(receipt['path'], {})
    if (validation.get('PASS') is not True
            or validation.get('repair_source_SHA') != source
            or validation.get('repair_commit_SHA') != commit
            or any(validation.get(field) is not True for field in REQUIRED_VALIDATION)):
        raise PermissionError('RECOVERY_ORIGINAL_SCIENTIFIC_VALIDATION_REQUIRED')
    sources = validation.get('source_files')
    if not isinstance(sources, list) or not sources or any(record(r['path']) != r for r in sources):
        raise PermissionError('RECOVERY_VERIFIED_SOURCE_FILES_REQUIRED')
    priority = repair.get('retry_priority', 100)
    if type(priority) is not int:
        raise ValueError('RECOVERY_INTEGER_PRIORITY_REQUIRED')
    request_receipt = repair.get('retry_request_receipt')
    alternatives = repair.get('retry_request_receipts_by_slot', {})
    code_root = repair.get('repair_code_root')
    if not code_root or not request_receipt or record(request_receipt['path']) != request_receipt:
        raise PermissionError('SEALED_FRESH_RETRY_REQUEST_REQUIRED')
    request = read(request_receipt['path'])
    if request.get('restart_from_zero') is True and reset is None:
        raise PermissionError('RETRY_ZERO_START_USER_AUTHORIZATION_REQUIRED')
    if reset is not None and (zero_start_authorization(root,request)!=reset or
            request.get('previous_attempts',[])!=[] or failure['arm']=='B3' and request.get('previous_attempts')!=[]):
        raise PermissionError('RETRY_AUTHORIZED_FRESH_ZERO_REQUEST_REQUIRED')
    if (request.get('arm') != failure['arm'] or request.get('day') != failure['date']
            or request.get('attempt_id') == failure['original_attempt_id']
            or not request.get('attempt_id') or Path(request['result']).exists()):
        raise PermissionError('RETRY_REQUEST_IDENTITY_OR_EXISTING_RESULT_DRIFT')
    retry_dir = Path(request['result']).resolve().parent
    expected = root / 'dates' / failure['arm'] / failure['date'] / 'attempts' / request['attempt_id']
    if retry_dir != expected or Path(request_receipt['path']).resolve() != expected / 'request.json':
        raise PermissionError('NEW_RETRY_ATTEMPT_DIRECTORY_REQUIRED')
    for slot_key, alternate in alternatives.items():
        if slot_key not in (('1', '2', '3') if failure['arm'] == 'B2' else ('1',)):
            raise PermissionError('RETRY_ALTERNATE_SLOT_INVALID')
        if record(alternate['path']) != alternate:
            raise PermissionError('RETRY_ALTERNATE_REQUEST_SHA_DRIFT')
        candidate = read(alternate['path'])
        candidate_expected = root / 'dates' / failure['arm'] / failure['date'] / 'attempts' / candidate['attempt_id']
        if (candidate.get('arm') != failure['arm'] or candidate.get('day') != failure['date']
                or candidate.get('worker_slot') != int(slot_key)
                or candidate['attempt_id'] == failure['original_attempt_id']
                or Path(candidate['result']).exists()
                or Path(candidate['result']).resolve().parent != candidate_expected
                or Path(alternate['path']).resolve() != candidate_expected / 'request.json'):
            raise PermissionError('RETRY_ALTERNATE_FRESH_SLOT_REQUEST_REQUIRED')
    with os_lock(root / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        key = (failure['arm'], failure['date'], failure['original_attempt_id'], source)
        for row in doc['entries']:
            if (row['arm'], row['date'], row['original_attempt_id'], row['repair_source_SHA']) == key:
                if supersede_queue_id is not None and row.get('supersedes_queue_id')!=supersede_queue_id:
                    raise PermissionError('REPAIR_SUPERSESSION_IDEMPOTENCE_DRIFT')
                return row
        previous=None
        if supersede_queue_id is not None:
            previous=next((entry for entry in doc['entries'] if entry['queue_id']==supersede_queue_id),None)
            if (previous is None or previous['arm']!=failure['arm'] or previous['date']!=failure['date']
                    or previous['repair_source_SHA']==source or not _unstarted_ready(previous)
                    or not _supervisor_preserves_unstarted_target(root,previous)):
                raise PermissionError('ONLY_UNSTARTED_READY_REPAIR_CAN_BE_SUPERSEDED')
        row = {key: failure[key] for key in REQUIRED_FAILURE}
        row.update(queue_id=uuid.uuid4().hex, repair_commit_SHA=commit,
                   repair_source_SHA=source, repair_reason=repair['repair_reason'],
                   retry_priority=priority, retry_attempt_id=None, new_worker_PID=None,
                   verification_status='READY_VERIFIED_REPAIR', queued_UTC=now(),
                   validation_receipt=receipt, source_files=sources,
                   native_budget_seconds=limit,
                   remaining_native_seconds=limit if reset is not None else limit - consumed if stage_accounting is None else (
                       limit - stage_accounting['runtime'][failure['failed_stage']]
                       if failure['failed_stage'] in B3_STAGES else None),
                   **original_receipts,
                   worker_module=repair.get('worker_module',
                       'v42_b2_seed_recovery_v19.worker' if failure['arm'] == 'B2' else 'v42_autonomous_b3.worker'),
                   retry_request_receipt=request_receipt, repair_code_root=str(Path(code_root).resolve()))
        row['campaign_root']=str(root)
        row['retry_request_receipts_by_slot'] = alternatives
        if reset is not None:
            row.update(restart_from_zero=True,reset_authorization=reset,
                native_budget_scope='NEW_VERIFIED_REPAIR_ATTEMPT',initial_native_runtime=0.,
                historical_native_runtime=consumed,historical_runtime_unknown=not _measured(consumed),
                old_attempts_and_accounting_preserved=True,previous_checkpoint_reuse=False,previous_native_budget_carry=False)
            if failure['arm']=='B3':
                row.update(historical_stage_native_runtime=original_result.get('stage_native_runtime'),
                    historical_stage_ledger_receipts=original_result.get('stage_native_ledger_receipts',{}),
                    historical_stage_ledger_identity_receipts=original_result.get('stage_native_ledger_identity_receipts',{}),
                    initial_stage_native_runtime={stage:0. for stage in B3_STAGES},
                    remaining_native_seconds_by_stage={stage:5400. for stage in B3_STAGES})
        if stage_accounting is not None:
            row.update(native_budget_scope='B3_STAGE_ISOLATED',
                       original_stage_native_runtime=stage_accounting['runtime'],
                       original_stage_native_calls=stage_accounting['counts'],
                       original_stage_native_accounting=stage_accounting['states'],
                       original_stage_ledger_receipts=stage_accounting['ledgers'],
                       original_stage_ledger_identity_receipts=stage_accounting['identities'],
                       remaining_native_seconds_by_stage={stage:limit-value for stage,value in stage_accounting['runtime'].items()})
        _verify_dispatch(row, request)
        for alternate in alternatives.values():
            _verify_dispatch(dict(row, retry_request_receipt=alternate), read(alternate['path']))
        if previous is not None:
            previous.update(verification_status='SUPERSEDED_UNSTARTED_READY',
                superseded_by_queue_id=row['queue_id'],superseded_UTC=now(),
                superseded_reason='NEW_INDEPENDENTLY_VERIFIED_REPAIR_SOURCE',
                original_prepared_repair_and_failure_evidence_preserved=True)
            row['supersedes_queue_id']=previous['queue_id']
        doc['entries'].append(row)
        doc['UTC'] = now()
        atomic(root / 'RECOVERY_QUEUE.json', doc)
        return row


def ready(root, arm, active_dates=()):
    """Select retries before ordinary pending dates without touching live work."""
    active = set(active_dates)
    rows = [row for row in queue(root)['entries']
            if row['arm'] == arm and row['date'] not in active
            and row['verification_status'] == 'READY_VERIFIED_REPAIR']
    rows.sort(key=lambda row: (-row['retry_priority'], row['queued_UTC'], row['date']))
    return rows


def dispatch_ready(root, arm, slot, manifest):
    """Only evidence-complete recovery entries can be launched by a supervisor."""
    entries = queue(root)['entries']
    if not any(row['arm'] == arm and row['verification_status'] in
               ('READY_VERIFIED_REPAIR', 'DISPATCH_INTENT') for row in entries):
        return None
    return _dispatch_ready(root, arm, slot, manifest)


def _request_workers(request_path):
    matches = []
    for proc in psutil.process_iter(['name']):
        if (proc.info['name'] or '').lower() not in ('python.exe', 'pythonw.exe'):
            continue
        try:
            args = proc.cmdline()
            if args and Path(args[-1]).resolve() == Path(request_path).resolve():
                matches.append(identity(proc.pid))
        except (psutil.Error, OSError, ValueError):
            continue
    return matches


def _verify_dispatch(row, request):
    """Validate inside the immutable repair checkout, using its own imports."""
    code_root = Path(row['repair_code_root']).resolve()
    if any(record(r['path']) != r for r in row['source_files']):
        raise SourceBlocked('RECOVERY_SOURCE_FILES_DRIFT')
    if (record(row['retry_request_receipt']['path']) != row['retry_request_receipt']
            or any(record(row[name]['path']) != row[name] for name in
                   ('original_result_receipt', 'original_ledger_receipt') if name in row)
            or record(row['validation_receipt']['path']) != row['validation_receipt']):
        raise PermissionError('RECOVERY_SEALED_EVIDENCE_DRIFT')
    validation = read(row['validation_receipt']['path'])
    if (validation.get('repair_source_SHA') != row['repair_source_SHA']
            or validation.get('repair_commit_SHA') != row['repair_commit_SHA']
            or validation.get('PASS') is not True
            or any(validation.get(field) is not True for field in REQUIRED_VALIDATION)):
        raise PermissionError('RECOVERY_VALIDATION_CHANGED')
    head = subprocess.run(['git', '-C', str(code_root), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != row['repair_commit_SHA']:
        raise PermissionError('RECOVERY_CHECKOUT_COMMIT_DRIFT')
    dirty = subprocess.run(['git', '-C', str(code_root), 'status', '--porcelain',
                            '--untracked-files=no'], capture_output=True, text=True, check=True).stdout
    if dirty.strip():
        raise PermissionError('RECOVERY_IMMUTABLE_CHECKOUT_REQUIRED')
    module = row['worker_module']
    allowed = ('v42_b2_seed_recovery_v19.worker', 'v42_autonomous_b2.worker') if row['arm'] == 'B2' else ('v42_autonomous_b3.worker',)
    if module not in allowed:
        raise PermissionError('VERIFIED_REPAIR_WORKER_MODULE_REQUIRED')
    if row.get('restart_from_zero'):
        reset=zero_start_authorization(row['campaign_root'],row)
        if (zero_start_authorization(row['campaign_root'],request)!=reset
                or request.get('reset_authorization')!=reset or request.get('previous_attempts',[])!=[]):
            raise PermissionError('RETRY_AUTHORIZED_FRESH_ZERO_REQUEST_REQUIRED')
        if row['arm']=='B2':
            sealed=read(request['manifest'])
            if row['date'] in sealed.get('prior_attempts',{}):
                raise PermissionError('B2_ZERO_START_RETRY_MUST_NOT_CARRY_PRIOR_NATIVE')
        elif request.get('previous_attempts')!=[]:
            raise PermissionError('B3_ZERO_START_RETRY_MUST_NOT_CARRY_PRIOR_NATIVE')
    elif row['arm'] == 'B2':
        sealed = read(request['manifest'])
        carried = sealed.get('prior_attempts', {}).get(row['date'], {})
        if (carried.get('Native_Runtime') != row['original_native_runtime']
                or carried.get('ledger') != row['original_ledger_receipt']
                or carried.get('result') != row['original_result_receipt']):
            raise PermissionError('RECOVERY_ORIGINAL_CUMULATIVE_BUDGET_CARRY_REQUIRED')
    else:
        # B3 carries each optimization stage separately. The real ledger
        # verifies the full prior call prefix, source identity and 5400 cap.
        accounting = b3_stage_accounting(read(row['original_result_receipt']['path']),
            day=row['date'], source=row['original_source_SHA'])
        if (accounting['runtime'] != row['original_stage_native_runtime']
                or accounting['ledgers'] != row['original_stage_ledger_receipts']
                or accounting['identities'] != row['original_stage_ledger_identity_receipts']):
            raise PermissionError('B3_SEALED_STAGE_NATIVE_ACCOUNTING_DRIFT')
        originals = [Path(value).resolve() for value in request.get('previous_attempts', [])]
        if any(not any(Path(receipt['path']).resolve().is_relative_to(value / 'PIPELINE') for value in originals)
                for receipt in accounting['ledgers'].values()):
            raise PermissionError('B3_REPAIR_PRIOR_STAGE_ACCOUNTING_REQUIRED')
    if module == 'v42_b2_seed_recovery_v19.worker':
        if request.get('implementation_SHA') != row['repair_source_SHA']:
            raise PermissionError('RETRY_REQUEST_SOURCE_SHA_DRIFT')
        verifier = ('import json,sys; from v42_b2_seed_recovery_v19.policy import verify_request; '
                    'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); m=verify_request(r); '
                    'assert m["source_commit"]==sys.argv[2]; '
                    'assert not m.get("benchmark_initialization_only"); '
                    'assert not m.get("diagnostics_only"); '
                    'assert m["initialization_native_limit_seconds"]==5400')
    elif module == 'v42_autonomous_b2.worker':
        if request.get('repair_source_SHA', request.get('deployment_SHA', request.get('implementation_SHA'))) != row['repair_source_SHA']:
            raise PermissionError('B2_ADAPTER_DEPLOYMENT_SHA_DRIFT')
        verifier = ('import json,sys; from v42_autonomous_b2.worker import verify_request; '
                    'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); verify_request(r)')
    else:
        # B3's sealed worker admits A1 reuse and the original full model itself;
        # the retry request must bind this immutable source seal explicitly.
        if (not request.get('source_seal') or request.get('repair_source_SHA') != row['repair_source_SHA']
                or request.get('implementation_SHA') != row['repair_source_SHA']
                or request.get('source_SHA') != row['repair_source_SHA']):
            raise PermissionError('B3_RETRY_EXPLICIT_SOURCE_SEAL_REQUIRED')
        verifier = ('import json,sys; from pathlib import Path; '
                    'from v42_autonomous_b3.admission import source_seal,validate_seal,validate_request,execution_permit; '
                    'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); '
                    'validate_request(r); s=source_seal(Path.cwd()); validate_seal(s,Path.cwd()); '
                    'assert s["source_sha"]==r["repair_source_SHA"]==r["implementation_SHA"]==r["source_SHA"]; '
                    'permit=execution_permit(r,s); permit.__enter__(); permit.__exit__(None,None,None)')
    subprocess.run([sys.executable.replace('pythonw.exe', 'python.exe'), '-B', '-X', 'utf8',
                    '-c', verifier, row['retry_request_receipt']['path'], row['repair_commit_SHA']],
                   cwd=code_root, check=True, capture_output=True, text=True)


def _dispatch_ready(root, arm, slot, manifest):
    root = Path(root).resolve()
    if arm not in ('B2', 'B3') or slot not in ((1, 2, 3) if arm == 'B2' else (1,)):
        raise PermissionError('RECOVERY_WORKER_SLOT_INVALID')
    with os_lock(root / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        supervisor = read(root / 'SUPERVISOR_STATE.json', {})
        if _retire_satisfied(doc,supervisor):
            atomic(root/'RECOVERY_QUEUE.json',doc)
        workers = supervisor.get('workers', {})
        active = {value['day'] for value in workers.values() if value.get('arm') == arm}
        if any(value.get('worker_slot') == slot for value in workers.values()):
            return None
        candidates = [row for row in doc['entries'] if row['arm'] == arm
                      and row['date'] not in active and row['verification_status'] in
                      ('READY_VERIFIED_REPAIR', 'DISPATCH_INTENT')]
        candidates.sort(key=lambda row: (-row['retry_priority'], row['queued_UTC']))
        if not candidates:
            return None
        row = next((candidate for candidate in candidates
                    if candidate['verification_status'] == 'DISPATCH_INTENT'
                    and candidate.get('worker_slot') == slot
                    or candidate['verification_status'] == 'READY_VERIFIED_REPAIR'
                    and (str(slot) in candidate.get('retry_request_receipts_by_slot', {})
                         or read(candidate['retry_request_receipt']['path'])['worker_slot'] == slot)), None)
        if row is None:
            return None
        if row['verification_status'] == 'READY_VERIFIED_REPAIR':
            alternate = row.get('retry_request_receipts_by_slot', {}).get(str(slot))
            if alternate:
                row['retry_request_receipt'] = alternate
        path = Path(row['retry_request_receipt']['path'])
        request = read(path)
        # Requests are pre-sealed for a slot; wait for that slot without editing.
        if request['worker_slot'] != slot:
            return None
        matches = _request_workers(path)
        if len(matches) > 1:
            raise PermissionError('DUPLICATE_RETRY_WORKER_REQUEST')
        if row['verification_status'] == 'DISPATCH_INTENT':
            if matches:
                worker = matches[0]
            elif Path(request['result']).exists():
                _finish_row(row, request['result'])
                atomic(root / 'RECOVERY_QUEUE.json', doc)
                return None
            else:
                row.update(verification_status='QUARANTINE_DISPATCH_INTERRUPTED',
                           Native_Runtime='UNKNOWN', reconciliation_UTC=now(),
                           reconciliation_reason='PERSISTED_INTENT_WITHOUT_LIVE_MATCH; NEVER_RELAUNCH')
                atomic(root / 'RECOVERY_QUEUE.json', doc)
                return None
        else:
            try:
                _verify_dispatch(row, request)
            except Exception as error:
                if common_failure(error):
                    raise SourceBlocked(str(error)) from error
                denied = path.parent / 'REPAIR_ADMISSION_FAILURE.json'
                atomic(denied, dict(arm=arm, day=row['date'], attempt_id=request['attempt_id'],
                    UTC=now(), status='QUARANTINE', reason=str(error), failure_class=type(error).__name__,
                    Native_Runtime=row['original_native_runtime'], new_attempt_native_runtime=0.,
                    before_Popen=True, before_Native=True, original_result_receipt=row['original_result_receipt'],
                    original_native_accounting_preserved=True))
                row.update(verification_status='QUARANTINE_REPAIR_ADMISSION',
                    admission_failure_receipt=record(denied), admission_failed_UTC=now(),
                    new_attempt_native_runtime=0.)
                atomic(root / 'RECOVERY_QUEUE.json', doc)
                return None
            if matches or Path(request['result']).exists():
                raise PermissionError('RETRY_REQUEST_ALREADY_EXECUTED')
            row.update(verification_status='DISPATCH_INTENT', retry_attempt_id=request['attempt_id'],
                       dispatch_intent_UTC=now(), worker_slot=slot)
            atomic(root / 'RECOVERY_QUEUE.json', doc)
            module = row['worker_module']
            command = [sys.executable.replace('pythonw.exe', 'python.exe'), '-B', '-X',
                       'utf8', '-m', module, str(path)]
            with (path.parent / 'stdout.log').open('ab') as out, (path.parent / 'stderr.log').open('ab') as err:
                child = subprocess.Popen(command, cwd=row['repair_code_root'], stdout=out, stderr=err,
                                         creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.NORMAL_PRIORITY_CLASS) if os.name == 'nt' else 0)
            worker = identity(child.pid)
        worker.update(request=str(path), worker_slot=slot, arm=arm, day=row['date'],
                      source_commit=row['repair_commit_SHA'], source_SHA=row['repair_source_SHA'],
                      recovery_queue_id=row['queue_id'])
        row.update(new_worker_PID=worker['PID'], worker=worker,
                   verification_status='WORKER_ENTERED', dispatched_UTC=now())
        atomic(root / 'RECOVERY_QUEUE.json', doc)
        return worker


def _unstarted_ready(row):
    if (row.get('verification_status')!='READY_VERIFIED_REPAIR'
            or any(row.get(name) for name in ('retry_attempt_id','new_worker_PID','dispatch_intent_UTC',
                                             'worker','worker_slot','launch_intent','popen_returned','dispatched_UTC'))):
        return False
    try:
        receipts=[row['retry_request_receipt'],*row.get('retry_request_receipts_by_slot',{}).values()]
        for receipt in receipts:
            if record(receipt['path'])!=receipt:
                return False
            request=read(receipt['path'])
            attempt=Path(request['result']).parent
            started=[attempt/name for name in ('RESULT.json','NATIVE_RUNTIME_LEDGER.json','progress.json','error.json','output')]
            started.extend(Path(request[name]) for name in ('output','progress','error') if request.get(name))
            if any(path.exists() for path in started) or _request_workers(receipt['path']):
                return False
    except (OSError,KeyError,TypeError,ValueError):return False
    return True


def _supervisor_preserves_unstarted_target(root, target):
    """Permit a new READY while a proved different attempt keeps running.

    This checks ownership only; it never edits the supervisor or a worker.
    The caller holds the queue lock, and _unstarted_ready separately rejects
    every target request/alternate process, dispatch marker and result.
    """
    try:
        cp=read(Path(root)/'SUPERVISOR_STATE.json',{})
        workers=cp.get('workers',{});dates=cp.get('dates',{})
        if not isinstance(workers,dict) or not isinstance(dates,dict):return False
        receipts=[target['retry_request_receipt'],*target.get('retry_request_receipts_by_slot',{}).values()]
        paths={Path(item['path']).resolve() for item in receipts}
        attempts={read(item['path'])['attempt_id'] for item in receipts}
        key=target['arm']+'/'+target['date'];date=dates.get(key,{})
        if not isinstance(date,dict):return False
        def refers(value, *, same_day, pending_list_active=True):
            return (any(value.get(name)==target['queue_id'] for name in
                        ('queue_id','recovery_queue_id','active_recovery_queue_id'))
                or pending_list_active and target['queue_id'] in value.get('retry_queue_ids',[])
                or value.get('request') and Path(value['request']).resolve() in paths
                or same_day and any(value.get(name) in attempts for name in
                                    ('attempt_id','current_attempt','retry_attempt_id')))
        # Explicit ownership of this queue/request is global. Generic
        # attempt names and inactive pending lists are scoped to a date.
        for date_key,date_value in dates.items():
            if not isinstance(date_value,dict):return False
            if date_key!=key and refers(date_value,same_day=False,pending_list_active=False):return False
        # An inactive RETRY_PENDING date lists its READY queue as pending
        # work. That list is not dispatch ownership. All explicit active
        # IDs, current attempts/requests and running/launch lists still block.
        pending_list_active=(key in workers or date.get('status')=='RUNNING'
                             or bool(date.get('launch_intent') or date.get('dispatch_intent_UTC')))
        if refers(date,same_day=True,pending_list_active=pending_list_active):return False
        active=False
        for worker_key,worker in workers.items():
            if not isinstance(worker,dict):return False
            arm,day=worker.get('arm'),worker.get('day')
            if refers(worker,same_day=arm==target['arm'] and day==target['date']):return False
            if (arm not in ('B2','B3') or day not in {f'2025-05-{n:02d}' for n in range(1,32)}
                    or worker_key!=arm+'/'+day):return False
            if worker_key!=key:continue
            active=True
            path=Path(worker['request']).resolve();request=read(path)
            attempt=request.get('attempt_id');source=request.get('implementation_SHA')
            expected=Path(root).resolve()/'dates'/arm/day/'attempts'/str(attempt)
            if (not attempt or attempt in attempts or path!=expected/'request.json'
                    or request.get('arm')!=arm or request.get('day')!=day
                    or not _sha(source,64)
                    or worker.get('source_SHA')!=source or type(worker.get('PID')) is not int
                    or worker.get('PID',0)<=0 or not alive(worker)
                    or worker.get('launch_intent') or worker.get('dispatch_intent_UTC')
                    or not worker.get('command') or Path(worker['command'][-1]).resolve()!=path
                    or '-m' not in worker['command']
                    or worker['command'][worker['command'].index('-m')+1]!=target.get('worker_module')
                    or worker.get('worker_slot')!=request.get('worker_slot')
                    or type(worker.get('worker_slot')) is not int
                    or worker.get('worker_slot') not in ((1,2,3) if arm=='B2' else (1,))
                    or Path(request['result']).resolve()!=expected/'RESULT.json'
                    or date.get('status')!='RUNNING' or date.get('current_attempt')!=attempt
                    or not date.get('request') or Path(date['request']).resolve()!=path
                    or date.get('source_SHA')!=source):return False
        if not active and date.get('status')=='RUNNING':return False
    except (OSError,KeyError,TypeError,ValueError,AttributeError,IndexError):return False
    return True


def _current_verified_pass(doc,cp,key):
    """Require the current sealed scientific/accounting recovery result again."""
    current=cp.get('dates',{}).get(key,{})
    if current.get('status')!='PASS' or key in cp.get('workers',{}):
        return None
    try:
        result_receipt=record(current['result'])
        if current.get('result_SHA')!=result_receipt['sha256']:
            return None
        result=read(current['result']);request=read(current['request'])
        identity=result.get('identity',{})
        if (request.get('arm')+'/'+request.get('day')!=key
                or current.get('current_attempt')!=request.get('attempt_id')
                or Path(request['result']).resolve()!=Path(current['result']).resolve()
                or current.get('source_SHA')!=request.get('implementation_SHA')
                or current.get('Native_Runtime')!=result.get('Native_Runtime')
                or 'run_id' in request and identity.get('run_id')!=request['run_id']
                or identity.get('attempt_id')!=current['current_attempt']):
            return None
        terminal=next((entry for entry in doc['entries'] if
            entry.get('verification_status')=='RECOVERY_PASS'
            and entry.get('arm')+'/'+entry.get('date')==key
            and entry.get('repair_source_SHA')==current['source_SHA']
            and entry.get('final_result_receipt')==result_receipt
            and Path(entry['retry_request_receipt']['path']).resolve()==Path(current['request']).resolve()),None)
        if terminal is None or record(terminal['retry_request_receipt']['path'])!=terminal['retry_request_receipt']:
            return None
        receipts=[terminal['validation_receipt'],*terminal['source_files']]
        if any(record(item['path'])!=item for item in receipts):
            return None
        sealed=[terminal.get('final_ledger_receipt')] if terminal['arm']=='B2' else [
            *terminal.get('final_stage_ledger_receipts',{}).values(),
            *terminal.get('final_stage_ledger_identity_receipts',{}).values()]
        if not sealed or any(not item or record(item['path'])!=item for item in sealed):
            return None
        verified=_finish_row(dict(terminal),current['result'])
        if verified['verification_status']!='RECOVERY_PASS':
            return None
        return dict(queue_id=terminal['queue_id'],request=terminal['retry_request_receipt'],
            result=result_receipt,source_SHA=current['source_SHA'],attempt_id=current['current_attempt'],
            native_accounting=verified['final_native_accounting'],scientific_PASS=True)
    except (PermissionError,OSError,KeyError,TypeError,ValueError):
        return None


def _retire_satisfied(doc,cp):
    changed=False
    for row in doc['entries']:
        if row.get('verification_status')!='READY_VERIFIED_REPAIR':continue
        key=row['arm']+'/'+row['date']
        proof=_current_verified_pass(doc,cp,key)
        if proof is not None and _unstarted_ready(row):
            row.update(verification_status='RETIRED_CURRENT_VERIFIED_PASS',retired_UTC=now(),
                retirement_reason='CURRENT_SEALED_SCIENTIFIC_AND_ACCOUNTING_VERIFIED_PASS',
                current_PASS_evidence=proof,original_prepared_repair_and_failure_evidence_preserved=True)
            changed=True
    return changed


def retire_satisfied_ready(root,cp):
    with os_lock(Path(root)/'RECOVERY_QUEUE.lock'):
        doc=queue(root)
        if _retire_satisfied(doc,cp):
            doc['UTC']=now();atomic(Path(root)/'RECOVERY_QUEUE.json',doc)
        return doc


def mark_dispatched(root, queue_id, attempt_id, worker, *, source_SHA):
    if not attempt_id or not alive(worker):
        raise PermissionError('REAL_RETRY_WORKER_REQUIRED')
    with os_lock(Path(root) / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        row = next(row for row in doc['entries'] if row['queue_id'] == queue_id)
        if row['repair_source_SHA'] != source_SHA:
            raise PermissionError('RETRY_REPAIR_SOURCE_SHA_DRIFT')
        if row['verification_status'] != 'READY_VERIFIED_REPAIR':
            raise PermissionError('RETRY_ALREADY_DISPATCHED')
        if attempt_id == row['original_attempt_id']:
            raise PermissionError('FRESH_RETRY_ATTEMPT_REQUIRED')
        row.update(retry_attempt_id=attempt_id, new_worker_PID=worker['PID'],
                   worker=worker, verification_status='WORKER_ENTERED',
                   dispatched_UTC=now())
        atomic(Path(root) / 'RECOVERY_QUEUE.json', doc)
        return row


def mark_verified(root, queue_id, evidence):
    """An admission request or PID alone is never a successful recovery."""
    required = ('source_admission_PASS', 'model_generation_PASS', 'Native_entered',
                'heartbeat_progress_PASS', 'ledger_progress_PASS')
    if any(evidence.get(key) is not True for key in required):
        raise PermissionError('REAL_RETRY_NATIVE_PROGRESS_EVIDENCE_REQUIRED')
    receipts = evidence.get('receipts', [])
    if not receipts or any(record(r['path']) != r for r in receipts):
        raise PermissionError('RETRY_EVIDENCE_SHA_DRIFT')
    with os_lock(Path(root) / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        row = next(row for row in doc['entries'] if row['queue_id'] == queue_id)
        if row['verification_status'] != 'WORKER_ENTERED':
            raise PermissionError('RETRY_WORKER_ENTRY_REQUIRED')
        row.update(verification_status='NATIVE_PROGRESS_VERIFIED',
                   verification=evidence, verified_UTC=now())
        atomic(Path(root) / 'RECOVERY_QUEUE.json', doc)
        return row


def _finish_row(row, result_path):
    """Preserve exact terminal evidence; a broken ledger remains quarantine."""
    result_path = Path(result_path).resolve()
    request = read(row['retry_request_receipt']['path'])
    if result_path != Path(request['result']).resolve():
        raise PermissionError('RECOVERY_TERMINAL_RESULT_PATH_DRIFT')
    result = read(result_path)
    actual_identity = result.get('identity', {})
    source = result.get('source_SHA', result.get('source_sha', actual_identity.get('source_SHA')))
    if (actual_identity.get('day') != row['date'] or actual_identity.get('arm') != row['arm']
            or actual_identity.get('attempt_id') != request['attempt_id']
            or source != row['repair_source_SHA']):
        raise PermissionError('RECOVERY_TERMINAL_IDENTITY_OR_SOURCE_DRIFT')
    row.update(final_result_receipt=record(result_path), finished_UTC=now(),
               final_result_status=result.get('status'), final_PASS=result.get('PASS') is True,
               final_Native_Runtime=result.get('Native_Runtime'))
    if (result.get('status')=='PASS') != (result.get('PASS') is True):
        row.update(verification_status='QUARANTINE_TERMINAL_POLICY',final_PASS=False,
            final_policy_error='RESULT_PASS_STATUS_DISAGREEMENT')
        return row
    if row['arm'] == 'B2':
        ledger_path = result_path.parent / 'NATIVE_RUNTIME_LEDGER.json'
        ledger = read(ledger_path, {})
        runtime = ledger.get('measured_Native_Runtime')
        measured = (type(runtime) in (int, float) and math.isfinite(runtime)
                    and runtime >= (0. if row.get('restart_from_zero') else row['original_native_runtime'])
                    and result.get('Native_Runtime') == runtime
                    and ledger.get('inflight') is None
                    and not any(call.get('runtime_unavailable') or call.get('entered_native') is not True
                                or type(call.get('Native_Runtime')) not in (int,float)
                                or not math.isfinite(call['Native_Runtime']) or call['Native_Runtime'] < 0
                                for call in ledger.get('calls', [])))
        if measured:
            carried=(ledger.get('prior_attempt') or {}).get('Native_Runtime',0.)
            measured=(type(carried) in (int,float) and carried>=0 and
                carried+sum(call['Native_Runtime'] for call in ledger.get('calls',[]))==runtime)
            if row.get('restart_from_zero'):measured=measured and carried==0.
        if ledger_path.exists():
            row['final_ledger_receipt'] = record(ledger_path)
        if not measured:
            row.update(verification_status='QUARANTINE_TERMINAL_ACCOUNTING',
                       final_native_accounting='UNKNOWN_OR_UNVERIFIED', final_PASS=False)
            return row
        row.update(final_native_accounting='MEASURED_CUMULATIVE',
                   final_remaining_native_seconds=max(0., row['native_budget_seconds'] - runtime))
        if result.get('PASS') is True and (runtime > row['native_budget_seconds']
                or result.get('benchmark_initialization_only') or result.get('scientific_PASS') is not True):
            row.update(verification_status='QUARANTINE_TERMINAL_POLICY', final_PASS=False)
            return row
    else:
        try:
            prior = None if row.get('restart_from_zero') else b3_stage_accounting(read(row['original_result_receipt']['path']),
                day=row['date'], source=row['original_source_SHA'])
            final = b3_stage_accounting(result, day=row['date'], source=row['repair_source_SHA'], previous=prior)
        except (PermissionError, OSError, KeyError, TypeError, ValueError) as error:
            row.update(verification_status='QUARANTINE_TERMINAL_ACCOUNTING',
                       final_native_accounting='UNKNOWN_OR_UNVERIFIED', final_PASS=False,
                       final_accounting_error=str(error))
            return row
        row.update(final_native_accounting='MEASURED_STAGE_CUMULATIVE',
                   final_stage_native_runtime=final['runtime'], final_stage_native_calls=final['counts'],
                   final_stage_ledger_receipts=final['ledgers'], final_stage_ledger_identity_receipts=final['identities'],
                   final_remaining_native_seconds_by_stage={stage:max(0.,5400-value) for stage,value in final['runtime'].items()})
        stages = result.get('stages', {})
        if result.get('PASS') is True and (set(stages) != set(B3_STAGES) or result.get('status') != 'PASS'
                or request.get('prepare_only') or any(not _measured(stage.get('native_seconds'))
                or stage['native_seconds'] > 5400
                or stage.get('original_integer_physical_verified') is not True
                or stage.get('independent_global_verified') is not True for stage in stages.values())
                or any(stages[stage]['native_seconds'] != final['runtime'][stage] for stage in B3_STAGES)):
            row.update(verification_status='QUARANTINE_TERMINAL_POLICY', final_PASS=False)
            return row
    row['verification_status'] = 'RECOVERY_PASS' if row['final_PASS'] and result.get('status') == 'PASS' else 'RECOVERY_FAILED'
    return row


def mark_finished(root, queue_id, result_path):
    with os_lock(Path(root) / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        row = next(row for row in doc['entries'] if row['queue_id'] == queue_id)
        if row['verification_status'] in ('RECOVERY_PASS', 'RECOVERY_FAILED',
                                          'QUARANTINE_TERMINAL_ACCOUNTING', 'QUARANTINE_TERMINAL_POLICY'):
            if row.get('final_result_receipt') != record(result_path):
                raise PermissionError('RECOVERY_TERMINAL_RESULT_NEVER_OVERWRITTEN')
            return row
        _finish_row(row, result_path)
        atomic(Path(root) / 'RECOVERY_QUEUE.json', doc)
        return row


def _frozen_observation(root, queue_id, kind, path, *, raw=None):
    """Capture mutable progress once into immutable recovery evidence."""
    path = Path(path)
    raw = path.read_bytes() if raw is None else raw
    snapshot = Path(root) / 'recovery_evidence' / queue_id / (kind + '_' + uuid.uuid4().hex + '.json')
    document = dict(observed_UTC=now(), source_path=str(path.resolve()),
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    snapshot=json.loads(raw.decode('utf-8-sig')))
    atomic(snapshot, document)
    return record(snapshot)


def _owned_worker_heartbeat(root, worker, row, request, path):
    attempt = Path(root).resolve() / 'dates' / row['arm'] / row['date'] / 'attempts' / request['attempt_id']
    receipt = row['retry_request_receipt']
    expected = attempt / 'HEARTBEAT.json' if row['arm'] == 'B2' else Path(request['output']).resolve() / 'HEARTBEAT.json'
    b3_output = (Path(row['repair_code_root']).resolve() / 'runtime/b3' / request['run_id'] / row['date'] / request['attempt_id']) if row['arm'] == 'B3' else None
    if (row['arm'] not in ('B2', 'B3') or request.get('arm') != row['arm']
            or request.get('day') != row['date']
            or request.get('attempt_id') != row['retry_attempt_id']
            or request.get('implementation_SHA') != row['repair_source_SHA']
            or Path(request['result']).resolve().parent != attempt
            or Path(worker['request']).resolve() != attempt / 'request.json'
            or Path(receipt['path']).resolve() != attempt / 'request.json'
            or record(receipt['path']) != receipt or path != expected
            or b3_output is not None and Path(request['output']).resolve() != b3_output):
        raise PermissionError('WORKER_HEARTBEAT_OBSERVATION_OWNERSHIP_OR_SEAL_DRIFT')


def _read_worker_heartbeat(root, worker, row, request, path):
    """Only an exact sealed worker heartbeat may defer a Windows access failure.

    The errno alone cannot prove an atomic replacement race. Preserve that
    uncertainty; persistent access failures belong to operational observation
    history, never to a fabricated empty heartbeat or Native accounting.
    """
    path = Path(path).resolve()
    _owned_worker_heartbeat(root, worker, row, request, path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    except PermissionError as error:
        if (sys.platform != 'win32' or error.errno != 13
                or getattr(error, 'winerror', None) not in (None, 5, 32, 33)
                or not error.filename or Path(error.filename).resolve() != path):
            raise
        raise HeartbeatObservationDeferred(path, error) from error
    return json.loads(raw.decode('utf-8-sig')), raw


def sync_worker(root, worker):
    """Record Native progress without changing the running worker or source."""
    queue_id = worker.get('recovery_queue_id')
    if not queue_id:
        return None
    row = next(row for row in queue(root)['entries'] if row['queue_id'] == queue_id)
    if row['verification_status'] != 'WORKER_ENTERED' or not alive(worker):
        return row
    request = read(worker['request'])
    attempt = Path(request['result']).parent
    heartbeat_path = attempt / 'HEARTBEAT.json' if row['arm'] == 'B2' else Path(request['output']) / 'HEARTBEAT.json'
    progress_path = Path(request['progress'])
    heartbeat, heartbeat_raw = _read_worker_heartbeat(root, worker, row, request, heartbeat_path)
    if heartbeat is None:
        return row
    progress = read(progress_path, {})
    if (heartbeat.get('timestamp_UTC', '') <= row.get('dispatched_UTC', '')
            or progress.get('attempt_id', progress.get('identity', {}).get('attempt_id')) != request['attempt_id']):
        return HeartbeatObservationRead(row)
    if row['arm'] == 'B2':
        model_path = Path(request['output']) / 'V19_MODEL_IDENTITY_VERIFICATION.json'
        ledger_path = attempt / 'NATIVE_RUNTIME_LEDGER.json'
        model = read(model_path, {})
        ledger = read(ledger_path, {})
        new_calls = [call for call in ledger.get('calls', []) if call.get('entered_native') is True]
        native_progress = (type(progress.get('Native_Runtime')) in (int, float)
                           and progress['Native_Runtime'] > ledger.get('measured_Native_Runtime', math.inf))
        if model.get('PASS') is not True or not (new_calls or ledger.get('inflight') and native_progress):
            return HeartbeatObservationRead(row)
        paths = [('model', model_path), ('ledger', ledger_path), ('progress', progress_path), ('heartbeat', heartbeat_path)]
    else:
        output = Path(request['output'])
        admission = output / 'B3_SOURCE_ADMISSION.json'
        admitted = read(admission, {})
        stage = heartbeat.get('stage')
        ledger_path = output / 'PIPELINE' / str(stage) / 'NATIVE_RUNTIME_LEDGER.json'
        ledger = read(ledger_path, {})
        if (admitted.get('PASS') is not True or admitted.get('source_sha') != row['repair_source_SHA']
                or stage not in ('M1', 'A2', 'M2') or not ledger.get('calls')):
            return HeartbeatObservationRead(row)
        paths = [('admission', admission), ('ledger', ledger_path), ('progress', progress_path), ('heartbeat', heartbeat_path)]
    receipts = [_frozen_observation(root, queue_id, kind, path,
                    raw=heartbeat_raw if kind == 'heartbeat' else None) for kind, path in paths]
    evidence = dict(source_admission_PASS=True, model_generation_PASS=True, Native_entered=True,
                    heartbeat_progress_PASS=True, ledger_progress_PASS=True, receipts=receipts)
    return HeartbeatObservationRead(mark_verified(root, queue_id, evidence))


def reconcile_workers(root):
    """Recover queue-owned workers lost between Popen and supervisor save."""
    adopted = []
    with os_lock(Path(root) / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        changed = False
        for row in doc['entries']:
            if row['verification_status'] not in ('DISPATCH_INTENT', 'WORKER_ENTERED', 'NATIVE_PROGRESS_VERIFIED'):
                continue
            path = row['retry_request_receipt']['path']
            matches = _request_workers(path)
            if len(matches) > 1:
                raise PermissionError('MULTIPLE_RECOVERY_WORKERS_SAME_REQUEST')
            if matches:
                if record(path)!=row['retry_request_receipt']:
                    raise PermissionError('RECOVERY_ORPHAN_REQUEST_SHA_DRIFT')
                request = read(path)
                worker = dict(matches[0], request=path, worker_slot=request['worker_slot'],
                              arm=row['arm'], day=row['date'], source_commit=row['repair_commit_SHA'],
                              source_SHA=row['repair_source_SHA'], recovery_queue_id=row['queue_id'])
                adopted.append(worker)
                row.update(worker=worker, new_worker_PID=worker['PID'], reconciled_UTC=now())
                if row['verification_status'] == 'DISPATCH_INTENT':
                    row['verification_status'] = 'WORKER_ENTERED'
                changed = True
            else:
                request = read(path)
                if Path(request['result']).exists():
                    _finish_row(row, request['result'])
                else:
                    row.update(verification_status='QUARANTINE_DISPATCH_INTERRUPTED',
                               final_native_accounting='UNKNOWN', reconciled_UTC=now())
                changed = True
        if changed:
            atomic(Path(root) / 'RECOVERY_QUEUE.json', doc)
    return adopted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('begin', 'end', 'guard', 'status', 'enqueue'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--token')
    parser.add_argument('--owner-pid', type=int)
    parser.add_argument('--owner-file')
    parser.add_argument('--failure-file')
    parser.add_argument('--repair-file')
    args = parser.parse_args()
    if args.action == 'begin':
        value = begin(args.root, owner_pid=args.owner_pid)
    elif args.action == 'end':
        value = end(args.root, args.token)
    elif args.action == 'guard':
        guard(args.root, args.token, owner=read(args.owner_file) if args.owner_file else None)
        value = dict(released=True)
    elif args.action == 'enqueue':
        value = enqueue(args.root, read(args.failure_file), read(args.repair_file), lease_token=args.token)
    else:
        value = dict(lease=read(Path(args.root) / 'REPAIR_LEASE.json'), recovery=queue(args.root))
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
