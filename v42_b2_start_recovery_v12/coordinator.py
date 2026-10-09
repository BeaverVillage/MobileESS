"""Single-worker B1 then three-worker B2 with durable date/slot identities.

No optimizer is implemented here. A worker executes one independent arm/date.
A dead attempt is terminal, never retried; a live orphan is adopted by identity.
"""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from pathlib import Path
import csv
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import psutil

from v42_pr134_b1.common import atomic, table, read, sha, digest, record, process, same_process, now, ROOT
from .storage import save_checkpoint
from .policy import MANIFEST, ATTEMPT, RETRY_DATES, attempt_path

DAYS = tuple(f'2025-05-{n:02d}' for n in range(1, 32))
AXIS = tuple((arm, day) for arm in ('B1', 'B2') for day in DAYS)
TERMINAL = frozenset({
    'PASS', 'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED', 'TIME_LIMIT_NO_VALID_INCUMBENT',
    'INFEASIBLE_PROVEN', 'INCONCLUSIVE', 'PHYSICAL_FAILURE', 'INPUT_FAILURE',
    'IMPLEMENTATION_FAILURE', 'OS_RESOURCE_FAILURE', 'FRESH_AC_FAILURE',
    'VALIDATION_FAILURE', 'NUMERICAL_FAILURE', 'INTERRUPTED_NO_VALID_RESULT',
})
_telemetry_processes = {}


def key(arm, day):
    return arm + '/' + day


def runtime_path(root):
    root = Path(root).resolve()
    if root.drive.upper() != 'D:':
        raise PermissionError('CAMPAIGN_WRITES_REQUIRE_D_DRIVE')
    return root


@contextmanager
def os_lock(path):
    """Use the shared campaign port of the prior Windows byte lock."""
    from .common import exclusive_lock, LockBusy
    with ExitStack() as stack:
        try:
            stack.enter_context(exclusive_lock(path))
        except LockBusy:
            yield False
        else:
            yield True


def load_manifest(root, *, verify=True):
    root = runtime_path(root)
    manifest = read(root / MANIFEST)
    if not manifest.get('run_id'):
        raise PermissionError('CAMPAIGN_RUN_ID_REQUIRED')
    supplied = manifest.get('axis', manifest.get('arm_dates'))
    if supplied is not None:
        axis = [(r['arm'], r['day']) if isinstance(r, dict) else tuple(r) for r in supplied]
        if axis != list(AXIS):
            raise PermissionError('B1_THEN_B2_62_DATE_AXIS_REQUIRED')
    if verify:
        # The authorized scientific/date adapter authority is owned by the new
        # common port. The legacy launch guard is intentionally never called.
        from .common import verify_manifest
        verify_manifest(root / MANIFEST, require_preflight=True)
    return manifest


def load_checkpoint(root, manifest):
    root = Path(root)
    path = root / 'CHECKPOINT_V12.json'
    if path.is_file():
        try:
            checkpoint = read(path)
        except (ValueError, OSError) as error:
            backup = root / 'CHECKPOINT_V12_PREVIOUS.json'
            receipt = root / 'CHECKPOINT_V12_PREVIOUS_SHA.json'
            if not backup.is_file() or not receipt.is_file() or sha(backup) != read(receipt)['sha256']:
                raise ValueError('CORRUPT_CHECKPOINT_NO_VERIFIED_BACKUP') from error
            damaged = root / ('CHECKPOINT_CORRUPT_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json')
            path.replace(damaged)
            checkpoint = read(backup)
            atomic(path, checkpoint)
    else:
        from .storage import initialize_checkpoint
        checkpoint = initialize_checkpoint(root, manifest)
    expected = [key(arm, day) for arm, day in AXIS]
    if checkpoint.get('run_id') != manifest['run_id'] or list(checkpoint.get('dates', {})) != expected:
        raise PermissionError('CHECKPOINT_RUN_OR_ARM_DATE_AXIS_DRIFT')
    for arm, day in AXIS:
        row = checkpoint['dates'][key(arm, day)]
        if row.get('arm') != arm or row.get('day') != day or row.get('attempts', 0) not in (0, 1):
            raise PermissionError('CHECKPOINT_ARM_DATE_OR_NO_RETRY_DRIFT')
        if row.get('status') not in TERMINAL | {'PENDING', 'RUNNING'}:
            raise PermissionError('CHECKPOINT_UNKNOWN_DATE_STATUS')
    return checkpoint


def counts(checkpoint, arm=None):
    rows = [r for r in checkpoint['dates'].values() if arm is None or r['arm'] == arm]
    return dict(total=len(rows), completed=sum(r['status'] in TERMINAL for r in rows),
                PASS=sum(r['status'] == 'PASS' for r in rows),
                TIMEOUT=sum(r['status'].startswith('TIME_LIMIT_') for r in rows),
                FAIL=sum(r['status'] in TERMINAL and r['status'] != 'PASS'
                         and not r['status'].startswith('TIME_LIMIT_') for r in rows),
                pending=sum(r['status'] not in TERMINAL for r in rows))


def ensure_phase(checkpoint, arm):
    if arm == 'B2' and counts(checkpoint, 'B1')['completed'] != 31:
        raise PermissionError('B2_CANNOT_BEGIN_BEFORE_ALL_B1_TERMINAL')


def worker_limit(arm):
    return 1 if arm == 'B1' else 3


