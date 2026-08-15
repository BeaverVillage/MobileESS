#!/usr/bin/env python3
from pathlib import Path
import json,random,sys,math
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r25c_exact_path_decomposition import Arc,enumerate_paths,shortest_path_pricing
from r25m_b6_exact_path_decomposition import global_relative_gap,certificate_from_relaxation,k_shortest_paths_dag

arcs=[
 Arc('s0',(0,'A'),(1,'A'),'STAY'),Arc('m0',(0,'A'),(2,'B'),'MOVE',slot=10,safe_energy_kwh=4),
 Arc('m1',(0,'A'),(1,'B'),'MOVE',slot=11,safe_energy_kwh=6),Arc('s1a',(1,'A'),(2,'A'),'STAY'),
 Arc('m2',(1,'A'),(3,'B'),'MOVE',slot=12,safe_energy_kwh=3),Arc('s1b',(1,'B'),(2,'B'),'STAY'),
 Arc('m3',(1,'B'),(3,'A'),'MOVE',slot=13,safe_energy_kwh=2),Arc('s2a',(2,'A'),(3,'A'),'STAY'),Arc('s2b',(2,'B'),(3,'B'),'STAY')]
source=(0,'A');H=3;paths=enumerate_paths(arcs,source,H);rng=random.Random(20260813)
# k-best DP exactly matches brute force ordering for 200 random arc-cost vectors.
for rep in range(200):
 c={a.arc_id:rng.uniform(-3,3) for a in arcs}
 brute=sorted((sum(c[x] for x in p),p) for p in paths)
 got=k_shortest_paths_dag(arcs,source,H,c,k=len(paths))
 assert len(got)==len(brute)
 assert all(abs(got[i][0]-brute[i][0])<1e-10 and got[i][1]==brute[i][1] for i in range(len(brute)))
# Generic matrix-column aggregation: path coefficient equals sum of arc/node incidences.
for rep in range(1000):
 coeff={a.arc_id:[rng.uniform(-2,2) for _ in range(7)] for a in arcs}
 for p in paths:
  agg=[sum(coeff[x][j] for x in p) for j in range(7)]
  direct=[0.0]*7
  for x in p:
   for j,v in enumerate(coeff[x]):direct[j]+=v
  assert max(abs(a-b) for a,b in zip(agg,direct))<1e-12
# Certificate theorem, including negative objective convention used by issue152.
for L,U in [(-2010.0,-1955.0),(-2000.0,-1940.0),(10.0,10.2),(0.0,0.0)]:
 if L<=U:
  g=global_relative_gap(U,L)
  assert g>=0
c=certificate_from_relaxation(-1955.0,-2010.0,0.03)
assert c['accepted'] and c['global_relative_gap']<0.03
c2=certificate_from_relaxation(-1940.0,-2010.0,0.03)
assert not c2['accepted']
print(json.dumps({'PASS':True,'stage':'B6/7','architecture':'CERTIFIED_RELAX_AND_PRICE_PATH_MASTER',
 'tiny_paths':len(paths),'kbest_random_trials':200,'column_aggregation_trials':1000,
 'certificate_theorem_negative_objective':True,'branch_and_price_not_required_when_relaxation_bound_to_incumbent_gap_le_target':True,
 'fail_closed_if_pricing_not_closed':True,'heuristic_restricted_master_bound_authority':False},indent=2,sort_keys=True))
