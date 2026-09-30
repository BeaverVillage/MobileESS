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
from .contracts import require
from .solver import size
from .mess_domain import build_domain, authority_key
from .mess_optimizer import optimize, OptimizeBudget

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


def construct(domain, grid_builder, *, stage='M1', mode='MILP'):
    """Build without optimize: reusable for honest model-size-only diagnostics."""
    started=perf_counter();sites=domain.sites;battery=domain.battery;horizon=domain.horizon
    model=gp.Model('V42_NATIVE_'+stage);model.Params.OutputFlag=0
    x={};charge={};discharge={};reactive={};energy={};directions={};unit_stats=[]
    try:
        for u in domain.units:
            m=u.mess;incoming=defaultdict(list);outgoing=defaultdict(list);travel_by_time=defaultdict(list)
            vars_before=model.NumVars;rows_before=model.NumConstrs;nz_before=model.NumNZs;unit_started=perf_counter()
            for k in u.arc_indices:
                a=domain.arcs[k];incoming[a.head].append(k);outgoing[a.tail].append(k)
                x[m,k]=model.addVar(vtype=GRB.BINARY,name=f'arc[{m},{k}]')
                if a.route is not None:travel_by_time[a.depart].append(k)
            flow_nodes=sorted(set(u.nodes)|{(u.origin,0)})
            for s,t in flow_nodes:
                if t<horizon:
                    model.addConstr(gp.quicksum(x[m,k] for k in outgoing[s,t])-gp.quicksum(x[m,k] for k in incoming[s,t])==int(t==0 and s==u.origin),name='flow')
            model.addConstr(gp.quicksum(x[m,k] for k in u.arc_indices if domain.arcs[k].connect==horizon)==1,name='terminal_location')
            for t,I in u.global_soc:energy[m,t]=model.addVar(lb=I.lower,ub=I.upper,name=f'SOC[{m},{t}]')
            model.addConstr(energy[m,0]==battery.initial,name='initial_SOC')
            model.addConstr(energy[m,horizon]==battery.terminal,name='terminal_SOC')
            for t in u.charge_times:directions[m,t]=model.addVar(vtype=GRB.BINARY,name=f'charge_mode[{m},{t}]')
            stay={domain.arcs[k].tail:k for k in u.stay_indices}
            electrical_by_time=defaultdict(list)
            for s,t in u.electrical_states:
                key=m,s,t;connected=x[m,stay[s,t]];direction=directions[m,t]
                electrical_by_time[t].append(s)
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
            for t in range(horizon):
                travel=gp.quicksum(domain.arcs[k].route.energy_kwh*x[m,k] for k in travel_by_time[t])
                model.addConstr(energy[m,t+1]==energy[m,t]+battery.dt_hours*(battery.eta_charge*gp.quicksum(charge[m,s,t] for s in electrical_by_time[t])
                    -gp.quicksum(discharge[m,s,t] for s in electrical_by_time[t])/battery.eta_discharge)-travel,name='energy_balance')
            model.update()
            unit_stats.append(dict(mess=m,initial_site=u.origin,site_count=len(sites),horizon_slots=horizon,
                stay_arcs=len(u.stay_indices),travel_arcs=len(u.travel_indices),total_arcs=len(u.arc_indices),
                route_binaries=len(u.arc_indices),charge_mode_binaries=len(u.charge_times),
                Pch=len(u.electrical_states),Pdis=len(u.electrical_states),Q=len(u.electrical_states),SOC=horizon+1,
                PCS16_rows=FACES*len(u.electrical_states) if mode!='CIRCLE_ONLY_DIAGNOSTIC' else 0,
                flow_rows=sum(t<horizon for _,t in flow_nodes),total_constraints=model.NumConstrs-rows_before,
                total_columns=model.NumVars-vars_before,total_nonzeros=model.NumNZs-nz_before,
                model_build_seconds=perf_counter()-unit_started))
        p={(s,t):gp.quicksum(discharge.get((u.mess,s,t),0.)-charge.get((u.mess,s,t),0.) for u in domain.units) for s in sites for t in range(horizon)}
        q={(s,t):gp.quicksum(reactive.get((u.mess,s,t),0.) for u in domain.units) for s in sites for t in range(horizon)}
        primary=grid_builder(model,p,q)
        require([name for name,_ in primary]==['rho','reserve_shortfall'],'GRID_PRIMARY_AND_P2_CONTRACT')
        movement=gp.quicksum(domain.arcs[k].route.energy_kwh*x[u.mess,k] for u in domain.units for k in u.travel_indices)
        count=gp.quicksum(x[u.mess,k] for u in domain.units for k in u.travel_indices)
        tie=gp.quicksum((k+1)*x[u.mess,k] for u in domain.units for k in u.arc_indices)
        model.update();pre=size(model)
        stats=dict(model_build_seconds=perf_counter()-started,model_size_before_solve=pre,
                   per_mess=unit_stats,route_variable_count=len(x),route_move_arcs=len(domain.routes),
                   reachability_removed=sum(len(u.removals) for u in domain.units),
                   zero_unreachable_PQ_columns=len(domain.units)*len(sites)*horizon-len(reactive),PCS_mode=mode)
        return model,primary+[('movement_kwh',movement),('movement_count',count),('tie',tie)],x,stats
    except BaseException:
        model.dispose();raise


