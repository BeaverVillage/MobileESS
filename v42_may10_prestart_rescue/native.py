"""Source-frozen, May10 PRESTART-only bounded native experiments."""
from dataclasses import replace
from pathlib import Path
import json,time,threading,math
import numpy as np
import psutil
import gurobipy as gp
from v42_pr134_b1.common import atomic,read,record,SETTINGS
from v42_a_stage_domain_v2.stress_backend import materialize
from .isolation import OUT,STATIC,assert_write_path,require_large_resource_isolation


def verify_sources():
    freeze=read(OUT/'NATIVE_SOURCE_FREEZE.json')
    for name,want in freeze['sources'].items():
        if record(name)['sha256']!=want:raise PermissionError('NATIVE_EXECUTED_SOURCE_BYTES_CHANGED')
    return freeze


def authorize_case(plan,name,snapshot_sha256,seconds,relax,presolve,previous):
    cases=plan['cases']
    if len(previous)>=len(cases) or name!=cases[len(previous)]['name']:
        raise PermissionError('ONLY_PREDECLARED_ORDERED_NATIVE_CASES_NO_RERUN')
    case=cases[len(previous)]
    if (case['snapshot_sha256']!=snapshot_sha256 or float(seconds)!=case['seconds']
        or bool(relax)!=case['relax'] or presolve!=case['presolve']):
        raise PermissionError('PREDECLARED_NATIVE_MODEL_OR_ALGORITHM_CHANGED')
    return case


