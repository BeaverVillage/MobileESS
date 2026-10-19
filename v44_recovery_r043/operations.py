"""Repair cache reference metadata; preserve every scientific execution gate."""
from pathlib import Path
from unittest.mock import patch
import argparse, os, subprocess, sys, traceback
from v44_recovery_r042 import operations as actual
from v44_recovery_r041 import operations as prep
from v44.common import read, record, verify, atomic, now
from v44.locks import coordinator, worker_slot, process_identity, exclusive_lock, alive

CAMPAIGN,OPS,STATE=actual.CAMPAIGN,actual.OPS,actual.STATE
PARENT=CAMPAIGN/'2025-05-07/B3/attempt001'
PERMIT=OPS/'R043_MAY07_B3_RECOVERY_AUTHORIZATION.json'
ENTRY='v44_recovery_r043.operations'

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def authority():
    actual.authority();v=read(PERMIT)
    verify(v['sources']+[v['previous_authorization'],v['validation']])
    if v['sources']!=sources() or v['previous_authorization']!=record(actual.AMENDMENT) or not read(v['validation']['path'])['PASS']:
        raise PermissionError('R043_RECOVERY_SOURCE_OR_VALIDATION_DRIFT')
    if v.get('day')!='2025-05-07' or v.get('arm')!='B3' or not v.get('finish_Planning_Actual_Fresh'):
        raise PermissionError('R043_EXPLICIT_MAY07_B3_USER_AUTHORITY_REQUIRED')
    return v

def corrected_owner(request):
    """Restore the producer location, without changing cache or domain evidence."""
    r=dict(request);proof=read(r['physical_cache_case_proof']['path'])
    verify([r['physical_cache_case_proof'],proof['result'],proof['cache']]+proof['sources']+list(proof['inputs'].values()))
    result=read(proof['result']['path']);stage=Path(proof['result']['path']).resolve().parent
    campaign=Path(r['campaign_root']).resolve()
    if (r.get('day'),r.get('arm'),r.get('stage'))!=('2025-05-07','B1','A1'):
        raise PermissionError('R043_SAME_MAY07_B1_A1_ONLY')
    if (stage.name!='A1' or stage.parent.parent!=campaign/'2025-05-07/B1'
        or proof.get('day')!=r['day'] or not result.get('PASS') or not result.get('FULL_feasible')
        or not result.get('independent_Global_LB_validated') or not 0<=result.get('certified_gap',1)<=.005):
        raise PermissionError('R043_CERTIFIED_ORIGINAL_CACHE_OWNER_REQUIRED')
    r.update(root=str(stage),case_root=str(stage.parent))
    return r

