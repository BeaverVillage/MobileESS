"""Frozen PR162 C3A: static replay, then exactly one native P1 optimization."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import argparse, ast, csv, hashlib, json, math, re, subprocess, sys, threading, time, traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent
PARENT=ROOT/'docs/v42_m1_ultracompact_exact_20261006'
BASE='1d922c91eb27056a5ccc79c92ef18146707099ab'
EXPECTED={
    'C3A_A.npz':'45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8',
    'C3A_DATA.npz':'20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467',
    'C3A_VALID_START.npz':'be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5'}
SOURCES={}
import numpy as np
from scipy import sparse
import psutil

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not math.isfinite(x):return None
    return x
def write(name,value):
    temp=OUT/(name+'.tmp')
    temp.write_bytes((json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))
    temp.replace(OUT/name)
def sha(path):
    path=Path(path)
    with path.open('rb') as stream: value=hashlib.file_digest(stream,'sha256').hexdigest()
    return value
def record(path):
    path=Path(path);value=dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)
    SOURCES[str(path)]=value;return value
def read(path):record(path);return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def finite(v):
    return float(v) if v is not None and math.isfinite(float(v)) and abs(float(v))<1e90 else None
def gap(ub,lb):return None if ub is None or lb is None or ub==0 else abs(ub-lb)/abs(ub)
def residual(A,d,x):
    r=A@x-d['rhs'];v=np.where(d['sense']=='=',abs(r),np.where(d['sense']=='<',r,-r))
    integers=d['types']!='C'
    return dict(finite=bool(np.isfinite(x).all()),max_constraint_residual=float(v.max(initial=0)),
        max_bound_residual=float(max((d['lower']-x).max(initial=0),(x-d['upper']).max(initial=0))),
        max_integrality_residual=float(abs(x[integers]-np.rint(x[integers])).max(initial=0)),
        objective=float(d['objective']@x+float(d['constant'])))

class PhysicalReplay:
    """Saved algebraic inverse + existing frozen original physical validator only.

    No C0/C1/C2 model or matrix is constructed. The saved certificate maps
    selected C3 coordinates back to the original physical coordinates.
    """
    def __init__(self):
        from v42_degen.common import SOURCE
        from v42_one_tree_bc.audit import Validator
        self.source=SOURCE
        identity=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/M1_MODEL_IDENTITY.json')
        freeze=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')
        assert freeze['PASS'] and sha(SOURCE/'DATA.pkl')==freeze['source_data_sha256']
        assert record(SOURCE/'FULL_A.npz')['sha256']==identity['matrix_sha256']
        assert record(SOURCE/'FULL_DATA.npz')['sha256']==identity['data_sha256']
        assert record(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')['sha256']==identity['A1_freeze_sha256']
        record(SOURCE/'DATA.pkl')
        self.full=sparse.load_npz(SOURCE/'FULL_A.npz')
        with np.load(SOURCE/'FULL_DATA.npz') as z:self.d={k:z[k] for k in z.files}
        axes=ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz';record(axes)
        with np.load(axes) as z:self.cols=z['columns'].copy()
        steps=read(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_ELIMINATION_CERTIFICATES.json')
        n=len(self.cols)+len(steps)
        self.target=np.full(n,-1,dtype=np.int64);self.offset=np.zeros(n)
        self.target[self.cols]=np.arange(len(self.cols));seen=set(map(int,self.cols))
        for s in reversed(steps):
            j=s['column'];assert j not in seen and len(s['terms'])<=1
            if s['terms']:
                k,w=next(iter(s['terms'].items()));k=int(k);assert k in seen and w==1.
                self.target[j]=self.target[k];self.offset[j]=s['constant']+self.offset[k]
            else:self.offset[j]=s['constant']
            seen.add(j)
        assert len(seen)==n and self.full.shape[1]<=n
        self.validator=Validator(self.full,self.d)
        self.arc=np.asarray([j for j,n in enumerate(self.d['names']) if str(n).startswith('arc[')],int)
        self.physical=np.asarray([j for j,n in enumerate(self.d['names']) if str(n).startswith(('arc[','SOC[','Pch[','Pdis[','Q[','charge_mode['))],int)
        for candidate in [SOURCE/'DATA.pkl']:
            assert record(candidate)['sha256']==freeze['source_data_sha256']
    def inverse(self,y):
        original=self.offset.copy();nz=self.target>=0;original[nz]+=y[self.target[nz]]
        return original[:self.full.shape[1]].copy()
    def check(self,y,A,d,is_start=False):
        r=residual(A,d,y);x=self.inverse(y);before=x.copy()
        flow_error=float(abs(x[self.arc]-np.rint(x[self.arc])).max(initial=0))
        # The frozen PR162 validator maps algebraically implied continuous route
        # auxiliaries to the original integer route within its existing tolerance.
        # For the required immutable start even this difference must be zero.
        if is_start:assert flow_error==0.,'START_ROUTE_MODIFICATION_FORBIDDEN'
        if flow_error<=1e-8:x[self.arc]=np.rint(x[self.arc])
        check=self.validator(x)
        physical_difference=float(abs(before[self.physical]-x[self.physical]).max(initial=0))
        passed=bool(check['PASS'] and r['finite'] and r['max_constraint_residual']<=1e-8 and r['max_bound_residual']<=1e-8 and r['max_integrality_residual']<=1e-8 and flow_error<=1e-8)
        if is_start:passed=passed and physical_difference==0
        return dict(PASS=passed,C3_residual=r,original_physical_audit=check,
            saved_inverse_certificate_used=True,C2_model_rebuilt=False,
            route_auxiliary_inverse_max_difference=flow_error,
            start_repaired=False,physical_start_max_difference=physical_difference if is_start else None,
            new_incumbent_inverse_mapping='Frozen PR162 route-auxiliary mapping; raw C3 point retained unchanged',
            objective=r['objective'])

def static_prepare():
    assert git('merge-base',BASE,'HEAD')==BASE,'WRONG_EXACT_BASE'
    changed=git('diff','--name-only',BASE,'HEAD').splitlines()
    assert all(p.startswith('docs/v42_m1_c3_native_1h_20261007/') for p in changed),changed
    authority=read(PARENT/'ULTRACOMPACT_CURRENT_AUTHORITY_M1.json')
    assert authority['PASS'] and authority['state']=='ULTRACOMPACT_EXACT_SELECTED' and authority['selected']=='C3A'
    assert (authority['N'],authority['H'],authority['MIPGap'],authority['FeasibilityTol'])==(4,96,.005,1e-8)
    for name,expected in EXPECTED.items():
        actual=record(PARENT/name);assert actual['sha256']==expected,(name,actual)
        blob=subprocess.check_output(['git','show',BASE+':'+str((PARENT/name).relative_to(ROOT)).replace('\\','/')],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest()==expected
    assert [authority[k] for k in ['selected_matrix_SHA256','selected_data_SHA256','selected_start_SHA256']]==list(EXPECTED.values())
    parent_before={str(p.relative_to(ROOT)):sha(p) for p in PARENT.iterdir() if p.is_file()}
    A=sparse.load_npz(PARENT/'C3A_A.npz')
    with np.load(PARENT/'C3A_DATA.npz') as z:d={k:z[k] for k in z.files}
    with np.load(PARENT/'C3A_VALID_START.npz') as z:start=z['point'].copy()
    counts=dict(rows=A.shape[0],columns=A.shape[1],binaries=int((d['types']=='B').sum()),continuous=int((d['types']=='C').sum()),nnz=int(A.nnz))
    assert counts==dict(rows=582808,columns=306040,binaries=9322,continuous=296718,nnz=5351612)
    assert set(d['types'])=={'B','C'} and A.shape==(len(d['rhs']),len(d['names'])) and len(start)==A.shape[1]
    nonzero=np.flatnonzero(d['objective']);assert len(nonzero)==1 and d['names'][nonzero[0]]=='rho_max' and d['objective'][nonzero[0]]==1 and float(d['constant'])==0
    from v42_degen.common import POLICY
    reference=read(PARENT/'C3_MILP_RESULT.json')
    settings=dict(POLICY,TimeLimit=3600,PreCrush=1,LazyConstraints=0)
    assert {k:v for k,v in settings.items() if k!='TimeLimit'}=={k:v for k,v in reference['settings'].items() if k!='TimeLimit'}
    replay=PhysicalReplay();start_check=replay.check(start,A,d,is_start=True)
    assert start_check['PASS'],'INVALID_UNMODIFIED_START'
    write('BASE_AUTHORITY.json',dict(PASS=True,exact_base_commit=BASE,PR=162,parent_head_verified=True,selected_authority=authority,
        reference_short_run={k:reference[k] for k in ['valid_UB','valid_LB','valid_gap','root_time','root_Work','node_count','native_Runtime','total_Work']},
        parent_namespace_before=parent_before,sources=list(SOURCES.values()),new_code_only_namespace='docs/v42_m1_c3_native_1h_20261007'))
    write('C3_IDENTITY_AUDIT.json',dict(PASS=True,selected='C3A',expected_hashes=EXPECTED,actual_hashes={n:sha(PARENT/n) for n in EXPECTED},
        selected_artifacts_match_exact_git_blobs=True,N=4,H=96,objective='minimize existing rho',objective_native_name='rho_max',objective_column=int(nonzero[0]),
        scientific_model_changed=False,compression_search=False,C2_rebuilt_or_benchmarked=False,old_LB_injected=False))
    write('C3_MODEL_CENSUS.json',dict(PASS=True,selected='C3A',**counts,
        row_families=dict(Counter(str(n).split('[')[0] for n in d['row_names'])),column_families=dict(Counter(str(n).split('[')[0] for n in d['names']))))
    write('C3_START_REPLAY.json',dict(**start_check,start_SHA256=sha(PARENT/'C3A_VALID_START.npz'),expected_start_SHA256=EXPECTED['C3A_VALID_START.npz'],
        independently_replayed_before_optimize=True,MIP_start_supplied_later_only_after_checks=True,repairs=0))
    print('STATIC_PREFLIGHT_PASS',counts,'start_max_residual',start_check['C3_residual']['max_constraint_residual'],flush=True)
    return A,d,start,replay,settings,reference

class Resource:
    def __init__(self):
        self.stop=threading.Event();self.origin=time.perf_counter();self.phase='BUILD';self.rows=[];self.errors=[]
    def run(self):
        proc=psutil.Process()
        with (OUT/'RESOURCE_TELEMETRY.csv').open('w',encoding='utf-8',newline='') as stream:
            fields=['UTC','wall_seconds','phase','PID','RSS','peak_RSS_so_far','available_RAM','process_CPU_seconds','CPU_percent','process_commit']
            w=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');w.writeheader();peak=0
            while True:
                try:
                    mem=proc.memory_info();vm=psutil.virtual_memory();cpu=proc.cpu_times();peak=max(peak,mem.rss)
                    row=dict(UTC=datetime.now(timezone.utc).isoformat(),wall_seconds=time.perf_counter()-self.origin,phase=self.phase,PID=os.getpid(),RSS=mem.rss,peak_RSS_so_far=peak,available_RAM=vm.available,process_CPU_seconds=cpu.user+cpu.system,CPU_percent=proc.cpu_percent(),process_commit=getattr(mem,'pagefile',None))
                    self.rows.append(row);w.writerow(row);stream.flush()
                except BaseException:self.errors.append(traceback.format_exc())
                if self.stop.wait(5):break
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def close(self):self.stop.set();self.thread.join(timeout=10)

def all_parameters(model):
    values={};defaults={};nondefault={}
    for name in dir(model.Params):
        if name.startswith('_'):continue
        try:
            info=model.getParamInfo(name)
            if info is None:continue
            values[name]=info[2];defaults[name]=info[5]
            if info[2]!=info[5]:nondefault[name]=info[2]
        except (AttributeError,RuntimeError):continue
    # Preserve infinity as a tagged string for parameter identity comparisons.
    def encode(v):return ('Infinity' if v>0 else '-Infinity') if isinstance(v,float) and not math.isfinite(v) else v
    return [{k:encode(v) for k,v in a.items()} for a in [values,defaults,nondefault]]

def optimize_once(A,d,start,replay,settings,reference):
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_rowgen.native import transport_audit
    source_commit=git('rev-parse','HEAD')
    assert not git('status','--porcelain=v1'),'COMMIT_PREREGISTRATION_AND_CODE_BEFORE_EXECUTION'
    assert not (OUT/'OPTIMIZE_ONCE.json').exists(),'NATIVE_RUN_ALREADY_ATTEMPTED_NO_RETRY'
    resource=Resource();resource.start();build_begin=time.perf_counter()
    model=build(A,d)
    for k,v in settings.items():model.setParam(k,v)
    model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(OUT/'M1_C3_NATIVE_1H.log')
    transport=transport_audit(model,A,d,np.arange(A.shape[0]))
    assert np.array_equal(np.asarray(model.getAttr('VarName')),d['names']) and np.array_equal(np.asarray(model.getAttr('ConstrName')),d['row_names'])
    variables=model.getVars();model.setAttr('Start',variables,start.tolist());model.update()
    assert np.array_equal(np.asarray(model.getAttr('Start')),start)
    effective,defaults,nondefault=all_parameters(model)
    metadata=['LogFile','TimeLimit','TSPort','LicenseID','Username']
    mismatches={k:dict(pr162=v,current=effective.get(k)) for k,v in reference['all_native_parameters'].items() if effective.get(k)!=v}
    assert not set(mismatches)-set(metadata),('NATIVE_PARAMETER_DRIFT',mismatches)
    assert effective['TimeLimit']==3600 and effective['NodeLimit']=='Infinity' and effective['MIPGap']==.005 and effective['FeasibilityTol']==1e-8
    write('SOLVER_PARAMETERS.json',dict(PASS=True,source_commit=source_commit,TimeLimit=3600,settings=settings,
        all_effective_before_optimize=effective,all_defaults=defaults,effective_nondefault=nondefault,reference_differences=mismatches,
        algorithm_parameter_changes=['TimeLimit'],logging_path_change_only=True,metadata_difference_keys=metadata,
        nondefault_parameter_count=len(nondefault),no_NodeLimit=True,no_hard_wall_timer=True,no_resource_guard=True,solver_version=list(gp.gurobi.version())))
    identity=read(OUT/'C3_IDENTITY_AUDIT.json');identity['native_transport']=transport;identity['native_census_matches_selected']=True
    identity['native_fingerprint']=int(model.Fingerprint);identity['start_supplied_bit_identical']=True;write('C3_IDENTITY_AUDIT.json',identity)
    build_wall=time.perf_counter()-build_begin
    history={'incumbents':[],'bounds':[],'root_messages':[],'first_root_optimal_callback':None,'first_processed_node':None,'first_branch_node':None,'errors':[]}
    state=dict(nodes=None,sol_count=None,incumbent=None,bound=None,gap=None)
    points=[];last_sample=-60.;native_begin=time.perf_counter();last_bound=None;last_incumbent=None
    progress_stream=(OUT/'M1_C3_NATIVE_1H_PROGRESS.csv').open('w',encoding='utf-8',newline='')
    fields=['UTC','wall_seconds','runtime','Work','where','event','nodes','sol_count','incumbent','bound','gap']
    progress=csv.DictWriter(progress_stream,fieldnames=fields,lineterminator='\n');progress.writeheader();progress_stream.flush()
    def emit(runtime,work,where,event):
        row=dict(UTC=datetime.now(timezone.utc).isoformat(),wall_seconds=time.perf_counter()-native_begin,runtime=runtime,Work=work,where=where,event=event,**state)
        progress.writerow(row);progress_stream.flush();return row
    def callback(m,where):
        nonlocal last_sample,last_bound,last_incumbent
        if where==gp.GRB.Callback.POLLING:return
        try:
            runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME));work=float(m.cbGet(gp.GRB.Callback.WORK));event=None
            if where==gp.GRB.Callback.MESSAGE:
                message=m.cbGet(gp.GRB.Callback.MSG_STRING)
                if re.search(r'Root relaxation:|Presolve time:|Presolved:',message):
                    history['root_messages'].append(dict(runtime=runtime,Work=work,message=message.strip()))
            if where==gp.GRB.Callback.MIP:
                state.update(nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),sol_count=int(m.cbGet(gp.GRB.Callback.MIP_SOLCNT)),incumbent=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBST)),bound=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBND)))
                state['gap']=gap(state['incumbent'],state['bound'])
                if state['bound'] is not None and state['bound']!=last_bound:
                    last_bound=state['bound'];row=emit(runtime,work,where,'BOUND_UPDATE');history['bounds'].append(row)
                if state['incumbent'] is not None and state['incumbent']!=last_incumbent:
                    last_incumbent=state['incumbent'];emit(runtime,work,where,'INCUMBENT_NATIVE_STATE')
                if state['nodes']>=1 and history['first_processed_node'] is None:history['first_processed_node']=emit(runtime,work,where,'FIRST_PROCESSED_NODE')
                if state['nodes']>1 and history['first_branch_node'] is None:history['first_branch_node']=emit(runtime,work,where,'FIRST_BRANCH_NODE')
            if where==gp.GRB.Callback.MIPSOL:
                obj=finite(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                event=dict(runtime=runtime,Work=work,wall_seconds=time.perf_counter()-native_begin,objective=obj,
                    nodes=float(m.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)),prior_native_solution_count=int(m.cbGet(gp.GRB.Callback.MIPSOL_SOLCNT)),
                    callback_bound=finite(m.cbGet(gp.GRB.Callback.MIPSOL_OBJBND)))
                history['incumbents'].append(event);points.append(np.asarray(m.cbGetSolution(variables)))
                emit(runtime,work,where,'MIPSOL_CANDIDATE')
            if where==gp.GRB.Callback.MIPNODE and m.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL and history['first_root_optimal_callback'] is None:
                history['first_root_optimal_callback']=dict(runtime=runtime,Work=work,nodes=float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)),bound=finite(m.cbGet(gp.GRB.Callback.MIPNODE_OBJBND)))
            if runtime-last_sample>=60:
                emit(runtime,work,where,'SAMPLE_60S');last_sample=runtime
        except BaseException:
            # An observation error is recorded and cannot terminate/change a solve.
            if len(history['errors'])<100:history['errors'].append(traceback.format_exc())
    original_optimize=gp.Model.optimize;calls=0
    def guarded_optimize(m,cb):
        nonlocal calls
        assert calls==0 and m is model,'SECOND_OPTIMIZE_FORBIDDEN'
        token=dict(source_commit=source_commit,exact_base=BASE,PID=os.getpid(),UTC=datetime.now(timezone.utc).isoformat(),
            optimize_calls=1,full_C3A_MILP=True,P1_only=True,TimeLimit=3600,model_SHA256=EXPECTED['C3A_A.npz'])
        with (OUT/'OPTIMIZE_ONCE.json').open('x',encoding='utf-8') as f:json.dump(token,f,ensure_ascii=False,indent=2)
        calls+=1;return original_optimize(m,cb)
    def forbidden_presolve(*args,**kwargs):raise AssertionError('SEPARATE_PRESOLVE_FORBIDDEN')
    gp.Model.optimize=guarded_optimize;gp.Model.presolve=forbidden_presolve
    resource.phase='OPTIMIZE';native_begin=time.perf_counter();actual_error=None
    print('ONE_C3A_NATIVE_OPTIMIZE_START',source_commit,'TimeLimit=3600',flush=True)
    try:
        model.optimize(callback)
    except BaseException:actual_error=traceback.format_exc()
    finally:
        opt_wall=time.perf_counter()-native_begin;resource.phase='POSTSOLVE';resource.close();progress_stream.close()
    # All candidate replay is after native optimization, no solver manipulation.
    audits=[]
    for event,point in zip(history['incumbents'],points):
        try:audit=replay.check(point,A,d)
        except BaseException:audit=dict(PASS=False,error=traceback.format_exc())
        audits.append(dict(event=event,audit=audit))
    sol_count=int(model.SolCount);terminal=None;ub=finite(model.ObjVal) if sol_count else None
    if sol_count:
        final_point=np.asarray(model.getAttr('X'));terminal=replay.check(final_point,A,d)
        np.savez_compressed(OUT/'M1_C3_NATIVE_1H_FINAL_POINT.npz',point=final_point)
    lb=finite(model.ObjBound);native_gap=finite(model.MIPGap) if sol_count else None
    independently_calculated_gap=gap(ub,lb)
    if native_gap is not None and independently_calculated_gap is not None:
        assert abs(native_gap-independently_calculated_gap)<=1e-10,'NATIVE_GAP_CROSSCHECK_FAILED'
    after,_,_=all_parameters(model)
    assert after==effective,'PARAMETERS_CHANGED_DURING_SOLVE'
    final_transport=transport_audit(model,A,d,np.arange(A.shape[0]));assert final_transport==transport
    parent=read(OUT/'BASE_AUTHORITY.json')
    assert {str(p.relative_to(ROOT)):sha(p) for p in PARENT.iterdir() if p.is_file()}==parent['parent_namespace_before'],'PARENT_EVIDENCE_CHANGED'
    for item in parent['sources']:assert record(item['path'])==item,'SCIENTIFIC_SOURCE_CHANGED'
    output=dict(PASS=actual_error is None and calls==1 and not history['errors'] and bool(terminal and terminal['PASS']),
        source_commit=source_commit,exact_base=BASE,selected='C3A',selected_hashes=EXPECTED,optimize_call_count=calls,
        TimeLimit=3600,native_Runtime=float(model.Runtime),native_Work=float(model.Work),optimize_wall_seconds=opt_wall,
        native_build_and_parameter_audit_wall_seconds=build_wall,native_Status=int(model.Status),native_SolCount=sol_count,
        native_NodeCount=float(model.NodeCount),native_IterCount=float(model.IterCount),native_BarIterCount=int(model.BarIterCount),
        native_UB=ub,native_global_LB=lb,native_ObjBoundC=finite(model.ObjBoundC),native_MIPGap=native_gap,
        independently_calculated_gap=independently_calculated_gap,gap_crosscheck_PASS=native_gap is not None and independently_calculated_gap is not None and abs(native_gap-independently_calculated_gap)<=1e-10,
        initial_verified_start_objective=float(d['objective']@start+float(d['constant'])),old_LB_injected=False,
        telemetry=history,incumbent_replays_after_native_solve=audits,terminal_physical_replay=terminal,
        actual_solver_exception=actual_error,observation_errors=history['errors'],resource_observation_errors=resource.errors,
        resources=dict(peak_RSS=max((r['RSS'] for r in resource.rows),default=None),minimum_available_RAM=min((r['available_RAM'] for r in resource.rows),default=None),
            observed_samples=len(resource.rows),paging_counters_recorded=False,no_resource_based_termination=True),
        model_attributes_unchanged=True,parameters_unchanged=True,parent_namespace_unchanged=True,scientific_sources_unchanged=True,
        M1_ACCEPTED=False,P2_executed=False,STOP=True)
    write('M1_C3_NATIVE_1H_RESULT.json',output)
    model.dispose()
    print('ONE_C3A_NATIVE_OPTIMIZE_FINISHED',output['native_Status'],output['native_Runtime'],ub,lb,independently_calculated_gap,flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--run',action='store_true');args=parser.parse_args()
    assert args.prepare!=args.run
    result=static_prepare()
    if args.run:optimize_once(*result)

if __name__=='__main__':main()
