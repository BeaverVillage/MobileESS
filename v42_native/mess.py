"""Audited native time-network MESS model with redundant PCS cone removed.

RouteArc/Battery/flow/SOC units and equations recovered from v42.joint_mobility.
The primary representation is 16-face inner polygon, never a face-count sweep.
"""
from dataclasses import dataclass,asdict
from collections import defaultdict
from math import isfinite,cos,sin,pi,hypot
from time import perf_counter
import gurobipy as gp
from gurobipy import GRB
from .contracts import require,digest
from .solver import optimize,size

FACES=16


@dataclass(frozen=True)
class RouteArc:
    route_id:str
    source:str
    destination:str
    depart:int
    arrive:int
    connect:int
    energy_kwh:float
    authority_sha256:str

    def validate(self,horizon):
        require(self.source!=self.destination and 0<=self.depart<self.arrive<=self.connect<horizon,'ROUTE_TIME')
        require(isfinite(self.energy_kwh) and self.energy_kwh>=0 and len(self.authority_sha256)==64,'ROUTE_AUTHORITY')


@dataclass(frozen=True)
class Battery:
    minimum:float
    maximum:float
    initial:float
    terminal:float
    p_limit:float
    pcs_kva:float
    eta_charge:float
    eta_discharge:float
    dt_hours:float=.25

    def validate(self):
        require(all(isfinite(v) for v in asdict(self).values()),'BATTERY_FINITE')
        require(0<=self.minimum<=self.initial<=self.maximum and self.minimum<=self.terminal<=self.maximum,'SOC_BOUNDS')
        require(0<self.p_limit<=self.pcs_kva and 0<self.eta_charge<=1 and 0<self.eta_discharge<=1 and self.dt_hours==.25,'BATTERY_UNITS')


def pcs_rows(model,p,q,connected,S,mode='MILP'):
    require(mode in ('MILP','LEGACY_BOTH','CIRCLE_ONLY_DIAGNOSTIC'),'PCS_MODE')
    if mode!='CIRCLE_ONLY_DIAGNOSTIC':
        for f in range(FACES):
            model.addConstr(cos(2*pi*f/FACES)*p+sin(2*pi*f/FACES)*q<=S*cos(pi/FACES)*connected,name='PCS16')
    if mode!='MILP':model.addQConstr(p*p+q*q<=S*S*connected,name='diagnostic_exact_PCS')


