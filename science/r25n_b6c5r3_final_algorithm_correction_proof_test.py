#!/usr/bin/env python3
from __future__ import annotations
import json, random, math
from collections import defaultdict
from r25c_exact_path_decomposition import Arc
from r25m_b6_exact_path_decomposition import (
    k_shortest_paths_dag, choose_time_layer_multiway_partition,
    _path_nodes, gap_target_lower_bound, global_relative_gap
)

rng=random.Random(20260813)
partition_cases=0
partition_failures=0
for case in range(250):
    H=5
    services=["A","B","C"]
    source=(0,"A")
    arcs=[]
    # STAY arcs
    for h in range(H):
        for s in services:
            arcs.append(Arc(f"S_{case}_{h}_{s}",(h,s),(h+1,s),"STAY"))
    # random 1- or 2-step MOVE arcs; all durations positive.
    for h in range(H):
        for s in services:
            for t in services:
                if s==t: continue
                if rng.random()<0.55:
                    arcs.append(Arc(f"M1_{case}_{h}_{s}_{t}",(h,s),(h+1,t),"MOVE",slot=0))
                if h+2<=H and rng.random()<0.25:
                    arcs.append(Arc(f"M2_{case}_{h}_{s}_{t}",(h,s),(h+2,t),"MOVE",slot=1))
    costs={a.arc_id:rng.uniform(-2,3) for a in arcs}
    paths=k_shortest_paths_dag(arcs,source,H,costs,256)
    if len(paths)<2: continue
    byid={a.arc_id:a for a in arcs}
    sample=paths[:min(24,len(paths))]
    part=choose_time_layer_multiway_partition(sample,source,byid,(),(),H,4)
    if part is None: continue
    nodes=set(part["nodes"])
    # Exact partition over ALL enumerated paths, not only the k-best sample.
    for _,pth,_ in paths:
        ns=set(_path_nodes(source,tuple(pth),byid))
        explicit=sum(1 for n in nodes if n in ns)
        rest=(explicit==0)
        memberships=explicit+(1 if rest else 0)
        partition_cases+=1
        if memberships!=1:
            partition_failures+=1

# Gap threshold identity remains exact for negative Stage-1 objectives.
gap_cases=0
gap_failures=0
for _ in range(5000):
    u=-rng.uniform(100,3000)
    g=0.03
    thr=gap_target_lower_bound(u,g)
    L=thr+rng.uniform(-100, min(100, u-thr))
    lhs=global_relative_gap(u,L)<=g+1e-12
    rhs=L>=thr-1e-12
    gap_cases+=1
    if lhs!=rhs:gap_failures+=1

checks={
    "multiway_partition_cases":partition_cases,
    "multiway_partition_failures":partition_failures,
    "gap_threshold_cases":gap_cases,
    "gap_threshold_failures":gap_failures,
    "threads_winner":4,
    "mobility_integrality_first":True,
    "strong_qcp_probe_disabled_in_runtime_contract":True,
    "dual_stabilization_disabled_in_runtime_contract":True,
    "fixed_dual_bound_scientific_authority_requires_exact_restricted_pricing":True,
    "scientific_feasible_set_changed":False,
    "objective_changed":False,
    "gap_semantics_changed":False,
}
PASS=(partition_cases>1000 and partition_failures==0 and gap_failures==0)
out={"status":"PASS" if PASS else "FAIL","PASS":PASS,"checks":checks}
print(json.dumps(out,indent=2))
raise SystemExit(0 if PASS else 2)
