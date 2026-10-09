"""One Native=0 model build at a time, after all B1 workers have exited."""
from pathlib import Path
import subprocess
import sys
import psutil
from .common import atomic, read, record, sha, process, same_process, now, ROOT

ORDER = tuple((day, mode) for day in ('2025-05-01', '2025-05-23')
              for mode in ('BASELINE', 'OPTIMIZED'))


def paths(root, day, mode):
    return Path(root) / 'source_validation_v10' / 'B2' / day / mode


def matching_process(command):
    from .coordinator import command_matches
    matches = []
    for peer in psutil.process_iter(['pid', 'name']):
        if (peer.info.get('name') or '').lower() not in ('python.exe', 'pythonw.exe'):
            continue
        try:
            if command_matches(command, peer.cmdline()):
                matches.append(process(peer.pid))
        except psutil.Error:
            continue
    if len(matches) > 1:
        raise PermissionError('V7_DUPLICATE_NATIVE_ZERO_MODEL_BUILD')
    return matches[0] if matches else None


def validate_receipt(path, request):
    receipt = read(path)
    if (receipt.get('PASS') is not True or receipt.get('Native_calls') != 0
            or receipt.get('P2_calls') != 0 or receipt.get('day') != request['day']
            or receipt.get('mode') != request['build_mode']
            or receipt.get('implementation_SHA') != request['implementation_SHA']
            or receipt.get('input_SHA') != sha(Path(request['input_folder']) / 'NATIVE_INPUT.json')):
        raise PermissionError('V7_FULL_BUILD_VALIDATION_RECEIPT_DRIFT')
    return receipt


def ready(root, manifest, checkpoint, actives):
    from .coordinator import counts
    root = Path(root)
    if counts(checkpoint, 'B1')['completed'] != 31 or actives:
        raise PermissionError('V7_HEAVY_VALIDATION_REQUIRES_ALL_B1_TERMINAL_AND_NO_WORKERS')
    path = root / 'B2_BUILD_FULL_VALIDATION_V10.json'
    state = read(path) if path.is_file() else dict(status='NOT_TESTED', PASS=False, builds={})
    if state.get('status') == 'FAIL':
        checkpoint['state'] = 'B2_BUILD_VALIDATION_FAILED'
        return False
    if state.get('status') == 'PASS':
        # The final gate must bind the current source and every completed build.
        if state.get('implementation_SHA') != manifest['implementation']['source_SHA']:
            raise PermissionError('V7_FULL_VALIDATION_SOURCE_DRIFT')
        if (set(state.get('builds', {})) != {d + '/' + m for d, m in ORDER}
                or set(state.get('comparisons', {})) != {'2025-05-01', '2025-05-23'}
                or any(row.get('PASS') is not True for row in state['comparisons'].values())):
            raise PermissionError('V7_FULL_VALIDATION_COVERAGE_OR_COMPARISON_DRIFT')
        for item in state['builds'].values():
            if record(item['receipt']['path']) != item['receipt']:
                raise PermissionError('V7_FULL_VALIDATION_PACKET_SHA_DRIFT')
        checkpoint['state'] = 'RUNNING'
        return True
    checkpoint['state'] = 'B2_NATIVE_ZERO_MODEL_VALIDATION'
    state.update(status='RUNNING', implementation_SHA=manifest['implementation']['source_SHA'], UTC=now())
    active = state.get('active')
    if active:
        if same_process(active['process']):
            atomic(path, state)
            return False
        result = Path(active['result'])
        if not result.is_file():
            state.update(status='FAIL', error='VALIDATION_PROCESS_EXIT_WITHOUT_RECEIPT', active=None)
            atomic(path, state)
            return False
        try:
            request = read(active['request'])
            receipt = validate_receipt(result, request)
            state['builds'][request['day'] + '/' + request['build_mode']] = dict(receipt=record(result), summary=receipt)
            state['active'] = None
        except (ValueError, OSError, PermissionError, KeyError) as error:
            state.update(status='FAIL', error=repr(error), active=None)
            atomic(path, state)
            return False
    pending = [(d, m) for d, m in ORDER if d + '/' + m not in state['builds']]
    if pending:
        # Only the first pending task may be adopted or started. A crash after
        # Popen cannot cause another date/model to be built concurrently.
        day, mode = pending[0]
        folder = paths(root, day, mode)
        request_path = folder / 'request.json'
        command = [manifest.get('Python', sys.executable), '-B', '-X', 'utf8', '-m',
                   'v42_may31_recovery_v10.full_validation', str(request_path)]
        orphan = matching_process(command)
        if request_path.is_file():
            request = read(request_path)
            result = Path(request['result'])
            if result.is_file() and not orphan:
                try:
                    receipt = validate_receipt(result, request)
                    state['builds'][day + '/' + mode] = dict(receipt=record(result), summary=receipt)
                except (ValueError, OSError, PermissionError, KeyError) as error:
                    state.update(status='FAIL', error=repr(error))
                atomic(path, state)
                return False
            if not orphan:
                state.update(status='FAIL', error='UNFINISHED_VALIDATION_ATTEMPT_NOT_AUTOMATICALLY_RETRIED')
                atomic(path, state)
                return False
        else:
            folder.mkdir(parents=True, exist_ok=False)
            from .policy import MANIFEST, ATTEMPT, VERSION
            request = dict(root=str(root), run_id=manifest['run_id'], day=day, arm='B2',
                input_folder=manifest['input_folders']['B2/' + day], output=str(folder / 'output'),
                progress=str(folder / 'progress.json'), result=str(folder / 'RESULT.json'),
                error=str(folder / 'error.json'), manifest=str(root / MANIFEST), manifest_SHA=sha(root / MANIFEST),
                started_UTC=now(), Threads=1, P2_calls=0, target_gap=.03, worker_slot=1,
                native_budget_seconds=5400, wall_budget_seconds=None, policy_version=VERSION,
                algorithm_version=VERSION, attempt_id=ATTEMPT,
                implementation_SHA=manifest['implementation']['source_SHA'], build_mode=mode,
                preflight_native_zero=True, input_authority_root=manifest['input_authority_root'])
            atomic(request_path, request)
        if orphan:
            identity = orphan
        else:
            from .worker import assert_no_other_native_worker
            assert_no_other_native_worker()
            with (folder / 'stdout.log').open('ab') as stdout, (folder / 'stderr.log').open('ab') as stderr:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
                identity = process(child.pid)
        state['active'] = dict(day=day, mode=mode, process=identity, request=str(request_path),
                               result=request['result'], adopted=bool(orphan), started_UTC=request['started_UTC'])
        atomic(path, state)
        return False
    comparisons = {}
    for day in ('2025-05-01', '2025-05-23'):
        original = state['builds'][day + '/BASELINE']['summary']
        improved = state['builds'][day + '/OPTIMIZED']['summary']
        identical = original['fingerprint'] == improved['fingerprint']
        comparisons[day] = dict(PASS=identical,
            baseline_seconds=original['total_preparation_seconds'], optimized_seconds=improved['total_preparation_seconds'],
            fingerprints_identical=identical, performance_observation='ONE_SEQUENTIAL_PAIR; NOT_CONTROLLED_BENCHMARK')
    state.update(comparisons=comparisons, PASS=all(d['PASS'] for d in comparisons.values()),
                 Native_calls=0, P2_calls=0, real_transition='NOT_YET_OBSERVED', UTC=now())
    state['status'] = 'PASS' if state['PASS'] else 'FAIL'
    atomic(path, state)
    return state['PASS']