def solve(stage,deadline,sites,initial_sites,routes,battery,horizon,grid_builder,
          incumbent=None,*,mode='MILP',diagnostic=False,progress=None):
    require(stage in ('M1','M2') and stage==deadline.stage,'MESS_STAGE')
    require(mode=='MILP' or diagnostic,'DIAGNOSTIC_CIRCLE_NOT_PRODUCTION')
    battery.validate();deadline.check();started=perf_counter()
    routes=tuple(dict.fromkeys(routes))
    for r in routes:r.validate(horizon);require(r.source in sites and r.destination in sites,'ROUTE_SITE')
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(horizon)]
    arcs += [(r.source,r.depart,r.destination,r.connect,r) for r in routes]
    domain=digest(dict(arcs=[(s,t,d,e,None if r is None else asdict(r)) for s,t,d,e,r in arcs],initial=initial_sites,battery=asdict(battery)))
    if incumbent:require(incumbent['domain_sha256']==domain,'M1_M2_DOMAIN_DRIFT')
    incoming=defaultdict(list);outgoing=defaultdict(list);by_time=defaultdict(list);stay={}
    for k,(s,t,d,e,r) in enumerate(arcs):
        incoming[d,e].append(k);outgoing[s,t].append(k);by_time[t].append(k)
        if r is None:stay[s,t]=k
    model=gp.Model('V42_NATIVE_'+stage);model.Params.OutputFlag=0
    x={};charge={};discharge={};reactive={};energy={};removed=[]
    try:
        for m,origin in sorted(initial_sites.items()):
            require(origin in sites,'INITIAL_SITE');reachable={(origin,0)}
            for t in range(horizon):
                for k in by_time[t]:
                    s,b,d,e,r=arcs[k]
                    if (s,b) in reachable:reachable.add((d,e))
            for k,(s,t,d,e,r) in enumerate(arcs):
                deadline.check()
                if (s,t) not in reachable:x[m,k]=0.;removed.append((m,k))
                else:x[m,k]=model.addVar(vtype=GRB.BINARY,name=f'arc[{m},{k}]')
            for s in sites:
                for t in range(horizon):
                    model.addConstr(gp.quicksum(x[m,k] for k in outgoing[s,t])-gp.quicksum(x[m,k] for k in incoming[s,t])==int(t==0 and s==origin),name='flow')
            model.addConstr(gp.quicksum(x[m,k] for k,a in enumerate(arcs) if a[3]==horizon)==1,name='terminal_location')
            for t in range(horizon+1):energy[m,t]=model.addVar(lb=battery.minimum,ub=battery.maximum,name=f'SOC[{m},{t}]')
            model.addConstr(energy[m,0]==battery.initial,name='initial_SOC');model.addConstr(energy[m,horizon]==battery.terminal,name='terminal_SOC')
            for t in range(horizon):
                direction=model.addVar(vtype=GRB.BINARY,name=f'charge_mode[{m},{t}]')
                for s in sites:
                    key=m,s,t;connected=x[m,stay[s,t]]
                    if isinstance(connected,float):
                        charge[key]=discharge[key]=reactive[key]=0.;continue
                    charge[key]=model.addVar(lb=0,ub=battery.p_limit,name=f'Pch[{m},{s},{t}]')
                    discharge[key]=model.addVar(lb=0,ub=battery.p_limit,name=f'Pdis[{m},{s},{t}]')
                    reactive[key]=model.addVar(lb=-battery.pcs_kva,ub=battery.pcs_kva,name=f'Q[{m},{s},{t}]')
                    model.addConstr(charge[key]<=battery.p_limit*connected,name='connected_Pch')
                    model.addConstr(discharge[key]<=battery.p_limit*connected,name='connected_Pdis')
                    model.addConstr(charge[key]<=battery.p_limit*direction,name='no_simultaneous_charge')
                    model.addConstr(discharge[key]<=battery.p_limit*(1-direction),name='no_simultaneous_discharge')
                    model.addConstr(reactive[key]<=battery.pcs_kva*connected,name='connected_Qmax')
                    model.addConstr(reactive[key]>=-battery.pcs_kva*connected,name='connected_Qmin')
                    pcs_rows(model,discharge[key]-charge[key],reactive[key],connected,battery.pcs_kva,mode)
                travel=gp.quicksum(arcs[k][-1].energy_kwh*x[m,k] for k in by_time[t] if arcs[k][-1] is not None)
                model.addConstr(energy[m,t+1]==energy[m,t]+battery.dt_hours*(battery.eta_charge*gp.quicksum(charge[m,s,t] for s in sites)
                    -gp.quicksum(discharge[m,s,t] for s in sites)/battery.eta_discharge)-travel,name='energy_balance')
        p={(s,t):gp.quicksum(discharge[m,s,t]-charge[m,s,t] for m in initial_sites) for s in sites for t in range(horizon)}
        q={(s,t):gp.quicksum(reactive[m,s,t] for m in initial_sites) for s in sites for t in range(horizon)}
        primary=grid_builder(model,p,q)
        require([name for name,_ in primary]==['rho','reserve_shortfall'],'GRID_PRIMARY_AND_P2_CONTRACT')
        movement=gp.quicksum(a[-1].energy_kwh*x[m,k] for m in initial_sites for k,a in enumerate(arcs) if a[-1] is not None)
        count=gp.quicksum(x[m,k] for m in initial_sites for k,a in enumerate(arcs) if a[-1] is not None)
        tie=gp.quicksum((k+1)*x[m,k] for m in initial_sites for k in range(len(arcs)))
        built=perf_counter();pre=size(model)
        best,receipt=optimize(model,primary+[('movement_kwh',movement),('movement_count',count),('tie',tie)],deadline,incumbent,
            diagnostic_quadratic=mode!='MILP',progress=progress)
        receipt.update(model_build_seconds=built-started,model_size_before_solve=pre,route_variable_count=sum(not isinstance(v,float) for v in x.values()),
            route_move_arcs=len(routes),reachability_removed=len(removed),zero_unreachable_PQ_columns=sum(isinstance(v,float) for v in reactive.values()),PCS_mode=mode)
        if best is None:return None,receipt
        best.update(domain_sha256=domain,mode=mode,initial_sites=initial_sites,units='kW_kvar_kVA_kWh_hours',
            chosen_arcs={m:[k for k in range(len(arcs)) if not isinstance(x[m,k],float) and best['values'][x[m,k].VarName]>.5] for m in initial_sites})
        for m,k in removed:best['values'][f'arc[{m},{k}]']=0.
        for collection,prefix in ((charge,'Pch'),(discharge,'Pdis'),(reactive,'Q')):
            for (m,s,t),v in collection.items():
                if isinstance(v,float):best['values'][f'{prefix}[{m},{s},{t}]']=0.
        best['physical_audit']=validate(best,sites,routes,battery,horizon)
        require(best['physical_audit']['PASS'],'MESS_PHYSICAL_VALIDATION_FAILED')
        return best,receipt
    finally:model.dispose()


