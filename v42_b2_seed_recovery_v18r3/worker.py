"""One sealed fresh attempt; shared Native ledger and unchanged exact M pipeline."""
from contextlib import ExitStack
from pathlib import Path
import argparse
import threading
import traceback
import psutil
from .common import read, atomic, record, now, process, environment, exclusive_lock, RUNTIME
from .policy import verify_request, VERSION
from .execution import worker_scope, assert_peers
from .budget import DateBudget


def run(path):
    request=read(path);manifest=verify_request(request);attempt=Path(request['result']).parent
    environment(attempt);identity={k:request[k] for k in ('run_id','arm','day','attempt_id','algorithm_version')}
    state=dict(identity,phase='SOURCE_ADMISSION',worker=process());stop=threading.Event();mutex=threading.RLock()
    def progress(value):
        with mutex:
            state.update(value,timestamp_UTC=now());atomic(request['progress'],state)
    def heartbeat():
        peak=0
        while not stop.wait(2):
            peak=max(peak,psutil.Process().memory_info().rss)
            with mutex:
                state['peak_process_RSS_bytes']=peak
                atomic(attempt/'HEARTBEAT.json',dict(worker=state['worker'],timestamp_UTC=now(),
                    phase=state['phase'],peak_process_RSS_bytes=peak))
    result=dict(identity=identity,PASS=False,status='IMPLEMENTATION_FAILURE',source_SHA=request['implementation_SHA'],
        source_commit=manifest['source_commit'],worker=state['worker'],started_UTC=request['started_UTC'])
    budget=None
    with ExitStack() as locks:
        locks.enter_context(exclusive_lock(attempt/'WORKER.lock'))
        if Path(request['result']).exists():raise PermissionError('V18R3_COMPLETED_ATTEMPT_NEVER_REEXECUTED')
        locks.enter_context(exclusive_lock(RUNTIME/'native_slots'/f"SLOT_{request['worker_slot']}.lock"))
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        try:
            with worker_scope(request):
                budget=DateBudget(attempt/'NATIVE_RUNTIME_LEDGER.json',progress=progress)
                progress(dict(phase='MODEL_PREPARATION',**budget.snapshot()))
                if manifest.get('benchmark_initialization_only'):
                    from .benchmark import run as m_run
                else:
                    from .m_stage import run as m_run
                scientific=m_run(request,budget,progress)
                result.update(status=scientific['status'],scientific=scientific,PASS=False,
                    scientific_PASS=scientific['PASS'],Native_Runtime=budget.used(),Native_calls=len(budget.calls),
                    prior_Native_Runtime=(budget.prior_attempt or {}).get('Native_Runtime',0.))
                # Charge all actual termination overhead, retain final verified
                # witnesses, and never relabel a valid witness as 'no incumbent'.
                if budget.used()>budget.native_limit:
                    result.update(status='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED',
                        native_budget_overshoot_seconds=budget.used()-budget.native_limit,
                        Native_budget_PASS=False)
                if manifest.get('benchmark_initialization_only'):
                    result.update(PASS=scientific['PASS'] is True,benchmark_initialization_only=True)
                elif scientific['PASS'] is True:
                    from v42_b2_start_recovery_v13.operations import run as operations
                    from v42_b2_start_recovery_v13.preflight import native_zero
                    with native_zero() as attempts:
                        evaluation=operations(request,scientific,progress)
                    if attempts:raise PermissionError('V18R3_ACTUAL_NATIVE_FORBIDDEN')
                    result.update(evaluation=evaluation,PASS=evaluation.get('PASS') is True,
                        status='PASS' if evaluation.get('PASS') is True else 'FRESH_AC_FAILURE')
        except BaseException as exc:
            from v42_b2_start_recovery_v13.worker import classify
            failure=dict(error=repr(exc),traceback=traceback.format_exc(),UTC=now())
            atomic(request['error'],failure)
            result.update(status=classify(exc),error=failure,PASS=False)
            if budget:
                result.update(Native_Runtime=budget.used(),Native_calls=len(budget.calls),
                    prior_Native_Runtime=(budget.prior_attempt or {}).get('Native_Runtime',0.))
                if any(c.get('runtime_unavailable') for c in budget.calls):
                    result.update(status='QUARANTINE',Native_Runtime=None,
                        known_completed_Native_Runtime=budget.used(),remaining_native_seconds=None)
        finally:
            stop.set();thread.join(timeout=5)
            if budget and budget.conservative():
                result.update(Native_Runtime=None,actual_cumulative_Native_Runtime='UNKNOWN',
                    budget_basis='CONSERVATIVE_LOST_CALL_WINDOW',Native_budget_accounted_upper_bound=budget.used(),
                    remaining_native_seconds=budget.remaining(),
                    current_attempt_measured_Native_Runtime=sum(c.get('Native_Runtime') or 0 for c in budget.calls),
                    lost_call_reserved_seconds=budget.prior_attempt['lost_call_reserved_seconds'])
            result.update(finished_UTC=now(),files=[record(p) for p in sorted(Path(request['output']).rglob('*')) if p.is_file()])
            if budget:result['ledger']=record(budget.path)
            atomic(request['result'],result)
            progress(dict(phase='TERMINAL',classification=result['status'],PASS=result['PASS']))
    return 0 if result['PASS'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('request');a=p.parse_args();raise SystemExit(run(a.request))
