"""Append independently verified original cuts and run at most two 180-second stages.

No FULL Gurobi model or independent LP is created. Durable stage/global latches
consume authorization before optimize, including unsuccessful calls.
"""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import argparse, gc, hashlib, json, math, os, shutil, subprocess, sys, time, traceback
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.critical_grid_cg.resources import memory, admission, inventory
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
OUT=ROOT/'docs/v42_critical_grid_cg/iteration01'
PREVIOUS=ROOT/'docs/v42_joint_critical_grid_lb_pilot/native360'
STAGE=1
TIME_LIMIT=180
UB=.6760534504652341
OLD_LB=.42547778318693985
GIB=1024**3

def require(ok,reason):
    if not ok: raise ValueError(reason)
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(path)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()
def load_data(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k] for k in z.files}
def build():
    require(not (OUT/'NATIVE0.json').exists(),'SEALED_BUILD_NO_REBUILD')
    begin=time.perf_counter();pre=memory()
    packet=read(OUT/'CUTS_EXACT.json');parent=read(PREVIOUS/'INDEPENDENT_CERTIFICATE.json')
    require(parent['PASS'] and 1<=len(packet['rows'])<=16,'PARENT_OR_CUT_GATE')
    # Verify frozen parent bytes before loading the smaller Joint CSR.
    frozen=read(PREVIOUS/'NATIVE0.json')
    for name,digest in frozen.get('file_sha256',frozen.get('files',{})).items():
        require(sha(PREVIOUS/name)==digest,'PARENT_FROZEN_BYTES:'+name)
    A=sparse.load_npz(PREVIOUS/'JOINT_A.npz').tocsr();d=load_data(PREVIOUS/'JOINT_DATA.npz')
    oldrows=A.shape[0];rr=[];cc=[];vv=[];rhs=[];names=[]
    for i,row in enumerate(packet['rows']):
        terms=row['terms']
        for col,value in sorted(terms.items(),key=lambda pair:int(pair[0])):
            rr.append(i);cc.append(int(col));vv.append(float(F(value)))
        rhs.append(float(row['native_rhs']));names.append(row['name'])
    cuts=sparse.csr_matrix((vv,(rr,cc)),shape=(len(rhs),A.shape[1]))
    combined=sparse.vstack((A,cuts),format='csr')
    d['rhs']=np.r_[d['rhs'],rhs]
    d['senses']=np.r_[d['senses'],np.full(len(rhs),'<')]
    d['row_names']=np.r_[d['row_names'],names]
    require(combined.shape[1]==244265 and sum(d['vtypes']=='B')==9322 and combined.shape[0]<=160000 and combined.nnz<=1800000,'SIZE_GATE')
    sparse.save_npz(OUT/'JOINT_A.npz',combined);np.savez_compressed(OUT/'JOINT_DATA.npz',**d)
    for name in ('JOINT_AXES.npz','JOINT_START.npz'):shutil.copyfile(PREVIOUS/name,OUT/name)
    u4=load_data(OUT/'JOINT_START.npz')['x']
    oldinc=load_data(PREVIOUS/'JOINT_INCUMBENT.npz')['x']
    violations=cuts@oldinc-np.array(rhs)
    require(np.all(violations>0),'ADOPTED_OUTWARD_ROWS_MUST_EXCLUDE_PREVIOUS_INCUMBENT')
    residual=combined@u4-d['rhs']
    errors=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
    require(float(errors.max())<=1e-8,'VERIFIED_U4_MIP_START_REPLAY')
    files={name:sha(OUT/name) for name in ('JOINT_A.npz','JOINT_DATA.npz','JOINT_AXES.npz','JOINT_START.npz','CUTS_EXACT.json')}
    write(OUT/'NATIVE0.json',dict(PASS=True,Native_optimize_calls=0,full_MILP_calls=0,stage=STAGE,
          previous=str(PREVIOUS),previous_certificate_sha=sha(PREVIOUS/'INDEPENDENT_CERTIFICATE.json'),
          dimensions=dict(rows=combined.shape[0],columns=combined.shape[1],binary=9322,nnz=int(combined.nnz)),
          matrix_sha=matrix_sha(combined),domain_sha=_domain_sha(d),file_sha256=files,
          previous_rows=oldrows,added_rows=len(rhs),U4_max_violation=float(errors.max()),
          previous_incumbent_cut_violations=violations.tolist(),model_extraction_seconds=time.perf_counter()-begin,
          memory_before=pre,memory_after=memory(),independent_verification_required=True))
    print(json.dumps(dict(PASS=True,rows=combined.shape[0],columns=combined.shape[1],binary=9322,nnz=int(combined.nnz))))

