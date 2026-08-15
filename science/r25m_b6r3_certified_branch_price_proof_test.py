#!/usr/bin/env python3
from __future__ import annotations
import json,random,math
from r25c_exact_path_decomposition import Arc
from r25m_b6_exact_path_decomposition import shortest_path_with_node_restrictions,path_satisfies_node_restrictions,branch_price_gap_prunable,global_relative_gap

H=4;src=(0,'A')
arcs=[
 Arc('a0',(0,'A'),(1,'A'),'STAY'),Arc('a1',(0,'A'),(1,'B'),'MOVE',slot=1),
 Arc('a2',(1,'A'),(2,'A'),'STAY'),Arc('a3',(1,'A'),(2,'B'),'MOVE',slot=3),
 Arc('a4',(1,'B'),(2,'B'),'STAY'),Arc('a5',(1,'B'),(2,'A'),'MOVE',slot=5),
 Arc('a6',(2,'A'),(3,'A'),'STAY'),Arc('a7',(2,'A'),(3,'B'),'MOVE',slot=7),
 Arc('a8',(2,'B'),(3,'B'),'STAY'),Arc('a9',(2,'B'),(3,'A'),'MOVE',slot=9),
 Arc('a10',(3,'A'),(4,'A'),'STAY'),Arc('a11',(3,'A'),(4,'B'),'MOVE',slot=11),
 Arc('a12',(3,'B'),(4,'B'),'STAY'),Arc('a13',(3,'B'),(4,'A'),'MOVE',slot=13)]
byid={a.arc_id:a for a in arcs};out={}
for a in arcs:out.setdefault(a.tail,[]).append(a)

def enum(cur,path):
 if cur[0]==H:
  yield tuple(path),cur;return
 for a in out.get(cur,[]):yield from enum(a.head,path+[a.arc_id])
paths=list(enum(src,[]))

def nodes(path):
 ns=[src];cur=src
 for aid in path:cur=byid[aid].head;ns.append(cur)
 return set(ns)

rng=random.Random(250613)
restricted_trials=0
candidates=[(1,'A'),(1,'B'),(2,'A'),(2,'B'),(3,'A'),(3,'B')]
for _ in range(500):
 cost={a.arc_id:rng.uniform(-3,5) for a in arcs}
 req=set(rng.sample(candidates,rng.randrange(0,3)))
 forb=set(rng.sample(candidates,rng.randrange(0,3)))-req
 feasible=[]
 for p,s in paths:
  if path_satisfies_node_restrictions(src,p,byid,req,forb):
   feasible.append((sum(cost[x] for x in p),p,s))
 got=shortest_path_with_node_restrictions(arcs,src,H,cost,req,forb)
 if not feasible:
  assert not math.isfinite(got[0])
 else:
  best=min(feasible,key=lambda z:(z[0],z[1],z[2][1]))
  assert abs(got[0]-best[0])<1e-10,(req,forb,got,best)
  assert path_satisfies_node_restrictions(src,got[1],byid,req,forb)
 restricted_trials+=1

# Binary node branch partitions every integer path exactly into y=0/y=1 children.
partition_checks=0
for n in candidates:
 p0=[p for p,s in paths if n not in nodes(p)]
 p1=[p for p,s in paths if n in nodes(p)]
 assert set(p0).isdisjoint(set(p1))
 assert set(p0)|set(p1)==set(p for p,s in paths)
 partition_checks+=1

# Gap pruning is conservative for minimization: if node LB passes, any tighter
# feasible optimum in [LB,U] also passes relative to the same incumbent U.
for U in (-1900.0,-1950.0,-2000.0):
 for L in (U-100,U-50,U-20,U-5):
  p=branch_price_gap_prunable(U,L,0.03)
  if p:
   for z in [L+(U-L)*i/20 for i in range(21)]:
    assert global_relative_gap(U,z)<=0.03+1e-12

print(json.dumps({'status':'PASS','restricted_shortest_path_trials':restricted_trials,'node_branch_partition_checks':partition_checks,'total_paths':len(paths),'certificate_pruning_math':'PASS'},indent=2))
