"""Preregistered sequential bounded root then MILP comparison, once only."""
from .common import *
from .start import validator as make_validator
from v42_degen.common import POLICY
from v42_redundancy.model import build
from v42_rowgen.native import transport_audit
from v42_m1_accel_vnext.native_state import inspect_live
from v42_dw_continuation.resources import WindowsCounters
from benchmark_m1_redundancy import parameters
import gurobipy as gp,psutil,threading,time,subprocess,re,gc,traceback
from datetime import datetime,timezone
def finite(v):return float(v) if math.isfinite(v) and abs(v)<1e90 else None
def safe(v):return float(np.nextafter(float(v)-1e-8,-np.inf)) if finite(v) is not None else None
def gap(ub,lb):return max(0,ub-lb)/max(abs(ub),1e-10)
def gate(label):
    live,blocked=inspect_live();vm=psutil.virtual_memory();result=dict(PASS=not blocked and vm.available>=8*1024**3,processes=live,blocked=blocked,free_RAM=vm.available,minimum_free_RAM=8*1024**3,no_process_killed=True);write('RESOURCE_GATE_'+label+'.json',result)
    if not result['PASS']:raise RuntimeError('BENCHMARK_DEFERRED_RESOURCE_CONFLICT')
class Resource:
    def __init__(self):self.rows=[];self.phase='common';self.stop=threading.Event();self.begin=time.perf_counter()
    def work(self):
        counters=WindowsCounters();proc=psutil.Process()
        try:
            while not self.stop.is_set():
                m=proc.memory_info();v=psutil.virtual_memory();self.rows.append(dict(UTC=datetime.now(timezone.utc).isoformat(),wall=time.perf_counter()-self.begin,arm=self.phase,RSS=m.rss,process_commit=getattr(m,'pagefile',None),free_RAM=v.available,**counters.sample()));self.stop.wait(.5)
        finally:counters.close()
    def start(self):self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
    def close(self):self.stop.set();self.thread.join(timeout=3);table('ULTRACOMPACT_RESOURCE_LEDGER.csv',self.rows,list(self.rows[0]))
