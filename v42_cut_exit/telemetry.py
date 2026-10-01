"""Read-only callback observations; timestamps never imply fresh bounds."""
import re,math
from .policy import BASE_GAP
def number(v):
    return float(v) if v is not None and math.isfinite(v) and abs(v)<1e90 else None
def gap(ub,lb):
    if ub is None or lb is None:return None
    if ub==lb==0:return 0.
    return abs(ub-lb)/abs(ub) if ub else None
class Telemetry:
    def __init__(self):
        self.events={};self.messages=[];self.observations=[];self.milestones={};self.first_non_root=None;self.raw_root=None;self.last_root_bound=None;self.post_root_bound=None;self.latest={};self.phase='OPTIMIZE_START'
    def message(self,now,msg):
        self.messages.append(msg)
        s=msg.strip()
        if not s:return
        if 'Presolve time:' in s:self.events.setdefault('presolve_end_seconds',now)
        if 'Root barrier log' in s:self.events.setdefault('root_barrier_start_seconds',now)
        if 'Barrier solved model' in s:self.events.setdefault('root_barrier_end_seconds',now)
        if s.startswith('Crossover log'):self.events.setdefault('crossover_start_seconds',now)
        if s.startswith('Crossover time:'):self.events.setdefault('crossover_end_seconds',now)
        if s.startswith('Root relaxation:'):
            self.events.setdefault('root_relaxation_completion_seconds',now)
            self.events.setdefault('post_lp_root_start_seconds',now)
            self.phase='POST_LP_ROOT'
    def observe(self,now,where,ub=None,lb=None,nodes=None,iterations=None,cuts=None):
        r=dict(seconds=now,where=where,incumbent=number(ub),bound=number(lb),nodes=nodes,iterations=iterations,cuts=cuts)
        r['relative_gap']=gap(r['incumbent'],r['bound']);self.latest=r
        for n in [1,10,100]:
            if nodes is not None and nodes>=n:self.milestones.setdefault(str(n),now)
        if not self.observations or now-self.observations[-1]['seconds']>=1 or where in ('MIPSOL','FIRST_NON_ROOT','FINAL'):self.observations.append(r)
    def node(self,now,nodes,ub,lb,raw=None):
        if nodes==0:
            if self.raw_root is None and raw is not None:self.raw_root=number(raw)
            self.last_root_bound=number(lb)
        elif self.first_non_root is None:
            self.first_non_root=now;self.post_root_bound=self.last_root_bound;self.phase='TREE'
            self.observe(now,'FIRST_NON_ROOT',ub,lb,nodes)
        self.observe(now,'MIPNODE',ub,lb,nodes)
    def checkpoint(self,target,wall):
        eligible=[r for r in self.observations if r['seconds']<=target and r['where'] not in ('FINAL',)]
        # No fabricated 600s state for a solve that completed early.
        if wall<target:return dict(reached=False,seconds=target,observation_seconds=None,incumbent=None,bound=None,nodes=None,relative_gap=None)
        r=eligible[-1].copy() if eligible else dict(incumbent=None,bound=None,nodes=None,relative_gap=None)
        obs=r.pop('seconds',None)
        return dict(r,reached=True,seconds=target,observation_seconds=obs,observation_age_seconds=target-obs if obs is not None else None,carried_forward=True)
    def summary(self,wall):
        for name in ['presolve_start_seconds','presolve_end_seconds','root_barrier_start_seconds','root_barrier_end_seconds','crossover_start_seconds','crossover_end_seconds','root_relaxation_completion_seconds','post_lp_root_start_seconds']:self.events.setdefault(name,None)
        completion=self.events.get('root_relaxation_completion_seconds')
        overhead=self.first_non_root-completion if self.first_non_root is not None and completion is not None else None
        return dict(events=self.events,first_non_root_node_seconds=self.first_non_root,first_non_root_evidence='MIPNODE_NODCNT > 0',first_non_root_is_observation_upper_bound=True,time_to_explored_nodes=self.milestones,post_lp_root_seconds=overhead,post_lp_root_censored=self.first_non_root is None,post_lp_root_censor_seconds=max(0,wall-completion) if self.first_non_root is None and completion is not None else None,raw_root_relaxation_bound=self.raw_root,post_root_bound=self.post_root_bound,root_cut_bound_gain=self.post_root_bound-self.raw_root if self.post_root_bound is not None and self.raw_root is not None else None,checkpoints={str(n):self.checkpoint(n,wall) for n in [300,600]},node_count_note='NodeCount includes the root. Non-root entry requires a MIPNODE callback with explored count >0; branch creation can precede this observation.',phase_limits='Cuts, probing, heuristics and their reoptimizations are not individually timed.')
def parse(log):
    ps=re.findall(r'Presolve time: ([\d.]+)s',log);sz=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
    root=re.findall(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log)
    cut=re.search(r'Cutting planes:\s*\n(.*?)(?:\n\s*\n|\nExplored)',log,re.S)
    families={}
    if cut:
        for name,count in re.findall(r'^\s*([^:\n]+):\s*(\d+)\s*$',cut.group(1),re.M):families[name.strip()]=int(count)
    return dict(presolve_seconds=float(ps[-1]) if ps else None,presolved=dict(zip(['rows','columns','nonzeros'],map(int,sz[-1]))) if sz else None,root_relaxation=dict(complete=True,objective_rounded=float(root[-1][0]),iterations=int(root[-1][1]),seconds=float(root[-1][2])) if root else dict(complete=False,seconds=None),cut_counts=families,warnings=[s.strip() for s in log.splitlines() if 'Warning' in s],MIP_start_accepted=bool(re.search(r'(Loaded user MIP start|User MIP start produced solution) with objective',log)))
