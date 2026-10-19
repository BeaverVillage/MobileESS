from pathlib import Path
import sys,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r021 import operations as ops
from v44_recovery_r019.operations import validate as validate19
from v44_recovery_r020.operations import validate as validate20
validate19();validate20();ops.validate()
h=read(ops.OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r021' and h['pending_revision'] is None
lease=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json');assert alive(lease)
assert 'v44_recovery_r021.operations' in psutil.Process(lease['pid']).cmdline()
workers=ops.workers();assert len(workers)==1
who=workers[0];request=read(who['cmdline'][-1]);root=Path(request['case_root'])
assert (request['day'],request['arm'],root.name)==('2025-05-02','B3','attempt004')
assert request['fresh_a2_parent'].endswith('attempt001') and not request.get('a2_checkpoint_parent')
assert not (root/'M1').exists()
admission=read(root/'FRESH_A2_RESTART_ADMISSION.json')
assert admission['PASS'] and admission['A2_Native_start']==0. and admission['previous_A2_time_imported'] is False and admission['previous_A2_point_or_support_imported'] is False
assert admission['M1_plan_sha']=='0d1bec449f5110dfd76c82265bc98fefa4fb0e8a691445a6f11f660d303eaf10'
ledger=read(root/'A2/NATIVE_RUNTIME_LEDGER.json')
assert ledger['Native_ceiling_seconds']==5400. and not ledger.get('checkpoint_resume') and not ledger['historical_costs_reused']
assert not ledger.get('inherited_Native_seconds') and abs(sum(c['Native_Runtime'] for c in ledger['calls'])-ledger['measured_Native_Runtime'])<1e-7
assert read(ops.OPS/'R021_CURRENT_A2_STOPPED.json')['measured_Native_seconds']==1214.5379996299744
for name in ['r021_native_smoke_02','r021_native_namespace_02']:assert read(Path('D:/MobileESS_V44/development')/name/'RESULT.json')['PASS']
record_=dict(UTC=now(),PASS=True,revision='v44_recovery_r021',day=request['day'],arm=request['arm'],attempt=root.name,
    status='FRESH_A2_STARTED_FROM_COMPLETED_M1',A2_Native_start=0.,A2_total_native_ceiling=5400.,
    current_Native_seconds=ledger['measured_Native_Runtime'],current_stage=read(root/'progress.json'),worker=who,coordinator=lease,
    old_A2_Native_seconds_preserved_separately=1214.5379996299744,old_A2_point_support_or_clock_imported=False,new_A1_M1_Native_calls=0,
    admission=record(root/'FRESH_A2_RESTART_ADMISSION.json'),validation=record(ops.OPS/'R021_CHANGE_AND_VALIDATION.json'),
    permit=record(ops.PERMIT),Native_smoke=record('D:/MobileESS_V44/development/r021_native_smoke_02/RESULT.json'),
    native_factory_policy_binding=record('D:/MobileESS_V44/development/r021_native_namespace_02/RESULT.json'),regressions=203,
    independent_full_A2_PASS_not_yet_claimed=True)
p=ops.OPS/'R021_FRESH_A2_RESTARTED.json';atomic(p,record_)
h.update(UTC=now(),active_regressions=203,active_operational_entry='v44_recovery_r021.operations',
    active_deployment_receipt_file=str(p),revision_selection='r021 active: May02 B3 fresh A2 from completed M1 with new zero A2 Native clock, robust simplex and exact rebuild performance.',
    last_observed_case_stage='May02/B3/attempt004 A2 fresh rebuild',next='Complete fresh stabilized A2, then first M2 and independent Actual/Fresh; future B1/B3 A2 retain improvements.')
atomic(ops.OPS/'CURRENT_HANDOFF.json',h)
print(dict(PASS=True,revision='r021',attempt='attempt004',A2_Native_start=0.,current_Native_seconds=ledger['measured_Native_Runtime'],worker=who['pid']))