def safe_attr(model, name):
    try:
        value = getattr(model, name)
        if isinstance(value, (float, np.floating)) and not math.isfinite(value):
            return None
        return value
    except Exception:
        return None


def native():
    require(not (OUT / 'PILOT_STARTED.json').exists(), 'OPTIMIZE_LATCH_EXISTS_NO_RERUN')
    for name in ('NATIVE0.json','INDEPENDENT_NATIVE0.json','PRE_LAUNCH_RESOURCE_HOLD.json'):
        require(read(OUT/name)['PASS'], 'PRE_NATIVE_GATE:'+name)
    require(read(OUT/'INDEPENDENT_NATIVE0.json')['FULL_projection_subset_native_Joint'], 'INCLUSION_GATE')
    if STAGE == 2:
        gate = read(OUT/'STAGE2_GATE.json')
        require(gate['PASS'] and all(gate['checks'].values()), 'STAGE2_NOT_AUTHORIZED')
        require(gate['previous_certificate_sha256'] == sha(PREVIOUS/'INDEPENDENT_CERTIFICATE.json')
                and gate['independent_native0_sha256'] == sha(OUT/'INDEPENDENT_NATIVE0.json'),
                'STAGE2_ADMISSION_PROOF_DRIFT')
    frozen = read(OUT / 'NATIVE0.json')['file_sha256']
    for p, expected in frozen.items():
        require(sha(OUT/p) == expected, 'SEALED_FILE_DRIFT:' + p)
    pre = memory()
    require(admission(pre), 'PRE_BUILD_MEMORY_GATE')
    A = sparse.load_npz(OUT / 'JOINT_A.npz').tocsr()
    d = load_data(OUT / 'JOINT_DATA.npz')
    import gurobipy as gp
    from gurobipy import GRB
    env = gp.Env(empty=True)
    env.setParam('LogFile', str(OUT / 'NATIVE.log'))
    env.start()
    model = gp.Model('Source18r_CriticalGrid_CG_LB_ONLY', env=env)
    for k,v in dict(Threads=1, TimeLimit=TIME_LIMIT, MIPGap=.03, MIPFocus=3,
                    FeasibilityTol=1e-8, IntFeasTol=1e-8, OptimalityTol=1e-8, Seed=42).items():
        model.setParam(k,v)
    create = time.perf_counter()
    x = model.addMVar(len(d['names']), lb=d['lb'], ub=d['ub'], vtype=d['vtypes'].tolist(), obj=d['c'])
    model.addMConstr(A, x, d['senses'], d['rhs'])
    model.ModelSense = GRB.MINIMIZE
    model.ObjCon = float(d['constant'])
    model.update()
    construction_seconds = time.perf_counter()-create
    before_readback = memory()
    native_A = model.getA().tocsr()
    checks = dict(matrix=matrix_sha(native_A) == matrix_sha(A), rhs=np.array_equal(model.getAttr('RHS'),d['rhs']),
                  senses=np.array_equal(model.getAttr('Sense'),d['senses']), lower=np.array_equal(x.LB,d['lb']),
                  upper=np.array_equal(x.UB,d['ub']), types=np.array_equal(x.VType,d['vtypes']),
                  objective=np.array_equal(x.Obj,d['c']), ObjCon=model.ObjCon == 0, ModelSense=model.ModelSense == GRB.MINIMIZE,
                  Rows=model.NumConstrs == A.shape[0], Columns=model.NumVars == A.shape[1], Binary=model.NumBinVars == int(sum(d['vtypes']=='B')),
                  NNZ=model.NumNZs == A.nnz)
    del native_A
    gc.collect()
    readback = dict(PASS=all(checks.values()), checks=checks, matrix_sha=matrix_sha(A),
                    parameters={k:getattr(model.Params,k) for k in ['Threads','TimeLimit','MIPGap','MIPFocus','FeasibilityTol','IntFeasTol','OptimalityTol','Seed']},
                    gurobi_version=list(gp.gurobi.version()), model_build_seconds=construction_seconds,
                    memory_before=pre, memory_after_build=before_readback, memory_after_readback=memory())
    write(OUT / 'NATIVE_READBACK.json', readback)
    require(readback['PASS'], 'NATIVE_READBACK_FAILED')
    with np.load(OUT / 'JOINT_START.npz') as z:
        x.Start = z['x']
    model.update()
    post = memory()
    observed_build_growth = max(0, post['Private_Commit_bytes']-pre['Private_Commit_bytes'])
    expected_growth = max(2*GIB, 4*observed_build_growth)
    safe_memory = admission(post, extra=expected_growth)
    write(OUT / 'MEMORY_ADMISSION.json', dict(PASS=safe_memory, sample=post, RAM_reserve_bytes=4*GIB,
          commit_reserve_bytes=6*GIB, estimated_additional_bytes=expected_growth,
          observed_model_build_private_growth_bytes=observed_build_growth,
          estimation_basis='Model already resident. Reserve max(2 GiB,4x observed model build private growth) for single-thread presolve/root/tree; continuous monitoring enforces system reserves.',
          matrix_arrays_only_in_process='JOINT only; FULL and C3A arrays disposed in prior build process'))
    if not safe_memory:
        write(OUT / 'RESULT.json', dict(classification='CG_RESOURCE_OR_NUMERIC_STOP', Native_optimize_calls=0,
                                      reason='POST_BUILD_RAM_OR_COMMIT_OR_GROWTH_GATE', memory=post))
        model.dispose(); env.dispose()
        return
    from tools.critical_grid_cg.resources import inventory
    peers, peer_errors = inventory()
    heavy_peers = [p for p in peers if p['gurobi_loaded_modules'] or
                   any(token in ' '.join(p['command']).lower() for token in
                       ['--mode native', 'gurobi_cl', 'native_worker', 'v42_svr11.worker', 'run_native', 'run_joint'])]
    write(OUT / 'PRE_OPTIMIZE_PEERS.json', dict(PASS=not heavy_peers and not peer_errors,
          observed_time=time.time(), own_PID_excluded=os.getpid(), peers=peers,
          errors=peer_errors, heavy_peers=heavy_peers))
    require(not heavy_peers and not peer_errors, 'CONCURRENT_HEAVY_GUROBI_GATE')
    # Both the global ledger and stage latch are sealed before optimize.
    ledger_path = OUT.parent/'NATIVE_LEDGER.json'
    ledger = read(ledger_path) if ledger_path.exists() else dict(calls=[], maximum_calls=2, maximum_requested_seconds=360)
    require(len(ledger['calls']) == STAGE-1 and len(ledger['calls']) < 2, 'GLOBAL_NATIVE_CALL_LIMIT')
    require(sum(r['TimeLimit'] for r in ledger['calls'])+TIME_LIMIT <= 360, 'GLOBAL_NATIVE_BUDGET')
    ledger['calls'].append(dict(stage=STAGE, TimeLimit=TIME_LIMIT, out=str(OUT), pid=os.getpid(), time=time.time()))
    write(ledger_path, ledger)
    # Exclusive create before first optimize: no error/time limit can authorize a retry.
    with (OUT / 'PILOT_STARTED.json').open('x', encoding='utf-8') as f:
        json.dump(dict(Native_optimize_max=1, time=time.time(), pid=os.getpid(),
                       git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                       independent_native0_sha256=sha(OUT/'INDEPENDENT_NATIVE0.json'),
                       parameters=readback['parameters'], files=frozen), f, indent=2)
    samples, events = [post], []
    last_sample, last_event, memory_stop = 0., 0., []
    callback_errors = []
    def callback(m, where):
        nonlocal last_sample,last_event
        now = time.monotonic()
        try:
            if now-last_sample >= .5:
                sample = memory()
                samples.append(sample)
                last_sample = now
                if not admission(sample, extra=0):
                    memory_stop.append(sample)
                    m.terminate()
            if where == GRB.Callback.MESSAGE:
                message = m.cbGet(GRB.Callback.MSG_STRING)
                if 'Numerical trouble' in message or 'Out of memory' in message or 'Numeric error' in message:
                    callback_errors.append(message.strip()); m.terminate()
            elif now-last_event >= 1 or where == GRB.Callback.PRESOLVE:
                e = dict(time=now, where=int(where))
                if where == GRB.Callback.MIP:
                    e.update(nodes=m.cbGet(GRB.Callback.MIP_NODCNT), bound=m.cbGet(GRB.Callback.MIP_OBJBND),
                             incumbent=m.cbGet(GRB.Callback.MIP_OBJBST), iterations=m.cbGet(GRB.Callback.MIP_ITRCNT))
                elif where == GRB.Callback.MIPNODE:
                    e.update(nodes=m.cbGet(GRB.Callback.MIPNODE_NODCNT), status=m.cbGet(GRB.Callback.MIPNODE_STATUS))
                elif where == GRB.Callback.PRESOLVE:
                    e.update(columns_deleted=m.cbGet(GRB.Callback.PRE_COLDEL), rows_deleted=m.cbGet(GRB.Callback.PRE_ROWDEL))
                else:
                    return
                # Gurobi sentinel incumbents are finite but not accepted as a bound.
                events.append(e); last_event=now
        except Exception as exc:
            callback_errors.append(repr(exc)); m.terminate()
    wall = time.perf_counter()
    optimize_error = None
    try:
        model.optimize(callback)
    except Exception as exc:
        optimize_error = repr(exc)
    samples.append(memory())
    native_wall = time.perf_counter()-wall
    status = safe_attr(model,'Status')
    bound = safe_attr(model,'ObjBound')
    valid = (status in [GRB.OPTIMAL,GRB.TIME_LIMIT,GRB.INTERRUPTED] and bound is not None
             and math.isfinite(bound) and abs(bound) < GRB.INFINITY and not callback_errors and not optimize_error)
    # Numeric status cannot be relabelled certified. Memory termination retains
    # solver bound only if its ordinary global-bound contract remains available.
    parent_certificate = read(PREVIOUS/'INDEPENDENT_CERTIFICATE.json')
    previous_lb = parent_certificate['Global_LB']
    published = max(previous_lb, bound) if valid else None
    classification = ('CG_GLOBAL_GAP_3PCT_PASS' if published >= UB*.97 else
                      'CG_LB_MATERIAL_IMPROVEMENT' if published-OLD_LB >= .005 else 'CG_LB_NONMATERIAL') if valid else 'CG_RESOURCE_OR_NUMERIC_STOP'
    if memory_stop:
        classification = 'CG_RESOURCE_OR_NUMERIC_STOP'
    result = dict(classification=classification, numerical_bound_candidate_valid=valid,
         Native_optimize_calls=1, full_MILP_calls=0, separate_LP_calls=0, campaign_calls=0,
         Status=status, ObjBound=bound, ObjBoundC=safe_attr(model,'ObjBoundC'), ObjVal=safe_attr(model,'ObjVal'),
         MIPGap=safe_attr(model,'MIPGap'), NodeCount=safe_attr(model,'NodeCount'), IterCount=safe_attr(model,'IterCount'),
         BarIterCount=safe_attr(model,'BarIterCount'), SolCount=safe_attr(model,'SolCount'),
         Runtime=safe_attr(model,'Runtime'), optimize_wall_seconds=native_wall,
         model_build_seconds=construction_seconds, MaxMemUsed_GB=safe_attr(model,'MaxMemUsed'), MemUsed_GB=safe_attr(model,'MemUsed'),
         UB=UB, LB_old=OLD_LB, LB_previous=previous_lb, Global_LB=published, LB_published=published, stage=STAGE, TimeLimit=TIME_LIMIT, goal_LB=UB*.97,
         global_gap=(UB-published)/UB if valid else None, delta_Joint16=published-OLD_LB if valid else None, goal_3percent=bool(valid and published>=UB*.97),
         memory_stop=bool(memory_stop), callback_errors=callback_errors, optimize_error=optimize_error,
         peak_process_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),
         peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),
         peak_sampled_private_commit_bytes=max(s['Private_Commit_bytes'] for s in samples),
         minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),
         minimum_commit_available=min(s['system']['Commit_available'] for s in samples),
         exact_numeric_BB_certificate=False, incumbent_is_full_UB=False)
    if safe_attr(model,'SolCount'):
        solution=x.X
        np.savez_compressed(OUT/'JOINT_INCUMBENT.npz',x=solution)
        residual=A@solution-d['rhs']
        violation=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
        result['incumbent_joint_replay']=dict(max_violation=float(max(violation)), rho=float(solution[-1]),
                                             full_feasibility_tested=False, promoted_to_UB=False)
    write(OUT/'MEMORY_TRACE.json',dict(samples=samples, unsafe_samples=memory_stop))
    write(OUT/'NATIVE_EVENTS.json',dict(events=events))
    model.dispose(); env.dispose()
    log=(OUT/'NATIVE.log').read_text(encoding='utf-8',errors='replace')
    result['root_relaxation_completed']='Root relaxation:' in log and ('objective' in log.split('Root relaxation:')[-1].split('\n')[0])
    result['presolve_summary']=[line for line in log.splitlines() if line.startswith(('Presolve removed','Presolved:','Root relaxation:','Explored ','User MIP start'))]
    write(OUT/'RESULT.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['build','native'],required=True)
    ap.add_argument('--out',type=Path,default=OUT);ap.add_argument('--previous',type=Path,default=PREVIOUS)
    ap.add_argument('--stage',type=int,choices=[1,2],default=1)
    args=ap.parse_args();OUT=args.out.resolve();PREVIOUS=args.previous.resolve();STAGE=args.stage
    try:build() if args.mode=='build' else native()
    except Exception as exc:
        write(OUT/('BUILD_FAILURE.json' if args.mode=='build' else 'NATIVE_FAILURE.json'),dict(error=repr(exc),traceback=traceback.format_exc(),memory=memory(),Native_optimize_started=(OUT/'PILOT_STARTED.json').exists()))
        raise
