"""Failures are local; only an unresolved preparation delays the Actual wave."""
from pathlib import Path
from contextlib import contextmanager
import time,traceback
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r038 import batch as inherited,cpu
from v44_recovery_r038.phases import load_handoff
from v44_recovery_r029.cpu_placement import windows_cpu_sets
from . import operations as op

RESOLVED={'PREPARED','EXCLUDED','PASS','ACTUAL_FAILED'}

def resolved(jobs):return bool(jobs) and all(j['status'] in RESOLVED for j in jobs)

def validate_manifest(value,queue):
    expected={op.key(j) for j in queue}
    groups=[value.get(k,[]) for k in ('ready','excluded','already_complete')]
    flat=[op.key(j) for group in groups for j in group]
    if len(flat)!=len(expected) or len(set(flat))!=len(flat) or set(flat)!=expected:raise PermissionError('R040_EVERY_FIXED_CASE_MUST_BE_RESOLVED_ONCE')
    if not value.get('all_preparations_resolved') or not 0<=len(groups[0])<=7:raise PermissionError('R040_ALL_PREPARATIONS_RESOLVED_REQUIRED')
    if any(not j.get('reason') for j in groups[1]):raise PermissionError('R040_EXCLUSION_REASON_REQUIRED')
    if groups[0]:
        if len(value['cpu_placement']['slots'])!=len(groups[0]):raise PermissionError('R040_P_CPU_COUNT_MUST_MATCH_READY_CASES')
        if [j['slot'] for j in groups[0]]!=list(range(1,len(groups[0])+1)):raise PermissionError('R040_READY_SLOTS_MUST_BE_UNIQUE_AND_CONTIGUOUS')
        if any(not j.get('handoff') or not j.get('case_root') for j in groups[0]):raise PermissionError('R040_SEALED_READY_HANDOFF_REQUIRED')
    return value

def publish(state):
    state['UTC']=now();state['R040_authorization']=record(op.AMENDMENT);atomic(op.STATE,state)

def status(state,running):
    # A corrupt failed case journal must not break telemetry for every worker.
    try:previous=read(op.CAMPAIGN/'CAMPAIGN_STATUS.json')
    except (OSError,ValueError):previous={}
    from v44.config import DAYS,ARMS
    rows={op.key(r):r for r in previous.get('cases',[])}
    for day in DAYS:
        for arm in ARMS:rows.setdefault((day,arm),dict(day=day,arm=arm,status='READY'))
    labels=dict(PENDING='READY',PREPARING='RUNNING',PREPARED='PRE_ACTUAL_READY',ACTUAL_RUNNING='RUNNING',PASS='COMPLETE',ACTUAL_FAILED='FAILED',EXCLUDED='EXCLUDED')
    for job in state['jobs']:
        rows[op.key(job)]=dict(day=job['day'],arm=job['arm'],status=labels.get(job['status'],job['status']),exclusion=job.get('exclusion'))
    atomic(op.CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),r038_phase=state['phase'],r040_case_isolation=True,
        cases=list(rows.values()),workers=[dict(pid=p.pid,day=j['day'],arm=j['arm'],worker_slot=j.get('parallel_slot',1)) for p,j in running]))

def exclude(job,reason,**evidence):
    job.update(status='EXCLUDED',exclusion=dict(UTC=now(),reason=reason,**evidence))
    path=op.OPS/'R040_EXCLUSIONS'/f"{job['day']}_{job['arm']}.json"
    atomic(path,dict(day=job['day'],arm=job['arm'],case_root=job.get('case_root'),**job['exclusion'],authorization=record(op.AMENDMENT)))
    job['exclusion_receipt']=record(path)

def completed(job):
    root=Path(job['case_root']) if job.get('case_root') else None
    result=read(root/'RESULT.json') if root and (root/'RESULT.json').exists() else {}
    return result.get('PASS') is True

def check_ready(job):
    request=read(job['prepare_request']);verify(request['sources']+request.get('R039_sources',[])+request.get('R040_sources',[]))
    if any(request[k]!=job[k] for k in ('day','arm','case_root')):raise PermissionError('R040_JOB_REQUEST_AXIS_DRIFT')
    if completed(job):job.update(status='PASS',result=record(Path(job['case_root'])/'RESULT.json'));return
    request['R038_pre_actual_handoff']=job['handoff'];load_handoff(request)
    root=Path(job['case_root'])
    if (root/'ACTUAL').exists():raise PermissionError('R040_EXISTING_ACTUAL_MUST_NOT_BE_RESTARTED')

