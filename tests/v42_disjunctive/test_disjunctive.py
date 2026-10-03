from v42_disjunctive.common import *
from v42_disjunctive.certificate import down,up,safe_bound,rational_bound
from fractions import Fraction as F
from scipy import sparse
import numpy as np
import pytest

def test_PR137_exact_model_identity():
    r=read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')
    assert r['PASS'] and r['base_exact_head']==BASE
    assert (r['rows'],r['columns'],r['binaries'],r['nnz'])==(886017,316743,208312,8447855)
    assert r['reference']==read(REF/'M1_PR135_MODEL_IDENTITY.json')['reference']
    assert all(sha(p)==h for p,h in r['source_SHA'].items())
    assert r['native_row_names_SHA']==read(ROOT/'docs/v42_m1_exact_formulation_strengthening/M1_STRENGTHENING_BASE_IDENTITY.json')['native_row_names_SHA']

def test_A1_freeze_unchanged():
    assert read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')['A1_freeze_SHA']==sha(SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')

def test_zero_margin_unchanged():
    r=read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')
    assert r['voltage']==[.95,1.05] and r['voltage_margin']==0

def test_NormalAmps_unchanged():
    assert read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')['NormalAmps_SHA']=='0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'

def test_P1_P2_unchanged():
    assert read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')['P1_P2_objective_SHA']==sha(SCIENCE/'M1_OBJECTIVE_CONTRACT.json')

def test_connection_partition_exhaustive_routes(monkeypatch):
    import v42_disjunctive.cuts as c
    monkeypatch.setattr(c,'write',lambda *a:None)
    r=c.bounded()
    assert r['PASS'] and all(r['cases'][v]>0 for v in ('transit','computed','uncomputed'))
    assert read(OUT/'CONNECTION_STATE_PARTITION_PROOF.json')['PASS']