def validate_parent():
    from v44.checkpoints import checked, assert_dead, ledger_state
    from v44.stages import require_m1
    assert_dead(PARENT);old=read(PARENT/'M1/request.json')
    checked(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
    m1=read(PARENT/'M1/RESULT.json');require_m1(m1,'2025-05-07')
    failure=read(PARENT/'A2/RESULT.json');ledger=read(PARENT/'A2/NATIVE_RUNTIME_LEDGER.json')
    if (failure.get('error')!="RuntimeError('A2_REQUIRED_COMPLETE_LOCAL_DOMAIN_REUSE_FAILED')"
        or failure.get('Native_seconds')!=0 or ledger.get('measured_Native_Runtime')!=0 or ledger.get('inflight')):
        raise PermissionError('R043_ONLY_DIAGNOSED_ZERO_NATIVE_A2_CACHE_FAILURE')
    ledger_state(PARENT/'M1/K48_NATIVE_LEDGER.json',ceiling=300.)
    ledger_state(PARENT/'M1/JOINT_NATIVE_LEDGER.json',ceiling=900.)
    return old,m1

def repaired_case(request):
    from v44 import worker
    from v44.campaign import stage_request
    from v44.execution import case_scope
    from v44.daily import load_aidc
    from v44_recovery_r029.voltage_policy import require_handoff
    from v44_recovery_r038.phases import prepare_actual
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    def progress(stage):atomic(root/'progress.json',dict(day=request['day'],arm=request['arm'],stage=stage,status='RUNNING',pid=who['pid'],UTC=now()))
    with worker_slot(request['day'],request['arm'],1,root=request['campaign_root'],lease=request['lease']),case_scope(request,request['lease'],who):
        try:
            old,m1=validate_parent()
            if old['scientific_source_sha']!=request['scientific_source_sha']:raise PermissionError('R043_SCIENTIFIC_FREEZE_DRIFT')
            verify(old['sources'])
            a1=read(PARENT/'A1_REUSE.json');verify([a1['AIDC_reference']])
            atomic(root/'A1_REUSE.json',a1)
            atomic(root/'RESTORED_COMPLETED_STAGES.json',dict(M1=dict(root=str(PARENT/'M1'),checkpoint=record(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json'),new_Native_calls=0)))
            atomic(root/'R043_RECOVERY_ADMISSION.json',dict(UTC=now(),PASS=True,authorization=record(PERMIT),
                completed_M1=record(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json'),original_M1_Native_seconds=m1['Native_seconds'],
                A2_original_Native_seconds=0,new_M1_Native_calls=0,cache_reference_repaired=True,scientific_model_changed=False))
            progress('A2');stage=stage_request(request,'A2')
            domain=read(CAMPAIGN/'B1_A1/2025-05-07.request.json')
            stage.update(physical_domain_request=domain,physical_cache_case_proof=domain['physical_cache_case_proof'],M1_result=record(PARENT/'M1/RESULT.json'))
            a2=worker.a_stage(stage,m1=m1);require_handoff(a2,request['day'])
            folder=Path(a2['AIDC_reference']['path']).parent;aidc,_=load_aidc(folder,request['day'])
            progress('M2');m2=worker.m_stage(stage_request(request,'M2'),aidc)
            if not m2['allow_downstream']:raise RuntimeError(m2['status'])
            stage=stage_request(request,'ACTUAL');stage['MESS_result']=str(root/'M2/RESULT.json')
            result.update(prepare_actual(stage,folder,m2['MESS_plan']),status='PRE_ACTUAL_READY',reused_completed_M1=True,new_M1_Native_calls=0)
            progress('PRE_ACTUAL_READY')
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result

def worker(path):
    authority();r=read(path);prep.previous.authorize(r)
    if r.get('R043_authorization')!=record(PERMIT) or r.get('r038_phase')!='PREPARE_SERIAL' or (r['day'],r['arm'])!=('2025-05-07','B3'):
        raise PermissionError('R043_EXPLICIT_PREPARATION_REQUEST_REQUIRED')
    if not prep.allowed():raise PermissionError('R043_PREPARATION_FENCE_REQUIRED')
    from v44_recovery_r041.preparation import install
    from v44_recovery_r029 import conditional_campaign
    with prep.previous.original.install(r),install(r),patch.object(conditional_campaign,'run_case',repaired_case):return prep.base.worker(r)

def run():
    from v44_recovery_r038 import batch as inherited
    from v44_recovery_r040 import batch
    authority()
    with exclusive_lock(OPS/'R043_RECOVERY_SUPERVISOR.lock'),coordinator(CAMPAIGN) as lease:
        if (OPS/'STOP_AUTONOMY.json').exists():raise PermissionError('R043_NEW_USER_STOP_PRESERVED')
        state=read(STATE)
        target=next(j for j in state['jobs'] if prep.key(j)==('2025-05-07','B3'))
        if target['status']=='PASS':return
        if target['status']!='EXCLUDED' or any(j['status']!='PASS' for j in state['jobs'] if j is not target):
            raise PermissionError('R043_ONLY_RETRY_EXCLUDED_MAY07_B3_AFTER_SIX_PASS')
        validate_parent()
        atomic(OPS/'R043_BATCH_BEFORE_RECOVERY.json',state)
        domain_path=CAMPAIGN/'B1_A1/2025-05-07.request.json';old_domain=read(domain_path)
        fixed=corrected_owner(old_domain)
        atomic(OPS/'R043_A1_CACHE_REQUEST_BEFORE.json',old_domain);atomic(domain_path,fixed)
        atomic(OPS/'R043_CACHE_OWNER_REPAIRED.json',dict(UTC=now(),before=record(OPS/'R043_A1_CACHE_REQUEST_BEFORE.json'),after=record(domain_path),
            original_A1_result=read(fixed['physical_cache_case_proof']['path'])['result'],changed_fields=['root','case_root'],source_or_cache_bytes_modified=False))
        atomic(OPS/'STOP_AUTONOMY.json',dict(UTC=now(),reason=prep.HOLD,allow_preparation=True,authorization=record(prep.AMENDMENT),
            auto_resume_after_preparations=record(actual.AMENDMENT),R043_authorization=record(PERMIT)))
        state.update(phase='PREPARE_SERIAL',lease=lease,all_PASS=False,Actual_paused_by_user=True)
        for field in ('exclusion','exclusion_receipt','result','process_exit','handoff','actual_request','parallel_slot'):target.pop(field,None)
        target['status']='PENDING'
        pointer=prep.new_request(target,lease,inherited.new_request);r=read(pointer)
        r['R043_authorization']=record(PERMIT);atomic(pointer,r);atomic(CAMPAIGN/'requests/2025-05-07_B3.json',r)
        atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='MAIN',r038_phase='PREPARE_SERIAL'))
        batch.publish(state)
        h=read(OPS/'CURRENT_HANDOFF.json');h.update(UTC=now(),active_revision='v44_recovery_r043',active_operational_entry=ENTRY,
            active_operational_permit=record(PERMIT),active_lease=lease,pending_revision='v44_recovery_r042',pending_permit=record(actual.AMENDMENT),
            Actual_auto_start_authorization=record(actual.AMENDMENT),next='Reuse May07 B3 M1, run corrected A2 then M2, then Actual/Fresh; preserve six completed PASS cases.')
        atomic(OPS/'CURRENT_HANDOFF.json',h)
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
        log=OPS/'r043_prepare.log'
        with log.open('ab') as stream:
            process=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',ENTRY,'--worker',str(pointer),'--algorithm',actual.ALGORITHM],cwd=Path(__file__).resolve().parents[1],env=env,
                stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        atomic(OPS/'R043_WORKER_LAUNCH.json',dict(UTC=now(),pid=process.pid,process_created=__import__('psutil').Process(process.pid).create_time(),request=record(pointer)))
        import time
        while process.poll() is None:batch.status(state,[(process,target)]);time.sleep(5)
        inherited.finish(process,target,'PREPARED');batch.publish(state);batch.status(state,[])
        if target['status']!='PREPARED':raise RuntimeError('R043_PREPARATION_FAILED_INSPECT_PRESERVED_RESULT')
        state['phase']='PRE_ACTUAL_USER_HOLD';batch.publish(state)
        manifest=batch.preflight(state);batch.publish(state)
        if target['status']!='PREPARED' or len(manifest['ready'])!=1:raise PermissionError('R043_VERIFIED_SINGLE_CASE_ACTUAL_HANDOFF_REQUIRED')
        if not actual.expected_hold(read(OPS/'STOP_AUTONOMY.json')):raise PermissionError('R043_NEW_USER_STOP_PRESERVED')
        atomic(OPS/'R043_PRE_ACTUAL_HOLD_PRESERVED.json',read(OPS/'STOP_AUTONOMY.json'));(OPS/'STOP_AUTONOMY.json').unlink()
        state['Actual_paused_by_user']=False
        actual.run_wave(lease,(state,manifest))
        final=read(STATE)
        atomic(OPS/'R043_FINAL_RESULT.json',dict(UTC=now(),PASS=final['all_PASS'],May07_B3=next(j for j in final['jobs'] if prep.key(j)==('2025-05-07','B3')),
            previously_completed_six_cases_preserved=True))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--algorithm',required=True,choices=[actual.ALGORITHM]);args=parser.parse_args()
    try:return worker(args.worker) if args.worker else run()
    except BaseException as error:
        atomic(OPS/'R043_RECOVERY_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':main()
