"""No callback filesystem writes: literal events, sparse traces and MIPSOL buffers."""
import time
import re
import threading
import numpy as np
import gurobipy as gp
from .common import finite
from v42_integrated.matrix import audit

TIMES=('presolve_end','barrier_start','barrier_end','crossover_start','crossover_end','root_relaxation_complete','DegenMoves_start','DegenMoves_end','root_processing_complete','first_nonroot','first_branch','first_incumbent')

def should_stop(times,incumbent_exists,model_feasible,cut_progress):
    progressed=times['first_nonroot'] is not None or times['first_branch'] is not None
    if progressed:return False
    if incumbent_exists and model_feasible and cut_progress:return False
    # The registered early-stop conjunction requires incumbent absence too.
    return not incumbent_exists and times['root_processing_complete'] is None

class Monitor:
    def __init__(self,A,d,variables,checkpoint=True):
        self.A=A;self.d=d;self.variables=variables;self.enabled=checkpoint
        self.times=dict.fromkeys(TIMES);self.events=[];self.trace=[];self.solutions=[];self.errors=[]
        self.calls=0;self.body_wall=0.;self.body_CPU=0.;self.last=-30.;self.latest=None;self.quick_valid=False
        self.checkpoint=None;self.early_stop=False;self.begin=None;self.done=threading.Event();self.watcher=None
    def event(self,name,t,literal):
        if self.times[name] is None:self.times[name]=t;self.events.append(dict(event=name,solver_seconds=t,literal=literal))
    def message(self,line,t):
        line=line.strip()
        if line.startswith('Presolve time:'):self.event('presolve_end',t,line)
        if 'root barrier log' in line.lower():self.event('barrier_start',t,line)
        if line.startswith('Barrier solved model'):self.event('barrier_end',t,line)
        if 'crossover log' in line.lower():self.event('crossover_start',t,line)
        if line.startswith('Crossover time:'):self.event('crossover_end',t,line)
        if line.startswith('Root relaxation:') and 'objective' in line:self.event('root_relaxation_complete',t,line)
        if line.startswith(('Root processing complete','Root node processing complete')):self.event('root_processing_complete',t,line)
        # A generic Total elapsed time (DegenMoves) line proves activity only,
        # and does not expose exact phase start/end timestamps.
        if '(DegenMoves)' in line:self.events.append(dict(event='DegenMoves_activity',solver_seconds=t,literal=line))
    def checkpoint_state(self,clock,now):
        latest=dict(self.latest) if self.latest is not None else None
        state=dict(clock=clock,observed_at_seconds=now,timestamps=dict(self.times),last_MIP_observation=latest,last_MIP_observation_age_seconds=(now-latest['time']) if latest and clock=='solver_runtime' else None,incumbent_observed=bool(self.solutions),full_unreduced_model_feasible_incumbent=self.quick_valid,independent_physical_validation='All buffered points independently checked after terminal; no unvalidated UB is published.',exact_600_node_count=None,exact_600_UB=None,exact_600_LB=None,unobservable_values_not_inferred=True)
        if clock=='solver_runtime' and latest and latest['time']==now:
            state.update(checkpoint_node_count=latest['nodes'],checkpoint_UB=latest['UB'],checkpoint_LB=latest['LB'],checkpoint_state_solver_seconds=now)
        else:state.update(checkpoint_node_count=None,checkpoint_UB=None,checkpoint_LB=None,checkpoint_state_solver_seconds=None)
        cut_progress=bool(latest and latest['cuts']>0)
        state['actual_cut_progress_observed']=cut_progress
        state['termination_requested']=should_stop(self.times,bool(self.solutions),self.quick_valid,cut_progress)
        return state
    def start_watch(self,m):
        self.begin=time.perf_counter()
        if not self.enabled:return
        def watch():
            while not self.done.wait(.25):
                elapsed=time.perf_counter()-self.begin
                if elapsed>=600:
                    if self.checkpoint is None:self.checkpoint=self.checkpoint_state('monotonic_wall_since_optimize',elapsed)
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
                point=np.asarray(m.cbGetSolution(self.variables),dtype=float)
                # One sparse full-row check per reported solution, not per callback.
                # It enables a model-feasible-incumbent checkpoint decision without
                # filesystem I/O or repeated coefficient loading inside callbacks.
                checked=audit(self.A,self.d,point,integral=True,tolerance=1e-8)
                self.quick_valid=self.quick_valid or checked['PASS']
                self.solutions.append(dict(time=t,objective=finite(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),point=point,full_rows=checked))
                self.event('first_incumbent',t,'MIPSOL callback; point buffered for independent physical certification')
            elif where==gp.GRB.Callback.MIPNODE:
                if float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))>0:self.event('first_nonroot',t,'MIPNODE_NODCNT > 0')
            elif where==gp.GRB.Callback.MIP:
                self.latest=dict(time=t,nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),nodes_left=float(m.cbGet(gp.GRB.Callback.MIP_NODLFT)),UB=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBST)),LB=finite(m.cbGet(gp.GRB.Callback.MIP_OBJBND)),cuts=int(m.cbGet(gp.GRB.Callback.MIP_CUTCNT)))
            if t-self.last>=30:
                self.last=t;self.trace.append(dict(time=t,where=where,last_MIP_observation=dict(self.latest) if self.latest else None))
            if self.enabled and t>=600:
                if self.checkpoint is None:self.checkpoint=self.checkpoint_state('solver_runtime',t)
                if where==gp.GRB.Callback.MIP and 'first_MIP_observation_at_or_after_600' not in self.checkpoint:self.checkpoint['first_MIP_observation_at_or_after_600']=dict(self.latest)
                if self.checkpoint['termination_requested']:self.early_stop=True;m.terminate()
        except Exception as error:self.errors.append(repr(error));m.terminate()
        finally:
            self.body_wall+=time.perf_counter()-wall;self.body_CPU+=time.thread_time()-cpu
    def json(self):
        return dict(timestamps=self.times,events=self.events,trace=self.trace,checkpoint=self.checkpoint,early_stop=self.early_stop,callback_errors=self.errors,time_origin='Gurobi RUNTIME except explicitly identified wall watchdog receipt',first_branch_exact_API_not_exposed=True,nulls_not_inferred=True)
