"""One fresh date attempt; all science is delegated to the existing A/M ports."""
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager, ExitStack
import argparse
import threading
import time
import traceback
import psutil
from .common import (RUNTIME, atomic, read, record, now, process, sha,
                     d_path, environment, exclusive_lock, LockBusy, worker_slot)
from .policy import MANIFEST, ATTEMPT, attempt_path
from .execution import worker_scope
from .budget import DateBudget, BudgetStop


def classify(error):
    text = str(error).upper()
    if isinstance(error, (BudgetStop, TimeoutError)) or 'BUDGET' in text:
        return 'TIME_LIMIT_NO_VALID_INCUMBENT'
    if isinstance(error, (MemoryError, LockBusy)):
        return 'OS_RESOURCE_FAILURE'
    if any(word in text for word in ('FRESH_', 'CONTROL_ACTIONS', 'OPENDSS')):
        return 'FRESH_AC_FAILURE'
    if any(word in text for word in ('PHYSICAL', 'INTEGER_REPLAY', 'SOC', 'PCC')):
        return 'PHYSICAL_FAILURE'
    if 'INFEASIBLE' in text:
        return 'INCONCLUSIVE'
    if any(word in text for word in ('INPUT', 'DATE', 'SHA', 'TRAFFIC', 'BUNDLE')):
        return 'INPUT_FAILURE'
    return 'IMPLEMENTATION_FAILURE'


def canonical(value):
    value = dict(value)
    # The reused M Hybrid reports gap() from its exact, independently verified
    # Frontier. Only that explicit phase may supply the display certificate;
    # a Native MIPGap or an arbitrary progress 'gap' cannot do so.
    if (str(value.get('phase', '')).startswith('M_ADAPTIVE_')
            and all(isinstance(value.get(k), (int, float)) for k in ('UB', 'global_LB', 'gap'))
            and 0 <= value['gap'] and value['global_LB'] <= value['UB']):
        value['certified_gap'] = value['gap']
        value['gap_source'] = 'REUSED_M_INDEPENDENT_EXACT_FRONTIER'
    for target, keys in {
        'independent_Global_LB': ('Certified_Global_LB', 'global_LB', 'LB'),
        'certified_gap': ('Certified_Gap', 'certified_gap'),
    }.items():
        for key in keys:
            if key in value and value[key] is not None:
                value[target] = value[key]; break
    return value


def _peer_request(args, request):
    """Validate a live peer from its persisted exact dispatch, not ACTIVES.

    ACTIVES is written after Popen and can lag a real worker. The persisted
    request and actual command close that window without accepting a second
    run, another input folder, or a reused arm/date/slot.
    """
    from .coordinator import command_matches, validate_request
    position = args.index('-m')
    if len(args) != position + 3:
        raise LockBusy('OTHER_CAMPAIGN_WORKER_MALFORMED_COMMAND')
    path = Path(args[-1]).resolve()
    root = Path(request['root']).resolve()
    if not path.is_relative_to(root / 'dates') or path.name != 'request.json':
        raise LockBusy('OTHER_CAMPAIGN_WORKER_DIFFERENT_RUN')
    try:
        peer = read(path)
        arm, day = peer['arm'], peer['day']
        attempt = attempt_path(root, arm, day)
        if (arm != 'B2' or request['arm'] != 'B2'
                or peer['run_id'] != request['run_id']
                or Path(peer['root']).resolve() != root
                or Path(peer['manifest']).resolve() != root / MANIFEST
                or peer['manifest_SHA'] != request['manifest_SHA']
                or path != attempt / 'request.json'
                or not command_matches(peer.get('worker_command'), args)):
            raise LockBusy('OTHER_CAMPAIGN_WORKER_SCOPE_CONFLICT')
        manifest = read(root / MANIFEST)
        if sha(root / MANIFEST) != request['manifest_SHA']:
            raise LockBusy('OTHER_CAMPAIGN_WORKER_MANIFEST_DRIFT')
        validate_request(root, manifest, peer)
        slot = worker_slot(peer)
        if (peer.get('Threads') != 1 or peer.get('P2_calls') != 0
                or peer.get('wall_budget_seconds') is not None
                or peer.get('native_budget_seconds') != 5400
                or any(Path(peer[name]).resolve() != attempt / filename
                       for name, filename in (('output', 'output'), ('progress', 'progress.json'),
                                              ('result', 'RESULT.json'), ('error', 'error.json')))):
            raise LockBusy('OTHER_CAMPAIGN_WORKER_POLICY_OR_OUTPUT_CONFLICT')
        if day == request['day']:
            raise LockBusy('DUPLICATE_CAMPAIGN_ARM_DATE')
        if slot == worker_slot(request):
            raise LockBusy('DUPLICATE_CAMPAIGN_WORKER_SLOT')
        return peer
    except (KeyError, OSError, ValueError, PermissionError) as error:
        raise LockBusy('OTHER_CAMPAIGN_WORKER_UNVERIFIED_REQUEST:' + str(path)) from error


