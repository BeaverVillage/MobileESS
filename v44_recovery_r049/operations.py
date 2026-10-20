"""Naturally drain the current month worker, requeue May23, and retain all PASS."""
import v44_recovery_r048a as previous
from . import weather
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import argparse,os,sys,time,subprocess,psutil
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,process_identity,EXTERNAL_LOCKS
from v44.prepare import require_execution_permit as raw_require

op=previous.op
HOME=weather.HOME;AUTH=HOME/'AUTHORIZATION.json';VALIDATION=HOME/'VALIDATION.json'
ENTRY='v44_recovery_r049.operations';REASON='R049_WEATHER_REPAIRED_NATURAL_HANDOVER'
ROOT=op.CAMPAIGNS[1];PERMIT=ROOT/'OPERATIONS/MAY23_B0_RECOVERED_WEATHER_PERMIT.json'
CERT=ROOT/'DOCUMENTS/MAY23_B0_RECOVERED_WEATHER_CERTIFICATION.json'


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    base=previous.authority();v=read(AUTH)
    verify(v['sources']+[v['previous_authorization'],v['validation'],v['supplement'],v['user_request']])
    if v['sources']!=sources() or v['previous_authorization']!=record(previous.AUTH) or not read(v['validation']['path'])['PASS']:
        raise PermissionError('R049_EXACT_SOURCE_DERIVATION_AND_VALIDATION_REQUIRED')
    plan=[dict(p,eligible=True,blockers=[]) if p['day']=='2025-05-23' else p for p in base['plan']]
    return dict(base,plan=plan,weather_recovery=record(AUTH))


def authorize_case(r):
    authority()
    if r.get('R049_authorization')!=record(AUTH):raise PermissionError('R049_EXPLICIT_REQUEST_AUTHORITY_REQUIRED')
    proxy=dict(r)
    if r['day']=='2025-05-23':
        if r['arm']!='B0' or r['execution_permit']!=record(PERMIT):raise PermissionError('R049_ONLY_MAY23_B0_REPAIRED_WEATHER')
        verify([record(weather.SUPPLEMENT)]+read(weather.SUPPLEMENT)['sources'])
        proxy['execution_permit']=record(ROOT/'OPERATIONS/B0_EXECUTION_PERMIT.json')
    return previous.authorize_case(proxy)


def new_request(job,lease):
    fn=previous.request_function();fn.__globals__['authorize_case']=previous.authorize_case
    path=fn(job,lease);r=read(path)
    r['R049_authorization']=record(AUTH)
    if r['day']=='2025-05-23':r['execution_permit']=record(PERMIT)
    extra=read(weather.SUPPLEMENT)['sources'] if r['day']=='2025-05-23' else []
    r['sources']=list({x['path']:x for x in r['sources']+sources()+extra+[record(AUTH),record(weather.SUPPLEMENT),r['execution_permit']]}.values());r['source_sha']=digest(r['sources'])
    authorize_case(r);atomic(path,r);return path


@contextmanager
def bindings(r=None):
    from v44 import prepare
    from v44_recovery_r029 import weather as original_weather
    with previous.bindings(),patch.object(op,'ENTRY',ENTRY),patch.object(op,'authority',authority),patch.object(op,'authorize_case',authorize_case),patch.object(op,'new_request',new_request),op.bindings(r):
        fallback=prepare.require_execution_permit
        def require(path,certification):
            if Path(path).resolve()!=PERMIT.resolve():return fallback(path,certification)
            cert=read(CERT)
            with op.core.week.period(tuple(cert['days'])):v=raw_require(path,cert)
            if v.get('allowed_dates')!=['2025-05-23'] or v.get('allowed_arms')!=['B0'] or v.get('R049_authorization')!=record(AUTH):
                raise PermissionError('R049_MAY23_ONLY_PERMIT')
            if r is not None and (r['day'],r['arm'])!=('2025-05-23','B0'):raise PermissionError('R049_SCOPED_PERMIT_NOT_FOR_OTHER_CASES')
            verify(v['recovery_sources']);return v
        with patch.object(prepare,'require_execution_permit',require),patch.object(original_weather,'loader',weather.loader):yield


