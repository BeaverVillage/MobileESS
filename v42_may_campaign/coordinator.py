"""Serial B1 then B2 campaign using the established atomic/PID/checkpoint ports.

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

import psutil

from v42_pr134_b1.common import atomic, table, read, sha, digest, record, process, same_process, now, ROOT
from v42_pr134_b1.coordinator import save_checkpoint

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
    manifest = read(root / 'CAMPAIGN_MANIFEST.json')
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
        verify_manifest(root / 'CAMPAIGN_MANIFEST.json', require_preflight=True)
    return manifest


def load_checkpoint(root, manifest):
    root = Path(root)
    path = root / 'CHECKPOINT.json'
    if path.is_file():
        try:
            checkpoint = read(path)
        except (ValueError, OSError) as error:
            backup = root / 'CHECKPOINT_PREVIOUS.json'
            receipt = root / 'CHECKPOINT_PREVIOUS_SHA.json'
            if not backup.is_file() or not receipt.is_file() or sha(backup) != read(receipt)['sha256']:
                raise ValueError('CORRUPT_CHECKPOINT_NO_VERIFIED_BACKUP') from error
            damaged = root / ('CHECKPOINT_CORRUPT_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json')
            path.replace(damaged)
            checkpoint = read(backup)
            atomic(path, checkpoint)
    else:
        checkpoint = dict(run_id=manifest['run_id'], state='READY',
                          dates={key(arm, day): dict(arm=arm, day=day, status='PENDING', attempts=0)
                                 for arm, day in AXIS}, last_error=None)
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


def validate_request(root, manifest, request):
    if request.get('run_id') != manifest['run_id'] or (request.get('arm'), request.get('day')) not in AXIS:
        raise PermissionError('WORKER_REQUEST_RUN_ARM_DATE_DRIFT')
    if Path(request['root']).resolve() != Path(root).resolve():
        raise PermissionError('WORKER_REQUEST_ROOT_DRIFT')
    expected_input = manifest.get('input_folders', {}).get(
        key(request['arm'], request['day']), str(Path(root) / 'inputs' / request['arm'] / request['day']))
    if Path(request['input_folder']).resolve() != Path(expected_input).resolve():
        raise PermissionError('ARM_DATE_INPUT_FOLDER_MIXING')
    for name in ('output', 'progress', 'result', 'error'):
        if not Path(request[name]).resolve().is_relative_to(Path(root).resolve()):
            raise PermissionError('WORKER_REQUEST_OUTPUT_ESCAPES_RUNTIME')
    if request.get('manifest_SHA') != sha(Path(root) / 'CAMPAIGN_MANIFEST.json'):
        raise PermissionError('WORKER_REQUEST_MANIFEST_SHA_DRIFT')
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
        if receipt.get('status') not in TERMINAL:
            return False
        files = receipt.get('files', [])
        if receipt['status'] == 'PASS' and (receipt.get('PASS') is not True or not files):
            return False
        return all(Path(r['path']).resolve().is_relative_to(Path(root).resolve())
                   and sha(r['path']) == r['sha256'] for r in files)
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


def recover_active(root, manifest, checkpoint):
    path = root / 'ACTIVE.json'
    active = read(path) if path.is_file() else {}
    if active.get('request'):
        request_path = Path(active['request']).resolve()
        if not request_path.is_relative_to(root):
            raise PermissionError('ACTIVE_REQUEST_ESCAPES_RUNTIME')
        request = read(request_path)
        validate_request(root, manifest, request)
        ensure_phase(checkpoint, request['arm'])
        row = checkpoint['dates'][key(request['arm'], request['day'])]
        worker = active.get('worker', {})
        if same_process(worker) and not command_matches(request.get('worker_command'), worker.get('command')):
            raise PermissionError('ACTIVE_PROCESS_COMMAND_DOES_NOT_MATCH_REQUEST')
        if not same_process(worker):
            worker = matching_live_worker(request_path) or {}
        if same_process(worker):
            if row['status'] in TERMINAL:
                raise PermissionError('LIVE_WORKER_FOR_TERMINAL_DATE')
            row.update(status='RUNNING', attempts=1, request=str(request_path),
                       started_UTC=request['started_UTC'])
            active.update(worker=worker, arm=request['arm'], day=request['day'], adopted=True)
            atomic(path, active)
            save_checkpoint(root, checkpoint)
            return active
    # A checkpoint may precede ACTIVE persistence. Find its exact live request
    # before declaring an interrupted attempt terminal; never spawn it again.
    for row in checkpoint['dates'].values():
        # request.json precedes the durable RUNNING checkpoint. An OS crash
        # in that short window must not turn the same arm/date into attempt 2.
        attempt = root / 'dates' / row['arm'] / row['day']
        if row['status'] == 'PENDING' and attempt.exists():
            request_path = attempt / 'request.json'
            if not request_path.is_file():
                row.update(status='IMPLEMENTATION_FAILURE', attempts=1,
                           error='INTERRUPTED_BEFORE_ATOMIC_REQUEST', finished_UTC=now())
                save_checkpoint(root, checkpoint)
                export(root, manifest, checkpoint)
                continue
            row.update(status='RUNNING', attempts=1, request=str(request_path))
        if row['status'] != 'RUNNING':
            continue
        request = read(row['request'])
        validate_request(root, manifest, request)
        ensure_phase(checkpoint, request['arm'])
        row['started_UTC'] = request['started_UTC']
        worker = matching_live_worker(row['request'])
        if worker:
            active = dict(arm=row['arm'], day=row['day'], request=row['request'], worker=worker,
                          started_UTC=row.get('started_UTC'), adopted=True)
            atomic(path, active)
            return active
        finish_attempt(root, manifest, checkpoint, row, request, None, interrupted=True)
    if active and not same_process(active.get('worker', {})):
        atomic(path, {})
    return {}


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
                       summary=receipt, finished_UTC=receipt.get('finished_UTC', now()))
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
    table(root / 'DATE_ARM_RESULTS.csv', rows,
          ['day', 'arm', 'status', 'attempts', 'result_SHA', 'incumbent_valid', 'P1_certified', 'case_SHA', 'error'])
    table(root / 'DATE_ARM_RUNTIME.csv', rows,
          ['day', 'arm', 'wall_seconds', 'Native_Runtime_seconds', 'Fresh_AC_seconds', 'Native_calls'])
    table(root / 'DATE_ARM_GAP.csv', rows,
          ['day', 'arm', 'UB', 'Native_BestBd', 'independent_Global_LB', 'Certified_Gap_percent', 'target_Gap_percent'])
    table(root / 'DATE_ARM_DDAY_AC.csv', rows,
          ['day', 'arm', 'Fresh_AC_status', 'Planning_max_line_loading', 'Fresh_AC_max_line_loading',
           'voltage_violations', 'current_violations'])
    table(root / 'FAILURE_LEDGER.csv', [r for r in rows if r['status'] != 'PASS'],
          ['day', 'arm', 'status', 'error', 'result_SHA', 'error_SHA', 'finished_UTC'])


def snapshot(root, manifest, checkpoint, active=None):
    active_path = root / 'ACTIVE.json'
    active = read(active_path) if active_path.is_file() else active or {}
    progress = {}
    if active.get('request'):
        request = read(active['request'])
        progress_path = Path(request['progress'])
        if progress_path.is_file():
            try:
                progress = read(progress_path)
            except (OSError, ValueError):
                pass
    telemetry = dict(RSS=None, CPU_seconds=None, CPU_percent=None,
                     RAM_available=psutil.virtual_memory().available, RAM_total=psutil.virtual_memory().total,
                     information_only=True)
    if same_process(active.get('worker', {})):
        try:
            identity = (active['worker']['PID'], active['worker']['created'])
            worker = _telemetry_processes.get(identity)
            if worker is None:
                _telemetry_processes.clear()
                worker = psutil.Process(identity[0])
                _telemetry_processes[identity] = worker
            cpu = worker.cpu_times()
            telemetry.update(RSS=worker.memory_info().rss, CPU_seconds=cpu.user + cpu.system,
                             CPU_percent=worker.cpu_percent(interval=None))
        except psutil.Error:
            pass
    totals = counts(checkpoint)
    heartbeat = dict(timestamp_UTC=now(), run_id=manifest['run_id'], process=process(),
                     state=checkpoint['state'], active=active, healthy_solver_kill=False)
    atomic(root / 'COORDINATOR_HEARTBEAT.json', heartbeat)
    value = dict(run_id=manifest['run_id'], state=checkpoint['state'], campaign_started=True,
                 current_phase=active.get('arm'), current_day=active.get('day'),
                 Coordinator_PID=heartbeat['process']['PID'], Worker_PID=active.get('worker', {}).get('PID'),
                 active=active, progress=progress, totals=totals, B1=counts(checkpoint, 'B1'), B2=counts(checkpoint, 'B2'),
                 completed_arm_dates=totals['completed'], day_rows=list(checkpoint['dates'].values()),
                 target_Global_Gap=0.005 if active.get('arm') == 'B1' else 0.03,
                 wall_budget_seconds=5400, native_budget_seconds=5400, P2_calls=0, Threads=1,
                 terminal_date_retries=0, B2_requires_all_B1_terminal=True,
                 resource=telemetry, last_error=checkpoint.get('last_error'), timestamp_UTC=now(),
                 heartbeat=heartbeat, monitor_port=manifest.get('monitor_port', 8793))
    atomic(root / 'CAMPAIGN_STATUS.json', value)
    transition_evidence(root, checkpoint, active, progress)
    return value


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


def new_request(root, manifest, arm, day):
    attempt = root / 'dates' / arm / day
    attempt.mkdir(parents=True, exist_ok=False)
    inputs = manifest.get('input_folders', {}).get(key(arm, day), str(root / 'inputs' / arm / day))
    request = dict(root=str(root), run_id=manifest['run_id'], arm=arm, day=day, input_folder=inputs,
                   output=str(attempt / 'output'), progress=str(attempt / 'progress.json'),
                   result=str(attempt / 'RESULT.json'), error=str(attempt / 'error.json'),
                   manifest=str(root / 'CAMPAIGN_MANIFEST.json'), manifest_SHA=sha(root / 'CAMPAIGN_MANIFEST.json'),
                   started_UTC=now(), wall_budget_seconds=5400, native_budget_seconds=5400,
                   target_gap=0.005 if arm == 'B1' else 0.03, Threads=1, P2_calls=0)
    atomic(attempt / 'request.json', request)
    return attempt / 'request.json', request


def default_worker_command(manifest, request_path):
    return [manifest.get('Python', manifest.get('python_executable', sys.executable)),
            '-B', '-X', 'utf8', '-m', 'v42_may_campaign.worker', str(request_path)]


def run(root, *, worker_command=None, verify=True, poll_seconds=0.5):
    root = runtime_path(root)
    manifest = load_manifest(root, verify=verify)
    command_factory = worker_command or default_worker_command
    with os_lock(root / 'COORDINATOR.lock') as acquired:
        if not acquired:
            return 0
        checkpoint = load_checkpoint(root, manifest)
        active = recover_active(root, manifest, checkpoint)
        checkpoint['state'] = 'RUNNING'
        save_checkpoint(root, checkpoint)
        stop = threading.Event()
        mutex = threading.RLock()

        def ticker():
            while not stop.wait(1):
                try:
                    with mutex:
                        snapshot(root, manifest, checkpoint)
                except Exception as error:
                    atomic(root / 'STATUS_EXCEPTION.json', dict(UTC=now(), error=str(error)))

        thread = threading.Thread(target=ticker, daemon=True)
        thread.start()
        try:
            snapshot(root, manifest, checkpoint)
            for arm, day in AXIS:
                row = checkpoint['dates'][key(arm, day)]
                if row['status'] in TERMINAL:
                    if row.get('result'):
                        request = read(row['request'])
                        if sha(row['result']) != row['result_SHA'] or not receipt_valid(
                                root, manifest, request, read(row['result'])):
                            raise PermissionError('COMPLETED_RESULT_SHA_DRIFT:' + key(arm, day))
                    continue
                ensure_phase(checkpoint, arm)
                child = None
                if active and same_process(active.get('worker', {})):
                    if (active['arm'], active['day']) != (arm, day):
                        raise PermissionError('LIVE_ORPHAN_DIFFERS_FROM_NEXT_ARM_DATE')
                    request_path = Path(active['request'])
                    request = read(request_path)
                elif row['status'] == 'RUNNING' or row.get('attempts', 0):
                    request = read(row['request'])
                    finish_attempt(root, manifest, checkpoint, row, request, None, interrupted=True)
                    atomic(root / 'ACTIVE.json', {})
                    active = {}
                    continue
                else:
                    request_path, request = new_request(root, manifest, arm, day)
                    validate_request(root, manifest, request)
                    row.update(status='RUNNING', attempts=1, request=str(request_path), started_UTC=request['started_UTC'])
                    command = command_factory(manifest, request_path)
                    request['worker_command'] = command
                    atomic(request_path, request)
                    with mutex:
                        save_checkpoint(root, checkpoint)
                    try:
                        with (request_path.parent / 'stdout.log').open('ab') as stdout, (request_path.parent / 'stderr.log').open('ab') as stderr:
                            child = subprocess.Popen(command, cwd=ROOT,
                                                     stdout=stdout, stderr=stderr)
                            worker = process(child.pid)
                    except (OSError, psutil.Error) as error:
                        if child and child.poll() is None:
                            # Never kill a launched worker when the identity
                            # query races; the exact command can recover it.
                            worker = matching_live_worker(request_path)
                            if not worker:
                                raise PermissionError('LAUNCHED_WORKER_IDENTITY_UNRESOLVED') from error
                        else:
                            atomic(request['error'], dict(classification='IMPLEMENTATION_FAILURE',
                                                         error=str(error), type=type(error).__name__, UTC=now()))
                            worker = {}
                    active = dict(arm=arm, day=day, request=str(request_path), worker=worker,
                                  started_UTC=request['started_UTC'], adopted=False)
                    atomic(root / 'ACTIVE.json', active)
                snapshot(root, manifest, checkpoint, active)
                while same_process(active.get('worker', {})):
                    if child is not None and child.poll() is not None:
                        break
                    time.sleep(poll_seconds)
                code = child.wait() if child is not None else None
                with mutex:
                    finish_attempt(root, manifest, checkpoint, row, request, code)
                    atomic(root / 'ACTIVE.json', {})
                    active = {}
                    snapshot(root, manifest, checkpoint)
            with mutex:
                checkpoint['state'] = 'COMPLETE'
                checkpoint['finished_UTC'] = now()
                save_checkpoint(root, checkpoint)
                export(root, manifest, checkpoint)
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
            stop.set()
            thread.join(timeout=3)


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1]))
