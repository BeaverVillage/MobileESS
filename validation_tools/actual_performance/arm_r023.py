"""Replace only the pending handover, after its old waiter naturally exits."""
from pathlib import Path
import sys,os,subprocess,psutil,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r023
from v44.common import read,record,atomic,now
from v44.locks import alive
from v44_recovery_r023.operations import OPS,PERMIT,validate
from v44_recovery_r023.handover import REASON
validate();h=read(OPS/'CURRENT_HANDOFF.json');guard=read(OPS/'R023_HANDOVER_GUARD.json')
assert h['active_revision']=='v44_recovery_r022' and h['pending_revision']=='v44_recovery_r022u'
stop=read(OPS/'STOP_AUTONOMY.json')
assert stop['reason']=='R022U_UNCONDITIONAL_FUTURE_SCOPE_SAFE_HANDOVER'
assert alive(guard['protected_worker']) and alive(guard['protected_coordinator'])
atomic(OPS/'R023_SUPERSEDED_PENDING_HANDOFF.json',h)
atomic(OPS/'R023_SUPERSEDED_PENDING_STOP.json',stop)
atomic(OPS/'STOP_AUTONOMY.json',dict(UTC=now(),reason=REASON,user_stop=False,
    scope='HOLD_NEXT_DISPATCH_ONLY_CURRENT_WORKER_AND_ALL_REMAINING_STAGES_CONTINUE',pilot_PASS_required=False))
# The old waiter sees the superseding hold and exits on its own. No process kill.
prior=read(OPS/'R022U_HANDOVER_START.json')
deadline=time.monotonic()+45
while alive(prior) and time.monotonic()<deadline:time.sleep(.5)
if alive(prior):raise RuntimeError('R023_PREVIOUS_PENDING_WAITER_STILL_ALIVE')
assert alive(guard['protected_worker']) and alive(guard['protected_coordinator'])
h.update(UTC=now(),pending_revision='v44_recovery_r023',pending_permit=record(PERMIT),
    pending_validation=record(OPS/'R023_CHANGE_AND_VALIDATION.json'),
    pending_regressions=read(OPS/'R023_CHANGE_AND_VALIDATION.json')['regressions'],
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R023',
    next_performance_revision='v44_recovery_r023',performance_revision_state='R023_NEXT_DAY_EXACT_SPARSE_ASSEMBLY_READY',
    unconditional_future_B1_B3=True,pilot_PASS_required=False,effective_from_day='2025-05-03',
    collector=str(OPS/'collect_watchdog_r023.py'),active_source_auditor=str(OPS/'audit_active_revision_r023.py'),
    protected_case=guard['protected_case_root'],protected_worker_pid=guard['protected_worker']['pid'],
    superseded_unlaunched_pending_revision='v44_recovery_r022u',
    pending_deployment_receipt_file=str(OPS/'R023_NEXT_DAY_ROLLOUT_READY.json'),
    pending_handover_start_file=str(OPS/'R023_HANDOVER_START.json'),
    latest_user_instruction='Improve assembly bottleneck and apply from May03 onward; retain unconditional future B1/B3 rollout.',
    revision_selection='Current May02 remains sealed r022; May03 onward uses r023 exact sparse assembly and unconditional r022 row generation.',
    next='Wait for current entire May02 case and coordinator natural terminal exit, then use r023 from May03. A2 PASS is not an eligibility gate.')
atomic(OPS/'CURRENT_HANDOFF.json',h)
with (OPS/'r023_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r023.operations','--handover'],cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(OPS/'R023_HANDOVER_START.json',dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(PERMIT),
    current_worker_preserved=guard['protected_worker'],pilot_PASS_required=False,effective_from_day='2025-05-03',
    superseded_waiter_exited_naturally=True))
print(dict(PASS=True,pid=proc.pid,current_worker_unchanged=guard['protected_worker']['pid'],pilot_PASS_required=False))
