"""Bind only the new basis-start computational policy to current evidence."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,sys

REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION

parser=argparse.ArgumentParser()
parser.add_argument('--regression',required=True)
parser.add_argument('--independent',required=True)
parser.add_argument('--owner',required=True)
parser.add_argument('--failure-evidence',required=True)
args=parser.parse_args()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
old_path=ROOT/'autonomous/V30_VERIFIED_REPAIR_VALIDATION.json'
old=read(old_path);manifest=read(ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
execution=sources();source=digest(execution)
assert len(execution)==98 and set(execution)==set(manifest['execution_sources'])
changed=[name for name in execution if execution[name]!=manifest['execution_sources'][name]]
assert changed==['v42_autonomous_b2/f1_basis.py'],changed
declared=dict(manifest['builder_original_sources']);declared.update(execution)
assert len(declared)==1105
original=[]
for name,sha in manifest['builder_original_sources'].items():
    receipt=record(REPO/name);assert receipt['sha256']==sha,name
    original.append(receipt)
assert len(original)==1007
regression=read(args.regression);independent=read(args.independent);owner=read(args.owner)
assert regression['PASS'] is True and regression['repair_source_SHA']==source
assert regression['Native_optimize_calls']==0 and regression['real_Native_model_constructions']==0
assert regression['source_files_unchanged'] is True
assert independent['PASS'] is True and independent['execution_sources']==execution
assert independent['execution_SHA']==source
assert independent['source_file_records']=={name:record(REPO/name) for name in declared}
assert independent['source_start_end_identical'] is True
assert independent['execution_start_end_identical'] is True
assert independent['test_start_end_identical'] is True
assert independent['Native_optimize_calls']==0 and independent['real_Native_model_constructions']==0
assert owner['PASS'] is True
failure=read(args.failure_evidence)
assert failure['PASS'] is True
assert failure['actual_timeout_observed'] is True
assets=[]
for row in old['sparse_required_additional_assets']:
    assert record(row['path'])==row
    relative=Path(row['path']).resolve().relative_to(Path('D:/v42run30')).as_posix()
    receipt=record(REPO/relative)
    assert (receipt['sha256'],receipt['bytes'])==(row['sha256'],row['bytes'])
    assets.append(receipt)
new=copy.deepcopy(old)
# Historical receipt fields remain attached to their original Source30 sources.
new.update(schema='V42_B2_SOURCE31_CURRENT_ORIGINAL_BASIS_NATIVE_PRESOLVE_START_VALIDATION',
    UTC=datetime.now(timezone.utc).isoformat(),PASS=True,
    repair_source_SHA=source,repair_commit_SHA=None,repair_code_root=str(REPO),
    binding_status='PRODUCTION98_VERIFIED_PENDING_IMMUTABLE_FREEZE',
    source_files=[record(REPO/name) for name in execution],original_source_files=original,
    sparse_required_additional_assets=assets,
    carried_Source30_validation=record(old_path),
    integrated_production_regressions=record(args.regression),
    independent_production_review=record(args.independent),
    current_basis_policy_owner_review=record(args.owner),
    actual_Source30_FULL_LP_timeout_evidence=record(args.failure_evidence),
    Method='F1 original1; eligible complete-basis FULL LP0; fallback original1',
    LPWarmStart='Eligible current original complete-basis2 into Native presolve; fallback original2 or cold',
    computational_change='Only eligible current-attempt original F1 basis full-LP native entry uses Method0/LPWarmStart2. Native presolve may crush that original basis internally; original model, fallback, precision and budgets unchanged.',
    original_basis_derived_from_same_attempt_FULL_validated_F1_only=True,
    original_unpresolved_basis_computational_start=False,
    Native_presolved_start_from_current_original_basis=True,
    full_LP_computational_entry_required_Method=0,
    full_LP_computational_entry_required_LPWarmStart=2,
    same_original_basis_and_call_rederived_at_entry=True,
    original_FULL_matrix_bounds_senses_objective_roundtrip_required=True,
    original_fallback_Method1_primal_dual_pair_LPWarmStart2_unchanged=True,
    new_Native_calls_added=0,Native_optimize_calls=0,production_validation_Native_calls=0,
    full_case_validation_Native_models=0,diagnostic_measured_Native_Runtime=0,
    Native_call_scope='Source31 evidence uses denied real model constructors; synthetic budget calls are not Native measurements.',
    actual_Source31_Native_performance_pending=True,actual_Source31_Global_Gap_PASS_pending=True,
    final_gap_PASS_claimed=False,actual_complete_day_or_month_speedup_not_proven=True,
    bottleneck_hypothesis='Original-basis LPWarmStart1 starts the unpresolved FULL problem. Source30 actual300-cap/SolCount0 motivates testing the same basis with LPWarmStart2 Native presolve; performance and complete root cause are not yet proven.',
    carried_evidence='All1007 original science and97of98 Source30 execution sources unchanged. Original exact matrix/domain/objective checks, Native accounting, initial FULL/integer/physical promotion, projection theorem reuse, fresh pricing bounds/full signed checker and RMP Presolve0 retained.',
    new_evidence='Current-source integrated Native-denied suite and independent current-source review/tests enforce the new entry/post parameters while preserving the original reset, source, basis, budget, callback, accounting and fallback guards.',
    healthy_active_workers_not_modified=True,
    fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True)
for key in REQUIRED_VALIDATION:new[key]=True
new['source_script']=record(__file__)
target=ROOT/'autonomous/V31_VALIDATION_BINDING_TEMPLATE.json';assert not target.exists()
target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=source,template=record(target))))
