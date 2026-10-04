from v42_dw_resume.common import *
from v42_dw_resume.audit import corrected_rows
from v42_dw_root.run import no_negative
import numpy as np
from scipy import sparse

def test_preexisting_v42_contract_and_append_only_addendum():
    from v42_campaign.authority import SCIENTIFIC
    a=read(OUT/'NUMERICAL_GATE_CORRECTION_ADDENDUM.json');assert SCIENTIFIC['postsolve_numerical_tol']==a['new_postsolve_tol']==1e-6
    assert not any(a[k] for k in ('scientific_model_changed','physical_authority_changed','solver_tolerances_changed','restart_from_zero','failed_iteration_210_dual_reused'))
def test_original_history_byte_preserved():assert preserved()>8900 and read(ORIGINAL/'DW_ROOT_RESULT.json')['status']=='INCONCLUSIVE'
def test_original_210_failure_not_retroactively_changed():
    r=read(OUT/'DW_ITER210_NUMERICAL_REAUDIT.json');assert not r['old_logged_gate_PASS'] and r['new_logged_gate_consistency_PASS'] and not r['retroactive_certification']
def test_missing_210_primal_not_invented():
    r=read(OUT/'DW_ITER210_NUMERICAL_REAUDIT.json');assert not r['saved_iteration_210_primal_available'] and not r['read_only_primal_reevaluation_performed'] and r['optimization_calls']==0
def test_checkpoint_all840_exact_and_physical():
    r=read(OUT/'DW_RESUME_CHECKPOINT_AUDIT.json');assert r['PASS'] and (r['initial_columns'],r['generated_columns'],r['total_columns'])==(4,836,840)
    assert len(r['checks'])==840 and all(c['PASS'] and c['raw_binary_exact'] and c['master_coefficients_exact'] and c['route_mode_PQ_SOC_initial_terminal_travel_PCS_PASS'] for c in r['checks'])
def test_checkpoint_file_SHA_identity():
    for r in read(OUT/'DW_RESUME_CHECKPOINT_AUDIT.json')['checks']:assert sha(ORIGINAL/r['file'])==r['file_SHA']
def test_no_old_pricing_or_dual_replayed():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');assert r['old_pricing_replay_calls']==0 and not r['failed_iteration_210_dual_reused'] and not r['restarted_from_zero']
    assert all(int(p['call'])>=837 and int(p['iteration'])>=211 for p in ledger('DW_RESUME_PRICING_LEDGER.csv',OUT))
def test_cold840_RMP_rebuild():
    r=read(OUT/'DW_RESUME_RMP_BUILD_RECEIPT.json');assert r['PASS'] and r['restored_columns']==840 and r['cold_rebuild'] and not r['basis_used'] and not r['failed_iteration_210_dual_reused']
def test_budget_not_reset_and_exact_receipt_authority():
    a=read(OUT/'NUMERICAL_GATE_CORRECTION_ADDENDUM.json');r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');old=read(ORIGINAL/'DW_ROOT_RESULT.json')
    assert a['remaining_heavy_budget']==3600-old['total_pilot_wall_seconds'] and r['wall_budget_PASS'] and r['cumulative_heavy_wall_seconds']<=3600
    assert r['cumulative_heavy_wall_seconds']==old['total_pilot_wall_seconds']+r['resumed_heavy_wall_seconds']
def test_affine_postsolve_changes_without_bounds_or_integer_relaxation():
    A=sparse.csr_matrix([[1.]]);d=dict(rhs=np.array([0.]),sense=np.array(['=']),lower=np.array([-1.]),upper=np.array([1.]),types=np.array(['C']),objective=np.array([0.]),constant=np.array(0.))
    assert corrected_rows(A,d,np.array([6.37e-8]))['PASS']
    assert not corrected_rows(A,d,np.array([1.01e-6]))['PASS']
    bounded=dict(d,upper=np.array([0.]));assert not corrected_rows(A,bounded,np.array([6.37e-8]))['PASS']
    integer=dict(d,types=np.array(['B']));assert not corrected_rows(A,integer,np.array([6.37e-8]),True)['PASS']
    assert not corrected_rows(A,d,np.array([6.37e-8]),False,np.array([True]))['PASS']
