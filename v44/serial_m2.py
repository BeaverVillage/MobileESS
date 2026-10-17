"""Explicit single-Worker campaign, two-thread Barrier M stages only.

Frozen files, matrices, budgets and physical admission stay unchanged. The
thread assignment and its original guards are routed together inside M scope;
all day/arm/model/lease/source checks remain active. A/Actual retain one thread.
"""
from contextlib import contextmanager,ExitStack
from functools import wraps
from pathlib import Path
from types import FunctionType,SimpleNamespace
from unittest.mock import patch
import argparse
import inspect
import subprocess
import textwrap

from . import barrier,cap300
from .common import RUNTIME,read,record,verify,atomic,digest,now

POLICY='V44_SERIAL_ONE_WORKER_M_BARRIER_THREADS2_GAP3_V1'
PERMIT=RUNTIME/'v43_planning_svr12_actual_v1/SERIAL_M2_EXECUTION_PERMIT.json'
CAMPAIGN=RUNTIME/'v43_planning_svr12_actual_v1/campaign002'


def overlay():
    return dict(policy=POLICY,source=record(__file__),adapter_sources=[record(barrier.__file__),record(cap300.__file__)],
        Workers=1,M_Threads=2,A_Threads=1,Actual_Workers=1,Root_Method=2,Joint_MIPGap=.03,
        arms=['B2','B3'],stages=['M1','M2'],K48_Threads=2,K48_Method=2,
        day_order='2025-05-01_THROUGH_07_SEQUENTIAL',B2_queue_first=True,
        Main_order='PER_DAY_B0_B1_B3_AFTER_B2_QUEUE',May01_B3_A1='REUSE_B1_GOLDEN003',
        K48_total=300.,Joint_total=900.,Joint_call_cap=300.,fresh_M_build=True,
        prior_M_clocks_imported=False,prior_M_incumbents_imported=False,
        unchanged_matrix_and_domain=True,unchanged_feasibility_tolerances=True,unchanged_FULL_validation=True,
        unchanged_Actual_SVR12=True,original_Raw_modified=False)


def validate(path=PERMIT):
    value=barrier.validate(path)
    if value.get('serial_M_overlay')!=overlay() or value.get('serial_M_policy_sha')!=digest(overlay()):
        raise PermissionError('EXACT_SERIAL_THREADS2_POLICY_REQUIRED')
    verify([value['serial_M_overlay']['source']]+value['serial_M_overlay']['adapter_sources'])
    return value


def make_permit():
    value=barrier.validate()
    value.update(UTC=now(),serial_M_overlay=overlay(),serial_M_policy_sha=digest(overlay()),
        direct_serial_instruction='B2와 B3의 M단계 2thread, 1worker로 7일 순차. Barrier 유지. 5월 1일 B2부터 재개.',
        new_campaign=str(CAMPAIGN))
    if PERMIT.exists():raise FileExistsError('SERIAL_M2_NEW_PERMIT_REQUIRED')
    atomic(PERMIT,value);validate();return value


def assignments(cases,running):
    from .config import B2_ORDER,MAIN_ORDER
    from .scheduler import TERMINAL
    if running:return []
    for lane,order in (('B2',B2_ORDER),('MAIN',MAIN_ORDER)):
        for day,arm in order:
            if cases.get((day,arm),'READY') not in TERMINAL:
                return [dict(day=day,arm=arm,worker_slot=1,lane=lane)]
    return []


def is_m(request):
    return request.get('arm') in ('B2','B3') and request.get('stage') in ('M1','M2')


def route_source(original,old,new,**names):
    source=textwrap.dedent(inspect.getsource(original))
    if source.count(old)!=1:raise ValueError('EXACT_THREADS_BOUNDARY_DRIFT:'+original.__name__)
    namespace=dict(original.__globals__,**names)
    exec(compile(source.replace(old,new),original.__code__.co_filename,'exec'),namespace)
    return namespace[original.__name__]


@contextmanager
def m_threads(request):
    """Keep original source bytes and every non-thread guard intact."""
    if not is_m(request) or request.get('Threads')!=2 or request.get('worker_slot')!=1:
        raise PermissionError('ONLY_SINGLE_SLOT_EXPLICIT_M_THREADS2')
    from v42_may_campaign import execution as legacy
    from v42_may_campaign_native90 import execution as inherited,budget as native_budget
    from .frozen.v43_mess.library import load
    modules=load();engine=modules['m_engine'];k48=modules['table_v_k48']
    original_native=native_budget.DateBudget.native_optimize
    # Resolve the guard at call time, after native_stage has installed its
    # lease/source wrapper. Never capture a pre-scope unguarded reference.
    native=route_source(original_native,'model.Params.Threads = 1','model.Params.Threads = 2',
        guard=lambda model:native_budget.guard(model))
    def adapt_guard(original):
        return route_source(original,'if int(model.Params.Threads) != 1:',
            'if int(model.Params.Threads) != 2:')
    joint=barrier.parameters(engine.APPROVED_JOINT_PARAMETERS,request['day'],request['stage'],request['arm'])
    joint.update(Threads=2,Method=2,MIPGap=.03)
    lower=dict(k48.ORIGINAL_NATIVE_PARAMETERS,Threads=2,Method=2)
    with ExitStack() as stack:
        stack.enter_context(patch.object(native_budget.DateBudget,'native_optimize',native))
        stack.enter_context(patch.object(legacy,'guard',adapt_guard(legacy.guard)))
        stack.enter_context(patch.object(inherited,'guard',adapt_guard(inherited.guard)))
        stack.enter_context(patch.object(engine,'APPROVED_JOINT_PARAMETERS',joint))
        stack.enter_context(patch.object(k48,'ORIGINAL_NATIVE_PARAMETERS',lower))
        yield dict(Joint=joint,K48=lower)