def read_actives(root):
    path = Path(root) / 'ACTIVES_V12.json'
    if path.is_file():
        value = read(path)
        if value.get('schema') != 'V42_MAY_ACTIVE_WORKER_SLOTS_V2' or not isinstance(value.get('workers'), dict):
            raise PermissionError('ACTIVE_WORKER_SLOTS_SCHEMA_REQUIRED')
        return value['workers']
    legacy = Path(root) / 'ACTIVE_V12.json'
    value = read(legacy) if legacy.is_file() else {}
    return {key(value['arm'], value['day']): value} if value.get('request') else {}


def persist_actives(root, manifest, actives):
    ordered = {name: actives[name] for name in sorted(actives)}
    atomic(root / 'ACTIVES_V12.json', dict(schema='V42_MAY_ACTIVE_WORKER_SLOTS_V2',
           run_id=manifest['run_id'], workers=ordered, updated_UTC=now()))
    atomic(root / 'ACTIVE_V12.json', next(iter(ordered.values()), {}))


def validate_slots(checkpoint, actives):
    arms = {a['arm'] for a in actives.values()}
    if len(arms) > 1:
        raise PermissionError('B1_B2_WORKER_OVERLAP_FORBIDDEN')
    if not arms:
        return
    arm = next(iter(arms)); ensure_phase(checkpoint, arm)
    slots = [a.get('worker_slot', 1) for a in actives.values()]
    if (len(slots) > worker_limit(arm) or len(set(slots)) != len(slots)
            or any(type(slot) is not int or not 1 <= slot <= worker_limit(arm) for slot in slots)):
        raise PermissionError('WORKER_SLOT_LIMIT_OR_DUPLICATE')


def validate_request(root, manifest, request):
    if request.get('policy_version') in ('NATIVE90_BUILD_REUSE_V2', 'MAY11_MAY19_RECOVERY_V5', 'MAY23_BUILD_EFFICIENCY_V6', 'B2_BUILD_INPUT_REUSE_V7_20261009', 'MAY_ALL_DAYS_PRECISION_RECOVERY_V9', 'MAY31_INTEGER_PRECISION_RECOVERY_V10', 'B2_FULL_VALIDATION_NAMESPACE_RECOVERY_V11'):
        from .storage import validate_inherited_request
        return validate_inherited_request(root, manifest, request)
    if request.get('run_id') != manifest['run_id'] or (request.get('arm'), request.get('day')) not in AXIS:
        raise PermissionError('WORKER_REQUEST_RUN_ARM_DATE_DRIFT')
    if Path(request['root']).resolve() != Path(root).resolve():
        raise PermissionError('WORKER_REQUEST_ROOT_DRIFT')
    if Path(request['manifest']).resolve() != Path(root).resolve() / MANIFEST:
        raise PermissionError('WORKER_REQUEST_MANIFEST_PATH_DRIFT')
    expected_input = manifest.get('input_folders', {}).get(
        key(request['arm'], request['day']), str(Path(root) / 'inputs' / request['arm'] / request['day']))
    if Path(request['input_folder']).resolve() != Path(expected_input).resolve():
        raise PermissionError('ARM_DATE_INPUT_FOLDER_MIXING')
    attempt = attempt_path(root, request['arm'], request['day'])
    for name, filename in (('output', 'output'), ('progress', 'progress.json'),
                           ('result', 'RESULT.json'), ('error', 'error.json')):
        if Path(request[name]).resolve() != attempt / filename:
            raise PermissionError('ARM_DATE_OUTPUT_PATH_MIXING:' + name)
    if request.get('manifest_SHA') != sha(Path(root) / MANIFEST):
        raise PermissionError('WORKER_REQUEST_MANIFEST_SHA_DRIFT')
    from .policy import verify_request
    verify_request(request)
    if request.get('wall_budget_seconds') is not None or request.get('native_budget_seconds')!=5400:
        raise PermissionError('WORKER_NATIVE_ONLY_BUDGET_POLICY_DRIFT')
    slot = request.get('worker_slot')
    if type(slot) is not int or not 1 <= slot <= worker_limit(request['arm']):
        raise PermissionError('WORKER_REQUEST_SLOT_OUTSIDE_ARM_LIMIT')
    for name in ('INPUT_IDENTITY.json', 'CASE_IDENTITY.json', 'INDEPENDENT_AIDC_IDENTITY.json', 'B2_FIXED_AIDC.json'):
        path = Path(request['input_folder']) / name
        if path.is_file():
            identity = read(path)
            identity = identity.get('identity', identity)
            if identity.get('arm', request['arm']) != request['arm'] or identity.get('day', request['day']) != request['day']:
                raise PermissionError('ARM_DATE_INPUT_LEDGER_MIXING')


def receipt_valid(root, manifest, request, receipt):
    try:
        identity = receipt.get('identity', receipt)
        if any(identity.get(name) != request[name] for name in ('run_id', 'arm', 'day')):
            return False
        if request.get('attempt_id') and any(identity.get(name)!=request[name] for name in ('attempt_id','algorithm_version')):
            return False
        if receipt.get('status') not in TERMINAL:
            return False
        files = receipt.get('files', [])
        if receipt['status'] == 'PASS' and (receipt.get('PASS') is not True or not files):
            return False
        if not all(Path(r['path']).resolve().is_relative_to(Path(root).resolve()) for r in files):
            return False
        # Only independent immutable file SHA checks run in parallel. Native
        # solver Threads=1, matrix builders and date budgets remain unchanged.
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix='artifact_sha') as pool:
            return all(pool.map(lambda r: sha(r['path']) == r['sha256'], files))
    except (KeyError, TypeError, ValueError, OSError):
        return False