def validate_start(incumbent, domain):
    """Reject changed authority/missing/invalid physical starts before assigning ANY Start."""
    require(incumbent.get('domain_sha256')==domain.sha256,'M1_M2_DOMAIN_DRIFT')
    require(incumbent.get('initial_sites')==dict(domain.initial_sites),'M1_M2_INITIAL_STATE_DRIFT')
    require(incumbent.get('mode')=='MILP','MESS_START_PCS_MODE')
    values=incumbent['values']
    for u in domain.units:
        chosen=incumbent['chosen_arcs'][u.mess]
        require(len(chosen)==len(set(chosen)) and set(chosen)<=set(u.arc_indices),'MESS_START_ARC_OUTSIDE_DOMAIN')
        for a in domain.arcs:
            name=f'arc[{u.mess},{a.index}]'
            require(name in values and isfinite(values[name]) and abs(values[name]-int(a.index in chosen))<=1e-5,'MESS_START_ARC_VALUE')
        for t in range(domain.horizon):
            direction=values.get(f'charge_mode[{u.mess},{t}]')
            require(direction is not None and isfinite(direction) and min(abs(direction),abs(direction-1))<=1e-5,'MESS_START_DIRECTION')
            for s in domain.sites:
                names=[f'{prefix}[{u.mess},{s},{t}]' for prefix in ('Pch','Pdis','Q')]
                require(all(n in values and isfinite(values[n]) for n in names),'MESS_START_MISSING_PQ')
                c,d,q=(values[n] for n in names)
                require(c<=domain.battery.p_limit*direction+1e-5 and d<=domain.battery.p_limit*(1-direction)+1e-5,'MESS_START_DIRECTION_LOGIC')
                if (s,t) not in u.electrical_states:require(max(abs(c),abs(d),abs(q))<=1e-5,'MESS_START_REMOVED_PQ')
        for t,I in u.global_soc:
            e=values.get(f'SOC[{u.mess},{t}]')
            require(e is not None and isfinite(e) and I.lower-1e-5<=e<=I.upper+1e-5,'MESS_START_SOC_BOUND')
    audit=validate(incumbent,domain.sites,domain.routes,domain.battery,domain.horizon)
    require(audit['PASS'],'MESS_START_PHYSICAL_INVALID:'+','.join(audit['violations']))
    return audit


