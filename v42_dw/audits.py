"""Exhaustive oracles ONLY for bounded gates. Not imported by May worker."""
from collections import defaultdict,Counter
from dataclasses import replace
from time import perf_counter
import numpy as np
import gurobipy as gp
from .common import *
from .column import ColumnFactory, METRICS
from .pricing import price,initial_columns
from .master import Master
from .cg import generate
from v42_compact.graph import GraphFactory,reconstruct
from v42_compact.equivalence import fixture,model_for,objectives,solve_levels
from v42_compact.formulation import values
from v42_temporal.native import temporal_domain
from v42_job_capability import build_domain,validate,resources_used
from v42_final.reserve import bind_headroom
from v42_temporal.service import bind_service

def make_factory(jobs,bounds,r,bundle=None,raw=None):
    graphs=GraphFactory(r,max(b.latest_completion for b in bounds.values()))
    return ColumnFactory(jobs,bounds,r,{u:graphs.graph(j,bounds[u]) for u,j in jobs.items()},bundle,raw)

def synthetic_binder(r):
    def bind(m,known,risk):
        import pandas as pd
        e=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv');kernel=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
        work=np.zeros(24);work[0]=1.
        timing=bind_service(m,work,kernel,e.Q10,e.Q90);anon={}
        for t in range(96):
            for k in r.capacities:anon[k,t]=m.addVar(lb=0)
            m.addConstr(gp.quicksum(anon[k,t] for k in r.capacities)==timing['gpu'][t])
        reserve=bind_headroom(m,known,anon,{},risk,r.capacities,range(96));rho=m.addVar(lb=0)
        for k in r.capacities:
            for t in range(96):m.addConstr(rho>=.5+.01*(known.get((k,t),0)+anon[k,t]))
        return [('rho',rho),('reserve_shortfall',reserve['runtime_shortfall']+reserve['CC4_shortfall']),('CC4_reference_deviation',timing['deviation'])]
    return bind

def pricing_audit(factory,uid,old,vectors=32):
    require(old,'EMPTY_EXHAUSTIVE_TEST_DOMAIN')
    columns=[factory.make(uid,o) for o in old];keys=sorted(set().union(*(c.master_coefficients() for c in columns)))
    rng=np.random.default_rng(20260930);rows=[]
    for index in range(vectors):
        dual={k:float(x) for k,x in zip(keys,rng.uniform(-2.,2.,len(keys)))}
        if index==0:dual={}
        c,rc,profile=price(factory,uid,dual)
        expected=min(x.reduced_cost(dual) for x in columns)
        require(c.option in old,'PRICING_PATH_NOT_OLD_PHYSICAL')
        require(abs(rc-expected)<=1e-7*max(1.,abs(expected)),'EXHAUSTIVE_PRICING_MISMATCH')
        repeated,rc2,_=price(factory,uid,dual)
        require(c.signature==repeated.signature and rc==rc2,'NONDETERMINISTIC_PRICING')
        rows.append(dict(vector=index,expected=expected,observed=rc,error=abs(rc-expected),signature=c.signature,**profile))
    return dict(job_id=uid,old_options=len(old),vectors=vectors,PASS=True,coverage=sorted(set(o.action(factory.jobs[uid]) for o in old)),
        delayed_WAN=any(o.migrated and o.transfer_start>o.checkpoint for o in old),carryout=any(o.segments[-1][2]>factory.r.control_end for o in old),rows=rows)

def reduced_cost_audit(master,c):
    m=master.m;m.update();require(m.Status==gp.GRB.OPTIMAL,'RC_AUDIT_MASTER_NOT_OPTIMAL')
    original=master.duals();manual=c.reduced_cost(original)
    clone=m.copy();clone.Params.OutputFlag=0;clone.Params.Presolve=0;clone.Params.Method=1
    rows=clone.getConstrs();co=c.master_coefficients()
    v=clone.addVar(lb=0,ub=0,column=gp.Column(list(co.values()),[rows[master.rows[k].index] for k in co]),name='RC_AUDIT_COLUMN')
    clone.update()
    # Supply the optimal old basis with the new fixed column nonbasic.
    clone.setAttr('VBasis',clone.getVars(),m.getAttr('VBasis')+[-1])
    clone.setAttr('CBasis',rows,m.getAttr('CBasis'));clone.optimize()
    require(clone.Status==gp.GRB.OPTIMAL,'RC_CLONE_NOT_OPTIMAL')
    reported=v.RC;newdual={k:rows[row.index].Pi for k,row in master.rows.items()}
    clone_manual=c.reduced_cost(newdual)
    require(abs(clone_manual-reported)<=1e-7*max(1.,abs(reported)),'MANUAL_RC_GUROBI_MISMATCH')
    require(abs(manual-reported)<=1e-7*max(1.,abs(reported)),'RC_ORIGINAL_DUAL_BASIS_DRIFT')
    result=dict(PASS=True,manual_RC=manual,Gurobi_RC=reported,clone_manual_RC=clone_manual,
        max_dual_drift=max((abs(original[k]-newdual[k]) for k in original),default=0.),
        coefficient_count=len(co),active_locks=len(master.locks),method='Optimal old basis + fixed nonbasic new column, dual simplex, presolve disabled')
    clone.dispose();return result

