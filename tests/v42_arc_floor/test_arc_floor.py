"""Required original-LP, conservative support, transfer and threshold tests."""
import pytest,numpy as np
from scipy import sparse
from fractions import Fraction as F
from v42_arc_floor.common import OUT,BASE_HEAD,EPS,read,thresholds,decision,early_trigger
from v42_arc_floor.support import certify,support

def test_PR143_exact_identity_checkpoint():
    x=read(OUT/'ARC_LP_BASE_IDENTITY.json');assert x['PASS'] and x['PR143_exact_head']==BASE_HEAD and len(x['checks'])==x['retained_columns']==1158

def test_original_FULL_axis_integrality_map_only():
    x=read(OUT/'ARC_LP_RELAXATION_IDENTITY.json');assert x['PASS'] and (x['rows'],x['columns'],x['nnz'])==(961472,316743,8587630)
    assert x['discrete_relaxed']==x['binary_relaxed']==208312 and x['integer_relaxed']==0
    assert x['only_integrality_relaxed'] and x['all_original_LB_UB_exact'] and x['native_relax_independent_crosscheck']['PASS']
    assert not any(x['original_native_constructs'].values()) and not x['IsMIP'] and x['ModelSense']==1
    with np.load(OUT/'ARC_LP_RELAXATION_MAP.npz') as z:assert np.all(z['relaxed_types']=='C') and np.array_equal(np.flatnonzero(z['original_types']!='C'),z['discrete_indices'])

def test_actual_arc_LP_OPTIMAL_and_primal_objective():
    n=read(OUT/'ARC_LP_NATIVE_RECEIPT.json');p=read(OUT/'ARC_LP_PRIMAL_AUDIT.json');assert n['status']==2 and not n['IsMIP'] and n['discrete_variables']==0
    assert n['settings']['Threads']==1 and n['settings']['FeasibilityTol']==n['settings']['OptimalityTol']==EPS
    assert not set(n['settings'])&{'MIPFocus','MIPGap','IntFeasTol','NodeMethod'}
    assert p['PASS'] and p['max_constraint_violation']<=1e-6 and p['max_bound_violation']<=EPS and p['objective_recompute_error']<=EPS

@pytest.mark.parametrize('name',['min_le','min_ge','equality','finite_LB','finite_UB','free','fixed','objective_constant'])
def test_native_dual_sign_support_fixtures(name):
    r=read(OUT/'ARC_LP_DUAL_CONVENTION_FIXTURES.json');x=next(x for x in r['fixtures'] if x['fixture']==name)
    assert r['PASS'] and x['PASS'] and x['native_status']==2 and abs(x['L_support']-x['native_objective'])<=EPS

def test_free_support_is_not_pseudo_finite():
    with pytest.raises(ValueError):support({0:F(1)},[-np.inf],[np.inf])
    with pytest.raises(ValueError):support({0:F(-1)},[0],[1e100])
    assert support({0:F(0)},[-np.inf],[np.inf])==0
    assert support({0:F(1)},[0],[np.inf])==0

def test_equality_multiplier_repair_exact_free_stationarity():
    A=sparse.csr_matrix([[1.]])
    d=dict(objective=np.array([2.]),constant=np.array(7.),rhs=np.array([2.]),sense=np.array(['=']),lower=np.array([-np.inf]),upper=np.array([np.inf]))
    with pytest.raises(ValueError):certify(A,d,np.array([2.+1e-10]))
    c=certify(A,d,np.array([2.+1e-10]),[(0,0)])
    assert c['L_dual_support']==11 and c['repaired_free_stationarity_max']==0 and c['equality_multiplier_repairs']==1
    assert c['original_bounds_only'] and not c['derived_pseudo_bounds_used']

def test_scalar_floor_validity_and_downward_rounding():
    a=read(OUT/'ARC_LP_CERTIFIED_RESULT.json');c=read(OUT/'ARC_LP_DUAL_SUPPORT_CERTIFICATE.json')
    assert a['ARC_LP_CERTIFIED'] and c['PASS'] and c['exact_rational'] and c['numerical_PASS'] and c['repaired_free_stationarity_max']==0
    assert F(c['L_dual_support'])<=F(int(c['exact_numerator']),int(c['exact_denominator']))
    assert a['L_arc_cert']<=a['native_optimum']+EPS and not a['legacy_used_as_authority']

