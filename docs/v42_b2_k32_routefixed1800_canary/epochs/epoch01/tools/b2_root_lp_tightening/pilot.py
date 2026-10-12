"""Three capped, sequential LP experiments; no integer optimization or campaign.

BASE is the literal K48 model with only binary types relaxed. GRID and SOC
append independently verified cuts. Source, incumbent and all predecessor
artifacts remain immutable. A consumed call can never be restarted.
"""
from pathlib import Path
from fractions import Fraction
import argparse, gc, hashlib, json, math, os, shutil, sys, time, traceback
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
from tools.b2_root_lp_tightening.resources import memory, admission, inventory, heavy_candidates, b1_safety, quick_callback_b1_safety
OUT=ROOT/'docs/v42_b2_root_lp_tightening/base'
PREVIOUS=ROOT/'docs/v42_critical_grid_cg/iteration02'
KIND='BASE'
GIB=1024**3
PARAMS=dict(Threads=1,TimeLimit=240,Method=1,FeasibilityTol=1e-8,OptimalityTol=1e-8)


def require(ok,reason):
    if not ok: raise ValueError(reason)


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(p)


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def data(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in z.files}


def build():
    require(not (OUT/'NATIVE0.json').exists(),'SEALED_MODEL_NO_REBUILD')
    start=time.perf_counter();before=memory()
    parent=read(PREVIOUS/'INDEPENDENT_CERTIFICATE.json')
    require(parent['PASS'],'PARENT_NOT_CERTIFIED')
    if KIND=='BASE':
        frozen=read(PREVIOUS/'INDEPENDENT_NATIVE0.json')['file_sha256']
        for name,digest in frozen.items():require(sha(PREVIOUS/name)==digest,'FROZEN_K48_BYTES:'+name)
        A=sparse.load_npz(PREVIOUS/'JOINT_A.npz').tocsr();d=data(PREVIOUS/'JOINT_DATA.npz')
        require(np.count_nonzero(d['vtypes']=='B')==9322 and np.all(np.isin(d['vtypes'],['B','C'])),'K48_TYPES')
        original_binary=np.flatnonzero(d['vtypes']=='B')
        d['vtypes']=np.full(len(d['vtypes']),'C')
        axes=PREVIOUS/'JOINT_AXES.npz';warm=PREVIOUS/'JOINT_START.npz'
    else:
        require(parent['solver_status']==2 and parent['LP_completed_numerical_OPTIMAL'],'BASE_LP_NOT_OPTIMAL_CERTIFIED')
        A=sparse.load_npz(PREVIOUS/'LP_A.npz').tocsr();d=data(PREVIOUS/'LP_DATA.npz')
        original_binary=data(PREVIOUS/'LP_ORIGINAL_BINARY.npz')['columns']
        packet=read(OUT/'CUTS_EXACT.json');rows=packet['rows']
        require(1<=len(rows)<=(16 if KIND=='GRID' else 32),'CUT_COUNT_GATE')
        rr=[];cc=[];vv=[]
        for i,row in enumerate(rows):
            for col,coef in sorted(row['terms'].items(),key=lambda pair:int(pair[0])):
                rr.append(i);cc.append(int(col));vv.append(float(Fraction(coef)))
        cuts=sparse.csr_matrix((vv,(rr,cc)),shape=(len(rows),A.shape[1]))
        oldrows=A.shape[0];A=sparse.vstack((A,cuts),format='csr')
        d['rhs']=np.r_[d['rhs'],[float(row['native_rhs']) for row in rows]]
        d['senses']=np.r_[d['senses'],np.full(len(rows),'<')]
        d['row_names']=np.r_[d['row_names'],[row['name'] for row in rows]]
        point=data(PREVIOUS/'LP_POINT.npz')['x']
        require(np.all(cuts@point-d['rhs'][oldrows:]>0),'CUTS_DO_NOT_EXCLUDE_BASE_FRACTIONAL_POINT')
        axes=PREVIOUS/'LP_AXES.npz';warm=PREVIOUS/'LP_START.npz'
    require(A.shape[1]==244265 and A.shape[0]<=160000 and A.nnz<=1800000 and np.all(d['vtypes']=='C'),'LP_SIZE_OR_TYPES')
    OUT.mkdir(parents=True,exist_ok=True)
    sparse.save_npz(OUT/'LP_A.npz',A);np.savez_compressed(OUT/'LP_DATA.npz',**d)
    np.savez_compressed(OUT/'LP_ORIGINAL_BINARY.npz',columns=original_binary)
    shutil.copyfile(axes,OUT/'LP_AXES.npz');shutil.copyfile(warm,OUT/'LP_START.npz')
    x=data(OUT/'LP_START.npz')['x'];residual=A@x-d['rhs']
    error=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
    require(float(error.max())<=1e-8,'ORIGINAL_U4_REPLAY')
    files=['LP_A.npz','LP_DATA.npz','LP_AXES.npz','LP_START.npz','LP_ORIGINAL_BINARY.npz']
    if KIND!='BASE':files.append('CUTS_EXACT.json')
    write(OUT/'NATIVE0.json',dict(PASS=True,kind=KIND,parent_PR211='d12315a3757aec187c8da0685c28ef901466386a',
          source18r='497609b46faa14ea7e32a9483a333ab32fd264ef',previous=str(PREVIOUS),
          previous_certificate_sha256=sha(PREVIOUS/'INDEPENDENT_CERTIFICATE.json'),Native_optimize_calls=0,
          original_binary_count=9322,dimensions=dict(rows=A.shape[0],columns=A.shape[1],binary=0,nnz=int(A.nnz)),
          matrix_sha=matrix_sha(A),domain_sha=_domain_sha(d),file_sha256={name:sha(OUT/name) for name in files},
          U4_max_violation=float(error.max()),model_extraction_seconds=time.perf_counter()-start,
          memory_before=before,memory_after=memory()))
    print(json.dumps(dict(PASS=True,kind=KIND,rows=A.shape[0],columns=A.shape[1],nnz=int(A.nnz))))


