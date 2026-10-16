"""Independent B3 A2 attempt with its own full-domain bound and Native clock."""
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
from v42_may_campaign_native90.budget import DateBudget
from v43_mess.budget import worker_permit,heavy_peers
from .adapter import scope,require_m1


def export(result,request,mess,out):
    """Export new A2 decisions; M1 is fixed evidence, never an A2 UB/LB."""
    core=read(result['freeze']['path']);prepare=read(out/'A_PREPARE_RECEIPT.json')
    if result['arm']!='B3' or core.get('A2_P1_ONLY_ACCEPTED') is not True or core.get('P2_calls')!=0:
        raise ValueError('A2_ORIGINAL_P1_ACCEPTANCE_REQUIRED')
    with np.load(result['planning']['path'],allow_pickle=False) as z:arrays={k:z[k].copy() for k in z.files}
    known=arrays['known_GPU'];anonymous=arrays['GPU']-known
    if anonymous.min() < -1e-7:raise ValueError('A2_NEGATIVE_ANONYMOUS_GPU')
    arrays['known_gpu']=known;arrays['cc4_served_gpu']=np.maximum(anonymous,0.)
    np.savez_compressed(out/'FINAL_AIDC_PHYSICAL.npz',**arrays)
    sites=list(map(str,arrays['sites']))
    aidc=dict(selected_jobs=core['selected_jobs'],
        CC4_service={str(tuple(map(int,k[6:-1].split(',')))):v for k,v in core['globals'].items() if k.startswith('CC4_x[')},
        CC4_carryout={k[13:-1]:v for k,v in core['globals'].items() if k.startswith('CC4_carryout[')},
        AIDC_P_by_site={s:arrays['PCC_P_kw'][:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:arrays['PCC_Q_kvar'][:,j].tolist() for j,s in enumerate(sites)})
    native=read(Path(request['input_folder'])/'NATIVE_INPUT.json')
    identity=dict(schema='V43_PR189_FIXED_M1_A2_ACCEPTED_V1',day='2025-05-01',arm='B3',stage='A2',
        parent_case_sha=digest(dict(source=request['source_sha'],matrix=prepare['verification']['reference_snapshot_sha256'],
            M1_plan=mess['plan_sha'],input=core['scientific_input'])),
        aidc_anchor=digest(aidc),input=core['scientific_input']['NATIVE_INPUT.json'],
        windows=core['scientific_input']['WINDOWS.json'],reference=native['reference'],
        source=request['sources'],physical=record(out/'FINAL_AIDC_PHYSICAL.npz'),
        parent_acceptance=result['freeze'],fixed_M1=request['M1_result'],fixed_M1_plan_sha=mess['plan_sha'],
        FULL_feasible=True,independent_Global_LB=result['LB'],FULL_UB=result['UB'],global_gap=result['certified_gap'],
        old_stage_bounds_transferred=False,P2_calls=0)
    atomic(out/'AIDC_REFERENCE.json',dict(identity=identity,**aidc))
    return record(out/'AIDC_REFERENCE.json')


def run(path):
    request=read(path);attempt=Path(request['root']);out=Path(request['output'])
    if request['day']!='2025-05-01' or request['arm']!='B3' or request['stage']!='A2':raise ValueError('B3_A2_MAY01_ONLY')
    if attempt.exists():raise ValueError('NEW_INDEPENDENT_A2_ATTEMPT_REQUIRED')
    verify_records(request['sources']+[request['M1_result']])
    if digest(request['sources'])!=request['source_sha']:raise ValueError('A2_SOURCE_FREEZE_SHA')
    m1=read(request['M1_result']['path']);mess=require_m1(m1)
    if heavy_peers():raise ValueError('A2_NO_COMPETING_HEAVY_WORKER')
    attempt.mkdir(parents=True);atomic(attempt/'request.json',request)
    atomic(attempt/'START.json',dict(UTC=now(),pid=os.getpid(),process_created=psutil.Process().create_time(),
        source_commit=git('rev-parse','HEAD').decode().strip(),sources=request['sources'],M1_result=request['M1_result'],
        day='2025-05-01',arm='B3',stage='A2',Worker=1,Threads=1))
    done=threading.Event();latest={};began=time.perf_counter()
    def progress(value):
        latest.update(value);atomic(attempt/'progress.json',dict(latest,UTC=now(),stage='A2'))
        if (attempt/'STOP_REQUESTED.json').exists():
            from v42_may_campaign.execution import _model
            live=_model.get()
            if live is None:raise RuntimeError('V43_A2_OFFICIAL_STOP_REQUESTED')
            live['model'].terminate()
    def heartbeat():
        while not done.wait(10):
            p=psutil.Process();atomic(attempt/'HEARTBEAT.json',dict(UTC=now(),pid=p.pid,latest=latest,
                CPU_seconds=sum(p.cpu_times()[:2]),RSS_bytes=p.memory_info().rss,wall_seconds=time.perf_counter()-began))
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    class Budget(DateBudget):
        def check(self,reserve=0):
            if (attempt/'STOP_REQUESTED.json').exists():raise RuntimeError('V43_A2_OFFICIAL_STOP_REQUESTED')
            return super().check(reserve)
    budget=Budget(attempt/'NATIVE_RUNTIME_LEDGER.json',native_limit=5400.,progress=progress)
    result=dict(PASS=False,arm='B3',stage='A2',day='2025-05-01')
    try:
        with worker_permit(request,request['sources']):
            with scope(request,m1) as original_run:
                result=original_run(request,budget,progress)
            if result['PASS']:
                if not 0<=result['certified_gap']<=.005:raise ValueError('A2_INDEPENDENT_GLOBAL_GAP_REQUIRED')
                final=export(result,request,mess,out)
                result.update(AIDC_reference=final,FULL_feasible=True,stage='A2',
                    fixed_M1_plan_sha=mess['plan_sha'],MESS_optimization_calls=0,
                    M1_UB_LB_transferred=False,original_PR189_AIDC_algorithm=True)
            verify_records(request['sources']+[request['M1_result']])
    except BaseException as error:result.update(PASS=False,error=repr(error),traceback=traceback.format_exc())
    finally:
        done.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),Native_seconds=budget.used(),wall_seconds=time.perf_counter()-began,
            inflight=budget.inflight,P2_calls=0,FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False)
        atomic(attempt/'RESULT.json',result)
        atomic(attempt/'RECONCILIATION.json',dict(UTC=now(),Native_seconds=budget.used(),Native_calls=len(budget.calls),inflight=budget.inflight))
    print({k:result.get(k) for k in ('PASS','stage','Native_seconds','wall_seconds','error')})
    return result


if __name__=='__main__':run(sys.argv[1])
