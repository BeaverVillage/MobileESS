"""Recover dispatch failures; retain the seven dated inputs and original 1/7/1 policy."""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from types import FunctionType
from unittest.mock import patch
import argparse,os,sys,time,subprocess,traceback
import psutil
from v44_week2 import operations as week
import v44_week2_sequence as seq
from v44_recovery_r044 import operations as repair
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import coordinator,exclusive_lock,alive,process_identity

CAMPAIGN,OPS,STATE=week.CAMPAIGN,week.OPS,week.STATE
PERMIT=OPS/'R045_DATED_CAMPAIGN_RESTART_AUTHORIZATION.json'
VALIDATION=OPS/'R045_VALIDATION.json'
ENTRY='v44_recovery_r045.operations'
_original_authority=week.authority


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    seq.authority();v=read(PERMIT)
    verify(v['sources']+[v['previous_authorization'],v['validation'],v['date_audit']])
    if v['sources']!=sources() or not read(v['validation']['path'])['PASS']:
        raise PermissionError('R045_SEALED_TESTED_RESTART_REQUIRED')
    keys=[(j['day'],j['arm']) for j in v['plan']]
    if len(keys)!=28 or set(keys)!={(d,a) for d in week.DAYS for a in week.ARMS}:
        raise PermissionError('R045_ALL_28_DATED_CASES_REQUIRED')
    if (v['prepare_workers'],v['actual_workers'],v['baseline_workers'])!=(1,7,1):
        raise PermissionError('R045_ORIGINAL_DISPATCH_POLICY_REQUIRED')
    return v


def request_authority(request=None):
    if request is None:return _original_authority()
    v=authority();plan=next((j for j in v['plan'] if seq.key(j)==seq.key(request)),None)
    if (plan is None or Path(request['case_root'])!=Path(plan['case_root'])
        or request.get('R045_authorization')!=record(PERMIT)
        or request.get('sequence_authorization')!=record(seq.AUTH)):
        raise PermissionError('R045_EXACT_DATED_CASE_AND_AUTHORIZATION_REQUIRED')
    # Extend only the admitted attempt location; all original input, day,
    # worker, source and scientific execution-permit checks remain mandatory.
    return _original_authority(dict(request,case_root=str(CAMPAIGN/request['day']/request['arm']/'attempt001')))


def publish(state,running=()):
    state['R045_authorization']=record(PERMIT);seq.publish(state,running)
    atomic(OPS/'R045_HEARTBEAT.json',dict(UTC=now(),**process_identity(),phase=state['phase'],
        workers=[dict(pid=p.pid,day=j['day'],arm=j['arm']) for p,j in running]))


def worker(path,entry_check=False):
    from .admission import boundary
    from .reference import project
    from v44_recovery_r029 import handover,conditional_campaign
    from v43_arms import reference
    request=read(path);request_authority(request);guard=boundary(request)
    if entry_check:
        atomic(OPS/'R045_ENTRY_CHECK.json',dict(PASS=True,UTC=now(),**process_identity(),
            day=request['day'],arm=request['arm'],request=record(path),protected_case=guard['protected_case_root'],
            live_current_coordinator_admitted=True,Native_calls=0));return
    with patch.object(handover,'require_boundary',lambda:boundary(request)),patch.object(reference,'project',project):
        if seq.key(request)==('2025-05-08','B3') and request['r038_phase']=='PREPARE_SERIAL':
            repair.authority()
            from v44_recovery_r038 import operations as inherited
            from v44_recovery_r039 import latency
            from v44_recovery_r041.preparation import deny_actual
            from v44 import worker as science
            continued=FunctionType(repair.repaired_case.__code__,dict(repair.repaired_case.__globals__,
                authority=authority,request_authority=request_authority,PERMIT=PERMIT),repair.repaired_case.__name__)
            with inherited.previous.install(),latency.install(lambda:request_authority(__import__('v44.execution',fromlist=['assert_current']).assert_current()['request'])),patch.object(conditional_campaign,'run_case',continued),patch.object(science,'actual',deny_actual):
                return inherited.base.worker(request)
        return seq.worker(path)


def new_request(job,lease,mode):
    plan=next(p for p in authority()['plan'] if seq.key(p)==seq.key(job))
    r=read(plan['original_request'])
    r.update(case_root=plan['case_root'],lease=lease,sequence_mode=mode,
        sequence_authorization=record(seq.AUTH),R045_authorization=record(PERMIT),
        r038_phase='PREPARE_SERIAL' if mode=='MAIN' else 'BASELINE_SEQUENTIAL')
    r['sources']=list({x['path']:x for x in r['sources']+sources()+[record(PERMIT)]}.values())
    r['source_sha']=digest(r['sources']);request_authority(r)
    path=OPS/'requests'/f"{r['day']}_{r['arm']}_R045.json";atomic(path,r)
    job.update(case_root=r['case_root'],prepare_request=str(path),status='PREPARING' if mode=='MAIN' else 'BASELINE_RUNNING')
    return path


