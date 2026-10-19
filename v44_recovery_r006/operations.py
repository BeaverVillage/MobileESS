"""Single-coordinator fail-continue recovery using unchanged Q250/M4 science."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
import traceback
import psutil
from v44.common import ROOT,DOC,read,record,verify,atomic,digest,now
from v44 import q250_m4_v2 as q
from v44.locks import coordinator,exclusive_lock,alive,process_identity

CAMPAIGN=q.CAMPAIGN
OPS=CAMPAIGN/'AUTONOMOUS_RECOVERY'
PERMIT=OPS/'RECOVERY_R006_EXECUTION_PERMIT.json'


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def validate():
    value=q.validate(PERMIT)
    revision=value['autonomous_recovery_overlay']
    verify(revision['sources'])
    if revision['sources']!=sources() or value['autonomous_recovery_policy_sha']!=digest(revision):
        raise PermissionError('IMMUTABLE_RECOVERY_REVISION_DRIFT')
    return value


def make_permit():
    value=q.validate(q.PERMIT)
    revision=dict(policy='V44_AUTONOMOUS_RECOVERY_R006',sources=sources(),
        diagnostic_only_fix='NONFINITE_SOLVER_BOUND_NULL_WITH_EXPLICIT_NONFINITE_TAG',
        science_parameters_changed=False,Native_budgets_changed=False,
        weather_observation_policy='REJECT_NONFINITE_ROWS_THEN_UNCHANGED_ASOF_MAX_AGE7200',
        weather_raw_modified=False,weather_values_imputed=False,
        initial_running_contract='EXISTING_CONTINUATION_ONLY_FOR_ALL_SOURCE_RUNNING_WITHOUT_NATIVE_WINDOW_NO_NEW_PENDING_STARTS',
        Joint_parameter_lookup='LIVE_APPROVED_M_ONLY_SCOPE_THREADS4_METHOD2_GAP003_WITH_MAY02_ROBUST_BARRIER',
        first_task='MAY03_B2_NEW_ACTUAL_FRESH_CONTEXT_REUSE_REVALIDATED_FULL_PLAN',
        later_M_retries='NEW_ATTEMPT_NATIVE0_NO_SEED_OR_CLOCK_INHERITANCE',max_attempts=3,
        user_instruction='2026-10-17 B2 failed: diagnose and fix; preserve healthy other worker; new revision after common cause fix may revalidate beyond default attempt count',
        original_permit=record(q.PERMIT))
    value.update(UTC=now(),autonomous_recovery_overlay=revision,autonomous_recovery_policy_sha=digest(revision))
    if PERMIT.exists():raise FileExistsError('IMMUTABLE_RECOVERY_PERMIT_ALREADY_EXISTS')
    atomic(PERMIT,value);validate();return value


def latest(root,day,arm):
    attempts=sorted((Path(root)/day/arm).glob('attempt[0-9][0-9][0-9]'))
    return attempts[-1] if attempts else None


def needs_retry(parent,result):
    # One new revision recovery after a proven common input-adapter cause.
    # Attempt004 is Actual/Fresh only; it does not reset any M Native clock.
    if (parent is not None and parent.parent.name=='B2' and parent.parent.parent.name=='2025-05-03'
            and parent.name=='attempt002' and result.get('error')=="ValueError('ORIGINAL_KNOWN_WINDOW_REQUIRED')"):
        return True
    if parent is None or int(parent.name[-3:])>=3:return False
    # Only a diagnosed error with an implemented fix, or the explicit user stop.
    if 'V43_M_OFFICIAL_STOP_REQUESTED' in result.get('error',''):return True
    if result.get('error') == "ValueError('EXACT_THREADS_BOUNDARY_DRIFT:native_optimize')":
        return not (parent/'RECOVERY_R006_APPLIED.json').exists()
    for name in ('M1','M2'):
        m=parent/name/'RESULT.json'
        if m.exists() and read(m).get('implementation_errors')==[
            "ValueError('Out of range float values are not JSON compliant: -inf')"]:
            return not (parent/'RECOVERY_R006_APPLIED.json').exists()
    return False


def states(root):
    from v44.config import DAYS,ARMS
    result={}
    for day in DAYS:
        for arm in ARMS:
            p=latest(root,day,arm)
            if p is None:state='READY'
            elif not (p/'RESULT.json').exists():
                # An unsealed dead worker is quarantined for a diagnosed new
                # attempt by the Codex heartbeat; never silently inherit state.
                state='BLOCKED'
            else:
                r=read(p/'RESULT.json');state=r['status']
                if needs_retry(p,r):state='READY'
            result[(day,arm)]=state
    return result


def decorate(case,permit):
    extra=[permit['Q250_M4_overlay']['source']]+permit['Q250_M4_overlay']['adapter_sources']+sources()
    rows=list({r['path']:r for r in case['sources']+extra}.values())
    case.update(execution_policy_sha=permit['execution_policy_sha'],operational_overlay=permit['operational_overlay'],
        numerical_overlay=permit['numerical_overlay'],numerical_policy_sha=permit['numerical_policy_sha'],
        Q250_M4_overlay=permit['Q250_M4_overlay'],Q250_M4_policy_sha=permit['Q250_M4_policy_sha'],
        autonomous_recovery_overlay=permit['autonomous_recovery_overlay'],
        autonomous_recovery_policy_sha=permit['autonomous_recovery_policy_sha'],Joint_call_cap_seconds=300.,
        sources=rows,source_sha=digest(rows))
    return case


def worker(request):
    from .finite_bound import install
    from .weather import install as weather_install
    from .initial_running import install as running_install
    from v44.campaign import run_case
    validate();verify(request['sources'])
    with q.install(PERMIT),install(),weather_install(Path(request['case_root'])/'WEATHER_OBSERVATION_ADMISSION.json'),running_install():
        if request.get('actual_resume_parent'):
            from .actual_resume import run
            return run(request)
        return run_case(request)


def run():
    from v44.config import B2_ORDER,MAIN_ORDER,axis
    permit=validate();freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
    base=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[
        r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']+freeze.get('physics_receipts',[])
    verify(base);data=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
    with coordinator(CAMPAIGN) as lease:
        atomic(OPS/'COORDINATOR_START.json',dict(UTC=now(),**process_identity(),permit=record(PERMIT)))
        while not (OPS/'STOP_AUTONOMY.json').exists():
            validate();state=states(CAMPAIGN)
            # Explicit latest instruction has priority over the May02 queue.
            may03=latest(CAMPAIGN,'2025-05-03','B2')
            priority=(may03 is not None and may03.name=='attempt002' and state[('2025-05-03','B2')]=='READY')
            target=('2025-05-03','B2') if priority else next((key for key in (*B2_ORDER,*MAIN_ORDER) if state.get(key)=='READY'),None)
            if target is None:
                atomic(OPS/'TERMINAL_SWEEP.json',dict(UTC=now(),all_cases_terminal=True,
                    all_PASS=all(s=='COMPLETE' for s in state.values()),
                    cases=[dict(day=d,arm=a,status=s) for (d,a),s in state.items()]))
                return
            day,arm=target;parent=latest(CAMPAIGN,day,arm);number=int(parent.name[-3:])+1 if parent else 1
            case_root=CAMPAIGN/day/arm/f'attempt{number:03d}'
            lane='B2' if arm=='B2' else 'MAIN'
            atomic(CAMPAIGN/'PHASE.json',dict(lane=lane,UTC=now()))
            dated=next(r for r in data['days'] if r['day']==day)
            case=decorate(dict(day=day,arm=arm,worker_slot=1,lane=lane,case_root=str(case_root),
                campaign_root=str(CAMPAIGN),lease=lease,sources=base+list(dated['files'].values()),
                scientific_source_sha=freeze['source_sha'],axis=axis(day),execution_permit=record(PERMIT)),permit)
            if priority:case['actual_resume_parent']=str(parent)
            verify(case['sources'])
            pointer=OPS/'requests'/f'{day}_{arm}_attempt{number:03d}.json';atomic(pointer,case)
            old=CAMPAIGN/'requests'/f'{day}_{arm}.json'
            if old.exists():
                archived=OPS/'request_history'/f'{day}_{arm}_before_attempt{number:03d}.json'
                if not archived.exists():atomic(archived,read(old))
            atomic(old,case)
            if arm=='B3' and not (CAMPAIGN/'B1_A1'/f'{day}.json').exists():
                case_root.mkdir(parents=True,exist_ok=False)
                atomic(case_root/'RESULT.json',dict(day=day,arm=arm,PASS=False,status='BLOCKED_DEPENDENCY',
                    reason='SAME_DATE_B1_A1_UNAVAILABLE',finished_UTC=now()))
                continue
            log=OPS/'launcher_logs';log.mkdir(parents=True,exist_ok=True)
            with (log/(pointer.stem+'.out.log')).open('ab') as out,(log/(pointer.stem+'.err.log')).open('ab') as err:
                env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
                proc=subprocess.Popen([sys.executable,'-u','-m','v44_recovery_r006.operations','--worker',str(pointer)],
                    cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while True:
                state=states(CAMPAIGN);state[target]='RUNNING'
                atomic(CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),cases=[dict(day=d,arm=a,status=s) for (d,a),s in state.items()],
                    workers=[dict(pid=proc.pid,day=day,arm=arm,worker_slot=1)]))
                if proc.poll() is not None:break
                time.sleep(1.)
            atomic(case_root.with_suffix('.PROCESS_EXIT.json'),dict(UTC=now(),exit_code=proc.returncode))
            if not (case_root/'RESULT.json').exists():
                atomic(case_root/'RESULT.json',dict(day=day,arm=arm,status='FAILED',PASS=False,
                    error='WORKER_EXIT_WITHOUT_RESULT',exit_code=proc.returncode,finished_UTC=now()))
            atomic(case_root/'RECOVERY_R006_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
                new_M_Native_clocks_from_zero=not priority,prior_M_UB_LB_seed_inherited=False,
                Actual_context='NEW_INDEPENDENT',original_parent=str(parent) if parent else None))
            state=states(CAMPAIGN)
            atomic(CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),cases=[dict(day=d,arm=a,status=s) for (d,a),s in state.items()],workers=[]))


def workers():
    found=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            cmd=' '.join(p.info['cmdline'] or [])
            if p.info['name'].lower() in ('python.exe','pythonw.exe') and '--worker' in cmd and (
                    'v44.q250_m4_v2' in cmd or 'v44_recovery_' in cmd):found.append(p.info)
        except (psutil.Error,AttributeError):pass
    return found


def watchdog():
    # Independent of Codex lifetime. It never terminates or suspends a Solver.
    with exclusive_lock(OPS/'SUPERVISOR.lock'):
        while not (OPS/'STOP_AUTONOMY.json').exists():
            try:
                lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');live=alive(lease);active=workers()
                atomic(OPS/'SUPERVISOR_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                    coordinator_alive=live,workers=active,stalled_solver_killed=False))
                if not live and not active and not (OPS/'TERMINAL_SWEEP.json').exists():
                    validate()
                    log=OPS/'supervisor_coordinator.log'
                    with log.open('ab') as stream:
                        proc=subprocess.Popen([sys.executable,'-u','-m','v44_recovery_r006.operations','--coordinator'],
                            cwd=ROOT,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    atomic(OPS/'SUPERVISOR_RESTART.json',dict(UTC=now(),pid=proc.pid,previous_lease=lease))
            except Exception as error:
                atomic(OPS/'SUPERVISOR_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
            time.sleep(30.)


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true')
    p.add_argument('--watchdog',action='store_true');p.add_argument('--make-permit',action='store_true')
    p.add_argument('--handover',action='store_true');a=p.parse_args()
    if a.make_permit:make_permit()
    elif a.worker:worker(read(a.worker))
    elif a.coordinator:run()
    elif a.watchdog:watchdog()
    elif a.handover:
        from .handover import run as handover
        handover()
    else:raise PermissionError('EXPLICIT_RECOVERY_MODE_REQUIRED')


if __name__=='__main__':main()
