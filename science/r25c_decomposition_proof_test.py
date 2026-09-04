#!/usr/bin/env python3
from pathlib import Path
import json, random, sys, math
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r25c_exact_path_decomposition import Arc, enumerate_paths, shortest_path_pricing, column_from_path, signature_additive_cost

# Tiny mobility DAG with variable-duration MOVE and STAY arcs.
arcs=[
 Arc('s0', (0,'A'),(1,'A'),'STAY'),
 Arc('m0', (0,'A'),(2,'B'),'MOVE',slot=10,safe_energy_kwh=4.0,route_penalty=0.04),
 Arc('m1', (0,'A'),(1,'B'),'MOVE',slot=11,safe_energy_kwh=6.0,route_penalty=0.06),
 Arc('s1a',(1,'A'),(2,'A'),'STAY'),
 Arc('m2', (1,'A'),(3,'B'),'MOVE',slot=12,safe_energy_kwh=3.0,route_penalty=0.03),
 Arc('s1b',(1,'B'),(2,'B'),'STAY'),
 Arc('m3', (1,'B'),(3,'A'),'MOVE',slot=13,safe_energy_kwh=2.0,route_penalty=0.02),
 Arc('s2a',(2,'A'),(3,'A'),'STAY'),
 Arc('s2b',(2,'B'),(3,'B'),'STAY'),
]
source=(0,'A');H=3
paths=enumerate_paths(arcs,source,H)
assert paths and len(paths)==5, paths
byid={a.arc_id:a for a in arcs}

# 1) every enumerated path is an unsplit source-to-H path; incidence is 0/1.
for p in paths:
    cur=source
    seen=set()
    for aid in p:
        assert aid not in seen;seen.add(aid)
        a=byid[aid];assert a.tail==cur;cur=a.head
    assert cur[0]==H

# 2) exact DAG pricing equals brute-force all-column minimum for many reduced-cost vectors.
rng=random.Random(20260813)
for rep in range(200):
    rc={a.arc_id:rng.uniform(-3,3) for a in arcs}
    best=min((sum(rc[x] for x in p),p) for p in paths)
    v,p,_=shortest_path_pricing(arcs,source,H,rc)
    assert abs(v-best[0])<=1e-10,(rep,v,best)
    assert abs(sum(rc[x] for x in p)-best[0])<=1e-10

# 3) BUILD7C-style linear coupling signature is exactly additive over path arcs.
stay_price={(h,s):rng.uniform(-1,1) for h in range(H) for s in ['A','B']}
move_price={(a.tail[0],a.slot,a.tail[1],a.head[1]):rng.uniform(-1,1) for a in arcs if a.kind=='MOVE'}
energy_price={h:rng.uniform(-1,1) for h in range(H)}
for p in paths:
    col=column_from_path('MESSX',byid,p)
    sig=signature_additive_cost(col,stay_price,move_price,energy_price)
    direct=0.0
    for aid in p:
        a=byid[aid]
        direct+=a.route_penalty
        if a.kind=='STAY':direct+=stay_price.get(a.tail,0.0)
        else:direct+=move_price.get((a.tail[0],a.slot,a.tail[1],a.head[1]),0.0)+energy_price.get(a.tail[0],0.0)*a.safe_energy_kwh
    assert abs(sig-direct)<=1e-10

# 4) Full-column mapping is a bijection for the tiny DAG: distinct paths => distinct arc incidence.
incs={tuple(sorted(p)) for p in paths}
assert len(incs)==len(paths)

print(json.dumps({
 'PASS':True,'stage':'A3/6','tiny_graph_path_count':len(paths),'pricing_random_trials':200,
 'unsplit_path_incidence':True,'pricing_equals_full_enumeration':True,
 'linear_coupling_signature_additive':True,'full_column_path_arc_bijection_tiny_graph':True,
 'production_claim':'Kernel proof only. Exact production replacement requires branch-and-price or equivalent all-column certification; heuristic restricted columns are forbidden.'
},indent=2,sort_keys=True))