def arm(label,stage,validator,lb,resource):
    cap=240 if stage=='ROOT' else 300;limit=230 if stage=='ROOT' else 285;guard=cap-5 if stage=='ROOT' else cap-7;begin=time.perf_counter();resource.phase=stage+'_'+label;gate(stage+'_'+label+'_BEFORE_BUILD');A,d=load(label)
    with np.load(OUT/(label+'_VALID_START.npz')) as z:seed=z['point'].copy()
    m=build(A,d);settings=dict(POLICY,TimeLimit=limit,PreCrush=1,LazyConstraints=0)
    if stage=='ROOT':settings['NodeLimit']=1
    for k,v in settings.items():m.setParam(k,v)
    m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(stage+'_'+label+'_NATIVE.log'));params=parameters(m);transport=transport_audit(m,A,d,np.arange(A.shape[0]));vv=m.getVars();m.setAttr('Start',vv,seed.tolist());ub=float(d['objective']@seed+float(d['constant']));initialub=ub;initiallb=lb;best=seed.copy();messages=[];events=[];progress=[];errors=[];rootcb=None;firstnew=None;last=-1
    def validate(y):
        r=validator('C2',y);rr=residual(A,d,y);r['candidate_residual']=rr;r['PASS']=bool(r['PASS'] and rr['max_row_violation']<=1e-8 and rr['max_bound_violation']<=1e-8 and rr['max_integrality_violation']<=1e-8);return r
    def cb(model,where):
        nonlocal ub,lb,best,rootcb,firstnew,last
        try:
            elapsed=time.perf_counter()-begin
            if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING));return
            if where==gp.GRB.Callback.MIPSOL:
                y=np.asarray(model.cbGetSolution(vv));r=validate(y);when=time.perf_counter()-begin;events.append(dict(arm_wall=elapsed,validation_completed=when,native_objective=float(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),audit=r))
                if r['PASS'] and r['objective']<ub-1e-8:
                    ub=r['objective'];best=y.copy()
                    if firstnew is None:firstnew=when
            if where==gp.GRB.Callback.MIPNODE and rootcb is None and model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL:
                rootcb=dict(Runtime=float(model.cbGet(gp.GRB.Callback.RUNTIME)),Work=float(model.cbGet(gp.GRB.Callback.WORK)),node_count=float(model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)),bound=float(model.cbGet(gp.GRB.Callback.MIPNODE_OBJBND)))
            if where==gp.GRB.Callback.MIP and elapsed-last>=1:
                raw=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND));valid=safe(raw) if raw is not None else None
                if valid is not None:
                    assert valid<=ub+1e-8;lb=max(lb,valid)
                progress.append(dict(arm_wall=elapsed,raw_native_bound=raw,valid_LB=lb,valid_UB=ub,valid_gap=gap(ub,lb),nodes=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT))));last=elapsed
            if elapsed>=guard:model.terminate()
        except BaseException:errors.append(traceback.format_exc());model.terminate()
    gate(stage+'_'+label+'_BEFORE_OPTIMIZE');elapsed=time.perf_counter()-begin;assert elapsed<guard,'BUILD_EXHAUSTED_ARM_BUDGET';timer=threading.Timer(guard-elapsed,m.terminate);timer.daemon=True;timer.start();nativebegin=time.perf_counter()
    print('ULTRA_ARM_START',stage,label,'rows',m.NumConstrs,'cols',m.NumVars,flush=True)
    try:
        m.optimize(cb);raw=finite(m.ObjBound);valid=safe(m.ObjBound)
        if valid is not None:assert valid<=ub+1e-8;lb=max(lb,valid)
        terminal=None
        if m.SolCount:
            y=np.asarray(m.getAttr('X'));terminal=validate(y)
            if terminal['PASS'] and terminal['objective']<ub-1e-8:ub=terminal['objective'];best=y.copy()
        final=validate(best);assert final['PASS'];np.savez_compressed(OUT/(stage+'_'+label+'_VALID_POINT.npz'),point=best)
        log=''.join(messages);root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds \(([\d.]+) work units\)',log);pre=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log);samples=[r for r in resource.rows if r['arm']==stage+'_'+label];wall=time.perf_counter()-begin
        assert wall<=cap,(stage,label,wall);assert m.Status in [2,8,9,11]
        result=dict(PASS=not errors,label=label,stage=stage,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),settings=settings,all_native_parameters=params,transport=transport,rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs,input_build_wall=nativebegin-begin,native_TimeLimit=limit,hard_arm_wall_cap=cap,total_arm_wall=wall,native_Runtime=m.Runtime,total_Work=m.Work,node_count=m.NodeCount,nodes_after_root=max(0,m.NodeCount-1) if root else 0,root_completed=bool(root),root_time=float(root[3]) if root else None,root_Work=float(root[4]) if root else None,root_metric_precision='Native printed root log (0.01 seconds / 0.01 Work); distinct from overall Work',root_objective_rounded=float(root[1]) if root else None,root_callback=rootcb,time_after_root=max(0,m.Runtime-float(root[3])) if root else None,raw_native_BestBd=raw,safely_adjusted_native_bound=valid,inherited_certified_full_domain_LB=initiallb,valid_LB=lb,valid_UB=ub,valid_gap=gap(ub,lb),initial_UB=initialub,first_new_valid_incumbent=firstnew,new_valid_incumbents=sum(e['audit']['PASS'] and e['audit']['objective']<initialub-1e-8 for e in events),events=events,progress=progress,terminal_audit=terminal,final_valid_full_original_audit=final,native_status=m.Status,native_SolCount=m.SolCount,presolved=dict(rows=int(pre[1]),columns=int(pre[2]),nnz=int(pre[3])) if pre else None,peak_RSS=max((r['RSS'] for r in samples),default=None),peak_process_commit=max((r['process_commit'] for r in samples),default=None),minimum_free_RAM=min((r['free_RAM'] for r in samples),default=None),peak_system_commit_percent=max((r['commit_percent'] for r in samples if r['commit_percent'] is not None),default=None),errors=errors,callbacks='Read-only point/bound validation and time termination; no added constraints/cuts/lazy/pricing')
        write((label+'_MILP_RESULT.json') if stage=='MILP' and label=='C2' else 'C3_MILP_RESULT.json' if stage=='MILP' else stage+'_'+label+'_RESULT.json',result);print('ULTRA_ARM_END',stage,label,'root',bool(root),'root_seconds',result['root_time'],'root_Work',result['root_Work'],'nodes',m.NodeCount,'gap',result['valid_gap'],'wall',wall,flush=True);return result
    finally:timer.cancel();m.dispose();gc.collect()
