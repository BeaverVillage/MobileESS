from pathlib import Path
import sys,os,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022u
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r022u.operations import OPS,PERMIT,validate
from v44_recovery_r022u.handover import REASON
validate();h=read(OPS/'CURRENT_HANDOFF.json');guard=read(OPS/'R022U_HANDOVER_GUARD.json')
assert h['active_revision']=='v44_recovery_r022' and h.get('pending_revision') is None
assert read(OPS/'STOP_AUTONOMY.json')['reason']==REASON
assert alive(guard['protected_worker']) and alive(guard['protected_coordinator'])
h.update(UTC=now(),pending_revision='v44_recovery_r022u',pending_permit=record(PERMIT),
    pending_validation=record(OPS/'R022U_CHANGE_AND_VALIDATION.json'),pending_regressions=234,
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R022U',
    next_performance_revision='v44_recovery_r022u',performance_revision_state='R022_UNCONDITIONAL_FUTURE_B1_B3_READY_NO_A2_PASS_GATE',
    unconditional_future_B1_B3=True,pilot_PASS_required=False,
    collector=str(OPS/'collect_watchdog_r022u.py'),active_source_auditor=str(OPS/'audit_active_revision_r022u.py'),
    latest_user_instruction='Apply r022 improvements unconditionally to every subsequent unstarted B1 and B3; do not require current A2 PASS.',
    next='Current r022 worker continues to natural terminal status; next unstarted B1 A1 and B3 A2 all use r022u unconditional r022 row generation regardless of current A2 outcome.')
atomic(OPS/'CURRENT_HANDOFF.json',h);root=Path(__file__).resolve().parents[2]
with (OPS/'r022u_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r022u.operations','--handover'],cwd=root,
        stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(OPS/'R022U_HANDOVER_START.json',dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(PERMIT),
    current_worker_preserved=guard['protected_worker'],pilot_PASS_required=False))
print(dict(PASS=True,pid=proc.pid,current_worker_unchanged=guard['protected_worker']['pid'],pilot_PASS_required=False))
