"""Resume May02 B3 after completed M1 and restored positive Phase I support."""
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
    from .a2_continue import scope,ADMISSION
    parent=Path(request['a2_checkpoint_parent']);assert_dead(parent)
    if (request['day'],request['arm'],parent.name)!=('2025-05-02','B3','attempt001'):
        raise PermissionError('R027_ONLY_EXPLICIT_MAY02_B3_CHECKPOINT')
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    def progress(stage):atomic(root/'progress.json',dict(day=request['day'],arm=request['arm'],stage=stage,status='RUNNING',pid=who['pid'],UTC=now()))
    with worker_slot(request['day'],request['arm'],1,root=request['campaign_root'],lease=request['lease']),case_scope(request,request['lease'],who):
        try:
            admission=read(ADMISSION);verify(admission['sources']+[admission['checkpoint'],admission['parent_request']])
            old=read(parent/'M1/request.json');checked(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
            m1=read(parent/'M1/RESULT.json');require_m1(m1,request['day'])
            if m1['MESS_plan']['plan_sha']!=admission['fixed_M1_plan_sha']:raise PermissionError('R027_M1_PLAN_DRIFT')
            a1=read(parent/'A1_REUSE.json');verify([a1['AIDC_reference']])
            atomic(root/'A1_REUSE.json',dict(a1,new_optimization_calls=0))
            atomic(root/'RESTORED_COMPLETED_STAGES.json',dict(M1=dict(root=str(parent/'M1'),
                checkpoint=record(parent/'M1/COMPLETED_STAGE_CHECKPOINT.json'),new_Native_calls=0)))
            atomic(root/'CHECKPOINT_RESUME_ADMISSION.json',dict(UTC=now(),PASS=True,admission=record(ADMISSION),
                original_failure=record(parent/'RESULT.json'),M1_plan_sha=m1['MESS_plan']['plan_sha'],
                Native_clock_reset=False,new_A1_or_M1_Native_calls=0))
            progress('A2');stage=stage_request(request,'A2')
            previous=read(parent/'A2/request.json')
            stage.update(physical_domain_request=previous['physical_domain_request'],
                physical_cache_case_proof=previous['physical_cache_case_proof'],M1_result=record(parent/'M1/RESULT.json'))
            with scope(stage):a2=worker.a_stage(stage,m1=m1)
            require_a2(a2,request['day'])
            folder=Path(a2['AIDC_reference']['path']).parent;aidc,_=load_aidc(folder,request['day'])
            progress('M2');m2=worker.m_stage(stage_request(request,'M2'),aidc)
            if not m2['allow_downstream']:raise RuntimeError(m2['status'])
            progress('ACTUAL_FRESH');actual=stage_request(request,'ACTUAL');actual['MESS_result']=str(root/'M2/RESULT.json')
            result.update(worker.actual(actual,folder,m2['MESS_plan']))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',
                resumed_A2_checkpoint=True,A2_checkpoint_start_solve=15,M1_reoptimized=False,
                A2_total_budget_seconds=5400.,A2_inherited_Native_seconds=admission['Native_account']['measured'])
        except BaseException as error:
            import traceback
            result.update(error=repr(error),traceback=traceback.format_exc())
        finally:
            result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result
