"""User-authorized Q operating subdomain and four-thread M-only campaign.

Build the cap into original FULL bounds and connection rows before any
projection, hashing or K48 proof. PCS rating, P, SOC and physics stay intact.
Historical pinned sources and results are never edited or imported as M seeds.
"""
from contextlib import contextmanager, ExitStack
from functools import wraps
from fractions import Fraction as F
from pathlib import Path
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
import argparse
import inspect
import math
import subprocess
import textwrap
import numpy as np

from . import barrier, cap300, serial_m2
from .common import RUNTIME, read, record, verify, atomic, digest, now

POLICY = 'V44_M_Q250_BARRIER_THREADS4_GAP3_V2'
Q_LIMIT = 250.
PERMIT = RUNTIME/'v43_planning_svr12_actual_v1/Q250_M4_V2_EXECUTION_PERMIT.json'
CAMPAIGN = RUNTIME/'v43_planning_svr12_actual_v1/campaign004'


def overlay():
    import v42_native.mess as native
    return dict(policy=POLICY, source=record(__file__),
        adapter_sources=[record(m.__file__) for m in (barrier, cap300, serial_m2, native)],
        Workers=1, M_Threads=4, A_Threads=1, Actual_Workers=1,
        arms=['B2','B3'], stages=['M1','M2'], Q_operating_limit_kvar=Q_LIMIT,
        cap_in_original_FULL=True, cap_in_connected_Q_rows=True, cap_in_Beam_and_LP_score=True,
        original_matrix_and_domain_changed=True, change='ONLY_Q_BOUNDS_AND_CONNECTED_Q_COEFFICIENT',
        PCS_kVA=400., P_limit_kW=300., SOC_and_route_authority_unchanged=True,
        Root_Method=2, Joint_MIPGap=.03, K48_Threads=4, K48_Method=2,
        K48_total=300., Joint_total=900., Joint_call_cap=300.,
        B2_queue_first=True, Main_order='PER_DAY_B0_B1_B3_AFTER_B2_MAY01_THROUGH_07',
        May01_A1='REUSE_GOLDEN003_NO_REOPTIMIZATION', B3_A1='REUSE_SAME_DATE_B1',
        fresh_M_build=True, prior_M_clocks_imported=False, prior_M_incumbents_imported=False,
        unchanged_FULL_validation=True, unchanged_feasibility_tolerances=True,
        unchanged_Actual_SVR12=True, original_Raw_modified=False)


def validate(path=PERMIT):
    value=barrier.validate(path)
    if value.get('Q250_M4_overlay')!=overlay() or value.get('Q250_M4_policy_sha')!=digest(overlay()):
        raise PermissionError('EXACT_Q250_M4_POLICY_REQUIRED')
    verify([value['Q250_M4_overlay']['source']]+value['Q250_M4_overlay']['adapter_sources'])
    return value


def make_permit():
    value=barrier.validate()
    value.update(UTC=now(), Q250_M4_overlay=overlay(), Q250_M4_policy_sha=digest(overlay()),
        direct_user_instruction='A stages one thread; B2/B3 all M stages Q +/-250 kvar per vehicle, four threads; fresh May01 campaign.',
        new_campaign=str(CAMPAIGN), original_campaign_preserved=True)
    if PERMIT.exists():raise FileExistsError('NEW_Q250_M4_PERMIT_REQUIRED')
    atomic(PERMIT,value);validate();return value


def native_adapter(original):
    """Same row/column order; change only explicit Q operating limits."""
    source=textwrap.dedent(inspect.getsource(original))
    edits={
        'lb=-battery.pcs_kva,ub=battery.pcs_kva': 'lb=-250.,ub=250.',
        "reactive[key]<=battery.pcs_kva*connected": "reactive[key]<=250.*connected",
        "reactive[key]>=-battery.pcs_kva*connected": "reactive[key]>=-250.*connected",
    }
    for old,new in edits.items():
        if source.count(old)!=1:raise ValueError('Q250_ORIGINAL_BUILD_BOUNDARY_DRIFT:'+old)
        source=source.replace(old,new)
    # The original constructor temporarily patches native.optimize to capture
    # a Native0 model. Resolve that patch at call time, as the original solve
    # function does; never retain the pre-scope optimizer in cloned globals.
    namespace=dict(original.__globals__,optimize=lambda *a,**kw:original.__globals__['optimize'](*a,**kw))
    exec(compile(source,original.__code__.co_filename,'exec'),namespace)
    return namespace[original.__name__]


