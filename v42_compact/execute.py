from time import perf_counter
from collections import defaultdict
from dataclasses import asdict
import gurobipy as gp
from .common import *
from .native import prepare,build
from .graph import reconstruct
from .formulation import values
from v42_job_capability import resources_used,resource_limit
from v42_native.supervision import atomic,supervise

def quality_met(passes):
    return bool(passes) and all(p['incumbent'] is not None and p['gap'] is not None and 0<=p['gap']<=.001+1e-10 for p in passes)

def optimization_receipt(phases,events,lex_complete):
    # Gurobi can return +/- infinity before a finite bound exists. Keep it
    # unavailable, rather than failing diagnostic publication after the solve.
    return clean(dict(passes=phases,optimizer_called=True,events=events,lex_complete=lex_complete))

def worker(context,payload):
    for row in payload['sources']:require(sha(row['path'])==row['sha256'],'COMPACT_SOURCE_DRIFT')
    data=prepare(context);context.check()
    from v42_a_stage_domain_v2.execution import require_action_authorized
    if payload['mode']!='BUILD_ONLY':require_action_authorized(data[0],'A1')
    m,variables,objectives,controls=build(context,data)
    try:
        if payload['mode']=='BUILD_ONLY':return
        m.Params.MIPGap=.001;m.Params.Threads=1;m.Params.Seed=20260929
        phases=[];events={};started=perf_counter();last_progress=[-10.]
        def callback(model,where):
            if where==gp.GRB.Callback.PRESOLVE:
                events.update(presolve_rows_removed=int(model.cbGet(gp.GRB.Callback.PRE_ROWDEL)),presolve_columns_removed=int(model.cbGet(gp.GRB.Callback.PRE_COLDEL)),last_presolve_observation_seconds=perf_counter()-started)
            elapsed=perf_counter()-started
            if where==gp.GRB.Callback.PRESOLVE and elapsed-last_progress[0]>=2:
                context.progress(dict(phase='PRESOLVE',optimizer_called=True,optimization_seconds=elapsed,**events));last_progress[0]=elapsed
            if where in (gp.GRB.Callback.MIP,gp.GRB.Callback.MIPSOL) and elapsed-last_progress[0]>=2:
                prefix='MIP_' if where==gp.GRB.Callback.MIP else 'MIPSOL_'
                context.progress(dict(phase='OPTIMIZATION',objective_level=objectives[len(phases)][0],optimizer_called=True,
                    incumbent=model.cbGet(getattr(gp.GRB.Callback,prefix+'OBJBST')) if prefix=='MIP_' else model.cbGet(gp.GRB.Callback.MIPSOL_OBJ),
                    best_bound=model.cbGet(getattr(gp.GRB.Callback,prefix+'OBJBND')),nodes=model.cbGet(getattr(gp.GRB.Callback,prefix+'NODCNT')),
                    optimization_seconds=elapsed,**events));last_progress[0]=elapsed
            if context.remaining<=0:model.terminate()
        for name,expr in objectives:
            if context.remaining<=30:break # retain the preceding incumbent for validation
            m.setObjective(expr);m.Params.TimeLimit=context.remaining-30
            atomic(context.folder/'OPTIMIZER_STARTED.json',dict(optimizer_called=True,objective_level=name,remaining_external_seconds=context.remaining,validation_budget_seconds=30,Threads=1,Seed=20260929,MIPGap=.001))
            m.optimize(callback)
            phases.append(dict(level=name,status=m.Status,incumbent=m.ObjVal if m.SolCount else None,best_bound=m.ObjBound,
                gap=m.MIPGap if m.SolCount else None,nodes=m.NodeCount,solve_seconds=m.Runtime))
            atomic(context.folder/'OPTIMIZATION.json',optimization_receipt(phases,events,len(phases)==len(objectives) and m.Status==gp.GRB.OPTIMAL))
            if not m.SolCount:return
            # Retain a quality-qualified time-limit incumbent; optimality and
            # completion of lower lex levels are reported separately.
            if m.Status!=gp.GRB.OPTIMAL:break
            if context.remaining<=30:break
            if len(phases)<len(objectives):m.addConstr(expr<=m.ObjVal+(1e-7 if name=='rho' else 1e-8))
        if not m.SolCount:return
        bundle,jobs,bounds,r,raw,graphs,prep=data;selected={};used=defaultdict(float)
        for uid,j in jobs.items():
            o=reconstruct(j,bounds[uid],r,graphs[uid],values(variables[uid]));selected[uid]=asdict(o)
            for key,n in resources_used(j,o).items():used[key]+=n
        physical=all(n<=resource_limit(key,r)+1e-5 for key,n in used.items())
        audit=dict(physical_PASS=physical,full_linear_max_violation=m.MaxVio,raw_incumbent_exists=True,
            lex_complete=len(phases)==len(objectives) and all(p['status']==gp.GRB.OPTIMAL for p in phases),quality_rule_met=quality_met(phases))
        atomic(context.folder/'INCUMBENT_AUDIT.json',audit)
        if physical and m.MaxVio<=1e-5 and audit['quality_rule_met']:
            context.publish(dict(stage='A1',selected=selected,audit=audit,passes=phases,accepted_native_plan=True,
                controls=[[float(gp.LinExpr(x).getValue()) for x in row] for row in controls]))
    finally:m.dispose()

