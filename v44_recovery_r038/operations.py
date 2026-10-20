"""User-authorized serial preparation barrier and seven P-only Actual workers."""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import argparse,subprocess,sys,time
from v44_recovery_r037 import operations as previous
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,process_identity

base=previous.base
CAMPAIGN,OPS,PERMIT=base.CAMPAIGN,base.OPS,base.PERMIT
RAW_ROOT=previous.RAW_ROOT
ENTRY='v44_recovery_r038.operations';ALGORITHM=previous.ALGORITHM
POLICY='R038_SERIAL_PRE_ACTUAL_BARRIER_THEN_SEVEN_P_ONLY_ACTUAL_FRESH_PROCESSES'
AMENDMENT=OPS/'R038_BATCH_EXECUTION_AUTHORIZATION.json'
STATE=OPS/'R038_BATCH_STATE.json'
HOLD_REASON='USER_PRE_ACTUAL_SERIAL_THEN_PARALLEL_PENDING'
latest=base.latest

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def authority():
    v=read(AMENDMENT);verify(v['sources']+[v[k] for k in ('previous_authorization','validation','queue_plan','boundary_request','confirmation')]+v['monitoring_sources'])
    if v['sources']!=sources() or v['policy']!=POLICY or v['previous_authorization']!=record(previous.AMENDMENT):
        raise PermissionError('R038_SEALED_BATCH_AUTHORITY_DRIFT')
    if not read(v['validation']['path'])['PASS'] or v['prepare_workers']!=1 or v['actual_workers']!=7 or not v['P_cores_only']:
        raise PermissionError('R038_EXPLICIT_SERIAL_THEN_PARALLEL_AUTHORITY_REQUIRED')
    previous.authority();return v

def validate():
    v=previous.validate();authority();return dict(v,batch_execution_authorization=record(AMENDMENT))

def states(root):
    result=previous.states(root)
    if STATE.exists():
        for j in read(STATE)['jobs']:
            if j['status'] in ('PREPARING','ACTUAL_RUNNING'):result[(j['day'],j['arm'])]='RUNNING'
            elif j['status']=='PREPARED':result[(j['day'],j['arm'])]='PRE_ACTUAL_READY'
    return result

def authorize(request):
    previous.authorize(request)
    if request.get('R038_batch_authorization')!=record(AMENDMENT):raise PermissionError('R038_REQUEST_AUTHORIZATION_REQUIRED')
    queue=read(authority()['queue_plan']['path'])
    if (request['day'],request['arm']) not in [(j['day'],j['arm']) for j in queue['jobs']]:raise PermissionError('R038_REQUEST_OUTSIDE_FIXED_BATCH')
    if request.get('worker_slot')!=1 or request.get('r038_phase') not in ('PREPARE_SERIAL','ACTUAL_PARALLEL'):
        raise PermissionError('R038_EXPLICIT_PHASE_AND_LEGACY_SCIENTIFIC_SLOT_REQUIRED')
    if request['r038_phase']=='ACTUAL_PARALLEL':
        ref=request['R038_all_prepared'];verify([ref])
        if ref!=record(OPS/'R038_ALL_PRE_ACTUAL_READY.json'):raise PermissionError('R038_ALL_READY_RECEIPT_REQUIRED')
        barrier=read(ref['path'])
        if (barrier.get('PASS') is not True or barrier.get('prepared_jobs')!=7 or
            barrier.get('authorization')!=record(AMENDMENT) or request['R038_pre_actual_handoff'] not in barrier['handoffs']):
            raise PermissionError('R038_SEVEN_PREPARATIONS_REQUIRED_BEFORE_ACTUAL')

@contextmanager
def install(request=None):
    from v44 import campaign
    from v44_recovery_r029 import conditional_campaign,cpu_placement
    from . import phases,cpu
    prepared=phases.compiled_prepare_case() if request and request['r038_phase']=='PREPARE_SERIAL' else None
    with previous.install(),ExitStack() as stack:
        if prepared is not None:
            # r030/r031 wrappers still surround the original conditional chain.
            stack.enter_context(patch.object(campaign,'_r038_prepare_actual',phases.prepare_actual,create=True))
            stack.enter_context(patch.object(campaign,'run_case',prepared))
        if request and request['r038_phase']=='ACTUAL_PARALLEL':
            stack.enter_context(patch.object(conditional_campaign,'run_case',phases.actual_case))
            plan=authority()['cpu_placement']
            stack.enter_context(patch.object(cpu_placement,'compute_cpu_scope',lambda n,receipt=None:cpu.compute_scope(request,n,receipt,plan)))
        yield

