"""One bounded sequential C0/C1/C2 native comparison; no formulation callbacks."""
from .common import *
from .build import load
from .formulation import Compact,residual
from .verify import inverse_map
from v42_degen.identity import inputs,signature
from v42_degen.common import POLICY
from v42_redundancy.model import build as native_build
from v42_rowgen.native import transport_audit
from v42_one_tree_bc.audit import Validator
from v42_strengthening.analysis import graph_inputs
from v42_m1_accel_vnext.native_state import inspect_live
from v42_dw_continuation.resources import WindowsCounters
from benchmark_m1_redundancy import parameters
import gurobipy as gp
import psutil,numpy as np
import threading,time,math,traceback,re,gc,subprocess
from datetime import datetime,timezone

NATIVE_LIMIT=270;ARM_WALL=300
def finite(v):return float(v) if math.isfinite(v) and abs(v)<1e90 else None
def safe(v):
    v=finite(v);return float(np.nextafter(v-1e-8,-np.inf)) if v is not None else None
def gap(ub,lb):return max(0.,ub-lb)/max(abs(ub),1e-10)
def gate(label):
    processes,blocked=inspect_live();write('RESOURCE_GATE_'+label+'.json',dict(PASS=not blocked,processes=processes,blocked=blocked,fleet_outputs_read=False))
    if blocked:raise RuntimeError('BENCHMARK_DEFERRED_RESOURCE_CONFLICT')

class Resource:
    def __init__(self):self.rows=[];self.phase='common';self.origin=time.perf_counter();self.stop=threading.Event()
    def worker(self):
        counters=WindowsCounters();p=psutil.Process()
        try:
            while not self.stop.is_set():
                m=p.memory_info();v=psutil.virtual_memory();self.rows.append(dict(UTC=datetime.now(timezone.utc).isoformat(),wall=time.perf_counter()-self.origin,arm=self.phase,RSS=m.rss,process_commit=getattr(m,'pagefile',None),free_RAM=v.available,**counters.sample()));self.stop.wait(.5)
        finally:counters.close()
    def start(self):self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
    def close(self):
        self.stop.set();self.thread.join(timeout=3)
        if self.rows:table('SUPERCOMPACT_RESOURCE_LEDGER.csv',self.rows,list(self.rows[0]))

class ScientificValidator:
    def __init__(self,full,fd,original,d,compact,T,offset,cols):
        self.validator=Validator(full,fd);self.original=original;self.d=d;self.compact=compact;self.T=T;self.offset=offset;self.cols=cols
        self.arc=np.asarray(sorted(compact.arc_columns.values()),int)
    def __call__(self,label,y):
        raw=self.T@y+self.offset if label=='C2' else y.copy();x=np.asarray(raw)[:self.original.shape[1]].copy()
        # Flows are algebraic auxiliaries: reconstruct their uniquely implied integer route.
        # Physical P/Q/SOC/mode decisions are copied without clipping or repair.
        flowerr=float(np.max(abs(x[self.arc]-np.rint(x[self.arc])),initial=0))
        if flowerr>1e-8:return dict(PASS=False,objective=float(self.d['objective']@x+float(self.d['constant'])),flow_reconstruction_max_difference=flowerr,reason='Route flow outside exact mapping tolerance')
        x[self.arc]=np.rint(x[self.arc]);check=self.validator(x);mapped=self.compact.forward(x);mapped=mapped[self.cols] if label=='C2' else mapped
        A,d=load(label);rr=residual(A,d,mapped)
        check.update(flow_reconstruction_max_difference=flowerr,physical_repairs=0,compact_reconstructed_residual=rr,objective=float(self.d['objective']@x+float(self.d['constant'])))
        check['PASS']=bool(check['PASS'] and rr['max_row_violation']<=1e-6 and rr['max_bound_violation']<=1e-8 and rr['max_integrality_violation']==0)
        return check