def reconcile(job):
    if completed(job):job.update(status='PASS',result=record(Path(job['case_root'])/'RESULT.json'));return
    if job['status']=='PREPARING':
        root=Path(job['case_root']);result=read(root/'RESULT.json') if (root/'RESULT.json').exists() else {}
        if result.get('status')=='PRE_ACTUAL_READY' and result.get('preparation_PASS'):
            job.update(status='PREPARED',handoff=result['pre_actual_handoff'])
        else:exclude(job,'PREPARATION_EXITED_WITHOUT_VERIFIED_READY_RESULT',original_result=result)
    elif job['status'] in ('PRE_FAILED','ACTUAL_FAILED'):
        exclude(job,'PREVIOUS_CASE_FAILURE',original_status=job['status'],original_error=job.get('dispatch_error'))
    elif job['status']=='ACTUAL_RUNNING':
        root=Path(job['case_root']);start=read(root/'ACTUAL_START.json') if (root/'ACTUAL_START.json').exists() else {}
        if alive(start):raise PermissionError('R040_LIVE_ACTUAL_CANNOT_BE_RECONCILED_OR_RESTARTED')
        exclude(job,'INTERRUPTED_ACTUAL_NOT_RESTARTED',partial_Actual_preserved=True)

def preflight(state):
    for job in state['jobs']:
        if job['status']=='PREPARED':
            try:check_ready(job)
            except Exception as error:exclude(job,'PRE_ACTUAL_VALIDATION_FAILED',error=repr(error),traceback=traceback.format_exc())
    if not resolved(state['jobs']):raise PermissionError('R040_PENDING_PREPARATION_CANNOT_ENTER_ACTUAL')
    ready=[];excluded=[];done=[]
    for job in state['jobs']:
        if job['status']=='PREPARED':ready.append(dict(day=job['day'],arm=job['arm'],case_root=job['case_root'],handoff=job['handoff'],slot=len(ready)+1))
        elif job['status']=='PASS':done.append(dict(day=job['day'],arm=job['arm'],result=job.get('result')))
        else:excluded.append(dict(day=job['day'],arm=job['arm'],reason=job.get('exclusion',{}).get('reason','CASE_FAILED'),receipt=job.get('exclusion_receipt')))
    manifest=dict(UTC=now(),authorization=record(op.AMENDMENT),lease=state['lease'],all_preparations_resolved=True,
        ready=ready,excluded=excluded,already_complete=done,cpu_placement=cpu.placement(windows_cpu_sets(),len(ready)) if ready else None)
    validate_manifest(manifest,op.queue());return manifest

def finish_actual(process,job):
    path=Path(job['case_root'])/'RESULT.json';result=read(path) if path.exists() else {}
    if not result or result.get('status')=='PRE_ACTUAL_READY':
        result=dict(day=job['day'],arm=job['arm'],PASS=False,status='FAILED',error='R040_ACTUAL_PROCESS_EXITED_WITHOUT_FINAL_RESULT',exit_code=process.returncode,finished_UTC=now())
        atomic(path,result)
    job.update(status='PASS' if process.returncode==0 and result.get('PASS') is True else 'ACTUAL_FAILED',result=record(path),process_exit=process.returncode)
    atomic(path.parent/'ACTUAL_PROCESS_EXIT.json',dict(UTC=now(),exit_code=process.returncode,isolated_from_other_cases=True))