def test_solver_and_pricing_tolerances_unchanged():
    for p in ledger('DW_RESUME_PRICING_LEDGER.csv',OUT):
        s=read(OUT/f"pricing_receipts/PRICE_{int(p['call']):04d}.json")['settings']
        assert s['FeasibilityTol']==s['OptimalityTol']==s['IntFeasTol']==1e-8 and s['MIPGap']==s['MIPGapAbs']==0 and s['Threads']==1 and s['TimeLimit']<=600
def test_global_BestBd_threshold_unchanged_and_timeout_not_certificate():
    assert not no_negative(None) and not no_negative(-1e-7) and not no_negative(-2e-8) and no_negative(-1e-8)
    for p in ledger('DW_RESUME_PRICING_LEDGER.csv',OUT):
        if p['NO_NEGATIVE_COLUMN_CERTIFIED']=='True':assert p['global_BestBd'] and float(p['global_BestBd'])>=-1e-8
def test_added_negative_columns_validated_no_merging_or_deletion():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');rows=ledger('DW_RESUME_COLUMN_VALIDATION_LEDGER.csv',OUT)
    assert sum(c['added']=='True' for c in rows)==r['new_validated_columns'] and r['cumulative_columns']==840+r['new_validated_columns']
    assert all(c['PASS']=='True' and float(c['reduced_cost'])<=-1e-7 for c in rows if c['added']=='True')
def test_new_dual_validated_before_pricing():
    rows=ledger('DW_RESUME_ITERATION_LEDGER.csv',OUT)
    for p in ledger('DW_RESUME_PRICING_LEDGER.csv',OUT):
        r=next(row for row in rows if row['iteration']==p['iteration']);assert r['dual_SHA']==p['dual_SHA'] and float(r['row_max_violation'])<=1e-6 and float(r['dual_violation'])<=1e-8
def test_all_four_same_dual_certificates_or_null_LB():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');c=read(OUT/'DW_CORRECTED_ROOT_CERTIFICATE.json')
    if r['DW_ROOT_OPTIMAL_CERTIFIED']:
        assert c['PASS'] and all(r['final_pricing_certificates'].values()) and r['DW_root_LB']>=BASE_LB-1e-8
        assert {p['MESS'] for p in ledger('DW_RESUME_PRICING_LEDGER.csv',OUT) if p['dual_SHA']==c['same_RMP_dual_SHA'] and p['NO_NEGATIVE_COLUMN_CERTIFIED']=='True'}==set(UNITS)
    else:assert r['DW_root_LB'] is None and c['L_DW'] is None
def test_cumulative_counts():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');assert r['cumulative_RMP_calls']==210+r['new_RMP_solves'] and r['cumulative_pricing_calls']==836+r['new_pricing_calls']
def test_preserved_full_domain_and_physical_authority():
    a=read(ORIGINAL/'DW_EXACTNESS_CONTRACT.json');assert all(not a[k] for k in ('top_k_routes','route_pool_restriction','hamming_restriction','site_pruning','time_pruning','heuristic_pricing'))
    census=read(OUT/'DW_RESUME_RMP_BUILD_RECEIPT.json')['pricing_model_census'];old=read(ORIGINAL/'DW_PRICING_MODEL_CENSUS.json')['blocks']
    for current,previous in zip(census,old):assert current['signature']==previous['signature'] and current['full_original_domain'] and current['horizon']==96
def test_no_production_or_branch_and_price_and_May_preserved():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');assert not any(r[k] for k in ('branch_and_price_run','production_M1_run','P2_RUN','A2_RUN','M2_RUN'))
    assert r['campaign_optimizer_calls']==r['campaign_Actual_calls']==r['campaign_Fresh_AC_calls']==0
    from v42_campaign.plan import build_plan
    assert build_plan()==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json') and len(build_plan()['nodes'])==1458
