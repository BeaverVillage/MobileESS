"""Bind the early zero-contract admission repair to unchanged Source36 science."""
from pathlib import Path
import argparse,json,sys,datetime
REPO=Path(r'D:\MobileESS_v42_autonomous');ROOT=Path(r'D:\v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION
parser=argparse.ArgumentParser();parser.add_argument('--independent',required=True);args=parser.parse_args()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
old_path=ROOT/'autonomous/V36_VERIFIED_REPAIR_VALIDATION_02.json';old=read(old_path)
m=read(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json');ex=sources();source=digest(ex)
assert old['PASS'] is True and len(ex)==99 and len(m['builder_original_sources'])==1007
assert set(ex)==set(m['execution_sources'])
assert {n for n in ex if ex[n]!=m['execution_sources'][n]}=={'v42_autonomous_b2/worker.py'}
records={n:record(REPO/n) for n in {**m['builder_original_sources'],**ex}}
assert len(records)==1106
assert all(records[n]['sha256']==h for n,h in m['builder_original_sources'].items())
owner_path=Path(r'D:\v42_source37_owner_review_20261010_02\SOURCE37_OWNER_SELECTED_NATIVE_DENIED_RECEIPT.json')
owner=read(owner_path);independent=read(args.independent)
assert record(owner_path)['sha256']=='27ce77e9469655163ea874f5d9e135e94404891f2306857a222690130c5617e3'
assert owner['PASS'] is True and owner['tests']==374 and owner['failures']==owner['errors']==0
assert owner['model_attempts']==owner['native_attempts']==[]
assert independent['PASS'] is True
assert independent['cases_collected']==independent['tests_passed']==374 and independent['exit_code']==0
assert independent['failures']==independent['skipped']==independent['modelattempts']==independent['nativeattempts']==[]
for evidence in (owner,independent):
 assert evidence['execution_sources']==ex and evidence['execution_SHA']==source and evidence['source_file_records']==records
 assert evidence['Native_optimize_calls']==evidence['real_Native_model_constructions']==0
 assert all(evidence[key] is True for key in ('source_start_end_identical','execution_start_end_identical','test_start_end_identical'))
assets=[]
for item in old['sparse_required_additional_assets']:
 assert record(item['path'])==item
 relative=Path(item['path']).relative_to(Path(r'D:\v42run36'))
 current=record(REPO/relative);assert (current['bytes'],current['sha256'])==(item['bytes'],item['sha256'])
 assets.append(current)
union=sorted(set(records)|{Path(item['path']).relative_to(REPO).as_posix() for item in assets});assert len(union)==1111
new=dict(schema='V42_B2_SOURCE37_EARLY_ZERO_CONTRACT_VALIDATION',PASS=True,UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 repair_source_SHA=source,repair_commit_SHA=None,repair_code_root=str(REPO),binding_status='PRODUCTION99_VERIFIED_PENDING_IMMUTABLE_FREEZE',
 source_files=[records[n] for n in ex],original_source_files=[records[n] for n in m['builder_original_sources']],
 sparse_required_additional_assets=assets,sparse_required_source_union=union,carried_source36_validation=record(old_path),
 current_source_selected_production_regressions=record(owner_path),independent_production_review=record(args.independent),
 original1007_and_other98_execution_modules_byte_identical_Source36=True,
 early_original_zero_authorization_after_complete_source_request_seals_before_model_or_Native=True,
 original_zero_authorization_code_byte_identical=True,science_domain_physics_integer_objective_precision_and_signed_certification_unchanged=True,
 original_FULL_LP_RMP_pricing_and_total5400_Native_budgets_unchanged=True,P2_calls=0,Threads=1,
 Native_optimize_calls=0,production_validation_Native_calls=0,full_case_validation_Native_models=0,diagnostic_measured_Native_Runtime=0,
 actual_Source37_Native_performance_pending=True,actual_Source37_Global_Gap_PASS_pending=True,final_gap_PASS_claimed=False,
 actual_complete_day_or_month_speedup_not_proven=True,new_execution_file_count=99,new_unique_source_asset_count=1111,
 healthy_active_workers_not_modified=True,fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True,
 scientific_limitations='Source37 corrects early admission only. Source36 current valid first-three requests are not restarted; actual RMP dual/nonunit convergence remains separate and no improvement or final PASS is claimed.',
 Native_call_scope='Owner and independent374 selected tests deny retained Model construction and optimize, attempts[]. Actual preflight/cache/RMP/original price factory admission remains required for each of three new slot requests.',
 source_script=record(__file__))
for key in REQUIRED_VALIDATION:assert old[key] is True;new[key]=True
p=ROOT/'autonomous/V37_VALIDATION_BINDING_TEMPLATE.json';assert not p.exists();p.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=source,template=record(p))))