def solve(snapshot,name,seconds,*,relax=False,presolve=-1,warm=None,validate=None):
    require_large_resource_isolation();freeze=verify_sources()
    if snapshot.objectives[0].name!='prestart_relocation':
        raise PermissionError('ONLY_ORIGINAL_MAY10_PRESTART_OBJECTIVE_AUTHORIZED')
    objective=snapshot.objectives[0]
    if (objective.constant!=0 or any(c.denominator!=1 or snapshot.vtypes[j] not in ('I','B')
        for j,c in objective.coefficients().items())):
        raise PermissionError('ORIGINAL_PRESTART_INTEGER_OBJECTIVE_PROOF_REQUIRED')
    folder=assert_write_path(OUT/'NATIVE'/name);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'RESULT.json').exists() or (folder/'CALL_ENTERED.json').exists():
        raise PermissionError('NO_AUTOMATIC_NATIVE_CASE_RERUN')
    budget=read(OUT/'NEW_NATIVE_CONTINUATION_BUDGET.json')
    previous=read(OUT/'NEW_NATIVE_CALLS.json')['calls'] if (OUT/'NEW_NATIVE_CALLS.json').exists() else []
    plan=read(OUT/'BENCHMARK_PLAN.json')
    if record(OUT/'BENCHMARK_PLAN.json')['sha256']!=freeze['plan_sha256']:
        raise PermissionError('NATIVE_PLAN_CHANGED_AFTER_SOURCE_FREEZE')
    if record(OUT/'NEW_NATIVE_CONTINUATION_BUDGET.json')['sha256']!=freeze['budget_sha256']:
        raise PermissionError('NATIVE_BUDGET_CHANGED_AFTER_SOURCE_FREEZE')
    authorize_case(plan,name,snapshot.fingerprint(),seconds,relax,presolve,previous)
    consumed=sum(c['Runtime'] for c in previous)
    limit=min(float(seconds),budget['native_limit_seconds']-consumed-30.)
    if limit<=0:raise PermissionError('NEW_NATIVE_BUDGET_EXHAUSTED_NO_RESET')
    source_snapshot=snapshot
    if relax:snapshot=replace(snapshot,vtypes=np.full(snapshot.matrix.shape[1],'C'))
    build=time.perf_counter();model,objectives=materialize(snapshot,'2025-05-10')
    model.setObjective(objectives[0][1],gp.GRB.MINIMIZE)
    actual=model.getA().tocsr();actual.sum_duplicates();actual.sort_indices()
    expected=np.zeros(model.NumVars)
    for j,c in snapshot.objectives[0].coefficients().items():expected[j]=float(c)
    box=lambda x,y:np.all((x==y)|((abs(x)>=1e100)&(abs(y)>=1e100)&(np.sign(x)==np.sign(y))))
    delta=actual-snapshot.matrix;delta.eliminate_zeros()
    compiled=dict(PASS=delta.nnz==0 and box(np.asarray(model.getAttr('LB')),snapshot.lower)
        and box(np.asarray(model.getAttr('UB')),snapshot.upper)
        and np.array_equal(model.getAttr('VType'),snapshot.vtypes)
        and np.array_equal(model.getAttr('Sense'),snapshot.senses)
        and np.array_equal(model.getAttr('RHS'),snapshot.rhs)
        and np.array_equal(model.getAttr('Obj'),expected)
        and model.ObjCon==float(snapshot.objectives[0].constant),
        snapshot_sha256=snapshot.fingerprint(),source_integer_snapshot_sha256=source_snapshot.fingerprint(),
        rows=model.NumConstrs,cols=model.NumVars,nnz=model.NumNZs,relaxation_only=relax)
    atomic(folder/'ACTUAL_MODEL_VERIFICATION.json',compiled)
    if not compiled['PASS']:model.dispose();raise ValueError('ACTUAL_NATIVE_MODEL_READBACK_MISMATCH')
    del actual,delta
    params=dict(SETTINGS,Threads=1,Method=2,NodeMethod=1,MIPFocus=3,Presolve=presolve,Crossover=-1)
    for key,value in params.items():model.setParam(key,value)
    model.Params.MemLimit=float('inf');model.Params.SoftMemLimit=float('inf')
    model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(folder/'SOLVER.log')
    model.Params.TimeLimit=limit
    if warm is not None:
        model.setAttr('Start',model.getVars(),warm.tolist())
    atomic(folder/'PARAMETERS.json',dict(actual={k:getattr(model.Params,k) for k in params},TimeLimit=limit,
        MemLimit=str(model.Params.MemLimit),SoftMemLimit=str(model.Params.SoftMemLimit),
        automatic_memory_stop=False,memory_throttling=False,Threads=1,source_commit=freeze['git_head']))
    samples=[];stop=threading.Event();callback_errors=[];progress=[]
    def observe_memory():
        while not stop.is_set():
            try:samples.append(dict(unix=time.time(),RSS=psutil.Process().memory_info().rss))
            except Exception:pass
            stop.wait(2)
    observer=threading.Thread(target=observe_memory,daemon=True);observer.start()
    def callback(m,where):
        if where==gp.GRB.Callback.MIPSOL and validate is not None:
            try:validate(np.asarray(m.cbGetSolution(m.getVars()),dtype=float),name)
            except Exception as error:callback_errors.append(repr(error))
        if where==gp.GRB.Callback.MIP and (not progress or time.perf_counter()-progress[-1]['clock']>=30):
            progress.append(dict(clock=time.perf_counter(),nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),
                bound=float(m.cbGet(gp.GRB.Callback.MIP_OBJBND)),incumbent=float(m.cbGet(gp.GRB.Callback.MIP_OBJBST))))
            atomic(folder/'PROGRESS.json',dict(trajectory=progress,acceptance_authority=False))
    error=None;entered=time.perf_counter()
    atomic(folder/'CALL_ENTERED.json',dict(unix=time.time(),case=name,TimeLimit=limit,
        source_commit=freeze['git_head'],predeclared_plan_sha256=freeze['plan_sha256'],
        native_call_may_not_be_retried=True))
    try:model.optimize(callback)
    except Exception as exception:error=repr(exception)
    finally:stop.set();observer.join(timeout=3)
    attrs={};errors={}
    for key in ('X','Pi','RC','VBasis','CBasis','FarkasDual'):
        try:attrs[key]=np.asarray(model.getAttr(key))
        except Exception as exception:errors[key]=str(exception)
    raw_path=assert_write_path(STATIC/'NATIVE'/name/'RAW.npz');raw_path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(raw_path,**attrs)
    def scalar(key):
        try:
            value=float(getattr(model,key));return value if math.isfinite(value) and abs(value)<1e99 else None
        except Exception:return None
    runtime=scalar('Runtime')
    result=dict(case=name,status=scalar('Status'),objective=scalar('ObjVal'),ObjBound=scalar('ObjBound'),
        Runtime=runtime if runtime is not None else time.perf_counter()-entered,Work=scalar('Work'),
        NodeCount=scalar('NodeCount'),SolCount=scalar('SolCount'),IterCount=scalar('IterCount'),
        BarIterCount=scalar('BarIterCount'),native_error=error,raw=record(raw_path),raw_attribute_errors=errors,
        callback_errors=callback_errors,peak_RSS_bytes=max((s['RSS'] for s in samples),default=0),
        build_and_readback_seconds=entered-build,actual_model=record(folder/'ACTUAL_MODEL_VERIFICATION.json'),
        source_commit=freeze['git_head'],native_Runtime_includes_callbacks=True,
        relaxation_only=relax,requested_TimeLimit=limit,parameters=record(folder/'PARAMETERS.json'))
    atomic(folder/'MEMORY_TELEMETRY.json',dict(samples=samples,metrics_only=True))
    atomic(folder/'RESULT.json',result)
    previous.append(result);atomic(OUT/'NEW_NATIVE_CALLS.json',dict(calls=previous,
        actual_total_Runtime=sum(c['Runtime'] for c in previous),budget_not_reset=True))
    print('RESCUE_NATIVE_RESULT',name,result['status'],result['objective'],result['ObjBound'],result['Runtime'],flush=True)
    model.dispose()
    return result,attrs
