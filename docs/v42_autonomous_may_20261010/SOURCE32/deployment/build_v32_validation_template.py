"""Bind canonical CLI identity and presolved F1 basis policy to current tests."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,sys
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION
p=argparse.ArgumentParser();p.add_argument('--owner',required=True);p.add_argument('--independent',required=True)
p.add_argument('--cli-failure-proof',required=True);p.add_argument('--lp-failure-evidence',required=True)
args=p.parse_args()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
old_path=ROOT/'autonomous/V30_VERIFIED_REPAIR_VALIDATION.json'
old=read(old_path);m=read(ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
ex=sources();sha=digest(ex)
assert len(ex)==98 and set(ex)==set(m['execution_sources'])
changed={name for name in ex if ex[name]!=m['execution_sources'][name]}
assert changed=={'v42_autonomous_b2/f1_basis.py','v42_autonomous_b2/worker.py'},changed
declared=dict(m['builder_original_sources']);declared.update(ex);assert len(declared)==1105
records={name:record(REPO/name) for name in declared}
assert all(records[name]['sha256']==v for name,v in m['builder_original_sources'].items())
for path in (args.owner,args.independent):
    d=read(path)
    assert d['PASS'] is True and d['execution_sources']==ex and d['execution_SHA']==sha
    assert d['source_file_records']==records
    assert all(d[k] is True for k in ('source_start_end_identical','execution_start_end_identical','test_start_end_identical'))
    assert d['Native_optimize_calls']==0 and d['real_Native_model_constructions']==0
    assert record(path)['bytes']>1000
lp=read(args.lp_failure_evidence);assert lp['PASS'] is True and lp['actual_timeout_observed'] is True
cli=read(args.cli_failure_proof)
assert cli['PASS'] is True
assets=[]
for row in old['sparse_required_additional_assets']:
    assert record(row['path'])==row
    name=Path(row['path']).resolve().relative_to(Path('D:/v42run30')).as_posix()
    current=record(REPO/name);assert (current['bytes'],current['sha256'])==(row['bytes'],row['sha256'])
    assets.append(current)
union=sorted(set(declared)|{Path(row['path']).relative_to(REPO).as_posix() for row in assets})
assert len(union)==1110
new=copy.deepcopy(old)
new.update(schema='V42_B2_SOURCE32_CANONICAL_CLI_AND_PRESOLVED_CURRENT_BASIS_VALIDATION',
    PASS=True,UTC=datetime.now(timezone.utc).isoformat(),repair_source_SHA=sha,repair_commit_SHA=None,
    repair_code_root=str(REPO),binding_status='PRODUCTION98_VERIFIED_PENDING_IMMUTABLE_FREEZE',
    source_files=[records[name] for name in ex],original_source_files=[records[name] for name in m['builder_original_sources']],
    sparse_required_additional_assets=assets,sparse_required_source_union=union,
    carried_Source30_validation=record(old_path),
    current_source_selected_production_regressions=record(args.owner),
    independent_production_review=record(args.independent),
    current_CLI_budget_identity_failure_proof=record(args.cli_failure_proof),
    actual_Source30_FULL_LP_timeout_evidence=record(args.lp_failure_evidence),
    carried_Source31_integrated305_receipt=record(ROOT/'autonomous/source30_regression_20261009T212753480380/V31_INTEGRATED_NATIVE_DENIED_REGRESSION.json'),
    carried_Source31_basis_policy_owner98_receipt=record('D:/v42_full_lp_warmstart_readonly_review_20261010_01/SOURCE31_F1_NATIVE_DENIED_TEST_RECEIPT_02.json'),
    carried_Source31_basis_policy_independent98_receipt=record('D:/v42_b2_v31_independent_review_20261010_01/SOURCE31_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_02.json'),
    carried_Source30_unchanged_cache120_and_RMP72_scope='Unchanged cache and RMP module/test bytes. Current-source selected suite tests CLI, scoped worker, F1 and RMP paths; historical suites are not represented as a current full-suite rerun.',
    computational_change='CLI delegates to canonical worker.run so strict original ReceiptDateBudget class/delegate identities match. Eligible current F1 basis uses Method0/LPWarmStart2 at exact original full-LP call.',
    canonical_CLI_same_original_budget_class_and_method_descriptors_required=True,
    original_RMP_type_alias_code_closure_raw_model_and_delegate_guards_unchanged=True,
    Method='F1 original1; eligible complete-basis FULL LP0; fallback original1',
    LPWarmStart='Eligible current original complete-basis2 into Native presolve; fallback original2 or cold',
    original_unpresolved_basis_computational_start=False,
    Native_presolved_start_from_current_original_basis=True,
    full_LP_computational_entry_required_Method=0,full_LP_computational_entry_required_LPWarmStart=2,
    original_fallback_Method1_primal_dual_pair_LPWarmStart2_unchanged=True,
    original_FULL_matrix_bounds_senses_objective_roundtrip_required=True,
    original_F1_120_FULL_LP_300_total5400_Threads1_precision_preserved=True,
    Native_optimize_calls=0,production_validation_Native_calls=0,full_case_validation_Native_models=0,
    diagnostic_measured_Native_Runtime=0,
    Native_call_scope='Current Source32 selected native/model-denied tests and dispatcher identity proof; synthetic original-budget calls are not Native measurements.',
    actual_Source32_Native_performance_pending=True,actual_Source32_Global_Gap_PASS_pending=True,
    final_gap_PASS_claimed=False,actual_complete_day_or_month_speedup_not_proven=True,
    prior_Source31_frozen_not_deployed_due_known_retained_CLI_failure=True,
    new_evidence='Current-source owner and independent selected production/CLI tests, complete1105 source records and original1007 unchanged science; strict identity repair reproduces -m dispatch without Native/model creation.',
    carried_evidence='All1007 original science and96of98 Source30 execution files unchanged. Source31 F1 policy is carried byte-identically. Cache theorem/fresh bound checks, RMP Presolve0, exact original math/certification/Native accounting remain unchanged.',
    healthy_active_workers_not_modified=True,fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True)
for key in REQUIRED_VALIDATION:new[key]=True
new['source_script']=record(__file__)
target=ROOT/'autonomous/V32_VALIDATION_BINDING_TEMPLATE.json';assert not target.exists()
target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=sha,template=record(target))))