def command_matches(expected, actual):
    if not expected or not actual or len(expected) != len(actual):
        return False
    try:
        return Path(expected[0]).resolve() == Path(actual[0]).resolve() and expected[1:] == actual[1:]
    except (OSError, ValueError):
        return False


def matching_live_worker(request_path):
    """Close the Popen-to-ACTIVE crash window using the exact worker command."""
    matches = []
    request_path = Path(request_path).resolve()
    expected = read(request_path).get('worker_command')
    for candidate in psutil.process_iter(['pid', 'cmdline']):
        try:
            command = candidate.info['cmdline'] or []
            if expected:
                if command_matches(expected, command):
                    matches.append(process(candidate.pid))
                continue
            if 'v42_may_campaign.worker' not in command:
                continue
            position = command.index('v42_may_campaign.worker')
            if position and command[position - 1] == '-m' and len(command) == position + 2:
                if Path(command[-1]).resolve() == request_path:
                    matches.append(process(candidate.pid))
        except (psutil.Error, ValueError, OSError):
            continue
    if len(matches) > 1:
        raise PermissionError('MULTIPLE_LIVE_WORKERS_FOR_SAME_REQUEST')
    return matches[0] if matches else None


def recovery_requests(root, manifest, checkpoint, persisted):
    """Validate every row before recovery can adopt or persist any worker.

    A valid request for another date is still invalid for this checkpoint row.
    Check the complete map first so a later bad row cannot leave a correctly
    running peer partially adopted or its durable checkpoint changed.
    """
    root = Path(root).resolve()
    requests = {}
    for arm, day in AXIS:
        name = key(arm, day)
        row = checkpoint['dates'][name]
        if (row.get('arm'), row.get('day')) != (arm, day):
            raise PermissionError('CHECKPOINT_REQUEST_ROW_ARM_DATE_DRIFT')
        canonical = Path(row['request']) if row.get('request') else attempt_path(root, arm, day)/'request.json'
        active = persisted.get(name, {})
        supplied = row.get('request')
        if row['status'] == 'RUNNING' and not supplied:
            raise PermissionError('CHECKPOINT_RUNNING_REQUEST_MISSING:' + name)
        if supplied and Path(supplied).resolve() != canonical:
            raise PermissionError('CHECKPOINT_REQUEST_PATH_NOT_CANONICAL:' + name)
        if active:
            if (active.get('arm'), active.get('day')) != (arm, day):
                raise PermissionError('ACTIVES_REQUEST_ARM_DATE_DRIFT')
            if Path(active['request']).resolve() != canonical:
                raise PermissionError('ACTIVES_REQUEST_PATH_NOT_CANONICAL:' + name)
        needs_request = bool(supplied or active or row['status'] == 'RUNNING')
        if not needs_request and row['status'] == 'PENDING':
            needs_request = canonical.is_file()
        if not needs_request:
            continue
        if not canonical.is_file():
            raise PermissionError('CHECKPOINT_REQUEST_CANONICAL_FILE_MISSING:' + name)
        request = read(canonical)
        if (request.get('arm'), request.get('day')) != (arm, day):
            raise PermissionError('CHECKPOINT_REQUEST_ARM_DATE_DRIFT:' + name)
        validate_request(root, manifest, request)
        slot = request.get('worker_slot', 1)
        for owner in (row, active):
            if 'worker_slot' in owner and (type(owner['worker_slot']) is not int or owner['worker_slot'] != slot):
                raise PermissionError('CHECKPOINT_REQUEST_WORKER_SLOT_DRIFT:' + name)
        worker = active.get('worker', {})
        if same_process(worker) and not command_matches(request.get('worker_command'), worker.get('command')):
            raise PermissionError('ACTIVE_PROCESS_COMMAND_DOES_NOT_MATCH_REQUEST')
        requests[name] = request
    if set(persisted) - set(checkpoint['dates']):
        raise PermissionError('ACTIVES_CHECKPOINT_DATE_KEY_DRIFT')
    return requests


def recover_actives(root, manifest, checkpoint):
    """Adopt every exact live worker, including each Popen/persistence gap."""
    persisted = read_actives(root)
    document = root / 'ACTIVES_V12.json'
    if document.is_file() and read(document).get('run_id') != manifest['run_id']:
        raise PermissionError('ACTIVES_RUN_ID_DRIFT')
    requests = recovery_requests(root, manifest, checkpoint, persisted)
    recovered = {}
    for name, row in checkpoint['dates'].items():
        attempt = Path(row['request']).parent if row.get('request') else attempt_path(root, row['arm'], row['day'])
        if row['status'] == 'PENDING' and attempt.exists():
            request_path = attempt / 'request.json'
            if not request_path.is_file():
                row.update(status='IMPLEMENTATION_FAILURE', attempts=1,
                           error='INTERRUPTED_BEFORE_ATOMIC_REQUEST', finished_UTC=now())
                save_checkpoint(root, checkpoint); export(root, manifest, checkpoint)
                continue
            row.update(status='RUNNING', attempts=1, request=str(request_path))
        if row['status'] in TERMINAL:
            if same_process(persisted.get(name, {}).get('worker', {})):
                raise PermissionError('LIVE_WORKER_FOR_TERMINAL_DATE')
            continue
        if row['status'] != 'RUNNING':
            continue
        request = requests[name]
        ensure_phase(checkpoint, request['arm'])
        row['started_UTC'] = request['started_UTC']
        active = persisted.get(name, {})
        worker = active.get('worker', {})
        if not same_process(worker):
            worker = matching_live_worker(row['request']) or {}
        if same_process(worker):
            slot = request.get('worker_slot', 1)
            recovered[name] = dict(arm=row['arm'], day=row['day'], request=row['request'],
                worker=worker, worker_slot=slot, started_UTC=request['started_UTC'], adopted=True)
            row.update(attempts=1, worker_slot=slot)
        else:
            finish_attempt(root, manifest, checkpoint, row, request, None, interrupted=True)
    validate_slots(checkpoint, recovered)
    save_checkpoint(root, checkpoint); persist_actives(root, manifest, recovered)
    return recovered