def pcs_vertices(case):
    """Intersect original PCS400/P300 polygon with Q +/-250, including edges."""
    from v42_ultracompact.current_verify import physical_pcs_authority
    from v42_ultracompact.polytope import vertices
    planes=physical_pcs_authority(case.original_A,case.original_d,case.graph)
    limit=F(float(case.graph[3].p_limit));q=F(Q_LIMIT)
    points=vertices(planes+[(F(1),F(0),limit),(F(-1),F(0),limit),
        (F(0),F(1),q),(F(0),F(-1),q)])
    if not points:raise ValueError('Q250_PCS_CONTEXT_EMPTY')
    return np.asarray([[float(p),float(q)] for p,q in points])


def check_plan(plan):
    values=[float(q) for series in plan['Q_kvar'].values() for q in series]
    if not values or any(not math.isfinite(q) or abs(q)>Q_LIMIT+1e-5 for q in values):
        raise ValueError('Q250_FULL_PLAN_OPERATING_LIMIT_VIOLATION')
    return dict(PASS=True,per_vehicle_max_abs_Q_kvar={u:max(map(abs,v),default=0.) for u,v in plan['Q_kvar'].items()},
        limit_kvar=Q_LIMIT,commands_clipped=False)


def bind_case(case,request):
    """Bind the changed numeric domain and the policy into every M Case SHA."""
    from .frozen.v43_mess.library import current_identity
    mask=np.asarray([str(n).startswith('Q[') for n in case.original_d['names']])
    if (not mask.any() or not np.all(case.original_d['lower'][mask]==-Q_LIMIT)
            or not np.all(case.original_d['upper'][mask]==Q_LIMIT)):
        raise ValueError('Q250_ORIGINAL_FULL_BOUND_COVER_REQUIRED')
    if case.graph[3].pcs_kva!=400. or case.graph[3].p_limit!=300.:
        raise ValueError('Q250_MUST_PRESERVE_PCS400_P300')
    case.identity=dict(case.identity,Q_operating_policy=POLICY,Q_operating_limit_kvar=Q_LIMIT,
        Q250_M4_policy_sha=request['Q250_M4_policy_sha'])
    case.case_sha=digest(case.identity);current_identity(case)
    atomic(case.output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**case.identity))
    atomic(case.output/'Q250_FULL_DOMAIN_AUDIT.json',dict(PASS=True,policy=POLICY,
        policy_sha=request['Q250_M4_policy_sha'],case_sha=case.case_sha,Q_columns=int(mask.sum()),
        lower_kvar=-Q_LIMIT,upper_kvar=Q_LIMIT,PCS_kVA=400.,P_limit_kW=300.,
        original_matrix_sha=case.identity['original_matrix_sha'],
        original_domain_sha=case.identity['original_domain_sha'],prior_M_case_imported=False))
    return case


@contextmanager
def q_domain():
    import v42_native.mess as native
    from .frozen.v43_mess.library import load
    from . import runtime
    modules=load();c=modules['m_candidates'];engine=modules['m_engine'];build=runtime.build
    prior_vertices=getattr(c,'_v43_original_vertices',c.pcs_vertices)
    had_original=hasattr(c,'_v43_original_vertices');export=engine.export_plan
    def export_plan(case,point):
        plan=export(case,point);audit=check_plan(plan)
        atomic(Path(getattr(case,'mess_execution_folder',case.output/'COMMON_M_PR222'))/'Q250_PLAN_AUDIT.json',
            dict(audit,policy=POLICY,case_sha=case.case_sha,plan_sha=plan['plan_sha']))
        return plan
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(native,'solve',native_adapter(native.solve)))
            stack.enter_context(patch.object(runtime,'build',lambda payload,request,progress=None:
                bind_case(build(payload,request,progress),request)))
            stack.enter_context(patch.object(c,'pcs_vertices',pcs_vertices))
            if had_original:stack.enter_context(patch.object(c,'_v43_original_vertices',pcs_vertices))
            stack.enter_context(patch.object(engine,'export_plan',export_plan))
            yield
    finally:
        # performance.install captures its original functions once per process.
        # Restore that captured authority too before a later B3 M2/A scope.
        if not had_original and hasattr(c,'_v43_original_grid_context'):
            c._v43_original_vertices=prior_vertices


