"""User-authorized B1/B3 barrier wave followed by B0/B2 daily serial cases.

The pinned week2 worker and scientific permit remain unchanged. Switch only
after the already running worker exits naturally and releases its source lease.
"""
from pathlib import Path
from contextlib import ExitStack
from types import FunctionType
from unittest.mock import patch
import argparse,os,sys,time,subprocess,traceback
import psutil
from v44_week2 import operations as old
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import coordinator,exclusive_lock,alive,process_identity

CAMPAIGN,OPS,STATE=old.CAMPAIGN,old.OPS,old.STATE
AUTH=OPS/'SEQUENCE_EXECUTION_PERMIT.json'
STOP=OPS/'STOP.json'
MAIN_BARRIER=OPS/'B1_B3_PREPARATIONS_RESOLVED.json'
ENTRY='v44_week2_sequence'
MAIN=tuple((d,a) for d in old.DAYS for a in ('B1','B3'))
BASELINE=tuple((d,a) for d in old.DAYS for a in ('B0','B2'))
MAIN_TERMINAL={'PASS','EXCLUDED','ACTUAL_FAILED'}
TRANSITION_REASON='USER_REQUESTED_MAIN_THEN_BASELINE_NATURAL_BOUNDARY'
INSTRUCTION='2026-10-19 user: B1/B3 campaign first. After B1/B3 finish, automatically run B0/B2 May08–14 using one worker, each date/arm Planning immediately followed by Actual/Fresh, then the next case. Do not split B0/B2 into planning and Actual waves.'

def key(job):return job['day'],job['arm']
def source():return record(__file__)

def authority(request=None):
    value=read(AUTH)
    verify([value['source'],value['original_permit'],value['tests']])
    if value['source']!=source() or value['original_permit']!=record(old.PERMIT):raise PermissionError('SEQUENCE_SOURCE_OR_BASELINE_PERMIT_DRIFT')
    if value['main']!=[list(k) for k in MAIN] or value['baseline']!=[list(k) for k in BASELINE]:raise PermissionError('SEQUENCE_FIXED_MEMBERSHIP_REQUIRED')
    if (value['main_prepare_workers'],value['main_actual_workers'],value['baseline_workers'],value['baseline_full_case_per_worker'])!=(1,7,1,True):
        raise PermissionError('SEQUENCE_EXPLICIT_USER_WORKER_POLICY_REQUIRED')
    old.authority(request)
    if request is not None:
        if request.get('sequence_authorization')!=record(AUTH):raise PermissionError('SEQUENCE_REQUEST_AUTHORITY_REQUIRED')
        mode=request.get('sequence_mode')
        expected=MAIN if mode=='MAIN' else BASELINE if mode=='BASELINE_FULL' else ()
        if key(request) not in expected:raise PermissionError('SEQUENCE_CASE_GROUP_REQUIRED')
    return value

def main_resolved(jobs):
    main=[j for j in jobs if key(j) in MAIN]
    return len(main)==14 and all(j['status'] in MAIN_TERMINAL for j in main)

def validate_main_barrier(value):
    ready=value.get('ready',[]);excluded=value.get('excluded',[])
    keys=[key(j) for j in ready+excluded]
    if len(keys)!=14 or len(set(keys))!=14 or set(keys)!=set(MAIN):raise PermissionError('SEQUENCE_ALL_14_MAIN_PREPARATIONS_REQUIRED')
    if not value.get('all_preparations_resolved') or value.get('Actual_started_before_barrier') is not False:
        raise PermissionError('SEQUENCE_MAIN_BARRIER_REQUIRED')
    if any(not j.get('handoff') for j in ready) or any(not j.get('exclusion_reason') for j in excluded):
        raise PermissionError('SEQUENCE_VERIFIED_MAIN_READY_OR_EXCLUDED_REQUIRED')
    count=min(7,len(ready));plan=value.get('cpu_placement')
    if (count and (not plan or len(plan['slots'])!=count)) or (not count and plan is not None):
        raise PermissionError('SEQUENCE_MAIN_SEVEN_SLOT_POOL_REQUIRED')
    return value

