"""Immutable input-only MESS prescreen; no solver or grid/point dependency.

Only structural zeros of the original nonnegative unit-flow DAG are removed.
SOC interval checks describe whole physical paths and are never used to remove
an arc from the original fractional LP. The original SOC/P/Q rows stay intact.
"""
from dataclasses import dataclass, replace
from collections import defaultdict, deque
from fractions import Fraction as F
from functools import lru_cache
from math import isfinite, nextafter, inf
from time import perf_counter
from .contracts import digest, require

BATTERY_FIELDS=('minimum','maximum','initial','terminal','p_limit','pcs_kva',
                'eta_charge','eta_discharge','dt_hours')
SLOT_FIELDS=('slot','arcs','stays','travel','states','Pch','Pdis','Q','SOC','charge_mode','PCS16')

def _intersection(a,b):
    if a is None or b is None:return None
    lo,hi=max(a[0],b[0]),min(a[1],b[1])
    return (lo,hi) if lo<=hi else None

def _hull(a,b):
    return b if a is None else a if b is None else (min(a[0],b[0]),max(a[1],b[1]))

def _shift(a,lo,hi):return None if a is None else (a[0]+lo,a[1]+hi)

def _outward(value,lower):
    result=float(value)
    if (F(result)>value if lower else F(result)<value):
        result=nextafter(result,-inf if lower else inf)
    return result

@dataclass(frozen=True)
class UnitDomain:
    mess:str
    origin:str
    retained:tuple
    forward:tuple
    backward:tuple
    removals:tuple
    slots:tuple
    terminal_states:int
    global_soc:tuple
    path_soc_rejections:tuple

    def receipt(self):
        rows=[dict(zip(SLOT_FIELDS,row)) for row in self.slots]
        return dict(mess=self.mess,origin=self.origin,retained_arc_indices=list(self.retained),
            forward_nodes=[list(v) for v in self.forward],backward_nodes=[list(v) for v in self.backward],
            removals=[dict(arc=k,reason=reason) for k,reason in self.removals],per_slot=rows,
            arcs=len(self.retained),stays=sum(r['stays'] for r in rows),
            travel=sum(r['travel'] for r in rows),states=sum(r['states'] for r in rows)+self.terminal_states,
            terminal_states=self.terminal_states,Pch=sum(r['Pch'] for r in rows),
            Pdis=sum(r['Pdis'] for r in rows),Q=sum(r['Q'] for r in rows),SOC=len(rows)+1,
            charge_mode=len(rows),PCS16=sum(r['PCS16'] for r in rows),
            global_SOC=[dict(slot=t,lower_exact=str(lo),upper_exact=str(hi),
                lower_outward=_outward(lo,True),upper_outward=_outward(hi,False))
                for t,lo,hi in self.global_soc],
            path_SOC_diagnostic_rejections=dict(self.path_soc_rejections),
            SOC_arc_deletions_applied=0,SOC_bound_changes_applied=0,
            path_SOC_diagnostics_are_not_fractional_LP_zero_proofs=True)

@dataclass(frozen=True)
class PhysicalDomain:
    sites:tuple
    initial:tuple
    routes:tuple
    battery:tuple
    horizon:int
    arcs:tuple
    units:tuple
    state_sha:str
    producer_wall_seconds:float
    cache_hit:bool=False
    lookup_wall_seconds:float=0.

    def scientific_state(self):
        return dict(schema='V42_EXACT_PHYSICAL_PRESCREEN_V1',sites=list(self.sites),initial=list(self.initial),
            battery=dict(zip(BATTERY_FIELDS,self.battery)),horizon=self.horizon,
            arcs=[(s,t,d,end,None if r is None else vars(r)) for s,t,d,end,r in self.arcs],
            units=[u.receipt() for u in self.units],
            structural_proof='Original nonnegative unit flow on a strict forward-time DAG; no source path or terminal suffix implies exact zero in LP and integer domains',
            SOC_pruning_policy='DIAGNOSTIC_ONLY_NO_ORIGINAL_FRACTIONAL_LP_ZERO_CERTIFICATE',
            energy_debit='Whole route energy in SOC[depart+1], not gradually over transit',
            native_optimize_calls=0,grid_or_optimization_artifacts_read=0)

    def receipt(self):
        proof=verify_domain(self)
        additional=sum(reason=='BACKWARD_DEAD_END' for u in self.units for _,reason in u.removals)
        return dict(self.scientific_state(),PASS=proof['PASS'],state_sha=self.state_sha,independent_proof=proof,
            additional_exact_removed_arcs=additional,additional_SOC_removed_arcs=0,
            original_constructor_forward_removed_arcs=sum(reason=='FORWARD_UNREACHABLE' for u in self.units for _,reason in u.removals),
            meaningful_new_physical_prescreen_gain=additional>0,
            producer_wall_seconds=self.producer_wall_seconds,cache_hit=self.cache_hit,
            lookup_wall_seconds=self.lookup_wall_seconds)