def recover_active(root, manifest, checkpoint):
    """Compatibility reader for the primary worker; recovery itself is plural."""
    return next(iter(recover_actives(root, manifest, checkpoint).values()), {})


def finish_attempt(root, manifest, checkpoint, row, request, exit_code, *, interrupted=False):
    result = Path(request['result'])
    error_path = Path(request['error'])
    if result.is_file():
        try:
            receipt = read(result)
            valid = receipt_valid(root, manifest, request, receipt)
        except (ValueError, OSError):
            valid = False
        if valid:
            row.update(status=receipt['status'], result=str(result), result_SHA=sha(result),
                       summary={k:v for k,v in receipt.items() if k!='files'}, finished_UTC=receipt.get('finished_UTC', now()))
        else:
            row.update(status='IMPLEMENTATION_FAILURE', error='TERMINAL_RECEIPT_IDENTITY_OR_SHA_FAILED',
                       finished_UTC=now())
    elif error_path.is_file():
        try:
            receipt = read(error_path)
            classification = receipt.get('classification', 'IMPLEMENTATION_FAILURE')
            if classification not in TERMINAL or classification == 'PASS':
                classification = 'IMPLEMENTATION_FAILURE'
            row.update(status=classification, error=receipt.get('error', 'WORKER_ERROR'),
                       error_receipt=str(error_path), error_SHA=sha(error_path), finished_UTC=now())
        except (ValueError, OSError) as error:
            row.update(status='IMPLEMENTATION_FAILURE', error='UNREADABLE_WORKER_ERROR:' + str(error), finished_UTC=now())
    else:
        status = 'INTERRUPTED_NO_VALID_RESULT' if interrupted else 'IMPLEMENTATION_FAILURE'
        if exit_code is not None and exit_code & 0xffffffff in (0xc0000017, 0xc000009a):
            status = 'OS_RESOURCE_FAILURE'
        row.update(status=status, error='WORKER_EXIT_WITHOUT_TERMINAL_RECEIPT:' + str(exit_code),
                   finished_UTC=now())
    row['attempts'] = 1
    if row['status'] != 'PASS':
        checkpoint['last_error'] = dict(arm=row['arm'], day=row['day'], status=row['status'],
                                      error=row.get('error', row.get('summary', {}).get('error')), UTC=now())
    save_checkpoint(root, checkpoint)
    export(root, manifest, checkpoint)
    return row['status']


def normalized_summary(row):
    """Map the worker's nested metrics to the established campaign CSV names."""
    receipt = row.get('summary', {})
    values = dict(receipt)
    values.update(receipt.get('fields') or {})
    evaluation = receipt.get('evaluation') or values.get('Fresh_AC') or {}
    ac = evaluation.get('summary') or {}

    def take(*names):
        for name in names:
            if values.get(name) is not None:
                return values[name]
        return None

    gap = take('certified_gap', 'Certified_Gap', 'global_gap')
    target = .005 if row['arm'] == 'B1' else .03
    planning = take('Planning_max_line_loading', 'planning_rho_max')
    result = dict(values)
    result.update(UB=take('UB'), independent_Global_LB=take('independent_Global_LB', 'LB'),
                  wall_seconds=take('optimization_wall_seconds', 'wall_seconds', 'optimization_seconds'),
                  Native_Runtime_seconds=take('Native_Runtime_seconds', 'Native_Runtime'),
                  Fresh_AC_seconds=take('evaluation_wall_seconds', 'Fresh_AC_seconds'),
                  Certified_Gap_percent=100 * gap if isinstance(gap, (int, float)) else None,
                  target_Gap_percent=100 * target, case_SHA=take('case_SHA', 'case_sha'),
                  Planning_max_line_loading=planning,
                  Fresh_AC_max_line_loading=ac.get('rho_max_AC', take('Fresh_AC_max_line_loading')),
                  voltage_violations=ac.get('voltage_violation_count', take('voltage_violations')),
                  current_violations=ac.get('line_current_violation_count', take('current_violations')),
                  Fresh_AC_status='PASS' if evaluation.get('PASS') is True else 'FAIL' if evaluation else 'NOT_RUN',
                  incumbent_valid=take('incumbent_valid') if take('incumbent_valid') is not None else
                    bool(receipt.get('scientific_PASS') or receipt.get('PASS')
                         or row['status'] == 'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'))
    result['P1_certified'] = (take('P1_certified') if take('P1_certified') is not None else
                              bool((receipt.get('scientific_PASS') or receipt.get('PASS'))
                                   and isinstance(gap, (int, float)) and 0 <= gap <= target))
    if result.get('Native_BestBd') is None and row.get('request'):
        ledger_path = Path(row['request']).parent / 'NATIVE_RUNTIME_LEDGER.json'
        if ledger_path.is_file():
            calls = read(ledger_path).get('calls', [])
            if calls:
                result['Native_BestBd'] = calls[-1].get('Native_BestBd')
    return result


