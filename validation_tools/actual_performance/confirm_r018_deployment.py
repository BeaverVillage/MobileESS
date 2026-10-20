"""Confirm the exact requested continuation and cumulative measured budget."""
from pathlib import Path
import sys,psutil,json,urllib.request
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r018 import operations as ops
from v44_recovery_r018.a2_continue import ADMISSION

permit=ops.validate();proof=read(ADMISSION)
handoff=read(ops.OPS/'CURRENT_HANDOFF.json');assert handoff['active_revision']=='v44_recovery_r018'
lease=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json');assert alive(lease)
owner=psutil.Process(lease['pid']);assert 'v44_recovery_r018.operations' in owner.cmdline()
workers=ops.workers();assert len(workers)==1
worker=workers[0];assert 'v44_recovery_r018.operations' in worker['cmdline']
request=read(worker['cmdline'][-1]);assert (request['day'],request['arm'])==('2025-05-02','B3')
root=Path(request['case_root']);assert root.name=='attempt002'
assert request['a2_checkpoint_parent']==proof['parent'];verify([proof['original_failure'],proof['Native_account']['ledger']])
assert not (root/'M1').exists(),'M1_MUST_REMAIN_A_VERIFIED_PARENT_NOT_REOPTIMIZED'
ledger=read(root/'A2/NATIVE_RUNTIME_LEDGER.json');parent=read(proof['Native_account']['ledger']['path'])
assert ledger['checkpoint_resume'] and ledger['Native_clock_reset'] is False
assert ledger['Native_ceiling_seconds']==5400. and ledger['inherited_Native_seconds']==proof['Native_account']['measured']
assert ledger['calls'][:len(parent['calls'])]==parent['calls']
assert ledger['measured_Native_Runtime']>=parent['measured_Native_Runtime']
restored=read(root/'A2/OUTPUT/A2_CHECKPOINT_RESTORATION.json');assert restored['PASS'] and restored['next_solve']==15
phase=root/'A2/OUTPUT/PHASE_I/S15'
assert phase.exists(),'CONTINUATION_HAS_NOT_YET_ENTERED_S15'
with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=10) as response:monitor=json.load(response)
text=monitor.get('build',{}).get('detail','')
assert '기존 Native 723.6초 승계' in text
receipt=dict(UTC=now(),PASS=True,revision='v44_recovery_r018',request=record(worker['cmdline'][-1]),
    coordinator=lease,worker=worker,stage=read(root/'progress.json'),checkpoint_start_solve=15,
    inherited_Native_seconds=proof['Native_account']['measured'],Native_total_ceiling=5400.,
    measured_Native_seconds_now=ledger['measured_Native_Runtime'],Native_clock_reset=False,
    original_calls_preserved=len(parent['calls']),new_A1_or_M1_optimization_calls=0,
    original_failure_preserved=proof['original_failure'],checkpoint_admission=record(ADMISSION),
    validation=record(ops.OPS/'R018_CHANGE_AND_VALIDATION.json'),permit=record(ops.PERMIT),
    actual_stage_folder=str(phase),monitor_budget_carry_display_verified=True,monitor_details=text)
atomic(ops.OPS/'R018_CHECKPOINT_RESUME_DEPLOYED.json',receipt)
handoff.update(UTC=now(),active_regressions=179,active_operational_entry='v44_recovery_r018.operations',
    revision_selection='r018 active: explicit May02 B3 A2 S15 same-budget checkpoint continuation; r017 sealed sources unchanged.',
    pending_windows_task=None,pending_regressions=None,active_deployment_receipt_file=str(ops.OPS/'R018_CHECKPOINT_RESUME_DEPLOYED.json'),
    last_observed_case_stage='May02/B3/attempt002 A2 checkpoint S15 continuation',
    next='Complete resumed May02 B3 A2, then M2 and independent Actual/Fresh; preserve all original constraints and budgets.')
atomic(ops.OPS/'CURRENT_HANDOFF.json',handoff)
print(dict(PASS=True,revision='r018',worker=worker['pid'],stage='A2',start_solve=15,
    inherited_Native_seconds=receipt['inherited_Native_seconds'],total_Native_seconds=ledger['measured_Native_Runtime']))
