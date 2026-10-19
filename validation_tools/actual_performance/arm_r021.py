from pathlib import Path
import os,sys,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r021.operations import OPS,CAMPAIGN,PERMIT,ROOT,validate,workers
from v44_recovery_r021.handover import REASON
validate();assert not workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'))
assert read('D:/MobileESS_V44/development/r021_native_smoke_02/RESULT.json')['PASS']
h=read(OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r019' and h.get('pending_revision') is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
h.update(UTC=now(),pending_revision='v44_recovery_r021',pending_permit=record(PERMIT),
    pending_validation=record(OPS/'R021_CHANGE_AND_VALIDATION.json'),pending_regressions=203,
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R021',next_performance_revision='v44_recovery_r021',
    performance_revision_state='R021_SEALED_READY_FRESH_A2_AFTER_M1_ZERO_NATIVE',effective_from_day='2025-05-02',
    collector=str(OPS/'collect_watchdog_r021.py'),active_source_auditor=str(OPS/'audit_active_revision_r012.py'),
    latest_user_instruction='Fix numerical instability and improve speed; restart May02 B3 A2 from completed M1. User clarified new A2 Native clock starts at zero.',
    superseded_unlaunched_revision='v44_recovery_r020',
    next='May02 B3 attempt004 fresh A2 at S0, no previous A2 point/support/time; reuse completed A1/M1. Then M2 and independent Actual/Fresh and future B1/B3 A2 queue.')
atomic(OPS/'CURRENT_HANDOFF.json',h)
with (OPS/'r021_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r021.operations','--handover'],cwd=ROOT,
        stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
receipt=dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(PERMIT),
    guard=record(OPS/'R021_HANDOVER_GUARD.json'),Native_smoke=record('D:/MobileESS_V44/development/r021_native_smoke_02/RESULT.json'))
atomic(OPS/'R021_HANDOVER_START.json',receipt);print(receipt)
