"""Exhaustive bounded physical sets and all six scientific optima."""
from collections import defaultdict,Counter
from dataclasses import replace,asdict
from itertools import product
from time import perf_counter
import gurobipy as gp,numpy as np
from .common import *
from .data import scientific_signature
from .native import local_units,reconstruct
from . import factor
from v42_exact.gates import fixture,adversarial
from v42_exact.support import ExactFactory
from v42_exact.factor import add_job as original_job,mapping
from v42_compact.formulation import add_resources,intervention
from v42_compact.equivalence import objectives,solve_levels
from v42_job_capability import build_domain,resources_used,resource_limit

def classes_for(jobs,bounds,r,raw=None,bundle=None,costs=None):
    result=defaultdict(list);identity=hashlib.sha256(repr(asdict(r)).encode()).hexdigest()
    bundle=bundle or dict(runtime_reserve_gamma=1,runtime_survival_kernel=[1,.5,.25])
    for u,j in sorted(jobs.items()):
        row=(raw or {}).get(u,dict(risk_nominal_completion_issue_slot=0,reference_end=0))
        result[digest(scientific_signature(j,bounds[u],identity,row,bundle,(costs or {}).get(u)))].append(u)
    return dict(result)

def model(jobs,bounds,r,kind,bundle=None,raw=None,native_grid=False):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=20260929
    m.Params.OptimalityTol=1e-9;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9;m.Params.TimeLimit=90
    f=ExactFactory(r,max(b.latest_completion for b in bounds.values()));graphs={u:f.graph(j,bounds[u]) for u,j in jobs.items()}
    classes=classes_for(jobs,bounds,r,raw,bundle)
    if kind=='F2':units=[dict(id=u,uid=u,members=[u],v=original_job(m,j,graphs[u],r),optional=False,stay_count=False) for u,j in sorted(jobs.items())]
    else:units=local_units(m,jobs,bounds,r,graphs,classes,kind)
    use=defaultdict(gp.LinExpr);metrics=[gp.LinExpr() for _ in range(3)];finishes=[]
    for unit in units:
        u=unit['uid'];j=jobs[u];v=unit['v']
        for key,x in factor.contributions(j,graphs[u],v).items():use[key]+=x
        for a,x in zip(metrics,intervention(j,v)):a+=x
        for n in ('f0','f1'):finishes.extend((u,k,t,x) for (k,t),x in v[n].items())
    add_resources(m,use,r)
    data=(bundle,jobs,bounds,r,raw,graphs,graphs,dict(classes=classes))
    return m,units,data,use,metrics,finishes

def canonical(plans,jobs,classes):
    out=dict(zip(jobs,plans))
    for us in classes.values():
        for u,o in zip(sorted(us),sorted(out[u] for u in us)):out[u]=o
    return tuple(out[u] for u in sorted(jobs))

def fixed_assignment(unit,options,jobs,data):
    bundle,js,bounds,r,raw,graphs,old,prep=data;uid=unit['uid'];j=jobs[uid];g=graphs[uid]
    if unit['stay_count']:
        selected=[options[u] for u in unit['members'] if not options[u].migrated];a={n:{} for n in unit['v']}
        for o in selected:
            a['y'][o.initial_site,o.start]=a['y'].get((o.initial_site,o.start),0)+1
            a['f0'][o.initial_site,o.start+j.service_slots]=a['f0'].get((o.initial_site,o.start+j.service_slots),0)+1
            for k,t0,t1 in o.segments:
                for t in range(t0,t1):a['r0'][k,t]=a['r0'].get((k,t),0)+1
        return a
    if unit['optional']:
        selected=sorted(options[u] for u in unit['members'] if options[u].migrated);lane=int(unit['id'].split('_LANE_')[-1])
        if lane>=len(selected):return {n:{} for n in unit['v']}
        return mapping(j,g,r,selected[lane])
    return mapping(j,g,r,options[uid])

