"""Exact necessary conditions, deliberately permissive supersets of M1."""
from collections import defaultdict
import numpy as np
from v42_root.common import *
from v42_native.voltage import Stage,voltage_for,authority_sha
from .grid import coefficients
from .handoff import validate_handoff

def voltage_intervals(coeff,anchor,sites,initial,routes,battery,node_names=None):
    # Forward reachability only; permits every independently reachable site to
    # have all reachable MESS ratings simultaneously. This is a SUPERSET, not
    # an assertion that those mutually exclusive injections are implementable.
    reachable={u:{(s,0)} for u,s in initial.items()};by_time=defaultdict(list)
    for r in routes:by_time[r.depart].append(r)
    for t in range(96):
        for u,nodes in reachable.items():
            for s in sites:
                if (s,t) in nodes:nodes.add((s,t+1))
            for r in by_time[t]:
                if (r.source,t) in nodes: nodes.add((r.destination,r.connect))
    limits={(s,t):sum((s,t) in nodes for nodes in reachable.values()) for s in sites for t in range(96)}
    rows=[];worst=[];blocker=None;v=voltage_for(Stage.M1)
    for t,c in enumerate(coeff):
        lower=[];upper=[]
        for i,name in enumerate(c.control_names):
            s=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):lo=hi=float(anchor['controls'][t][i])
            elif name.startswith('mess_p_kw'):hi=limits[s,t]*battery.p_limit;lo=-hi
            elif name.startswith('mess_q_kvar'):hi=limits[s,t]*battery.pcs_kva;lo=-hi
            else:raise ValueError('UNRECOGNIZED_CONTROL')
            lower.append(lo);upper.append(hi)
        lb=np.array(lower);ub=np.array(upper);a=c.voltage_matrix.T
        lo=c.voltage_constant+np.maximum(a,0)@lb+np.minimum(a,0)@ub
        hi=c.voltage_constant+np.maximum(a,0)@ub+np.minimum(a,0)@lb
        for n,(l,h) in enumerate(zip(lo,hi)):
            if l>v.upper_squared+1e-8 or h<v.lower_squared-1e-8:
                rows.append(dict(slot=t,index=n,node_phase=node_names[n] if node_names else str(n),minimum_squared=float(l),maximum_squared=float(h),
                                 minimum_pu=float(np.sqrt(max(0,l))),maximum_pu=float(np.sqrt(max(0,h))),
                                 required_upper_change_pu=max(0,float(np.sqrt(max(0,l)))-v.upper_pu),
                                 required_lower_change_pu=max(0,v.lower_pu-float(np.sqrt(max(0,h)))),
                                 voltage_constant=float(c.voltage_constant[n]),coefficients=a[n].tolist(),lower_controls=lower,upper_controls=upper))
        worst.append(dict(slot=t,min_squared=float(lo.min()),max_squared=float(hi.max())))
        if t==79 and node_names and '83.2' in node_names:
            n=node_names.index('83.2');blocker=dict(slot=79,node_phase='83.2',minimum_squared=float(lo[n]),maximum_squared=float(hi[n]),minimum_pu=float(np.sqrt(max(0,lo[n]))),maximum_pu=float(np.sqrt(max(0,hi[n]))))
    return dict(PASS=not rows,impossible_rows=rows,impossible_count=len(rows),slot_summary=worst,
                PR105_blocker_interval=blocker,strongest_contradiction=max(rows,key=lambda r:max(r['required_upper_change_pu'],r['required_lower_change_pu'])) if rows else None,
                bound_semantics='Fixed exact AIDC. For each site/time, sum all independently source-reachable MESS P bounds and Q nameplates. Drops PCS coupling, route exclusivity, SOC coupling: a permissive SUPERSET. Passing is necessary, not sufficient.',
                PCS_relaxed_only_in_diagnostic=True,production_PCS_unchanged=True,voltage_authority_sha256=authority_sha(Stage.M1))

def preflight(data,anchor,sites,initial,routes,battery):
    handoff=read(OUT/'A1_TO_M1_HANDOFF.json');validate_handoff(handoff,anchor)
    cert,coeff=coefficients(data[0])
    with np.load(cert['outputs']['voltage']['path'],allow_pickle=False) as z:
        node_names=next(z[k].astype(str).tolist() for k in z.files if any(v in k.lower() for v in ('node','bus','name')) and z[k].ndim==1 and len(z[k])==len(coeff[0].voltage_constant))
    result=voltage_intervals(coeff,anchor,sites,initial,routes,battery,node_names)
    dump('M1_MESS_PQ_VOLTAGE_INTERVAL_DIAGNOSIS.json',result)
    # Every unit can remain at its source for all slots, P=Q=0, initial=terminal
    # energy. This witnesses SOC/terminal possibility, not robust grid feasibility.
    soc=battery.minimum<=battery.initial<=battery.maximum and battery.initial==battery.terminal
    domain=bool(routes) and bool(sites) and all(s in sites for s in initial.values())
    passed=result['PASS'] and soc and domain
    receipt=dict(PASS=passed,AIDC_anchor_PASS=True,AIDC_anchor_digest=digest(anchor),route_graph_nonempty=domain,
                 SOC_outer_feasibility=soc,terminal_SOC_possible=soc,PCS_connected_stay_possible=domain,
                 full_MESS_PQ_voltage_necessary_condition=result['PASS'],native_M1_authorized=passed,
                 sufficient_feasibility_claim=False,margin_relaxed=False)
    dump('M1_PREFLIGHT.json',receipt)
    if not passed:
        dump('M1_ROBUST_VOLTAGE_INFEASIBILITY.json',dict(status='PROVEN_STATIC_INFEASIBILITY' if not result['PASS'] else 'DOMAIN_PREFLIGHT_FAILED',
             impossible_row_count=result['impossible_count'],impossible_rows=result['impossible_rows'],
             strongest_contradiction=result['strongest_contradiction'],
             binding_authorities='Outer P/Q/nameplate and exact source reachability bounds. SOC/route exclusivity/PCS coupling were relaxed in the proof, so cannot rescue contradiction.',margin_changed=False))
    return receipt