def decorate(case):
    with previous.install():case=base.decorate(case,read(PERMIT))
    case['R038_batch_authorization']=record(AMENDMENT)
    case['sources']=list({r['path']:r for r in case['sources']+sources()+[record(AMENDMENT)]}.values())
    case['source_sha']=digest(case['sources']);return case

def worker(path):
    request=read(path);validate();authorize(request);verify(request['sources'])
    if request['r038_phase']=='ACTUAL_PARALLEL':
        import psutil
        from .cpu import validate_topology
        plan=authority()['cpu_placement'];validate_topology(plan)
        slot=request['parallel_actual_slot']
        if type(slot) is not int or not 1<=slot<=7:raise PermissionError('R038_INVALID_PARALLEL_SLOT')
        psutil.Process().cpu_affinity([plan['slots'][slot-1]['logical']])
    with install(request):base.worker(request)

def watchdog():
    validate()
    with exclusive_lock(OPS/'SUPERVISOR.lock'):
        while not (OPS/'STOP_AUTONOMY.json').exists():
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');active=base.workers()
            atomic(OPS/'SUPERVISOR_HEARTBEAT.json',dict(UTC=now(),**process_identity(),revision=ENTRY,
                coordinator_alive=alive(lease),workers=active,stalled_solver_killed=False))
            done=STATE.exists() and read(STATE).get('phase') in ('COMPLETE','PREPARATION_FAILED','INTERRUPTED_REQUIRES_DIAGNOSIS')
            if not alive(lease) and not active and not done:
                with (OPS/'r038_coordinator.log').open('ab') as stream:
                    proc=subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--coordinator','--algorithm',ALGORITHM],
                        cwd=Path(__file__).resolve().parents[1],stdout=stream,stderr=stream,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                atomic(OPS/'SUPERVISOR_RESTART.json',dict(UTC=now(),pid=proc.pid,revision=ENTRY,previous_lease=lease))
            time.sleep(15)

def boundary_ready():
    auth=authority();case=Path(auth['protected_case_root'])
    return (not base.workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json')) and
        (case/'RESULT.json').exists() and type(read(case/'RESULT.json').get('PASS')) is bool)

def handover():
    validate()
    with exclusive_lock(OPS/'R038_HANDOVER.lock'):
        while True:
            stop=OPS/'STOP_AUTONOMY.json'
            if not stop.exists():
                if not (OPS/'R038_HANDOVER_APPLIED.json').exists():raise PermissionError('R038_OWN_HANDOVER_HOLD_REQUIRED')
                break
            if read(stop).get('reason')!=HOLD_REASON or read(stop).get('user_stop'):return
            atomic(OPS/'R038_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),revision=ENTRY,
                phase='WAITING_FOR_MAY04_B1_NATURAL_COMPLETION',workers=base.workers(),worker_untouched=True))
            if boundary_ready():
                validate()
                stop.rename(OPS/'R038_HANDOVER_HOLD_PRESERVED.json')
                atomic(OPS/'R038_HANDOVER_APPLIED.json',dict(UTC=now(),PASS=True,authorization=record(AMENDMENT),
                    boundary_result=record(Path(authority()['protected_case_root'])/'RESULT.json'),worker_terminated=False))
                break
            time.sleep(5)
    watchdog()

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true')
    p.add_argument('--watchdog',action='store_true');p.add_argument('--handover',action='store_true')
    p.add_argument('--algorithm',required=True,choices=[ALGORITHM]);a=p.parse_args()
    if sum((bool(a.worker),a.coordinator,a.watchdog,a.handover))!=1:raise PermissionError('R038_ONE_MODE_REQUIRED')
    if a.handover:return handover()
    if (OPS/'STOP_AUTONOMY.json').exists():raise PermissionError('R038_STOP_PRESERVED')
    validate()
    if a.worker:return worker(a.worker)
    if a.coordinator:
        from .batch import run
        return run()
    return watchdog()

if __name__=='__main__':main()
