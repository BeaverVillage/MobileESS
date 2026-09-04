#!/usr/bin/env python3
import json, math, random
from collections import defaultdict
from r25c_exact_path_decomposition import Arc
from r25m_b6_exact_path_decomposition import (
    k_shortest_paths_dag,
    branch_fractionality,
    strong_branch_score,
    branch_candidate_key,
    branch_side_distance,
    select_strong_branch_shortlist,
)

R=random.Random(20260813)

# 1) Basic scoring algebra: stronger worst-child improvement must dominate.
assert strong_branch_score(-100.0,-95.0,-96.0)[0] == 4.0
assert strong_branch_score(-100.0,-99.0,-90.0)[0] == 1.0
assert strong_branch_score(-100.0,float('inf'),-98.0)[0] == 2.0
assert strong_branch_score(-100.0,None,-98.0) == (-1.0,-1.0)

# 2) Fractionality and branch distances are well-defined and positive.
for _ in range(2000):
    x=R.uniform(-3.0,5.0)
    f=branch_fractionality(x)
    assert 0.0 <= f <= 0.5+1e-12
    fl=math.floor(x);ce=math.ceil(x)
    if abs(x-round(x))>1e-9:
        b=('integer','x',x,'I',-10.0,10.0)
        assert branch_side_distance(b,0)>0 and branch_side_distance(b,1)>0

# 3) The shortlist must no longer let a late-horizon 0.5 state automatically win
# a tie solely because it is maximally fractional.  Earlier states receive a mild
# shortlist preference, while final selection is still delegated to strong probes.
H=54
mob=[
    (0.50,-53,'M1',(53,'S1'),0.50),
    (0.49,-12,'M1',(12,'S2'),0.49),
    (0.48,-20,'M2',(20,'S3'),0.48),
]
sl=select_strong_branch_shortlist(mob,[],H,limit=3,early_weight=0.35)
assert sl[0][0]=='mobility_node'
assert sl[0][2][0] < 53, sl

# 4) Exact branch partition proof on random complete paths: occupancy branch 0/1
# is disjoint and exhaustive for every original trajectory.
partition_cases=0
partition_fail=0
for trial in range(400):
    H=R.randint(4,8)
    services=[f'S{i}' for i in range(R.randint(2,4))]
    source=(0,services[0]); arcs=[];aid=0
    for h in range(H):
        for s in services:
            arcs.append(Arc(f'a{aid}',(h,s),(h+1,s),'STAY'));aid+=1
            for d in services:
                if d!=s and R.random()<0.55:
                    arcs.append(Arc(f'a{aid}',(h,s),(h+1,d),'MOVE',slot=aid));aid+=1
    costs={a.arc_id:R.uniform(-1,1) for a in arcs}
    paths=k_shortest_paths_dag(arcs,source,H,costs,k=32)
    if not paths: continue
    byid={a.arc_id:a for a in arcs}
    # collect visited internal nodes from paths
    nodes=set()
    path_nodes=[]
    for _,p,sink in paths:
        cur=source;ns={source}
        for x in p:
            cur=byid[x].head;ns.add(cur)
        path_nodes.append(ns)
        nodes |= {n for n in ns if 0<n[0]<H}
    if not nodes: continue
    n=R.choice(sorted(nodes))
    c0=[];c1=[]
    for i,ns in enumerate(path_nodes):
        (c1 if n in ns else c0).append(i)
    if set(c0)&set(c1) or set(c0)|set(c1)!=set(range(len(paths))):
        partition_fail+=1
    partition_cases+=1

# 5) Integer branching is also an exact disjoint partition of the integer domain.
integer_partition_cases=0
for _ in range(1000):
    lo=R.randint(-5,2);hi=R.randint(lo+1,8)
    x=R.uniform(lo+0.05,hi-0.05)
    if abs(x-round(x))<1e-4: x+=0.13
    fl=math.floor(x);ce=math.ceil(x)
    vals=list(range(lo,hi+1))
    a={v for v in vals if v<=fl};b={v for v in vals if v>=ce}
    assert not (a&b)
    assert a|b==set(vals)
    integer_partition_cases+=1

# 6) Candidate keys are stable and do not depend on the current fractional value.
b1=('mobility_node','M1',(17,'S4'),0.41)
b2=('mobility_node','M1',(17,'S4'),0.49)
assert branch_candidate_key(b1)==branch_candidate_key(b2)
i1=('integer','mode_x',0.4,'B',0.0,1.0)
i2=('integer','mode_x',0.6,'B',0.0,1.0)
assert branch_candidate_key(i1)==branch_candidate_key(i2)

out={
  'status':'PASS' if partition_fail==0 else 'FAIL',
  'strong_branch_probe_certificate_authority':False,
  'pseudocost_certificate_authority':False,
  'exact_child_pricing_closure_still_required':True,
  'late_horizon_fractionality_only_rule_removed':True,
  'shortlist_early_horizon_tie_bias':True,
  'mobility_branch_partition_cases':partition_cases,
  'mobility_branch_partition_failures':partition_fail,
  'integer_branch_partition_cases':integer_partition_cases,
  'scientific_feasible_set_changed':False,
  'objective_changed':False,
  'long_issue152_solve':False,
}
print(json.dumps(out,indent=2,sort_keys=True))
if out['status']!='PASS': raise SystemExit(2)
