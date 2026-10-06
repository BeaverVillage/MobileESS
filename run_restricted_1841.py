"""One bounded integer-master UB attempt after the frozen conservative gate.

The integer master's native bound is restricted-domain evidence, never global LB.
"""
from pathlib import Path
import json,time,hashlib,os,traceback,subprocess
import numpy as np
from scipy import sparse
import psutil
from revalidate_rmp43 import canonical_rebuild
from v42_degen.identity import inputs
from v42_dw_root.partition import axes
from v42_dw_resume.audit import corrected_rows,prototypes,pure_binary_equalities

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'docs/v42_m1_conservative_early_bap_20261006'
RAW=ROOT/'docs/v42_m1_numerical_dual_certificate_20261006/polish/POLISHED_TERMINAL_BEFORE_GATE.npz'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,x):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False),encoding='utf8')
def pool_point(h):
    p=ROOT/h['file'];assert sha(p)==h['file_SHA']
    with np.load(p) as z:return (z['x'] if 'x' in z else z['local_values']).copy()
def validate_integer(v,x,pool,A,d,B,e,owner,row_owner):
    offset=len(x)-len(pool);lam=x[offset:]
    assert np.array_equal(lam,np.rint(lam)) and np.isin(lam,[0.,1.]).all(),'RAW_LAMBDA_NOT_EXACT_INTEGER'
    y=np.zeros(A.shape[1]);global_axis=np.flatnonzero(owner<0);y[global_axis]=x[:offset]
    selected=[];physical=[]
    with np.load(ROOT/'docs/v42_m1_exact_dw_cg_root_pilot/DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native)
    for unit in range(4):
        ix=[j for j,h in enumerate(pool) if int(h['MESS'][-2:])-1==unit and lam[j]==1]
        assert len(ix)==1,'EXACT_CONVEXITY_SELECTION_REQUIRED'
        j=ix[0];local=pool_point(pool[j]);b=blocks[unit]
        y[b.columns]=local;physical.append(b.validate(local,True));selected.append(dict(column=j,**pool[j]))
    audit=corrected_rows(A,d,y,True,pure_binary_equalities(A,d))
    assert audit['PASS'] and all(p['PASS'] for p in physical),'INTEGER_ORIGINAL_OR_PHYSICAL_AUDIT_FAILED'
    objective=float(d['objective']@y+float(d['constant']))
    assert abs(objective-float(v['objective']@x+v['constant']))<=1e-8
    return y,dict(PASS=True,objective=objective,full_original=audit,local_physical=physical,selected=selected,
        original_integer_pattern_exact=True,repairs=0,restricted_native_bound_not_global=True)
def run():
    assert read(OUT/'certificate/SPLIT_DUAL_GATES.json')['EXACT_DUAL_AUTHORITY_FOR_BAP']
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'RESTRICTED_INTEGER_ONCE.json').open('x',encoding='utf8') as f:
        json.dump(dict(pid=os.getpid(),creation=psutil.Process().create_time(),maximum_calls=1,
                       source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),f)
    start=time.perf_counter();model,v,meta=canonical_rebuild(RAW)
    pool=read(ROOT/'docs/v42_m_stage_exact_completion/DW_CHECKPOINT_LATEST.json')['pool'];assert len(pool)==1841
    model.setAttr('VType',model.getVars()[-1841:],['I']*1841);model.update()
    for k,w in dict(Threads=1,MIPGap=.005,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,Seed=20260929,TimeLimit=120.,LogToConsole=0).items():model.setParam(k,w)
    model.Params.LogFile=str(OUT/'RESTRICTED_INTEGER_MASTER.log')
    write('RESTRICTED_INTEGER_PRE_SOLVE.json',dict(retained_columns=1841,objective_rows_original_bounds_unchanged=True,
        only_lambda_types_changed_to_integer=True,MIPGap=.005,cap=120.,build_wall=time.perf_counter()-start))
    telemetry=[];last=[0.]
    def callback(m,where):
        now=time.perf_counter()
        if now-last[0]>=1:
            vm=psutil.virtual_memory();pm=psutil.Process().memory_info();telemetry.append(dict(wall=now-start,RAM_available=vm.available,RSS=pm.rss,commit=getattr(pm,'pagefile',None)));last[0]=now
    print('RESTRICTED_INTEGER_OPTIMIZE_STARTED',flush=True);model.optimize(callback)
    result=dict(native_status=model.Status,native_runtime=model.Runtime,nodes=model.NodeCount,integer_UB=None,
        restricted_native_bound=model.ObjBound if abs(model.ObjBound)<1e90 else None,restricted_bound_never_global=True,
        new_native_calls=1,wall=time.perf_counter()-start,resource_telemetry=telemetry)
    if model.SolCount:
        x=np.asarray(model.getAttr('X'));np.savez_compressed(OUT/'RESTRICTED_INTEGER_RAW.npz',point=x)
        A,d,B,e,*_=inputs();owner,row_owner=axes()
        try:
            y,audit=validate_integer(v,x,pool,A,d,B,e,owner,row_owner)
            np.savez_compressed(OUT/'VALID_INTEGER_ORIGINAL_POINT.npz',point=y)
            result.update(integer_UB=audit['objective'],independent_audit=audit,original_point_SHA=sha(OUT/'VALID_INTEGER_ORIGINAL_POINT.npz'))
        except (AssertionError,ValueError) as exc:result.update(candidate_rejected=str(exc))
    write('RESTRICTED_INTEGER_MASTER_RESULT.json',result);print(json.dumps({k:x for k,x in result.items() if k not in ('resource_telemetry','independent_audit')}),flush=True);model.dispose()
if __name__=='__main__':
    try:run()
    except BaseException:
        write('RESTRICTED_INTEGER_DRIVER_ERROR.json',dict(traceback=traceback.format_exc()));raise