def validate(result,sites,routes,battery,horizon,tolerance=1e-5):
    v=result['values'];arcs=[(s,t,s,t+1,None) for s in sites for t in range(horizon)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    violations=[];maximum=0.;travel_total=0.
    for m,origin in result['initial_sites'].items():
        selected=[arcs[k] for k in result['chosen_arcs'][m]];loc=origin;t=0;visited=[]
        while t<horizon:
            match=[a for a in selected if a[:2]==(loc,t)]
            if len(match)!=1:violations.append('FLOW');break
            a=match[0];visited.append(a);loc,t=a[2:4]
        if len(visited)!=len(selected):violations.append('EXTRA_ARC')
        E=battery.initial
        for t in range(horizon):
            ch=dis=0
            for s in sites:
                c=v[f'Pch[{m},{s},{t}]'];d=v[f'Pdis[{m},{s},{t}]'];q=v[f'Q[{m},{s},{t}]'];p=d-c
                connected=any(a[:2]==(s,t) and a[-1] is None for a in selected)
                maximum=max(maximum,hypot(p,q)/battery.pcs_kva)
                if min(c,d)<-tolerance or max(c,d)>battery.p_limit+tolerance or c*d>tolerance:violations.append('P_MODE')
                if not connected and max(abs(p),abs(q))>tolerance:violations.append('TRANSIT_PQ')
                if result['mode']!='CIRCLE_ONLY_DIAGNOSTIC' and any(cos(2*pi*f/16)*p+sin(2*pi*f/16)*q>battery.pcs_kva*cos(pi/16)*connected+tolerance for f in range(16)):violations.append('POLYGON')
                ch+=c;dis+=d
            travel=sum(a[-1].energy_kwh for a in selected if a[1]==t and a[-1] is not None);travel_total+=travel
            E+=battery.dt_hours*(battery.eta_charge*ch-dis/battery.eta_discharge)-travel
            if not battery.minimum-tolerance<=E<=battery.maximum+tolerance or abs(E-v[f'SOC[{m},{t+1}]'])>tolerance:violations.append('SOC')
        if abs(E-battery.terminal)>tolerance:violations.append('TERMINAL_SOC')
    if maximum>1+tolerance:violations.append('EXACT_CIRCLE')
    return dict(PASS=not violations,violations=violations,max_exact_circle_ratio=maximum,mobility_energy_kwh=travel_total)
