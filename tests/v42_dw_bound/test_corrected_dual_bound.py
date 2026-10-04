from v42_dw_bound.common import *
from v42_dw_bound.certificate import corrected,global_dual,decide
from v42_dw_bound.fixtures import master
from v42_disjunctive.certificate import down
from fractions import Fraction as F
from scipy import sparse
import numpy as np
import ast

def test_weak_duality_negative_blocks_exact_enumeration():
    case=dict(demands=[[4,1],[3,1]]);rmp=master(case,[[0],[0]]);full=master(case,[[0,1],[0,1]])
    assert rmp['value']==7 and full['value']==2
    stars=[min(-sum(p*v for p,v in zip(rmp['pi'],a))-rmp['alpha'][m] for a in block) for m,block in enumerate(rmp['cols'])]
    assert stars==[-3,-2] and rmp['value']+sum(min(F(0),b) for b in stars)==full['value']
def test_positive_pricing_does_not_raise_bound_above_RMP():
    r=master(dict(demands=[[1,3],[1,2]]),[[0],[0]])
    stars=[min(-sum(p*v for p,v in zip(r['pi'],a))-r['alpha'][m] for a in block) for m,block in enumerate(r['cols'])]
    assert stars==[0,0] and r['value']==2
def test_conservative_beta_dyadic_outward_rounding():
    native=[-.5,.1,0.,-.25];alpha=[2.,3.,4.,5.];lb,q,beta,delta=corrected(F(0),alpha,native)
    expected=F(14)+sum(min(F(0),F(down(F(v)-F(EPS)))) for v in native)
    assert q==expected and F(lb)<=q and all(b<=F(n)-F(EPS) for b,n in zip(beta,native))
def test_free_global_nonzero_stationarity_is_paid_not_discarded():
    A=sparse.csr_matrix([[1.,-1.]])
    d=dict(sense=np.array(['=']),objective=np.array([1.,0.]),rhs=np.array([2.]),constant=np.array(0.))
    v,p=global_dual(A,d,np.array([.5]),np.array([0.,-3.]),np.array([10.,3.]))
    assert v==F(-1,2) and p['nonzero_residual_columns']==2 and not p['sign_projection']
def test_wrong_actual_Pi_sign_is_rejected():
    import pytest
    A=sparse.csr_matrix([[1.]])
    d=dict(sense=np.array(['<']),objective=np.array([1.]),rhs=np.array([2.]),constant=np.array(0.))
    with pytest.raises(AssertionError):global_dual(A,d,np.array([1.]),np.array([0.]),np.array([10.]))
def test_material_early_stop_direction():
    assert decide(T_MATERIAL,T_MATERIAL+.1)=='PROVEN_MATERIAL'
    assert decide(T_MATERIAL-.001,T_MATERIAL+.1)=='INCONCLUSIVE'
def test_nonmaterial_early_stop_direction_and_boundary():
    assert decide(None,T_MATERIAL)=='PROVEN_NONMATERIAL' and decide(None,T_MATERIAL+.001)=='INCONCLUSIVE'
def test_prereg_base_budget_and_policy():
    p=read(OUT/'DW_DUAL_BOUND_PREREGISTRATION.json');assert p['base']==BASE and p['total_new_heavy_budget_seconds']==3600 and p['per_pricing_max_seconds']==300
    assert not p['pricing_first_negative_termination'] and not p['heuristic_pricing'] and p['full_original_local_domain']
def test_all_1048_checkpoint_columns_preserved():
    a=read(OUT/'DW_BOUND_CHECKPOINT_AUDIT.json');assert a['PASS'] and (a['initial_columns'],a['generated_columns'],a['total_columns'])==(4,1044,1048)
    assert len(a['checks'])==1048 and all(c['PASS'] and c['raw_integer_exact'] and c['axis_exact'] for c in a['checks'])
    for c in a['checks']:assert sha(ROOT/c['file'])==c['file_SHA']
def test_PR140_all_tracked_bytes_unchanged():assert preserved()>9900
def test_matrix_partition_and_native_domains_unchanged():
    a=read(OUT/'DW_BOUND_BUILD_RECEIPT.json');old=read(RESUME/'DW_RESUME_RMP_BUILD_RECEIPT.json')['pricing_model_census']
    assert a['PASS'] and a['restored']==1048 and not a['old_basis_used'] and not a['failed_terminal_dual_used']
    for new,previous in zip(a['pricing_census'],old):assert new['signature']==previous['signature'] and new['full_original_domain'] and new['horizon']==96
