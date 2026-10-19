"""Arm a sealed future handover without touching the running Case."""
import os,sys,subprocess
from pathlib import Path
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
import psutil
from v44.common import read,record,verify,atomic,now,ROOT
from v44.locks import alive
from v44_recovery_r016 import operations as revision
from v44_recovery_r016.handover import REASON,require_boundary

ops=revision.OPS;revision.validate()
guard=read(ops/'R016_HANDOVER_GUARD.json')
assert alive(guard['protected_worker']) and alive(guard['protected_coordinator'])
assert '--worker' in psutil.Process(guard['protected_worker']['pid']).cmdline()
try:require_boundary()
except PermissionError as error:
    assert str(error)=='R016_PROTECTED_B3_ENTIRE_CASE_NOT_FINISHED'
else:raise AssertionError('Early r016 coordinator entry must be denied')
for process in psutil.process_iter(['pid','cmdline']):
    command=process.info['cmdline'] or []
    assert not ('v44_recovery_r016.operations' in command and '--handover' in command),'R016_HANDOVER_ALREADY_RUNNING'
stop=ops/'STOP_AUTONOMY.json';prior=read(stop)
assert prior.get('reason')=='R015_PERFORMANCE_VALIDATION_SAFE_HANDOVER_AFTER_HEALTHY_WORKER' and not prior.get('user_stop')
atomic(ops/'R016_PREVIOUS_STOP_PRESERVED.json',prior)
handoff=read(ops/'CURRENT_HANDOFF.json');atomic(ops/'R016_PREVIOUS_HANDOFF_PRESERVED.json',handoff)
atomic(stop,dict(UTC=now(),reason=REASON,user_stop=False,authorization=guard['authorization'],
    protected_worker=guard['protected_worker'],protected_coordinator=guard['protected_coordinator'],
    policy='KEEP_CURRENT_R015_B3_ACTUAL_AND_FRESH_THEN_R016_B0_B1_B3'))
with (ops/'r016_handover.log').open('ab') as stream:
    process=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r016.operations','--handover'],
        cwd=ROOT,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
        stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
identity=dict(pid=process.pid,process_created=psutil.Process(process.pid).create_time())
atomic(ops/'R016_HANDOVER_START.json',dict(UTC=now(),**identity,permit=record(revision.PERMIT),
    guard=record(ops/'R016_HANDOVER_GUARD.json'),protected_worker_interrupted=False))
handoff.update(UTC=now(),pending_revision='v44_recovery_r016',pending_permit=record(revision.PERMIT),
    pending_validation=record(ops/'R016_CHANGE_AND_VALIDATION.json'),pending_regressions=168,
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R016',handover_process_pid=process.pid,
    handover_start=record(ops/'R016_HANDOVER_START.json'),dispatch_hold_reason=REASON,
    next_performance_revision='v44_recovery_r016',performance_revision_state='R016_PENDING_CURRENT_B3_ENTIRE_CASE_NATURAL_FINISH',
    r016_improved_arms=['B0','B1','B3'],
    latest_user_instruction='Use r016 for B0, B1 and B3 from the next Case after current May01 B3 attempt003 entire Actual and independent Fresh naturally finish. No current restart or interruption.',
    next='Finish current r015 May01 B3 attempt003 Actual/Fresh, then r016 single Supervisor/Coordinator May02 B0, B1, B3 queue.')
atomic(ops/'CURRENT_HANDOFF.json',handoff)
print(dict(PASS=True,waiting_handover=identity,active_revision=handoff['active_revision'],pending_revision=handoff['pending_revision'],protected_worker=guard['protected_worker']))
