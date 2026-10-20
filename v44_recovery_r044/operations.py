"""Safe boundary continuation of May08 B3, then the existing 1/7/1 campaign."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import argparse,os,sys,subprocess,time,traceback
import v44_recovery_r043
from v44_week2 import operations as week
import v44_week2_sequence as sequence
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,worker_slot,process_identity

CAMPAIGN,OPS,STATE=week.CAMPAIGN,week.OPS,week.STATE
PARENT=CAMPAIGN/'2025-05-08/B3/attempt001'
TARGET=CAMPAIGN/'2025-05-08/B3/attempt002'
PERMIT=OPS/'R044_MAY08_B3_RECOVERY_AUTHORIZATION.json'
VALIDATION=OPS/'R044_VALIDATION.json'
ENTRY='v44_recovery_r044.operations'
REASON='R044_MAY08_B3_CONTINUOUS_REPAIR_NATURAL_BOUNDARY'
_week_authority=week.authority
_sequence_new_request=sequence.new_request


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    sequence.authority();v=read(PERMIT)
    verify(v['sources']+[v['previous_authorization'],v['validation']]+v['evidence'])
    if (v['sources']!=sources() or v['previous_authorization']!=record(sequence.AUTH)
        or not read(v['validation']['path'])['PASS'] or v.get('target')!=str(TARGET)
        or v.get('Native_clock_reset') is not False or v.get('M1_reoptimized') is not False):
        raise PermissionError('R044_SEALED_EXACT_CASE_RECOVERY_REQUIRED')
    return v


def target_request(request):
    return (request.get('day'),request.get('arm'),Path(request.get('case_root',''))) == ('2025-05-08','B3',TARGET)


def request_authority(request=None):
    if request is None or not target_request(request):return _week_authority(request)
    v=read(PERMIT);verify(v['sources']+[record(PERMIT),v['validation']])
    if (v['sources']!=sources() or request.get('R044_authorization')!=record(PERMIT)
        or request.get('R044_parent')!=str(PARENT) or not read(v['validation']['path'])['PASS']):
        raise PermissionError('R044_EXPLICIT_ATTEMPT002_AUTHORITY_REQUIRED')
    # Retain every original date, group, source, worker and execution-permit
    # gate. Only this explicitly sealed attempt location is extended.
    return _week_authority(dict(request,case_root=str(PARENT)))


def validate_parent():
    from v44.checkpoints import assert_dead,checked,ledger_state
    from v44.stages import require_m1
    assert_dead(PARENT)
    old=read(PARENT/'M1/request.json');checked(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
    m1=read(PARENT/'M1/RESULT.json');require_m1(m1,'2025-05-08')
    failure=read(PARENT/'A2/RESULT.json')
    if 'A_CERTIFIED_LB_UB_CONFLICT' not in failure.get('error',''):
        raise PermissionError('R044_ONLY_DIAGNOSED_A2_BOUND_CONFLICT')
    account=ledger_state(PARENT/'A2/NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    if abs(account['measured']-12.59800386428833)>1e-7:
        raise PermissionError('R044_ORIGINAL_A2_NATIVE_ACCOUNT_DRIFT')
    ledger_state(PARENT/'M1/K48_NATIVE_LEDGER.json',ceiling=300.)
    ledger_state(PARENT/'M1/JOINT_NATIVE_LEDGER.json',ceiling=900.)
    return old,m1,account


def repaired_case(request):
    from v44 import worker
    from v44.campaign import stage_request
    from v44.execution import case_scope
    from v44.daily import load_aidc
    from v44_recovery_r029.voltage_policy import require_handoff
    from .numerical import scope
    authority();request_authority(request)
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    def progress(stage):atomic(root/'progress.json',dict(day=request['day'],arm=request['arm'],stage=stage,status='RUNNING',pid=who['pid'],UTC=now()))
    with worker_slot(request['day'],request['arm'],1,root=CAMPAIGN,lease=request['lease']),case_scope(request,request['lease'],who):
        try:
            old,m1,account=validate_parent()
            if old['scientific_source_sha']!=request['scientific_source_sha']:raise PermissionError('R044_SCIENTIFIC_FREEZE_DRIFT')
            a1=read(PARENT/'A1_REUSE.json');verify([a1['AIDC_reference']]);atomic(root/'A1_REUSE.json',a1)
            atomic(root/'RESTORED_COMPLETED_STAGES.json',dict(M1=dict(root=str(PARENT/'M1'),
                checkpoint=record(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json'),new_Native_calls=0)))
            atomic(root/'R044_RECOVERY_ADMISSION.json',dict(PASS=True,UTC=now(),authorization=record(PERMIT),
                original_failure=record(PARENT/'A2/RESULT.json'),completed_M1=record(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json'),
                M1_reoptimized=False,Native_clock_reset=False,inherited_A2_Native_seconds=account['measured'],
                total_A2_Native_ceiling=5400.,fixed_M1_plan_sha=m1['MESS_plan']['plan_sha']))
            progress('A2');stage=stage_request(request,'A2');previous=read(PARENT/'A2/request.json')
            stage.update(physical_domain_request=previous['physical_domain_request'],
                physical_cache_case_proof=previous['physical_cache_case_proof'],M1_result=record(PARENT/'M1/RESULT.json'))
            with scope():a2=worker.a_stage(stage,m1=m1)
            require_handoff(a2,request['day'])
            folder=Path(a2['AIDC_reference']['path']).parent;aidc,_=load_aidc(folder,request['day'])
            progress('M2');m2=worker.m_stage(stage_request(request,'M2'),aidc)
            if not m2['allow_downstream']:raise RuntimeError(m2['status'])
            stage=stage_request(request,'ACTUAL');stage['MESS_result']=str(root/'M2/RESULT.json')
            result.update(week.prepare_actual(stage,folder,m2['MESS_plan']),status='PRE_ACTUAL_READY',
                reused_completed_M1=True,new_M1_Native_calls=0,inherited_A2_Native_seconds=account['measured'])
            progress('PRE_ACTUAL_READY')
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result


def require_live():
    from v44.execution import assert_current
    return request_authority(assert_current()['request'])


def worker(path):
    authority();request=read(path);sequence.authority(request)
    if not target_request(request) or request['r038_phase']!='PREPARE_SERIAL':return sequence.worker(path)
    from v44_recovery_r038 import operations as inherited
    from v44_recovery_r029 import conditional_campaign
    from v44_recovery_r039 import latency
    from v44_recovery_r041.preparation import deny_actual
    from v44 import worker as science
    with inherited.previous.install(),latency.install(require_live),patch.object(conditional_campaign,'run_case',repaired_case),patch.object(science,'actual',deny_actual):
        return inherited.base.worker(request)


def new_request(job,lease,mode):
    if sequence.key(job)!=('2025-05-08','B3'):return _sequence_new_request(job,lease,mode)
    if mode!='MAIN':raise PermissionError('R044_MAIN_PREPARATION_ONLY')
    request=read(OPS/'requests/2025-05-08_B3.json')
    request.update(case_root=str(TARGET),lease=lease,R044_authorization=record(PERMIT),R044_parent=str(PARENT),
        r038_phase='PREPARE_SERIAL',sequence_mode='MAIN',sequence_authorization=record(sequence.AUTH))
    request['sources']=list({r['path']:r for r in request['sources']+sources()+[record(PERMIT)]}.values())
    request['source_sha']=digest(request['sources']);request_authority(request)
    path=OPS/'requests/2025-05-08_B3_R044.json';atomic(path,request)
    job.update(case_root=str(TARGET),prepare_request=str(path),status='PREPARING',recovery_authorization=record(PERMIT))
    return path


def transition():
    authority()
    with exclusive_lock(OPS/'R044_CONTROLLER.lock'):
        while True:
            state=read(STATE);stop=read(sequence.STOP) if sequence.STOP.exists() else {}
            if stop.get('reason')!=REASON or stop.get('R044_authorization')!=record(PERMIT):
                atomic(OPS/'R044_NEW_USER_STOP_PRESERVED.json',dict(UTC=now(),stop=stop));return
            active=[]
            for job in state['jobs']:
                if job.get('case_root'):
                    for name in ('START.json','ACTUAL_START.json'):
                        p=Path(job['case_root'])/name
                        if p.exists() and alive(read(p)):active.append(read(p))
            atomic(OPS/'R044_TRANSITION_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                old_coordinator_alive=alive(state.get('lease')),active_workers=[p['pid'] for p in active]))
            if not alive(state.get('lease')) and not active:break
            time.sleep(5)
        if any(j['status'] in ('PREPARING','ACTUAL_RUNNING','BASELINE_RUNNING') for j in state['jobs']):
            raise PermissionError('R044_UNRECONCILED_OLD_WORKER_STATE')
        target=next(j for j in state['jobs'] if sequence.key(j)==('2025-05-08','B3'))
        if target['status']!='EXCLUDED' or target['case_root']!=str(PARENT) or TARGET.exists():
            raise PermissionError('R044_ORIGINAL_FAILED_CASE_AND_FRESH_ATTEMPT_REQUIRED')
        validate_parent();atomic(OPS/'R044_STATE_BEFORE_RECOVERY.json',state)
        for field in ('result','process_exit','exclusion_reason','traceback','handoff','actual_request','parallel_slot'):target.pop(field,None)
        target['status']='PENDING';state['R044_recovery_authorization']=record(PERMIT)
        atomic(STATE,state);atomic(OPS/'R044_NATURAL_BOUNDARY_ADOPTED.json',dict(UTC=now(),
            old_state=record(OPS/'R044_STATE_BEFORE_RECOVERY.json'),sources_unchanged=True,worker_interrupted=False,
            previous_preparations_preserved=True,authorization=record(PERMIT)))
        atomic(OPS/'R044_TRANSITION_STOP_PRESERVED.json',stop);sequence.STOP.unlink()
        pointer=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json');value=read(pointer)
        value.update(UTC=now(),operational_recovery=record(PERMIT),operational_entry=ENTRY)
        atomic(pointer,value)
        return sequence.run()


@contextmanager
def bindings():
    with week.bindings(),patch.object(week,'authority',request_authority),patch.object(sequence,'new_request',new_request),patch.object(sequence,'ENTRY',ENTRY):yield


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--transition',action='store_true');args=parser.parse_args()
    with bindings():
        try:
            if args.worker:return worker(args.worker)
            if args.transition:return transition()
            parser.error('Choose --worker or --transition')
        except BaseException as error:
            atomic(OPS/'R044_CONTROLLER_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':main()
