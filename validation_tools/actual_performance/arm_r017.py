"""Arm the sealed r017 boundary waiter without interrupting any campaign work."""
from pathlib import Path
import os,sys,subprocess,psutil
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,atomic,now,verify
from v44.locks import alive
from v44_recovery_r017.operations import OPS,PERMIT,validate,ROOT
from v44_recovery_r017.handover import REASON

validate();guard=read(OPS/'R017_HANDOVER_GUARD.json');value=read(OPS/'CURRENT_HANDOFF.json')
assert value['active_revision']=='v44_recovery_r015' and value['pending_revision']=='v44_recovery_r016'
stop=read(OPS/'STOP_AUTONOMY.json');assert stop['reason']==REASON and not stop.get('user_stop')
for process in psutil.process_iter(['name','cmdline']):
    command=process.info['cmdline'] or []
    if (process.info['name'] or '').lower() in ('python.exe','pythonw.exe'):
        assert not ('v44_recovery_r016.operations' in command),'OLD_R016_PROCESS_STILL_ALIVE'
        assert not ('v44_recovery_r017.operations' in command),'R017_ALREADY_RUNNING'
verify([record(OPS/'R017_WINDOWS_TASK.json'),guard['protected_request']])
value.update(UTC=now(),latest_user_instruction='Apply sealed structural r017 to B0, B1 and B3 after current May01 B3 entire Actual and independent Fresh plus natural worker/coordinator exit; replace pending r016.',
    pending_revision='v44_recovery_r017',pending_permit=record(PERMIT),
    pending_validation=record(OPS/'R017_CHANGE_AND_VALIDATION.json'),pending_regressions=173,
    next_performance_revision='v44_recovery_r017',performance_revision_state='R017_PENDING_CURRENT_B3_ENTIRE_CASE_NATURAL_FINISH',
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R017',dispatch_hold_reason=REASON,
    handover_process_pid=None,handover_start=None,pending_handover_start_file=str(OPS/'R017_HANDOVER_START.json'),
    r017_improved_arms=['B0','B1','B3'],
    collector=str(OPS/'collect_watchdog_r017.py'),active_source_auditor=str(OPS/'audit_active_revision_r008.py'),
    superseded_r016_permit=record(OPS/'RECOVERY_R016_EXECUTION_PERMIT.json'),
    next='Finish current May01 B3 entire Actual and independent Fresh, then r017 single Supervisor/Coordinator continues next ready May02 B0, B1, B3 queue.')
atomic(OPS/'CURRENT_HANDOFF.json',value)
log=OPS/'r017_handover.log'
with log.open('ab') as stream:
    process=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r017.operations','--handover'],
        cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
identity=dict(pid=process.pid,process_created=psutil.Process(process.pid).create_time())
started=dict(UTC=now(),**identity,permit=record(PERMIT),guard=record(OPS/'R017_HANDOVER_GUARD.json'),
    protected_worker_interrupted=False,superseded_r016_waiter_naturally_exited=True)
atomic(OPS/'R017_HANDOVER_START.json',started)
# Do not rewrite CURRENT_HANDOFF after starting the waiter: its coordinator
# may already be promoting the active revision at a fast completed boundary.
atomic(OPS/'R017_SAFE_HANDOVER_ARMED.json',dict(UTC=now(),PASS=True,revision='v44_recovery_r017',
    improved_arms=['B0','B1','B3'],regressions=173,permit=record(PERMIT),
    validation=record(OPS/'R017_CHANGE_AND_VALIDATION.json'),waiting_handover=started,
    windows_task=record(OPS/'R017_WINDOWS_TASK.json'),
    protected_worker=guard['protected_worker'],protected_coordinator=guard['protected_coordinator'],
    current_worker_not_interrupted=True,r016_task_disabled=True,
    boundary='ENTIRE_CASE_TERMINAL_AND_NATURAL_WORKER_COORDINATOR_EXIT',
    collector=record(OPS/'collect_watchdog_r017.py'),auditor=record(OPS/'audit_active_revision_r008.py')))
print(started)
