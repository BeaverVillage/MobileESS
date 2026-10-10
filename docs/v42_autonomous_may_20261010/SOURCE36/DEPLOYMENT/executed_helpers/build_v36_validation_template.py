"""Bind a current-start RMP computational choice; original science unchanged."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,sys
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION
p=argparse.ArgumentParser();p.add_argument('--owner',required=True);p.add_argument('--independent',required=True)
args=p.parse_args()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

old_path=ROOT/'autonomous/V35_VERIFIED_REPAIR_VALIDATION.json';old=read(old_path)
assert old['PASS'] is True
m_path=ROOT/'B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json';m=read(m_path)
ex=sources();sha=digest(ex)
assert len(ex)==99 and len(m['execution_sources'])==99
assert set(ex)==set(m['execution_sources'])
assert {name for name in ex if ex[name]!=m['execution_sources'][name]}=={'v42_autonomous_b2/rmp_presolve.py'}
assert sha=='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
declared=dict(m['builder_original_sources']);declared.update(ex)
assert len(m['builder_original_sources'])==1007 and len(declared)==1106
records={name:record(REPO/name) for name in declared}
assert all(records[name]['sha256']==value for name,value in m['builder_original_sources'].items())
for path,expected in ((args.owner,'3ff0607e176918b08d63aeeced4667e687609dc72e33180321a82ba8924557ac'),
                      (args.independent,'c74bc9a9c721106e3bba4ee8094a2cad3a7ad46b61702aaf0af07f61f4187605')):
    d=read(path)
    assert record(path)['sha256']==expected
    assert d['PASS'] is True
    if path==args.owner:
        assert d['status']=='PASS' and d['tests']==369 and d['failures']==0 and d['errors']==0
        assert d['model_attempts']==[] and d['native_attempts']==[]
        tests=d['test_file_records']
    else:
        assert d['cases_collected']==369 and d['tests_passed']==369 and d['exit_code']==0
        assert d['failures']==[] and d['skipped']==[]
        assert d['modelattempts']==[] and d['nativeattempts']==[]
        assert d['test_file_records_start']==d['test_file_records_end']
        tests=d['test_file_records_start']
    assert d['execution_sources']==ex and d['execution_SHA']==sha and d['source_file_records']==records
    assert all(d[key] is True for key in ('source_start_end_identical','execution_start_end_identical','test_start_end_identical'))
    assert d['Native_optimize_calls']==0 and d['real_Native_model_constructions']==0
    assert all(record(REPO/name)==row for name,row in tests.items())
assets=[]
for row in old['sparse_required_additional_assets']:
    assert record(row['path'])==row
    name=Path(row['path']).resolve().relative_to(Path('D:/v42run35')).as_posix()
    current=record(REPO/name)
    assert (current['bytes'],current['sha256'])==(row['bytes'],row['sha256'])
    assets.append(current)
union=sorted(set(declared)|{Path(row['path']).relative_to(REPO).as_posix() for row in assets})
assert len(union)==1111
new=copy.deepcopy(old)
for key in ('L2_L3_RMP_and_mixed_price_inputs_unmodified',
            'actual_Source35_Native_performance_pending','actual_Source35_Global_Gap_PASS_pending'):
    new.pop(key,None)
new.update(schema='V42_B2_SOURCE36_CURRENT_RMP_PRIMAL_COMPUTATIONAL_SELECTION_VALIDATION',
    PASS=True,UTC=datetime.now(timezone.utc).isoformat(),repair_source_SHA=sha,repair_commit_SHA=None,
    repair_code_root=str(REPO),binding_status='PRODUCTION99_VERIFIED_PENDING_IMMUTABLE_FREEZE',
    source_files=[records[name] for name in ex],original_source_files=[records[name] for name in m['builder_original_sources']],
    sparse_required_additional_assets=assets,sparse_required_source_union=union,
    carried_Source35_validation=record(old_path),carried_Source35_manifest=record(m_path),
    current_source_selected_production_regressions=record(args.owner),independent_production_review=record(args.independent),
    computational_change='Original Method1 remains mandatory at original budget admission. At the sole original30-second RMP Native boundary, exact complete current P/D installation plus sealed original and Native-scaled row and bound violations within literal original1e-9 may select Method0. All cold, ineligible or finite nonfeasible starts retain Method1. Presolve0, warm2 when installed, Threads1, Crossover, all original precision and matrix/domain/objective/row/Pi transport and original independent checker remain unchanged.',
    eligible_current_complete_start_original_and_Native_rows_and_bounds_literal_1e_9_required=True,
    Method0_only_after_original_Method1_budget_entry_and_complete_P_D_readback=True,
    cold_ineligible_and_finite_nonfeasible_start_original_Method1_preserved=True,
    exact_selected_Method_checked_before_and_after_single_Native_delegate=True,
    Entry_code_descriptor_instance_and_source_math_start_post_writer_guards_required=True,
    no_post_Native_start_setters_updates_or_parameter_repairs_required=True,
    original_progress_guard_failure_inflight_unknown_preserved=True,
    existing_RMP_call_only_no_added_Native_calls=True,
    Source35_F1_price_seed_full_LP_worker_and_other98_execution_modules_byte_identical=True,
    original_FULL_LP_RMP_pricing_total_Native_budgets_precision_constraints_unchanged=True,
    new_execution_file_count=99,new_unique_source_asset_count=1111,
    Native_optimize_calls=0,production_validation_Native_calls=0,full_case_validation_Native_models=0,
    diagnostic_measured_Native_Runtime=0,
    Native_call_scope='Source36 owner and independent369 tests denied retained real model construction and optimize. Synthetic fixture Runtime is not a Native measurement. Actual Source35 observations are historical.',
    actual_Source36_Native_performance_pending=True,actual_Source36_Global_Gap_PASS_pending=True,
    final_gap_PASS_claimed=False,actual_complete_day_or_month_speedup_not_proven=True,
    new_evidence='Current selected369 regressions including RMP136, complete1106 records start=end and original1007 plus other98 execution bytes identical to Source35. No real Native/model attempts occurred.',
    carried_evidence='Verified immutable Source35 price/full-LP/worker and original scientific source authority are retained. Historical Source35 actual positive independently certified L1 lower bounds and Method1 RMP timeouts do not prove Source36 performance or final scientific PASS.',
    healthy_active_workers_not_modified=True,fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True)
for key in REQUIRED_VALIDATION:new[key]=True
new['source_script']=record(__file__)
target=ROOT/'autonomous/V36_VALIDATION_BINDING_TEMPLATE.json'
assert not target.exists()
target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=sha,template=record(target))))