def compare_masters(factory,domains,native=False):
    initial,fixed,_=initial_columns(factory);binder=None if native else synthetic_binder(factory.r)
    # Full column LP benchmark: retain the same continuous global model.
    full=Master(factory,initial,fixed,binder,phase1=False)
    for uid,old in domains.items():
        if not factory.graphs[uid].fixed:
            for o in old:full.add(factory.make(uid,o))
    full_result=solve_levels(full.m,full.levels[:-1]);full_size=full.size();full.dispose()
    cg=Master(factory,initial,fixed,binder);sign=[]
    def check_rc():
        uid=next((u for u,g in factory.graphs.items() if not g.fixed),None)
        if uid is not None:
            old=next((o for o in domains[uid] if o.migrated),domains[uid][-1])
            sign.append(reduced_cost_audit(cg,factory.make(uid,old)))
    result=generate(cg,solve_audit=check_rc,include_tie=False)
    observed=[x['value'] for x in result['levels'] if x['level']!='PHASE_I']
    if full_result['status']=='INFEASIBLE':require(result['infeasible'],'PHASE1_INFEASIBILITY_MISMATCH')
    else:
        require(result['converged'] and result['phase1_zero'],'CG_NOT_CONVERGED')
        require(np.allclose(observed,full_result['objectives'],atol=3e-6,rtol=1e-7),'FULL_COLUMN_LP_MISMATCH')
    repeat=None
    if not native:
        other=Master(factory,initial,fixed,binder)
        repeat=generate(other,include_tie=False)
        require([c.signature for c in cg.columns.values()]==[c.signature for c in other.columns.values()],'CG_COLUMN_ORDER_NONDETERMINISTIC')
        require([(x['level'],x['value']) for x in result['levels']]==[(x['level'],x['value']) for x in repeat['levels']],'CG_REPEAT_OBJECTIVES')
        other.dispose()
    lp=dict(PASS=True,full_column=full_result,CG=dict(levels=result['levels'],iterations=len(result['iterations']),phase1_zero=result['phase1_zero'],infeasible=result['infeasible']),
        full_size=full_size,CG_size=cg.size(),native_grid=native,deterministic_repeat=repeat is not None)
    cg.dispose()
    binary=Master(factory,initial,fixed,binder,phase1=False)
    for uid,old in domains.items():
        if not factory.graphs[uid].fixed:
            for o in old:binary.add(factory.make(uid,o))
    binary.m.update()
    for v in binary.variables.values():v.VType=gp.GRB.BINARY
    binary_result=solve_levels(binary.m,binary.levels[:-1])
    if binary.m.SolCount:
        for s,v in binary.variables.items():
            if v.X>.5:validate(factory.jobs[binary.columns[s].job_id],binary.columns[s].option,factory.bounds[binary.columns[s].job_id],factory.r)
    binary.dispose()
    compact,v,use,metrics,finishes=model_for(factory.jobs,factory.bounds,factory.r,graphs=factory.graphs)
    levels=objectives(compact,factory.jobs,factory.r,use,metrics,finishes,factory.bundle,factory.raw,native)
    compact_result=solve_levels(compact,levels)
    if compact.SolCount:
        for uid,j in factory.jobs.items():reconstruct(j,factory.bounds[uid],factory.r,factory.graphs[uid],values(v[uid]))
    compact.dispose()
    require(binary_result['status']==compact_result['status'],'INTEGER_FEASIBILITY_MISMATCH')
    if binary_result['objectives'] is not None:require(np.allclose(binary_result['objectives'],compact_result['objectives'],atol=3e-6,rtol=1e-7),'INTEGER_OBJECTIVE_MISMATCH:'+str((binary_result,compact_result)))
    return lp,dict(PASS=True,binary_full_column=binary_result,compact=compact_result,native_grid=native),sign