def attr(model,name):
    try:
        v=getattr(model,name)
        return None if isinstance(v,float) and not math.isfinite(v) else v
    except Exception:return None


def native():
    require(not (OUT/'PILOT_STARTED.json').exists(),'LP_CALL_LATCH_EXISTS_NO_RETRY')
    zero=read(OUT/'NATIVE0.json');independent=read(OUT/'INDEPENDENT_NATIVE0.json')
    require(zero['PASS'] and independent['PASS'],'INDEPENDENT_NATIVE0_GATE')
    for name,digest in zero['file_sha256'].items():require(sha(OUT/name)==digest,'SEALED_MODEL_DRIFT:'+name)
    safety=b1_safety();write(OUT/'PRE_NATIVE_B1_SAFETY.json',safety)
    require(safety['PASS'],'B1_PRIORITY_GATE')
    peers,errors=inventory();heavy=heavy_candidates(peers)
    write(OUT/'PRE_NATIVE_PEERS.json',dict(PASS=not heavy and not errors,peers=peers,errors=errors,heavy_peers=heavy))
    require(not heavy and not errors,'OTHER_HEAVY_NATIVE_PRESENT')
    before=memory();require(admission(before),'PRE_BUILD_MEMORY')
    A=sparse.load_npz(OUT/'LP_A.npz').tocsr();d=data(OUT/'LP_DATA.npz')
    import gurobipy as gp
    from gurobipy import GRB
    env=gp.Env(empty=True);env.setParam('LogFile',str(OUT/'NATIVE.log'));env.start()
    model=gp.Model('B2_K48_'+KIND+'_LP_ONLY',env=env)
    for key,value in PARAMS.items():model.setParam(key,value)
    start=time.perf_counter()
    x=model.addMVar(A.shape[1],lb=d['lb'],ub=d['ub'],obj=d['c'],vtype=GRB.CONTINUOUS)
    model.addMConstr(A,x,d['senses'],d['rhs']);model.ObjCon=float(d['constant']);model.ModelSense=GRB.MINIMIZE;model.update()
    create=time.perf_counter()-start
    readback=model.getA().tocsr()
    checks=dict(matrix=matrix_sha(readback)==matrix_sha(A),rhs=np.array_equal(model.getAttr('RHS'),d['rhs']),
          senses=np.array_equal(model.getAttr('Sense'),d['senses']),lower=np.array_equal(x.LB,d['lb']),
          upper=np.array_equal(x.UB,d['ub']),types=np.array_equal(x.VType,d['vtypes']),objective=np.array_equal(x.Obj,d['c']),
          ObjCon=model.ObjCon==float(d['constant']),ModelSense=model.ModelSense==1,Rows=model.NumConstrs==A.shape[0],
          Columns=model.NumVars==A.shape[1],Binary=model.NumBinVars==0,IsMIP=model.IsMIP==0,NNZ=model.NumNZs==A.nnz)
    del readback;gc.collect()
    write(OUT/'NATIVE_READBACK.json',dict(PASS=all(checks.values()),checks=checks,matrix_sha=matrix_sha(A),
          parameters={key:getattr(model.Params,key) for key in PARAMS},model_build_seconds=create,gurobi_version=list(gp.gurobi.version())))
    require(all(checks.values()),'LP_NATIVE_READBACK_FAILED')
    post=memory();growth=max(0,post['Private_Commit_bytes']-before['Private_Commit_bytes']);reserve=max(2*GIB,4*growth)
    write(OUT/'MEMORY_ADMISSION.json',dict(PASS=admission(post,reserve),sample=post,RAM_reserve_bytes=4*GIB,
          commit_reserve_bytes=6*GIB,estimated_additional_bytes=reserve,observed_model_build_private_growth_bytes=growth))
    require(admission(post,reserve),'POST_BUILD_MEMORY')
    safety=b1_safety();write(OUT/'PRE_OPTIMIZE_B1_SAFETY.json',safety);require(safety['PASS'],'FRESH_B1_PRIORITY_GATE')
    peers,errors=inventory();heavy=heavy_candidates(peers)
    write(OUT/'PRE_OPTIMIZE_PEERS.json',dict(PASS=not heavy and not errors,peers=peers,errors=errors,heavy_peers=heavy))
    require(not heavy and not errors,'FRESH_OTHER_HEAVY_NATIVE_GATE')
    ledger_path=OUT.parent/'NATIVE_LEDGER.json'
    ledger=read(ledger_path) if ledger_path.exists() else dict(calls=[],maximum_calls=3,maximum_requested_seconds=720)
    require(len(ledger['calls'])<3 and KIND not in [call['kind'] for call in ledger['calls']],'GLOBAL_LP_CALL_LIMIT')
    require(sum(call['TimeLimit'] for call in ledger['calls'])+240<=720,'GLOBAL_LP_NATIVE_BUDGET')
    ledger['calls'].append(dict(kind=KIND,TimeLimit=240,time=time.time(),pid=os.getpid(),out=str(OUT)))
    write(ledger_path,ledger)
    with (OUT/'PILOT_STARTED.json').open('x',encoding='utf-8') as stream:
        json.dump(dict(kind=KIND,maximum_optimize_calls=1,pid=os.getpid(),parameters=PARAMS,
                       files=zero['file_sha256'],independent_native0_sha256=sha(OUT/'INDEPENDENT_NATIVE0.json')),stream,indent=2)
    samples=[post];issues=[];b1_stops=[];memory_stops=[];last_memory=0.;last_b1=0.
    def callback(m,where):
        nonlocal last_memory,last_b1
        now=time.monotonic()
        try:
            if now-last_memory>=.5:
                sample=memory();samples.append(sample);last_memory=now
                if not admission(sample,0):memory_stops.append(sample);m.terminate()
            if now-last_b1>=5:
                record=quick_callback_b1_safety();last_b1=now
                if not record['PASS']:
                    b1_stops.append(record)
                    m.terminate()
            if where==GRB.Callback.MESSAGE:
                msg=m.cbGet(GRB.Callback.MSG_STRING)
                if any(token in msg.lower() for token in ('numerical trouble','out of memory','numeric error')):
                    issues.append(msg.strip());m.terminate()
        except Exception as exc:issues.append(repr(exc));m.terminate()
    begin=time.perf_counter();error=None
    try:model.optimize(callback)
    except Exception as exc:error=repr(exc)
    elapsed=time.perf_counter()-begin;samples.append(memory())
    status=attr(model,'Status')
    if status==GRB.OPTIMAL and not issues and not error and not b1_stops and not memory_stops:
        np.savez_compressed(OUT/'LP_POINT.npz',x=x.X,pi=model.getAttr('Pi'),rc=x.RC)
    result=dict(kind=KIND,Status=status,Native_optimize_calls=1,TimeLimit=240,
          full_MILP_calls=0,campaign_calls=0,IEEE8500_calls=0,ObjVal=attr(model,'ObjVal'),
          ObjBound=attr(model,'ObjBound'),Runtime=attr(model,'Runtime'),IterCount=attr(model,'IterCount'),
          BarIterCount=attr(model,'BarIterCount'),model_build_seconds=create,optimize_wall_seconds=elapsed,
          MaxMemUsed_GB=attr(model,'MaxMemUsed'),peak_process_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),
          peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),
          minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),
          minimum_commit_available=min(s['system']['Commit_available'] for s in samples),
          callback_errors=issues,optimize_error=error,b1_conflict_stop=bool(b1_stops),memory_stop=bool(memory_stops),
          LP_OPTIMAL_candidate=status==2 and not issues and not error and not b1_stops and not memory_stops,
          independent_certificate_required=True,reduced_primal_is_FULL_UB=False)
    write(OUT/'MEMORY_TRACE.json',dict(samples=samples,unsafe_samples=memory_stops))
    write(OUT/'B1_PRIORITY_TRACE.json',dict(conflicts=b1_stops,mutations=0,normal_B2_terminate_on_B1_appearance=True))
    model.dispose();env.dispose();write(OUT/'RESULT.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['build','native'],required=True)
    ap.add_argument('--kind',choices=['BASE','GRID','SOC'],default=KIND);ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--previous',type=Path,default=PREVIOUS)
    args=ap.parse_args();KIND=args.kind;OUT=args.out.resolve();PREVIOUS=args.previous.resolve()
    try:build() if args.mode=='build' else native()
    except Exception as exc:
        write(OUT/(args.mode.upper()+'_FAILURE.json'),dict(error=repr(exc),traceback=traceback.format_exc(),
              Native_optimize_started=(OUT/'PILOT_STARTED.json').exists(),memory=memory()))
        raise