def require_live():
    from v44.execution import assert_current
    authority(assert_current()['request'])

def worker(path):
    from v44_recovery_r038 import operations as original,cpu
    from v44_recovery_r029 import conditional_campaign,cpu_placement
    from v44_recovery_r039 import latency
    request=read(path);authority(request)
    if request['sequence_mode']=='MAIN' and request['r038_phase']=='PREPARE_SERIAL':return old.worker(path)
    # Identical inherited algorithm installations; only the dispatch style differs.
    with original.previous.install(),latency.install(require_live),ExitStack() as stack:
        if request['sequence_mode']=='MAIN':
            if request['r038_phase']!='ACTUAL_PARALLEL':raise PermissionError('SEQUENCE_MAIN_ACTUAL_PHASE_REQUIRED')
            barrier=validate_main_barrier(read(MAIN_BARRIER));plan=barrier['cpu_placement'];cpu.validate_topology(plan)
            function=FunctionType(old.actual_case.__code__,dict(old.actual_case.__globals__,
                BARRIER=MAIN_BARRIER,validate_barrier=validate_main_barrier),old.actual_case.__name__)
            stack.enter_context(patch.object(conditional_campaign,'run_case',function))
            stack.enter_context(patch.object(cpu_placement,'compute_cpu_scope',lambda n,receipt=None:cpu.compute_scope(request,n,receipt,plan)))
            psutil.Process().cpu_affinity([plan['slots'][request['parallel_actual_slot']-1]['logical']])
        else:
            if request['r038_phase']!='BASELINE_SEQUENTIAL':raise PermissionError('SEQUENCE_BASELINE_FULL_CASE_PHASE_REQUIRED')
            state=read(STATE)
            if state.get('phase')!='BASELINE_SEQUENTIAL' or not main_resolved(state['jobs']):
                raise PermissionError('SEQUENCE_B0_B2_ONLY_AFTER_MAIN_TERMINAL')
            # Keep the original full run_case: REFERENCE -> optional M1 ->
            # Actual -> independent Fresh, all inside this single worker.
        return original.base.worker(request)

def launch(path,label):
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    folder=OPS/'logs';folder.mkdir(exist_ok=True)
    with (folder/(path.stem+'.sequence.'+label+'.out.log')).open('ab') as out,(folder/(path.stem+'.sequence.'+label+'.err.log')).open('ab') as err:
        return subprocess.Popen([sys.executable,'-X','utf8','-u','-m',ENTRY,'--worker',str(path)],cwd=old.RUNNER_ROOT,env=env,
            stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def publish(state,running=()):
    state['sequence_authorization']=record(AUTH);old.publish(state,running)
    atomic(OPS/'SEQUENCE_HEARTBEAT.json',dict(UTC=now(),**process_identity(),phase=state['phase'],
        workers=[dict(pid=p.pid,day=j['day'],arm=j['arm']) for p,j in running],baseline_followup_armed=state['phase'].startswith('MAIN_')))

def new_request(job,lease,mode):
    path=old.new_request(job,lease);r=read(path)
    r.update(sequence_mode=mode,sequence_authorization=record(AUTH))
    if mode=='BASELINE_FULL':r['r038_phase']='BASELINE_SEQUENTIAL';job['status']='BASELINE_RUNNING'
    atomic(path,r);authority(r);return path

def collect(process,job,planning=False,baseline=False):
    old.finish(process,job,planning)
    if baseline and job['status']=='ACTUAL_FAILED' and not (Path(job['case_root'])/'ACTUAL').exists():job['status']='EXCLUDED'

def prepare_main(state,lease):
    state['phase']='MAIN_PREPARE_SERIAL';publish(state)
    for target in MAIN:
        job=next(j for j in state['jobs'] if key(j)==target)
        if job['status']!='PENDING':continue
        if STOP.exists():return False
        atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='MAIN',r038_phase='PREPARE_SERIAL'))
        try:
            path=new_request(job,lease,'MAIN');publish(state);process=launch(path,'prepare')
            while process.poll() is None:publish(state,[(process,job)]);time.sleep(5)
            collect(process,job,planning=True)
        except Exception as error:job.update(status='EXCLUDED',exclusion_reason=repr(error),traceback=traceback.format_exc())
        publish(state)
    return True

