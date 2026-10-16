"""Explicit May02--07 Forecast-only cohort alongside the existing May01 job.

The running generator and its pinned physics sources are never edited. Each
child uses the exact generator with its own dated inputs, engine and outputs.
The existing heavy lease covers the cohort until May01 exits; the supervisor
then owns those same OS locks. Children check the live lease before compiling
each independent probe, and wait during an unavailable lease handover.
"""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import argparse
import os
import subprocess
import sys
import time
import traceback

from .common import ROOT,RUNTIME,atomic,read,record,verify,digest,now,NotReady,replace_atomic
from .config import DAYS,axis
from .locks import alive,process_identity,exclusive_lock,coordinator,EXTERNAL_LOCKS

GROUP=RUNTIME/'svr11_revision01/FORECAST_PARALLEL_MAY02_07'
PARENT=RUNTIME/'svr11_revision01/FORECAST_LEASE'
CHILD_DAYS=DAYS[1:]
ACTIVE=RUNTIME/'svr11_revision01/FORECAST_ACTIVE.json'


def forecast_readiness(day):
    """Actual-only initialization blockers do not certify or block Forecast."""
    from .svr11_forecast import base_day
    row=base_day(day)
    allowed=lambda b:(b=='INITIAL_MESS_DATED_SOURCE_UNVERIFIED_TEMPLATE_MAY01_VALUES'
        or b.startswith('INITIAL_RUNNING_SOURCE_SITE_UNRESOLVED:'))
    if any(not allowed(b) for b in row['blockers']):
        raise NotReady('FORECAST_SOURCE_BLOCKED:'+day+':'+str(row['blockers']))
    labels=('native','windows','planning_input','power_authority','provenance','R0_reference',
        'route_table','traffic_forecast','runtime_provider','electrical')
    verify([row['files'][k] for k in labels])
    native=read(row['files']['native']['path']);plan=read(row['files']['planning_input']['path'])
    provenance=read(row['files']['provenance']['path'])
    if any(x['day']!=day for x in (native,plan,provenance)):
        raise ValueError('FORECAST_DATED_SOURCE_MISMATCH')
    from datetime import datetime
    if any(datetime.fromisoformat(x['issue_time']).timestamp()!=axis(day)['issue_seconds'] for x in (native,plan)):
        raise ValueError('FORECAST_ISSUE_AXIS_MISMATCH')
    sites=dict(MESS01='STA01',MESS02='STA12',MESS03='STA08',MESS04='STA06')
    battery=native['battery']
    if native['initial_MESS_sites']!=sites or battery['initial']!=760. or not (
        battery['minimum']<=battery['initial']<=battery['maximum'] and battery['p_limit']<=battery['pcs_kva']):
        raise ValueError('FORECAST_EXPLICIT_DAILY_INITIAL_MESS_ASSUMPTION_DRIFT')
    forecast=provenance['daily_sources']['aemo_forecast.json'];verify([forecast])
    evidence=dict(PASS=True,day=day,status='FORECAST_GENERATION_INPUT_READY',
        scientific_sources={k:row['files'][k] for k in labels},forecast=forecast,
        independent_daily_MESS_initial_state='INDEPENDENT_DAILY_MESS_INITIAL_STATE_ASSUMPTION',
        issue_initial_sites=sites,battery=battery,
        original_overall_input_status=row['status'],Actual_only_blockers_preserved=row['blockers'],
        Actual_input_read=False,Actual_execution_certified=False,
        R0_site_start_and_known_population_changed=False,
        note='Forecast R0 uses the original planning_site/reference_start; no Actual initializer is consulted.')
    # This adapter admits only this Forecast call, never the Actual/campaign path.
    return dict(row,status='INPUT_READY'),evidence


def validate_parent(parent):
    if parent.get('root')!=str(PARENT.resolve()) or parent.get('external_locks')!=[str(p) for p in EXTERNAL_LOCKS]:
        raise PermissionError('EXACT_RUNNING_FORECAST_PARENT_LEASE_REQUIRED')
    if not alive(parent):raise NotReady('RUNNING_MAY01_FORECAST_LEASE_NOT_LIVE')
    import psutil
    command=psutil.Process(parent['pid']).cmdline()
    if 'v44.svr11_forecast' not in command or '2025-05-01' not in command:
        raise PermissionError('ONLY_EXISTING_MAY01_FORECAST_MAY_DELEGATE')


def live_owner(state):
    if state.get('mode') not in ('DELEGATED_EXISTING_MAY01_FORECAST','OWNED_FORECAST_COHORT'):return False
    return alive(state.get('owner',{})) and alive(state.get('supervisor',{}))