def transition():
    authority()
    with exclusive_lock(HOME/'TRANSITION.lock'):
        initial=read(op.STATE);old_lease=initial['lease']
        while alive(old_lease):
            state=read(op.STATE);owner=read(op.OWNER)
            # Baseline Actual's single outer shared-resource scope covers both
            # Actual and Fresh. A live heartbeat proves that scope is entered.
            safe=owner.get('mode')=='EXCLUSIVE' or (not state.get('workers') and all(j['status'] in op.core.seq.MAIN_TERMINAL for j in state['jobs']))
            for w in state.get('workers',[]):
                job=next((j for j in state['jobs'] if j['day']==w['day']),None)
                if not job or w['arm']!='B0':continue
                h=Path(job['case_root'])/'ACTUAL/HEARTBEAT.json'
                if h.exists() and read(h).get('pid')==w['pid'] and alive(w):safe=True
            if not op.stop_matches() and not (state.get('main_adopted') and not op.core.seq.STOP.exists()):raise PermissionError('R049_FOREIGN_STOP_PRESERVED')
            if safe:
                atomic(HOME/'PREVIOUS_DRAIN_MARKER.json',read(op.core.seq.STOP) if op.core.seq.STOP.exists() else {})
                atomic(op.core.seq.STOP,dict(UTC=now(),reason=REASON,authorization=record(AUTH),operational_transition=True,user_stop=False,current_workers_must_finish=True))
                break
            atomic(HOME/'TRANSITION_HEARTBEAT.json',dict(UTC=now(),**process_identity(),waiting_for='CURRENT_CASE_ENTERED_ACTUAL_RESOURCE_SCOPE',old_owner=old_lease));time.sleep(3)
        while alive(old_lease):
            if read(op.core.seq.STOP).get('reason')!=REASON:raise PermissionError('R049_NEW_STOP_PRESERVED')
            atomic(HOME/'TRANSITION_HEARTBEAT.json',dict(UTC=now(),**process_identity(),waiting_for='CURRENT_B0_AND_B2_NATURAL_TERMINAL',old_owner=old_lease));time.sleep(3)
        state=read(op.STATE)
        if state.get('workers'):raise PermissionError('R049_ALL_OLD_WORKERS_MUST_DRAIN')
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
        with (HOME/'controller.out.log').open('ab') as out,(HOME/'controller.err.log').open('ab') as err:
            p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',ENTRY,'--run'],cwd=op.core.week.RUNNER_ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        atomic(HOME/'RUN_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time(),authorization=record(AUTH)))


def run():
    authority();state=read(op.STATE)
    if alive(state['lease']) or state.get('workers'):raise PermissionError('R049_PREVIOUS_MONTH_OWNER_MUST_DRAIN')
    if read(op.core.seq.STOP).get('reason')!=REASON:raise PermissionError('R049_EXPLICIT_HANDOVER_REQUIRED')
    with exclusive_lock(op.HOME/'CONTROLLER.lock'),ExitStack() as locks:
        atomic(HOME/'STATE_BEFORE_RECOVERY.json',state)
        job=next(j for j in state['jobs'] if j['day']=='2025-05-23')
        if job['status']!='EXCLUDED' or Path(job['case_root']).exists():raise PermissionError('R049_ONLY_UNSTARTED_EXCLUDED_MAY23')
        job.update(status='BASELINE_QUEUED',exclusion_reason=None,weather_recovery=record(AUTH))
        lease=dict(**process_identity(),UTC=now(),root=str(op.HOME),external_locks=[str(p) for p in EXTERNAL_LOCKS],shared_parent=authority()['parent_lease'])
        atomic(op.LEASE,lease)
        if state.get('main_adopted'):
            locks.enter_context(exclusive_lock(op.MAIN/'locks/COORDINATOR.lock'))
            for path in EXTERNAL_LOCKS:locks.enter_context(exclusive_lock(path))
            main_lease=dict(lease,root=str(op.MAIN));atomic(op.MAIN/'COORDINATOR_LEASE.json',main_lease)
            s=read(op.core.STATE);s['lease']=main_lease;op.core.publish(s)
            atomic(op.OWNER,dict(mode='EXCLUSIVE',UTC=now(),lease=lease,external_locks=[str(p) for p in EXTERNAL_LOCKS]))
        else:atomic(op.OWNER,dict(mode='SHARED_PARENT',UTC=now(),lease=lease,parent=authority()['parent_lease']))
        atomic(op.core.seq.STOP,dict(UTC=now(),reason=op.REASON,authorization=record(op.AUTH),operational_transition=True,user_stop=False,current_workers_must_finish=True))
        state.update(phase='B0_MONTH_PARALLEL',lease=lease,R049_authorization=record(AUTH));state.pop('error',None)
        return previous.continuation()(state,lease,locks)


def main():
    p=argparse.ArgumentParser();p.add_argument('--transition',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--worker',type=Path);p.add_argument('--entry-check',action='store_true');a=p.parse_args()
    if a.transition:return transition()
    r=read(a.worker) if a.worker else None
    with bindings(r):
        if a.worker:return op.worker(a.worker,a.entry_check)
        if a.run:return run()
    p.error('Choose --transition, --run or --worker')

if __name__=='__main__':main()
