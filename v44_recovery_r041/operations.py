"""Retry diagnosed preparations while the user's Actual stop remains effective."""
from pathlib import Path
from unittest.mock import patch
import argparse,sys,subprocess,os,time,inspect,textwrap
from v44_recovery_r040 import operations as previous,batch
from v44.common import read,record,verify,atomic,now
from v44.locks import coordinator,alive,exclusive_lock,process_identity

base=previous.base
CAMPAIGN,OPS,PERMIT,STATE=previous.CAMPAIGN,previous.OPS,previous.PERMIT,previous.STATE
ENTRY='v44_recovery_r041.operations';ALGORITHM=previous.ALGORITHM
AMENDMENT=OPS/'R041_PREPARATION_REPAIR_AUTHORIZATION.json'
HOLD='USER_ACTUAL_PAUSED_PREPARATION_REPAIR_ALLOWED'
queue=previous.queue;key=previous.key

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def authority():
    v=read(AMENDMENT);verify(v['sources']+[v['previous_authorization'],v['validation']])
    if v['sources']!=sources() or v['previous_authorization']!=record(previous.AMENDMENT) or not read(v['validation']['path'])['PASS']:
        raise PermissionError('R041_SEALED_REPAIR_AUTHORITY_DRIFT')
    if not v.get('Actual_explicitly_paused') or not v.get('preparation_actual_fence'):raise PermissionError('R041_USER_ACTUAL_STOP_REQUIRED')
    previous.authority();return v

def attach(request):return dict(previous.attach(request),R041_authorization=record(AMENDMENT),R041_sources=sources())

def allowed():
    stop=OPS/'STOP_AUTONOMY.json'
    return stop.exists() and read(stop).get('reason')==HOLD and read(stop).get('allow_preparation') is True

def worker(path):
    r=read(path);authority();previous.authorize(r);verify(r['R041_sources'])
    if r.get('R041_authorization')!=record(AMENDMENT) or r.get('r038_phase')!='PREPARE_SERIAL':raise PermissionError('R041_ONLY_PREPARATION_AUTHORIZED_ACTUAL_PAUSED')
    if not allowed():raise PermissionError('R041_PREPARATION_RELEASE_REQUIRED')
    from .preparation import install
    with previous.original.install(r),install(r):result=base.worker(r)
    if result and result.get('preparation_PASS') is True:
        atomic(Path(r['case_root'])/'progress.json',dict(UTC=now(),stage='PRE_ACTUAL_READY',status='WAITING',Actual_started=False))
    return result

def launch(path,label):
    if label!='prepare':raise PermissionError('R041_USER_ACTUAL_HOLD_NO_LAUNCH')
    from v44_recovery_r039 import operations as old
    args=[sys.executable,'-u','-m',ENTRY,'--worker',str(path),'--algorithm',ALGORITHM]
    logs=OPS/'launcher_logs';logs.mkdir(exist_ok=True)
    with (logs/(path.stem+'.r041.out.log')).open('ab') as out,(logs/(path.stem+'.r041.err.log')).open('ab') as err:
        return subprocess.Popen(args,cwd=Path(__file__).resolve().parents[1],env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def new_request(job,lease,original):
    pointer=original(job,lease);r=attach(read(pointer))
    if key(job)==('2025-05-06','B1'):r['planning_repair_parent']=str(CAMPAIGN/'2025-05-06/B1/attempt001/A1')
    if key(job)==('2025-05-07','B1'):
        r.update(wall_resume_parent=str(CAMPAIGN/'2025-05-07/B1/attempt001'),resume_completed_A1_only=True)
    atomic(pointer,r);atomic(CAMPAIGN/'requests'/f"{job['day']}_{job['arm']}.json",r);return pointer

def run():
    authority()
    if not allowed():return
    with coordinator(CAMPAIGN) as lease:
        h=read(OPS/'CURRENT_HANDOFF.json');h.update(UTC=now(),active_revision='v44_recovery_r041',active_operational_entry=ENTRY,active_operational_permit=record(AMENDMENT),active_lease=lease,
            pending_revision=None,pending_permit=None,Actual_paused_by_user=True,next='Repair and retry failed preparations only; never start Actual without an explicit user resume.')
        atomic(OPS/'CURRENT_HANDOFF.json',h)
        source=textwrap.dedent(inspect.getsource(batch.run))
        source=source.replace("if (op.OPS/'STOP_AUTONOMY.json').exists():return","if not _prepare_allowed():return")
        boundary='    manifest=preflight(state);publish(state)'
        if source.count(boundary)!=1:raise ValueError('R041_PRE_ACTUAL_HOLD_BOUNDARY_DRIFT')
        source=source.replace(boundary,"    state['phase']='PRE_ACTUAL_USER_HOLD';publish(state);status(state,[]);return\n"+boundary)
        from v44_recovery_r039.latency import compile_like
        inherited_new=batch.inherited.new_request
        def create(job,lease):return new_request(job,lease,inherited_new)
        namespace_op=type('PreparationOps',(),dict(STATE=STATE,OPS=OPS,CAMPAIGN=CAMPAIGN,queue=staticmethod(queue),key=staticmethod(key),attach=staticmethod(attach),launch=staticmethod(launch)))
        function=compile_like(batch.run,source,'r041_prepare_only',op=namespace_op,_prepare_allowed=allowed)
        with patch.object(batch.inherited,'new_request',create):function(lease)

def watchdog():
    authority()
    with exclusive_lock(OPS/'R041_SUPERVISOR.lock'):
        while allowed():
            state=read(STATE)
            if state.get('phase')=='PRE_ACTUAL_USER_HOLD':return
            if not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json')) and not base.workers():
                with (OPS/'r041_coordinator.log').open('ab') as out:
                    p=subprocess.Popen([sys.executable,'-u','-m',ENTRY,'--coordinator','--algorithm',ALGORITHM],cwd=Path(__file__).resolve().parents[1],stdout=out,stderr=out,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                atomic(OPS/'R041_COORDINATOR_LAUNCH.json',dict(UTC=now(),pid=p.pid))
            time.sleep(15)

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true');p.add_argument('--watchdog',action='store_true');p.add_argument('--algorithm',required=True,choices=[ALGORITHM]);a=p.parse_args()
    if a.worker:return worker(a.worker)
    if a.coordinator:return run()
    return watchdog()

if __name__=='__main__':main()
