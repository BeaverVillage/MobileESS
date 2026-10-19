"""User-authorized fresh A2 from the verified completed May02 B3 M1 boundary."""
from pathlib import Path
from v44.common import read,record,verify,atomic,now


def run(request):
    from v44.locks import process_identity,worker_slot
    from v44.execution import case_scope
    from v44.campaign import stage_request
    from v44.checkpoints import checked,assert_dead
    from v44.daily import load_aidc
    from v44.stages import require_m1,require_a2
    from v44 import worker
    parent=Path(request['fresh_a2_parent']);assert_dead(parent)
    if (request['day'],request['arm'],parent.name)!=('2025-05-02','B3','attempt001'):
        raise PermissionError('R025_ONLY_USER_AUTHORIZED_MAY02_B3_FRESH_A2')
    overlay=request['autonomous_recovery_overlay'];policy=overlay.get('fresh_A2_restart',{})
    if policy.get('Native_clock_reset') is not False or policy.get('reuse_completed_M1') is not True:
        raise PermissionError('R025_EXPLICIT_FRESH_A2_ZERO_NATIVE_POLICY_REQUIRED')
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    def progress(stage):atomic(root/'progress.json',dict(day=request['day'],arm=request['arm'],stage=stage,status='RUNNING',pid=who['pid'],UTC=now()))
    with worker_slot(request['day'],request['arm'],1,root=request['campaign_root'],lease=request['lease']),case_scope(request,request['lease'],who):
        try:
            from .parent_admission import validate as validate_parent
            compatibility=validate_parent(parent,root/'PARENT_VERIFICATION',request)
            old=read(parent/'M1/request.json');checked(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
            m1=read(parent/'M1/RESULT.json');require_m1(m1,request['day'])
            a1=read(parent/'A1_REUSE.json');verify([a1['AIDC_reference']])
            atomic(root/'A1_REUSE.json',dict(a1,new_optimization_calls=0))
            atomic(root/'RESTORED_COMPLETED_STAGES.json',dict(M1=dict(root=str(parent/'M1'),checkpoint=record(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json'),new_Native_calls=0)))
            atomic(root/'FRESH_A2_RESTART_ADMISSION.json',dict(UTC=now(),PASS=True,authorization=record(Path(request['campaign_root'])/'AUTONOMOUS_RECOVERY/R025_USER_AUTHORIZATION.json'),
                completed_M1_checkpoint=record(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json'),M1_plan_sha=m1['MESS_plan']['plan_sha'],
                A2_Native_start=policy['Native_start'],A2_total_native_budget=3600.,previous_A2_time_imported=True,
                Native_clock_reset=False,previous_A2_point_or_support_imported=True,new_A1_or_M1_Native_calls=0,
                parent_compatibility=record(root/'PARENT_VERIFICATION/R025_PARENT_COMPATIBILITY.json')))
            progress('A2');stage=stage_request(request,'A2');previous=read(parent/'A2/request.json')
            stage.update(physical_domain_request=previous['physical_domain_request'],physical_cache_case_proof=previous['physical_cache_case_proof'],M1_result=record(parent/'M1/RESULT.json'))
            continuation=read(request['r025_continuation']['path'])
            verify(continuation['sources']+[continuation['checkpoint'],continuation['native_parent']])
            stage.update(r025_state_checkpoint=continuation['checkpoint'],r025_native_parent=continuation['native_parent']['path'])
            a2=worker.a_stage(stage,m1=m1);require_a2(a2,request['day'])
            folder=Path(a2['AIDC_reference']['path']).parent;aidc,_=load_aidc(folder,request['day'])
            progress('M2');m2=worker.m_stage(stage_request(request,'M2'),aidc)
            if not m2['allow_downstream']:raise RuntimeError(m2['status'])
            progress('ACTUAL_FRESH');actual=stage_request(request,'ACTUAL');actual['MESS_result']=str(root/'M2/RESULT.json')
            result.update(worker.actual(actual,folder,m2['MESS_plan']))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',fresh_A2_restarted=False,
                A2_policy_continued=True,M1_reoptimized=False,A2_Native_start=policy['Native_start'],Native_clock_reset=False)
        except BaseException as error:
            import traceback
            result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result