def export(root, manifest, checkpoint):
    rows = []
    for row in checkpoint['dates'].values():
        if row['status'] not in TERMINAL:
            continue
        rows.append(dict(row, **{k: v for k, v in normalized_summary(row).items()
                                if k not in row and k not in ('files', 'identity')}))
    table(root / 'V12_DATE_ARM_RESULTS.csv', rows,
          ['day', 'arm', 'status', 'attempts', 'result_SHA', 'incumbent_valid', 'P1_certified', 'case_SHA', 'error'])
    table(root / 'V12_DATE_ARM_RUNTIME.csv', rows,
          ['day', 'arm', 'wall_seconds', 'Native_Runtime_seconds', 'Fresh_AC_seconds', 'Native_calls'])
    table(root / 'V12_DATE_ARM_GAP.csv', rows,
          ['day', 'arm', 'UB', 'Native_BestBd', 'independent_Global_LB', 'Certified_Gap_percent', 'target_Gap_percent'])
    table(root / 'V12_DATE_ARM_DDAY_AC.csv', rows,
          ['day', 'arm', 'Fresh_AC_status', 'Planning_max_line_loading', 'Fresh_AC_max_line_loading',
           'voltage_violations', 'current_violations'])
    table(root / 'V12_FAILURE_LEDGER.csv', [r for r in rows if r['status'] != 'PASS'],
          ['day', 'arm', 'status', 'error', 'result_SHA', 'error_SHA', 'finished_UTC'])


def worker_snapshot(active):
    request = read(active['request'])
    def optional(path):
        try:
            return read(path) if Path(path).is_file() else {}
        except (OSError, ValueError):
            return {}
    progress = optional(request['progress'])
    heartbeat_path = Path(request['result']).parent / 'HEARTBEAT.json'
    heartbeat = optional(heartbeat_path)
    telemetry = dict(RSS=None, CPU_seconds=None, CPU_percent=None, information_only=True)
    alive = same_process(active.get('worker', {}))
    if alive:
        try:
            identity = (active['worker']['PID'], active['worker']['created'])
            worker = _telemetry_processes.setdefault(identity, psutil.Process(identity[0]))
            cpu = worker.cpu_times()
            telemetry.update(RSS=worker.memory_info().rss, CPU_seconds=cpu.user + cpu.system,
                             CPU_percent=worker.cpu_percent(interval=None))
        except psutil.Error:
            pass
    def take(*names):
        return next((progress[n] for n in names if progress.get(n) is not None), None)
    wall = take('wall_seconds', 'Wall_Time', 'wall_elapsed_seconds')
    if wall is None:
        wall = max(0., time.time() - datetime.fromisoformat(active['started_UTC']).timestamp())
    return dict(active, PID=active.get('worker', {}).get('PID'), worker_alive=alive,
        phase=progress.get('phase', 'DISPATCHED'), progress=progress, heartbeat=heartbeat,
        heartbeat_timestamp_UTC=heartbeat.get('timestamp_UTC'),
        UB=take('UB'), independent_Global_LB=take('independent_Global_LB', 'Certified_Global_LB'),
        Certified_Gap=take('certified_gap', 'Certified_Gap'),
        Native_Runtime_seconds=take('Native_Runtime', 'Native_Runtime_seconds'),
        wall_seconds=wall, remaining_seconds=max(0., 5400. - (take('Native_Runtime','Native_Runtime_seconds') or 0.)), resource=telemetry)


