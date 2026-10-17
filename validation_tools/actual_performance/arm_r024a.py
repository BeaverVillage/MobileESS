from pathlib import Path
import sys,os,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024a
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r024a.operations import OPS,CAMPAIGN,PERMIT,validate,workers
from v44_recovery_r024a.handover import REASON
validate();assert not workers() and not alive(read(CAMPAIGN/'COORDINATOR_LEASE.json'))
h=read(OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r024' and h.get('pending_revision') is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
h.update(UTC=now(),pending_revision='v44_recovery_r024a',pending_permit=record(PERMIT),
 pending_validation=record(OPS/'R024A_CHANGE_AND_VALIDATION.json'),pending_regressions=read(OPS/'R024A_CHANGE_AND_VALIDATION.json')['regressions'],
 pending_windows_task='MobileESS_V44_Campaign004_Recovery_R024A',next_performance_revision='v44_recovery_r024a',
 performance_revision_state='R024A_SEALED_ADAPTIVE_PRICING_READY_FRESH_A2_NATIVE0',unconditional_future_B1_B3=True,pilot_PASS_required=False,
 effective_from_day='2025-05-02',collector=str(OPS/'collect_watchdog_r024a.py'),active_source_auditor=str(OPS/'audit_active_revision_r024a.py'),
 latest_user_instruction='r024a adaptive pricing; May02 B3 attempt007 A2 Native0/5400 completed M1 reused; all future B1/B3 A stages unconditional; preserve PASS',
 next='May02 B3 attempt007 fresh A2 then original M2 Actual Fresh after A2 certification; continue future unstarted campaign')
atomic(OPS/'CURRENT_HANDOFF.json',h)
with (OPS/'r024a_handover.log').open('ab') as stream:
 p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r024a.operations','--handover'],cwd=Path(__file__).resolve().parents[2],
  stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(OPS/'R024A_HANDOVER_START.json',dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time(),permit=record(PERMIT)))
print(dict(PASS=True,pid=p.pid))