def arm(label,validator,lb,resources):
    begin=time.perf_counter();deadline=begin+ARM_WALL;resources.phase=label;gate(label+'_BEFORE_BUILD');A,d=load(label)
    with np.load(OUT/(label+'_VALID_START.npz')) as z:seed=z['point'].copy()
    t=time.perf_counter();m=native_build(A,d);buildwall=time.perf_counter()-t
    settings=dict(POLICY,TimeLimit=NATIVE_LIMIT,PreCrush=1,LazyConstraints=0)
    for k,v in settings.items():m.setParam(k,v)
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(label+'_NATIVE.log'));params=parameters(m)
    transport=transport_audit(m,A,d,np.arange(A.shape[0]));assert np.array_equal(np.asarray(m.getAttr('VarName')),d['names']) and np.array_equal(np.asarray(m.getAttr('ConstrName')),d['row_names'])
    variables=m.getVars();m.setAttr('Start',variables,seed.tolist());ub=float(d['objective']@seed+float(d['constant']));initial_lb=lb;best=seed.copy();initial_ub=ub
    messages=[];progress=[];candidates=[];errors=[];first=None;firstvalid=None;last=-1.;rootcb=None
    def callback(model,where):
        nonlocal ub,lb,best,first,firstvalid,last,rootcb
        try:
            elapsed=time.perf_counter()-begin
            if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING));return
            if where==gp.GRB.Callback.MIPSOL:
                if first is None:first=elapsed
                y=np.asarray(model.cbGetSolution(variables));r=validator(label,y);when=time.perf_counter()-begin
                candidates.append(dict(arm_wall=elapsed,validation_completed=when,native_objective=float(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),audit=r))
                if r['PASS']:
                    if firstvalid is None:firstvalid=when
                    if r['objective']<ub:ub=r['objective'];best=y.copy()
            if where==gp.GRB.Callback.MIPNODE and rootcb is None and model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL:
                work=None
                try:work=float(model.cbGet(gp.GRB.Callback.WORK))
                except (AttributeError,gp.GurobiError):pass
                rootcb=dict(Runtime=float(model.cbGet(gp.GRB.Callback.RUNTIME)),Work=work,node_count=float(model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)),bound=float(model.cbGet(gp.GRB.Callback.MIPNODE_OBJBND)))
            if where==gp.GRB.Callback.MIP and elapsed-last>=1:
                raw=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND));b=safe(raw) if raw is not None else None
                if b is not None:
                    if b>ub+1e-8:raise RuntimeError('NATIVE_BOUND_EXCEEDS_VALID_UB')
                    lb=max(lb,b)
                progress.append(dict(arm=label,arm_wall=elapsed,raw_native_BestBd=raw,safely_adjusted_native_bound=b,inherited_certified_full_domain_LB=initial_lb,valid_global_LB=lb,valid_UB=ub,valid_gap=gap(ub,lb),nodes=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT))));last=elapsed
            if time.perf_counter()>=deadline-7:model.terminate()
        except BaseException:errors.append(traceback.format_exc());model.terminate()
    gate(label+'_BEFORE_OPTIMIZE');assert time.perf_counter()<deadline-NATIVE_LIMIT-7,'BUILD_EXCEEDS_IDENTICAL_NATIVE_BUDGET'
    timer=threading.Timer(deadline-time.perf_counter()-7,m.terminate);timer.daemon=True;timer.start();nativebegin=time.perf_counter()
    print('COMPACT_ARM_START',label,'rows',m.NumConstrs,'columns',m.NumVars,'B',m.NumBinVars,'nnz',m.NumNZs,flush=True)
    try:
        m.optimize(callback);optwall=time.perf_counter()-nativebegin;raw=finite(m.ObjBound);b=safe(m.ObjBound)
        if b is not None:
            if b>ub+1e-8:errors.append('FINAL_BOUND_EXCEEDS_VALID_UB')
            else:lb=max(lb,b)
        terminal=None
        if m.SolCount:
            y=np.asarray(m.getAttr('X'));terminal=validator(label,y);np.savez_compressed(OUT/(label+'_RAW_POINT.npz'),point=y)
            if terminal['PASS'] and terminal['objective']<ub:ub=terminal['objective'];best=y.copy()
        final=validator(label,best);assert final['PASS'];np.savez_compressed(OUT/(label+'_VALID_POINT.npz'),point=best)
        log=''.join(messages);root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log);presolved=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
        samples=[r for r in resources.rows if r['arm']==label];wall=time.perf_counter()-begin
        if wall>ARM_WALL:errors.append('HARD_ARM_WALL_EXCEEDED')
        if m.Status not in [2,9,11]:errors.append('UNEXPECTED_NATIVE_STATUS:'+str(m.Status))
        result=dict(PASS=not errors,arm=label,executed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,continuous=int(np.sum(d['types']=='C')),nnz=m.NumNZs,scientific_signature=signature(A,d),settings=settings,all_native_parameters=params,transport=transport,
            build_wall=buildwall,input_and_build_wall=nativebegin-begin,optimize_wall=optwall,total_arm_wall=wall,hard_arm_wall_cap=ARM_WALL,native_TimeLimit=NATIVE_LIMIT,
            native_runtime=m.Runtime,Gurobi_Work=m.Work,LP_iterations=m.IterCount,barrier_iterations=m.BarIterCount,node_count=m.NodeCount,nodes_after_root=max(0.,m.NodeCount-1) if root else 0.,root_completed=bool(root),root_time=float(root[3]) if root else None,root_objective_rounded=float(root[1]) if root else None,root_iterations=int(root[2]) if root else None,first_root_optimal_callback=rootcb,
            presolved=dict(rows=int(presolved[1]),columns=int(presolved[2]),nnz=int(presolved[3])) if presolved else None,raw_native_BestBd=raw,safely_adjusted_native_bound=b,inherited_certified_full_domain_LB=initial_lb,valid_global_LB=lb,valid_UB=ub,valid_global_gap=gap(ub,lb),initial_valid_UB=initial_ub,initial_valid_LB=initial_lb,first_native_incumbent=first,first_independently_valid_native_incumbent=firstvalid,start_independently_valid_at_arm_wall=0.,native_status=m.Status,native_SolCount=m.SolCount,raw_native_UB=finite(m.ObjVal) if m.SolCount else None,
            peak_RSS=max((r['RSS'] for r in samples),default=None),peak_process_commit=max((r['process_commit'] for r in samples),default=None),minimum_free_RAM=min((r['free_RAM'] for r in samples),default=None),peak_system_commit_percent=max((r['commit_percent'] for r in samples if r['commit_percent'] is not None),default=None),sampled_memory_peaks=True,terminal_native_audit=terminal,valid_final_full_original_audit=final,candidates=candidates,progress=progress,errors=errors,callbacks='Read-only bounds/incumbent validation and bounded terminate; no cuts/lazy/rowgen')
        filenames={'C0':'C0_COMPACT_FULL_RESULT.json','C1':'C1_COMPACT_REDUCED_RESULT.json','C2':'C2_SUPERCOMPACT_RESULT.json'};write(filenames[label],result)
        print('COMPACT_ARM_END',label,'root',bool(root),'Work',m.Work,'nodes',m.NodeCount,'LB',lb,'UB',ub,'gap',gap(ub,lb),'wall',wall,'errors',errors,flush=True)
        return result
    finally:timer.cancel();m.dispose();gc.collect()

