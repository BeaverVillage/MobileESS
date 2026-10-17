from pathlib import Path
import sys,psutil,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r022 import operations as ops
ops.validate();h=read(ops.OPS/'CURRENT_HANDOFF.json')
assert h['active_revision']=='v44_recovery_r022' and h.get('pending_revision') is None
lease=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json');assert alive(lease)
assert 'v44_recovery_r022.operations' in psutil.Process(lease['pid']).cmdline()
workers=ops.workers();assert len(workers)==1;who=workers[0];request=read(who['cmdline'][-1]);root=Path(request['case_root'])
assert (request['day'],request['arm'],root.name)==('2025-05-02','B3','attempt005')
assert request['fresh_a2_parent'].endswith('attempt001') and not request.get('a2_checkpoint_parent')
assert not (root/'A1').exists() and not (root/'M1').exists()
admission=read(root/'FRESH_A2_RESTART_ADMISSION.json');compat=read(root/'PARENT_VERIFICATION/R022_PARENT_COMPATIBILITY.json')
assert compat['PASS'] and compat['new_A1_M1_Native_calls']==0 and admission['A2_Native_start']==0.
assert admission['previous_A2_time_imported'] is False and admission['previous_A2_point_or_support_imported'] is False
assert admission['M1_plan_sha']=='0d1bec449f5110dfd76c82265bc98fefa4fb0e8a691445a6f11f660d303eaf10'
ledger=read(root/'A2/NATIVE_RUNTIME_LEDGER.json')
assert ledger['Native_ceiling_seconds']==5400. and not ledger.get('checkpoint_resume') and not ledger['historical_costs_reused']
assert not ledger.get('inherited_Native_seconds') and abs(sum(c['Native_Runtime'] for c in ledger['calls'])-ledger['measured_Native_Runtime'])<1e-7
verify(read(ops.OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
receipt=dict(UTC=now(),PASS=True,revision='v44_recovery_r022',day=request['day'],arm=request['arm'],attempt=root.name,
    status='FRESH_A2_STARTED_FROM_COMPLETED_M1',A2_Native_start=0.,A2_total_native_ceiling=5400.,current_Native_seconds=ledger['measured_Native_Runtime'],
    current_stage=read(root/'progress.json'),worker=who,coordinator=lease,
    admission=record(root/'FRESH_A2_RESTART_ADMISSION.json'),parent_compatibility=record(root/'PARENT_VERIFICATION/R022_PARENT_COMPATIBILITY.json'),
    validation=record(ops.OPS/'R022_CHANGE_AND_VALIDATION.json'),permit=record(ops.PERMIT),Native_smoke=record('D:/MobileESS_V44/development/r022/native_smoke/RESULT.json'),
    regressions=221,old_A2_Native_seconds_preserved=486.14000034332275,new_A1_M1_Native_calls=0,
    actual_B1_A1_and_B3_A2_common_adapter_tested=True,future_rowgen_after_pilot_PASS=True,complete_A2_PASS_not_yet_claimed=True,
    PR='https://github.com/BeaverVillage/MobileESS/pull/233',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],text=True).strip())
atomic(ops.OPS/'R022_FRESH_A2_RESTARTED.json',receipt)
h.update(UTC=now(),active_deployment_receipt_file=str(ops.OPS/'R022_FRESH_A2_RESTARTED.json'),
    adapter_source_commit=receipt['source_commit'],active_regressions=221,
    last_observed_case_stage='May02/B3/attempt005 A2 fresh Native0 rebuild from independently validated completed M1',
    revision_selection='r022 active: certified active-row Phase I and exact fast attribution; common B1 A1 and B3 A2 routing after May02 pilot PASS.')
atomic(ops.OPS/'CURRENT_HANDOFF.json',h)
print(dict(PASS=True,revision='r022',attempt='attempt005',A2_Native_start=0.,current_Native_seconds=ledger['measured_Native_Runtime'],worker=who['pid']))