def assert_no_other_native_worker(request=None):
    # Only same approved run B2 peers may coexist. Coordinator/Watchdog and
    # monitors are read-only parents and do not occupy scientific slots.
    peers = []
    slots = {worker_slot(request)} if request is not None else set()
    dates = {request['day']} if request is not None else set()
    # Windows cmdline reads are expensive cross-process queries. Query names
    # first, retaining exactly the same Python worker membership and checks.
    for candidate in psutil.process_iter(['pid', 'name']):
        if candidate.pid == psutil.Process().pid:
            continue
        try:
            if (candidate.info.get('name') or '').lower() not in ('python.exe', 'pythonw.exe', 'python'):
                continue
            args = candidate.cmdline() or []
            module = args[args.index('-m') + 1] if '-m' in args and len(args) > args.index('-m') + 1 else ''
            if module in ('v42_may_campaign.worker', 'v42_may_campaign_native90.worker', 'v42_may_recovery_v5.worker', 'v42_may_build_v6.worker', 'v42_may_mess_build_v7.worker', 'v42_may25_recovery_v9.worker', 'v42_may31_recovery_v10.worker', 'v42_b2_start_recovery_v11.worker'):
                if request is None:
                    raise LockBusy('OTHER_CAMPAIGN_WORKER_PID:' + str(candidate.pid))
                peer = _peer_request(args, request)
                slot = worker_slot(peer)
                if slot in slots or peer['day'] in dates:
                    raise LockBusy('DUPLICATE_CAMPAIGN_PEER_SLOT_OR_DATE')
                peers.append(dict(PID=candidate.pid, arm=peer['arm'], day=peer['day'],
                                  worker_slot=slot, request=str(Path(args[-1]).resolve()), command=args))
                slots.add(slot); dates.add(peer['day'])
                if len(peers) >= 3:
                    raise LockBusy('CAMPAIGN_B2_MAX_THREE_WORKERS')
                continue
            historical = ('v42_a_stage', 'v42_m1_', 'v42_may12_rescue')
            scripts = [Path(arg) for arg in args if isinstance(arg, str) and arg.lower().endswith('.py')]
            script_worker = any(any(part.startswith(historical) for part in script.parts)
                                or 'v42_pr134_b1' in script.parts and script.stem == 'worker'
                                or 'v42_may_campaign' in script.parts and script.stem == 'worker'
                                for script in scripts)
            if (module.startswith(historical) or module == 'v42_pr134_b1.worker' or script_worker):
                raise LockBusy('OTHER_SCIENTIFIC_WORKER_PID:' + str(candidate.pid))
        except psutil.Error:
            continue
    return peers


@contextmanager
def native_worker_admission(request, *, date_owned=False, started=None):
    """Hold one B2 slot (all slots for B1) and the date's lifetime OS lock."""
    slot = worker_slot(request)
    root = d_path(request['root'])
    attempt = attempt_path(root, request['arm'], request['day'])
    if started is None:
        dispatch = max(0., (datetime.now(timezone.utc)
                           - datetime.fromisoformat(request['started_UTC'])).total_seconds())
        started = time.perf_counter() - dispatch
    def check():
        assert_no_other_native_worker(request)
    # Detect an incompatible historical worker before waiting on its older
    # lifetime global lock. All current workers hold this mutex only briefly.
    check()
    with ExitStack() as owned:
        with exclusive_lock(RUNTIME / 'NATIVE_WORKER.lock', wait=True, check=check):
            if not date_owned:
                owned.enter_context(exclusive_lock(attempt / 'WORKER.lock'))
            for number in ((1, 2, 3) if request['arm'] == 'B1' else (slot,)):
                owned.enter_context(exclusive_lock(RUNTIME / 'native_slots' / f'SLOT_{number}.lock'))
            peers = assert_no_other_native_worker(request)
            receipt = dict(schema='V42_MAY_NATIVE_WORKER_ADMISSION_V2', PASS=True,
                run_id=request['run_id'], arm=request['arm'], day=request['day'], worker_slot=slot,
                root=str(root), manifest_SHA=request['manifest_SHA'], worker=process(), peers=peers or [],
                B1_parallel_workers=1, B2_parallel_workers=3, Threads=1, P2_calls=0,
                own_tmp=str(attempt / 'tmp'), admitted_UTC=now())
            atomic(attempt / 'NATIVE_WORKER_ADMISSION.json', receipt)
        yield receipt


