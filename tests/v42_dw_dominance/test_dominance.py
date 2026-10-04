"""Dominance, exact fixture optima, and refusal to promote an integer bound."""
import pytest
from fractions import Fraction as F
from v42_dw_dominance.common import OUT,PR142,BASE_HEAD,BASE_LB,T_MATERIAL,read,sha,early_trigger,classify,decision
from v42_dw_dominance.fixtures import run,vertices

@pytest.fixture(scope='module')
def enumerated():return run()

@pytest.mark.parametrize('name',['route_split','charge_mode','SOC_travel_energy','PCS','grid_coupling','terminal_SOC','multi_MESS_coupling'])
def test_full_enumeration_dominance_and_integer_equivalence(enumerated,name):
    x=next(x for x in enumerated['fixtures'] if x['fixture']==name)
    assert F(x['z_arc_LP'])<=F(x['z_DW_LP'])<=F(x['z_original_integer'])
    assert F(x['z_DW_integer'])==F(x['z_original_integer'])
    assert x['PASS'] and x['all_integer_face_vertices']>0

def test_integer_bound_cannot_be_transferred_through_local_hulls():
    r=[([-1,0],'<',0),([0,-1],'<',0),([1,0],'<',1),([0,1],'<',1),([-1,-1],'<',F(-1,2))]
    v=vertices(2,r);assert min(sum(x) for x in v)==F(1,2)
    integer=[(x,y) for x in (0,1) for y in (0,1) if x+y>=F(1,2)]
    assert min(sum(x) for x in integer)==1
    assert read(OUT/'DW_BOUND_AGGREGATION_PROOF.json')['adopted_floor'] is None

