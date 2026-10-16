"""Resume one interrupted B2 case from its saved arrays, pool and Native ledger.

Original Raw stays immutable. No model rebuild, A1, K48 or budget reset.
"""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace,MethodType
import inspect
import os
import shutil
import sys
import textwrap
import threading
import time
import traceback

import numpy as np
import psutil
from scipy import sparse

from v43.common import ROOT,DOC,read,record,verify_records,atomic,now
from v42_native.contracts import digest
from .budget import StageBudget,worker_permit,heavy_peers
from .worker import result_fields,execution_status


def restore_case(parent,out,request,modules):
    from v43_arms.reference import load as reference
    from v42_bootstrap.m1 import native_inputs
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from .library import current_identity
    payload=reference(request['fixed_AIDC_reference'])
    sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[
        (r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    graph=(sites,initial,arcs,battery,receipt)
    A=sparse.load_npz(parent/'FULL_A.npz');B=sparse.load_npz(parent/'C3A_A.npz')
    def arrays(name):
        with np.load(parent/name,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
    d=arrays('FULL_DATA.npz');e=arrays('C3A_DATA.npz')
    identity=read(parent/'SCIENTIFIC_CASE_IDENTITY.json');case_sha=identity.pop('case_sha')
    m=modules['m_engine']
    if (digest(identity)!=case_sha or m.matrix_sha(B)!=identity['selected_matrix_sha']
            or m.domain_sha(e)!=identity['selected_domain_sha']):raise ValueError('SAME_CASE_CHECKPOINT_ARRAY_DRIFT')
    compact=Compact(A,d,arcs,initial,96)
    axes=arrays('CURRENT_C2_AXES.npz');steps=read(parent/'CURRENT_C2_ALIASES.json')
    if not np.array_equal(compact.d['names'][axes['columns']],e['names']):
        raise ValueError('SAME_CASE_INVERSE_COLUMN_AXIS_DRIFT')
    inverse=SimpleNamespace(initial_names=compact.d['names'],col_ids=axes['columns'],steps=steps)
    inverse.inverse=MethodType(Presolve.inverse,inverse)
    def lift(point):
        if np.asarray(point).shape!=(B.shape[1],):raise ValueError('CURRENT_M_POINT_AXIS_DRIFT')
        return compact.inverse(inverse.inverse(point))
    case=SimpleNamespace(original_A=A,original_d=d,A=B,d=e,graph=graph,case_sha=case_sha,
        identity=identity,bundle=payload['bundle'],anchor=read(parent/'FIXED_AIDC_ANCHOR.json'),
        planning=payload['planning'],output=out,lift=lift,plan_exporter=m.export_plan,mess_stage_budget_seconds=1800.)
    current_identity(case)
    registry=read(parent/'COMMON_M_PR222/ITERATION_0005/INCUMBENT/SAME_CASE_INCUMBENT_REGISTRY.json')
    if any(r['binding']!=m.binding(case) for r in registry):raise ValueError('RESUME_CASE_BINDING_DRIFT')
    verify_records([r['raw'] for r in registry])
    return case,payload,registry


def continued_budget(out,case,prior,progress,parent):
    if prior['inflight'] is not None or any(r.get('status')!='FINISHED' for r in prior['calls']):
        raise ValueError('RESUME_REQUIRES_ALL_PRIOR_NATIVE_CALLS_RECONCILED')
    budget=StageBudget(out/'JOINT_NATIVE_LEDGER.json',case=case,kind='PLANNING_NATIVE',progress=progress)
    if not 0<=prior['measured_Native_Runtime']<budget.native_limit:raise ValueError('RESUME_NO_REMAINING_NATIVE_BUDGET')
    budget.native_used=float(prior['measured_Native_Runtime'])
    budget.calls=deepcopy(prior['calls']);budget.costs=deepcopy(prior['costs'])
    persist=budget.persist
    def saved():
        persist()
        doc=read(budget.path);doc.update(same_case_continuation=True,
            parent_ledger=record(parent/'JOINT_NATIVE_LEDGER.json'),
            prior_same_case_Native_seconds=prior['measured_Native_Runtime'],Native_budget_reset=False)
        atomic(budget.path,doc)
    budget.persist=saved;budget.persist()
    return budget


def route_adaptive(module,parent):
    """Continue epoch 6; the unfinished published pool is reused exactly once."""
    previous=read(parent/'COMMON_M_PR222/ADAPTIVE_PROGRESS.json')
    history=previous['history'];epoch=max(r['epoch'] for r in history)+1
    if epoch!=6:raise ValueError('THIS_RESUME_REQUIRES_PUBLISHED_UNSOLVED_EPOCH_6')
    unsolved=parent/f'COMMON_M_PR222/ITERATION_{epoch:04d}'
    if (unsolved/'JOINT/NATIVE_CALL.json').exists():raise ValueError('RESUME_POOL_ALREADY_HAS_NATIVE_CALL')
    pool=read(unsolved/'POOL.json')
    if module.pool_identity(pool['pools'])!=pool['pool_sha']:raise ValueError('RESUME_POOL_SHA_DRIFT')
    reservoir={};seen=set()
    for directory in sorted((parent/'COMMON_M_PR222').glob('ITERATION_*')):
        if not (directory/'POOL.json').exists():continue
        row=read(directory/'POOL.json')
        if int(directory.name.rsplit('_',1)[-1])<epoch:seen.add(row['pool_sha'])
        for unit,paths in row['pools'].items():
            for path in paths:reservoir.setdefault(unit,{})[tuple(path)]=dict(path=path)
    state=dict(epoch=epoch-1,reservoir=reservoir,used_paths={},seen_pools=seen,feedback=deepcopy(history))
    native_calls=[read(parent/f'COMMON_M_PR222/ITERATION_{i:04d}/JOINT/NATIVE_CALL.json') for i in range(1,epoch)]
    tree=ast.parse(textwrap.dedent(inspect.getsource(module.run)));changed=dict(state=0,loop=0,history=0)
    class Route(ast.NodeTransformer):
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='state':
                node.value=ast.Call(func=ast.Name('_resume_state',ast.Load()),args=[],keywords=[]);changed['state']+=1
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Tuple) and [getattr(t,'id',None) for t in node.targets[0].elts]==['calls','seen_models','history']:
                node.value=ast.Call(func=ast.Name('_resume_history',ast.Load()),args=[],keywords=[]);changed['history']+=1
            return self.generic_visit(node)
        def visit_For(self,node):
            if isinstance(node.target,ast.Name) and node.target.id=='epoch':
                if ast.unparse(node.iter)!='range(1, 1101)':raise ValueError('RESUME_EPOCH_BOUNDARY_DRIFT')
                node.iter.args[0]=ast.Constant(epoch);changed['loop']+=1
            return self.generic_visit(node)
    tree=Route().visit(tree);ast.fix_missing_locations(tree)
    if changed!=dict(state=1,loop=1,history=1):raise ValueError('RESUME_ADAPTIVE_SOURCE_SHAPE_DRIFT')
    ns=dict(module.__dict__,_resume_state=lambda:deepcopy(state),
        _resume_history=lambda:(deepcopy(native_calls),set(),deepcopy(history)))
    exec(compile(tree,module.__file__,'exec'),ns)
    return ns['run'],pool['pools'],epoch


def run(parent,out):
    parent,out=Path(parent),Path(out)
    request=read(parent/'request.json');prior=read(parent/'JOINT_NATIVE_LEDGER.json')
    if (request['arm'],request['stage'],request['day'])!=('B2','M1','2025-05-01'):
        raise ValueError('EXPLICIT_SAME_B2_M1_MAY01_RESUME_ONLY')
    if psutil.pid_exists(read(parent/'START.json')['pid']) or heavy_peers():raise ValueError('RESUME_OLD_WORKER_MUST_BE_DEAD')
    if (parent/'RESULT.json').exists() or out.exists():raise ValueError('NEW_CONTINUATION_OF_INCOMPLETE_ATTEMPT_ONLY')
    verify_records(request['sources']+[request['fixed_AIDC_record']])
    out.mkdir(parents=True);request=dict(request,root=str(out),output=str(out),continuation_of=str(parent))
    sources=request['sources']+[record(__file__),record(ROOT/'v43_mess/resume_supervisor.ps1'),
        record(ROOT/'v43_resume/worker.py'),record(ROOT/'v43_resume/__init__.py')];atomic(out/'request.json',request)
    atomic(out/'START.json',dict(UTC=now(),pid=os.getpid(),process_created=psutil.Process().create_time(),
        sources=sources,parent=str(parent),same_scientific_case=True,new_optimization_stage=False,Worker=1,Threads=1))
    for name in ('K48_NATIVE_LEDGER.json','LOWER_STAGE_RESULT.json','NATIVE0_CERTIFICATION.json','SCIENTIFIC_CASE_IDENTITY.json'):
        shutil.copyfile(parent/name,out/name)
    began=time.perf_counter();done=threading.Event();latest={};budget=None;control=None
    def progress(value):
        latest.update(value);atomic(out/'progress.json',dict(latest,UTC=now()))
        if (out/'STOP_REQUESTED.json').exists():
            from v42_may_campaign.execution import _model
            live=_model.get()
            if live is not None:live['model'].terminate()
            else:raise RuntimeError('RESUME_OFFICIAL_STOP_REQUESTED')
    def heartbeat():
        while not done.wait(10):
            p=psutil.Process();mem=p.memory_info();atomic(out/'HEARTBEAT.json',dict(UTC=now(),pid=p.pid,latest=latest,
                CPU_seconds=sum(p.cpu_times()[:2]),RSS_bytes=mem.rss,peak_RSS_bytes=mem.peak_wset,wall_seconds=time.perf_counter()-began))
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    result=dict(PASS=False,arm='B2',stage='M1',day='2025-05-01',continuation_of=str(parent),same_case_checkpoint_resume=True)
    try:
        with worker_permit(request,sources):
            from .library import load
            from .performance import install,record_caches
            modules=load();m=modules['m_engine'];adaptive=modules['m_adaptive'];g=modules['table_v_global_control']
            progress(dict(phase='RESTORE_SAME_CASE_ARRAYS_AND_INVERSE_NO_OPTIMIZE',arm='B2',day=request['day']))
            case,payload,registry=restore_case(parent,out,request,modules);install(case,modules)
            lower=read(parent/'LOWER_STAGE_RESULT.json')
            control=g.GlobalGapControl(g.mess_scope(case),.03,out/'GLOBAL_CONTROL');case.global_gap_control=control
            for row in lower['history']:g.mess_lower(control,case,row,same_case_checkpoint=True,new_K48_Native_calls=0)
            budget=continued_budget(out,case,prior,progress,parent)
            routed,pool,epoch=route_adaptive(adaptive,parent);adaptive.run=routed
            original_generate=modules['m_candidates'].generate;first=[True]
            def generate(current,point,bank,clock):
                if bank.best is None:raise ValueError('RESUME_SAVED_FULL_INCUMBENT_NOT_ADMITTED')
                if first[0]:first[0]=False;return deepcopy(pool)
                return original_generate(current,point,bank,clock)
            case.candidate_generator=generate
            checkpoint=dict(parent_request=record(parent/'request.json'),parent_K48=record(parent/'K48_NATIVE_LEDGER.json'),
                parent_Joint=record(parent/'JOINT_NATIVE_LEDGER.json'),case_sha=case.case_sha,
                source_sha=case.identity['source_sha'],resume_epoch=epoch,prior_Joint_Native_seconds=budget.used(),
                remaining_Joint_Native_seconds=budget.remaining(),K48_reexecuted=False,A1_reexecuted=False,
                model_rebuilt=False,presolve_reexecuted=False,Original_FULL_case_unchanged=True,
                unfinished_pool_reused_exactly=True,unpersisted_private_Beam_cache='REBUILT_FROM_PUBLISHED_CURRENT_CASE_POOLS',
                same_heuristic_trajectory_claimed=False,prior_Raw_overwritten=False)
            atomic(out/'RESUME_CHECKPOINT_RECEIPT.json',checkpoint)
            progress(dict(phase='RESUME_JOINT_FROM_EPOCH_6',budget_kind='PLANNING_NATIVE',Native_Runtime=budget.used(),
                remaining_seconds=budget.remaining(),inflight=False))
            with np.load(registry[0]['raw']['path'],allow_pickle=False) as z:seed=z['point'].copy()
            other=[r for r in registry[1:] if r['raw']['sha256']!=registry[0]['raw']['sha256']]
            ub,point=m.optimize_mess(case,seed,other,budget)
            atomic(out/'UPPER_STAGE_RESULT.json',ub);record_caches(case,out/'CURRENT_CASE_CACHE_METRICS.json')
            if point is not None:np.savez_compressed(out/'ACCEPTED_M_POINT.npz',point=point)
            bounds=control.bounds();result.update(case_sha=case.case_sha,fixed_AIDC=payload['identity'],lower=lower,upper=ub,
                **result_fields(ub,bounds),**execution_status(ub,bounds),MESS_plan=ub['mess'],
                K48_Native_seconds=read(parent/'K48_NATIVE_LEDGER.json')['measured_Native_Runtime'],
                Joint_Native_seconds=budget.used(),new_Joint_Native_seconds=budget.used()-prior['measured_Native_Runtime'],
                Native_calls=3+len(budget.calls),new_Native_calls=len(budget.calls)-len(prior['calls']),
                Actual_diagnostic_allowed=ub['FULL_validated'],restricted_ObjBound_is_Global_LB=False,P2_calls=0)
            control.finish('IMPLEMENTATION_OR_NUMERICAL_FAILURE' if not result['M_stage_execution_PASS'] else
                'GLOBAL_GAP_TARGET_MET' if bounds['global_gap_certified'] else
                'NATIVE_BUDGET_EXHAUSTED' if budget.remaining()<=10 else 'NO_FURTHER_CERTIFIED_IMPROVEMENT')
            verify_records(sources)
    except BaseException as error:result.update(PASS=False,error=repr(error),traceback=traceback.format_exc())
    finally:
        if control is not None:control.close()
        done.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),wall_seconds=time.perf_counter()-began,inflight=None,
            Native_seconds=read(parent/'K48_NATIVE_LEDGER.json')['measured_Native_Runtime']+(budget.used() if budget else prior['measured_Native_Runtime']),
            FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False)
        atomic(out/'RESULT.json',result);atomic(out/'RECONCILIATION.json',dict(UTC=now(),inflight=None,
            Native_seconds=result['Native_seconds'],same_case_continuation=True,new_Native_calls=result.get('new_Native_calls',0)))
    print({k:result.get(k) for k in ('PASS','status','new_Native_calls','Native_seconds','error')},flush=True)
    return result


if __name__=='__main__':run(*sys.argv[1:])