def run_wave(state,manifest):
    validate_manifest(manifest,op.queue())
    atomic(op.MANIFEST,manifest);manifest_ref=record(op.MANIFEST)
    state['resolved_manifest']=manifest_ref;publish(state)
    if not manifest['ready']:return []
    state['phase']='ACTUAL_PARALLEL';publish(state)
    atomic(op.CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='ACTUAL_PARALLEL',max_workers=len(manifest['ready']),R040_authorization=record(op.AMENDMENT)))
    running=[]
    for item in manifest['ready']:
        if (op.OPS/'STOP_AUTONOMY.json').exists():break
        job=next(j for j in state['jobs'] if op.key(j)==op.key(item))
        try:
            case=op.attach(read(job['prepare_request']));case.update(lease=state['lease'],r038_phase='ACTUAL_PARALLEL',
                parallel_actual_slot=item['slot'],R038_pre_actual_handoff=job['handoff'],R040_resolved_manifest=manifest_ref)
            op.authorize(case)
            pointer=Path(job['prepare_request']).with_name(Path(job['prepare_request']).stem+'_R040_ACTUAL.json')
            atomic(pointer,case);job.update(actual_request=str(pointer),parallel_slot=item['slot'])
            process=op.launch(pointer,'actual');job.update(status='ACTUAL_RUNNING');running.append((process,job))
        except Exception as error:
            job.update(status='ACTUAL_FAILED',dispatch_error=repr(error),dispatch_traceback=traceback.format_exc())
            atomic(op.OPS/'R040_ACTUAL_LAUNCH_FAILURES'/f"{job['day']}_{job['arm']}.json",dict(UTC=now(),job=job,other_cases_continue=True))
        publish(state)
    while running:
        for process,job in running[:]:
            if process.poll() is not None:
                try:finish_actual(process,job)
                except Exception as error:job.update(status='ACTUAL_FAILED',finalization_error=repr(error))
                running.remove((process,job));publish(state)
        status(state,running);time.sleep(5)
    return manifest['ready']

@contextmanager
def reserve_when_available(plan,lease):
    while True:
        manager=cpu.reserve_pool(plan,op.OPS,lease)
        try:manager.__enter__();break
        except PermissionError as error:
            if str(error)!='R038_P_PHYSICAL_CORE_ALREADY_RESERVED':raise
            if (op.OPS/'STOP_AUTONOMY.json').exists():raise PermissionError('R040_USER_STOP_DURING_RESOURCE_WAIT')
            atomic(op.OPS/'R040_CPU_RESOURCE_WAIT.json',dict(UTC=now(),reason=str(error),no_Actual_failure_inferred=True));time.sleep(5)
    try:yield
    finally:manager.__exit__(None,None,None)

def run(lease):
    state=read(op.STATE)
    if [op.key(j) for j in state['jobs']]!=[op.key(j) for j in op.queue()]:raise PermissionError('R040_FIXED_BATCH_MEMBERSHIP_DRIFT')
    state.update(phase='PREPARE_SERIAL',lease=lease)
    for job in state['jobs']:
        try:reconcile(job)
        except Exception as error:exclude(job,'PREVIOUS_CASE_STATE_UNREADABLE_OR_INVALID',error=repr(error),traceback=traceback.format_exc())
    publish(state)
    for job in state['jobs']:
        if (op.OPS/'STOP_AUTONOMY.json').exists():return
        if job['status']!='PENDING':continue
        atomic(op.CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='MAIN',r038_phase='PREPARE_SERIAL'))
        try:
            pointer=inherited.new_request(job,lease);atomic(pointer,op.attach(read(pointer)));publish(state)
            process=op.launch(pointer,'prepare')
            while process.poll() is None:status(state,[(process,job)]);time.sleep(5)
            inherited.finish(process,job,'PREPARED')
            if job['status']=='PRE_FAILED':exclude(job,'PREPARATION_FAILED',result=job.get('result'),exit_code=process.returncode)
        except Exception as error:exclude(job,'PREPARATION_DISPATCH_OR_EXECUTION_FAILED',error=repr(error),traceback=traceback.format_exc())
        publish(state);status(state,[])
    if (op.OPS/'STOP_AUTONOMY.json').exists():return
    manifest=preflight(state);publish(state)
    if manifest['ready']:
        inherited.background_to_E()
        with reserve_when_available(manifest['cpu_placement'],lease):run_wave(state,manifest)
    else:run_wave(state,manifest)
    state.update(phase='COMPLETE' if all(j['status'] in ('PASS','EXCLUDED','ACTUAL_FAILED') for j in state['jobs']) else 'INTERRUPTED_REQUIRES_DIAGNOSIS',
        all_PASS=all(j['status']=='PASS' for j in state['jobs']),excluded_cases=[op.key(j) for j in state['jobs'] if j['status']=='EXCLUDED'],
        Actual_failures=[op.key(j) for j in state['jobs'] if j['status']=='ACTUAL_FAILED'])
    publish(state);status(state,[])
