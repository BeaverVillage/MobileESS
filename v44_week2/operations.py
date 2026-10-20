"""Explicitly authorized new dates, serial planning, then a seven-worker wave."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch
import argparse, os, sys, subprocess, time, traceback
import psutil
import v44_recovery_r043  # Select the original byte-pinned scientific checkout first.
from v44.common import ROOT, DOC as BASE_DOC, read, record, verify, atomic, digest, now
from v44.locks import coordinator, exclusive_lock, process_identity, alive

DAYS=tuple(f'2025-05-{i:02d}' for i in range(8,15))
OLD_DAYS=tuple(f'2025-05-{i:02d}' for i in range(1,8))
ARMS=('B0','B1','B2','B3')
CAMPAIGN=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign005_may08_14')
OPS=CAMPAIGN/'OPERATIONS'
DOC=CAMPAIGN/'DOCUMENTS'
PERMIT=OPS/'EXECUTION_PERMIT.json'
STATE=OPS/'BATCH_STATE.json'
BARRIER=OPS/'ALL_PREPARATIONS_RESOLVED.json'
ENTRY='v44_week2.operations'
RUNNER_ROOT=Path(__file__).resolve().parents[1]
INSTRUCTION='2026-10-19 user: V44 r43; same campaign May 8–14; planning 1 worker; once all healthy Actual preparations ready, exclude failures and run Actual together with 7 workers.'

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

@contextmanager
def period(days):
    from v44 import config
    old=config.DAYS;config.DAYS=days
    try:yield
    finally:config.DAYS=old

@contextmanager
def bindings():
    """Scope the new date axis and input manifest; pinned physics stays original."""
    from v44 import config, daily, inputs, public_inputs, prepare
    from v44_recovery_r029 import a2_cache
    original=prepare.require_execution_permit
    def require(path,certification):
        path=Path(path).resolve()
        if path==PERMIT.resolve():
            certification=read(DOC/'PREEXECUTION_CERTIFICATION.json')
            with period(DAYS):value=original(path,certification)
            if value.get('campaign_root')!=str(CAMPAIGN) or value.get('campaign_sources')!=sources():
                raise PermissionError('WEEK2_SEALED_CAMPAIGN_SOURCE_OR_ROOT_DRIFT')
            verify(value['campaign_sources']+[value['input_manifest'],value['baseline_permit']])
            return value
        # Historical permits retain their original date scope and all validators.
        with period(OLD_DAYS):return original(path,certification)
    with period(DAYS),ExitStack() as stack:
        for module in (daily,inputs,public_inputs,a2_cache):stack.enter_context(patch.object(module,'DOC',DOC))
        for module in (inputs,public_inputs):stack.enter_context(patch.object(module,'DAYS',DAYS))
        stack.enter_context(patch.object(prepare,'require_execution_permit',require))
        yield

def prepare():
    from v44 import inputs, public_inputs, daily
    from v44_recovery_r043 import operations as baseline
    from v44_recovery_r038 import operations as original
    baseline.authority();original.previous.validate()
    if PERMIT.exists():raise FileExistsError('IMMUTABLE_NEW_CAMPAIGN_ALREADY_PREPARED')
    DOC.mkdir(parents=True,exist_ok=True);OPS.mkdir(parents=True,exist_ok=True)
    freeze=read(BASE_DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
    atomic(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json',freeze)
    public_inputs.prepare_descriptors()
    # Each date gets the same issue-only initialization algorithm and independent
    # daily MESS assumption used in week 1; never read prior optimized states.
    from v43_actual.vendor.initial_state import prepare_initialization
    from v43_actual.vendor.initialization import initialize_running
    from v44.initial_states import mess_contract
    bindings_doc=read(DOC/'DAILY_AUTHORITY_BINDINGS.json')
    for day in DAYS:
        target=DOC/'initial_states'/day;native_folder=inputs.NATIVE_ROOT/day
        bundle=inputs.BUNDLE_ROOT/('DAY_'+day.replace('-',''))
        native=read(native_folder/'NATIVE_INPUT.json')
        local=target/'INPUT';local.mkdir(parents=True,exist_ok=True)
        for source,name in ((native_folder/'NATIVE_INPUT.json','NATIVE_INPUT_TEMPLATE_B1.json'),(bundle/'PLANNING_INPUT_BUNDLE.json','PLANNING_INPUT_BUNDLE.json')):
            (local/name).write_bytes(source.read_bytes())
        def initialize(*args,**kwargs):
            kwargs['expected_counts']=None;return initialize_running(*args,**kwargs)
        result=daily.clone(prepare_initialization,initialize_running=initialize)(local,target/'RUNNING',budget=None,
            source_assessment=dict(policy='INITIAL_RUNNING_SITE_MODEL_ASSUMED',reuse='Same V44 week1 issue-only initializer',private_completion_or_runtime_reads=0))
        if not result['policy']['PASS']:raise ValueError('DATED_INITIALIZATION_FAILED:'+day)
        mess=target/'MESS_DAILY_INITIAL_STATE.json';atomic(mess,mess_contract(day,native))
        bindings_doc[day].update(initial_running=record(target/'RUNNING/SYNTHETIC_INITIALIZATION_POLICY.json'),initial_MESS=record(mess))
    atomic(DOC/'DAILY_AUTHORITY_BINDINGS.json',bindings_doc)
    manifest=inputs.manifest();atomic(DOC/'SEVEN_DAY_INPUT_MANIFEST.json',manifest)
    blocked=[dict(day=r['day'],blockers=r['blockers']) for r in manifest['days'] if r['blockers']]
    if blocked:raise ValueError(dict(INPUT_BLOCKERS=blocked))
    # Preserve and summarize the completed comparison campaign, including every arm.
    prior=baseline.CAMPAIGN;completed=[]
    for day in OLD_DAYS:
        for arm in ARMS:
            results=[p for p in sorted((prior/day/arm).glob('attempt*/RESULT.json')) if read(p).get('PASS') is True]
            if len(results)!=1:raise ValueError(f'AMBIGUOUS_BASELINE_COMPLETE_RESULT:{day}/{arm}:{len(results)}')
            completed.append(dict(day=day,arm=arm,result=record(results[0])))
    atomic(OPS/'BASELINE_R043.json',dict(PASS=True,UTC=now(),revision='v44_recovery_r043',completed_cases=completed,
        authority=record(baseline.PERMIT),final_result=record(baseline.OPS/'R043_FINAL_RESULT.json')))
    certification=dict(read(BASE_DOC/'PREEXECUTION_CERTIFICATION.json'),UTC=now(),status='V44_PRESTART_READY',
        days=list(DAYS),inputs='PASS',blockers=[],input_manifest=record(DOC/'SEVEN_DAY_INPUT_MANIFEST.json'),
        baseline_r043=record(OPS/'BASELINE_R043.json'),campaign_sources=sources(),validation_scope='Date/IO and dispatcher; scientific implementation inherited unchanged')
    atomic(DOC/'PREEXECUTION_CERTIFICATION.json',certification)
    value=dict(read(original.PERMIT),UTC=now(),days=list(DAYS),source_sha=freeze['source_sha'],certification_sha=digest(certification),
        explicit_user_approved=True,mode='EXECUTE',campaign_root=str(CAMPAIGN),campaign_sources=sources(),
        input_manifest=record(DOC/'SEVEN_DAY_INPUT_MANIFEST.json'),baseline_permit=record(original.PERMIT),
        user_instruction=INSTRUCTION,prepare_workers=1,actual_workers=7,all_preparations_barrier=True,exclude_failed_cases=True)
    atomic(PERMIT,value)
    jobs=[dict(day=d,arm=a,status='PENDING') for d in DAYS for a in ARMS]
    atomic(STATE,dict(UTC=now(),phase='PREPARE_SERIAL',jobs=jobs,authorization=record(PERMIT),baseline='V44 r043'))
    return dict(PASS=True,days=list(DAYS),cases=len(jobs),baseline_complete=len(completed),campaign=str(CAMPAIGN))

def authority(request=None):
    from v44.prepare import require_execution_permit
    value=require_execution_permit(PERMIT,read(DOC/'PREEXECUTION_CERTIFICATION.json'))
    if (value.get('prepare_workers'),value.get('actual_workers'),value.get('exclude_failed_cases'),value.get('all_preparations_barrier'))!=(1,7,True,True):
        raise PermissionError('WEEK2_USER_DISPATCH_POLICY_REQUIRED')
    if request is not None:
        if request['day'] not in DAYS or request['arm'] not in ARMS or request['worker_slot']!=1:
            raise PermissionError('WEEK2_FIXED_CASE_REQUIRED')
        if request['execution_permit']!=record(PERMIT) or Path(request['campaign_root'])!=CAMPAIGN:
            raise PermissionError('WEEK2_EXACT_EXECUTION_AUTHORITY_REQUIRED')
        expected=CAMPAIGN/request['day']/request['arm']/'attempt001'
        if Path(request['case_root'])!=expected:raise PermissionError('WEEK2_NEW_INDEPENDENT_ATTEMPT_ONLY')
        verify(request['sources'])
    return value

def prepare_actual(request,folder,mess):
    from v44.execution import assert_current
    from v44.campaign import stage_file
    from v44.checkpoints import checked
    from v44.daily import load_aidc
    case=assert_current()['request'];authority(case);root=Path(case['case_root'])
    if case['r038_phase']!='PREPARE_SERIAL' or (root/'ACTUAL').exists():raise PermissionError('WEEK2_PLANNING_ACTUAL_FENCE')
    load_aidc(folder,case['day']);refs=[record(Path(folder)/'AIDC_REFERENCE.json')]
    stages=dict(B0=(),B1=('A1',),B2=('M1',),B3=('M1','A2','M2'))[case['arm']]
    for stage in stages:
        path=stage_file(case,stage);cp=path.parent/'COMPLETED_STAGE_CHECKPOINT.json'
        checked(cp,read(path.parent/'request.json'),'COMPLETED');refs.extend([record(path),record(cp)])
    value=dict(schema='V44_R038_PRE_ACTUAL_HANDOFF_V1',UTC=now(),ready=True,day=case['day'],arm=case['arm'],
        case_root=str(root),source_sha=case['source_sha'],sources=case['sources'],evidence=refs,aidc_folder=str(folder),
        MESS_plan=mess,MESS_result=request.get('MESS_result'),actual_started=False,Native_clocks_reset=False)
    value['handoff_sha']=digest(value);atomic(root/'PRE_ACTUAL_READY.json',value)
    return dict(PASS=False,preparation_PASS=True,Actual_Fresh_not_run=True,pre_actual_handoff=record(root/'PRE_ACTUAL_READY.json'))

def require_live():
    from v44.execution import assert_current
    authority(assert_current()['request'])

def validate_barrier(value):
    expected={(d,a) for d in DAYS for a in ARMS}
    ready=value.get('ready',[]);excluded=value.get('excluded',[])
    keys=[(j['day'],j['arm']) for j in ready+excluded]
    if len(keys)!=28 or len(set(keys))!=28 or set(keys)!=expected:
        raise PermissionError('WEEK2_ALL_28_PREPARATIONS_MUST_BE_RESOLVED_ONCE')
    if value.get('all_preparations_resolved') is not True or value.get('Actual_started_before_barrier') is not False:
        raise PermissionError('WEEK2_COMPLETE_PREPARATION_BARRIER_REQUIRED')
    if any(not j.get('handoff') for j in ready) or any(not j.get('exclusion_reason') for j in excluded):
        raise PermissionError('WEEK2_READY_PROOF_OR_EXCLUSION_REASON_REQUIRED')
    count=min(7,len(ready));plan=value.get('cpu_placement')
    if (count and (not plan or len(plan['slots'])!=count)) or (not count and plan is not None):
        raise PermissionError('WEEK2_SEVEN_SLOT_HEALTHY_POOL_REQUIRED')
    return value

def actual_case(request):
    from v44 import worker,campaign
    from v44.execution import case_scope
    from v44_recovery_r038.phases import load_handoff
    from v44_recovery_r038.cpu import actual_slot
    barrier=validate_barrier(read(BARRIER));verify([request['week2_barrier']])
    if request['week2_barrier']!=record(BARRIER) or not barrier['all_preparations_resolved']:
        raise PermissionError('WEEK2_COMPLETE_PREPARATION_BARRIER_REQUIRED')
    if barrier['lease']!=request['lease']:raise PermissionError('WEEK2_BARRIER_LIVE_LEASE_REQUIRED')
    if not any(j['day']==request['day'] and j['arm']==request['arm'] and j['handoff']==request['R038_pre_actual_handoff'] for j in barrier['ready']):
        raise PermissionError('WEEK2_HEALTHY_HANDOFF_REQUIRED')
    root=Path(request['case_root']);who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1)
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    with actual_slot(request,OPS,barrier['cpu_placement']) as selected,case_scope(request,request['lease'],who):
        try:
            handoff=load_handoff(request)
            if (root/'ACTUAL').exists():raise PermissionError('WEEK2_EXISTING_ACTUAL_CONTEXT_PROTECTED')
            atomic(root/'ACTUAL_START.json',dict(who,UTC=now(),cpu=selected,barrier=record(BARRIER)))
            atomic(root/'progress.json',dict(UTC=now(),stage='ACTUAL_FRESH',status='RUNNING',pid=who['pid']))
            stage=campaign.stage_request(request,'ACTUAL');stage['MESS_result']=handoff['MESS_result']
            result.update(worker.actual(stage,Path(handoff['aidc_folder']),handoff['MESS_plan']))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',new_Planning_or_M_Native_calls_in_actual_worker=0)
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result

def worker(path):
    from v44 import campaign,worker as science
    from v44_recovery_r038 import operations as original,phases,cpu
    from v44_recovery_r029 import conditional_campaign,cpu_placement
    from v44_recovery_r039 import latency
    from v44_recovery_r041.preparation import deny_actual,dump_with_parent
    from v42_may_campaign_native90 import a_stage
    request=read(path);authority(request)
    # Install every inherited scientific/storage improvement. Historical queue
    # permissions are replaced by this campaign's explicit sealed date permit.
    with original.previous.install(),latency.install(require_live),ExitStack() as stack:
        if request['r038_phase']=='PREPARE_SERIAL':
            stack.enter_context(patch.object(phases,'prepare_actual',prepare_actual))
            prepared=phases.compiled_prepare_case()
            stack.enter_context(patch.object(campaign,'_r038_prepare_actual',prepare_actual,create=True))
            stack.enter_context(patch.object(campaign,'run_case',prepared))
            stack.enter_context(patch.object(science,'actual',deny_actual))
            stack.enter_context(patch.object(a_stage,'_dump_state',dump_with_parent(a_stage._dump_state,request['case_root'])))
        elif request['r038_phase']=='ACTUAL_PARALLEL':
            plan=read(BARRIER)['cpu_placement'];cpu.validate_topology(plan)
            stack.enter_context(patch.object(conditional_campaign,'run_case',actual_case))
            stack.enter_context(patch.object(cpu_placement,'compute_cpu_scope',lambda n,receipt=None:cpu.compute_scope(request,n,receipt,plan)))
            psutil.Process().cpu_affinity([plan['slots'][request['parallel_actual_slot']-1]['logical']])
        else:raise PermissionError('WEEK2_EXPLICIT_PHASE_REQUIRED')
        return original.base.worker(request)

def new_request(job,lease):
    from v44.config import axis
    from v44_recovery_r038 import operations as original
    from v44_recovery_r039 import operations as latency
    freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json');data=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
    rows=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']+freeze.get('physics_receipts',[])
    dated=next(r for r in data['days'] if r['day']==job['day']);rows+=list(dated['files'].values())+sources()+[record(PERMIT)]
    root=CAMPAIGN/job['day']/job['arm']/'attempt001'
    case=original.decorate(dict(day=job['day'],arm=job['arm'],worker_slot=1,lane='B2' if job['arm']=='B2' else 'MAIN',
        case_root=str(root),campaign_root=str(CAMPAIGN),lease=lease,sources=rows,scientific_source_sha=freeze['source_sha'],
        axis=axis(job['day']),execution_permit=record(PERMIT),r038_phase='PREPARE_SERIAL'))
    case=latency.attach(case);authority(case)
    target=OPS/'requests'/f"{job['day']}_{job['arm']}.json";atomic(target,case)
    job.update(case_root=str(root),prepare_request=str(target),status='PREPARING');return target

def launch(path,label):
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    folder=OPS/'logs';folder.mkdir(parents=True,exist_ok=True)
    with (folder/(path.stem+'.'+label+'.out.log')).open('ab') as out,(folder/(path.stem+'.'+label+'.err.log')).open('ab') as err:
        return subprocess.Popen([sys.executable,'-X','utf8','-u','-m',ENTRY,'--worker',str(path)],cwd=RUNNER_ROOT,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def publish(state,running=()):
    state['UTC']=now();atomic(STATE,state)
    atomic(CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),phase=state['phase'],cases=state['jobs'],
        workers=[dict(pid=p.pid,day=j['day'],arm=j['arm']) for p,j in running]))

def finish(process,job,planning):
    root=Path(job['case_root']);path=root/'RESULT.json'
    result=read(path) if path.exists() else dict(PASS=False,status='FAILED',error='WORKER_EXIT_WITHOUT_RESULT')
    valid=(process.returncode==0 and result.get('status')=='PRE_ACTUAL_READY' and result.get('preparation_PASS') is True) if planning else (process.returncode==0 and result.get('PASS') is True)
    if planning and valid:
        verify([result['pre_actual_handoff']]);job.update(status='PREPARED',handoff=result['pre_actual_handoff']);atomic(root/'PRE_ACTUAL_RESULT.json',result)
    else:job['status']='PASS' if valid else ('EXCLUDED' if planning else 'ACTUAL_FAILED')
    if not path.exists():atomic(path,result)
    job.update(result=record(path),process_exit=process.returncode)
    if not valid:job['exclusion_reason']=result.get('error',result.get('reason',result.get('status')))

def run():
    from v44_recovery_r038 import cpu
    from v44_recovery_r029.cpu_placement import windows_cpu_sets
    from v44_recovery_r038.phases import load_handoff
    authority();state=read(STATE)
    if state['phase']!='PREPARE_SERIAL' or any(j['status']!='PENDING' for j in state['jobs']):raise PermissionError('WEEK2_ALREADY_STARTED_NO_SILENT_RESTART')
    with coordinator(CAMPAIGN) as lease:
        state['lease']=lease
        atomic(Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json'),dict(UTC=now(),root=str(CAMPAIGN),status='RUNNING',coordinator=lease,revision='V44 r043 / May08–14',prepare_workers=1,actual_workers=7))
        publish(state)
        for job in state['jobs']:
            if (OPS/'STOP.json').exists():state['phase']='USER_STOPPED';publish(state);return
            atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='B2' if job['arm']=='B2' else 'MAIN',r038_phase='PREPARE_SERIAL'))
            try:
                pointer=new_request(job,lease);publish(state);process=launch(pointer,'prepare')
                while process.poll() is None:publish(state,[(process,job)]);time.sleep(5)
                finish(process,job,True)
            except Exception as error:job.update(status='EXCLUDED',exclusion_reason=repr(error),traceback=traceback.format_exc())
            publish(state)
        # Flush and independently validate every preparation before any Actual.
        for job in state['jobs']:
            if job['status']!='PREPARED':continue
            try:
                r=read(job['prepare_request']);r['R038_pre_actual_handoff']=job['handoff'];authority(r);load_handoff(r)
            except Exception as error:job.update(status='EXCLUDED',exclusion_reason='HANDOFF_VALIDATION:'+repr(error))
        ready=[dict(day=j['day'],arm=j['arm'],case_root=j['case_root'],handoff=j['handoff']) for j in state['jobs'] if j['status']=='PREPARED']
        count=min(7,len(ready));plan=cpu.placement(windows_cpu_sets(),count) if count else None
        barrier=dict(UTC=now(),all_preparations_resolved=True,lease=lease,authorization=record(PERMIT),ready=ready,
            excluded=[j for j in state['jobs'] if j['status']=='EXCLUDED'],Actual_started_before_barrier=False,cpu_placement=plan)
        validate_barrier(barrier);atomic(BARRIER,barrier);state['phase']='ACTUAL_PARALLEL';publish(state)
        if count:
            atomic(CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='ACTUAL_PARALLEL',max_workers=7))
            with cpu.reserve_pool(plan,OPS,lease):
                pending=[j for j in state['jobs'] if j['status']=='PREPARED'];running=[];available=list(range(1,count+1))
                while pending or running:
                    while pending and available and not (OPS/'STOP.json').exists():
                        job=pending.pop(0);slot=available.pop(0)
                        r=read(job['prepare_request']);r.update(r038_phase='ACTUAL_PARALLEL',parallel_actual_slot=slot,R038_pre_actual_handoff=job['handoff'],week2_barrier=record(BARRIER))
                        pointer=OPS/'requests'/f"{job['day']}_{job['arm']}_ACTUAL.json";atomic(pointer,r)
                        try:
                            process=launch(pointer,'actual');job.update(status='ACTUAL_RUNNING',parallel_slot=slot);running.append((process,job))
                        except Exception as error:
                            job.update(status='ACTUAL_FAILED',exclusion_reason='ACTUAL_LAUNCH:'+repr(error));available.append(slot)
                        publish(state,running)
                    for process,job in running[:]:
                        if process.poll() is not None:finish(process,job,False);available.append(job['parallel_slot']);running.remove((process,job));publish(state,running)
                    if not running and (OPS/'STOP.json').exists():state['phase']='USER_STOPPED';publish(state);return
                    publish(state,running);time.sleep(5)
        state.update(phase='COMPLETE',all_PASS=all(j['status']=='PASS' for j in state['jobs']));publish(state)
        atomic(OPS/'FINAL_RESULT.json',dict(UTC=now(),phase='COMPLETE',PASS=state['all_PASS'],passed=sum(j['status']=='PASS' for j in state['jobs']),excluded=sum(j['status']=='EXCLUDED' for j in state['jobs']),Actual_failed=sum(j['status']=='ACTUAL_FAILED' for j in state['jobs'])))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--run',action='store_true');parser.add_argument('--worker',type=Path);args=parser.parse_args()
    with bindings():
        if args.prepare:print(prepare(),flush=True)
        elif args.worker:worker(args.worker)
        elif args.run:
            try:run()
            except BaseException as error:atomic(OPS/'COORDINATOR_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise
        else:parser.error('Choose --prepare, --run or --worker')

if __name__=='__main__':main()
