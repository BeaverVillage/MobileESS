"""Literal solver events only; one conditional 1800-second optimization."""
import re
import gurobipy as gp
from .governance import write

TIMES=('model_ready','presolve_end','barrier_start','barrier_end','crossover_start',
       'crossover_end','root_relaxation_complete','root_processing_complete',
       'first_nonroot_node','first_branch')

def root_gate(times,checkpoint=600):
    observations=[times[k] for k in ('root_processing_complete','first_nonroot_node','first_branch')]
    if all(t is None or t>checkpoint for t in observations):return 'FAIL'
    nonroot=times['first_nonroot_node'];branch=times['first_branch']
    progressed=any(t is not None and t<=checkpoint for t in (nonroot,branch))
    # A nonroot node directly demonstrates that root processing finished;
    # its unexposed literal timestamp nevertheless remains null.
    if progressed:return 'PASS'
    return 'ROOT_COMPLETED_BRANCH_NOT_OBSERVED'

class Monitor:
    def __init__(self,checkpoint=True):
        self.times=dict.fromkeys(TIMES);self.times['model_ready']=0.
        self.events=[];self.trace=[];self.last=-30.;self.first_incumbent=None
        self.root_objective=None;self.root_runtime=None;self.early_stop=False
        self.checkpoint_enabled=checkpoint;self.errors=[]
    def message(self,line,t):
        line=line.strip();events=[]
        if line.startswith('Presolve time:'):events.append('presolve_end')
        if 'barrier log' in line.lower() or line.startswith('Barrier statistics:'):events.append('barrier_start')
        if line.startswith('Barrier solved model'):events.append('barrier_end')
        if 'crossover log' in line.lower():events.append('crossover_start')
        if line.startswith('Crossover time:'):events.append('crossover_end')
        if line.startswith('Root relaxation:') and 'objective' in line:
            events.append('root_relaxation_complete')
            match=re.search(r'objective\s+([-+\deE.]+)',line)
            self.root_objective=float(match[1]) if match else None
            match=re.search(r'([\d.]+) seconds',line)
            self.root_runtime=float(match[1]) if match else None
        if line.startswith(('Root processing complete','Root node processing complete')):events.append('root_processing_complete')
        # Gurobi exposes no reliable exact first-branch timestamp in this API.
        for event in events:
            if self.times[event] is None:
                self.times[event]=t;self.events.append(dict(time=t,event=event,literal=line))
    def __call__(self,m,where):
        if where==gp.GRB.Callback.POLLING:return
        try:
            t=float(m.cbGet(gp.GRB.Callback.RUNTIME))
            if where==gp.GRB.Callback.MESSAGE:
                self.message(m.cbGet(gp.GRB.Callback.MSG_STRING),t)
            elif where==gp.GRB.Callback.MIPNODE:
                count=float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))
                if count>0 and self.times['first_nonroot_node'] is None:
                    self.times['first_nonroot_node']=t
                    self.events.append(dict(time=t,event='first_nonroot_node',documented_callback='MIPNODE_NODCNT > 0',explored_nodes=count))
            elif where==gp.GRB.Callback.MIPSOL and self.first_incumbent is None:
                self.first_incumbent=t
            if t-self.last>=30:
                self.last=t;state=dict(time=t,callback=where)
                if where==gp.GRB.Callback.MIP:
                    state.update(nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),nodes_left=float(m.cbGet(gp.GRB.Callback.MIP_NODLFT)),bound=float(m.cbGet(gp.GRB.Callback.MIP_OBJBND)))
                self.trace.append(state)
                write('M1_LIVE_TIMELINE.json',dict(timestamps=self.times,events=self.events,trace=self.trace,early_stop=self.early_stop))
                print('M1_PROGRESS',state,self.times,flush=True)
            if self.checkpoint_enabled and t>=600 and root_gate(self.times)=='FAIL':
                self.early_stop=True;m.terminate()
        except Exception as error:
            self.errors.append(repr(error));m.terminate()
