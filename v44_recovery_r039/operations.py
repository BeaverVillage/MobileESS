"""Keep the live B3 intact; authorized B1 Actual sidecar and r038 continuation."""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
from types import SimpleNamespace
import argparse,os,subprocess,sys,time,traceback,inspect,textwrap
import psutil
from v44_recovery_r038 import operations as previous
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,process_identity,coordinator,EXTERNAL_LOCKS
from . import latency

base=previous.base
CAMPAIGN,OPS,PERMIT=previous.CAMPAIGN,previous.OPS,previous.PERMIT
ENTRY='v44_recovery_r039.operations'
AMENDMENT=OPS/'R039_LATENCY_AND_PARALLEL_ACTUAL_AUTHORIZATION.json'
OWNER=OPS/'R039_RESOURCE_OWNER.json'
REPAIR=OPS/'R039_B1_ACTUAL_REQUEST.json'
HOLD='R039_NATURAL_PREPARATION_BOUNDARY_HANDOVER'
PARENT=CAMPAIGN/'2025-05-04/B1/attempt002'

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def authority():
    value=read(AMENDMENT)
    verify(value['sources']+[value['previous_authorization'],value['validation']])
    if value['sources']!=sources() or value['previous_authorization']!=record(previous.AMENDMENT):raise PermissionError('R039_AUTHORITY_DRIFT')
    if (value.get('slot_wall_limit_seconds','MISSING') is not None or value.get('latency_is_PASS_criterion') is not False
        or value.get('simulation_slot_seconds')!=900 or not read(value['validation']['path'])['PASS']):raise PermissionError('R039_EXPLICIT_WALL_ONLY_REMOVAL_REQUIRED')
    previous.authority();return value

def require():
    from v44.execution import assert_current
    c=assert_current();request=c['request']
    if request.get('R039_latency_authorization')!=record(AMENDMENT):raise PermissionError('R039_REQUEST_AUTHORITY_REQUIRED')
    verify(request['R039_sources'])
    if request.get('r039_repair'):resource_owner(c['lease'])

def resource_owner(lease):
    if not alive(lease):raise PermissionError('R039_REPAIR_COORDINATOR_DEAD')
    # Transfer of the real external OS locks may take a few milliseconds.
    for _ in range(100):
        value=read(OWNER)
        if value.get('coordinator')!=lease:raise PermissionError('R039_REPAIR_COORDINATOR_CHANGED')
        if value.get('mode')=='OWNED_EXTERNAL_LOCKS' and alive(value['external_owner']):return value
        if value.get('mode')=='DELEGATED_ACTUAL_ONLY' and alive(value['external_owner']):
            if value['external_owner']==read(CAMPAIGN/'COORDINATOR_LEASE.json'):return value
        time.sleep(.1)
    raise PermissionError('R039_LIVE_REAL_EXTERNAL_RESOURCE_OWNER_REQUIRED')

def attach(request):
    request=dict(request,R039_latency_authorization=record(AMENDMENT),R039_sources=sources())
    return request

def validate_parent():
    from v44.checkpoints import checked,assert_dead
    from v44.daily import load_aidc
    assert_dead(PARENT);r=read(PARENT/'A1/request.json')
    if (r['day'],r['arm'],r['stage'])!=('2025-05-04','B1','A1'):raise PermissionError('R039_SAME_DATE_ARM_A1_ONLY')
    cp=checked(PARENT/'A1/COMPLETED_STAGE_CHECKPOINT.json',r,'COMPLETED')
    result=read(PARENT/'A1/RESULT.json')
    if not result.get('PASS') or not result.get('FULL_feasible') or result.get('certified_gap',1)>.005:raise PermissionError('R039_CERTIFIED_A1_REQUIRED')
    if read(PARENT/'RESULT.json').get('error')!="RuntimeError('V43_CONTROLLER_EXCEEDED_900_SECOND_SLOT')":raise PermissionError('R039_DIAGNOSED_LATENCY_FAILURE_ONLY')
    folder=Path(result['AIDC_reference']['path']).parent
    load_aidc(folder,r['day']);return folder,cp,result

