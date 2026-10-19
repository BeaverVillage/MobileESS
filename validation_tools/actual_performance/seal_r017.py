"""Seal r017 only after packaged native parity and regression validation."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now,digest
from v44_recovery_r017 import operations as ops
from v44_recovery_r016.operations import validate as validate16
from v44_recovery_r015.operations import validate as validate15

development=Path('D:/MobileESS_V44/development')
evidence=development/'r017_integrated_01/RESULT.json';value=read(evidence)
assert value['PASS'] and value['Native_optimizer_calls']==0 and len(value['checks'])==9
assert value['sources']==ops.sources();verify(value['sources'])
regressions=development/'r017_regressions_final.xml';tree=ET.parse(regressions).getroot()
assert not tree.findall('.//failure') and not tree.findall('.//error')
assert len(tree.findall('.//testcase'))==173
validate15();validate16()
structural=read(development/'ACTUAL_STRUCTURAL_HISTORY_VALIDATION.json');assert structural['PASS']
verify(structural['sources']+structural['evidence'])
for name in ('history.py','immutable.py'):
    assert (Path('v44_recovery_r017')/name).read_bytes()==(Path('v44_actual_prefix')/name).read_bytes()
changed={'current_ac_performance.py','operations.py','handover.py'}
for source in Path('v44_recovery_r016').glob('*.py'):
    if source.name not in changed:
        expected=source.read_text(encoding='utf8').replace('r016','r017').replace('R016','R017')
        assert expected==(Path('v44_recovery_r017')/source.name).read_text(encoding='utf8'),source.name
guard=read(ops.OPS/'R017_HANDOVER_GUARD.json')
verify([guard['authorization'],guard['protected_request'],guard['previous_permit']])
assert not guard['current_case_interrupt_allowed'] and not guard['current_case_restart_allowed']
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r017',
    inherited_revision_validation=record(ops.OPS/'R016_CHANGE_AND_VALIDATION.json'),
    improved_arms=['B0','B1','B3'],structural_validation=record(development/'ACTUAL_STRUCTURAL_HISTORY_VALIDATION.json'),
    packaged_native_validation=record(evidence),regression_receipt=record(regressions),regressions=173,
    packaged_native_exact_pairs=9,earlier_structural_exact_pairs=23,
    packaged_native_checks=value['checks'],measurements=value['measurements'],
    native_solves_removed=0,current_candidate_checks_skipped=0,Independent_Fresh_full_measurements=True,
    hidden_native_snapshot_restored=False,Raw_JSON_bytes_unchanged=True,
    historical_guard_cadence='First and final full live controls/ratings and unchanged outer inventories; intermediate control audit certificates require exact prefix plus native state/voltages/counters. Repeated static ratings audits consolidated within historical slots only.',
    sources=ops.sources(),inherited_science_sources_unchanged=True,Native_budgets_changed=False,
    constraints_objectives_tolerances_changed=False,
    user_authorization=guard['authorization'],handover_guard=record(ops.OPS/'R017_HANDOVER_GUARD.json'),
    production_transition='After current May01 B3 attempt003 entire Actual and independent Fresh plus natural worker/coordinator exits. Replaces pending r016, no current restart.',
    timing_limitations='Diagnostic candidate timings after warmup, not campaign completion time; initial certificate construction can add overhead.',
    preparation_source=record(__file__))
target=ops.OPS/'R017_CHANGE_AND_VALIDATION.json';assert not target.exists();atomic(target,report)
ops.make_permit()
snapshot=ops.OPS/'source_snapshots/r017';snapshot.mkdir(exist_ok=False)
for source in Path('v44_recovery_r017').glob('*.py'):(snapshot/source.name).write_bytes(source.read_bytes())
atomic(snapshot/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(target)))
atomic(ops.OPS/'R017_SEALED.json',dict(UTC=now(),PASS=True,permit=record(ops.PERMIT),
    validation=record(target),sources=ops.sources(),source_sha=digest(ops.sources()),snapshot=str(snapshot),
    protected_request=guard['protected_request'],user_authorization=guard['authorization']))
ops.validate()
print(dict(PASS=True,permit=str(ops.PERMIT),regressions=173,real_exact_pairs=32))