@contextmanager
def m_threads(request):
    if not serial_m2.is_m(request) or request.get('Threads')!=4 or request.get('worker_slot')!=1:
        raise PermissionError('ONLY_SINGLE_SLOT_EXPLICIT_M_THREADS4')
    from v42_may_campaign import execution as legacy
    from v42_may_campaign_native90 import execution as inherited,budget as native_budget
    from .frozen.v43_mess.library import load
    modules=load();engine=modules['m_engine'];k48=modules['table_v_k48']
    native=serial_m2.route_source(native_budget.DateBudget.native_optimize,
        'model.Params.Threads = 1','model.Params.Threads = 4',guard=lambda model:native_budget.guard(model))
    def guard(original):
        return serial_m2.route_source(original,'if int(model.Params.Threads) != 1:',
            'if int(model.Params.Threads) != 4:')
    joint=barrier.parameters(engine.APPROVED_JOINT_PARAMETERS,request['day'],request['stage'],request['arm'])
    joint.update(Threads=4,Method=2,MIPGap=.03)
    lower=dict(k48.ORIGINAL_NATIVE_PARAMETERS,Threads=4,Method=2)
    with ExitStack() as stack:
        stack.enter_context(patch.object(native_budget.DateBudget,'native_optimize',native))
        stack.enter_context(patch.object(legacy,'guard',guard(legacy.guard)))
        stack.enter_context(patch.object(inherited,'guard',guard(inherited.guard)))
        stack.enter_context(patch.object(engine,'APPROVED_JOINT_PARAMETERS',joint))
        stack.enter_context(patch.object(k48,'ORIGINAL_NATIVE_PARAMETERS',lower))
        yield dict(Joint=joint,K48=lower)


@contextmanager
def install(path=PERMIT):
    permit=validate(path)
    from . import execution,worker,campaign,checkpoints
    with cap300.install(path):
        old_guard=execution.assert_current;old_stage=worker.m_stage;old_request=campaign.stage_request
        old_envelope=checkpoints.envelope
        def guard():
            value=old_guard();validate(path);request=value['request']
            if request.get('Q250_M4_policy_sha')!=permit['Q250_M4_policy_sha'] or request.get('worker_slot')!=1:
                raise PermissionError('Q250_M4_REQUEST_POLICY_REQUIRED')
            if request.get('resume_of') or request.get('resume_parent'):
                raise PermissionError('Q250_REQUIRES_FRESH_M_NO_OLD_CHECKPOINT')
            return value
        def stage_request(case,stage):
            request=old_request(case,stage);request['Threads']=4 if serial_m2.is_m(request) else 1
            return request
        def envelope(*args,**kwargs):
            value=old_envelope(*args,**kwargs)
            value.update(Q250_M4_overlay=permit['Q250_M4_overlay'],Q250_M4_policy_sha=permit['Q250_M4_policy_sha'])
            value['checkpoint_sha']=digest({k:v for k,v in value.items() if k!='checkpoint_sha'})
            return value
        @wraps(old_stage)
        def stage(request,aidc):
            if request.get('resume_parent'):raise PermissionError('Q250_FRESH_M_REQUIRED')
            with m_threads(request) as parameters,q_domain():
                atomic(Path(request['case_root'])/(request['stage']+'.Q250_M4_POLICY.json'),dict(
                    UTC=now(),Q250_M4_overlay=permit['Q250_M4_overlay'],Q250_M4_policy_sha=permit['Q250_M4_policy_sha'],
                    effective_parameters=parameters,fresh_M_stage=True))
                return old_stage(request,aidc)
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'assert_current',guard))
            stack.enter_context(patch.object(worker,'m_stage',stage))
            stack.enter_context(patch.object(campaign,'stage_request',stage_request))
            stack.enter_context(patch.object(checkpoints,'envelope',envelope))
            yield permit


