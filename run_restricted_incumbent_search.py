"""Bounded same-1841-column integer UB search after first TIME_LIMIT/no point.

No old incumbent/bound/checkpoint is imported. Native restricted bounds never
become global bounds; a candidate must pass the unchanged original validators.
"""
import os,time,json,traceback,subprocess
import numpy as np
import psutil
from run_restricted_1841 import *

def search():
    first=read(OUT/'RESTRICTED_INTEGER_MASTER_RESULT.json')
    assert first['native_status']==9 and first['integer_UB'] is None
    with (OUT/'RESTRICTED_INCUMBENT_SEARCH_REGISTERED.json').open('x',encoding='utf8') as f:
        json.dump(dict(pid=os.getpid(),creation=psutil.Process().create_time(),native_cap=480.,maximum_calls=1,
            source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            reason='Initial 120s restricted integer master spent most of its budget on root relaxation and had no integer point; latest user requests a valid restricted integer UB before BAP.',
            initial_call_native=first['native_runtime'],same_1841_pool=True,partial_native_checkpoint_imported=False),f,indent=2)
    start=time.perf_counter();m,v,meta=canonical_rebuild(RAW);vars=m.getVars();pool=read(ROOT/'docs/v42_m_stage_exact_completion/DW_CHECKPOINT_LATEST.json')['pool']
    m.setAttr('VType',vars[-1841:],['I']*1841);m.update()
    # A MIP candidate from the original seed columns. Solver may reject it;
    # it is not called feasible or an incumbent until independent validation.
    selected={next(j for j,h in enumerate(pool) if h['MESS']==f'MESS{i+1:02d}') for i in range(4)}
    m.setAttr('Start',vars[-1841:],[1. if j in selected else 0. for j in range(1841)])
    for k,x in dict(Threads=1,MIPGap=.005,Method=2,NodeMethod=1,MIPFocus=1,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,Seed=20260929,TimeLimit=480.,LogToConsole=0).items():m.setParam(k,x)
    m.Params.LogFile=str(OUT/'RESTRICTED_INCUMBENT_SEARCH.log');telemetry=[];last=[0.]
    def callback(m,w):
        now=time.perf_counter()
        if now-last[0]>=1:
            last[0]=now;pm=psutil.Process().memory_info();telemetry.append(dict(wall=now-start,RAM_available=psutil.virtual_memory().available,RSS=pm.rss,commit=getattr(pm,'pagefile',None)))
    print('RESTRICTED_INCUMBENT_SEARCH_STARTED',flush=True);m.optimize(callback)
    result=dict(native_status=m.Status,native_runtime=m.Runtime,nodes=m.NodeCount,integer_UB=None,restricted_native_bound=m.ObjBound if abs(m.ObjBound)<1e90 else None,
        restricted_bound_never_global=True,new_native_calls=1,total_restricted_native_calls=2,total_restricted_native_runtime=first['native_runtime']+m.Runtime,
        wall=time.perf_counter()-start,resource_telemetry=telemetry)
    if m.SolCount:
        x=np.asarray(m.getAttr('X'));np.savez_compressed(OUT/'RESTRICTED_INCUMBENT_SEARCH_RAW.npz',point=x)
        A,d,B,e,*_=inputs();owner,row_owner=axes()
        try:
            y,audit=validate_integer(v,x,pool,A,d,B,e,owner,row_owner)
            np.savez_compressed(OUT/'VALID_INTEGER_ORIGINAL_POINT.npz',point=y)
            result.update(integer_UB=audit['objective'],independent_audit=audit,original_point_SHA=sha(OUT/'VALID_INTEGER_ORIGINAL_POINT.npz'))
        except (AssertionError,ValueError) as exc:result['candidate_rejected']=str(exc)
    write('RESTRICTED_INCUMBENT_SEARCH_RESULT.json',result)
    print(json.dumps({k:x for k,x in result.items() if k not in ('resource_telemetry','independent_audit')}),flush=True);m.dispose()
if __name__=='__main__':
    try:search()
    except BaseException:
        write('RESTRICTED_INCUMBENT_SEARCH_ERROR.json',dict(traceback=traceback.format_exc()));raise