def launch(path,label,entry_check=False):
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    args=[sys.executable,'-X','utf8','-u','-m',ENTRY,'--worker',str(path)]
    if entry_check:args+=['--entry-check']
    folder=OPS/'logs';folder.mkdir(exist_ok=True)
    with (folder/(path.stem+'.r045.'+label+'.out.log')).open('ab') as out,(folder/(path.stem+'.r045.'+label+'.err.log')).open('ab') as err:
        return subprocess.Popen(args,cwd=week.RUNNER_ROOT,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def collect(process,job,planning=False,baseline=False):
    root=Path(job['case_root'])
    if process.returncode!=0 or not (root/'START.json').exists() or not (root/'RESULT.json').exists():
        job.update(status='INFRASTRUCTURE_BLOCKED',process_exit=process.returncode)
        raise RuntimeError(f"R045_WORKER_ENTRY_OR_INFRASTRUCTURE_FAILURE:{job['day']}/{job['arm']}:{process.returncode}")
    week.finish(process,job,planning)
    if baseline and job['status']=='ACTUAL_FAILED' and not (root/'ACTUAL').exists():job['status']='EXCLUDED'


def wait_one(process,job,state):
    while process.poll() is None:publish(state,[(process,job)]);time.sleep(5)


def prepare_main(state,lease):
    state['phase']='MAIN_PREPARE_SERIAL';publish(state)
    for key in seq.MAIN:
        job=next(j for j in state['jobs'] if seq.key(j)==key)
        if job['status']!='PENDING':continue
        if seq.STOP.exists():return False
        atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='MAIN',r038_phase='PREPARE_SERIAL'))
        path=new_request(job,lease,'MAIN');publish(state)
        # Test the actual subprocess name, request and boundary under the live
        # coordinator lease before admitting scientific execution.
        checked=launch(path,'entry',entry_check=True);wait_one(checked,job,state)
        if checked.returncode!=0:raise RuntimeError('R045_REAL_SUBPROCESS_ENTRY_CHECK_FAILED')
        process=launch(path,'prepare');wait_one(process,job,state);collect(process,job,planning=True);publish(state)
    return True


def actual_main(state,lease):
    from v44_recovery_r038 import cpu
    from v44_recovery_r029.cpu_placement import windows_cpu_sets
    from v44_recovery_r038.phases import load_handoff
    main=[j for j in state['jobs'] if seq.key(j) in seq.MAIN]
    for job in main:
        if job['status']=='PREPARED':
            r=read(job['prepare_request']);r['R038_pre_actual_handoff']=job['handoff'];request_authority(r);load_handoff(r)
    ready=[dict(day=j['day'],arm=j['arm'],case_root=j['case_root'],handoff=j['handoff']) for j in main if j['status']=='PREPARED']
    count=min(7,len(ready));plan=cpu.placement(windows_cpu_sets(),count) if count else None
    barrier=dict(UTC=now(),all_preparations_resolved=True,lease=lease,authorization=record(seq.AUTH),
        R045_authorization=record(PERMIT),ready=ready,excluded=[j for j in main if j['status']=='EXCLUDED'],
        Actual_started_before_barrier=False,cpu_placement=plan)
    seq.validate_main_barrier(barrier);atomic(seq.MAIN_BARRIER,barrier)
    state['phase']='MAIN_ACTUAL_PARALLEL';publish(state)
    if not count:return
    atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='ACTUAL_PARALLEL',max_workers=7))
    errors=[]
    with cpu.reserve_pool(plan,OPS,lease):
        pending=[j for j in main if j['status']=='PREPARED'];running=[];available=list(range(1,count+1))
        while pending or running:
            while pending and available and not seq.STOP.exists() and not errors:
                job=pending.pop(0);slot=available.pop(0)
                r=read(job['prepare_request']);r.update(lease=lease,r038_phase='ACTUAL_PARALLEL',parallel_actual_slot=slot,
                    R038_pre_actual_handoff=job['handoff'],week2_barrier=record(seq.MAIN_BARRIER),R045_authorization=record(PERMIT))
                request_authority(r);path=OPS/'requests'/f"{job['day']}_{job['arm']}_R045_ACTUAL.json";atomic(path,r)
                p=launch(path,'actual');job.update(status='ACTUAL_RUNNING',parallel_slot=slot,actual_request=str(path));running.append((p,job));publish(state,running)
            for p,job in running[:]:
                if p.poll() is not None:
                    try:collect(p,job)
                    except Exception as error:errors.append(repr(error))
                    available.append(job['parallel_slot']);running.remove((p,job));publish(state,running)
            if not running and (seq.STOP.exists() or errors):break
            publish(state,running);time.sleep(5)
    if errors:raise RuntimeError('R045_ACTUAL_INFRASTRUCTURE_BLOCKED:'+repr(errors))


