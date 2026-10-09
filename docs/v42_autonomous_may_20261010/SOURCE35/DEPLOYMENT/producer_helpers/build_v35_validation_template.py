"""Bind separate computational F1 prices; retain original certified frontier."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,sys
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION
p=argparse.ArgumentParser();p.add_argument('--owner',required=True);p.add_argument('--independent',required=True)
p.add_argument('--diagnosis-owner',required=True);p.add_argument('--diagnosis-independent',required=True);args=p.parse_args()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
old_path=ROOT/'autonomous/V34_VERIFIED_REPAIR_VALIDATION.json';old=read(old_path)
m=read(ROOT/'B2_V34_ZERO_START_DEPLOYMENT_MANIFEST.json');ex=sources();sha=digest(ex)
assert len(ex)==99 and len(m['execution_sources'])==98
assert set(ex)-set(m['execution_sources'])=={'v42_autonomous_b2/f1_price_seed.py'}
assert not set(m['execution_sources'])-set(ex)
assert {name for name in m['execution_sources'] if ex[name]!=m['execution_sources'][name]}=={'v42_autonomous_b2/worker.py'}
declared=dict(m['builder_original_sources']);declared.update(ex);assert len(declared)==1106
records={name:record(REPO/name) for name in declared}
assert all(records[name]['sha256']==v for name,v in m['builder_original_sources'].items())
for path in (args.owner,args.independent):
    d=read(path)
    assert d['PASS'] is True and d['execution_sources']==ex and d['execution_SHA']==sha
    assert d['source_file_records']==records
    assert all(d[k] is True for k in ('source_start_end_identical','execution_start_end_identical','test_start_end_identical'))
    assert d['Native_optimize_calls']==0 and d['real_Native_model_constructions']==0
    assert record(path)['bytes']>1000
diagnosis_owner=read(args.diagnosis_owner);diagnosis_independent=read(args.diagnosis_independent)
assert record(args.diagnosis_owner)['sha256']=='94dd89f0a9d5d36ebb8fde0d321e3a4e6533f49b9fdbdf4159c77a41040bc1a6'
assert record(args.diagnosis_independent)['sha256']=='fa6319097aa59b8a7f4eae89dfc7ec307d510900f4ceaba209a9a0c5bac2ec7b'
assert diagnosis_owner['PASS'] is True and diagnosis_independent['PASS'] is True
assets=[]
for row in old['sparse_required_additional_assets']:
    assert record(row['path'])==row
    name=Path(row['path']).resolve().relative_to(Path('D:/v42run34')).as_posix()
    current=record(REPO/name);assert (current['bytes'],current['sha256'])==(row['bytes'],row['sha256'])
    assets.append(current)
union=sorted(set(declared)|{Path(row['path']).relative_to(REPO).as_posix() for row in assets});assert len(union)==1111
new=copy.deepcopy(old)
new.update(schema='V42_B2_SOURCE35_CURRENT_F1_COMPUTATIONAL_PRICE_SEPARATE_FROM_CERTIFIED_LB_VALIDATION',
    PASS=True,UTC=datetime.now(timezone.utc).isoformat(),repair_source_SHA=sha,repair_commit_SHA=None,
    repair_code_root=str(REPO),binding_status='PRODUCTION99_VERIFIED_PENDING_IMMUTABLE_FREEZE',
    source_files=[records[name] for name in ex],original_source_files=[records[name] for name in m['builder_original_sources']],
    sparse_required_additional_assets=assets,sparse_required_source_union=union,
    carried_Source34_validation=record(old_path),
    current_source_selected_production_regressions=record(args.owner),independent_production_review=record(args.independent),
    actual_Source32_current_F1_nonzero_coupling_and_zero_price_diagnosis=record(args.diagnosis_owner),
    independent_actual_Source32_original_repair_and_fresh_full_checker=record(args.diagnosis_independent),
    computational_change='Retain Source34 full-LP and RMP computational policies byte-identical. Only the original scheduled L1/L4 lp_round computational price input may use same-current-live-F1 original repaired and completely independently checked dual when the passed certified dual is empty and current certified frontier is zero. The driver certified dual, original frontier and final exact bracket are untouched; only original lp_round may return a freshly certified adopted dual.',
    existing_L1_L4_calls_only_no_added_Native_calls=True,
    current_live_F1_issuer_token_full_replay_source_case_known_Native_required=True,
    no_saved_array_or_previous_attempt_admission_required=True,
    original_repair_and_complete_full_checker_and_stored_candidate_exact_matching_required=True,
    certified_zero_full_LP_tie_and_original_missing_or_ineligible_candidate_cold_path_preserved=True,
    weaker_computational_seed_never_published_as_certified_LB=True,
    L2_L3_RMP_and_mixed_price_inputs_unmodified=True,
    original_lp_round_make_prices_local_bounds_full_signed_checker_frontier_and_exact_return_required=True,
    lazy_attempt_local_factory_and_original_alias_restore_on_all_exits_required=True,
    original_FULL_LP_RMP_pricing_total_Native_budgets_precision_constraints_unchanged=True,
    new_execution_file_count=99,new_unique_source_asset_count=1111,
    Native_optimize_calls=0,production_validation_Native_calls=0,full_case_validation_Native_models=0,
    diagnostic_measured_Native_Runtime=0,
    Native_call_scope='Current Source35 owner and independent native/model-denied tests; actual Source32 diagnosis is historical. Synthetic fixture Runtime is not a Native measurement.',
    actual_Source35_Native_performance_pending=True,actual_Source35_Global_Gap_PASS_pending=True,
    final_gap_PASS_claimed=False,actual_complete_day_or_month_speedup_not_proven=True,
    new_evidence='Current-source selected regressions, complete1106 records and all1007 original science unchanged. Actual Source32 producer matched existing certificates and independent diagnosis freshly reran original repair/envelope/full checker without Native/model creation.',
    carried_evidence='Source34 owner/independent244, immutable1110 freeze and actual27 canonical admissions/nine safe queues remain historical. Source34 full-LP/RMP modules and other97 prior execution modules are unchanged. No historical suite is labeled a current full-suite rerun.',
    healthy_active_workers_not_modified=True,fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True)
for key in REQUIRED_VALIDATION:new[key]=True
new['source_script']=record(__file__)
target=ROOT/'autonomous/V35_VALIDATION_BINDING_TEMPLATE.json';assert not target.exists()
target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=sha,template=record(target))))