def snapshot(root, manifest, checkpoint, active=None):
    actives = read_actives(root)
    if not actives and active and active.get('request'):
        actives = {key(active['arm'], active['day']): active}
    workers = [worker_snapshot(a) for a in actives.values()]
    primary = workers[0] if workers else {}
    active = actives.get(key(primary.get('arm'), primary.get('day')), {}) if primary else {}
    slots = [next((row for row in workers if row['arm'] == 'B2' and row.get('worker_slot', 1) == slot),
                  dict(worker_slot=slot, arm='B2', day=None, PID=None, worker_alive=False,
                       phase='WAITING_FOR_B1' if counts(checkpoint, 'B1')['completed'] != 31 else 'IDLE',
                       progress={}, resource={}, heartbeat={})) for slot in range(1, 4)]
    totals = counts(checkpoint)
    heartbeat = dict(timestamp_UTC=now(), run_id=manifest['run_id'], process=process(),
        state=checkpoint['state'], active=active, workers=actives, healthy_solver_kill=False)
    atomic(root / 'COORDINATOR_HEARTBEAT.json', heartbeat)
    telemetry = dict(RSS=sum(row['resource'].get('RSS') or 0 for row in workers),
        CPU_seconds=sum(row['resource'].get('CPU_seconds') or 0 for row in workers),
        CPU_percent=sum(row['resource'].get('CPU_percent') or 0 for row in workers),
        RAM_available=psutil.virtual_memory().available, RAM_total=psutil.virtual_memory().total,
        information_only=True)
    value = dict(run_id=manifest['run_id'], state=checkpoint['state'], campaign_started=True,
        current_phase=primary.get('arm') or pending_phase(checkpoint), current_day=primary.get('day'),
        Coordinator_PID=heartbeat['process']['PID'], Worker_PID=primary.get('PID'),
        active=active, actives=actives, workers=workers, worker_slots=slots,
        B1_worker=next((row for row in workers if row['arm'] == 'B1'), None),
        progress=primary.get('progress', {}), totals=totals, B1=counts(checkpoint, 'B1'), B2=counts(checkpoint, 'B2'),
        completed_arm_dates=totals['completed'], day_rows=list(checkpoint['dates'].values()),
        target_Global_Gap=.005 if primary.get('arm') == 'B1' else .03,
        wall_budget_seconds=None, native_budget_seconds=5400, P2_calls=0, Threads=1,
        B1_parallel_workers=1, B2_parallel_workers=3, terminal_date_retries=0, authorized_recovery_dates=list(RETRY_DATES), algorithm_version='B2_FULL_VALIDATION_LIVE_WORKERS_RECOVERY_V12',
        B2_requires_all_B1_terminal=True, resource=telemetry, last_error=checkpoint.get('last_error'),
        timestamp_UTC=now(), heartbeat=heartbeat, monitor_port=manifest.get('monitor_port', 8793))
    value['inherited_result_verification'] = checkpoint.get('inherited_result_verification')
    atomic(root / 'CAMPAIGN_STATUS.json', value)
    recovery={day:checkpoint['dates'][key('B1',day)] for day in RETRY_DATES}
    atomic(root/'MAY31_RECOVERY_SEQUENCE_V12.json',dict(UTC=now(),run_id=manifest['run_id'],
        algorithm_version='B2_FULL_VALIDATION_LIVE_WORKERS_RECOVERY_V12',authorized_order=list(RETRY_DATES),
        current_day=primary.get('day'),current_arm=primary.get('arm'),
        next_unstarted_B1_dates=[row['day'] for row in sorted(checkpoint['dates'].values(),
            key=lambda r:({d:i for i,d in enumerate(RETRY_DATES)}.get(r['day'],2),r['day']))
            if row['arm']=='B1' and row['status']=='PENDING'],
        recovery_dates={d:{k:r.get(k) for k in ('status','attempt_id','algorithm_version','request','result','result_SHA','started_UTC','finished_UTC')} for d,r in recovery.items()},
        active_workers=[dict(arm=w['arm'],day=w['day'],PID=w.get('PID'),phase=w.get('phase'),heartbeat=w.get('heartbeat')) for w in workers],
        B1_remaining_dates_continue_after_recovery=True,B2_parallel_workers=3,
        original_results_and_ledgers_preserved=True,automated_by_OS_Coordinator=True))
    first = actives.get(key('B2', DAYS[0]), active)
    first_progress = next((row['progress'] for row in workers if row['arm'] == first.get('arm') and row['day'] == first.get('day')), {})
    transition_evidence(root, checkpoint, first, first_progress)
    parallel_evidence(root, checkpoint, actives, workers)
    return value


def parallel_evidence(root, checkpoint, actives, workers):
    path = root / 'B2_THREE_WORKER_PARALLEL_VERIFICATION.json'
    value = read(path) if path.is_file() else dict(native_zero_tests=dict(PASS=False, status='NO_TEST_RECEIPT_CONNECTED'),
        actual_parallel=dict(status='NOT_YET_OBSERVED'))
    live = [row for row in workers if row['arm'] == 'B2' and row['worker_alive']]
    value.update(run_id=checkpoint['run_id'], B1_terminal_count=counts(checkpoint, 'B1')['completed'],
        B2_active_dates=[row['day'] for row in live], B2_live_workers=len(live), updated_UTC=now())
    actual = value.get('actual_parallel', {})
    if len(live) == 3 and actual.get('status') != 'OBSERVED':
        ensure_phase(checkpoint, 'B2')
        actual = dict(status='OBSERVED', observed_UTC=now(),
            workers=[dict(worker_slot=row['worker_slot'], day=row['day'], worker=row['worker'],
                input_SHA=sha(Path(read(row['request'])['input_folder']) / 'NATIVE_INPUT.json'),
                started_UTC=row['started_UTC'], heartbeat=row['heartbeat']) for row in live])
    if actual.get('status') == 'OBSERVED':
        for observed in actual['workers']:
            matching = next((row for row in workers if row['worker'] == observed['worker']), None)
            if matching and matching['heartbeat'] and not observed.get('heartbeat'):
                observed['heartbeat'] = matching['heartbeat']
        value['actual_parallel'] = actual
    atomic(path, value)