def wait_for_lease(group,supervisor):
    while True:
        if not alive(supervisor):raise NotReady('FORECAST_COHORT_SUPERVISOR_GONE')
        state=read(Path(group)/'LEASE_STATE.json')
        if live_owner(state):return state
        # No new engine is constructed until an external owner is live again.
        time.sleep(.1)


def worker(day,group):
    if day not in CHILD_DAYS:raise ValueError('MAY01_RUNNING_SOURCE_AND_PROCESS_PRESERVED')
    from . import svr11_forecast as forecast
    from .svr11_hardware import HARDWARE,scope,source_identity
    group=Path(group);request=read(group/'REQUEST.json');supervisor=request['supervisor']
    verify(request['launcher_sources'])
    if request['days']!=list(CHILD_DAYS):raise ValueError('EXPLICIT_SIX_DATE_FORECAST_SCOPE_REQUIRED')
    h=read(HARDWARE/'HARDWARE.json')
    if record(HARDWARE/'HARDWARE.json')!=request['hardware'] or source_identity()!=request['physics_source_SHA']:
        raise ValueError('FORECAST_COHORT_PHYSICS_DRIFT')
    owned=group/day;owned.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(group/'locks'/f'{day}.lock'):
        row,evidence=forecast_readiness(day);atomic(owned/'FORECAST_ONLY_INPUT_READINESS.json',evidence)
        identity=dict(**process_identity(),day=day,UTC=now(),hardware=request['hardware'],
            source_SHA=h['source_SHA'],launcher_sources=request['launcher_sources'],
                output=str(Path(request['models_root'])/day),Native_calls=0)
        atomic(owned/'START.json',identity);print(dict(event='START',**identity),flush=True)
        try:
            with scope():
                from v42_regcontrol import authority
                original_compile=authority.compile_verified
                def guarded_compile():
                    wait_for_lease(group,supervisor)
                    return original_compile()
                with patch.object(authority,'compile_verified',guarded_compile),patch.object(forecast,'MODELS',Path(request['models_root'])),patch.object(forecast,'base_day',lambda requested:row if requested==day else (_ for _ in ()).throw(ValueError('CROSS_DAY_FORECAST_READ'))):
                    result=forecast.generate(day,progress=lambda r:print(r,flush=True))
            verify(request['launcher_sources'])
            atomic(owned/'RESULT.json',dict(PASS=True,day=day,UTC=now(),result=result,
                Native_calls=0,Actual_calls=0,Fresh_calls=0))
            print(dict(event='COMPLETED',PASS=True,day=day),flush=True)
        except BaseException as error:
            atomic(owned/'RESULT.json',dict(PASS=False,day=day,UTC=now(),error=repr(error),traceback=traceback.format_exc()))
            raise


