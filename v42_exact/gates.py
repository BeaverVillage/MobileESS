from collections import defaultdict
from dataclasses import replace
from itertools import product
from time import perf_counter
import runpy
import numpy as np
import gurobipy as gp
from .common import *
from .support import ExactFactory
from . import factor
from v42_job_capability import build_domain,resources_used,resource_limit
from v42_compact.formulation import add_job,contributions,add_resources,intervention,values
from v42_compact.graph import old_to_compact,reconstruct
from v42_compact.equivalence import objectives,solve_levels

fixture=runpy.run_path(str(ROOT/'tests/test_v42_job_capability.py'))['fixture']
FACTOR_SOURCE_SHA=sha(ROOT/'v42_exact/factor.py')

def model(jobs,bounds,r,graphs,factored):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=20260929
    # Bounded equivalence certificates use stricter numerical LP/integer
    # tolerances than the frozen production solver. Small normalized CC4
    # objective coefficients otherwise permit default dual-tolerance drift.
    m.Params.OptimalityTol=1e-9;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    use=defaultdict(gp.LinExpr);v={};metrics=[gp.LinExpr() for _ in range(3)];finishes=[]
    for uid,j in jobs.items():
        g=graphs[uid];v[uid]=factor.add_job(m,j,g,r) if factored else add_job(m,j,g)
        u=factor.contributions(j,g,v[uid]) if factored else contributions(j,g,v[uid])
        for key,x in u.items():use[key]+=x
        for a,x in zip(metrics,intervention(j,v[uid])):a+=x
        for n in ('f0','f1'):finishes.extend((uid,k,t,x) for (k,t),x in v[uid][n].items())
    add_resources(m,use,r);return m,v,use,metrics,finishes

def paths(label,jobs,bounds,r):
    factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()))
    graphs={u:factory.graph(j,bounds[u]) for u,j in jobs.items()};domains={u:build_domain(j,bounds[u],r)[0] for u,j in jobs.items()}
    expected=set()
    for options in product(*(domains[u] for u in jobs)):
        use=defaultdict(float)
        for j,o in zip(jobs.values(),options):
            for key,n in resources_used(j,o).items():use[key]+=n
        if all(n<=resource_limit(key,r)+1e-9 for key,n in use.items()):expected.add(options)
    records=[];fw=[];rv=[]
    for kind in ('F1','F2'):
        m,v,use,metrics,finishes=model(jobs,bounds,r,graphs,kind=='F2');m.Params.TimeLimit=90
        for i,options in enumerate(sorted(expected)):
            temporary=[]
            for (u,j),o in zip(jobs.items(),options):
                a=factor.mapping(j,graphs[u],r,o) if kind=='F2' else old_to_compact(o)
                for n,items in v[u].items():
                    for key,x in items.items():temporary.append(m.addConstr(gp.LinExpr(x)==a.get(n,{}).get(key,0)))
            m.optimize()
            if m.Status!=gp.GRB.OPTIMAL:raise ValueError('OLD_TO_NEW_INFEASIBLE:'+label+':'+kind+':'+str(i))
            got=tuple((factor.reconstruct(j,bounds[u],r,graphs[u],values(v[u])) if kind=='F2' else reconstruct(j,bounds[u],r,graphs[u],values(v[u]))) for u,j in jobs.items())
            if got!=options:raise ValueError('FORWARD_SIGNATURE')
            fw.append(dict(case=label,formulation=kind,assignment=i,jobs=len(jobs),PASS=True));m.remove(temporary);m.update()
        m.Params.PoolSearchMode=2;m.Params.PoolSolutions=max(100,len(expected)*3+10);m.Params.PoolGap=0;m.setObjective(0);m.optimize()
        if m.Status not in (gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE):raise ValueError('POOL_INCOMPLETE:'+label+':'+kind)
        found=set()
        for i in range(m.SolCount):
            m.Params.SolutionNumber=i
            a={u:{n:{key:(x.Xn if isinstance(x,gp.Var) else x) for key,x in items.items()} for n,items in vv.items()} for u,vv in v.items()}
            got=tuple((factor.reconstruct(j,bounds[u],r,graphs[u],a[u]) if kind=='F2' else reconstruct(j,bounds[u],r,graphs[u],a[u])) for u,j in jobs.items())
            found.add(got);rv.append(dict(case=label,formulation=kind,assignment=i,jobs=len(jobs),PASS=got in expected))
        if found!=expected:raise ValueError('PHYSICAL_SET_MISMATCH:'+label+':'+kind+':'+str((len(expected),len(found))))
        records.append(dict(formulation=kind,old_physical_paths=len(expected),new_integral_paths=m.SolCount,distinct_physical_paths=len(found),PASS=True))
        m.dispose()
    return records,fw,rv