def test_formal_theorem_and_all_adversarial_fixtures():
    assert read(OUT/'DW_CORRECTED_DUAL_THEOREM.json')['PASS']
    a=read(OUT/'DW_CORRECTED_BOUND_BOUNDED_FIXTURES.json');assert a['PASS'] and len(a['cases'])>=10
    for c in a['cases']:assert F(c['L_corr'])<=F(c['z_full'])<=F(c['z_RMP']) and c['converged_equality']
def test_actual_native_Pi_ObjBound_and_ObjCon_confirmation():
    a=read(OUT/'DW_DUAL_SIGN_AND_BOUND_PROOF.json');assert a['PASS'] and a['manual_RC_equals_solver_RC'] and a['ObjBound_minimization_and_ObjCon_verified']
    assert all(c['PASS'] for c in a['native_cases'])
def test_pricing_never_terminates_at_first_negative():
    source=(ROOT/'v42_dw_bound/run.py').read_text(encoding='utf8');tree=ast.parse(source)
    observe=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='observe')
    assert not any(isinstance(n,ast.Attribute) and n.attr=='terminate' for n in ast.walk(observe))
    for p in ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT):
        r=read(OUT/p['receipt']);assert not r['first_negative_termination'] and not r['callback_termination']
def test_full_domain_zero_gaps_solver1e8_and_300s():
    for p in ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT):
        r=read(OUT/p['receipt']);s=r['settings'];assert s['Threads']==1 and s['MIPGap']==s['MIPGapAbs']==0 and s['TimeLimit']<=300
        assert s['FeasibilityTol']==s['IntFeasTol']==s['OptimalityTol']==EPS and r['full_original_domain'] and r['horizon']==96 and r['objective_transport_exact']
def test_TimeLimit_is_bound_only_and_never_most_negative_added():
    prices=ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT);cols=ledger('DW_NEW_COLUMN_LEDGER.csv',OUT)
    for c in cols:
        p=next(p for p in prices if p['call']==c['pricing_call']);assert p['classification']=='OPTIMAL_NEGATIVE' and float(c['rc_opt'])<-EPS
    assert len(cols)==read(OUT/'DW_FINAL_RESULT.json')['new_columns']
def test_four_betas_bind_to_one_actual_optimal_RMP_dual():
    rmps=ledger('DW_RMP_LEDGER.csv',OUT)
    for p in ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT):
        r=next(r for r in rmps if r['iteration']==p['iteration']);assert r['status']=='2' and r['dual_SHA']==p['dual_SHA'] and float(r['full_row_max'])<=POST
def test_certificate_or_null_never_uses_incumbent_as_beta():
    r=read(OUT/'DW_FINAL_RESULT.json');c=read(OUT/'DW_FINAL_BOUND_CERTIFICATE.json')
    if c['PASS']:
        b=c['best_certificate'];assert b['certified'] and b['L_corr']<=b['U_RMP']+POST and b['all_retained_corrected_RC_audit_PASS']
        for f,beta in zip(b['pricing_receipts'],b['beta_raw']):assert read(OUT/f)['ObjBound']==beta and read(OUT/f)['valid_bound']
    else:assert r['best_corrected_certified_LB'] is None
def test_no_replay_no_aging_and_budget_preserved():
    r=read(OUT/'DW_FINAL_RESULT.json');assert r['old_pricing_replayed']==0 and not r['old_failed_dual_used'] and r['retained_columns']==1048+r['new_columns'] and r['wall_budget_PASS'] and r['total_heavy_wall_seconds']<=3600
def test_May_and_downstream_production_firewall():
    r=read(OUT/'DW_FINAL_RESULT.json');assert r['May_optimizer_Actual_Fresh_AC']==[0,0,0] and not any(r[k] for k in ('branch_and_price_run','production_M1','P2_RUN','A2_RUN','M2_RUN'))
    from v42_campaign.plan import build_plan
    assert build_plan()==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json') and len(build_plan()['nodes'])==1458
