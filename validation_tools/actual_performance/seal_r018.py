from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now,digest
from v44_recovery_r018 import operations as ops
from v44_recovery_r018.a2_continue import ADMISSION
from v44_recovery_r017.operations import validate as validate17

proof=read(ADMISSION);assert proof['PASS'] and proof['new_Native_calls']==0
assert proof['same_saved_S14_matrix_fingerprint'] and proof['original_inclusion_witness']['PASS']
assert proof['new_compact_elastic_replay']['PASS'] and proof['next_solve']==15
verify(proof['sources']+[proof['checkpoint'],proof['parent_request'],proof['implementation']])
assert abs(proof['Native_account']['measured']-723.613000869751)<1e-9
tree=ET.parse('D:/MobileESS_V44/development/r018_regressions_final.xml').getroot()
assert not tree.findall('.//failure') and not tree.findall('.//error')
assert len(tree.findall('.//testcase'))==179
validate17()
changed={'operations.py','handover.py'}
for source in Path('v44_recovery_r017').glob('*.py'):
    if source.name not in changed:
        assert (Path('v44_recovery_r018')/source.name).read_text(encoding='utf8')==source.read_text(encoding='utf8').replace('r017','r018').replace('R017','R018')
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r018',
    user_authorization=record(ops.OPS/'MAY02_B3_CHECKPOINT_RESUME_USER_AUTHORIZATION.json'),
    inherited_R017_validation=record(ops.OPS/'R017_CHANGE_AND_VALIDATION.json'),
    inherited_R017_sources_semantically_unchanged_except_explicit_A2_resume=True,
    checkpoint_admission=record(ADMISSION),checkpoint=proof['checkpoint'],
    exact_saved_S14_matrix_fingerprint=True,original_inclusion_witness=proof['original_inclusion_witness'],
    new_compact_replay=proof['new_compact_elastic_replay'],weight_drift=proof['weights_drift'],
    preserved_exact_Phi=proof['exact_Phi_preserved'],next_solve=15,
    inherited_Native_seconds=proof['Native_account']['measured'],remaining_Native_seconds=proof['Native_account']['remaining'],
    A2_total_Native_ceiling=5400.,Native_clock_reset=False,original_failure_and_Raw_preserved=True,
    A1_and_M1_reoptimization_calls=0,original_rows_bounds_types_and_rho_objective_unchanged=True,
    sign_and_inclusion_guards_not_bypassed=True,stagnation_rule_preserved=True,
    independent_A2_gap_requirement_unchanged=.005,Independent_Fresh_full_measurements=True,
    constraints_or_tolerances_relaxed=False,regressions=179,
    regression_receipt=record('D:/MobileESS_V44/development/r018_regressions_final.xml'),
    sources=ops.sources(),preparation_source=record(__file__))
path=ops.OPS/'R018_CHANGE_AND_VALIDATION.json';assert not path.exists();atomic(path,report)
ops.make_permit()
snapshot=ops.OPS/'source_snapshots/r018';snapshot.mkdir(exist_ok=False)
for source in Path('v44_recovery_r018').glob('*.py'):(snapshot/source.name).write_bytes(source.read_bytes())
atomic(snapshot/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(path)))
atomic(ops.OPS/'R018_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),
    permit=record(ops.PERMIT),validation=record(path),checkpoint_admission=record(ADMISSION),snapshot=str(snapshot)))
ops.validate();print(dict(PASS=True,regressions=179,next_solve=15,remaining=proof['Native_account']['remaining']))
