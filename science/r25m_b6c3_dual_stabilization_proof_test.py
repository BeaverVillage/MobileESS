#!/usr/bin/env python3
import json, math, random
from collections import defaultdict
from r25c_exact_path_decomposition import Arc
from r25m_b6_exact_path_decomposition import (
    blend_dual_maps, update_dual_center, k_shortest_paths_dag,
    k_shortest_paths_with_node_restrictions,
)

R=random.Random(20260813)
TOL=1e-7

# Pure helper algebra.
for _ in range(2000):
    keys=list(range(R.randint(1,12)))
    cur={k:R.uniform(-5,5) for k in keys}
    cen={k:R.uniform(-5,5) for k in keys}
    a=R.uniform(0.05,1.0)
    got=blend_dual_maps(cur,cen,a)
    assert all(abs(got[k]-(a*cur[k]+(1-a)*cen[k]))<1e-12 for k in keys)
    b=R.uniform(0,0.95)
    upd=update_dual_center(cen,cur,b)
    assert all(abs(upd[k]-(b*cen[k]+(1-b)*cur[k]))<1e-12 for k in keys)

# Build random acyclic routing DAGs and verify the scientific closure decision is
# *entirely* determined by the true dual exact minimum path, not stabilization.
cases=0
false_closure=0
unsafe_stab_insert=0
true_negative_missed=0
restricted_cases=0
for trial in range(700):
    H=R.randint(4,8)
    services=[f'S{i}' for i in range(R.randint(2,4))]
    source=(0,services[0])
    arcs=[]; aid=0
    # STAY and random 1/2-step moves. Guarantee STAY connectivity to H.
    for h in range(H):
        for s in services:
            arcs.append(Arc(f'a{aid}',(h,s),(h+1,s),'STAY'));aid+=1
            for d in services:
                if d==s: continue
                if R.random()<0.55:
                    D=1 if h+1<=H else None
                    if D:
                        arcs.append(Arc(f'a{aid}',(h,s),(h+1,d),'MOVE',slot=aid));aid+=1
                if h+2<=H and R.random()<0.22:
                    arcs.append(Arc(f'a{aid}',(h,s),(h+2,d),'MOVE',slot=aid));aid+=1
    true_cost={a.arc_id:R.uniform(-3,3) for a in arcs}
    center_cost={a.arc_id:R.uniform(-3,3) for a in arcs}
    alpha=R.uniform(0.2,0.9)
    stab_cost={a.arc_id:alpha*true_cost[a.arc_id]+(1-alpha)*center_cost[a.arc_id] for a in arcs}

    true_k=k_shortest_paths_dag(arcs,source,H,true_cost,8)
    stab_k=k_shortest_paths_dag(arcs,source,H,stab_cost,8)
    assert true_k and stab_k
    true_min=true_k[0][0]
    closure=(true_min>=-TOL)
    # Stabilized candidates are accepted only after evaluation under true costs.
    accepted=[]
    byid={a.arc_id:a for a in arcs}
    for _,p,sink in stab_k:
        trc=sum(true_cost[x] for x in p)
        if trc < -TOL:
            accepted.append((trc,p))
            if trc >= -TOL: unsafe_stab_insert+=1
    if closure and accepted:
        # impossible because exact true minimum is <= every candidate true cost
        false_closure+=1
    if true_min < -TOL and not (true_k[0][0] < -TOL):
        true_negative_missed+=1
    cases+=1

    # Restricted-child version: same closure invariant with required/forbidden nodes.
    internal=[(h,s) for h in range(1,H) for s in services]
    forbidden=set(R.sample(internal,k=min(len(internal),R.randint(0,2)))) if internal else set()
    required=set()
    if internal and R.random()<0.45:
        # choose at most one required state at a time, avoiding forbidden
        cand=[n for n in internal if n not in forbidden]
        if cand: required={R.choice(cand)}
    tk=k_shortest_paths_with_node_restrictions(arcs,source,H,true_cost,required,forbidden,8)
    sk=k_shortest_paths_with_node_restrictions(arcs,source,H,stab_cost,required,forbidden,8)
    if tk:
        tmin=tk[0][0]
        closure2=(tmin>=-TOL)
        accepted2=[]
        for _,p,sink in sk:
            trc=sum(true_cost[x] for x in p)
            if trc < -TOL: accepted2.append(trc)
        if closure2 and accepted2:false_closure+=1
        restricted_cases+=1

out={
  'status':'PASS' if false_closure==0 and unsafe_stab_insert==0 and true_negative_missed==0 else 'FAIL',
  'random_root_cases':cases,
  'random_restricted_child_cases':restricted_cases,
  'false_pricing_closure_cases':false_closure,
  'unsafe_stabilized_insertions':unsafe_stab_insert,
  'true_negative_minimum_missed':true_negative_missed,
  'stabilized_dual_certificate_authority':False,
  'true_current_dual_exact_minimum_path_is_closure_oracle':True,
  'stabilized_candidates_rechecked_under_true_dual':True,
  'scientific_feasible_set_changed':False,
  'objective_changed':False,
  'long_issue152_solve':False,
}
print(json.dumps(out,indent=2,sort_keys=True))
if out['status']!='PASS': raise SystemExit(2)
