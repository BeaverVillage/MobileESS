from pathlib import Path
from types import SimpleNamespace,MethodType
import numpy as np
from scipy import sparse
from v44.common import read,record,verify,atomic,digest,now
from v44_recovery_r015.wall_resume import arrays
from .authorization import authorized_parent

def validate_b3_parent(parent, output):
    from v44.daily import load_aidc
    from v44.locks import alive
    from v44.checkpoints import checked
    from v44.planning import scope
    from v44.frozen.v43_mess.library import load, current_identity
    from v42_bootstrap.m1 import native_inputs
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_m1_research.check_ub import validate_candidate
    from v44.q250_m4_v2 import check_plan
    parent, output = Path(parent), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    stage = parent/'M2'; start = read(parent/'START.json')
    if alive(start):
        raise PermissionError('PARENT_WORKER_MUST_BE_DEAD')
    request = read(stage/'request.json')
    if (request['day'], request['arm'], request['stage']) != (parent.parent.parent.name, 'B3', 'M2'):
        raise PermissionError('SAME_DAY_B3_M2_ACTUAL_RESUME_ONLY')
    checked(stage/'BINARY_STAGE_CHECKPOINT.json', request, 'M_BINARY')
    verify(start['sources'])
    result = read(stage/'RESULT.json')
    checked(stage/'COMPLETED_STAGE_CHECKPOINT.json',request,'COMPLETED')
    if (not authorized_parent(parent)
            or not result['FULL_feasible'] or result.get('implementation_errors')
            or not result.get('allow_downstream') or not result.get('M_stage_execution_PASS')):
        raise PermissionError('ONLY_DIAGNOSED_OBSERVATION_FAILURE_WITH_HEALTHY_FULL_POINT')
    a2_request = dict(day=request['day'],arm='B3',stage='A2',source_sha=start['source_sha'],case_root=str(parent))
    checked(parent/'A2/COMPLETED_STAGE_CHECKPOINT.json',a2_request,'COMPLETED')
    a2 = read(parent/'A2/RESULT.json')
    if not a2.get('PASS') or not 0 <= a2.get('certified_gap',1) <= .005:
        raise PermissionError('ORIGINAL_A2_INDEPENDENT_GAP_REQUIRED')
    verify([a2['AIDC_reference']])
    aidc_folder = Path(a2['AIDC_reference']['path']).parent
    payload, _ = load_aidc(aidc_folder, request['day'])
    modules = load()
    with scope(request['day']):
        sites, initial, routes, battery, receipt = native_inputs(payload['bundle'])
        arcs = [(s,t,s,t+1,None) for s in sites for t in range(96)] + [
            (r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
        A, B = sparse.load_npz(stage/'FULL_A.npz'), sparse.load_npz(stage/'C3A_A.npz')
        data, selected = arrays(stage/'FULL_DATA.npz'), arrays(stage/'C3A_DATA.npz')
        identity = read(stage/'SCIENTIFIC_CASE_IDENTITY.json'); case_sha = identity.pop('case_sha')
        if (identity['aidc_anchor'] != payload['identity']['aidc_anchor'] or
                identity['source_sha'] != request['source_sha'] or
                (identity['day'],identity['arm'],identity['stage']) != (parent.parent.parent.name,'B3','M2')):
            raise PermissionError('PARENT_CASE_SOURCE_DATE_ARM_ANCHOR_DRIFT')
        compact = Compact(A, data, arcs, initial, 96)
        axes = arrays(stage/'CURRENT_C2_AXES.npz')
        inverse = SimpleNamespace(A=B, d=selected, col_ids=axes['columns'], row_ids=axes['rows'],
            initial_names=compact.d['names'], steps=read(stage/'CURRENT_C2_ALIASES.json'),
            rows=read(stage/'CURRENT_C2_ROW_PROOFS.json'), bound=read(stage/'CURRENT_C2_BOUND_PROOFS.json'))
        inverse.inverse = MethodType(Presolve.inverse, inverse)
        case = SimpleNamespace(original_A=A, original_d=data, A=B, d=selected,
            graph=(sites,initial,arcs,battery,receipt), case_sha=case_sha, identity=identity,
            bundle=payload['bundle'], output=output,
            lift=lambda point: compact.inverse(inverse.inverse(point)))
        current_identity(case)
        point = arrays(stage/'ACCEPTED_M_POINT.npz')['point']
        validation = validate_candidate(case, point)
        if not validation['PASS']:
            atomic(output/'FULL_REPLAY_FAILED.json', validation)
            raise PermissionError('PRESERVED_FULL_POINT_REPLAY_FAILED')
        plan = modules['m_engine'].export_plan(case, point)
        if plan != result['MESS_plan']:
            raise PermissionError('EXPORTED_FULL_PLAN_DIFFERS_FROM_PRESERVED_PLAN')
        q = check_plan(plan)
    from v44.checkpoints import ledger_state
    lower=ledger_state(stage/'K48_NATIVE_LEDGER.json',ceiling=300.)
    upper=ledger_state(stage/'JOINT_NATIVE_LEDGER.json',ceiling=900.)
    if (abs(lower['measured']-result['K48_Native_seconds'])>1e-7 or
            abs(upper['measured']-result['Joint_Native_seconds'])>1e-7):
        raise PermissionError('ORIGINAL_NATIVE_RUNTIME_RECONCILIATION_FAILED')
    reconciliation=dict(UTC=now(),K48=lower,Joint=upper,original_stage_result=record(stage/'RESULT.json'),
        actual_native_inflight=False,parent_worker_dead=True,original_ledger_modified=False,
        budget_reset=False,new_optimization_calls=0)
    atomic(output/'PARENT_NATIVE_RECONCILIATION.json', reconciliation)
    admission = dict(UTC=now(),PASS=True,parent=record(stage/'RESULT.json'),
        original_case_sha=case_sha, original_source_sha=request['source_sha'],
        FULL_replay=validation,Q250=q,plan_sha=plan['plan_sha'],
        global_gap_certified=result['global_gap_certified'],global_gap=result['Global_Gap'],
        independent_LB=result['Global_LB'],original_FULL_UB=result['Global_UB'],
        new_optimization_calls=0,original_failure_preserved=True,
        authorization='USER_20261017_EXPLICIT_STOP_AND_R015_ACTUAL_RESTART',
        downstream='UNCERTIFIED_GAP_ORIGINAL_FULL_PLAN_ACTUAL_FRESH_ONLY',
        Actual_Tap_Queue_context='NEW_INDEPENDENT_120_SLOT_CONTEXT')
    atomic(output/'ACTUAL_RESUME_ADMISSION.json', admission)
    return aidc_folder, plan, stage/'RESULT.json'

def run(request):
    from v44.locks import process_identity, worker_slot
    from v44.execution import case_scope
    from v44 import worker
    from v44.campaign import stage_request
    parent = Path(request['wall_resume_parent'])
    if (request['day'], request['arm']) != (parent.parent.parent.name, parent.parent.name):
        raise PermissionError('RESUME_REQUEST_PARENT_DATE_ARM_MISMATCH')
    root = Path(request['case_root']); root.mkdir(parents=True, exist_ok=False)
    who = dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
    result = dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    with worker_slot(request['day'],request['arm'],1,root=request['campaign_root'],lease=request['lease']), case_scope(request,request['lease'],who):
        try:
            from v42_may_campaign_native90.preflight import native_zero
            with native_zero() as denied:
                folder, plan, parent_result = validate_b3_parent(request['wall_resume_parent'],root/'PARENT_AUDIT')
            if denied:raise PermissionError('ACTUAL_RESUME_VALIDATION_NATIVE_OPTIMIZER_CALL_FORBIDDEN')
            atomic(root/'progress.json',dict(UTC=now(),stage='ACTUAL_FRESH',status='RUNNING',pid=who['pid']))
            stage = stage_request(request,'ACTUAL')
            stage['MESS_result'] = str(parent_result) if parent_result is not None else None
            result.update(worker.actual(stage,folder,plan))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',
                new_M_Native_calls=0,AIDC_parent_revalidated=True,user_authorized_r015_restart=True,performance_revision='v44_recovery_r015',
                Actual_context='NEW_INDEPENDENT_NO_PARTIAL_TAP_QUEUE_REUSE')
            if parent_result is not None:
                result.update(M_gap_certified=read(parent_result)['global_gap_certified'],M_plan_original_FULL_revalidated=True,
                    M_parent_result=record(parent_result))
        except BaseException as error:
            import traceback
            result.update(error=repr(error),traceback=traceback.format_exc())
        finally:
            result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result
