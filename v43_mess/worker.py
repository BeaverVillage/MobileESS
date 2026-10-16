"""One immutable May01 M stage: Original FULL, seedless K48, Beam/Joint."""
from contextlib import ExitStack
from pathlib import Path
import os
import sys
import threading
import time
import traceback

import numpy as np
import psutil

from v43.common import ROOT,DOC,read,record,verify_records,atomic,git,now
from v42_native.contracts import digest
from .library import load
from .budget import worker_permit,StageBudget,heavy_peers


def run(request_path):
    request=read(request_path);out=Path(request['output'])
    if out.exists():raise ValueError('NEW_INDEPENDENT_M_STAGE_ATTEMPT_REQUIRED')
    if heavy_peers():raise RuntimeError('OTHER_V43_HEAVY_WORKER_ALIVE')
    sources=request['sources'];verify_records(sources)
    if 'fixed_AIDC_record' in request:verify_records([request['fixed_AIDC_record']])
    if digest(sources)!=request['source_sha']:raise ValueError('M_STAGE_SOURCE_FREEZE_SHA')
    out.mkdir(parents=True)
    atomic(out/'request.json',request)
    atomic(out/'START.json',dict(UTC=now(),pid=os.getpid(),process_created=psutil.Process().create_time(),
        request=record(out/'request.json'),sources=sources,source_commit=git('rev-parse','HEAD').decode().strip(),
        Worker=1,Threads=1))
    latest={};done=threading.Event();began=time.perf_counter();budgets=[]
    def progress(value):
        latest.update(value);atomic(out/'progress.json',dict(latest,UTC=now()))
        if (out/'STOP_REQUESTED.json').exists():
            from v42_may_campaign.execution import _model
            live=_model.get()
            if live is None:raise RuntimeError('V43_M_OFFICIAL_STOP_REQUESTED')
            live['model'].terminate()
    def heartbeat():
        while not done.wait(10):
            p=psutil.Process();atomic(out/'HEARTBEAT.json',dict(UTC=now(),pid=p.pid,latest=latest,
                CPU_seconds=sum(p.cpu_times()[:2]),RSS_bytes=p.memory_info().rss,wall_seconds=time.perf_counter()-began))
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    result=dict(PASS=False,arm=request['arm'],stage=request['stage'],day=request['day'])
    control=None
    try:
        with worker_permit(request,sources):
            from v42_may_campaign_native90.preflight import native_zero
            from .case import build,golden_a1
            if request['arm']=='B2':
                from v43_arms.reference import load as baseline
                payload=baseline(request['fixed_AIDC_reference'])
            elif request['stage']=='M1':payload=golden_a1()
            else:
                from v43_arms.reference import load as fixed_aidc
                payload=fixed_aidc(request['fixed_AIDC_reference'])
                i=payload['identity']
                if (i.get('stage')!='A2' or i.get('arm')!='B3' or i.get('FULL_feasible') is not True
                        or not 0<=i.get('global_gap',1.)<=.005):
                    raise ValueError('M2_REQUIRES_CURRENT_FULL_A2_WITH_INDEPENDENT_GAP')
                verify_records([i['parent_acceptance']])
            with native_zero() as denied:
                progress(dict(phase='ORIGINAL_FULL_M_BUILD_NATIVE0'))
                case=build(payload,request,progress)
                modules=load();k=modules['table_v_k48'];m=modules['m_engine']
                packet,proof=k.prepare_k16(case,None,out/'NATIVE0_K16')
                if denied or proof.get('PASS') is not True:raise ValueError('REAL_M_NATIVE0_ORIGINAL_RELAXATION_PROOF_FAILED')
                atomic(out/'NATIVE0_CERTIFICATION.json',dict(PASS=True,Native_calls=0,case_sha=case.case_sha,
                    K16_original_FULL_inclusion=proof,previous_UB_LB_point_or_clock_reused=False,
                    Joint_FULL_lift='CHECKED_ON_EACH_GENERATED_POOL_BEFORE_NATIVE'))
            build_wall=time.perf_counter()-began
            control_module=modules['table_v_global_control']
            control=control_module.GlobalGapControl(control_module.mess_scope(case),.03,out/'GLOBAL_CONTROL')
            case.global_gap_control=control
            lower=StageBudget(out/'K48_NATIVE_LEDGER.json',case=case,kind='K48_SEPARATE',progress=progress);budgets.append(lower)
            progress(dict(phase='SEEDLESS_K16_K32_K48',case_sha=case.case_sha))
            from .prepared import run_prepared_k48
            lb=run_prepared_k48(k,case,packet,proof,lower,out/'K48_EXECUTION')
            del packet
            upper=StageBudget(out/'JOINT_NATIVE_LEDGER.json',case=case,kind='PLANNING_NATIVE',progress=progress);budgets.append(upper)
            progress(dict(phase='ADAPTIVE_BEAM_FOUR_DIRECT_JOINT'))
            ub,point=m.optimize_mess(case,None,[],upper)
            if point is not None:
                np.savez_compressed(out/'ACCEPTED_M_POINT.npz',point=point)
            bounds=control.bounds()
            result.update(PASS=ub['FULL_validated'],FULL_feasible=ub['FULL_validated'],case_sha=case.case_sha,
                identity=record(out/'SCIENTIFIC_CASE_IDENTITY.json'),fixed_AIDC=payload['identity'],
                lower=lb,upper=ub,**bounds,build_wall_seconds=build_wall,
                K48_Native_seconds=lower.used(),Joint_Native_seconds=upper.used(),
                K48_measured_ceiling_overrun_seconds=max(0.,lower.used()-lower.native_limit),
                Joint_measured_ceiling_overrun_seconds=max(0.,upper.used()-upper.native_limit),
                Native_budget_compliance='WITHIN_MEASURED_CEILINGS' if lower.used()<=lower.native_limit and upper.used()<=upper.native_limit
                    else 'MEASURED_SOLVER_TIMELIMIT_OVERRUN_RECORDED_NO_FURTHER_CALLS_IN_EXHAUSTED_LEDGER',
                MESS_plan=ub['mess'],Native_calls=sum(len(b.calls) for b in budgets),
                status='GLOBAL_GAP_PASS' if bounds['global_gap_certified'] else
                    'FULL_FEASIBLE_GAP_NOT_CERTIFIED' if ub['FULL_validated'] else 'NO_FULL_FEASIBLE_POINT',
                Actual_diagnostic_allowed=ub['FULL_validated'],restricted_ObjBound_is_Global_LB=False,
                historical_case_bounds_or_clocks_transferred=False,P2_calls=0)
            control.finish('GLOBAL_GAP_TARGET_MET' if bounds['global_gap_certified'] else
                'NATIVE_BUDGET_EXHAUSTED' if upper.remaining()<=10 else
                'NO_FURTHER_CERTIFIED_IMPROVEMENT' if ub['FULL_validated'] else 'NO_FULL_FEASIBLE_SOLUTION')
            verify_records(sources)
    except BaseException as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        if control is not None:control.close()
        done.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),wall_seconds=time.perf_counter()-began,
            Native_seconds=sum(b.used() for b in budgets),inflight=None,
            FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False)
        atomic(out/'RESULT.json',result)
        atomic(out/'RECONCILIATION.json',dict(UTC=now(),inflight=None,
            Native_seconds=sum(b.used() for b in budgets),Native_calls=sum(len(b.calls) for b in budgets)))
    print({k:result[k] for k in ('PASS','arm','stage','Native_seconds','wall_seconds')})
    return result


if __name__=='__main__':run(sys.argv[1])