def same_params(a,b):return {k:v for k,v in a['all_native_parameters'].items() if k!='LogFile'}=={k:v for k,v in b['all_native_parameters'].items() if k!='LogFile'}
def run():
    required=['ULTRACOMPACT_FIXTURE_RESULTS.json','ULTRACOMPACT_ADVERSARIAL_RESULTS.json','ULTRACOMPACT_INDEPENDENT_VERIFICATION.json','ULTRACOMPACT_START_VALIDATION.json','PR161_REPLAY_PR160_CERTIFICATE_TRANSPORT_AUDIT.json','PR161_REPLAY_SUPERCOMPACT_INDEPENDENT_VERIFICATION.json']
    for n in required:assert read(n)['PASS'],n
    size=read('MATERIALITY_GATE.json');assert size['PASS'];assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip(),'FREEZE_SOURCE_REQUIRED';gate('PREFLIGHT')
    with (OUT/'BENCHMARK_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),root_arms=['C2','C3A'],MILP_arms=['C2','C3A'],sequential=True),f)
    validator,identity=make_validator();lb=json.loads((ROOT/'docs/v42_m1_one_tree_bc_20261006/M1_ONE_TREE_BC_INPUT_FREEZE.json').read_text())['inherited_full_domain_LB'];resource=Resource();resource.start()
    try:
        a=arm('C2','ROOT',validator,lb,resource);b=arm('C3A','ROOT',validator,lb,resource);assert a['PASS'] and b['PASS'] and same_params(a,b)
        write('ULTRACOMPACT_ROOT_COMPARISON.json',dict(PASS=True,C2=a,C3=b,other_C3_candidates_identical=True,all_native_parameters_except_log_identical=True))
        c=arm('C2','MILP',validator,lb,resource);d=arm('C3A','MILP',validator,lb,resource);assert c['PASS'] and d['PASS'] and same_params(c,d)
        write('ULTRACOMPACT_MILP_COMPARISON.json',dict(PASS=True,C2=c,C3=d,all_native_parameters_except_log_identical=True))
        timegate=a['root_completed'] and b['root_completed'] and b['root_time']<=.85*a['root_time'];workgate=a['root_completed'] and b['root_completed'] and b['root_Work']<=.85*a['root_Work'];nodegate=d['nodes_after_root']>c['nodes_after_root']+1;boundgate=d['valid_LB']>c['valid_LB']+1e-6;gapgate=d['valid_gap']<c['valid_gap']-1e-6;incgate=d['first_new_valid_incumbent'] is not None and (c['first_new_valid_incumbent'] is None or d['first_new_valid_incumbent']<=.85*c['first_new_valid_incumbent']);selected=bool(timegate or workgate or nodegate or boundgate or gapgate or incgate)
        write('ULTRACOMPACT_SELECTION.json',dict(PASS=True,state='ULTRACOMPACT_EXACT_SELECTED' if selected else 'ULTRACOMPACT_EXACT_BUT_NO_SPEEDUP',selected=selected,selected_formulation='C3A' if selected else 'FROZEN_PR161_C2',exactness=True,root_time_gate=timegate,root_Work_gate=workgate,node_gate=nodegate,valid_LB_gate=boundgate,valid_gap_gate=gapgate,new_incumbent_gate=incgate,comparison_tolerance=1e-6,algorithm_tournament_executed=False,STOP=True))
    finally:resource.close()
if __name__=='__main__':run()
