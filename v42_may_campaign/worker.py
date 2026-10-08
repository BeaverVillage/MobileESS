"""One fresh date attempt; all science is delegated to the existing A/M ports."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import threading
import time
import traceback
import psutil
from .common import (RUNTIME, atomic, read, record, now, process, sha,
                     d_path, environment, exclusive_lock, LockBusy)
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
    for target, keys in {
        'independent_Global_LB': ('Certified_Global_LB', 'global_LB', 'LB'),
        'certified_gap': ('Certified_Gap', 'certified_gap'),
    }.items():
        for key in keys:
            if key in value and value[key] is not None:
                value[target] = value[key]; break
    return value


def assert_no_other_native_worker():
    # Monitors and this campaign's Coordinator/Watchdog are read-only parents.
    for candidate in psutil.process_iter(['pid', 'cmdline', 'name']):
        if candidate.pid == psutil.Process().pid:
            continue
        try:
            args = candidate.info['cmdline'] or []
            if (candidate.info.get('name') or '').lower() not in ('python.exe', 'pythonw.exe', 'python'):
                continue
            module = args[args.index('-m') + 1] if '-m' in args and len(args) > args.index('-m') + 1 else ''
            if module == 'v42_may_campaign.worker':
                raise LockBusy('OTHER_CAMPAIGN_WORKER_PID:' + str(candidate.pid))
            if (module.startswith(('v42_a_stage', 'v42_m1_')) or module == 'v42_pr134_b1.worker'):
                raise LockBusy('OTHER_SCIENTIFIC_WORKER_PID:' + str(candidate.pid))
        except psutil.Error:
            continue


def run(request_path):
    started = time.perf_counter()
    request_path = d_path(request_path)
    request = read(request_path)
    # Include Coordinator request persistence, process dispatch and Python
    # startup in the same date's wall ceiling, before model construction.
    dispatch_seconds = max(0., (datetime.now(timezone.utc) - datetime.fromisoformat(request['started_UTC'])).total_seconds())
    date_started = started - dispatch_seconds
    root = d_path(request['root']); environment(root)
    attempt = d_path(request['result']).parent
    output = d_path(request['output'])
    if (request_path != attempt / 'request.json' or output != attempt / 'output'
            or attempt != root / 'dates' / request['arm'] / request['day']):
        raise PermissionError('WORKER_ARM_DATE_OUTPUT_ISOLATION')
    if Path(request['result']).exists():
        raise PermissionError('COMPLETED_ATTEMPT_NEVER_REEXECUTED')
    identity = {k: request[k] for k in ('run_id', 'arm', 'day')}
    worker = process(); stop = threading.Event(); mutex = threading.RLock()
    state = dict(phase='INPUT_IDENTITY_VERIFICATION', worker=worker, **identity)
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
                  started_UTC=request['started_UTC'], worker=worker, files=[], P2_calls=0)
    budget = None; scientific = None
    try:
        from .coordinator import validate_request, load_manifest, TERMINAL
        manifest = load_manifest(root)
        validate_request(root, manifest, request)
        with exclusive_lock(RUNTIME / 'NATIVE_WORKER.lock'), worker_scope(request):
            assert_no_other_native_worker()
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
                        or optimization_seconds > 5400 or budget.used() > 5400):
                    raise ValueError('FINAL_ORIGINAL_CERTIFICATE_OR_BUDGET_FAILURE')
                # Actual/Fresh AC is separately timed, never used to extend P1.
                from .operations import run as operations
                from .preflight import native_zero
                evaluation_started = time.perf_counter()
                with native_zero() as attempts:
                    evaluation = operations(request, scientific, progress)
                if attempts:
                    raise PermissionError('ACTUAL_FRESH_NATIVE_OPTIMIZATION_FORBIDDEN')
                evaluation_seconds = time.perf_counter() - evaluation_started
                result.update(evaluation_wall_seconds=evaluation_seconds, evaluation=evaluation)
                summary.update(Fresh_AC=evaluation, evaluation_wall_seconds=evaluation_seconds)
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
