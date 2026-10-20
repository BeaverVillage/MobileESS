from pathlib import Path
import os,sys,subprocess,psutil
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,atomic,now
from v44_recovery_r018.operations import OPS,PERMIT,ROOT,validate,workers
from v44_recovery_r018.handover import REASON
validate();assert not workers()
value=read(OPS/'CURRENT_HANDOFF.json');assert value['active_revision']=='v44_recovery_r017' and value['pending_revision'] is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
value.update(UTC=now(),latest_user_instruction='Fix May02 B3 A2 frozen artificial-weight drift and resume validated saved S14 support and point at S15, preserving old failure and all measured native time.',
    pending_revision='v44_recovery_r018',pending_permit=record(PERMIT),pending_validation=record(OPS/'R018_CHANGE_AND_VALIDATION.json'),
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R018',dispatch_hold_reason=REASON,
    next_performance_revision='v44_recovery_r018',performance_revision_state='R018_CHECKPOINT_RECOVERY_READY',
    collector=str(OPS/'collect_watchdog_r018.py'),active_source_auditor=str(OPS/'audit_active_revision_r009.py'),
    next='Priority May02 B3 A2 checkpoint continuation at S15; preserve 723.613 seconds of 5400 total, then continue original queue.')
atomic(OPS/'CURRENT_HANDOFF.json',value)
with (OPS/'r018_handover.log').open('ab') as stream:
    p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r018.operations','--handover'],
        cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
started=dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time(),
    permit=record(PERMIT),guard=record(OPS/'R018_HANDOVER_GUARD.json'),old_failure_preserved=True)
atomic(OPS/'R018_HANDOVER_START.json',started);print(started)