@contextmanager
def install(path=PERMIT):
    permit=validate(path)
    from . import execution,worker,campaign
    with cap300.install(path):
        old_guard=execution.assert_current;old_stage=worker.m_stage;old_request=campaign.stage_request
        def guard():
            value=old_guard();validate(path);request=value['request']
            if request.get('serial_M_policy_sha')!=permit['serial_M_policy_sha'] or request.get('worker_slot')!=1:
                raise PermissionError('SERIAL_M2_REQUEST_POLICY_REQUIRED')
            return value
        def stage_request(case,stage):
            request=old_request(case,stage)
            request['Threads']=2 if is_m(request) else 1
            return request
        @wraps(old_stage)
        def stage(request,aidc):
            with m_threads(request) as parameters:
                atomic(Path(request['case_root'])/(request['stage']+'.NUMERICAL_POLICY.json'),dict(
                    UTC=now(),serial_M_overlay=permit['serial_M_overlay'],serial_M_policy_sha=permit['serial_M_policy_sha'],
                    effective_parameters=parameters,fresh_M_stage=not bool(request.get('resume_parent'))))
                return old_stage(request,aidc)
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'assert_current',guard))
            stack.enter_context(patch.object(worker,'m_stage',stage))
            stack.enter_context(patch.object(campaign,'stage_request',stage_request))
            yield permit


def coordinator_run(root,path=PERMIT):
    from . import campaign
    permit=validate(path);original_atomic=campaign.atomic
    def write(path,value):
        if Path(path).parent.name=='requests' and isinstance(value,dict) and 'case_root' in value:
            value=dict(value,execution_policy_sha=permit['execution_policy_sha'],operational_overlay=permit['operational_overlay'],
                numerical_overlay=permit['numerical_overlay'],numerical_policy_sha=permit['numerical_policy_sha'],
                serial_M_overlay=permit['serial_M_overlay'],serial_M_policy_sha=permit['serial_M_policy_sha'],
                Joint_call_cap_seconds=300.)
        original_atomic(path,value)
    def launch(command,**kwargs):
        command=list(command);index=command.index('-m')+1
        if command[index]!='v44.campaign':raise PermissionError('ONLY_SERIAL_CAMPAIGN_WORKER')
        command[index]='v44.serial_m2';command+=['--permit',str(path)]
        return subprocess.Popen(command,**kwargs)
    fn=campaign.run
    namespace=dict(fn.__globals__,assignments=assignments,atomic=write,
        subprocess=SimpleNamespace(Popen=launch,CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    run=FunctionType(fn.__code__,namespace,fn.__name__,fn.__defaults__,fn.__closure__);run.__kwdefaults__=fn.__kwdefaults__
    with install(path):return run(root,path,resume=False)


def thread_smoke(output,path=PERMIT):
    """Tiny pre-campaign Native guard check, not a physical simulation."""
    import gurobipy as gp
    from .locks import coordinator,worker_slot,process_identity
    from .execution import case_scope,native_stage
    from v42_may_campaign_native90.budget import DateBudget
    permit=validate(path);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    request=read(RUNTIME/'v43_planning_svr12_actual_v1/campaign001/2025-05-01/B2/attempt001/M1/request.json')
    request.update(case_root=str(output/'case'),campaign_root=str(output),root=str(output/'M1'),output=str(output/'M1'),
        worker_slot=1,Threads=2,execution_permit=record(path),execution_policy_sha=permit['execution_policy_sha'],
        serial_M_policy_sha=permit['serial_M_policy_sha'])
    atomic(output/'PHASE.json',dict(lane='B2',UTC=now()))
    with coordinator(output) as lease:
        request['lease']=lease;who=dict(**process_identity(),day=request['day'],arm='B2',worker_slot=1)
        with worker_slot(request['day'],'B2',1,root=output,lease=lease),case_scope(request,lease,who),install(path),m_threads(request),native_stage(request):
            model=gp.Model('THREAD2_GUARD_SMOKE')
            try:
                x=model.addVar(lb=0.,ub=2.,obj=1.);y=model.addVar(vtype='B')
                model.addConstr(x>=1.+y);model.update()
                budget=DateBudget(output/'NATIVE_LEDGER.json',native_limit=1.)
                budget.optimize(model,track='M',label='THREAD2_GUARD_SMOKE',requested_seconds=1.)
                result=dict(UTC=now(),PASS=model.Status==gp.GRB.OPTIMAL and model.Params.Threads==2,
                    observed_Threads=model.Params.Threads,Native_seconds=model.Runtime,Native_calls=len(budget.calls),
                    serial_M_policy_sha=permit['serial_M_policy_sha'],physical_simulation=False,campaign_case=False)
                atomic(output/'RESULT.json',result);return result
            finally:model.dispose()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--permit',type=Path,default=PERMIT)
    parser.add_argument('--worker',type=Path);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--thread-smoke',type=Path)
    parser.add_argument('--root',type=Path,default=CAMPAIGN);args=parser.parse_args()
    if args.worker:
        request=read(args.worker)
        if request.get('worker_slot')!=1:raise PermissionError('SERIAL_WORKER_SLOT_ONE_REQUIRED')
        with install(args.permit):
            from .campaign import run_case
            run_case(request)
    elif args.thread_smoke:thread_smoke(args.thread_smoke,args.permit)
    elif args.execute:coordinator_run(args.root,args.permit)
    else:raise PermissionError('EXPLICIT_SERIAL_EXECUTION_REQUIRED')


if __name__=='__main__':main()
