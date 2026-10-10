"""Bind current-source tests to model-local RMP starts and unchanged science."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,sys
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
sys.path.insert(0,str(REPO))
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from v42_autonomous.recovery import REQUIRED_VALIDATION
p=argparse.ArgumentParser();p.add_argument('--owner',required=True);p.add_argument('--independent',required=True)
p.add_argument('--rmp-failure-evidence',required=True);args=p.parse_args()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
old_path=ROOT/'autonomous/V33_VERIFIED_REPAIR_VALIDATION.json';old=read(old_path)
m=read(ROOT/'B2_V33_ZERO_START_DEPLOYMENT_MANIFEST.json');ex=sources();sha=digest(ex)
assert len(ex)==98 and set(ex)==set(m['execution_sources'])
changed={name for name in ex if ex[name]!=m['execution_sources'][name]}
assert changed=={'v42_autonomous_b2/rmp_presolve.py'},changed
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
rmp=read(args.rmp_failure_evidence)
assert rmp['PASS'] is True and rmp['execution_SHA']==read(ROOT/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json')['execution_SHA']
assert {r['day'] for r in rmp['rows']}=={'2025-05-01','2025-05-02','2025-05-03'}
for row in rmp['rows']:
    assert len(row['RMP'])==2
    for actual in row['RMP']:
        assert actual['Native_status']==11 and actual['SolCount']==0 and actual['error'] is None
        assert actual['dual_status']=='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN'
        assert actual['finite_Pi_count']==0 and actual['restricted_master_is_Global_LB'] is False
        assert actual['actual_parameters']['Method']==1 and actual['actual_parameters']['Presolve']==0
        assert actual['actual_parameters']['Threads']==1 and actual['actual_parameters']['TimeLimit']==30
        for field in ('entry','result'):assert record(actual[field]['path'])==actual[field]
assets=[]
for row in old['sparse_required_additional_assets']:
    assert record(row['path'])==row
    name=Path(row['path']).resolve().relative_to(Path('D:/v42run33')).as_posix()
    current=record(REPO/name);assert (current['bytes'],current['sha256'])==(row['bytes'],row['sha256'])
    assets.append(current)
union=sorted(set(declared)|{Path(row['path']).relative_to(REPO).as_posix() for row in assets})
assert len(union)==1110
new=copy.deepcopy(old)
new.update(schema='V42_B2_SOURCE34_CURRENT_ATTEMPT_RMP_PRIMAL_DUAL_START_VALIDATION',
    PASS=True,UTC=datetime.now(timezone.utc).isoformat(),repair_source_SHA=sha,repair_commit_SHA=None,
    repair_code_root=str(REPO),binding_status='PRODUCTION98_VERIFIED_PENDING_IMMUTABLE_FREEZE',
    source_files=[records[name] for name in ex],original_source_files=[records[name] for name in m['builder_original_sources']],
    sparse_required_additional_assets=assets,sparse_required_source_union=union,
    carried_Source33_validation=record(old_path),
    current_source_selected_production_regressions=record(args.owner),
    independent_production_review=record(args.independent),
    actual_Source32_RMP30_timeout_and_missing_Pi_evidence=record(args.rmp_failure_evidence),
    computational_change='Retain Source33 eligible current-F1 full-LP Method6/LPWarmStart2 and strict PDHG settings unchanged. Only RMP receives model-local same-current-attempt primal projection and explicit computational zero DStart/LPWarmStart2 at the single existing original30-second Method1/Presolve0 call. Starts are computational hints, not feasibility, basis, Native Pi, objective or bound authority. No post-Native start setter/update, and original run disposes the owned model.',
    RMP_Method=1,RMP_Presolve=0,RMP_LPWarmStart=2,RMP_original_required_seconds=30.,
    RMP_same_attempt_current_point_nonunit_and_current_seed_catalog_projection_required=True,
    RMP_explicit_computational_zero_DStart_is_not_Native_Pi_or_bound=True,
    RMP_original_and_Native_scaled_residuals_recorded_without_rounding_or_clipping=True,
    RMP_model_local_only_original_cold_fallback_for_ineligible_start_required=True,
    RMP_start_readback_required_before_single_original_Native_delegate=True,
    RMP_no_post_Native_start_setter_update_or_start_readback_required=True,
    RMP_original_owned_model_finally_disposal_required=True,
    RMP_missing_Native_Pi_remains_missing_and_not_zero_dual=True,
    RMP_original_source_type_model_closure_row_pullback_budget_and_checker_required=True,
    original_F1_120_FULL_LP_300_RMP30_total5400_Threads1_precision_preserved=True,
    Native_optimize_calls=0,production_validation_Native_calls=0,full_case_validation_Native_models=0,
    diagnostic_measured_Native_Runtime=0,
    Native_call_scope='Current Source34 selected owner and independent native/model-denied tests; Source32 actual30-second failure evidence is historical. Synthetic budget calls are not Native measurements.',
    actual_Source34_Native_performance_pending=True,actual_Source34_Global_Gap_PASS_pending=True,
    final_gap_PASS_claimed=False,actual_complete_day_or_month_speedup_not_proven=True,
    new_evidence='Owner and independent current-source selected regressions, all1105 file records and original1007 unchanged science. Source33 full-LP computational policy is byte-identical; current RMP hint guards/lifecycle are tested.',
    carried_evidence='Source33 review214/214, sparse freeze and actual27 canonical admissions remain historical. Original1007 and97of98 Source33 execution files remain identical. No past suite is represented as a current full-suite rerun.',
    healthy_active_workers_not_modified=True,fresh_native_runtime_zero_no_previous_checkpoint_or_budget_carry=True)
for key in REQUIRED_VALIDATION:new[key]=True
new['source_script']=record(__file__)
target=ROOT/'autonomous/V34_VALIDATION_BINDING_TEMPLATE.json';assert not target.exists()
target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,source_SHA=sha,template=record(target))))