def test_only_selected_stay_bound_changed_and_restored():
    import csv
    rows=list(csv.DictReader((OUT/'CONDITIONAL_STATE_LP_RESULTS.csv').open(encoding='utf8')))
    assert rows
    assert all(r['only_selected_bounds_changed']=='True' and r['baseline_basis_restored']=='True' and r['stay_name'].startswith('arc[') for r in rows)
    with np.load(ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz') as z:
        assert all(z['integer_types'][int(r['column'])]=='B' and z['names'][int(r['column'])]==r['stay_name'] for r in rows)
    assert read(OUT/'CONDITIONAL_POST_LOOP_IDENTITY.json')['PASS']

def test_safe_coefficient_below_certified_conditional_bound():
    r=read(OUT/'CONDITIONAL_LB_CERTIFICATE.json')
    for c in r['certificates']:
        if c['PASS']:
            assert BASE_LB<=c['L_safe']<=c['certified_conditional_lower_bound']
            q=F(int(c['exact_bound_numerator']),int(c['exact_bound_denominator']))
            assert F(c['rational_lower_bound'])<=q
            assert c['primal_full_rows_audit']['PASS'] and c['basis_exists']
            assert sha(OUT/c['dual_certificate_file'])==c['dual_certificate_SHA']
    assert r['safe_coefficients_from_raw_objective'] is False

def test_cut_exact_valid_and_downward_coefficients():
    assert read(OUT/'DISJUNCTIVE_EPIGRAPH_VALIDITY_PROOF.json')['PASS']
    for c in read(OUT/'DISJUNCTIVE_CUT_DEFINITIONS.json')['cuts']:
        for v in c['terms']:
            assert 0<=F(v['coefficient'])<=F(v['L_safe'])-F(BASE_LB)

def test_uncomputed_state_fallback():
    assert read(OUT/'DISJUNCTIVE_CUT_DEFINITIONS.json')['uncomputed_fallback']==BASE_LB
    coefficients=[F(1,100),F(2,100)]
    assert F(BASE_LB)+sum(c*y for c,y in zip(coefficients,[0,0]))==F(BASE_LB)

def test_transit_fallback():
    assert read(OUT/'DISJUNCTIVE_CUT_DEFINITIONS.json')['transit_fallback']==BASE_LB
    assert read(OUT/'DISJUNCTIVE_EPIGRAPH_BOUNDED_EQUIVALENCE.json')['cases']['transit']>0

def test_no_new_binaries():
    m=read(OUT/'STRENGTHENED_MATRIX_IDENTITY.json')['matrix']
    assert m['binaries']==208312 and m['columns']==316743 and m['added_binaries']==m['added_columns']==0

def test_no_domain_pruning_except_exact_Farkas_proof():
    r=read(OUT/'CONDITIONAL_INFEASIBLE_STATE_PROOF.json')
    assert r['unproven_fixings_added']==0
    for c in r['proven_fixings']:
        assert c['PASS'] and c['independently_reconstructed_without_solver']
        assert F(int(c['exact_bound_numerator']),int(c['exact_bound_denominator']))>0
    assert read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')['no_site_route_time_domain_change']

def test_no_false_old_UB_LB_promotion_or_loose_material_gate():
    assert material(BASE_LB)['PASS'] is False
    assert material(BASE_LB+.001)['PASS'] is False
    assert material(BASE_LB+.0051)['PASS'] is True
    assert material(None)['PASS'] is False
    root=read(OUT/'DISJUNCTIVE_STRENGTHENED_ROOT_RESULT.json')
    assert root['fresh_root_solve'] and root['no_old_bound_or_diagnostic_UB_promotion']
    assert root['selected']==material(root['objective_LB'])['PASS']

def test_campaign_orchestrator_exact_bytes():
    r=read(OUT/'CAMPAIGN_ORCHESTRATOR_PRESERVATION.json')
    assert r['PASS'] and r['dry_plan_stages']==1458
    assert all(sha(ROOT/v['path'])==v['base_SHA']==v['current_SHA'] for v in r['byte_identical_files'])

def test_Actual_feedback_firewall():
    plan=read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')
    for n in plan['nodes']:
        if n['planning']:
            assert n['Actual_values_allowed'] is False
            assert not any('/ACTUAL' in p or '/FRESH_AC' in p for p in n['Planning_dependencies'])

def test_B3_four_loop_contract():
    from v42_campaign.plan import build_plan
    plan=read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')
    assert build_plan()==plan
    assert plan['main_order']==['B0','B1','B2','B3_L1'] and plan['convergence_order']==['B3_L2','B3_L3','B3_L4']
    r=read(OUT/'CAMPAIGN_ORCHESTRATOR_PRESERVATION.json')
    assert r['B3_four_loop_contract_preserved'] and not r['fixed_point_early_stop'] and not r['B0_B1_B2_repeated']

def test_May_production_calls_zero():
    r=read(OUT/'CAMPAIGN_NO_EXECUTION_RECEIPT.json')
    assert r['campaign_optimizer_calls']==r['campaign_Actual_calls']==r['campaign_Fresh_AC_calls']==0
    assert all(r[k]=='NOT_RUN' for k in ('MAY_MAIN_CAMPAIGN_EXECUTION','B3_LOOP2_PRODUCTION','B3_LOOP3_PRODUCTION','B3_LOOP4_PRODUCTION'))

def test_exact_weak_duality_pays_for_inexact_dual_residual():
    # min x, x>=1/3, 0<=x<=2. A deliberately inexact pi is still valid.
    A=sparse.csr_matrix([[1.]])
    d=dict(objective=np.array([1.]),constant=np.array(0.),rhs=np.array([1/3]),sense=np.array(['>']))
    r=rational_bound(A,d,np.array([1.+1e-10]),np.array([0.]),np.array([2.]))
    bound=F(int(r['exact_bound_numerator']),int(r['exact_bound_denominator']))
    assert F(r['rational_lower_bound'])<=bound<=F(1/3)
    assert bound<F(1/3) and r['nonzero_residual_columns']==1

@pytest.mark.parametrize('q',[F(1,3),F(-1,3),F(7,10),F(1234567,998)])
def test_outward_bounds_exact_rational(q):
    assert F(down(q))<=q<=F(up(q))

def test_wall_budget_warm_basis_and_no_retries():
    r=read(OUT/'CONDITIONAL_STATE_LP_RESOURCE_RECEIPT.json')
    assert r['wall_budget_PASS'] and r['total_separation_wall_seconds']<=1800
    assert r['model_instances']==1 and r['Threads']==1 and r['Method']==1
    assert r['cold_conditional_barrier_calls']==r['retry_calls']==r['other_solver_calls']==r['pytest_during_heavy']==0
    assert sum(r['classifications'].values())==r['actual_conditional_LP_calls']
    log=(OUT/'CONDITIONAL_STATE_LP.log').read_text(encoding='utf8')
    assert log.count('LP warm-start: use basis')==r['actual_conditional_LP_calls']
    assert log.count('Optimize a model with 886017 rows, 316743 columns and 8447855 nonzeros')==r['actual_conditional_LP_calls']

def test_canary_requires_new_strict_material_gate():
    root=read(OUT/'DISJUNCTIVE_STRENGTHENED_ROOT_RESULT.json')
    canary=read(OUT/'DISJUNCTIVE_MIP_CANARY_RESULT.json')
    if not root['selected']:
        assert canary['status']=='NOT_RUN' and canary['optimization_calls']==0
        assert canary['next_direction']=='route-transition / multi-time disjunction'
    else:assert canary['optimization_calls']==1 and canary['settings']['TimeLimit']==600

def test_baseline_basis_is_complete_and_optimal_without_retry():
    r=read(OUT/'DISJ_BASELINE_BASIS_RECEIPT.json')
    assert r['PASS'] and r['optimization_calls']==1 and r['usable_simplex_basis']
    assert abs(r['objective']-BASE_LB)<=1e-8 and r['full_original_audit']['PASS']
    with np.load(OUT/'BASELINE_BASIS.npz') as z:
        assert len(z['VBasis'])==316743 and len(z['CBasis'])==886017
        assert int((z['VBasis']==0).sum())+int((z['CBasis']==0).sum())==886017

def test_installed_native_cut_has_correct_sign_and_all_three_cases(monkeypatch):
    import gurobipy as gp
    import v42_disjunctive.cuts as cuts
    from v42_integrated.matrix import arrays
    definition=dict(MESS='unit',slot=0,added=True,
                    terms=[dict(column=0,coefficient=.02),dict(column=1,coefficient=.03)])
    monkeypatch.setattr(cuts,'read',lambda p: {'cuts':[definition]} if p.name=='DISJUNCTIVE_CUT_DEFINITIONS.json' else {'proven_fixings':[]})
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    try:
        for i in range(3):m.addVar(vtype='B',name=f'arc[unit,{i}]')
        m.addVar(lb=0,ub=1,name='rho_max');m.update()
        result=cuts.install(m);A,d=arrays(m)
        assert result==dict(cuts_added=1,exact_infeasible_state_fixings=0)
        assert m.NumVars==4 and m.NumBinVars==3 and m.NumConstrs==1
        assert d['sense'][0]=='>' and d['rhs'][0]==BASE_LB
        assert list(A.toarray()[0])==[-.02,-.03,0.,1.]
        # Evaluate exactly, including computed, uncomputed and transit states.
        for y in ((1,0,0),(0,1,0),(0,0,1),(0,0,0)):
            rho=F(BASE_LB)+F(.02)*y[0]+F(.03)*y[1]
            lhs=sum(F(float(a))*v for a,v in zip(A.toarray()[0],[*y,rho]))
            assert lhs==F(BASE_LB)
    finally:m.dispose()