def scientific(jobs,bounds,r,bundle=None,raw=None,native_grid=False):
    factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()));old={u:factory.original.graph(j,bounds[u]) for u,j in jobs.items()};graphs={u:factory.graph(j,bounds[u]) for u,j in jobs.items()}
    result=[]
    for kind in ('F0','F1','F2'):
        m,v,use,metrics,finishes=model(jobs,bounds,r,old if kind=='F0' else graphs,kind=='F2')
        levels=objectives(m,jobs,r,use,metrics,finishes,bundle,raw,native_grid);row=solve_levels(m,levels);row['formulation']=kind
        if m.SolCount:
            for u,j in jobs.items():
                if kind=='F2':factor.reconstruct(j,bounds[u],r,graphs[u],values(v[u]))
                else:reconstruct(j,bounds[u],r,(old if kind=='F0' else graphs)[u],values(v[u]))
        result.append(row);m.dispose()
    if len({x['status'] for x in result})!=1:raise ValueError('SCIENTIFIC_FEASIBILITY')
    if result[0]['objectives'] is not None:
        for x in result[1:]:
            if not np.allclose(result[0]['objectives'],x['objectives'],atol=3e-6,rtol=1e-7):raise ValueError('SCIENTIFIC_VALUES:'+str(result))
    return dict(PASS=True,results=result,native_grid=native_grid)

def adversarial():
    j,b,r,_=fixture('F');j=replace(j,service_slots=4);b=replace(b,allowed_starts=(0,),latest_completion=14)
    cases=[]
    def push(n,rr=r,jj=j,bb=b,joint=False):
        jobs={jj.uid:jj};bounds={jj.uid:bb}
        if joint:jobs['SECOND']=replace(jj,uid='SECOND');bounds['SECOND']=bb
        cases.append((n,jobs,bounds,rr))
    push('single_slot');push('zero_rate',replace(r,wan_capacities={('AB',t):0 if t==2 else 200 for t in range(12)}))
    push('multiple_zero',replace(r,wan_capacities={('AB',t):0 if t in (2,3,4) else 200 for t in range(12)}))
    push('final_partial',replace(r,wan_capacities={('AB',t):200 for t in range(12)}))
    rr=replace(r,capacities={'A':8,'B':8,'C':8},rack_limits={'A':(8,),'B':(8,),'C':(8,)},
        paths={('A','B'):('L1',),('A','C'):('L1','L2'),('B','A'):('L1',),('B','C'):('L2',),('C','A'):('L1','L2'),('C','B'):('L2',)},
        wan_capacities={(l,t):200 if l=='L1' else 120 for l in ('L1','L2') for t in range(12)})
    jj=replace(j,initial_sites=('A','B','C'))
    push('two_destinations',rr,jj);push('different_bottlenecks',rr,jj);push('same_path_different_start')
    push('checkpoint_equal_start',jj=replace(j,state='RUNNING',elapsed_seconds=1800));push('long_checkpoint_wait')
    push('restart_near_horizon',replace(r,wan_capacities={('AB',t):0 if t<6 else 200 for t in range(12)}))
    push('post_H',jj=replace(j,service_slots=11),bb=replace(b,latest_completion=20))
    push('fixed_WAN',replace(r,fixed_wan={('AB',2):100}));push('fixed_active',replace(r,fixed_transfers={2:r.max_active_transfers}))
    push('two_jobs_same_link',replace(r,wan_capacities={('AB',t):400 for t in range(12)}),joint=True)
    # Keep initial source fixed via RUNNING to limit joint exhaustive products;
    # both jobs still choose any destination in the full synthetic authority.
    jr=replace(jj,state='RUNNING',elapsed_seconds=0)
    push('two_paths_shared_link',rr,jr,joint=True)
    disjoint=replace(rr,paths={('A','B'):('L1',),('A','C'):('L2',),('B','A'):('L1',),('C','A'):('L2',)})
    push('two_disjoint_paths',disjoint,jr,joint=True)
    return cases

def main():
    fw=[];rv=[];synthetic=[];adv=[]
    for case in 'ABCDEFGHIJ':
        j,b,r,_=fixture(case);records,a,z=paths(case,{j.uid:j},{j.uid:b},r);fw+=a;rv+=z
        synthetic.append(dict(case=case,paths=records,scientific=scientific({j.uid:j},{j.uid:b},r)));print('A-J',case,'PASS',flush=True)
    dump('SYNTHETIC_EXHAUSTIVE_EQUIVALENCE.json',dict(PASS=True,cases=synthetic,factor_source_sha256=FACTOR_SOURCE_SHA))
    for label,jobs,bounds,r in adversarial():
        records,a,z=paths(label,jobs,bounds,r);fw+=a;rv+=z;adv.append(dict(case=label,paths=records,scientific=scientific(jobs,bounds,r)))
        print('adversarial',label,'PASS',flush=True)
    dump('ADVERSARIAL_WAN_TESTS.json',dict(PASS=True,cases=adv,factor_source_sha256=FACTOR_SOURCE_SHA))
    table('OLD_TO_FACTORIZED_MAPPING.csv',fw);table('FACTORIZED_TO_OLD_VALIDATION.csv',rv)
    dump('WAN_TEMPLATE_EQUIVALENCE.json',dict(PASS=True,method='Exact fixed assignments and exhaustive complete Gurobi integer solution pool; all bounded old physical Options, individual and competing-job fixtures',
        factor_source_sha256=FACTOR_SOURCE_SHA,
        old_to_new=len(fw),new_to_old=len(rv),zero_failure=True,profiles=['bytes_per_link_slot','active_slots','end','restart','remaining_payload'],
        limitation='Standalone all pair/start feasible and infeasible contracts are tested separately in pytest. These records include complete job path feasibility.'))
    print('bounded gates PASS',flush=True)

if __name__=='__main__':main()