def run():
    for n in ['PR160_CERTIFICATE_TRANSPORT_AUDIT.json','SUPERCOMPACT_FIXTURE_RESULTS.json','SUPERCOMPACT_ROUTE_ENUMERATION.json','SUPERCOMPACT_FRACTIONAL_RELAXATION_AUDIT.json','SUPERCOMPACT_ADVERSARIAL_RESULTS.json','SUPERCOMPACT_INDEPENDENT_VERIFICATION.json','COMPACT_START_VALIDATION.json']:assert read(n)['PASS'],n
    assert read('SUPERCOMPACT_FINAL_MATRIX_AUDIT.json')['size_gate'];gate('PREFLIGHT')
    assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip(),'SOURCE_MUST_BE_FROZEN'
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with (OUT/'SUPERCOMPACT_BENCHMARK_ONCE.json').open('x',encoding='utf-8') as stream:json.dump(dict(source_commit=source,native_limit=NATIVE_LIMIT,hard_wall=ARM_WALL,sequential_arms=['C0','C1','C2']),stream)
    full,fd,A,d,identity,_=inputs();sites,initial,arcs,battery,_=graph_inputs();compact=Compact(A,d,arcs,initial,96)
    _,_,_,_,T,offset,rows,cols,_=inverse_map();validator=ScientificValidator(full,fd,A,d,compact,T,offset,cols)
    parent=ROOT/'docs/v42_m1_one_tree_bc_20261006/M1_ONE_TREE_BC_INPUT_FREEZE.json';lb=json.loads(parent.read_text())['inherited_full_domain_LB']
    write('SUPERCOMPACT_EXECUTION_FREEZE.json',dict(source_commit=source,base=BASE,identity=identity,original_signature=signature(A,d),inherited_certified_full_domain_LB=lb,LB_source=str(parent.relative_to(ROOT)),LB_SHA256=sha(parent),source_files={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted((ROOT/'v42_supercompact').glob('*.py'))},C2_signature=signature(*load('C2')),start_validation=read('COMPACT_START_VALIDATION.json'),solver_policy=dict(POLICY,TimeLimit=NATIVE_LIMIT,PreCrush=1,LazyConstraints=0),sequential=True,no_tournament_execution=True))
    resources=Resource();resources.start();results=[]
    try:
        for label in ['C0','C1','C2']:
            r=arm(label,validator,lb,resources);results.append(r);assert r['PASS'],label+' execution failed'
    finally:resources.close()
    pp=[{k:v for k,v in r['all_native_parameters'].items() if k!='LogFile'} for r in results];assert pp[0]==pp[1]==pp[2]
    a,b,c=results
    root_gate=c['root_completed'] and not a['root_completed'] and not b['root_completed']
    matched_time=all(r['root_completed'] and r['root_time'] for r in results) and c['root_time']<=.8*min(a['root_time'],b['root_time'])
    matched_work=all(r['first_root_optimal_callback'] and r['first_root_optimal_callback']['Work'] for r in results) and c['first_root_optimal_callback']['Work']<=.8*min(a['first_root_optimal_callback']['Work'],b['first_root_optimal_callback']['Work'])
    bound_gate=c['valid_global_LB']>max(a['valid_global_LB'],b['valid_global_LB'])+.001 and c['valid_global_gap']<min(a['valid_global_gap'],b['valid_global_gap'])-.001
    node_gate=c['root_completed'] and c['nodes_after_root']>max(a['nodes_after_root'],b['nodes_after_root'])+1
    selected=bool(root_gate or matched_time or matched_work or bound_gate or node_gate)
    state='SUPER_COMPACT_EXACT_SELECTED' if selected else 'SUPER_COMPACT_EXACT_BUT_NO_SPEEDUP'
    comparison=dict(PASS=True,final_state=state,SUPER_COMPACT_EXACT_SELECTED=selected,root_completion_gate=bool(root_gate),matched_root_time_gate=bool(matched_time),matched_root_Work_gate=bool(matched_work),valid_LB_gap_gate=bool(bound_gate),genuine_node_progress_gate=bool(node_gate),memory_or_size_only_selection=False,unfinished_root_Work_used_for_selection=False,all_native_parameters_identical_except_LogFile=True,compared_parameter_count=len(pp[0]),arms=[{k:r[k] for k in ['arm','root_completed','root_time','first_root_optimal_callback','node_count','nodes_after_root','native_runtime','Gurobi_Work','valid_UB','raw_native_BestBd','safely_adjusted_native_bound','inherited_certified_full_domain_LB','valid_global_LB','valid_global_gap','peak_RSS','peak_process_commit','minimum_free_RAM','total_arm_wall']} for r in results],STOP=True,no_extra_optimize=True)
    write('SUPERCOMPACT_MILP_COMPARISON.json',comparison);write('SUPERCOMPACT_SELECTION.json',comparison)
    trajectories=[p for r in results for p in r['progress']]
    if trajectories:table('SUPERCOMPACT_GAP_TRAJECTORY.csv',trajectories,list(trajectories[0]))
    print('COMPARISON_DONE',state,flush=True)
if __name__=='__main__':
    try:run()
    except BaseException:write('SUPERCOMPACT_BENCHMARK_ERROR.json',dict(traceback=traceback.format_exc()));raise