def coordinator_run(root,path=PERMIT):
    from . import campaign
    permit=validate(path);original_atomic=campaign.atomic
    def write(target,value):
        if Path(target).parent.name=='requests' and isinstance(value,dict) and 'case_root' in value:
            sources=list({r['path']:r for r in value['sources']+
                [permit['Q250_M4_overlay']['source']]+permit['Q250_M4_overlay']['adapter_sources']}.values())
            value=dict(value,execution_policy_sha=permit['execution_policy_sha'],operational_overlay=permit['operational_overlay'],
                numerical_overlay=permit['numerical_overlay'],numerical_policy_sha=permit['numerical_policy_sha'],
                Q250_M4_overlay=permit['Q250_M4_overlay'],Q250_M4_policy_sha=permit['Q250_M4_policy_sha'],Joint_call_cap_seconds=300.,
                sources=sources,source_sha=digest(sources))
        original_atomic(target,value)
    def launch(command,**kwargs):
        command=list(command);index=command.index('-m')+1
        if command[index]!='v44.campaign':raise PermissionError('ONLY_Q250_CAMPAIGN_WORKER')
        command[index]='v44.q250_m4_v2';command+=['--permit',str(path)]
        return subprocess.Popen(command,**kwargs)
    fn=campaign.run
    namespace=dict(fn.__globals__,assignments=serial_m2.assignments,atomic=write,
        subprocess=SimpleNamespace(Popen=launch,CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    run=FunctionType(fn.__code__,namespace,fn.__name__,fn.__defaults__,fn.__closure__);run.__kwdefaults__=fn.__kwdefaults__
    with install(path):return run(root,path,resume=False)


def thread_smoke(output,path=PERMIT):
    """Two-variable guard smoke outside campaign; no physical simulation."""
    import gurobipy as gp
    from .locks import coordinator,worker_slot,process_identity
    from .execution import case_scope,native_stage
    from v42_may_campaign_native90.budget import DateBudget
    permit=validate(path);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    request=read(RUNTIME/'v43_planning_svr12_actual_v1/campaign001/2025-05-01/B2/attempt001/M1/request.json')
    request.update(case_root=str(output/'case'),campaign_root=str(output),root=str(output/'M1'),output=str(output/'M1'),
        worker_slot=1,Threads=4,execution_permit=record(path),execution_policy_sha=permit['execution_policy_sha'],
        Q250_M4_policy_sha=permit['Q250_M4_policy_sha'])
    atomic(output/'PHASE.json',dict(lane='B2',UTC=now()))
    with coordinator(output) as lease:
        request['lease']=lease;who=dict(**process_identity(),day=request['day'],arm='B2',worker_slot=1)
        with worker_slot(request['day'],'B2',1,root=output,lease=lease),case_scope(request,lease,who),install(path),m_threads(request),native_stage(request):
            model=gp.Model('Q250_THREADS4_GUARD_SMOKE')
            try:
                x=model.addVar(lb=-Q_LIMIT,ub=Q_LIMIT,obj=1.);y=model.addVar(vtype='B')
                model.addConstr(x>=-200.+y);model.update()
                budget=DateBudget(output/'NATIVE_LEDGER.json',native_limit=1.)
                budget.optimize(model,track='M',label='Q250_THREADS4_GUARD_SMOKE',requested_seconds=1.)
                result=dict(UTC=now(),PASS=model.Status==gp.GRB.OPTIMAL and model.Params.Threads==4,
                    observed_Threads=model.Params.Threads,Native_seconds=model.Runtime,Native_calls=len(budget.calls),
                    Q250_M4_policy_sha=permit['Q250_M4_policy_sha'],physical_simulation=False,campaign_case=False)
                atomic(output/'RESULT.json',result);return result
            finally:model.dispose()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--permit',type=Path,default=PERMIT)
    parser.add_argument('--worker',type=Path);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--thread-smoke',type=Path);parser.add_argument('--root',type=Path,default=CAMPAIGN)
    args=parser.parse_args()
    if args.worker:
        with install(args.permit):
            from .campaign import run_case
            run_case(read(args.worker))
    elif args.thread_smoke:thread_smoke(args.thread_smoke,args.permit)
    elif args.execute:coordinator_run(args.root,args.permit)
    else:raise PermissionError('EXPLICIT_Q250_M4_EXECUTION_REQUIRED')


if __name__=='__main__':main()