def repair_case(request):
    from v44.execution import case_scope
    from v44 import worker,campaign
    from v44_recovery_r029 import cpu_placement
    root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
    who=dict(**process_identity(),day=request['day'],arm=request['arm'],worker_slot=1,extra_Actual_worker=True)
    result=dict(day=request['day'],arm=request['arm'],PASS=False,status='FAILED')
    with exclusive_lock(CAMPAIGN/'locks/R039_EXTRA_ACTUAL_SLOT.lock'),exclusive_lock(CAMPAIGN/'locks/cases/2025-05-04_B1.lock'),case_scope(request,request['lease'],who):
        atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha'],R039_sources=request['R039_sources']))
        try:
            require();folder,cp,plan=validate_parent()
            atomic(root/'A1_REUSE.json',dict(UTC=now(),PASS=True,parent_checkpoint=record(PARENT/'A1/COMPLETED_STAGE_CHECKPOINT.json'),
                parent_result=record(PARENT/'A1/RESULT.json'),AIDC_reference=record(folder/'AIDC_REFERENCE.json'),
                parent_source_sha=cp['key']['source_sha'],new_optimization_calls=0,Actual_restart='ORIGINAL_INITIAL_STATE',partial_Actual_state_reused=False))
            atomic(root/'RESTORED_COMPLETED_STAGES.json',dict(A1=dict(root=str(PARENT/'A1'))))
            rows=cpu_placement.windows_cpu_sets();highest=max(r['efficiency_class'] for r in rows)
            psutil.Process().cpu_affinity([r['logical'] for r in rows if r['efficiency_class']==highest])
            with cpu_placement.compute_cpu_scope(1,root/'R039_P_CORE.json') as cpu:
                if cpu['efficiency_core_fallback']:raise PermissionError('R039_P_ONLY_REQUIRED')
                atomic(root/'ACTUAL_START.json',dict(who,UTC=now(),cpu=cpu,original_initial_state=True,authorization=record(AMENDMENT)))
                atomic(root/'progress.json',dict(UTC=now(),stage='ACTUAL_FRESH',status='RUNNING',pid=who['pid']))
                stage=campaign.stage_request(request,'ACTUAL');stage['MESS_result']=None
                result.update(worker.actual(stage,folder,None))
            result.update(status='COMPLETE' if result.get('PASS') else 'FAILED',new_A1_or_M_optimization_calls=0,
                A1_parent=record(PARENT/'A1/RESULT.json'),wall_latency_limit_removed=True)
        except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
        finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
    return result

def worker(path):
    request=read(path);authority();verify(request['sources']+request['R039_sources'])
    if request['R039_latency_authorization']!=record(AMENDMENT):raise PermissionError('R039_WORKER_AUTHORITY_REQUIRED')
    with latency.install(require):
        if request.get('r039_repair'):
            previous.previous.authorize(request)
            from v44_recovery_r029 import conditional_campaign
            with previous.previous.install(),patch.object(conditional_campaign,'run_case',repair_case):return base.worker(request)
        previous.authorize(request)
        return previous.worker(path)

