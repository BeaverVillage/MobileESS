"""Retain r041's preparation fence; release the healthy Actual wave at the barrier."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import sys,subprocess,os,time,argparse,inspect,textwrap,traceback
from v44_recovery_r041 import operations as preparation
from v44_recovery_r040 import operations as actual,batch
from v44.common import read,record,verify,atomic,now
from v44.locks import alive,exclusive_lock,coordinator,process_identity

CAMPAIGN,OPS,STATE=actual.CAMPAIGN,actual.OPS,actual.STATE
ENTRY='v44_recovery_r042.operations';ALGORITHM=actual.ALGORITHM
AMENDMENT=OPS/'R042_AUTOMATIC_POST_PREPARATION_ACTUAL_AUTHORIZATION.json'
RELEASE=OPS/'R042_ACTUAL_RELEASE.json'
original_require=actual.require

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def authority():
    value=read(AMENDMENT);verify(value['sources']+[value['previous_authorization'],value['validation']])
    if value['sources']!=sources() or value['previous_authorization']!=record(preparation.AMENDMENT) or not read(value['validation']['path'])['PASS']:
        raise PermissionError('R042_AUTO_START_SOURCE_AUTHORITY_DRIFT')
    if not value.get('auto_Actual_after_preparations') or not value.get('preparation_fence_retained'):raise PermissionError('R042_EXPLICIT_USER_AUTO_START_REQUIRED')
    preparation.authority();return value

def workers():return [w for w in actual.base.workers() if '--worker' in w['cmdline']]

def resolved_state(state):
    return (state.get('phase')=='PRE_ACTUAL_USER_HOLD' and batch.resolved(state.get('jobs',[]))
        and [actual.key(j) for j in state['jobs']]==[actual.key(j) for j in actual.queue()])

def expected_hold(stop):
    return stop.get('reason')==preparation.HOLD and stop.get('allow_preparation') is True and stop.get('authorization')==record(preparation.AMENDMENT)

def release_authorized(request):
    value=read(RELEASE)
    if value.get('authorization')!=record(AMENDMENT) or value.get('all_preparations_resolved') is not True or value.get('lease')!=request['lease']:
        raise PermissionError('R042_VERIFIED_POST_PREPARATION_RELEASE_REQUIRED')
    if not alive(value['lease']):raise PermissionError('R042_LIVE_ACTUAL_COORDINATOR_REQUIRED')
    if (OPS/'STOP_AUTONOMY.json').exists():raise PermissionError('R042_NEW_USER_STOP_PREVENTS_ACTUAL_START')
    return value

def require():
    original_require()
    from v44.execution import assert_current
    r=assert_current()['request']
    if r.get('R042_authorization')!=record(AMENDMENT):raise PermissionError('R042_LIVE_REQUEST_AUTHORITY_REQUIRED')
    verify(r['R042_sources'])

def attach(request):
    value=dict(preparation.attach(request),R042_authorization=record(AMENDMENT),R042_sources=sources())
    # Completed-stage reuse flags belong to preparation. Leaving them here
    # would select a legacy case runner before the dedicated Actual runner.
    fields=('fresh_a2_parent','a2_checkpoint_parent','r024b_continuation','r024b_adaptive_parent',
        'wall_resume_parent','actual_resume_parent','resume_of','resume_parent','planning_repair_parent','resume_completed_A1_only')
    value['R042_preparation_routing_preserved']={k:value.pop(k) for k in fields if k in value}
    return value

def worker(path):
    r=read(path);authority();verify(r['R042_sources']+r.get('R041_sources',[]))
    if r.get('R042_authorization')!=record(AMENDMENT) or r.get('r038_phase')!='ACTUAL_PARALLEL':raise PermissionError('R042_ACTUAL_ONLY_AFTER_BARRIER')
    release_authorized(r)
    with patch.object(actual,'require',require):return actual.worker(path)

def launch(path,label):
    if label!='actual':raise PermissionError('R042_PREPARATIONS_MUST_STAY_IN_FENCED_R041')
    release_authorized(read(path))
    folder=OPS/'launcher_logs';folder.mkdir(exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (folder/(path.stem+'.r042.out.log')).open('ab') as out,(folder/(path.stem+'.r042.err.log')).open('ab') as err:
        return subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--worker',str(path),'--algorithm',ALGORITHM],cwd=Path(__file__).resolve().parents[1],env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def run_wave(lease,prepared=None):
    state=read(STATE) if prepared is None else prepared[0]
    # Revalidate each handoff independently; one bad case is excluded locally.
    state['lease']=lease
    manifest=batch.preflight(state) if prepared is None else prepared[1]
    state['R042_authorization']=record(AMENDMENT);batch.publish(state)
    atomic(RELEASE,dict(UTC=now(),authorization=record(AMENDMENT),lease=lease,all_preparations_resolved=True,
        ready_cases=[actual.key(j) for j in manifest['ready']],excluded_cases=[actual.key(j) for j in manifest['excluded']],
        preflight_summary=manifest,preparation_Actual_fence_retained=True))
    proxy=type('ActualOps',(),dict(OPS=OPS,CAMPAIGN=CAMPAIGN,STATE=STATE,MANIFEST=actual.MANIFEST,AMENDMENT=actual.AMENDMENT,
        queue=staticmethod(actual.queue),key=staticmethod(actual.key),attach=staticmethod(attach),launch=staticmethod(launch),authorize=staticmethod(actual.authorize)))
    source=textwrap.dedent(inspect.getsource(batch.run_wave))
    from v44_recovery_r039.latency import compile_like
    run=compile_like(batch.run_wave,source,'r042_actual_wave',op=proxy)
    h=read(OPS/'CURRENT_HANDOFF.json');h.update(active_revision='v44_recovery_r042',active_operational_entry=ENTRY,active_operational_permit=record(AMENDMENT),
        active_lease=lease,pending_revision=None,pending_permit=None,Actual_paused_by_user=False,Actual_auto_start_authorization=record(AMENDMENT),
        next='Run all verified healthy Actual/Fresh workers independently; preserve case failure isolation and all physical checks.')
    atomic(OPS/'CURRENT_HANDOFF.json',h)
    if manifest['ready']:
        batch.inherited.background_to_E()
        with batch.reserve_when_available(manifest['cpu_placement'],lease):run(state,manifest)
    else:run(state,manifest)
    state.update(phase='COMPLETE' if all(j['status'] in ('PASS','EXCLUDED','ACTUAL_FAILED') for j in state['jobs']) else 'INTERRUPTED_REQUIRES_DIAGNOSIS',all_PASS=all(j['status']=='PASS' for j in state['jobs']),
        excluded_cases=[actual.key(j) for j in state['jobs'] if j['status']=='EXCLUDED'],Actual_failures=[actual.key(j) for j in state['jobs'] if j['status']=='ACTUAL_FAILED'])
    batch.publish(state);batch.status(state,[])

def watchdog():
    authority()
    with exclusive_lock(OPS/'R042_AUTOMATIC_ACTUAL.lock'):
        while True:
            state=read(STATE);stop_path=OPS/'STOP_AUTONOMY.json';stop=read(stop_path) if stop_path.exists() else {}
            live=alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'));active=workers()
            atomic(OPS/'R042_AUTO_START_HEARTBEAT.json',dict(UTC=now(),**process_identity(),phase=state['phase'],coordinator_alive=live,
                ready=sum(j['status']=='PREPARED' for j in state['jobs']),total=len(state['jobs']),Actual_started=False if stop else None))
            if state.get('phase')=='COMPLETE':return
            if stop and not expected_hold(stop):
                atomic(OPS/'R042_NEW_USER_STOP_PRESERVED.json',dict(UTC=now(),stop=stop));return
            if not live and not active:
                if stop and resolved_state(state):
                    authority()
                    with coordinator(CAMPAIGN) as lease:
                        # Check again under the real exclusive coordinator locks.
                        current=read(STATE)
                        if not resolved_state(current) or not expected_hold(read(stop_path)):return
                        current['lease']=lease
                        manifest=batch.preflight(current);batch.publish(current)
                        atomic(OPS/'R042_ACTUAL_HOLD_PRESERVED.json',read(stop_path));stop_path.unlink()
                        run_wave(lease,(current,manifest))
                    return
                if not stop and RELEASE.exists():
                    verify([read(RELEASE)['authorization']])
                    # An interrupted worker context is never restored or overwritten.
                    for j in state['jobs']:
                        if j['status']=='ACTUAL_RUNNING':batch.reconcile(j)
                    state['phase']='PRE_ACTUAL_USER_HOLD';batch.publish(state)
                    with coordinator(CAMPAIGN) as lease:run_wave(lease)
                    return
            time.sleep(5)

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--watchdog',action='store_true');p.add_argument('--algorithm',required=True,choices=[ALGORITHM]);a=p.parse_args()
    if a.worker:return worker(a.worker)
    try:return watchdog()
    except Exception as error:
        atomic(OPS/'R042_AUTO_START_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc(),no_global_failure_hidden=True))
        raise

if __name__=='__main__':main()
