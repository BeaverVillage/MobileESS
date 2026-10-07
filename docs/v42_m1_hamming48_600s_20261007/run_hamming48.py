"""Exactly one Hamming48/600s native solve; frozen PR170 algorithm and C3A readers."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import argparse, csv, hashlib, importlib.util, json, math, subprocess, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
OLD=ROOT/'docs/v42_m1_gap_rootcause_20261007'
PREVIOUS=ROOT/'docs/v42_m1_hamming48_20261007'
BASE='bf455bbea26d644d8952d1d2da90f8f645cf0df1'
UB=.6324498168172089
LB=.5687116003498334
SETTINGS=dict(Threads=1,TimeLimit=600,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0)
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('h48_readonly_h169',OLD/'common.py')
hc=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hc;spec.loader.exec_module(hc)
sha=hc.sha;clean=hc.clean;read=hc.read;stamp=hc.stamp
def write(name,obj):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(p)
def table(name,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(clean(rows))
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def finite(v):return float(v) if math.isfinite(float(v)) and abs(float(v))<1e90 else None
def snapshot(name):
    import psutil
    processes=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            if p.info['name'] and ('python' in p.info['name'].lower() or 'gurobi' in p.info['name'].lower()):processes.append(p.info)
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    write(name,dict(UTC=stamp(),processes=processes,memory=dict(psutil.virtual_memory()._asdict()),other_workers_untouched=True,controlled_performance_benchmark=False))
def protected():
    return {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for folder in [OLD,PREVIOUS,hc.HISTORY,hc.PARENT] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.suffix!='.pyc'}
def prepare():
    assert git('merge-base',BASE,'HEAD')==BASE,'WRONG_BASE'
    assert all(p.startswith('docs/v42_m1_hamming48_600s_20261007/') for p in git('diff','--name-only',BASE,'HEAD').splitlines())
    assert not (OUT/'OPTIMIZE_ONCE.json').exists(),'SOLVE_ALREADY_STARTED'
    assert (OUT/'PREREGISTRATION.md').exists()
    A,d,_=hc.load()
    for folder in (OLD,PREVIOUS):
        for name,digest in read(folder/'SHA256_MANIFEST.json')['files'].items():assert sha(folder/name)==digest,'HISTORICAL_MANIFEST_MISMATCH'
    center_path=PREVIOUS/'BEST_VALID_POINT.npz'
    assert sha(center_path)=='f9192e2d6a8eb04b4096f983bdc1abbf65c1abab5613e02cd759713299d5c6cc'
    with np.load(center_path) as z:center=z['x'].copy()
    assert len(center)==A.shape[1] and float(d['objective']@center+float(d['constant']))==UB
    before=protected()
    old_result=read(OLD/'UB_LOCAL_NEIGHBORHOOD_RESULT.json')
    definition=read(OLD/'UB_LOCAL_NEIGHBORHOOD_DEFINITION.json')
    source=(OLD/'solve_neighborhood.py').read_text(encoding='utf-8')
    assert 'if 64<=t<=84:free.append(int(j))' in source
    assert 'weights=np.where(reference[free]>.5,-1.,1.)' in source
    previous_settings=read(PREVIOUS/'SOLVER_PARAMETERS.json')['settings']
    assert {k:v for k,v in SETTINGS.items() if k!='TimeLimit'}=={k:v for k,v in previous_settings.items() if k!='TimeLimit'}
    assert previous_settings['TimeLimit']==300 and SETTINGS['TimeLimit']==600
    b=np.flatnonzero(d['types']=='B');free=[]
    for j in b:
        name=str(d['names'][j]);t=int(name.rsplit(',',1)[-1][:-1])
        if 64<=t<=84:free.append(int(j))
    free=np.asarray(free,int);fixed=np.setdiff1d(b,free)
    assert d['names'][free].tolist()==definition['free_names']
    assert all(str(n).startswith(('node_activity[','charge_mode[')) for n in d['names'][free])
    assert (len(free),len(fixed))==(2100,7222)
    assert sum(str(n).startswith('node_activity[') for n in d['names'][free])==2016
    assert sum(str(n).startswith('charge_mode[') for n in d['names'][free])==84
    with np.load(PREVIOUS/'NEIGHBORHOOD_RESTRICTION.npz') as z:
        assert np.array_equal(free,z['free']) and np.array_equal(fixed,z['fixed'])
    assert read(PREVIOUS/'HAMMING48_MODEL_AUTHORITY.json')['free_names']==d['names'][free].tolist()
    raw=hc.replay(A,d,center,True)
    physical=hc.physical_reader().check(center,A,d,is_start=True)
    valid=bool(raw['PASS'] and physical['PASS'])
    write('BASE_IDENTITY.json',dict(PASS=True,exact_base_HEAD=BASE,initial_HEAD=git('rev-parse','HEAD'),scientific_PR162_HEAD='1d922c91eb27056a5ccc79c92ef18146707099ab',center_artifact=str(center_path.relative_to(ROOT)),center_SHA256=sha(center_path),center_UB=UB,global_LB=LB,protected_before=before,scientific_model_unchanged=True))
    write('CENTER_VALIDATION.json',dict(PASS=valid,UTC=stamp(),objective=UB,point_SHA256=sha(center_path),original_C3A=raw,full_physical=physical,original_A1_frozen_interface_verified=True,repairs=0,optimize_calls_so_far=0))
    if not valid:
        write('RESULT.json',dict(classification='CENTER_INCUMBENT_INVALID',optimize_calls=0));raise AssertionError('CENTER_INCUMBENT_INVALID')
    e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
    e['lower'][fixed]=center[fixed];e['upper'][fixed]=center[fixed]
    weights=np.where(center[free]>.5,-1.,1.);rhs=48-int((center[free]>.5).sum())
    row=sparse.csr_matrix((weights,(np.zeros(len(free),int),free)),shape=(1,A.shape[1]))
    B=sparse.vstack([A,row],format='csr')
    e.update(rhs=np.r_[d['rhs'],rhs],sense=np.concatenate([d['sense'],['<']]),row_names=np.concatenate([d['row_names'],['PRIMAL_NEIGHBORHOOD_HAMMING48']]))
    local=hc.replay(B,e,center,True)
    assert local['PASS'] and np.array_equal(center[b],np.rint(center[b]))
    c=d['types']=='C'
    assert np.array_equal(e['lower'][c],d['lower'][c]) and np.array_equal(e['upper'][c],d['upper'][c])
    np.savez_compressed(OUT/'NEIGHBORHOOD_RESTRICTION.npz',free=free,fixed=fixed,center_binary=center[b],binary_columns=b,weights=weights,rhs=np.array(rhs),radius=np.array(48))
    write('HAMMING24_AUTHORITY.json',dict(PASS=True,source=str((OLD/'solve_neighborhood.py').relative_to(ROOT)),source_SHA256=sha(OLD/'solve_neighborhood.py'),saved_definition_SHA256=sha(OLD/'UB_LOCAL_NEIGHBORHOOD_DEFINITION.json'),saved_result_SHA256=sha(OLD/'UB_LOCAL_NEIGHBORHOOD_RESULT.json'),radius=24,center_UB=old_result['baseline_UB'],best_valid_UB=old_result['new_valid_UB'],Runtime=old_result['Runtime'],Work=old_result['Work'],free_count=len(free),fixed_count=len(fixed),free_names_exactly_match=True,original_source_selection='All original B whose last name index is 64..84; actual saved names are only node_activity and charge_mode',settings=old_result['settings'],continuous_original_bounds_free=True))
    write('HAMMING48_MODEL_AUTHORITY.json',dict(PASS=True,UTC=stamp(),radius=48,slots=[64,84],units=['MESS01','MESS02','MESS03','MESS04'],families=['node_activity','charge_mode'],free_count=len(free),node_activity_count=2016,charge_mode_count=84,fixed_count=len(fixed),free_names=d['names'][free].tolist(),free_indices_identical_to_PR170=True,Hamming_definition='sum x_j for center=0 + sum(1-x_j) for center=1 <=48',Hamming_ones_count=int((center[free]>.5).sum()),signed_row_rhs=rhs,restriction_SHA256=sha(OUT/'NEIGHBORHOOD_RESTRICTION.npz'),center_SHA256=sha(center_path),outside_fixed_to_new_center=True,original_rows=A.shape[0],restricted_rows=B.shape[0],cols=A.shape[1],B=int((d['types']=='B').sum()),C=int(c.sum()),original_nnz=A.nnz,restricted_nnz=B.nnz,original_objective_unchanged=True,continuous_bounds_bit_identical=True,original_physics_unchanged=True,only_experiment_policy_difference='TimeLimit300->600; center/start/outside-fix updated to PR170 incumbent as explicitly requested',PR170_driver_SHA256=sha(PREVIOUS/'run_hamming48.py'),no_LB_cuts=True))
    write('MIP_START_VALIDATION.json',dict(PASS=True,UTC=stamp(),original=raw,restricted=local,Hamming_distance=0,point_SHA256=sha(center_path),no_modification=True,start_supplied=False,start_accepted=None,independently_replayed_before_optimize=True))
    assert before==protected(),'HISTORICAL_EVIDENCE_CHANGED'
    print('PREFLIGHT_PASS',len(free),len(fixed),raw['max_constraint_violation'],flush=True)
    return A,d,center,B,e,free,fixed
def parameters(m):
    values={};defaults={}
    for name in dir(m.Params):
        if name.startswith('_'):continue
        try:
            info=m.getParamInfo(name)
            if info is not None:values[name]=info[2];defaults[name]=info[5]
        except (AttributeError,RuntimeError):pass
    encode=lambda v:('Infinity' if v>0 else '-Infinity') if isinstance(v,float) and not math.isfinite(v) else v
    return [{k:encode(v) for k,v in a.items()} for a in [values,defaults]]
def solve(prepared):
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_integrated.matrix import arrays
    A,d,center,B,e,free,fixed=prepared
    snapshot('RESOURCE_BEFORE.json');model=build(B,e)
    for k,v in SETTINGS.items():model.setParam(k,v)
    model.Params.LogFile=str(OUT/'NATIVE_SOLVER.log');model.Params.OutputFlag=1;model.Params.LogToConsole=0
    variables=model.getVars();model.setAttr('Start',variables,center.tolist());model.update()
    assert np.array_equal(np.asarray(model.getAttr('Start')),center)
    native_A,native_d=arrays(model)
    assert (native_A!=B).nnz==0
    for k in e:assert np.array_equal(native_d[k],e[k]),k
    effective,defaults=parameters(model)
    assert all(effective[k]==v for k,v in SETTINGS.items())
    previous_effective=read(PREVIOUS/'SOLVER_PARAMETERS.json')['all_effective_before_optimize']
    parameter_differences={k:dict(PR170=previous_effective.get(k),current=effective.get(k)) for k in set(previous_effective)|set(effective) if previous_effective.get(k)!=effective.get(k)}
    assert set(parameter_differences)=={'TimeLimit','LogFile'},parameter_differences
    write('SOLVER_PARAMETERS.json',dict(PASS=True,settings=SETTINGS,all_effective_before_optimize=effective,defaults=defaults,nondefault={k:v for k,v in effective.items() if v!=defaults[k]},solver_version=list(gp.gurobi.version()),PR170_algorithm_parameters_identical_except_TimeLimit=True,PR170_effective_differences=parameter_differences,sweep=False,parameters_changed_during_solve=False))
    authority=read(OUT/'HAMMING48_MODEL_AUTHORITY.json');authority.update(native_transport_bit_identical=True,native_Fingerprint=int(model.Fingerprint));write('HAMMING48_MODEL_AUTHORITY.json',authority)
    start_validation=read(OUT/'MIP_START_VALIDATION.json');start_validation.update(start_supplied=True,native_Start_bit_identical=True);write('MIP_START_VALIDATION.json',start_validation)
    traces=[];errors=[];begin=time.perf_counter();saved=OUT/'incumbents';saved.mkdir(exist_ok=True)
    fields=['event','UTC','discovery_wall_seconds','native_Runtime','Work','rho','Hamming_distance','node_count','best_bound_neighborhood_only','MIP_gap_neighborhood_only','previous_best','is_new_incumbent','point','SHA256']
    stream=(OUT/'INCUMBENT_TRACE.csv').open('w',encoding='utf-8',newline='');writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader();stream.flush()
    def callback(m,where):
        if where!=gp.GRB.Callback.MIPSOL:return
        try:
            runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME));work=float(m.cbGet(gp.GRB.Callback.WORK));obj=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ));bound=finite(m.cbGet(gp.GRB.Callback.MIPSOL_OBJBND));prev=finite(m.cbGet(gp.GRB.Callback.MIPSOL_OBJBST))
            point=np.asarray(m.cbGetSolution(variables));index=len(traces)+1;path=saved/f'INCUMBENT_{index:04d}.npz';np.savez_compressed(path,x=point)
            event=dict(event=index,UTC=stamp(),discovery_wall_seconds=time.perf_counter()-begin,native_Runtime=runtime,Work=work,rho=obj,Hamming_distance=int(np.count_nonzero((point[free]>.5)!=(center[free]>.5))),node_count=float(m.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)),best_bound_neighborhood_only=bound,MIP_gap_neighborhood_only=abs(obj-bound)/abs(obj) if bound is not None and obj else None,previous_best=prev,is_new_incumbent=prev is None or obj<prev,point=str(path.relative_to(OUT)).replace('\\','/'),SHA256=sha(path))
            traces.append(event);writer.writerow(clean(event));stream.flush()
        except BaseException:errors.append(traceback.format_exc())
    calls=0;native_optimize=gp.Model.optimize
    def guard(m,*args,**kwargs):
        nonlocal calls
        assert calls==0 and m is model,'SECOND_OPTIMIZE_FORBIDDEN'
        assert not (OUT/'OPTIMIZE_ONCE.json').exists()
        token=dict(PID=os.getpid(),UTC=stamp(),source_commit=git('rev-parse','HEAD'),exact_base=BASE,optimize_calls=1,settings=SETTINGS,radius=48,phase='NATIVE_ENTER')
        with (OUT/'OPTIMIZE_ONCE.json').open('x',encoding='utf-8') as f:json.dump(token,f,ensure_ascii=False,indent=2)
        calls+=1;return native_optimize(m,*args,**kwargs)
    def forbidden(*args,**kwargs):raise AssertionError('SEPARATE_PRESOLVE_FORBIDDEN')
    gp.Model.optimize=guard;gp.Model.presolve=forbidden
    exception=None;begin=time.perf_counter();print('HAMMING48_600_SINGLE_NATIVE_START',flush=True)
    try:model.optimize(callback)
    except BaseException:exception=traceback.format_exc()
    finally:stream.close()
    report=dict(UTC=stamp(),optimize_calls=calls,Status=int(model.Status),Runtime=float(model.Runtime),Work=float(model.Work),NodeCount=float(model.NodeCount),SolCount=int(model.SolCount),IterCount=float(model.IterCount),BarIterCount=int(model.BarIterCount),ObjVal=float(model.ObjVal) if model.SolCount else None,neighborhood_ObjBound=finite(model.ObjBound),neighborhood_MIPGap=float(model.MIPGap) if model.SolCount else None,optimize_wall_seconds=time.perf_counter()-begin,MIPSOL_events=len(traces),new_incumbent_events=sum(r['is_new_incumbent'] for r in traces),callback_errors=errors,solver_exception=exception,global_LB=LB,neighborhood_bound_not_global=True,global_optimality_claimed=False)
    if model.SolCount:np.savez_compressed(OUT/'BEST_SOLVER_POINT.npz',x=np.asarray(model.getAttr('X')))
    write('NATIVE_RECEIPT.json',report)
    after,_=parameters(model);assert after==effective
    text=(OUT/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
    start_validation.update(start_accepted='Loaded user MIP start' in text,start_acceptance_evidence=[line for line in text.splitlines() if 'MIP start' in line]);write('MIP_START_VALIDATION.json',start_validation)
    model.dispose();snapshot('RESOURCE_AFTER.json')
    physical=hc.physical_reader();candidates=[]
    if (OUT/'BEST_SOLVER_POINT.npz').exists():candidates.append(OUT/'BEST_SOLVER_POINT.npz')
    candidates.extend(OUT/r['point'] for r in sorted(traces,key=lambda r:r['rho']) if r['rho']<UB)
    audits=[];best=UB;best_point=center;accepted=None;seen=set();solver_best_checked=False
    for path in candidates:
        with np.load(path) as z:point=z['x'].copy()
        point_key=hashlib.sha256(point.tobytes()).hexdigest()
        if point_key in seen:continue
        seen.add(point_key)
        raw=hc.replay(A,d,point,True);phy=physical.check(point,A,d)
        restriction=hc.replay(B,e,point,True)
        passing=bool(raw['PASS'] and phy['PASS'] and restriction['PASS'])
        audit=dict(point=str(path.relative_to(OUT)).replace('\\','/'),point_SHA256=sha(path),objective=float(d['objective']@point+float(d['constant'])),PASS=passing,original=raw,physical=phy,restricted=restriction)
        audits.append(audit)
        if not solver_best_checked:
            write('BEST_CANDIDATE_FULL_REPLAY.json',dict(PASS=passing,original_C3A=raw,restricted=restriction,point=audit['point'],point_SHA256=audit['point_SHA256'],no_repairs=True))
            write('BEST_CANDIDATE_PHYSICAL_REPLAY.json',phy)
            write('BEST_CANDIDATE_GRID_REPLAY.json',dict(**phy['original_physical_audit']['exhaustive_grid'],point=audit['point'],frozen_A1_interface_verified=True,original_rows_only=True))
            solver_best_checked=True
        if passing and audit['objective']<best:best=audit['objective'];best_point=point;accepted=audit
        # Objective-sorted candidates: after first strict-PASS minimum, later ones cannot improve.
        if accepted is not None:break
    if not solver_best_checked:
        raw=hc.replay(A,d,center,True);phy=physical.check(center,A,d,is_start=True)
        write('BEST_CANDIDATE_FULL_REPLAY.json',dict(PASS=True,solver_candidate_available=False,retained_center=True,original_C3A=raw))
        write('BEST_CANDIDATE_PHYSICAL_REPLAY.json',phy);write('BEST_CANDIDATE_GRID_REPLAY.json',phy['original_physical_audit']['exhaustive_grid'])
    np.savez_compressed(OUT/'BEST_VALID_POINT.npz',x=best_point)
    write('CANDIDATE_VALIDATION_HISTORY.json',dict(audits=audits,all_MIPSOL_points_saved=True,validation_order='best native candidate first, then remaining improving MIPSOL candidates in objective order until first valid minimum',no_extra_solve=True))
    delta=UB-best
    classification='HAMMING48_600_PRIMAL_IMPROVEMENT_CONFIRMED' if delta>=.001 else 'HAMMING48_600_MINOR_IMPROVEMENT' if delta>0 else 'HAMMING48_600_NO_VALID_IMPROVEMENT'
    if exception or errors or calls!=1:classification='HAMMING48_600_EXECUTION_INVALID'
    report.update(classification=classification,UB_old=UB,UB_new=best,absolute_improvement=delta,accepted_candidate=accepted['point'] if accepted else None,best_solver_candidate_full_replay_PASS=read(OUT/'BEST_CANDIDATE_FULL_REPLAY.json')['PASS'],H_best=int(np.count_nonzero((best_point[free]>.5)!=(center[free]>.5))),HAMMING_BOUNDARY_ACTIVE=bool(np.count_nonzero((best_point[free]>.5)!=(center[free]>.5))==48),best_valid_point_SHA256=sha(OUT/'BEST_VALID_POINT.npz'),historical_evidence_unchanged=protected()==read(OUT/'BASE_IDENTITY.json')['protected_before'],parameters_unchanged=True)
    assert report['historical_evidence_unchanged'];write('RESULT.json',report)
    write('BEST_FULL_REPLAY.json',dict(best_solver_candidate=read(OUT/'BEST_CANDIDATE_FULL_REPLAY.json'),best_solver_physical=read(OUT/'BEST_CANDIDATE_PHYSICAL_REPLAY.json'),best_valid_point_SHA256=sha(OUT/'BEST_VALID_POINT.npz'),valid_UB=best,PASS=bool(hc.replay(A,d,best_point,True)['PASS'] and physical.check(best_point,A,d)['PASS']),original_C3A_dimension=A.shape[1],global_LB=LB))
    print('HAMMING48_600_COMPLETE',classification,best,delta,report['H_best'],flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--solve',action='store_true');args=parser.parse_args();assert args.prepare!=args.solve
    if args.solve:assert not git('status','--porcelain=v1'),'COMMIT_PREREGISTRATION_AND_PREFLIGHT_BEFORE_EXECUTION'
    prepared=prepare()
    if args.solve:solve(prepared)
