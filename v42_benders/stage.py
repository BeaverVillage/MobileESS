"""Explicit anchor/state adapter shared by M1 and M2; no stage hidden cache."""
from dataclasses import dataclass,replace
from time import perf_counter
import numpy as np
import gurobipy as gp
from .canonical import from_model
from .engine import solve,relative_gap

@dataclass(frozen=True)
class Authority:
    sites: tuple
    routes: tuple
    battery: object
    horizon: int
    grid_builder: object # function(anchor, model, site_P, site_Q)
    point_validator: object # function(anchor, initial_state, names, point)

class BuildDeadline:
    def __init__(self,seconds):self.stage='M1';self.started=perf_counter();self.seconds=seconds
    def check(self):
        if self.remaining<=0:raise TimeoutError('MODEL_BUILD_DEADLINE')
    @property
    def remaining(self):return max(0.,self.seconds-(perf_counter()-self.started))

def build_model(aidc_anchor,initial_mess_state,authority,seconds=600):
    from v42_native import mess as native
    battery=replace(authority.battery,initial=float(initial_mess_state['initial_SOC']))
    battery.validate()
    sites=dict(initial_mess_state['sites'])
    if not sites or any(s not in authority.sites for s in sites.values()):raise ValueError('INITIAL_STATE')
    captured={}
    def builder(m,p,q):return authority.grid_builder(aidc_anchor,m,p,q)
    def capture(m,objectives,deadline,*args,**kwargs):
        from v42_two.contract import mess_groups
        groups=mess_groups(objectives)
        m.setObjective(objectives[0][1]);m.update()
        captured['model']=m.copy()
        arcs=[(s,t,s,t+1,None) for s in authority.sites for t in range(authority.horizon)]
        arcs += [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(authority.routes)]
        energy={};count={}
        for name in m.getAttr('VarName'):
            if name.startswith('arc['):
                k=int(name[4:-1].split(',')[1]);r=arcs[k][-1]
                energy[name]=0. if r is None else r.energy_kwh;count[name]=float(r is not None)
        captured.update(energy=energy,count=count,groups=[g.name for g in groups])
        return None,dict(optimize_calls=0)
    previous=native.optimize;native.optimize=capture
    try:
        native.solve('M1',BuildDeadline(seconds),authority.sites,sites,authority.routes,battery,
            authority.horizon,builder)
    finally:native.optimize=previous
    return captured

def solve_mess_stage_exact_benders(aidc_anchor,initial_mess_state,objective_stage,
        p1_lock=None,warm_start=None,time_limit=600,*,authority,threads=1):
    if objective_stage not in ['P1_MAX_LINE_LOADING','P2_MIN_INTERVENTION']:raise ValueError('OBJECTIVE_STAGE')
    if objective_stage=='P1_MAX_LINE_LOADING' and p1_lock is not None:raise ValueError('P1_HAS_NO_LOCK')
    if objective_stage=='P2_MIN_INTERVENTION' and (not p1_lock or not p1_lock.get('accepted')):
        raise ValueError('P2_REQUIRES_PRODUCTION_P1_ACCEPTANCE')
    from v42_native.contracts import digest
    context=digest(dict(aidc_anchor=aidc_anchor,initial_mess_state=initial_mess_state))
    if p1_lock and p1_lock.get('anchor_state_sha256')!=context:raise ValueError('P1_LOCK_CONTEXT_MISMATCH')
    started=perf_counter();built=build_model(aidc_anchor,initial_mess_state,authority,time_limit)
    m=built['model'];env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    try:
        if p1_lock:
            from v42_two.contract import P1_EPS
            m.addConstr(m.getVarByName('rho_max')<=p1_lock['value']+P1_EPS,name='inherited_P1_lock')
        m.update();can=from_model(m)
        names=list(map(str,can.names));start=None
        if warm_start is not None:
            start=np.asarray([warm_start.get(n,np.nan) for n in names])
            # Start values never change route bounds or the matrix.
        def validate(z):return authority.point_validator(aidc_anchor,initial_mess_state,names,z)
        kwargs={}
        if objective_stage=='P2_MIN_INTERVENTION':
            kwargs=dict(movement=np.asarray([built['energy'].get(names[i],0.) for i in can.xi]),
                count=np.asarray([built['count'].get(names[i],0.) for i in can.xi]),accepted_p1=p1_lock['value'])
        result,point,cuts=solve(can,env=env,seconds=max(.001,time_limit-(perf_counter()-started)),
            threads=threads,warm_start=start,warm_start_is_hint=True,validate=validate,**kwargs)
        result.update(objective_stage=objective_stage,anchor_explicit=True,initial_state_explicit=True,
            master_binaries=len(can.xi),route_bounds_unchanged=True,warm_start_only=True,
            joint_P_Q_SOC_decisions=True,P1_lock=None if p1_lock is None else p1_lock['value']+1e-7,
            A2_RUN=False,M2_RUN=False,Actual_PQ_repair=False,anchor_state_sha256=context,
            warm_start_values_applied=0 if start is None else int(np.isfinite(start[can.xi]).sum()),
            warm_start_constraints_changed=0)
        result['accepted']=bool(point is not None and result['status']=='P1_GAP_TARGET' and result['relative_gap']<=.005)
        return result,None if point is None else dict(zip(names,map(float,point))),cuts
    finally:m.dispose();env.dispose()