def run(request_path):
    started = time.perf_counter()
    request_path = d_path(request_path)
    request = read(request_path)
    root = d_path(request['root'])
    attempt = d_path(request['result']).parent
    if (request_path != attempt / 'request.json'
            or attempt != attempt_path(root, request['arm'], request['day'])
            or any(d_path(request[name]) != attempt / filename
                   for name, filename in (('output', 'output'), ('progress', 'progress.json'),
                                          ('result', 'RESULT.json'), ('error', 'error.json')))):
        raise PermissionError('WORKER_ARM_DATE_OUTPUT_ISOLATION')
    # Acquire before heartbeat/progress/error/result writes, and retain through
    # terminal persistence. A duplicate process cannot damage a live attempt.
    with exclusive_lock(attempt / 'WORKER.lock'):
        if Path(request['result']).exists():
            raise PermissionError('COMPLETED_ATTEMPT_NEVER_REEXECUTED')
        return _run_locked(request_path, request, started)


def _run_locked(request_path, request, started):
    # Include Coordinator request persistence, process dispatch and Python
    # startup in the same date's wall ceiling, before model construction.
    dispatch_seconds = max(0., (datetime.now(timezone.utc) - datetime.fromisoformat(request['started_UTC'])).total_seconds())
    date_started = started - dispatch_seconds
    root = d_path(request['root'])
    attempt = d_path(request['result']).parent
    output = d_path(request['output'])
    environment(attempt)
    identity = {k: request[k] for k in ('run_id', 'arm', 'day', 'attempt_id', 'algorithm_version')}
    worker = process(); stop = threading.Event(); mutex = threading.RLock()
    state = dict(phase='INPUT_IDENTITY_VERIFICATION', worker=worker,
                 worker_slot=request.get('worker_slot'), **identity)
    def progress(value):
        with mutex:
            state.update(canonical(value), timestamp_UTC=now())
            atomic(request['progress'], state)
    def heartbeat():
        while not stop.wait(2):
            with mutex:
                atomic(attempt / 'HEARTBEAT.json', dict(worker=worker, identity=identity,
                    timestamp_UTC=now(), phase=state['phase'], input_SHA=sha(Path(request['input_folder']) / 'NATIVE_INPUT.json')))
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    result = dict(identity=identity, PASS=False, status='IMPLEMENTATION_FAILURE',
                  started_UTC=request['started_UTC'], worker=worker, files=[], P2_calls=0, attempt_id=request['attempt_id'], algorithm_version=request['algorithm_version'])
    budget = None; scientific = None
    try:
        from .coordinator import validate_request, load_manifest, TERMINAL
        manifest = load_manifest(root)
        validate_request(root, manifest, request)
        with worker_scope(request), native_worker_admission(
                request, date_owned=True, started=date_started) as admission:
            result.update(worker_slot=admission['worker_slot'], own_tmp=admission['own_tmp'],
                          admission=record(attempt / 'NATIVE_WORKER_ADMISSION.json'))
            budget = DateBudget(attempt / 'NATIVE_RUNTIME_LEDGER.json', started=date_started, progress=progress)
            from . import a_stage, m_stage
            stage = a_stage if request['arm'] == 'B1' else m_stage
            scientific = stage.run(request, budget, progress)
            optimization_seconds = budget.wall()
            budget.check()
            status = scientific.get('classification', scientific.get('status', 'IMPLEMENTATION_FAILURE'))
            if status not in TERMINAL:
                status = 'VALIDATION_FAILURE'
            summary = {k: scientific.get(k) for k in (
                'UB', 'LB', 'certified_gap', 'planning_rho_max', 'case_sha', 'P2_calls')}
            summary.update(independent_Global_LB=summary['LB'], optimization_seconds=optimization_seconds,
                           Native_Runtime=budget.used(), wall_seconds=optimization_seconds)
            progress(dict(summary, phase='P1_CERTIFICATION_COMPLETE', classification=status))
            result.update(status=status, scientific_PASS=scientific.get('PASS') is True,
                          optimization_wall_seconds=optimization_seconds, fields=summary)
            if scientific.get('PASS') is True and status == 'PASS':
                target = .005 if request['arm'] == 'B1' else .03
                if (summary['certified_gap'] is None or not 0 <= summary['certified_gap'] <= target
                        or summary['UB'] is None or summary['LB'] is None or summary['UB'] < summary['LB']
                        or budget.used() > 5400):
                    raise ValueError('FINAL_ORIGINAL_CERTIFICATE_OR_BUDGET_FAILURE')
                # Actual/Fresh AC is separately timed, never used to extend P1.
                from .operations import run as operations
                from .preflight import native_zero
                evaluation_started = time.perf_counter()
                progress(dict(phase='PLANNING_FIXED_DECISION_FREEZE',evaluation_started_UTC=now()))
                with native_zero() as attempts:
                    evaluation = operations(request, scientific, progress)
                if attempts:
                    raise PermissionError('ACTUAL_FRESH_NATIVE_OPTIMIZATION_FORBIDDEN')
                evaluation_seconds = time.perf_counter() - evaluation_started
                result.update(evaluation_wall_seconds=evaluation_seconds, evaluation=evaluation)
                summary.update(Fresh_AC=evaluation, evaluation_wall_seconds=evaluation_seconds)
                progress(dict(evaluation_wall_seconds=evaluation_seconds))
                if evaluation.get('PASS') is True:
                    result.update(PASS=True, status='PASS')
                else:
                    result.update(status='FRESH_AC_FAILURE')
            output.mkdir(parents=True, exist_ok=True)
            # Immutable receipts refer transitively to all model/point artifacts.
            result['files'] = [record(p) for p in sorted(output.rglob('*')) if p.is_file()]
            result['files'].append(record(attempt / 'NATIVE_RUNTIME_LEDGER.json'))
            result.update(Native_Runtime=budget.used(), Native_calls=len(budget.calls),
                          B2_AIDC_optimization_calls=0 if request['arm'] == 'B2' else None,
                          input_SHA=sha(Path(request['input_folder']) / 'NATIVE_INPUT.json'))
    except BaseException as error:
        output.mkdir(parents=True, exist_ok=True)
        failure = dict(PASS=False, identity=identity, error=repr(error), traceback=traceback.format_exc(), UTC=now())
        atomic(request['error'], failure)
        atomic(output / 'WORKER_FAILURE.json', failure)
        retained = [record(p) for p in sorted(output.rglob('*')) if p.is_file()]
        ledger_path = attempt / 'NATIVE_RUNTIME_LEDGER.json'
        if ledger_path.exists():
            retained.append(record(ledger_path))
        result.update(PASS=False, status=classify(error), error=repr(error), files=retained)
        if scientific:
            result.update(scientific_PASS=scientific.get('PASS') is True,
                fields=canonical({k: scientific.get(k) for k in ('UB', 'LB', 'certified_gap', 'planning_rho_max', 'case_sha')}))
        if (result['status'] == 'TIME_LIMIT_NO_VALID_INCUMBENT' and scientific
                and scientific.get('UB') is not None):
            result['status'] = 'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
        if budget is not None:
            result.update(Native_Runtime=budget.used(), Native_calls=len(budget.calls), wall_seconds=budget.wall())
    finally:
        stop.set(); thread.join(timeout=5)
        result.update(finished_UTC=now(), total_worker_wall_seconds=time.perf_counter() - started)
        result.update(dispatch_wall_seconds=dispatch_seconds,
                      total_date_wall_seconds=time.perf_counter() - date_started)
        atomic(request['result'], result)
        progress(dict(phase='TERMINAL', classification=result['status'], PASS=result['PASS']))
        atomic(attempt / 'HEARTBEAT.json', dict(worker=worker, identity=identity,
            timestamp_UTC=now(), phase='TERMINAL', status=result['status']))
    return 0 if result['PASS'] else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('request')
    return run(parser.parse_args().request)


if __name__ == '__main__':
    raise SystemExit(main())
