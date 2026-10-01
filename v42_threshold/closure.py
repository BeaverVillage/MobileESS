"""Conditional graph/energy ancestry diagnosis, never another solve/window sweep."""
from collections import defaultdict
from .common import *

def energy_predecessors(slot):
    assert 0<=slot<=96
    return list(range(slot))

def route_predecessors(graph,origin,target=66):
    bytime=defaultdict(list);incoming=defaultdict(list)
    for k,a in enumerate(graph):bytime[a[1]].append(k);incoming[a[2:4]].append((a[:2],k))
    reachable={(origin,0)}
    for t in range(96):
        for k in bytime[t]:
            a=graph[k]
            if a[:2] in reachable:reachable.add(a[2:4])
    # At a boundary, either a reachable site node or a legal in-progress trip.
    seeds={n for n in reachable if n[1]==target}
    crossing=[k for k,a in enumerate(graph) if a[-1] is not None and a[1]<target<a[3] and a[:2] in reachable]
    seeds.update(graph[k][:2] for k in crossing)
    ancestors=set(seeds);stack=list(seeds);edges=set(crossing)
    while stack:
        node=stack.pop()
        for predecessor,k in incoming[node]:
            if predecessor not in reachable:continue
            edges.add(k)
            if predecessor not in ancestors:ancestors.add(predecessor);stack.append(predecessor)
    return dict(earliest_slot=min(n[1] for n in ancestors),ancestor_nodes=len(ancestors),ancestor_arcs=len(edges),
        target_boundary=target,possible_in_progress_travel_arcs=len(crossing),initial_node_is_ancestor=(origin,0) in ancestors,
        reachability_used_for_dependency_diagnosis_only=True)

def location(v,u,t,graph,sites):
    stay={s:v.get(f'arc[{u},{k}]',0.) for k,a in enumerate(graph) for s in [a[0]] if a[-1] is None and a[1]==t}
    transit=[dict(arc=k,source=a[0],departure=a[1],destination=a[2],connection=a[3],root_mass=v.get(f'arc[{u},{k}]',0.))
        for k,a in enumerate(graph) if a[-1] is not None and a[1]<=t<a[3] and v.get(f'arc[{u},{k}]',0.)>1e-9]
    return dict(site_mass=stay,transit_mass=sum(r['root_mass'] for r in transit),travel_support=transit)

def diagnose(classification):
    if classification!='B3_INCONCLUSIVE':
        dump('CAUSAL_BACKWARD_CLOSURE.json',dict(execution='NOT_RUN_CERTIFICATE_OBTAINED',earliest_causal_predecessor_slot=None,
            no_new_window_solve=True,reason='Conditional Phase D applies only while the threshold question remains inconclusive.'))
        table('CAUSAL_BACKWARD_CLOSURE.csv',[],['source','unit','slot','execution'])
        return
    _,_,_,sites,initial,_,battery=inputs();graph=arcs();sources=[]
    for source in SOURCES:v,path=root(source);sources.append((source,v,path))
    with np.load(PR113/'B3_SOLUTION.npz',allow_pickle=False) as z:
        sources.append(('PR113_B3_INCUMBENT',dict(zip(map(str,z['names']),map(float,z['values']))),PR113/'B3_SOLUTION.npz'))
    if (OUT/'DIRECT_SOLUTION.npz').exists():
        with np.load(OUT/'DIRECT_SOLUTION.npz',allow_pickle=False) as z:
            sources.append(('DIRECT_UNCERTIFIED_POINT',dict(zip(map(str,z['names']),map(float,z['values']))),OUT/'DIRECT_SOLUTION.npz'))
    rows=[];units=[]
    for source,v,path in sources:
        for u,origin in sorted(initial.items()):
            cumulative=battery.initial;charged=discharged=travelled=0.;states={};observed=[]
            for t in range(66):
                c=sum(v.get(f'Pch[{u},{s},{t}]',0.) for s in sites);d=sum(v.get(f'Pdis[{u},{s},{t}]',0.) for s in sites)
                travel=sum(a[-1].energy_kwh*v.get(f'arc[{u},{k}]',0.) for k,a in enumerate(graph) if a[-1] is not None and a[1]==t)
                charge=battery.dt_hours*battery.eta_charge*c;discharge=battery.dt_hours*d/battery.eta_discharge
                if max(abs(charge),abs(discharge),abs(travel))>1e-7:observed.append(t)
                charged+=charge;discharged+=discharge;travelled+=travel;cumulative+=charge-discharge-travel
                rows.append(dict(source=source,unit=u,slot=t,charge_mode=v[f'charge_mode[{u},{t}]'],Pch_kw=c,Pdis_kw=d,
                    charge_energy_kwh=charge,discharge_energy_kwh=discharge,travel_energy_kwh=travel,
                    SOC_stored_next=v[f'SOC[{u},{t+1}]'],SOC_reconstructed_next=cumulative,
                    SOC_reconstruction_residual=cumulative-v[f'SOC[{u},{t+1}]'],outside_B3=t<58))
                if t+1 in [58,66]:
                    states[t+1]=dict(SOC=v[f'SOC[{u},{t+1}]'],SOC_reconstructed=cumulative,
                        initial_SOC=battery.initial,cumulative_charge_energy_kwh=charged,cumulative_discharge_energy_kwh=discharged,
                        cumulative_travel_energy_kwh=travelled,location=location(v,u,t+1,graph,sites))
            route=route_predecessors(graph,origin)
            units.append(dict(source=source,source_sha256=sha(path),unit=u,state_at_58=states[58],state_at_66=states[66],
                earliest_SOC_decision_predecessor_slot=min(energy_predecessors(66)),earliest_location_predecessor_slot=route['earliest_slot'],
                earliest_observed_nonzero_energy_ancestor=min(observed) if observed else None,
                route_dependency=route,SOC_dependency_chain='SOC66 -> SOC65 -> ... -> SOC0; each transition includes all Pch/Pdis and departure travel debit',
                mode_ancestry_slots=energy_predecessors(66),travel_ancestry_slots=energy_predecessors(66)))
    dump('CAUSAL_BACKWARD_CLOSURE.json',dict(execution='DIAGNOSIS_ONLY',earliest_causal_predecessor_slot=0,units=units,
        dependency_derived_successor_candidate_window=[0,95],expanded_window_run=False,parameter_sweep=False,
        dependency_graph_not_materiality_certificate=True,
        graph_meaning='Potential physical ancestry, not a claim that every ancestor is active or that all earlier binaries must be restored. SOC58 inherits pre58 P/mode/travel history; SOC66 inherits through slot0. Full96 terminal equality additionally couples later dispatch globally.',
        no_claim_58_buffer_sufficient=True,no_claim_window0_necessary_or_sufficient=True,
        line_sw1_A='Late P/Q/location at 66-95 affect inherited binding line faces; ancestry can affect those decisions but does not prove a unique route/mode/SOC gap cause.',
        optimization_calls=0))
    table('CAUSAL_BACKWARD_CLOSURE.csv',rows)