def actual_main(state,lease):
    from v44_recovery_r038 import cpu
    from v44_recovery_r029.cpu_placement import windows_cpu_sets
    from v44_recovery_r038.phases import load_handoff
    main=[j for j in state['jobs'] if key(j) in MAIN]
    for job in main:
        if job['status']!='PREPARED':continue
        try:
            r=read(job['prepare_request']);r['R038_pre_actual_handoff']=job['handoff'];old.authority(r);load_handoff(r)
        except Exception as error:job.update(status='EXCLUDED',exclusion_reason='HANDOFF_VALIDATION:'+repr(error))
    ready=[dict(day=j['day'],arm=j['arm'],case_root=j['case_root'],handoff=j['handoff']) for j in main if j['status']=='PREPARED']
    count=min(7,len(ready));plan=cpu.placement(windows_cpu_sets(),count) if count else None
    barrier=dict(UTC=now(),all_preparations_resolved=True,lease=lease,authorization=record(AUTH),ready=ready,
        excluded=[j for j in main if j['status']=='EXCLUDED'],Actual_started_before_barrier=False,cpu_placement=plan)
    validate_main_barrier(barrier);atomic(MAIN_BARRIER,barrier);state['phase']='MAIN_ACTUAL_PARALLEL';publish(state)
    if not count:return
    atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='ACTUAL_PARALLEL',max_workers=7))
    with cpu.reserve_pool(plan,OPS,lease):
        pending=[j for j in main if j['status']=='PREPARED'];running=[];available=list(range(1,count+1))
        while pending or running:
            while pending and available and not STOP.exists():
                job=pending.pop(0);slot=available.pop(0)
                r=read(job['prepare_request']);r.update(lease=lease,r038_phase='ACTUAL_PARALLEL',parallel_actual_slot=slot,
                    R038_pre_actual_handoff=job['handoff'],week2_barrier=record(MAIN_BARRIER),sequence_mode='MAIN',sequence_authorization=record(AUTH))
                path=OPS/'requests'/f"{job['day']}_{job['arm']}_SEQUENCE_ACTUAL.json";atomic(path,r)
                try:
                    process=launch(path,'actual');job.update(status='ACTUAL_RUNNING',parallel_slot=slot,actual_request=str(path));running.append((process,job))
                except Exception as error:job.update(status='ACTUAL_FAILED',exclusion_reason='ACTUAL_LAUNCH:'+repr(error));available.append(slot)
                publish(state,running)
            for process,job in running[:]:
                if process.poll() is not None:collect(process,job);available.append(job['parallel_slot']);running.remove((process,job));publish(state,running)
            if not running and STOP.exists():return
            publish(state,running);time.sleep(5)

def baseline_serial(state,lease):
    if not main_resolved(state['jobs']):raise PermissionError('SEQUENCE_MAIN_NOT_FINISHED')
    state['phase']='BASELINE_SEQUENTIAL';publish(state)
    for target in BASELINE:
        job=next(j for j in state['jobs'] if key(j)==target)
        if job['status'] in MAIN_TERMINAL:continue
        if job['status']!='BASELINE_QUEUED':raise PermissionError('SEQUENCE_BASELINE_PENDING_STATE_REQUIRED')
        if STOP.exists():return
        atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='B2' if job['arm']=='B2' else 'MAIN',max_workers=1,sequence_mode='BASELINE_FULL'))
        try:
            path=new_request(job,lease,'BASELINE_FULL');publish(state);process=launch(path,'full_case')
            while process.poll() is None:publish(state,[(process,job)]);time.sleep(5)
            collect(process,job,baseline=True)
        except Exception as error:job.update(status='EXCLUDED',exclusion_reason=repr(error),traceback=traceback.format_exc())
        publish(state)

