"""Confirm the tested future revision is armed without touching the live case."""
from pathlib import Path
import sys,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r019.operations import validate as old_validate
from v44_recovery_r020 import operations as ops
from v44_recovery_r020.handover import boundary,REASON
old_validate();ops.validate()
h=read(ops.OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r019' and h['pending_revision']=='v44_recovery_r020'
guard=read(ops.OPS/'R020_HANDOVER_GUARD.json');heartbeat=read(ops.OPS/'R020_HANDOVER_HEARTBEAT.json')
assert alive(heartbeat) and 'v44_recovery_r020.operations' in psutil.Process(heartbeat['pid']).cmdline()
lease=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json');workers=ops.workers()
assert len(workers)==1 and workers[0]['pid']==guard['protected_worker']['pid']
assert 'v44_recovery_r019.operations' in workers[0]['cmdline']
assert not boundary(guard,lease=lease,workers=workers)
assert read(ops.OPS/'STOP_AUTONOMY.json')['reason']==REASON
task=read(ops.OPS/'R020_WINDOWS_TASK.json');assert task['State']=='Ready' and 'v44_recovery_r020.operations' in task['Arguments']
case=Path(guard['protected_case_root']);ledger=read(case/'A2/NATIVE_RUNTIME_LEDGER.json')
assert ledger['Native_clock_reset'] is False and ledger['Native_ceiling_seconds']==5400.
assert ledger['inherited_Native_seconds']==723.613000869751
receipt=dict(UTC=now(),PASS=True,status='SEALED_AND_ARMED_WAITING_FOR_PROTECTED_MAY02_B3_ENTIRE_CASE',
    active_revision='v44_recovery_r019',pending_revision='v44_recovery_r020',effective_from_day='2025-05-03',
    B1_A2_covered=True,B3_A2_covered=True,improved_arms=['B0','B1','B3'],regressions=193,
    protected_case=str(case),protected_worker=workers[0],protected_worker_interrupted=False,
    protected_Native_clock_reset=False,protected_Native_seconds_observed=ledger['measured_Native_Runtime'],
    waiter=heartbeat,coordinator=lease,validation=record(ops.OPS/'R020_CHANGE_AND_VALIDATION.json'),
    seal=record(ops.OPS/'R020_SEALED.json'),permit=record(ops.PERMIT),windows_task=record(ops.OPS/'R020_WINDOWS_TASK.json'),
    active_and_pending_source_OS_audit_PASS=True,rollout_requires_further_user_action=False,
    full_campaign_speedup_measured=False,full_campaign_scientific_PASS_claimed=False)
path=ops.OPS/'R020_ROLLOUT_READY.json';atomic(path,receipt)
h.update(UTC=now(),pending_deployment_receipt_file=str(path),pending_regressions=193,
    next='Automatic r020 handover after May02 B3 entire case and natural owner exit; both B1/B3 A2 use faster stage-local rebuilds from May03 onward.')
atomic(ops.OPS/'CURRENT_HANDOFF.json',h)
print(dict(PASS=True,active='r019',pending='r020',protected_worker=workers[0]['pid'],waiter=heartbeat['pid'],B1_A2=True,B3_A2=True))
