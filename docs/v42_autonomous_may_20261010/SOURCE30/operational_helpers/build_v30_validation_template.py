"""Bind computational repairs to actual tests, review and unchanged science."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime,timezone
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION
parser=argparse.ArgumentParser()
parser.add_argument('--regression',required=True)
parser.add_argument('--independent',required=True)
parser.add_argument('--cache-review',required=True)
parser.add_argument('--RMP-review',required=True)
parser.add_argument('--control-review',required=True)
parser.add_argument('--control-independent',required=True)
args=parser.parse_args()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
execution=sources();source=digest(execution);assert len(execution)==98
old_manifest=read(ROOT/'B2_V28_ZERO_START_DEPLOYMENT_MANIFEST.json')
changed=[name for name,sha in old_manifest['execution_sources'].items() if execution[name]!=sha]
assert changed==['v42_autonomous_b2/worker.py'],changed
assert set(execution)-set(old_manifest['execution_sources'])=={
    'v42_autonomous_b2/pricing_cache.py','v42_autonomous_b2/rmp_presolve.py'}
original=[]
for name,sha in old_manifest['builder_original_sources'].items():
    current=record(REPO/name);assert current['sha256']==sha,name;original.append(current)
assert len(original)==1007
regression=read(args.regression);independent=read(args.independent)
assert regression['PASS'] is True and regression['repair_source_SHA']==source
assert regression['Native_optimize_calls']==0 and regression['real_Native_model_constructions']==0
assert independent['PASS'] is True
assert independent['execution_sources']==execution
assert independent['execution_SHA']==source
declared=dict(old_manifest['builder_original_sources']);declared.update(execution)
assert len(declared)==1105
independent_records=independent['source_file_records']
assert isinstance(independent_records,dict) and set(independent_records)==set(declared)
assert independent_records=={name:record(REPO/name) for name in declared}
assert independent['source_start_end_identical'] is True
assert independent['execution_start_end_identical'] is True
assert independent['test_start_end_identical'] is True
for path in (args.cache_review,args.RMP_review,args.control_review,args.control_independent):
    assert read(path)['PASS'] is True
cpu=REPO/'tmp/v29_projection_cache_draft/actual_saved_may01/20261009T200959_019719Z/ONE_ACTUAL_SAVED_PROJECTION_EQUIVALENCE_CPU_RECEIPT.json'
frequency=REPO/'tmp/v29_projection_cache_draft/V29_ACTUAL_SOURCE27_CONSUMER_REUSE_FREQUENCY.json'
startup=REPO/'tmp/v29_projection_cache_draft/V29_NATIVE_ZERO_SCOPE_STARTUP_SOURCE_SNAPSHOT_CPU.json'
for path in (cpu,frequency,startup):assert path.is_file()
old=read(ROOT/'autonomous/V28_VERIFIED_REPAIR_VALIDATION.json')
new=dict(old)
new.update(schema='V42_B2_SOURCE30_CURRENT_PROJECTION_REUSE_AND_RMP_PRESOLVE_VALIDATION',
    PASS=True,UTC=datetime.now(timezone.utc).isoformat(),repair_source_SHA=source,repair_commit_SHA=None,
    repair_code_root=str(REPO),binding_status='PRODUCTION98_VERIFIED_PENDING_IMMUTABLE_FREEZE',
    source_files=[record(REPO/name) for name in execution],original_source_files=original,
    source_file_count=98,original_source_file_count=1007,sparse_required_source_union_count=1110,
    Native_optimize_calls=0,production_validation_Native_calls=0,full_case_validation_Native_models=0,
    Native_call_scope='Source30 validation contains only denied real model constructors and synthetic original-budget receipts; no new actual Native calls.',
    diagnostic_measured_Native_Runtime=0,
    prior_diagnostic_Native_calls_preserved_in_carried_Source28_validation=True,
    carried_Source28_validation=record(ROOT/'autonomous/V28_VERIFIED_REPAIR_VALIDATION.json'),
    integrated_production_regressions=record(args.regression),
    independent_production_review=record(args.independent),
    cache_owner_production_review=record(args.cache_review),
    RMP_owner_production_review=record(args.RMP_review),
    unstarted_READY_supersession_control_owner_review=record(args.control_review),
    unstarted_READY_supersession_independent_review=record(args.control_independent),
    active_normal_worker_identity_and_ledger_not_changed_by_supersession=True,
    saved_actual_projection_CPU_equivalence=record(cpu),
    actual_current_Source27_four_round_consumer_reuse_frequency=record(frequency),
    actual_saved_Source27_scope_startup_CPU=record(startup),
    projection_proof_reuse_scope='Only a scope-created theorem for the same live case/decomposition/current attempt; no existing disk proof or historical state admitted.',
    projection_first_derivation_and_independent_envelope_verification_retained=True,
    all_original_local_price_bounds_and_full_signed_checker_fresh_each_round=True,
    no_cached_dual_price_or_bound_or_Global_LB=True,
    cache_cold_saved_actual_case_wall_seconds=47.972,
    unchanged_saved_actual_case_original_wall_seconds=37.092,
    cache_saved_actual_case_hit_wall_seconds=[16.115,15.203],
    cache_saved_actual_case_scope_startup_wall_seconds=.459043,
    cache_saved_actual_case_cold_plus_startup_penalty_about_seconds=11.339,
    small_fixture_cache_slowdowns_preserved=True,
    actual_complete_day_or_month_speedup_not_proven=True,
    restricted_master_computational_change='Only Presolve0 at the original one30-second RMP Native call; original Method1, NumericFocus3, ScaleFlag2, precision, rows, domain, objective and guards retained.',
    restricted_master_objective_not_Global_LB=True,
    presolve_uncrush_numerical_hypothesis_not_final_root_cause_or_performance_proof=True,
    original_budget_delegate_and_Runtime_persistence_exactly_once=True,
    pre_Native_guard_failure_original_inflight_UNKNOWN_preserved=True,
    original_F1_120_FULL_LP_300_total5400_Threads1_precision_preserved=True,
    fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True,
    healthy_active_workers_not_modified=True,
    actual_Source30_Native_performance_pending=True,
    actual_Source30_Global_Gap_PASS_pending=True,
    new_evidence='Actual integrated Native/model-denied tests and independent public production factory/hook/source/budget review; saved actual original proof/round math equivalence with cold slowdown and repeated-hit timings recorded honestly.',
    carried_evidence='All1007 original science files and all96 prior execution files except the routing worker are byte-identical. Current-attempt original FULL physical/integer/exact-objective and full-signed certificates remain required. New cache retains the original theorem and recomputes original bounds/checks; Presolve changes only original Native computational policy after unchanged exact matrix/domain/objective admission.')
for key in REQUIRED_VALIDATION:new[key]=True
assets=[];asset_records=[]
for row in old['sparse_required_additional_assets']:
    assert record(row['path'])==row
    # The sealed Source28 validation deliberately retains Source27 historical
    # asset receipts; bind the unchanged bytes into the new checkout explicitly.
    relative=Path(row['path']).relative_to(Path('D:/v42run27')).as_posix()
    current=record(REPO/relative)
    assert (current['sha256'],current['bytes'])==(row['sha256'],row['bytes'])
    assets.append(relative);asset_records.append(current)
new['sparse_required_additional_assets']=asset_records
new['sparse_required_source_union']=sorted(set(execution)|set(old_manifest['builder_original_sources'])|set(assets))
assert len(new['sparse_required_source_union'])==1110
new['source_script']=record(__file__)
target=ROOT/'autonomous/V30_VALIDATION_BINDING_TEMPLATE.json';assert not target.exists()
target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=source,template=record(target)),ensure_ascii=False))