def supervise(group=GROUP,resume_from=None):
    from .svr11_hardware import HARDWARE,source_identity
    group=Path(group);group.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(group/'locks/SUPERVISOR.lock'):
        if (group/'REQUEST.json').exists():raise FileExistsError('FORECAST_COHORT_ALREADY_CREATED')
        parent=read(PARENT/'COORDINATOR_LEASE.json')
        if alive(parent):validate_parent(parent)
        else:
            from .svr11_grid import ready
            ready(DAYS[0])
        for day in CHILD_DAYS:forecast_readiness(day)
        supervisor=process_identity()
        from .svr11_forecast import MODELS
        models=MODELS if resume_from is None else group/'models'
        restored=[]
        if resume_from is not None:
            previous=read(Path(resume_from)/'REQUEST.json')
            from .locks import alive as process_alive
            if process_alive(previous['supervisor']):raise NotReady('OLD_FORECAST_SUPERVISOR_STILL_LIVE')
            expected_source=source_identity()
            for day in CHILD_DAYS:
                start=Path(resume_from)/day/'START.json'
                if start.exists() and process_alive(read(start)):raise NotReady('OLD_FORECAST_WORKER_STILL_LIVE')
                old=Path(previous.get('models_root',str(MODELS)))/day;target=models/day
                target.mkdir(parents=True,exist_ok=False)
                slots=[]
                for checkpoint in sorted(old.glob('SLOT_*.json')):
                    saved=read(checkpoint);verify([saved['data']])
                    if saved['source_SHA']!=expected_source or saved['day']!=day:
                        raise ValueError('FORECAST_RESUME_SAVED_SOURCE_DAY_DRIFT')
                    (target/checkpoint.name).write_bytes(checkpoint.read_bytes());slots.append(record(checkpoint))
                restored.append(dict(day=day,completed_slots=len(slots),original_checkpoints=slots))
        request=dict(schema='V44_EXPLICIT_SIX_FORECAST_WORKERS_V1',UTC=now(),
            days=list(CHILD_DAYS),supervisor=supervisor,existing_May01=parent,
            models_root=str(models),resume_from=None if resume_from is None else str(resume_from),restored=restored,
            hardware=record(HARDWARE/'HARDWARE.json'),physics_source_SHA=source_identity(),
            launcher_sources=[record(Path(__file__)),record(ROOT/'v44/locks.py'),record(ROOT/'v44/common.py')],
            user_authorization='2026-10-16: keep current May01; run remaining May02--07 with six parallel workers',
            only_Forecast=True,Native_calls=0,Actual_calls=0,Fresh_calls=0,
            independent_processes=True,shared_engine_or_tap_state=False)
        atomic(group/'REQUEST.json',request)
        for source in request['launcher_sources']:
            target=group/'SOURCE_SNAPSHOT'/Path(source['path']).name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(source['path']).read_bytes())
            if record(target)['sha256']!=source['sha256']:raise ValueError('FORECAST_LAUNCHER_ARCHIVE_BYTE_DRIFT')
        atomic(ACTIVE,dict(group=str(group),request=record(group/'REQUEST.json'),UTC=now()))
        def state(mode,owner=None):
            atomic(group/'LEASE_STATE.json',dict(mode=mode,owner=owner,supervisor=supervisor,UTC=now()))
        children={};files=[];lease_stack=ExitStack();owned=False
        try:
            if alive(parent):state('DELEGATED_EXISTING_MAY01_FORECAST',parent)
            else:
                lease=lease_stack.enter_context(coordinator(group));owned=True;state('OWNED_FORECAST_COHORT',lease)
            for day in CHILD_DAYS:
                stdout=(group/(day+'.stdout.log')).open('x',encoding='utf8');files.append(stdout)
                stderr=(group/(day+'.stderr.log')).open('x',encoding='utf8');files.append(stderr)
                env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
                child=subprocess.Popen([sys.executable,'-u','-m','v44.svr11_forecast_parallel','--worker',day,'--group',str(group)],
                    cwd=ROOT,stdout=stdout,stderr=stderr,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
                children[day]=child
                atomic(group/(day+'_PROCESS.json'),dict(pid=child.pid,day=day,supervisor=supervisor,UTC=now()))
            while True:
                active={day:proc for day,proc in children.items() if proc.poll() is None}
                if not active:break
                if not owned and not alive(parent):
                    state('WAITING_EXTERNAL_LOCK_HANDOVER')
                    from v42_may_campaign.common import LockBusy
                    try:
                        lease=lease_stack.enter_context(coordinator(group))
                    except LockBusy:
                        time.sleep(.25);continue
                    owned=True;state('OWNED_FORECAST_COHORT',lease)
                try:
                    atomic(group/'PROCESSES.json',dict(UTC=now(),active_days=list(active),
                        processes={d:dict(pid=p.pid,exit_code=p.poll()) for d,p in children.items()},
                        lease_mode='OWNED_FORECAST_COHORT' if owned else 'DELEGATED_EXISTING_MAY01_FORECAST'))
                except PermissionError as error:
                    # Read-only UI telemetry cannot revoke the heavy lease.
                    import uuid
                    atomic(group/('TELEMETRY_WRITE_ERROR_'+uuid.uuid4().hex+'.json'),dict(UTC=now(),error=repr(error)))
                time.sleep(.5)
            outcomes={d:p.returncode for d,p in children.items()}
            atomic(group/'RESULT.json',dict(PASS=all(code==0 for code in outcomes.values()),
                UTC=now(),exit_codes=outcomes,Native_calls=0,Actual_calls=0,Fresh_calls=0))
        finally:
            # No source changes, silent relaunch, or termination of any worker.
            # An unexpected supervisor loss makes children fail closed at their
            # next independent compile. Their completed slots remain intact.
            state('COHORT_FINISHED' if all(p.poll() is not None for p in children.values()) else 'SUPERVISOR_EXITED')
            lease_stack.close()
            for stream in files:stream.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=CHILD_DAYS)
    parser.add_argument('--group',type=Path,default=GROUP);parser.add_argument('--resume-from',type=Path);args=parser.parse_args()
    # Applies the same IO-only retry to the exact frozen producer's writers.
    # No generator, control, coefficient or saved slot bytes are edited.
    with patch.object(os,'replace',replace_atomic):
        if args.worker:worker(args.worker,args.group)
        else:supervise(args.group,args.resume_from)


if __name__=='__main__':main()
