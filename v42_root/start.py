"""Fixed source-plan completion, then at most one exact feasibility attempt."""
from dataclasses import asdict
from collections import Counter
import gurobipy as gp,numpy as np
from .common import *
from .factor import mapping
from .certify import certificate
from v42_job_capability import Option

def physical_options(selected):
    out={}
    for u,value in selected.items():
        d=dict(value);d['segments']=tuple(tuple(x) for x in d['segments']);d['wan']=tuple(tuple(x) for x in d['wan']);out[u]=Option(**d)
    return out

def assignments(unit,selected,data):
    bundle,jobs,bounds,r,raw,graphs,old,prep=data;u=unit['uid'];j=jobs[u];v=unit['v']
    if unit['stay_count']:
        plans=[selected[x] for x in unit['members'] if not selected[x].migrated];a={n:{} for n in v}
        for o in plans:
            a['y'][o.initial_site,o.start]=a['y'].get((o.initial_site,o.start),0)+1
            a['f0'][o.initial_site,o.segments[-1][2]]=a['f0'].get((o.initial_site,o.segments[-1][2]),0)+1
            for k,lo,hi in o.segments:
                for t in range(lo,hi):a['r0'][k,t]=a['r0'].get((k,t),0)+1
        return a
    if unit['optional']:
        plans=sorted(selected[x] for x in unit['members'] if selected[x].migrated);lane=int(unit['id'].split('_LANE_')[-1])
        if lane>=len(plans):return {n:{} for n in v}
        return mapping(j,graphs[u],r,plans[lane])
    return mapping(j,graphs[u],r,selected[u])

def validate_source(m,units,data,controls,bindings,levels):
    from v42_a_stage_domain_v2.execution import require_action_authorized
    require_action_authorized(data[0],'FEASIBILITY_MIP')
    audit=read(OUT/'MIP_START_AUTHORITY_AUDIT.json');c=None;receipt=None
    if audit['physical_precheck_PASS']:
        start=time.perf_counter();selected=physical_options(read(LOCAL/'REFERENCE_PLAN.json'));m.update();c=m.copy();cv=c.getVars();fixed={}
        for unit in units:
            a=assignments(unit,selected,data)
            for name,items in unit['v'].items():
                for key,x in items.items():
                    if isinstance(x,gp.Var) and x.VType in ('B','I'):
                        target=a.get(name,{}).get(key,0)
                        if x.index in fixed and abs(fixed[x.index]-target)>1e-8:raise ValueError('INCONSISTENT_SOURCE_ASSIGNMENT')
                        fixed[x.index]=target
        if len(fixed)!=m.NumIntVars:raise ValueError('SOURCE_MISSING_INTEGER_ASSIGNMENT')
        for i,x in fixed.items():cv[i].LB=x;cv[i].UB=x
        c.update();lp=c.relax();c.dispose();c=lp;c.setObjective(0);c.Params.Threads=1;c.Params.Seed=20260929;c.Params.TimeLimit=600;c.Params.OutputFlag=1;c.Params.LogFile=str(LOCAL/'SOURCE_COMPLETION_LP.log')
        opt_start=time.perf_counter();c.optimize();elapsed=time.perf_counter()-opt_start
        if c.Status==gp.GRB.OPTIMAL:
            dense=np.asarray(c.getAttr('X'),dtype=float);cert,plan,ctrl,snap=certificate(m,units,data,controls,bindings,levels,dense,c.MaxVio)
            dump('MIP_START_PHYSICAL_VALIDATION.json',dict(cert,status='SOURCE_REFERENCE_FULL_GLOBAL_VALIDATION',source_jobs_fixed=True,source_completion_LP_seconds=elapsed,total_source_completion_seconds=time.perf_counter()-start))
            if cert['PASS']:
                np.save(LOCAL/'MIP_START_X.npy',dense);atomic(LOCAL/'MIP_START_PLAN.json',plan);atomic(LOCAL/'MIP_START_CONTROLS.json',ctrl)
                receipt=dict(available=True,validated=True,type='COMPLETE_VALIDATED_MIP_START',authority='frozen native reference-start/reference-site/Q50 plan; continuous native control/CC4 completion validated separately',feasibility_attempt_RUN=False,source_completion_LP_seconds=elapsed,source_completion_total_seconds=time.perf_counter()-start,physical_certificate=cert,partial=False,artificial_physical_slack=0)
        else:dump('MIP_START_PHYSICAL_VALIDATION.json',dict(PASS=False,status='SOURCE_GLOBAL_COMPLETION_FAILED',solver_status=c.Status,source_completion_LP_seconds=elapsed))
        c.dispose()
    if receipt is None:
        start=time.perf_counter();m.update();c=m.copy();c.setObjective(0);c.Params.Threads=1;c.Params.Seed=20260929;c.Params.MIPGap=.005;c.Params.TimeLimit=600;c.Params.OutputFlag=1;c.Params.LogFile=str(LOCAL/'FEASIBILITY_ONLY.log');opt_start=time.perf_counter();c.optimize();elapsed=time.perf_counter()-opt_start
        receipt=dict(available=False,validated=False,feasibility_attempt_RUN=True,feasibility_optimize_seconds=elapsed,feasibility_total_seconds=time.perf_counter()-start,feasibility_status=c.Status,partial=False,artificial_physical_slack=0,same_full_physical_feasible_set=True,scientific_A1_budget_charged=False)
        if c.SolCount:
            dense=np.asarray(c.getAttr('X'),dtype=float);cert,plan,ctrl,snap=certificate(m,units,data,controls,bindings,levels,dense,c.MaxVio);dump('MIP_START_PHYSICAL_VALIDATION.json',dict(cert,status='EXACT_FULL_FEASIBILITY_GENERATION'))
            if cert['PASS']:
                np.save(LOCAL/'MIP_START_X.npy',dense);atomic(LOCAL/'MIP_START_PLAN.json',plan);atomic(LOCAL/'MIP_START_CONTROLS.json',ctrl);receipt.update(available=True,validated=True,type='COMPLETE_VALIDATED_MIP_START',authority='one same-full-feasible-set exact zero-objective attempt',physical_certificate=cert)
        else:dump('MIP_START_PHYSICAL_VALIDATION.json',dict(PASS=False,status='NO_VALIDATED_START',feasibility_status=c.Status))
        c.dispose()
    receipt.update(frozen_before_primary_A1=True,accepted_by_Gurobi=None)
    dump('MIP_START_RECEIPT.json',receipt)
    if receipt['validated']:
        values=np.load(LOCAL/'MIP_START_X.npy');m.setAttr('Start',m.getVars(),values.tolist());m.update()
    return receipt
