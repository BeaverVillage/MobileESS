#!/usr/bin/env python3
from __future__ import annotations
import json, random
from r25m_b6_exact_path_decomposition import Arc,k_shortest_paths_dag,rc_audit_pass,guarded_full_lb

def brute(arcs,source,H,cost):
    out={}
    for a in arcs: out.setdefault(a.tail,[]).append(a)
    ans=[]
    def dfs(u,val,path):
        if u[0]==H:
            ans.append((val,tuple(path),u)); return
        for a in out.get(u,[]): dfs(a.head,val+cost.get(a.arc_id,0.0),path+[a.arc_id])
    dfs(source,0.0,[])
    return sorted(ans,key=lambda z:(z[0],z[1],z[2][1]))

# Small variable-duration DAG with >8 paths.
S=(0,'A'); H=4; arcs=[]
def A(i,t,h):
    kind='STAY' if t[1]==h[1] and h[0]==t[0]+1 else 'MOVE'
    arcs.append(Arc(i,t,h,kind,slot=None if kind=='STAY' else len(arcs)))
A('a0',S,(1,'A')); A('a1',S,(1,'B')); A('a2',S,(2,'C'))
A('a3',(1,'A'),(2,'A')); A('a4',(1,'A'),(2,'B')); A('a5',(1,'B'),(2,'A')); A('a6',(1,'B'),(2,'B'))
for u in [(2,'A'),(2,'B'),(2,'C')]:
    A('x'+u[1]+'0',u,(3,'A')); A('x'+u[1]+'1',u,(3,'B'))
for u in [(3,'A'),(3,'B')]:
    A('y'+u[1]+'0',u,(4,'A')); A('y'+u[1]+'1',u,(4,'B'))

rng=random.Random(250613)
max_diff=0.0
for _ in range(250):
    c={a.arc_id:rng.uniform(-2,2) for a in arcs}
    b=brute(arcs,S,H,c)
    k=k_shortest_paths_dag(arcs,S,H,c,k=8)
    assert len(k)==min(8,len(b))
    for x,y in zip(k,b[:8]):
        max_diff=max(max_diff,abs(x[0]-y[0])); assert x[1:]==y[1:]
        assert abs(x[0]-y[0])<1e-12

assert rc_audit_pass(1.2187140804908386e-05,1e-4)
assert not rc_audit_pass(1.1e-4,1e-4)
lb,safe=guarded_full_lb(-2017.4052901958783,4,1e-4)
assert lb < -2017.4052901958783 and safe>0
assert abs(safe-(4e-4+max(1e-6,1e-9*2017.4052901958783)))<1e-12
# The guard can only weaken a minimization lower bound.
assert lb == -2017.4052901958783-safe

res={
 'status':'PASS','stage':'B6/7','revision':'R25M_B6R2_BATCH_PRICING_NUMERICAL_GUARD',
 'kbest_random_trials':250,'kbest_k':8,'max_cost_diff':max_diff,
 'observed_B6R1_rc_mismatch':1.2187140804908386e-05,'B6R2_rc_audit_tol':1e-4,
 'guarded_lower_bound_example':lb,'lower_bound_safety_example':safe,
 'batch_pricing_changes_feasible_set':False,'lower_bound_guard_can_only_weaken_certificate':True
}
print(json.dumps(res,indent=2))
