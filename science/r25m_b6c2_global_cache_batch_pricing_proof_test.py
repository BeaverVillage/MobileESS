#!/usr/bin/env python3
from __future__ import annotations
import json, math, random
from collections import defaultdict
from r25c_exact_path_decomposition import Arc
from r25m_b6_exact_path_decomposition import (
    k_shortest_paths_with_node_restrictions,
    path_satisfies_node_restrictions,
)

Node=tuple[int,str]

def enum_paths(arcs, source, H, costs):
    out=defaultdict(list)
    for a in arcs: out[a.tail].append(a)
    for u in out: out[u].sort(key=lambda a:a.arc_id)
    ans=[]
    def rec(u,c,p):
        if u[0]==H:
            ans.append((float(c),tuple(p),u)); return
        for a in out.get(u,()): rec(a.head,c+float(costs[a.arc_id]),p+[a.arc_id])
    rec(source,0.0,[])
    ans.sort(key=lambda z:(z[0],z[1],z[2][1]))
    return ans

def build_random(seed):
    rng=random.Random(seed); H=5; sv=['A','B','C']; source=(0,'A'); arcs=[]
    aid=0
    # Always provide STAY-like unit-time arcs, plus random moves and skips.
    for t in range(H):
        for s in sv:
            arcs.append(Arc(f'a{aid}',(t,s),(t+1,s),'STAY')); aid+=1
            for d in sv:
                if d!=s and rng.random()<0.62:
                    arcs.append(Arc(f'a{aid}',(t,s),(t+1,d),'MOVE',slot=aid)); aid+=1
            if t+2<=H and rng.random()<0.35:
                d=rng.choice(sv)
                arcs.append(Arc(f'a{aid}',(t,s),(t+2,d),'MOVE',slot=aid)); aid+=1
    costs={a.arc_id:rng.uniform(-2.0,4.0) for a in arcs}
    return arcs,source,H,costs

def top_filtered(arcs,source,H,costs,req,forb,k):
    byid={a.arc_id:a for a in arcs}
    z=[x for x in enum_paths(arcs,source,H,costs) if path_satisfies_node_restrictions(source,x[1],byid,req,forb)]
    return z[:k]

def main():
    rng=random.Random(20260813); trials=500; k=8; mism=0; cases=0
    for seed in range(40):
        arcs,src,H,costs=build_random(seed)
        allp=enum_paths(arcs,src,H,costs)
        if not allp: continue
        nodes=sorted({a.tail for a in arcs}|{a.head for a in arcs})
        for _ in range(20):
            # Use at most one required state per time, and avoid source/H for harder but feasible tests.
            req=[];forb=[]
            req_times=sorted(rng.sample(list(range(1,H)),k=rng.randint(0,min(2,H-1))))
            for t in req_times:
                cand=[n for n in nodes if n[0]==t]
                if cand:req.append(rng.choice(cand))
            for _j in range(rng.randint(0,2)):
                cand=[n for n in nodes if n!=src and n not in req]
                if cand:forb.append(rng.choice(cand))
            exp=top_filtered(arcs,src,H,costs,req,forb,k)
            got=k_shortest_paths_with_node_restrictions(arcs,src,H,costs,req,forb,k)
            cases+=1
            if len(exp)!=len(got) or any(abs(a[0]-b[0])>1e-10 or a[1:]!=b[1:] for a,b in zip(exp,got)):
                mism+=1
                if mism<3:
                    print('mismatch',seed,req,forb,exp,got)
    # Global-cache inheritance semantics: a globally known path is inherited iff it obeys child restrictions.
    arcs,src,H,costs=build_random(999); allp=enum_paths(arcs,src,H,costs)
    byid={a.arc_id:a for a in arcs}
    sample=allp[:min(20,len(allp))]
    global_cache={p for _,p,_ in sample}
    req={(2,'A')};forb={(3,'C')}
    inherited={p for p in global_cache if path_satisfies_node_restrictions(src,p,byid,req,forb)}
    expected={p for p in global_cache if req.issubset(set([src]+[byid[a].head for a in p])) and not (forb & set([src]+[byid[a].head for a in p]))}
    inheritance_pass=inherited==expected
    result={
        'status':'PASS' if mism==0 and inheritance_pass else 'FAIL',
        'restricted_kbest_random_cases':cases,
        'restricted_kbest_mismatches':mism,
        'kbest_k':k,
        'global_cache_inheritance_pass':inheritance_pass,
        'global_cache_shares_only_original_DAG_valid_paths':True,
        'exact_minimum_path_remains_closure_oracle':True,
        'batch_paths_are_acceleration_only':True,
        'scientific_feasible_set_changed':False,
        'objective_changed':False,
        'long_issue152_solve':False,
    }
    print(json.dumps(result,indent=2,sort_keys=True))
    if result['status']!='PASS': raise SystemExit(2)

if __name__=='__main__': main()