def main():
    require((OUT/'PREREGISTRATION.json').exists(),'NO_PREREGISTRATION')
    synthetic=[];lp=[];integer=[];sign=[]
    for case in 'ABCDEFGHIJ':
        j,b,r,_=fixture(case);old,_=build_domain(j,b,r);f=make_factory({j.uid:j},{j.uid:b},r)
        if not f.graphs[j.uid].fixed:synthetic.append(dict(case=case,**pricing_audit(f,j.uid,old)))
        else:require(len(old)==1 and f.make(j.uid,old[0]).option==f.graphs[j.uid].fixed,'FIXED_COLUMN_EQUIVALENCE');synthetic.append(dict(case=case,PASS=True,old_options=1,vectors=0,scope='constant'))
        a,z,s=compare_masters(f,{j.uid:old});lp.append(dict(case=case,**a));integer.append(dict(case=case,**z));sign+=s
        print('synthetic',case,'PASS',flush=True)
    dump('PRICING_EXHAUSTIVE_SYNTHETIC_AUDIT.json',dict(PASS=True,cases=synthetic))
    from v42_boundary.boundaries import load_native
    bundle,jobs,bounds,seconds,r,raw=load_native()
    selected=[u for u in sorted(jobs) if jobs[u].service_slots<=3 and len(bounds[u].allowed_starts)==1][:2]
    domains={u:temporal_domain(jobs[u],bounds[u],r)[0] for u in selected}
    # The bounded compact benchmark includes only selected jobs' risk. Do not
    # misclassify omitted active jobs as Q50-expired fixed-risk population.
    f=make_factory({u:jobs[u] for u in selected},{u:bounds[u] for u in selected},r,bundle,{u:raw[u] for u in selected})
    real=[pricing_audit(f,u,domains[u],16) for u in selected]
    # Diverse bounded real physics: two authorized sites, two authorized starts;
    # retain *all* checkpoint/WAN times and the original full completion tail.
    more=[]
    for pred in (lambda u:jobs[u].state=='PENDING' and len(bounds[u].allowed_starts)>1 and jobs[u].service_slots<=3,
                 lambda u:jobs[u].state=='RUNNING' and jobs[u].service_slots>120):
        uid=next(u for u in sorted(jobs) if pred(u));j=jobs[uid]
        sites=tuple(dict.fromkeys((j.reference_site,)+tuple(s for s in j.initial_sites if s!=j.reference_site)))[:2]
        j=replace(j,initial_sites=sites);b=replace(bounds[uid],allowed_starts=tuple(bounds[uid].allowed_starts)[:2])
        old,_=temporal_domain(j,b,r);sub=make_factory({uid:j},{uid:b},r,bundle,raw)
        more.append(dict(bounded_sites=sites,bounded_starts=b.allowed_starts,latest_completion=b.latest_completion,**pricing_audit(sub,uid,old,16)))
        print('real pricing',uid,len(old),'PASS',flush=True)
    a,z,s=compare_masters(f,domains,native=True);lp.append(dict(case='real_native_pair',**a));integer.append(dict(case='real_native_pair',**z));sign+=s
    dump('PRICING_REAL_SUBSET_AUDIT.json',dict(PASS=True,unmodified_short_jobs=real,bounded_diverse_jobs=more,limitation='Two-site/two-start bounded diverse fixtures; original WAN horizon and full tail retained. Production May uses all authorized sites/starts.'))
    require(sign and any(x['active_locks']>=4 for x in sign),'MISSING_LOCK_RC_AUDIT')
    dump('REDUCED_COST_SIGN_AUDIT.json',dict(PASS=True,rows=sign,all_coupling_families=['GPU','WAN','ACTIVE','RISK','CONVEXITY','METRIC'],locks='Column coefficients in locks zero by construction; metric-balance dual includes lock values.'))
    dump('FULL_COLUMN_MASTER_EQUIVALENCE.json',dict(PASS=True,cases=lp,benchmark='All complete physical columns, not naive compact LP'))
    dump('SMALL_INTEGER_EQUIVALENCE.json',dict(PASS=True,cases=integer,full_May_integer_optimality=False))
    print('All decomposition gates PASS',flush=True)

if __name__=='__main__':main()