def test_base_exact_identity_and_checkpoint():
    a=read(OUT/'DW_DOMINANCE_BASE_AUDIT.json');assert a['PASS'] and a['base_SHA']==BASE_HEAD
    assert a['retained_columns']==len(a['checks'])==1158
    assert a['checkpoint_SHA']==sha(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json')

def test_original_matrix_projection_and_global_freedom():
    p=read(OUT/'DW_COUPLING_IDENTITY_AUDIT.json');assert p['PASS']
    assert p['exact_duplicate_rows']==75455 and p['original_variable_axis_size']==316743
    assert p['disjoint_exhaustive_axes'] and p['bounds_objective_constant_identical'] and p['rho_no_extra_freedom']

def test_full_domain_not_finite_pool_theorem():
    p=read(OUT/'DW_FULL_SCALE_DOMINANCE_PROOF.json');assert p['PASS']
    assert p['full_domain_proof_is_symbolic_affine_inclusion'] and p['finite_pool_not_full_hull']
    assert len(p['proof_steps'])==6

def test_no_primal_or_mip_bound_promoted_to_arc_floor():
    p=read(OUT/'ARC_FLOOR_PROVENANCE_INSPECTION.json');assert not p['PASS']
    assert p['MIP_certificate_remains_valid_for_integer_problem'] and not p['requested_value_disproved']
    assert p['full_LP_point_keys']==p['reduced_LP_point_keys']==['values']
    assert not p['original_arc_LP_lower_bound_certified']

def test_max_rule_requires_both_same_optimum_premises():
    p=read(OUT/'DW_BOUND_AGGREGATION_PROOF.json');assert not p['PASS'] and p['dominance_theorem_PASS']
    r=read(OUT/'DW_PR142_REAGGREGATED_INTERVAL.json')
    assert r['certified_interval']==[r['L_corr_best'],r['U_RMP_best']]
    assert r['conditional_interval_if_arc_floor_certified']==[max(BASE_LB,r['L_corr_best']),r['U_RMP_best']]
    assert not r['conditional_interval_is_certified']

def test_bestbd_incumbent_diagnostics_do_not_change_lower_bound():
    p=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json');assert not p['incumbent_used_as_LB']
    for x in p['per_MESS']:
        assert x['proof_gap_m']>=-1e-8 and not x['incumbent_used_for_LB']
        assert x['rc_opt_m'] is None or x['native_status']==2
        assert abs(x['proof_weakness_room_m']-(min(0,x['rc_inc_m'])-min(0,x['beta_m'])))<1e-12
    assert p['classification']=='TRUE_NEGATIVE_RC_DOMINANT'

def test_registered_smoothing_true_dual_full_domain_and_no_deletion():
    p=read(OUT/'DW_THRESHOLD_PREREGISTRATION.json')
    assert p['full_original_domain'] and not p['column_deletion']
    assert p['true_RC_threshold']==-1e-7 and p['no_negative_BestBd']==-1e-8
    assert 'Discovery' in read(PR142/'DW_STABILIZATION_PREREGISTRATION.json')['policy']['acceptance'] or 'true' in p['certificate_authority'].lower()

def test_four_same_dual_existing_certifications():
    rows=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json')['per_MESS']
    for k in sorted({x['round'] for x in rows}):
        group=[x for x in rows if x['round']==k]
        assert len(group)==4 and len({x['dual_SHA'] for x in group})==1

def test_registered_fixed_resources_no_warm_or_tuning():
    p=read(OUT/'DW_THRESHOLD_PREREGISTRATION.json')
    assert p['fixed_workers']==4 and p['Threads']==1 and p['RAM_floor_GiB']==1
    assert not p['warm_RMP_tests'] and not p['warm_RMP_selected'] and not p['speed_tuning']
    assert p['optimize_budget_seconds']==900 and p['maximum_discovery_rounds']==8 and p['final_certification_rounds_at_most']==1

@pytest.mark.parametrize('accepted,uppers,expected',[
    ([0,0],[.59,.589,.588],'TWO_ZERO_ACCEPTED'),
    ([1,1,1],[.585,.5849,.5848,.5847],'THREE_ROUND_IMPROVEMENT_BELOW_0_001'),
    ([1],[T_MATERIAL+.001],'UPPER_WITHIN_0_002'),
    ([1,1],[.59,.588,.586],None),
])
def test_frozen_early_certification_triggers(accepted,uppers,expected):assert early_trigger(accepted,uppers)==expected

@pytest.mark.parametrize('room,negative,deficit,sufficient,expected',[
    (.02,0,.01,True,'PRICING_BOUND_WEAKNESS_SUPPORTED'),
    (0,.02,.01,True,'TRUE_NEGATIVE_RC_DOMINANT'),
    (.02,.02,.01,True,'MIXED'),
    (0,0,.01,False,'INCONCLUSIVE'),
])
def test_preregistered_classification(room,negative,deficit,sufficient,expected):assert classify(room,negative,deficit,sufficient)==expected

def test_threshold_authority_and_stop():
    assert decision(T_MATERIAL,T_MATERIAL+.01)=='PROVEN_MATERIAL'
    assert decision(BASE_LB,T_MATERIAL)=='PROVEN_NONMATERIAL'
    assert decision(BASE_LB,T_MATERIAL+.01)=='INCONCLUSIVE'
    r=read(OUT/'DW_THRESHOLD_FINAL_RESULT.json');assert r['total_optimize_wall_union']==r['new_pricing_calls']==r['new_RMP_solves']==r['new_discovery_columns']==0
    assert r['stop_stage']==4 and r['experiment_status']=='NOT_RUN'

def test_worker_and_feedback_preservation_no_production():
    p=read(OUT/'CAMPAIGN_WORKER_POLICY.json');assert [p[f'B{k}_DAY_WORKERS'] for k in range(4)]==[4,1,4,1]
    assert p['B2_INNER_PRICING_WORKERS']==1 and p['B3_INNER_PRICING_WORKERS']==4
    assert not p['Actual_to_Planning'] and p['previous_Planning_only']
    p=read(OUT/'CAMPAIGN_NO_EXECUTION_RECEIPT.json')
    assert p['MAY_PRODUCTION_CALLS']==p['Actual_calls']==p['Fresh_AC_calls']==0 and not p['BRANCH_AND_PRICE_RUN']
