"""Resolve every preparation, then dispatch the healthy subset independently."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import argparse,os,subprocess,sys,time,traceback
import psutil
from v44_recovery_r039 import operations as previous
from v44_recovery_r038 import operations as original
from v44_recovery_r038 import cpu
from v44.common import read,record,verify,atomic,now
from v44.locks import alive,exclusive_lock,coordinator,process_identity

base=original.base
CAMPAIGN,OPS,PERMIT=original.CAMPAIGN,original.OPS,original.PERMIT
STATE=original.STATE
ENTRY='v44_recovery_r040.operations';ALGORITHM=original.ALGORITHM
AMENDMENT=OPS/'R040_CASE_ISOLATION_AUTHORIZATION.json'
HOLD='R040_CASE_ISOLATION_NATURAL_BOUNDARY'
MANIFEST=OPS/'R040_RESOLVED_BATCH_MANIFEST.json'

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def authority():
    value=read(AMENDMENT);verify(value['sources']+[value['previous_authorization'],value['validation']])
    if value['sources']!=sources() or value['previous_authorization']!=record(previous.AMENDMENT):raise PermissionError('R040_SOURCE_AUTHORITY_DRIFT')
    if not read(value['validation']['path'])['PASS'] or not value.get('exclude_only_failed_case') or value.get('max_Actual_workers')!=7:
        raise PermissionError('R040_EXPLICIT_INDEPENDENT_CASE_AUTHORIZATION_REQUIRED')
    previous.authority();return value

def queue():return read(original.authority()['queue_plan']['path'])['jobs']

def key(job):return (job['day'],job['arm'])

def attach(request):
    return dict(previous.attach(request),R040_authorization=record(AMENDMENT),R040_sources=sources())

def subset(request):
    ref=request['R040_resolved_manifest'];verify([ref]);manifest=read(ref['path'])
    if manifest.get('authorization')!=record(AMENDMENT) or manifest.get('lease')!=request['lease']:
        raise PermissionError('R040_RESOLVED_MANIFEST_AUTHORITY_OR_LEASE_DRIFT')
    from .batch import validate_manifest
    validate_manifest(manifest,queue())
    slot=request['parallel_actual_slot'];entries=manifest['ready']
    if type(slot) is not int or not 1<=slot<=len(entries):raise PermissionError('R040_SUBSET_SLOT_OUT_OF_RANGE')
    item=entries[slot-1]
    if key(item)!=key(request) or item['handoff']!=request['R038_pre_actual_handoff'] or item['case_root']!=request['case_root']:
        raise PermissionError('R040_CASE_NOT_IN_RESOLVED_HEALTHY_SUBSET')
    return manifest

def authorize(request):
    authority()
    if request.get('R040_authorization')!=record(AMENDMENT):raise PermissionError('R040_REQUEST_AUTHORITY_REQUIRED')
    verify(request['sources']+request['R039_sources']+request['R040_sources'])
    if request.get('R039_latency_authorization')!=record(previous.AMENDMENT) or request['R040_sources']!=sources():
        raise PermissionError('R040_LATENCY_AND_OPERATIONAL_SOURCES_REQUIRED')
    if key(request) not in {key(j) for j in queue()} or request.get('worker_slot')!=1:
        raise PermissionError('R040_FIXED_CASE_AND_LEGACY_SLOT_REQUIRED')
    if request.get('r038_phase')=='PREPARE_SERIAL':original.authorize(request)
    elif request.get('r038_phase')=='ACTUAL_PARALLEL':
        # The new user authority replaces only r038's all-seven-success gate.
        # Every scientific, storage, checkpoint and real resource guard remains.
        original.previous.authorize(request);subset(request)
    else:raise PermissionError('R040_EXPLICIT_PREPARE_OR_ACTUAL_PHASE_REQUIRED')

def require():
    previous.require()
    from v44.execution import assert_current
    r=assert_current()['request']
    if r.get('R040_authorization')!=record(AMENDMENT):raise PermissionError('R040_LIVE_REQUEST_AUTHORITY_REQUIRED')
    verify(r['R040_sources'])

def worker(path):
    request=read(path);authorize(request)
    if request['r038_phase']=='PREPARE_SERIAL':return previous.worker(path)
    from .actual import actual_case
    from v44_recovery_r029 import conditional_campaign,cpu_placement
    plan=subset(request)['cpu_placement'];cpu.validate_topology(plan)
    psutil.Process().cpu_affinity([plan['slots'][request['parallel_actual_slot']-1]['logical']])
    with original.previous.install(),previous.latency.install(require),patch.object(conditional_campaign,'run_case',actual_case),patch.object(
            cpu_placement,'compute_cpu_scope',lambda n,receipt=None:cpu.compute_scope(request,n,receipt,plan)):
        return base.worker(request)

def launch(path,label):
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    folder=OPS/'launcher_logs';folder.mkdir(exist_ok=True)
    with (folder/(path.stem+'.r040.'+label+'.out.log')).open('ab') as out,(folder/(path.stem+'.r040.'+label+'.err.log')).open('ab') as err:
        return subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--worker',str(path),'--algorithm',ALGORITHM],
            cwd=Path(__file__).resolve().parents[1],env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def run():
    from .batch import run as batch_run
    authority()
    with coordinator(CAMPAIGN) as lease:
        h=read(OPS/'CURRENT_HANDOFF.json');h.update(UTC=now(),active_revision='v44_recovery_r040',active_operational_entry=ENTRY,
            active_operational_permit=record(AMENDMENT),active_lease=lease,pending_revision=None,pending_permit=None,pending_validation=None,
            collector=str(OPS/'collect_watchdog_r040.py'),active_source_auditor=str(OPS/'audit_active_revision_r040.py'),
            latest_user_instruction=authority()['user_instruction'],entry=f'python -m {ENTRY} --watchdog --algorithm {ALGORITHM}',
            next='Resolve every preparation. Exclude only failed/unready case; run all validated healthy Actual/Fresh cases independently on P cores.')
        atomic(OPS/'CURRENT_HANDOFF.json',h)
        return batch_run(lease)

def watchdog():
    authority()
    with exclusive_lock(OPS/'R040_SUPERVISOR.lock'):
        while not (OPS/'STOP_AUTONOMY.json').exists():
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');workers=base.workers();state=read(STATE)
            atomic(OPS/'R040_SUPERVISOR_HEARTBEAT.json',dict(UTC=now(),**process_identity(),coordinator_alive=alive(lease),workers=workers))
            if state.get('phase')=='COMPLETE':return
            if not alive(lease) and not workers:
                with (OPS/'r040_coordinator.log').open('ab') as stream:
                    p=subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--coordinator','--algorithm',ALGORITHM],cwd=Path(__file__).resolve().parents[1],stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                atomic(OPS/'R040_COORDINATOR_LAUNCH.json',dict(pid=p.pid,process_created=psutil.Process(p.pid).create_time(),UTC=now()))
            time.sleep(15)

def handover():
    authority()
    with exclusive_lock(OPS/'R040_HANDOVER.lock'):
        stop=OPS/'STOP_AUTONOMY.json'
        while stop.exists():
            if read(stop).get('reason')!=HOLD:return
            active=base.workers();lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
            atomic(OPS/'R040_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),workers=active,coordinator=lease,current_worker_untouched=True))
            if not active and not alive(lease):
                atomic(OPS/'R040_HANDOVER_HOLD_PRESERVED.json',read(stop));stop.unlink()
                atomic(OPS/'R040_HANDOVER_APPLIED.json',dict(UTC=now(),PASS=True,authorization=record(AMENDMENT),worker_terminated=False))
                break
            time.sleep(5)
    watchdog()

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true');p.add_argument('--watchdog',action='store_true');p.add_argument('--handover',action='store_true')
    p.add_argument('--algorithm',required=True,choices=[ALGORITHM]);a=p.parse_args()
    if sum((bool(a.worker),a.coordinator,a.watchdog,a.handover))!=1:raise PermissionError('R040_ONE_MODE_REQUIRED')
    if a.worker:return worker(a.worker)
    if a.handover:return handover()
    if (OPS/'STOP_AUTONOMY.json').exists():return
    if a.coordinator:return run()
    return watchdog()

if __name__=='__main__':main()