def transition_evidence(root, checkpoint, active, progress=None):
    """Persist real B1-to-B2 observation separately from Native=0 tests."""
    path = root / 'B1_TO_B2_TRANSITION_VERIFICATION.json'
    evidence = read(path) if path.is_file() else dict(
        native_zero_tests=dict(PASS=False, status='NO_TEST_RECEIPT_CONNECTED'),
        actual_transition=dict(status='NOT_YET_OBSERVED'))
    evidence['run_id'] = checkpoint['run_id']
    evidence['B1_terminal_count'] = counts(checkpoint, 'B1')['completed']
    evidence['B1_all_terminal'] = evidence['B1_terminal_count'] == 31
    actual = evidence.get('actual_transition', {})
    if active.get('arm') == 'B2' and active.get('day') == DAYS[0] and same_process(active.get('worker', {})):
        ensure_phase(checkpoint, 'B2')
        request = read(active['request'])
        if actual.get('status') != 'OBSERVED':
            folder = Path(request['input_folder'])
            input_files = [record(p) for p in sorted(folder.rglob('*')) if p.is_file()] if folder.is_dir() else []
            actual = dict(status='OBSERVED', observation_UTC=now(),
                          B1_counts=counts(checkpoint, 'B1'), B1_last_day=DAYS[-1],
                          B2_first_day=DAYS[0], B2_worker=active['worker'],
                          started_UTC=request['started_UTC'], input_folder=str(folder),
                          input_SHA=sha(folder / 'NATIVE_INPUT.json') if (folder / 'NATIVE_INPUT.json').is_file()
                                    else digest(input_files) if input_files else None,
                          input_files_SHA=digest(input_files) if input_files else None,
                          input_files=input_files, first_heartbeat=None,
                          coordinator_restart_adoption=active.get('adopted', False))
        worker_heartbeat_path = Path(request['result']).parent / 'HEARTBEAT.json'
        if not worker_heartbeat_path.is_file():
            worker_heartbeat_path = Path(request['output']) / 'HEARTBEAT.json'
        worker_heartbeat = read(worker_heartbeat_path) if worker_heartbeat_path.is_file() else {}
        if not actual.get('first_heartbeat') and worker_heartbeat:
            identity = worker_heartbeat.get('worker', worker_heartbeat.get('process', {}))
            if identity == active['worker']:
                actual['first_heartbeat'] = dict(worker_heartbeat, evidence=str(worker_heartbeat_path))
        if not actual.get('first_heartbeat') and progress:
            worker_row = progress.get('worker', {})
            if worker_row == active['worker'] and progress.get('timestamp_UTC'):
                actual['first_heartbeat'] = dict(timestamp_UTC=progress['timestamp_UTC'], worker=worker_row,
                                               phase=progress.get('phase'), evidence=request['progress'])
        evidence['actual_transition'] = actual
    evidence['updated_UTC'] = now()
    atomic(path, evidence)
    return evidence


def new_request(root, manifest, arm, day, *, worker_slot=1):
    attempt = attempt_path(root, arm, day)
    attempt.mkdir(parents=True, exist_ok=False)
    inputs = manifest.get('input_folders', {}).get(key(arm, day), str(root / 'inputs' / arm / day))
    request = dict(root=str(root), run_id=manifest['run_id'], arm=arm, day=day, input_folder=inputs,
                   output=str(attempt / 'output'), progress=str(attempt / 'progress.json'),
                   result=str(attempt / 'RESULT.json'), error=str(attempt / 'error.json'),
                   manifest=str(root / MANIFEST), manifest_SHA=sha(root / MANIFEST),
                   started_UTC=now(), wall_budget_seconds=None, native_budget_seconds=5400,
                   target_gap=0.005 if arm == 'B1' else 0.03, Threads=1, P2_calls=0,
                   worker_slot=worker_slot)
    from .policy import VERSION
    request.update(policy_version=VERSION,implementation_SHA=manifest['implementation']['source_SHA'], attempt_id=ATTEMPT, algorithm_version=VERSION,
        input_authority_root=str(Path(manifest['scientific_authority']['path']).parent))
    cache=manifest.get('input_cache_sources',{}).get(key(arm,day))
    if cache is not None:
        request.update(_current_date_physical_cache=cache['folder'],_physical_cache_identity=cache['receipt'],
            _expected_complete_domain_hashes=cache['complete_domain_hashes'],
            _expected_model_verification=cache['model_verification'])
    atomic(attempt / 'request.json', request)
    return attempt / 'request.json', request


def default_worker_command(manifest, request_path):
    return [manifest.get('Python', manifest.get('python_executable', sys.executable)),
            '-B', '-X', 'utf8', '-m', 'v42_b2_start_recovery_v12.worker', str(request_path)]


def pending_phase(checkpoint):
    if counts(checkpoint, 'B1')['completed'] != 31:
        return 'B1'
    return 'B2' if counts(checkpoint, 'B2')['completed'] != 31 else None


def reap_finished(root, manifest, checkpoint, actives, children):
    completed = []
    for name, active in list(actives.items()):
        child = children.get(name)
        if same_process(active.get('worker', {})):
            continue
        if child is not None and child.poll() is None:
            # A transient PID query failure must not free a living OS child.
            continue
        request = read(active['request'])
        if active['arm'] == 'B2':
            parallel_evidence(root, checkpoint, actives, [worker_snapshot(a) for a in actives.values()])
        finish_attempt(root, manifest, checkpoint, checkpoint['dates'][name], request,
                       child.wait() if child is not None else None)
        del actives[name]; children.pop(name, None); completed.append(name)
    if completed:
        persist_actives(root, manifest, actives)
    return completed


