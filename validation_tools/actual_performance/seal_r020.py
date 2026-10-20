"""Seal the tested future-date A2 rebuild revision; leave r019 untouched."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,verify,atomic,now,digest
from v44_recovery_r019.operations import validate as previous_validate
from v44_recovery_r020 import operations as ops
from v44_recovery_r020.handover import REASON
previous_validate()
assert read(ops.OPS/'STOP_AUTONOMY.json')['reason']==REASON
benchmark=Path('D:/MobileESS_V44/development/r020_class_validation_04/RESULT.json');b=read(benchmark)
assert b['PASS'] and b['Native_optimizer_calls']==0 and b['original_and_changed_matrix_objective_descriptor_proofs_identical']
tests=Path('D:/MobileESS_V44/development/r020_regressions_final.xml');tree=ET.parse(tests).getroot()
assert not tree.findall('.//failure') and not tree.findall('.//error') and len(tree.findall('.//testcase'))==193
guard=read(ops.OPS/'R020_HANDOVER_GUARD.json')
assert guard['effective_from_day']=='2025-05-03' and '2025-05-02' in guard['protected_case_root']
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r020',regressions=193,regression_receipt=record(tests),
    benchmark=record(benchmark),benchmark_scope='THREE_REAL_A2_CLASSES_WITH_ORIGINAL_AND_CHANGED_SUPPORT_AND_CONCRETE_PATH_COLUMN_NOT_FULL_CAMPAIGN',
    real_class_warm_rebuild_speedup=b['warm_speedup'],real_class_changed_rebuild_speedup=b['changed_class_speedup'],
    effective_from_day='2025-05-03',improved_arms=['B0','B1','B3'],B1_A2_covered=True,B3_A2_covered=True,
    both_A2_paths_routing_regression_PASS=True,protected_case=guard['protected_case_root'],
    protected_worker_interrupted=False,source_19_unchanged=True,source_19_permit=record(ops.OPS/'RECOVERY_R019_EXECUTION_PERMIT.json'),
    changes=['Full-input-byte guarded native class-block reuse within one A stage',
             'Reuse successful exact projection proof only for complete identical content hashes; object alias layout is irrelevant',
             'Single-pass class-column and descriptor indexes preserve original ordering',
             'Apply all selected graph changes in original order then construct identical full pool ledger once',
             'Freeze initial reference artificial weights/signs throughout fresh Phase I using all original inclusion guards'],
    independent_full_point_replays_skipped=0,Native_optimizer_calls_added=0,
    constraints_or_tolerances_relaxed=False,Native_budgets_changed=False,
    inherited_Actual_Fresh_improvements_preserved=True,sources=ops.sources())
path=ops.OPS/'R020_CHANGE_AND_VALIDATION.json';assert not path.exists();atomic(path,report)
ops.make_permit()
snapshot=ops.OPS/'source_snapshots/r020';snapshot.mkdir(exist_ok=False)
for source in Path('v44_recovery_r020').glob('*.py'):(snapshot/source.name).write_bytes(source.read_bytes())
atomic(snapshot/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(path)))
atomic(ops.OPS/'R020_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT),validation=record(path)))
ops.validate();print(dict(PASS=True,regressions=193,B1_A2=True,B3_A2=True,effective_from_day='2025-05-03',warm_speedup=b['warm_speedup'],changed_speedup=b['changed_class_speedup']))