def test_dominance_transitivity_and_max_bound():
    x=read(OUT/'DW_ARC_FLOOR_TRANSFER_CERTIFICATE.json');a=read(OUT/'DW_AGGREGATED_LOWER_BOUND.json');assert x['PASS'] and a['PASS']
    assert a['L_DW_cert']==max(a['L_arc_cert'],a['L_corr_best_old']) and not a['legacy_MIP_bound_used']

def test_native_and_support_threshold_authority_no_legacy():
    a=read(OUT/'ARC_LP_CERTIFIED_RESULT.json');t=read(OUT/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');x=thresholds(a['native_optimum'],a['L_arc_cert'])
    assert all(t[k]==v for k,v in x.items()) and not t['legacy_authority']
    assert t['material_comparator']>=t['nonmaterial_comparator']

def test_numerical_threshold_band_does_not_give_false_decision():
    t=thresholds(.5,.49999999)
    assert decision(.505,.6,t)=='PROVEN_MATERIAL'
    assert decision(.49,t['nonmaterial_comparator'],t)=='PROVEN_NONMATERIAL'
    assert decision(.49,(t['T_cert']+t['T_from_lower'])/2,t)=='INCONCLUSIVE'

@pytest.mark.parametrize('accepted,upper,expected',[
    ([0,0],[.6,.59],'TWO_ZERO_ACCEPTED'),
    ([1,1,1],[.6,.5999,.5998,.5997],'THREE_ROUND_IMPROVEMENT_BELOW_0_001'),
    ([1],[.576],'UPPER_WITHIN_0_002'),
])
def test_frozen_early_certification_trigger(accepted,upper,expected):assert early_trigger(accepted,upper,.575)==expected

def test_true_RC_Discovery_and_same_dual_certification():
    from pathlib import Path
    for file in (OUT/'pricing_receipts').glob('PRICE_*.json'):
        p=read(file);assert p['settings']['Threads']==1 and p['full_original_domain'] and not p['basis_or_pool_restriction']
        if p['type']!='DISCOVERY':assert p['dual_SHA']==p['true_dual_SHA'] and not p['stabilized_discovery']
        for c in p['candidates']:
            if c['selected']:assert c['valid_negative'] and c['rc_inc']<=-1e-7 and c['physical']['PASS'] and c['full_original_local']['PASS']
    final=read(OUT/'DW_THRESHOLD_FINAL_CERTIFICATION.json')
    if final['status']=='COMPLETED':assert len(final['pricing_receipts'])==4

def test_distinct_budgets_no_domain_or_pricing_redesign():
    a=read(OUT/'ARC_OPTIMIZE_INTERVALS.json');d=read(OUT/'DW_OPTIMIZE_INTERVALS.json');p=read(OUT/'ARC_LP_PREREGISTRATION.json')
    assert a['union_seconds']<=600 and d['union_seconds']<=900 and d['arc_budget_carried']==0
    assert p['pricing_full_original_domain'] and not p['pricing_redesign'] and not p['column_deletion'] and not p['parameter_sweeps']
    assert not p['warm_RMP_selected'] and p['fixed_pricing_workers']==4 and p['RAM_floor_GiB']==1

def test_worker_campaign_production_firewall():
    p=read(OUT/'CAMPAIGN_WORKER_POLICY.json');assert [p[f'B{k}_DAY_WORKERS'] for k in range(4)]==[4,1,4,1]
    assert p['B2_INNER_PRICING']==1 and p['B3_INNER_PRICING']==4 and not p['Actual_to_Planning']
    p=read(OUT/'CAMPAIGN_NO_EXECUTION_RECEIPT.json');assert p['May_optimizer_calls']==p['Actual_calls']==p['Fresh_AC_calls']==0 and not p['Branch_and_Price']