def dispatch_available(root, manifest, checkpoint, actives, children, command_factory):
    """Fill only free slots, preserving the pending date's original order."""
    validate_slots(checkpoint, actives)
    if (root/'HOLD_V12.json').exists():return []
    arm = pending_phase(checkpoint)
    if arm is None:
        return []
    if arm == 'B2':
        from .deferred_validation import ready
        previous_state = checkpoint['state']
        if not ready(root, manifest, checkpoint, actives):
            if checkpoint['state'] != previous_state:
                save_checkpoint(root, checkpoint)
            return []
    ensure_phase(checkpoint, arm)
    if any(active['arm'] != arm for active in actives.values()):
        raise PermissionError('LIVE_WORKER_ARM_DIFFERS_FROM_PENDING_PHASE')
    free = [slot for slot in range(1, worker_limit(arm) + 1)
            if slot not in {active.get('worker_slot', 1) for active in actives.values()}]
    pending = [row for row in checkpoint['dates'].values()
               if row['arm'] == arm and row['status'] == 'PENDING' and row['attempts'] == 0]
    if arm == 'B1':
        order={day:i for i,day in enumerate(RETRY_DATES)}
        pending.sort(key=lambda r:(order.get(r['day'],2),r['day']))
    started = []
    for slot, row in zip(free, pending):
        day = row['day']; name = key(arm, day)
        request_path, request = new_request(root, manifest, arm, day, worker_slot=slot)
        validate_request(root, manifest, request)
        command = command_factory(manifest, request_path)
        request['worker_command'] = command; atomic(request_path, request)
        row.update(status='RUNNING', attempts=1, worker_slot=slot,
                   request=str(request_path), started_UTC=request['started_UTC'],
                   attempt_id=ATTEMPT, algorithm_version=request['algorithm_version'])
        save_checkpoint(root, checkpoint)
        child = None
        try:
            with (request_path.parent / 'stdout.log').open('ab') as stdout, (request_path.parent / 'stderr.log').open('ab') as stderr:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
                identity = process(child.pid)
        except (OSError, psutil.Error) as error:
            if child is not None and child.poll() is None:
                identity = matching_live_worker(request_path)
                if not identity:
                    raise PermissionError('LAUNCHED_WORKER_IDENTITY_UNRESOLVED') from error
            else:
                atomic(request['error'], dict(classification='IMPLEMENTATION_FAILURE',
                                             error=str(error), type=type(error).__name__, UTC=now()))
                identity = {}
        actives[name] = dict(arm=arm, day=day, request=str(request_path), worker=identity,
            worker_slot=slot, started_UTC=request['started_UTC'], adopted=False)
        if child is not None:
            children[name] = child
        persist_actives(root, manifest, actives)
        started.append(name)
    return started


def run(root, *, worker_command=None, verify=True, poll_seconds=0.5):
    root = runtime_path(root)
    if (root/'HOLD_V12.json').exists():return 0
    manifest = load_manifest(root, verify=verify)
    command_factory = worker_command or default_worker_command
    with os_lock(root / 'COORDINATOR.lock') as acquired:
        if not acquired:
            return 0
        checkpoint = load_checkpoint(root, manifest)
        stop = threading.Event(); mutex = threading.RLock()
        def ticker():
            while not stop.wait(1):
                try:
                    with mutex:
                        snapshot(root, manifest, checkpoint)
                except Exception as error:
                    atomic(root / 'STATUS_EXCEPTION.json', dict(UTC=now(), error=str(error)))
        thread = threading.Thread(target=ticker, daemon=True); thread.start()
        try:
            checkpoint['state'] = 'VERIFYING_INHERITED_RESULTS'
            snapshot(root, manifest, checkpoint)
            recovery_requests(root, manifest, checkpoint, read_actives(root))
            completed = [name for name, row in checkpoint['dates'].items()
                if row['status'] in TERMINAL and row.get('result')]
            verified = []
            for name, row in checkpoint['dates'].items():
                if row['status'] in TERMINAL and row.get('result'):
                    checkpoint['inherited_result_verification'] = dict(current=name,
                        verified=len(verified), total=len(completed), UTC=now())
                    request = read(row['request'])
                    if sha(row['result']) != row['result_SHA'] or not receipt_valid(
                            root, manifest, request, read(row['result'])):
                        raise PermissionError('COMPLETED_RESULT_SHA_DRIFT:' + name)
                    verified.append(name)
            checkpoint['inherited_result_verification'] = dict(PASS=True,
                verified=len(verified), total=len(completed), UTC=now())
            actives = recover_actives(root, manifest, checkpoint)
            children = {}
            checkpoint['state'] = 'RUNNING'; save_checkpoint(root, checkpoint)
            while pending_phase(checkpoint) is not None or actives:
                if (root/'HOLD_V12.json').exists():
                    checkpoint['state']='HOLD';save_checkpoint(root,checkpoint);return 0
                with mutex:
                    reap_finished(root, manifest, checkpoint, actives, children)
                    dispatch_available(root, manifest, checkpoint, actives, children, command_factory)
                    snapshot(root, manifest, checkpoint)
                if pending_phase(checkpoint) is not None or actives:
                    time.sleep(poll_seconds)
            with mutex:
                checkpoint.update(state='COMPLETE', finished_UTC=now())
                save_checkpoint(root, checkpoint); export(root, manifest, checkpoint)
                snapshot(root, manifest, checkpoint)
            return 0
        except BaseException as error:
            checkpoint['state'] = 'COORDINATOR_ERROR'
            with mutex:
                save_checkpoint(root, checkpoint)
            atomic(root / 'COORDINATOR_ERROR.json', dict(error=str(error), traceback=traceback.format_exc(),
                                                       UTC=now(), process=process()))
            raise
        finally:
            stop.set(); thread.join(timeout=3)


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1]))