def physical_sets(label,jobs,bounds,r,kinds=('F2A','F2B','F2C')):
    domains={u:build_domain(j,bounds[u],r)[0] for u,j in sorted(jobs.items())};us=sorted(jobs);classes=classes_for(jobs,bounds,r);expected=set();original=[]
    for plans in product(*(domains[u] for u in us)):
        used=defaultdict(float)
        for u,o in zip(us,plans):
            for key,n in resources_used(jobs[u],o).items():used[key]+=n
        if all(n<=resource_limit(k,r)+1e-9 for k,n in used.items()):
            original.append(plans);expected.add(canonical(plans,us,classes))
    records=[];decompositions=[]
    for kind in kinds:
        m,units,data,use,metrics,finishes=model(jobs,bounds,r,kind)
        # Forward test EVERY original individual assignment, including UID permutations.
        for index,plans in enumerate(original):
            options=dict(zip(us,plans));temporary=[]
            for unit in units:
                a=fixed_assignment(unit,options,jobs,data)
                for name,items in unit['v'].items():
                    for key,x in items.items():temporary.append(m.addConstr(gp.LinExpr(x)==a.get(name,{}).get(key,0)))
            m.optimize()
            if m.Status!=gp.GRB.OPTIMAL:raise ValueError('FORWARD:'+label+':'+kind+':'+str(index))
            recovered=reconstruct(units,data)
            expected_plan=canonical(plans,us,classes) if kind in ('F2B','F2C') else plans
            if tuple(recovered[u] for u in us)!=tuple(asdict(o) for o in expected_plan):raise ValueError('FORWARD_DECOMPOSITION')
            if reconstruct(units,data)!=recovered:raise ValueError('NONDETERMINISTIC_DECOMPOSITION')
            m.remove(temporary);m.update()
        m.setObjective(0);m.Params.PoolSearchMode=2;m.Params.PoolGap=0;m.Params.PoolSolutions=max(100,len(original)*8+20);m.optimize()
        if m.Status not in (gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE):raise ValueError('INCOMPLETE_REVERSE_POOL:'+label+':'+kind)
        found=set()
        from v42_job_capability import Option
        for index in range(m.SolCount):
            m.Params.SolutionNumber=index;recovered=reconstruct(units,data,pool=True)
            def option(value):
                d=dict(value);d['segments']=tuple(tuple(x) for x in d['segments']);d['wan']=tuple(tuple(x) for x in d['wan']);return Option(**d)
            plans=tuple(option(recovered[u]) for u in us);sig=canonical(plans,us,classes)
            if sig not in expected:raise ValueError('FACTORIZED_ONLY_PHYSICAL_PATH')
            found.add(sig);decompositions.append(dict(case=label,formulation=kind,pool=index,individual_jobs=len(jobs),PASS=True,deterministic=True))
        if found!=expected:raise ValueError('PHYSICAL_SET:'+label+':'+kind+':'+str((len(found),len(expected))))
        records.append(dict(formulation=kind,original_individual_paths=len(original),canonical_physical_sets=len(expected),reverse_pool_paths=m.SolCount,PASS=True));m.dispose()
    return records,decompositions

def scientific(label,jobs,bounds,r,bundle=None,raw=None,native_grid=False):
    rows=[]
    for kind in ('F2','F2A','F2B','F2C'):
        m,units,data,use,metrics,finishes=model(jobs,bounds,r,kind,bundle,raw,native_grid)
        levels=objectives(m,jobs,r,use,metrics,finishes,bundle,raw,native_grid);row=solve_levels(m,levels);row['formulation']=kind
        if row['status']=='OPTIMAL':reconstruct(units,data)
        rows.append(row);m.dispose()
    if len({row['status'] for row in rows})!=1:raise ValueError('SCIENTIFIC_STATUS:'+label+str(rows))
    if rows[0]['objectives'] is not None and any(not np.allclose(rows[0]['objectives'],row['objectives'],atol=3e-6,rtol=1e-7) for row in rows[1:]):raise ValueError('SCIENTIFIC_VALUES:'+label+str(rows))
    return dict(PASS=True,case=label,rows=rows,native_grid=native_grid)

def fixtures():
    cases=[]
    for label in 'ABCDEFGHIJ':
        j,b,r,_=fixture(label);cases.append((label,{j.uid:j},{j.uid:b},r))
    cases.extend(adversarial())
    for label,base in [('two_identical_STAY','C'),('two_identical_TS','B'),('two_identical_migration','F'),('shared_GPU','D'),('shared_WAN','F'),('same_destination','F'),('different_UID','D'),('two_paths_decomposition','F')]:
        j,b,r,_=fixture(base);j=replace(j,service_slots=4);b=replace(b,allowed_starts=(0,1) if base in ('B','D') else (0,),latest_completion=14)
        jobs={j.uid:j,'UID_Z':replace(j,uid='UID_Z')};bounds={u:b for u in jobs};cases.append((label,jobs,bounds,r))
    j,b,r,_=fixture('D');j=replace(j,service_slots=2);b=replace(b,allowed_starts=(0,2,4),latest_completion=12)
    jobs={str(i):replace(j,uid=str(i)) for i in range(3)};cases.append(('multiple_start_count_paths',jobs,{u:b for u in jobs},r))
    return cases

def main():
    result=[];validation=[];started=perf_counter()
    for label,jobs,bounds,r in fixtures():
        sets,rows=physical_sets(label,jobs,bounds,r);sci=scientific(label,jobs,bounds,r);result.append(dict(case=label,physical=sets,scientific=sci));validation+=rows
        print('bounded',label,'PASS',flush=True)
    source={'v42_root/'+name:sha(ROOT/'v42_root'/name) for name in ('common.py','data.py','factor.py','native.py','eliminate.py','gates.py')}
    dump('SCIENTIFIC_AGGREGATION_EQUIVALENCE.json',dict(PASS=True,cases=result,source_sha256=source,seconds=perf_counter()-started,physical_scope='all bounded original individual assignments map; complete reverse integer pools equal physical sets modulo authorized identical-job UID permutation',deterministic_individual_decomposition_PASS=True))
    table('AGGREGATE_TO_INDIVIDUAL_VALIDATION.csv',validation)
if __name__=='__main__':main()