def solve(stage,deadline,sites,initial_sites,routes,battery,horizon,grid_builder,
          incumbent=None,*,mode='MILP',diagnostic=False,progress=None,domain=None):
    require(stage in ('M1','M2') and stage==deadline.stage,'MESS_STAGE')
    require(mode=='MILP' or diagnostic,'DIAGNOSTIC_CIRCLE_NOT_PRODUCTION')
    prepared=perf_counter();sites=tuple(sites);routes=tuple(routes)
    data_preparation=perf_counter()-prepared;screen_started=perf_counter()
    supplied=domain is not None
    if domain is None:domain=build_domain(sites,initial_sites,routes,battery,horizon)
    else:require(domain.input_sha256==authority_key(sites,initial_sites,routes,battery,horizon),'MESS_SHARED_DOMAIN_AUTHORITY_DRIFT')
    screen_seconds=perf_counter()-screen_started
    preparation=perf_counter()-prepared
    warm_audit=validate_start(incumbent,domain) if incumbent is not None else None
    # Legacy Deadline callers keep their requested duration; elapsed BUILD time
    # does not consume it. Native integration should pass OptimizeBudget(1800).
    budget=deadline if isinstance(deadline,OptimizeBudget) else OptimizeBudget(stage,deadline.seconds)
    model,objectives,x,stats=construct(domain,grid_builder,stage=stage,mode=mode)
    try:
        best,receipt=optimize(model,objectives,budget,incumbent,diagnostic_quadratic=mode!='MILP',
                              progress=progress,exact_diagnostic=diagnostic)
        receipt.update(stats,data_domain_preparation_seconds=preparation,
                       data_preparation_seconds=data_preparation,prescreen_or_authority_validation_seconds=screen_seconds,
                       domain_sha256=domain.sha256,shared_domain_supplied=supplied,
                       warm_start_physical_validation=warm_audit)
        if best is None:return None,receipt
        best.update(domain_sha256=domain.sha256,mode=mode,initial_sites=dict(domain.initial_sites),units='kW_kvar_kVA_kWh_hours',
                    chosen_arcs={u.mess:[k for k in u.arc_indices if best['values'][x[u.mess,k].VarName]>.5] for u in domain.units})
        for u in domain.units:
            for a in domain.arcs:best['values'].setdefault(f'arc[{u.mess},{a.index}]',0.)
            for t in range(horizon):
                best['values'].setdefault(f'charge_mode[{u.mess},{t}]',0.)
                for s in sites:
                    for prefix in ('Pch','Pdis','Q'):best['values'].setdefault(f'{prefix}[{u.mess},{s},{t}]',0.)
        best['physical_audit']=validate(best,sites,routes,battery,horizon)
        require(best['physical_audit']['PASS'],'MESS_PHYSICAL_VALIDATION_FAILED')
        return best,receipt
    finally:model.dispose()


def validate(result,sites,routes,battery,horizon,tolerance=1e-5):
    v=result['values'];arcs=[(s,t,s,t+1,None) for s in sites for t in range(horizon)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    violations=[];maximum=0.;travel_total=0.
    for m,origin in result['initial_sites'].items():
        if abs(v[f'SOC[{m},0]']-battery.initial)>tolerance:violations.append('INITIAL_SOC')
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
                if not connected and max(abs(c),abs(d),abs(q))>tolerance:violations.append('TRANSIT_PQ')
                if result['mode']!='CIRCLE_ONLY_DIAGNOSTIC' and any(cos(2*pi*f/16)*p+sin(2*pi*f/16)*q>battery.pcs_kva*cos(pi/16)*connected+tolerance for f in range(16)):violations.append('POLYGON')
                ch+=c;dis+=d
            travel=sum(a[-1].energy_kwh for a in selected if a[1]==t and a[-1] is not None);travel_total+=travel
            E+=battery.dt_hours*(battery.eta_charge*ch-dis/battery.eta_discharge)-travel
            if not battery.minimum-tolerance<=E<=battery.maximum+tolerance or abs(E-v[f'SOC[{m},{t+1}]'])>tolerance:violations.append('SOC')
        if abs(E-battery.terminal)>tolerance:violations.append('TERMINAL_SOC')
    if maximum>1+tolerance:violations.append('EXACT_CIRCLE')
    return dict(PASS=not violations,violations=violations,max_exact_circle_ratio=maximum,mobility_energy_kwh=travel_total)