def validator(candidate,payload):
    from v42_boundary.boundaries import load_native
    from v42_job_capability import Option,validate
    bundle,jobs,bounds,seconds,r,raw=load_native();used=defaultdict(float)
    require(set(candidate['selected'])==set(jobs),'ALL_JOBS_INCUMBENT')
    for uid,value in candidate['selected'].items():
        value=dict(value);value['segments']=tuple(tuple(x) for x in value['segments']);value['wan']=tuple(tuple(x) for x in value['wan'])
        o=Option(**value);validate(jobs[uid],o,bounds[uid],r)
        for key,x in resources_used(jobs[uid],o).items():used[key]+=x
    return dict(PASS=all(x<=resource_limit(key,r)+1e-5 for key,x in used.items()) and quality_met(candidate['passes']) and candidate['audit']['full_linear_max_violation']<=1e-5)

def main():
    import os
    os.environ['PYTHONUTF8']='1';LOCAL.mkdir(exist_ok=True)
    for filename in ('SYNTHETIC_EQUIVALENCE.json','REAL_SUBSET_EQUIVALENCE.json','COMPACT_PATH_EQUIVALENCE_AUDIT.json'):
        require(read(OUT/filename)['PASS'],'EQUIVALENCE_BEFORE_MAY')
    sources=[rec(p) for p in (ROOT/'v42_compact').glob('*.py')]
    entry='v42_native.compact_worker:'
    if not (LOCAL/'build_only').exists():
        _,receipt=supervise('A1',entry+'worker',entry+'validator',dict(mode='BUILD_ONLY',sources=sources),LOCAL/'build_only',seconds=600)
        dump('BUILD_SUPERVISOR_RECEIPT.json',receipt)
    else:require(read(LOCAL/'build_only/stage_receipt.json')['timeout_reason']=='COMPLETED','NO_RETRY_FAILED_BUILD')
    if not (LOCAL/'build_only/MODEL_COMPLETE.json').exists():print('COMPACT_BUILD_FAILED_STOP',flush=True);return
    folder=LOCAL/'A1'
    if folder.exists():
        repair=read(OUT/'PRE_OPTIMIZE_ACCEPTANCE_REPAIR.json')
        require(repair['optimization_calls_in_invalidated_attempt']==0 and not (folder/'MODEL_COMPLETE.json').exists(),'NO_RETRY_STARTED_SOLVE')
        folder=LOCAL/'A1_acceptance_repair'
    candidate,receipt=supervise('A1',entry+'worker',entry+'validator',dict(mode='SOLVE',sources=sources),folder,seconds=600)
    dump('A1_SUPERVISOR_RECEIPT.json',receipt)
    if candidate is not None:raise RuntimeError('ACCEPTED_A1_REQUIRES_M1_A2_M2_CONTINUATION')
    print('A1 completed without accepted incumbent',flush=True)

if __name__=='__main__':main()