def run():
    authority();state=read(STATE)
    expected={(d,a) for d in old.DAYS for a in old.ARMS}
    if len(state['jobs'])!=28 or {key(j) for j in state['jobs']}!=expected:raise PermissionError('SEQUENCE_ALL_28_CASES_PRESERVED')
    if any(j['status'] in ('PREPARING','ACTUAL_RUNNING','BASELINE_RUNNING') for j in state['jobs']):raise PermissionError('SEQUENCE_LIVE_OR_UNRESOLVED_OLD_WORKER')
    with coordinator(CAMPAIGN) as lease:
        state['lease']=lease
        for job in state['jobs']:
            if key(job) in BASELINE and job['status']=='PENDING':job['status']='BASELINE_QUEUED'
            job['execution_group']='B1_B3_MAIN' if key(job) in MAIN else 'B0_B2_FOLLOWUP'
        atomic(OPS/'SEQUENCE_BOUNDARY_ADOPTED.json',dict(UTC=now(),lease=lease,authority=record(AUTH),
            old_state=record(OPS/'SEQUENCE_OLD_STATE_PRESERVED.json'),active_worker_interrupted=False))
        pointer=read(Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json'))
        pointer.update(UTC=now(),coordinator=lease,status='RUNNING',dispatch_sequence=record(AUTH),
            main_prepare_workers=1,main_actual_workers=7,baseline_workers=1,baseline_full_case_per_worker=True)
        atomic(Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json'),pointer)
        if not prepare_main(state,lease):return
        actual_main(state,lease)
        if STOP.exists():state['phase']='USER_STOPPED';publish(state);return
        baseline_serial(state,lease)
        if STOP.exists():state['phase']='USER_STOPPED';publish(state);return
        if not all(j['status'] in MAIN_TERMINAL for j in state['jobs']):raise PermissionError('SEQUENCE_FINAL_UNRESOLVED_CASE')
        state.update(phase='COMPLETE',all_PASS=all(j['status']=='PASS' for j in state['jobs']));publish(state)
        atomic(OPS/'FINAL_RESULT.json',dict(UTC=now(),phase='COMPLETE',PASS=state['all_PASS'],
            passed=sum(j['status']=='PASS' for j in state['jobs']),excluded=sum(j['status']=='EXCLUDED' for j in state['jobs']),
            Actual_failed=sum(j['status']=='ACTUAL_FAILED' for j in state['jobs']),sequence_authorization=record(AUTH)))

def transition():
    authority()
    with exclusive_lock(OPS/'SEQUENCE_CONTROLLER.lock'):
        while True:
            state=read(STATE);lease=state.get('lease');status=read(CAMPAIGN/'CAMPAIGN_STATUS.json')
            active=[]
            for job in state['jobs']:
                if job.get('case_root'):
                    for name in ('START.json','ACTUAL_START.json'):
                        p=Path(job['case_root'])/name
                        if p.exists() and alive(read(p)):active.append(read(p))
            atomic(OPS/'SEQUENCE_TRANSITION_HEARTBEAT.json',dict(UTC=now(),**process_identity(),phase='WAIT_FOR_CURRENT_WORKER_NATURAL_EXIT',
                old_coordinator_alive=alive(lease),active_workers=active,followup_armed=True))
            stop=read(STOP) if STOP.exists() else {}
            if stop.get('reason')!=TRANSITION_REASON or stop.get('sequence_authorization')!=record(AUTH):
                atomic(OPS/'SEQUENCE_USER_STOP_PRESERVED.json',dict(UTC=now(),stop=stop));return
            if not alive(lease) and not active:
                if state['phase']!='USER_STOPPED':raise PermissionError('SEQUENCE_EXPECTED_NATURAL_BOUNDARY_REQUIRED')
                atomic(OPS/'SEQUENCE_OLD_STATE_PRESERVED.json',state)
                atomic(OPS/'SEQUENCE_TRANSITION_STOP_PRESERVED.json',stop);STOP.unlink()
                return run()
            time.sleep(5)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--transition',action='store_true');parser.add_argument('--worker',type=Path);args=parser.parse_args()
    with old.bindings():
        if args.worker:return worker(args.worker)
        if not args.transition:parser.error('Choose --transition or --worker')
        try:return transition()
        except BaseException as error:
            atomic(OPS/'SEQUENCE_CONTROLLER_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':main()