def baseline_serial(state,lease):
    if not seq.main_resolved(state['jobs']):raise PermissionError('R045_MAIN_ACTUAL_NOT_FINISHED')
    state['phase']='BASELINE_SEQUENTIAL';publish(state)
    for key in seq.BASELINE:
        job=next(j for j in state['jobs'] if seq.key(j)==key)
        if job['status'] in seq.MAIN_TERMINAL:continue
        if seq.STOP.exists():return
        if job['status']!='BASELINE_QUEUED':raise PermissionError('R045_BASELINE_QUEUED_REQUIRED')
        atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='B2' if job['arm']=='B2' else 'MAIN',max_workers=1))
        path=new_request(job,lease,'BASELINE_FULL');publish(state)
        checked=launch(path,'entry',entry_check=True);wait_one(checked,job,state)
        if checked.returncode!=0:raise RuntimeError('R045_BASELINE_SUBPROCESS_ENTRY_CHECK_FAILED')
        p=launch(path,'full_case');wait_one(p,job,state);collect(p,job,baseline=True);publish(state)


def restore_state(lease):
    from v44_recovery_r038.phases import load_handoff
    state=read(STATE)
    if alive(state.get('lease')) or seq.STOP.exists():raise PermissionError('R045_LIVE_OLD_OWNER_OR_USER_STOP_PRESERVED')
    atomic(OPS/'R045_STATE_BEFORE_RESTART.json',state)
    for job in state['jobs']:
        plan=next(j for j in authority()['plan'] if seq.key(j)==seq.key(job))
        root=Path(job['case_root'])
        if (root/'ACTUAL').exists() or (root/'ACTUAL_START.json').exists():raise PermissionError('R045_EXISTING_ACTUAL_CONTEXT_REQUIRES_SEPARATE_ADMISSION')
        for name in ('result','process_exit','exclusion_reason','traceback','actual_request','parallel_slot'):job.pop(name,None)
        if plan['reuse_prepared']:
            r=read(plan['original_request']);r.update(lease=lease,R045_authorization=record(PERMIT),R038_pre_actual_handoff=job['handoff'])
            request_authority(r);load_handoff(r)
            path=OPS/'requests'/f"{job['day']}_{job['arm']}_R045_ADOPTED.json";atomic(path,r)
            job.update(status='PREPARED',prepare_request=str(path))
        else:
            job.pop('handoff',None);job.update(case_root=plan['case_root'],status='PENDING' if seq.key(job) in seq.MAIN else 'BASELINE_QUEUED')
        job['execution_group']='B1_B3_MAIN' if seq.key(job) in seq.MAIN else 'B0_B2_FOLLOWUP'
    state.update(lease=lease,all_PASS=False,phase='MAIN_PREPARE_SERIAL',R045_authorization=record(PERMIT))
    return state


def run():
    authority()
    with exclusive_lock(OPS/'R045_CONTROLLER.lock'),coordinator(CAMPAIGN) as lease:
        state=None
        try:
            state=restore_state(lease)
            # Preserve the incomplete old reference folder; a fresh baseline
            # later writes only into the original canonical day location.
            ref=CAMPAIGN/'references/2025-05-08'
            if ref.exists() and not (ref/'AIDC_REFERENCE.json').exists():
                dest=OPS/'R045_PRESERVED_INCOMPLETE_REFERENCE_2025-05-08'
                if dest.exists():raise FileExistsError('R045_REFERENCE_ARCHIVE_ALREADY_EXISTS')
                if ref.resolve().parent!=(CAMPAIGN/'references').resolve():raise PermissionError('R045_EXACT_REFERENCE_PATH_REQUIRED')
                ref.rename(dest)
            final=OPS/'FINAL_RESULT.json'
            if final.exists():final.rename(OPS/'R045_PREVIOUS_TERMINAL_SUMMARY.json')
            pointer=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json');v=read(pointer)
            v.update(UTC=now(),coordinator=lease,status='RUNNING',operational_entry=ENTRY,operational_recovery=record(PERMIT));atomic(pointer,v)
            publish(state)
            if not prepare_main(state,lease):return
            actual_main(state,lease)
            if seq.STOP.exists():state['phase']='USER_STOPPED';publish(state);return
            baseline_serial(state,lease)
            if seq.STOP.exists():state['phase']='USER_STOPPED';publish(state);return
            if not all(j['status'] in seq.MAIN_TERMINAL for j in state['jobs']):raise PermissionError('R045_UNRESOLVED_CASES_CANNOT_COMPLETE')
            state.update(phase='COMPLETE',all_PASS=all(j['status']=='PASS' for j in state['jobs']));publish(state)
            atomic(OPS/'FINAL_RESULT.json',dict(UTC=now(),phase='COMPLETE',PASS=state['all_PASS'],jobs=state['jobs'],authorization=record(PERMIT)))
        except BaseException as error:
            if state is not None:state.update(phase='INFRASTRUCTURE_BLOCKED',all_PASS=False);publish(state)
            atomic(OPS/'R045_CONTROLLER_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise


@contextmanager
def bindings():
    with week.bindings(),patch.object(week,'authority',request_authority):yield


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--worker',type=Path);p.add_argument('--entry-check',action='store_true');a=p.parse_args()
    with bindings():
        if a.worker:
            try:return worker(a.worker,a.entry_check)
            except BaseException as error:
                atomic(OPS/(a.worker.stem+'.R045_WORKER_ERROR.json'),dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise
        if a.run:return run()
        p.error('Choose --run or --worker')

if __name__=='__main__':main()
