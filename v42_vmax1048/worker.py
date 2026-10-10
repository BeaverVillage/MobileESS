"""Own one real B2 May01 diagnostic attempt without touching existing solvers."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import sys
import threading
import time
import traceback

from v42_pr134_b1.common import atomic,now,read,record,process
from v42_common_campaign.authority import singleton
from . import POLICY
from .authority import verify_request,assert_peers


def run(request_path):
    request=read(request_path)
    manifest=verify_request(request)
    assert_peers(request)
    attempt=Path(request['result']).parent
    if Path(request['result']).exists() or (attempt/'NATIVE_RUNTIME_LEDGER.json').exists():
        raise PermissionError('VMAX1048_PRIOR_ATTEMPT_REQUIRES_MEASURED_RECOVERY_NOT_RESET')
    started=time.perf_counter()
    stopped=threading.Event();mutex=threading.RLock()
    state=dict(arm='B2',day=request['day'],stage='B2_M',phase='SOURCE_ADMISSION',
        source_SHA=request['source_SHA'],source_commit=manifest['source_commit'],
        planning_policy=POLICY,worker=process(),started_UTC=now())
    def progress(value):
        with mutex:
            state.update(value,updated_UTC=now(),worker_wall_seconds=time.perf_counter()-started)
            atomic(request['progress'],state)
    def ticker():
        while not stopped.wait(10):progress({})
    thread=threading.Thread(target=ticker,daemon=True)
    result=dict(identity={k:request[k] for k in ('run_id','arm','day','attempt_id')},
        source_SHA=request['source_SHA'],source_commit=manifest['source_commit'],
        algorithm_version=manifest['algorithm_version'],planning_policy=POLICY,
        planning_voltage_max_pu=1.048,actual_voltage_min_pu=.95,actual_voltage_max_pu=1.05,
        diagnostic_only=True,independent_holdout=False,all31_policy_conversion_approved=False,
        PASS=False,status='IMPLEMENTATION_FAILURE',actual_ac_physical_pass=False,
        worker=process(),request=record(request_path),started_UTC=now())
    progress({});thread.start()
    observer=None
    try:
        shared=Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\native_slots')
        with singleton(attempt/'WORKER.lock'),singleton(shared/'SLOT_3.lock'),singleton(shared/'VMAX1048_DIAGNOSTIC.lock'):
            from v42_common_campaign import b2
            from v42_common_mess.planning_policy import scope
            from .actual_controls import observer_context
            # The original Native scope and cumulative DateBudget remain active.
            # The diagnostic permit replaces admission with stricter policy/source
            # checks, including explicitly preserved canary peers and their SHA.
            with ExitStack() as stack:
                stack.enter_context(patch.object(b2,'verify_request',verify_request))
                stack.enter_context(patch.object(b2,'assert_peers',assert_peers))
                stack.enter_context(scope(POLICY,baseline_output=manifest['original_May01_output']))
                observer=stack.enter_context(observer_context(Path(request['output']),source_SHA=request['source_SHA']))
                result.update(b2.run(request,manifest,progress))
            if observer.receipt is not None:
                result['actual_control_observer']=observer.receipt
                observation=read(observer.receipt['path'])
                if result.get('evaluation') is not None and (
                        observation.get('PASS') is not True or observation.get('slots') != 96
                        or observation.get('control_actions_done_slots') != 96
                        or observation.get('regulator_settings_SHA') != manifest['original_regcontrol_settings_SHA']
                        or observation.get('execution_source_SHA') != request['source_SHA']
                        or observation.get('Actual_voltage_limits_pu') != [.95,1.05]):
                    result.update(PASS=False,status='ACTUAL_CONTROL_OBSERVATION_FAILED')
            model_audit=Path(request['output'])/'VMAX1048_MODEL_POLICY_AUDIT.json'
            if model_audit.is_file():result['planning_model_policy_audit']=record(model_audit)
    except Exception as error:
        result.update(PASS=False,actual_ac_physical_pass=False,
            status='INPUT_OR_SOURCE_FAILURE' if isinstance(error,PermissionError) else 'IMPLEMENTATION_FAILURE',
            error=repr(error),traceback=traceback.format_exc())
        atomic(request['error'],dict(error=repr(error),traceback=traceback.format_exc(),UTC=now()))
    finally:
        stopped.set();thread.join(timeout=2)
        result.update(completed_UTC=now(),worker_wall_seconds=time.perf_counter()-started)
        ledger_path=attempt/'NATIVE_RUNTIME_LEDGER.json'
        if ledger_path.is_file():
            ledger=read(ledger_path)
            result.update(native_ledger=record(ledger_path),Native_Runtime=ledger['measured_Native_Runtime'],
                native_runtime_seconds=ledger['measured_Native_Runtime'],native_calls=len(ledger['calls']),
                native_budget_overshoot_seconds=max(0.,ledger['measured_Native_Runtime']-1800))
            if ledger.get('inflight') is not None or any(row.get('runtime_unavailable') for row in ledger['calls']):
                result.update(PASS=False,status='INPUT_OR_SOURCE_FAILURE',actual_native_runtime='UNKNOWN')
        atomic(request['result'],result)
        progress(dict(phase=result['status'],state=result['status']))
    return result


if __name__=='__main__':
    result=run(sys.argv[1])
    print(dict(status=result['status'],PASS=result['PASS']))
    raise SystemExit(0 if result['PASS'] else 1)
