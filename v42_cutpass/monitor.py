"""Buffer-only callback; strict nonroot/branch checkpoint regardless of UB."""
import re,time,threading
import numpy as np
import gurobipy as gp
from .common import finite
TIMES=('presolve_end','barrier_start','barrier_end','crossover_start','crossover_end','root_relaxation_complete','root_processing_complete','first_nonroot','first_branch','first_incumbent')
def root_pass(times):return any(times[k] is not None and times[k]<=600 for k in ('first_nonroot','first_branch'))
class Monitor:
    def __init__(self,variables,checkpoint=True):
        self.variables=variables;self.enabled=checkpoint;self.times=dict.fromkeys(TIMES);self.events=[];self.trace=[];self.solutions=[];self.start_messages=[];self.errors=[]
        self.calls=0;self.body_wall=0.;self.body_CPU=0.;self.last=-30.;self.latest=None;self.checkpoint=None;self.early_stop=False;self.done=threading.Event();self.watcher=None
    def event(self,name,t,literal):
        if self.times[name] is None:self.times[name]=t;self.events.append(dict(event=name,solver_seconds=t,literal=literal))
    def message(self,line,t):
        line=line.strip()
        if 'mip start' in line.lower():self.start_messages.append(dict(time=t,literal=line))
        for prefix,name in (('Presolve time:','presolve_end'),('Barrier solved model','barrier_end'),('Crossover time:','crossover_end'),('Root processing complete','root_processing_complete'),('Root node processing complete','root_processing_complete')):
            if line.startswith(prefix):self.event(name,t,line)
        if 'root barrier log' in line.lower():self.event('barrier_start',t,line)
        if 'crossover log' in line.lower():self.event('crossover_start',t,line)
        if line.startswith('Root relaxation:') and 'objective' in line:self.event('root_relaxation_complete',t,line)
    def state(self,clock,now):
        latest=dict(self.latest) if self.latest else None
        current=clock=='solver_runtime' and latest is not None and latest['time']==now
        return dict(clock=clock,observed_at_seconds=now,timestamps=dict(self.times),last_MIP_observation=latest,incumbent_observed=bool(self.solutions),Start_messages=list(self.start_messages),checkpoint_node_count=latest['nodes'] if current else None,checkpoint_UB=latest['UB'] if current else None,checkpoint_LB=latest['LB'] if current else None,checkpoint_cuts=latest['cuts'] if current else None,checkpoint_state_solver_seconds=now if current else None,exact_600_node_count=None,exact_600_UB=None,exact_600_LB=None,exact_600_cut_count=None,termination_requested=not root_pass(self.times),incumbent_does_not_override_root_path_stop=True)
    def start_watch(self,m):
        begin=time.perf_counter()
        if not self.enabled:return
        def watch():
            while not self.done.wait(.25):
                elapsed=time.perf_counter()-begin
                if elapsed>=600:
                    if self.checkpoint is None:self.checkpoint=self.state('monotonic_wall_since_optimize',elapsed)
                    if self.checkpoint['termination_requested']:self.early_stop=True;m.terminate()
                    return
        self.watcher=threading.Thread(target=watch,daemon=True);self.watcher.start()
    def finish(self):
        self.done.set()
        if self.watcher:self.watcher.join(timeout=1)
    def __call__(self,m,where):
        wall=time.perf_counter();cpu=time.thread_time();self.calls+=1
        try:
            if where==gp.GRB.Callback.POLLING:return
            t=float(m.cbGet(gp.GRB.Callback.RUNTIME))
            if where==gp.GRB.Callback.MESSAGE:self.message(m.cbGet(gp.GRB.Callback.MSG_STRING),t)
            elif where==gp.GRB.Callback.MIPSOL:
                self.solutions.append(dict(time=t,objective=finite(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),point=np.asarray(m.cbGetSolution(self.variables),dtype=float)))
                self.event('first_incumbent',t,'MIPSOL raw point buffered; audits only after terminal')
            elif where==gp.GRB.Callback.MIPNODE:
                if float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))>0:self.event('first_nonroot',t,'MIPNODE_NODCNT > 0')
            elif where==gp.GRB.Callback.MIP:
                self.latest=dict(time=t,nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),nodes_left=float(m.cbGet(gp.GRB.Callback.MIP_NODLFT)),UB=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBST)),LB=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBND)),cuts=int(m.cbGet(gp.GRB.Callback.MIP_CUTCNT)))
            if t-self.last>=30:self.last=t;self.trace.append(dict(time=t,where=where,last_MIP_observation=dict(self.latest) if self.latest else None))
            if self.enabled and t>=600:
                if self.checkpoint is None:self.checkpoint=self.state('solver_runtime',t)
                if where==gp.GRB.Callback.MIP and 'first_MIP_at_or_after_600' not in self.checkpoint:self.checkpoint['first_MIP_at_or_after_600']=dict(self.latest)
                if not root_pass(self.times):self.early_stop=True;m.terminate()
        except Exception as e:self.errors.append(repr(e));m.terminate()
        finally:self.body_wall+=time.perf_counter()-wall;self.body_CPU+=time.thread_time()-cpu
    def json(self):return dict(timestamps=self.times,events=self.events,trace=self.trace,checkpoint=self.checkpoint,early_stop=self.early_stop,callback_errors=self.errors,first_branch_unexposed=True,unobserved_times_not_inferred=True)
def start_receipt(messages):
    literals=[r['literal'] for r in messages]
    loaded=any('Loaded user MIP start' in s for s in literals)
    produced=any('Produced solution with objective' in s or 'User MIP start produced solution' in s for s in literals)
    rejected=any('did not produce a new incumbent solution' in s or 'violates constraint' in s for s in literals)
    objective=next((float(m.group(1)) for s in literals if (m:=re.search(r'(?:with objective|objective)\s+([-+\d.eE]+)',s))),None)
    return dict(START_ATTEMPTED=True,START_SOLVER_ACCEPTED=bool(loaded or produced),Start_loaded_message_observed=loaded,rejection_message_observed=rejected,acceptance_observable=loaded or produced or rejected,solver_reported_Start_objective=objective,rejection_reason=[s for s in literals if 'violates' in s or 'did not produce' in s],messages=messages,solver_tolerances_not_relaxed=True,external_Start_repair_calls=0)
