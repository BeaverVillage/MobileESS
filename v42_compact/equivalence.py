"""Bounded complete-option oracle, excluded from compact production imports."""
from dataclasses import replace
from collections import defaultdict
from time import perf_counter
import runpy
import numpy as np
import gurobipy as gp
from .common import *
from .graph import GraphFactory,old_to_compact,reconstruct
from .formulation import add_job,contributions,add_resources,intervention,values
from .native import completion_risk,grid
from v42_job_capability import build_domain,resources_used,resource_limit,validate
from v42_temporal.native import temporal_domain
from v42_final.reserve import bind_headroom,risk_exposure
from v42_temporal.service import bind_service

fixture=runpy.run_path(str(ROOT/'tests/test_v42_job_capability.py'))['fixture']

def model_for(jobs,bounds,r,graphs=None,domains=None):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=20260929
    use=defaultdict(gp.LinExpr);v={};metrics=[gp.LinExpr() for _ in range(3)];finishes=[]
    for uid,j in jobs.items():
        if graphs is not None:
            v[uid]=add_job(m,j,graphs[uid]);u=contributions(j,graphs[uid],v[uid])
            for key,x in u.items():use[key]+=x
            for a,x in zip(metrics,intervention(j,v[uid])):a+=x
            for family in ('f0','f1'):
                finishes += [(uid,k,t,x) for (k,t),x in v[uid][family].items()]
        else:
            z=[m.addVar(vtype=gp.GRB.BINARY) for o in domains[uid]];v[uid]=z
            m.addConstr(gp.quicksum(z)==1)
            for o,x in zip(domains[uid],z):
                for key,n in resources_used(j,o).items():use[key]+=n*x
                for a,n in zip(metrics,(int(o.migrated),o.start-j.reference_start,int(o.initial_site!=j.reference_site))):a+=n*x
                finishes.append((uid,o.segments[-1][0],o.segments[-1][2],x))
    add_resources(m,use,r);return m,v,use,metrics,finishes

def paths(j,b,r,old):
    g=GraphFactory(r,max(b.latest_completion,r.control_end)).graph(j,b)
    m,v,use,_,_=model_for({j.uid:j},{j.uid:b},r,graphs={j.uid:g})
    forward=[]
    # Fix every event/state to each old trajectory. This verifies actual model
    # rows, not just the mapping function.
    for index,o in enumerate(old):
        a=old_to_compact(o);temporary=[]
        for n,items in v[j.uid].items():
            for key,x in items.items():temporary.append(m.addConstr(gp.LinExpr(x)==a[n].get(key,0)))
        m.optimize();require(m.Status==gp.GRB.OPTIMAL,'OLD_TO_COMPACT_INFEASIBLE')
        recovered=reconstruct(j,b,r,g,values(v[j.uid]));require(recovered==o,'FORWARD_SIGNATURE')
        forward.append(dict(job=j.uid,option=index,migrated=o.migrated,start=o.start,checkpoint=o.checkpoint,transfer_start=o.transfer_start,PASS=True))
        m.remove(temporary);m.update()
    m.Params.PoolSearchMode=2;m.Params.PoolSolutions=max(100,len(old)*2+10);m.Params.PoolGap=0.;m.setObjective(0);m.optimize()
    require(m.Status in (gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE),'POOL_NOT_COMPLETE')
    found=set();reverse=[]
    for i in range(m.SolCount):
        m.Params.SolutionNumber=i
        a={n:{key:(x.Xn if isinstance(x,gp.Var) else x) for key,x in items.items()} for n,items in v[j.uid].items()}
        o=reconstruct(j,b,r,g,a);found.add(o)
        reverse.append(dict(job=j.uid,pool_solution=i,physical_valid=True,old_signature_exists=o in old,
            maximum_state_fractionality=max((abs(x-round(x)) for n in ('r0','h','r1') for x in a[n].values()),default=0.)))
    require(found==set(old),'COMPACT_PATH_SET_MISMATCH:'+j.uid+':'+str((len(old),len(found),len(found-set(old)),len(set(old)-found))))
    m.dispose();return forward,reverse,g

def objectives(m,jobs,r,use,metrics,finishes,bundle=None,raw=None,native_grid=False):
    known={(k,t):use['GPU',k,t]+r.fixed_gpu.get((k,t),0) for k in r.capacities for t in range(max(120,r.control_end))}
    risk=defaultdict(gp.LinExpr)
    for uid,k,t,x in finishes:
        co=completion_risk(jobs[uid],raw[uid],k,t,bundle) if bundle else risk_exposure(jobs[uid].gpu,t,k,[1,.5,.25],range(120))
        for key,n in co.items():risk[key]+=n*x
    if native_grid:
        primary,timing,_=grid(m,bundle,known,risk)
        return primary+[('CC4_reference_deviation',timing['deviation'])]+list(zip(('migration_count','shift_slots','prestart_changes'),metrics))
    # The same actual PR97 envelope/binder and reserve rows, with a small
    # explicitly synthetic cohort; not an asserted native electrical result.
    e=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv');kernel=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
    work=np.zeros(24);work[0]=1.
    timing=bind_service(m,work,kernel,e.Q10,e.Q90);anon={}
    for t in range(96):
        for k in r.capacities:anon[k,t]=m.addVar(lb=0)
        m.addConstr(gp.quicksum(anon[k,t] for k in r.capacities)==timing['gpu'][t])
    reserve=bind_headroom(m,known,anon,{},risk,r.capacities,range(96));rho=m.addVar(lb=0)
    for k in r.capacities:
        for t in range(96):m.addConstr(rho>=.5+.01*(known.get((k,t),0)+anon[k,t]))
    return [('rho',rho),('reserve_shortfall',reserve['runtime_shortfall']+reserve['CC4_shortfall']),('CC4_reference_deviation',timing['deviation'])]+list(zip(('migration_count','shift_slots','prestart_changes'),metrics))

