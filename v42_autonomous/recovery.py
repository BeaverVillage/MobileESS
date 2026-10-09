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
        os.replace(temporary, path)
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


def enqueue(root, failure, repair, *, lease_token):
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
    consumed = failure['original_native_runtime']
    if (isinstance(consumed, bool) or not isinstance(consumed, (int, float))
            or not math.isfinite(consumed) or consumed < 0
            or failure.get('budget_basis') == 'CONSERVATIVE_LOST_CALL_WINDOW'
            or failure.get('runtime_unknown') or failure.get('quarantined')):
        raise PermissionError('UNKNOWN_NATIVE_RUNTIME_NO_AUTOMATIC_RETRY')
    limit = failure.get('native_budget_seconds', 5400)
    if isinstance(limit, bool) or limit != 5400:
        raise ValueError('RECOVERY_NATIVE_BUDGET_REQUIRED')
    if consumed >= limit:
        raise PermissionError('EXHAUSTED_NATIVE_BUDGET_NO_AUTOMATIC_RETRY')
    original_receipts = {}
    for name in ('original_result_receipt', 'original_ledger_receipt'):
        receipt = failure.get(name)
        if not receipt or record(receipt['path']) != receipt:
            raise PermissionError('ORIGINAL_FAILURE_RECEIPT_REQUIRED:' + name)
        original_receipts[name] = receipt
    original_result = read(original_receipts['original_result_receipt']['path'])
    ledger = read(original_receipts['original_ledger_receipt']['path'])
    measured = ledger.get('measured_Native_Runtime', ledger.get('measured_native_runtime'))
    if (original_result.get('PASS') is True or original_result.get('Native_Runtime') != consumed
            or measured != consumed or ledger.get('inflight') is not None
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
    code_root = repair.get('repair_code_root')
    if not code_root or not request_receipt or record(request_receipt['path']) != request_receipt:
        raise PermissionError('SEALED_FRESH_RETRY_REQUEST_REQUIRED')
    request = read(request_receipt['path'])
    if (request.get('arm') != failure['arm'] or request.get('day') != failure['date']
            or request.get('attempt_id') == failure['original_attempt_id']
            or not request.get('attempt_id') or Path(request['result']).exists()):
        raise PermissionError('RETRY_REQUEST_IDENTITY_OR_EXISTING_RESULT_DRIFT')
    retry_dir = Path(request['result']).resolve().parent
    expected = root / 'dates' / failure['arm'] / failure['date'] / 'attempts' / request['attempt_id']
    if retry_dir != expected or Path(request_receipt['path']).resolve() != expected / 'request.json':
        raise PermissionError('NEW_RETRY_ATTEMPT_DIRECTORY_REQUIRED')
    with os_lock(root / 'RECOVERY_QUEUE.lock'):
        doc = queue(root)
        key = (failure['arm'], failure['date'], failure['original_attempt_id'], source)
        for row in doc['entries']:
            if (row['arm'], row['date'], row['original_attempt_id'], row['repair_source_SHA']) == key:
                return row
        row = {key: failure[key] for key in REQUIRED_FAILURE}
        row.update(queue_id=uuid.uuid4().hex, repair_commit_SHA=commit,
                   repair_source_SHA=source, repair_reason=repair['repair_reason'],
                   retry_priority=priority, retry_attempt_id=None, new_worker_PID=None,
                   verification_status='READY_VERIFIED_REPAIR', queued_UTC=now(),
                   validation_receipt=receipt, source_files=sources,
                   native_budget_seconds=limit,
                   remaining_native_seconds=limit - consumed,
                   **original_receipts,
                   worker_module=repair.get('worker_module',
                       'v42_b2_seed_recovery_v19.worker' if failure['arm'] == 'B2' else 'v42_autonomous_b3.worker'),
                   retry_request_receipt=request_receipt, repair_code_root=str(Path(code_root).resolve()))
        _verify_dispatch(row, request)
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
    if (record(row['retry_request_receipt']['path']) != row['retry_request_receipt']
            or any(record(r['path']) != r for r in row['source_files'])
            or any(record(row[name]['path']) != row[name] for name in
                   ('original_result_receipt', 'original_ledger_receipt'))
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
        if request.get('repair_source_SHA', request.get('deployment_SHA')) != row['repair_source_SHA']:
            raise PermissionError('B2_ADAPTER_DEPLOYMENT_SHA_DRIFT')
        verifier = ('import json,sys; from v42_autonomous_b2.worker import verify_request; '
                    'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); verify_request(r)')
    else:
        # B3's sealed worker admits A1 reuse and the original full model itself;
        # the retry request must bind this immutable source seal explicitly.
        if request.get('repair_source_SHA') != row['repair_source_SHA']:
            raise PermissionError('B3_RETRY_EXPLICIT_SOURCE_SEAL_REQUIRED')
        verifier = ('import json,sys; from pathlib import Path; '
                    'from v42_autonomous_b3.admission import source_seal,validate_seal,validate_request,execution_permit; '
                    'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); '
                    'validate_request(r); s=source_seal(Path.cwd()); validate_seal(s,Path.cwd()); '
                    'assert s["source_sha"]==r["repair_source_SHA"]; '
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
        row = candidates[0]
        path = Path(row['retry_request_receipt']['path'])
        request = read(path)
        _verify_dispatch(row, request)
        # Requests are pre-sealed for a slot; wait for that slot without editing.
        if request['worker_slot'] != slot:
            return None
        matches = _request_workers(path)
        if len(matches) > 1:
            raise PermissionError('DUPLICATE_RETRY_WORKER_REQUEST')
        if row['verification_status'] == 'DISPATCH_INTENT':
            if matches:
                worker = matches[0]
            else:
                row.update(verification_status='QUARANTINE_DISPATCH_INTERRUPTED',
                           Native_Runtime='UNKNOWN', reconciliation_UTC=now(),
                           reconciliation_reason='PERSISTED_INTENT_WITHOUT_LIVE_MATCH; NEVER_RELAUNCH')
                atomic(root / 'RECOVERY_QUEUE.json', doc)
                return None
        else:
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
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            worker = identity(child.pid)
        worker.update(request=str(path), worker_slot=slot, arm=arm, day=row['date'],
                      source_commit=row['repair_commit_SHA'], source_SHA=row['repair_source_SHA'],
                      recovery_queue_id=row['queue_id'])
        row.update(new_worker_PID=worker['PID'], worker=worker,
                   verification_status='WORKER_ENTERED', dispatched_UTC=now())
        atomic(root / 'RECOVERY_QUEUE.json', doc)
        return worker


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