def _unit(mess,origin,sites,arcs,battery,H):
    bytime=defaultdict(list)
    for k,a in enumerate(arcs):bytime[a[1]].append(k)
    forward={(origin,0)}
    for t in range(H):
        for k in bytime[t]:
            a=arcs[k]
            if a[:2] in forward:forward.add(a[2:4])
    backward={(s,H) for s in sites}
    for t in reversed(range(H)):
        for k in bytime[t]:
            a=arcs[k]
            if a[2:4] in backward:backward.add(a[:2])
    removed=[];keep=[]
    for k,a in enumerate(arcs):
        reason='FORWARD_UNREACHABLE' if a[:2] not in forward else 'BACKWARD_DEAD_END' if a[2:4] not in backward else None
        if reason:removed.append((k,reason))
        else:keep.append(k)
    require((origin,0) in backward,'MESS_ORIGINAL_GRAPH_NO_TERMINAL_PATH')
    states={v for k in keep for v in (arcs[k][:2],arcs[k][2:4])}
    bounds=(F(battery['minimum']),F(battery['maximum']))
    initial=F(battery['initial']);terminal=F(battery['terminal']);limit=F(battery['p_limit'])
    charge=F(float(battery['dt_hours']*battery['eta_charge']))*limit
    discharge=F(float(battery['dt_hours']/battery['eta_discharge']))*limit
    ordered=sorted(keep,key=lambda k:(arcs[k][1],k))
    # Exact stored binary-rational coefficient products; no epsilon trimming.
    def delta(k):
        route=arcs[k][-1]
        return (-discharge,charge) if route is None else (-F(float(route.energy_kwh)),-F(float(route.energy_kwh)))
    ef={(origin,0):(initial,initial)};eb={(s,H):(terminal,terminal) for s in sites}
    for k in ordered:
        a=arcs[k];lo,hi=delta(k);value=_intersection(_shift(ef.get(a[:2]),lo,hi),bounds)
        if value is not None:ef[a[2:4]]=_hull(ef.get(a[2:4]),value)
    for k in reversed(ordered):
        a=arcs[k];lo,hi=delta(k);value=_intersection(_shift(eb.get(a[2:4]),-hi,-lo),bounds)
        if value is not None:eb[a[:2]]=_hull(eb.get(a[:2]),value)
    meet={v:_intersection(ef.get(v),eb.get(v)) for v in states};rejected=defaultdict(int)
    for k in ordered:
        a=arcs[k];reason=None
        for v in (a[:2],a[2:4]):
            if v not in ef:reason='FORWARD_PATH_SOC_EMPTY'
            elif v not in eb:reason='BACKWARD_PATH_SOC_EMPTY'
            elif meet[v] is None:reason='PATH_SOC_INTERSECTION_EMPTY'
            if reason:break
        lo,hi=delta(k)
        if not reason and _intersection(_shift(meet[a[:2]],lo,hi),meet[a[2:4]]) is None:reason='PATH_ARC_SOC_IMAGE_EMPTY'
        if reason:rejected[reason]+=1
    # Global SOC outer envelope covers fractional route mixtures; it is
    # reported only. Current PR161 security remains the bound-change authority.
    keep_set=set(keep)
    cost=[max((F(float(arcs[k][-1].energy_kwh)) for k in bytime[t]
        if k in keep_set and arcs[k][-1] is not None),default=F(0)) for t in range(H)]
    lo=[bounds[0]]*(H+1);hi=[bounds[1]]*(H+1);lo[0]=hi[0]=initial;lo[H]=hi[H]=terminal
    for t in range(H):lo[t+1]=max(lo[t+1],lo[t]-discharge-cost[t]);hi[t+1]=min(hi[t+1],hi[t]+charge)
    for t in reversed(range(H)):lo[t]=max(lo[t],lo[t+1]-charge);hi[t]=min(hi[t],hi[t+1]+discharge+cost[t])
    slots=[]
    for t in range(H):
        ks=[k for k in bytime[t] if k in keep_set];stay=sum(arcs[k][-1] is None for k in ks)
        slots.append((t,len(ks),stay,len(ks)-stay,sum(v[1]==t for v in states),stay,stay,stay,1,1,16*stay))
    return UnitDomain(mess,origin,tuple(keep),tuple(sorted(forward)),tuple(sorted(backward)),tuple(removed),
        tuple(slots),sum(v[1]==H for v in states),tuple((t,lo[t],hi[t]) for t in range(H+1)),tuple(sorted(rejected.items())))

@lru_cache(maxsize=8)
def _cached(sites,initial,routes,battery,H):
    began=perf_counter();b=dict(zip(BATTERY_FIELDS,battery))
    arcs=tuple([(s,t,s,t+1,None) for s in sites for t in range(H)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)])
    units=tuple(_unit(m,origin,sites,arcs,b,H) for m,origin in initial)
    result=PhysicalDomain(sites,initial,routes,battery,H,arcs,units,'',perf_counter()-began)
    state_sha=digest(result.scientific_state())
    return replace(result,state_sha=state_sha,producer_wall_seconds=perf_counter()-began)

def build_domain(sites,initial_sites,routes,battery,horizon):
    """Same original graph input key for B2/B3 M1/M2; no grid-bound cache."""
    began=perf_counter();sites=tuple(sites);routes=tuple(routes);battery.validate()
    require(type(horizon) is int and horizon>0 and sites and len(set(sites))==len(sites),'MESS_PHYSICAL_DOMAIN_AXIS')
    require(initial_sites and all(origin in sites for origin in initial_sites.values()),'MESS_PHYSICAL_DOMAIN_INITIAL')
    for r in routes:
        r.validate(horizon);require(r.source in sites and r.destination in sites,'ROUTE_SITE')
    values=tuple(float(getattr(battery,k)) for k in BATTERY_FIELDS)
    hits=_cached.cache_info().hits
    result=_cached(sites,tuple(sorted(initial_sites.items())),routes,values,horizon)
    return replace(result,cache_hit=_cached.cache_info().hits>hits,lookup_wall_seconds=perf_counter()-began)

def verify_domain(domain):
    from .mess_domain_verify import verify_domain as independently_verify
    return independently_verify(domain)
