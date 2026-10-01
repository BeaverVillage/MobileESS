"""Exact two-time path support; diagnostic witnesses, never trajectory masters."""
from collections import defaultdict
import gurobipy as gp
from .common import *

def root_axis():
    if read(OUT/'ROOT_SOURCE_RECEIPT.json')['chosen']=='S3':return read(PRIOR/'ROOT_STATE_AXIS.json')
    axis=read(PRIOR/'ROOT_STATE_AXIS.json');_,_,_,sites,units,routes,_=inputs()
    with np.load(RELAX/'S2_ROOT_LP_SOLUTION.npz',allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    for u in units:
        for t in range(96):
            y={s:v.get(f'arc[{u},{sites.index(s)*96+t}]',0.) for s in sites}
            axis[f'{u}:{t}']['root']={**y,'TRANSIT':1-sum(y.values())}
    return axis

def paired_paths(arcs,sites,origin,t1,t2,first_states,H=96):
    bytime=defaultdict(list)
    for k,a in enumerate(arcs):bytime[a[1]].append(k)
    candidates={}
    for first in first_states:
        best={(origin,0):(0.,[])}
        for t in range(H):
            for k in bytime[t]:
                s,start,d,end,r=arcs[k]
                if (s,start) not in best:continue
                if start<=t1<end and (s if r is None else 'TRANSIT')!=first:continue
                cost,path=best[s,start];newcost=cost+(r.energy_kwh if r else 0.);newpath=path+[k];node=d,end
                if node not in best or newcost<best[node][0]:best[node]=newcost,newpath
                if start<=t2<end:
                    second=s if r is None else 'TRANSIT';key=first,second
                    if key not in candidates or newcost<candidates[key][0]:candidates[key]=(newcost,newpath+[sites.index(d)*H+j for j in range(end,H)])
    return candidates

def all_pairs():
    _,_,_,sites,initial,routes,b=inputs();arcs=arcs_for(sites,routes);axis=root_axis();bytime=defaultdict(list)
    for k,a in enumerate(arcs):bytime[a[1]].append(k)
    records=[];witnesses={};feas=[]
    for u,origin in sorted(initial.items()):
        for t1,t2 in TIME_PAIRS:
            candidates=paired_paths(arcs,sites,origin,t1,t2,axis[f'{u}:{t1}']['states'])
            for (a,z),(energy,path) in sorted(candidates.items()):
                assert energy<=min(b.initial-b.minimum,b.maximum-b.initial)+TOL
                records.append(dict(MESS=u,time1=t1,time2=t2,state_a=a,state_b=z,reachable=True,minimum_witness_travel_energy=energy))
                witnesses[f'{u}:{t1}:{t2}:{a}:{z}']=dict(path=path,travel_energy=energy)
            aa=axis[f'{u}:{t1}'];bb=axis[f'{u}:{t2}'];m=gp.Model();m.Params.OutputFlag=0;m.Params.Method=2;m.Params.Threads=1
            w=m.addVars(list(candidates),lb=0)
            for a in aa['states']:m.addConstr(gp.quicksum(w[x,z] for x,z in candidates if x==a)==aa['root'][a])
            for z in bb['states']:m.addConstr(gp.quicksum(w[x,y] for x,y in candidates if y==z)==bb['root'][z])
            m.setObjective(0);m.optimize();assert m.Status==gp.GRB.OPTIMAL and m.MaxVio<=TOL,(u,t1,t2,m.Status)
            feas.append(dict(MESS=u,time1=t1,time2=t2,support_pairs=len(candidates),status=int(m.Status),representable=True,max_marginal_residual=m.MaxVio,
                CROSS_TIME_MARGINAL_HULL_VIOLATION=False,raw_marginals_used=True))
            m.dispose();print('EXACT REACH & ROOT HULL',u,t1,t2,len(candidates),'PASS',flush=True)
    table('G3_REACHABLE_STATE_PAIRS.csv',records);table('G3_ROOT_MARGINAL_FEASIBILITY.csv',feas)
    (OUT/'G3_ROUTE_WITNESSES.json.gz').write_bytes(gzip.compress(json.dumps(witnesses).encode(),mtime=0))
    dump('ROUTE_FLOW_INTEGRALITY_DIAGNOSIS.json',dict(PASS=True,support_pairs=len(records),marginal_tests=len(feas),marginal_hull_violation_count=0,
        ROUTE_FLOW_PAIR_PROJECTION_ALREADY_IMPLIED=True,
        proof='Each unit has a directed acyclic time-expanded single-commodity network with integer unit supply. Its node-arc incidence is totally unimodular; nonnegative unit flows decompose into source-terminal paths. Time-cut states are linear arc sums, so path decomposition induces a supported two-time joint distribution with exactly these marginals. No route-flow polytope weakness follows from fractional marginals. This statement concerns pure route flow, not the joint grid/SOC/PQ MILP relaxation.',
        exact_support='For every authority-reachable first state, forward DAG dynamic programming restricts every crossing arc at t1 to that state and records all crossing states at t2. Prefixes extend by original stay arcs to the terminal. This enumerates existence, independent of root values.',
        no_trajectory_master=True,no_domain_changed=True))
if __name__=='__main__':all_pairs()