def launch(path,label):
    folder=OPS/'launcher_logs';folder.mkdir(exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (folder/(label+'.out.log')).open('ab') as out,(folder/(label+'.err.log')).open('ab') as err:
        return subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--worker',str(path),'--algorithm',previous.ALGORITHM],
            cwd=Path(__file__).resolve().parents[1],env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def repair_request(lease):
    validate_parent()
    root=CAMPAIGN/'2025-05-04/B1/attempt003'
    if root.exists():raise PermissionError('R039_REPAIR_ATTEMPT_ALREADY_EXISTS')
    old=read(PARENT/'A1/request.json')
    case={k:v for k,v in old.items() if k not in ('stage','output','root','actual_resume_parent','resume_of')}
    case.update(case_root=str(root),lease=lease,r039_repair=True,actual_from_initial_state=True)
    # All old scientific seals remain; the new operational authority is explicit.
    case=attach(case)
    case['sources']=list({r['path']:r for r in case['sources']+sources()+[record(AMENDMENT)]}.values())
    case['source_sha']=digest(case['sources']);atomic(REPAIR,case)
    pointer=CAMPAIGN/'requests/2025-05-04_B1.json'
    atomic(OPS/'R039_B1_PREVIOUS_REQUEST.json',read(pointer));atomic(pointer,case)
    return case

def run_batch(lease,repair):
    from v44_recovery_r038 import batch
    source=textwrap.dedent(inspect.getsource(batch.run))
    source=latency.replace_once(source,'with coordinator(op.CAMPAIGN) as lease:','with _held_coordinator(op.CAMPAIGN) as lease:')
    source=latency.replace_once(source,"        with reserve_pool(auth['cpu_placement'],op.OPS,lease):","        _wait_for_repair()\n        with reserve_pool(auth['cpu_placement'],op.OPS,lease):")
    @contextmanager
    def held(root):yield lease
    def wait_repair():
        while repair is not None and repair.poll() is None:
            atomic(OPS/'R039_HANDOVER_HEARTBEAT.json',dict(UTC=now(),phase='ALL_SEVEN_PREPARED_WAITING_FOR_EXTRA_B1_ACTUAL',repair_pid=repair.pid))
            time.sleep(5)
    def new_launch(pointer,label):
        value=attach(read(pointer));atomic(pointer,value)
        return launch(pointer,pointer.stem+'.'+label)
    # Existing prepared requests/handoffs retain their original source_sha.
    # New latency code is pinned independently in every launched request.
    publish=batch.publish
    def published(state):
        publish(state)
        path=OPS/'CURRENT_HANDOFF.json';h=read(path)
        h.update(active_revision='v44_recovery_r039',active_operational_entry=ENTRY,active_operational_permit=record(AMENDMENT),
            pending_revision=None,pending_permit=None,latency_overlay=record(AMENDMENT),r038_batch_preserved=True,
            entry=f'python -m {ENTRY} --watchdog --algorithm {previous.ALGORITHM}')
        atomic(path,h)
    run=latency.compile_like(batch.run,source,'batch',_held_coordinator=held,_wait_for_repair=wait_repair,launch=new_launch,publish=published)
    with patch.object(batch,'launch',new_launch),patch.object(batch,'publish',published):run()

def dispatch():
    authority()
    with exclusive_lock(OPS/'R039_DISPATCH.lock'):
        lease=dict(**process_identity(),UTC=now(),root=str(CAMPAIGN),external_locks=[str(p) for p in EXTERNAL_LOCKS],
            extra_Actual_delegation=record(AMENDMENT))
        repair=None
        existing=read(REPAIR) if REPAIR.exists() else None
        if existing is None:
            owner=read(CAMPAIGN/'COORDINATOR_LEASE.json')
            if not alive(owner):raise PermissionError('R039_INITIAL_LIVE_CAMPAIGN_OWNER_REQUIRED')
            atomic(OWNER,dict(UTC=now(),mode='DELEGATED_ACTUAL_ONLY',coordinator=lease,external_owner=owner,
                authorization=record(AMENDMENT),owns_external_OS_locks=False,extra_Native_optimization_allowed=False))
            repair_request(lease);repair=launch(REPAIR,'R039_May04_B1_Actual')
            atomic(OPS/'R039_REPAIR_LAUNCH.json',dict(UTC=now(),pid=repair.pid,coordinator=lease,request=record(REPAIR)))
        elif alive(existing['lease']):raise PermissionError('R039_PREVIOUS_REPAIR_COORDINATOR_STILL_LIVE')
        elif not (Path(existing['case_root'])/'RESULT.json').exists():raise PermissionError('R039_INTERRUPTED_REPAIR_REQUIRES_DIAGNOSIS')
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists() and read(stop).get('reason')!=HOLD:raise PermissionError('R039_UNRELATED_USER_STOP_PRESERVED')
        atomic(stop,dict(UTC=now(),reason=HOLD,user_stop=False,current_worker_must_finish=True,authorization=record(AMENDMENT)))
        # The live B3 is never signalled, terminated or suspended. Its current
        # preparation completes under its original sources and original lease.
        while alive(read(CAMPAIGN/'COORDINATOR_LEASE.json')):
            atomic(OPS/'R039_HANDOVER_HEARTBEAT.json',dict(UTC=now(),phase='WAITING_FOR_LIVE_B3_NATURAL_PREPARATION_COMPLETION',
                coordinator=lease,repair_pid=repair.pid if repair else None,workers=base.workers()))
            time.sleep(5)
        with coordinator(CAMPAIGN) as owned:
            atomic(OWNER,dict(UTC=now(),mode='OWNED_EXTERNAL_LOCKS',coordinator=lease,external_owner=owned,owns_external_OS_locks=True))
            if read(stop).get('reason')!=HOLD:raise PermissionError('R039_HOLD_CHANGED')
            atomic(OPS/'R039_HANDOVER_HOLD_PRESERVED.json',read(stop));stop.unlink()
            atomic(OPS/'R039_HANDOVER_APPLIED.json',dict(UTC=now(),PASS=True,live_B3_untouched=True,lease=owned,authorization=record(AMENDMENT)))
            run_batch(owned,repair)
            if repair is not None:repair.wait()

def watchdog():
    authority()
    with exclusive_lock(OPS/'R039_WATCHDOG.lock'):
        while True:
            state=read(previous.STATE)
            if state.get('phase') in ('COMPLETE','PREPARATION_FAILED','INTERRUPTED_REQUIRES_DIAGNOSIS'):return
            helper=read(OPS/'R039_DISPATCH_LAUNCH.json')
            if not alive(helper) and not base.workers():
                with (OPS/'r039_dispatch.log').open('ab') as stream:
                    proc=subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--dispatch','--algorithm',previous.ALGORITHM],cwd=Path(__file__).resolve().parents[1],stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                p=psutil.Process(proc.pid);atomic(OPS/'R039_DISPATCH_LAUNCH.json',dict(pid=p.pid,process_created=p.create_time(),UTC=now()))
            time.sleep(15)

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--dispatch',action='store_true');p.add_argument('--watchdog',action='store_true')
    p.add_argument('--algorithm',required=True,choices=[previous.ALGORITHM]);a=p.parse_args()
    if sum((bool(a.worker),a.dispatch,a.watchdog))!=1:raise PermissionError('R039_ONE_MODE_REQUIRED')
    if a.worker:return worker(a.worker)
    if a.dispatch:return dispatch()
    return watchdog()

if __name__=='__main__':main()