def solve_levels(m,levels):
    m.Params.MIPGap=0;m.Params.TimeLimit=90
    result=[]
    for name,expr in levels:
        m.setObjective(expr);m.optimize()
        if m.Status==gp.GRB.INFEASIBLE:return dict(status='INFEASIBLE',objectives=None)
        require(m.Status==gp.GRB.OPTIMAL,'BOUNDED_EQUIVALENCE_SOLVE_NOT_OPTIMAL:'+str(m.Status))
        result.append(m.ObjVal);m.addConstr(expr<=m.ObjVal+(1e-7 if name=='rho' else 1e-8))
    return dict(status='OPTIMAL',objectives=result,max_violation=m.MaxVio)

def pair(jobs,bounds,r,domains,graphs,bundle=None,raw=None,native_grid=False):
    rows=[]
    for compact in (False,True):
        m,v,use,metrics,finishes=model_for(jobs,bounds,r,graphs=graphs if compact else None,domains=domains)
        levels=objectives(m,jobs,r,use,metrics,finishes,bundle,raw,native_grid)
        result=solve_levels(m,levels);result['binary_count']=m.NumBinVars
        if compact and m.SolCount:
            for uid,j in jobs.items():reconstruct(j,bounds[uid],r,graphs[uid],values(v[uid]))
        rows.append(result);m.dispose()
    require(rows[0]['status']==rows[1]['status'],'FEASIBILITY_EQUIVALENCE')
    if rows[0]['objectives'] is not None:require(np.allclose(rows[0]['objectives'],rows[1]['objectives'],atol=3e-6,rtol=1e-7),'SCIENTIFIC_OBJECTIVE_EQUIVALENCE:'+str(rows))
    return dict(PASS=True,old=rows[0],compact=rows[1],native_grid=native_grid,scientific_levels=['rho','reserve_shortfall','CC4_reference_deviation','migration_count','shift_slots','prestart_changes'])

def main():
    forward=[];reverse=[];synthetic=[]
    for case in 'ABCDEFGHIJ':
        j,b,r,_=fixture(case);old,_=build_domain(j,b,r);a,z,g=paths(j,b,r,old);forward+=a;reverse+=z
        synthetic.append(dict(case=case,**pair({j.uid:j},{j.uid:b},r,{j.uid:old},{j.uid:g})))
        print('synthetic',case,'PASS',flush=True)
    dump('SYNTHETIC_EQUIVALENCE.json',dict(PASS=True,cases=synthetic,scope='All A-J bounded fixtures; same PR97 service binder and full six scientific levels; synthetic affine grid'))
    from v42_boundary.boundaries import load_native
    bundle,jobs,bounds,seconds,r,raw=load_native();selected=[u for u in sorted(jobs) if jobs[u].service_slots<=3 and len(bounds[u].allowed_starts)==1][:2]
    factory=GraphFactory(r,max(b.latest_completion for b in bounds.values()));domains={};graphs={}
    for uid in selected:
        old,_=temporal_domain(jobs[uid],bounds[uid],r);a,z,g=paths(jobs[uid],bounds[uid],r,old);forward+=a;reverse+=z;domains[uid]=old;graphs[uid]=g
    result=pair({u:jobs[u] for u in selected},{u:bounds[u] for u in selected},r,domains,graphs,bundle,raw,True)
    dump('REAL_SUBSET_EQUIVALENCE.json',dict(PASS=True,selection='First two lexicographic real jobs with d<=3 and singleton start; complete untruncated domains, jointly optimized with full native grid and CC4',jobs=selected,result=result,
        limitation='Real subset covers short service/preplacement. TS/migration/RUNNING/carryout combinations covered by bounded synthetic fixtures, not claimed as diverse real subsets.'))
    csv('OLD_TO_COMPACT_MAPPING.csv',forward);csv('COMPACT_TO_PHYSICAL_VALIDATION.csv',reverse)
    dump('COMPACT_PATH_EQUIVALENCE_AUDIT.json',dict(PASS=True,old_options_tested=len(forward),old_to_compact_failures=0,compact_schedules_tested=len(reverse),compact_to_old_failures=0,
        reverse_method='Exhaustive bounded Gurobi solution pool, complete optimum status, event signatures compared to every old option',fractional_state_failures=0))
    print('All equivalence gates PASS',flush=True)

if __name__=='__main__':main()
