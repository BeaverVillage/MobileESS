from fractions import Fraction as F
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from v42_m1_anytime.dual_stabilization import (StageIdentity,DualSearch,ray_maximum,
    repair_equalities,mix,checked_dual,dual_sha)

def identity(stage='B2_M',case='c'):
    return StageIdentity(stage,'2025-05-01','a'*64,'b'*64,'d'*64,case*64,'e'*64,'f'*64)

def problem(A=((1.,),),c=(1.,),b=(.5,),sense=('=',),lo=(0.,),hi=(1.,),names=('x[0]',),rows=('constraint[0]',)):
    d={k:np.asarray(v) for k,v in dict(objective=c,rhs=b,sense=sense,lower=lo,upper=hi,names=names,row_names=rows).items()}
    d['constant']=np.asarray(0.);d['types']=np.asarray(['C']*len(c))
    return SimpleNamespace(A=csr_matrix(np.asarray(A)),d=d,case_sha='c'*64)

def exact_checker(case):
    # Existing independent theorem; no native imports or solver is required.
    from v42_m1_research.check_lb import check_rational_dual_certificate
    return lambda y:check_rational_dual_certificate(case.A,case.d,y,case_sha=case.case_sha)

def test_exact_ray_finds_peak_missed_by_all_positive_grid_weights():
    p=problem();r=ray_maximum(p.A,p.d,{}, {'0':'64'})
    assert r['alpha']=='1/64' and r['exact_computational_box_bound']=='1/2'
    assert r['Global_LB_claimed'] is False and r['independent_certificate'] is False

def test_every_breakpoint_can_confirm_no_improvement():
    p=problem(c=(0.,),b=(0.,));r=ray_maximum(p.A,p.d,{}, {'0':'64'})
    assert r['alpha']=='0' and r['exact_computational_box_bound']=='0'

def test_convex_rational_mix_preserves_both_inequality_signs():
    p=problem(A=((1.,),(1.,)),b=(0.,0.),sense=('<','>'),rows=('left','right'))
    for alpha in ('0','1/8','1/4','1/2','3/4','1'):
        y=mix({'0':'-1/3','1':'2/3'},{'0':'-5/7','1':'3/7'},alpha)
        assert checked_dual(p.A,p.d,y)==y and F(y['0'])<=0<=F(y['1'])

def test_noncanonical_or_unknown_row_axes_rejected():
    p=problem()
    for bad in ({'00':'1'},{'-1':'1'},{'1':'1'}):
        with pytest.raises(ValueError):checked_dual(p.A,p.d,bad)

def test_incorrect_sign_and_nonfinite_domain_rejected():
    p=problem(sense=('<',))
    with pytest.raises(ValueError):checked_dual(p.A,p.d,{'0':'1'})
    p.d['upper'][0]=np.inf
    with pytest.raises(ValueError):ray_maximum(p.A,p.d,{}, {'0':'-1'})

def test_triangular_repair_preserves_exact_input_and_inequality_multiplier():
    p=problem(A=((1.,-2.),(0.,1.)),c=(1.,0.),b=(0.,1.),sense=('=','<'),lo=(0.,0.),hi=(10.,1.),
        names=('helper[0]','x[0]'),rows=('helper_binding[0]','capacity[0]'))
    y,report=repair_equalities(p.A,p.d,{'0':'10/3','1':'-1/3'})
    assert y=={'0':'1','1':'-1/3'} and report['changed_equalities']==1
    assert report['Native_calls']==0 and report['Global_LB_claimed'] is False

def test_affine_definition_cycle_rejected():
    p=problem(A=((1.,-1.),(-1.,1.)),c=(0.,0.),b=(0.,0.),sense=('=','='),lo=(0.,0.),hi=(1.,1.),
        names=('a[0]','b[0]'),rows=('a_binding[0]','b_binding[0]'))
    with pytest.raises(ValueError,match='CYCLE'):repair_equalities(p.A,p.d,{})

def test_selected_candidate_uses_existing_exact_checker_not_rank_as_authority():
    p=problem();r=DualSearch(identity()).select(p,{}, {'0':'64'},0,certify=exact_checker(p))
    assert r['status']=='QUALIFIED' and r['alpha']=='1/64' and F(r['certificate']['exact_bound'])==F(1,2)
    assert r['Global_LB_published'] is False and len(r['checks'])<=2

def test_cross_stage_and_fixed_input_identities_never_share_keys():
    m1=identity('B3_M1');m2=identity('B3_M2')
    assert m1.sha!=m2.sha and m1.sha!=identity().sha
    changed=StageIdentity('B3_M1',m1.day,m1.source_sha,m1.input_sha,'0'*64,m1.case_sha,m1.matrix_sha,m1.domain_sha)
    assert changed.sha!=m1.sha

def test_foreign_case_certificate_cannot_be_admitted():
    p=problem();s=DualSearch(identity())
    with pytest.raises(ValueError,match='SAME_STAGE'):
        s.select(p,{}, {'0':'64'},0,certify=lambda y:dict(PASS=True,case_sha='9'*64,exact_bound='1'))

def test_same_raw_dual_pair_not_rechecked_after_failure():
    p=problem();s=DualSearch(identity());calls=[]
    def bad(y):calls.append(y);return dict(PASS=False)
    with pytest.raises(ValueError):s.select(p,{}, {'0':'64'},0,certify=bad)
    assert s.select(p,{}, {'0':'64'},0,certify=bad)['status']=='NON_NOVEL' and len(calls)==1

def test_duplicate_pricing_ignores_irrelevant_unit_multipliers():
    s=DualSearch(identity());d=SimpleNamespace(coupling_rows=np.asarray([0]),nonunit_block=SimpleNamespace(original_rows=np.asarray([],dtype=int)))
    assert s.consume_pricing(d,{'0':'1','1':'2'})
    assert not s.consume_pricing(d,{'0':'1','1':'999'})
    assert s.consume_pricing(d,{'0':'1','1':'999'},'MILP_AND_LP')

def test_bounded_rescue_needs_certified_gain_novel_catalog_budget_and_stagnation():
    s=DualSearch(identity());cert=dict(PASS=True,case_sha='c'*64,exact_bound='1/2')
    s.record_pricing({},cert,F(1,100),new_catalog_sha='1'*64)
    h=[dict(method='U1',certified_gain=0)]*8
    assert s.take_rescue(h,209,F(1,2)) is None
    assert s.take_rescue(h,210,F(3,100)) is None
    assert s.take_rescue(h,210,F(1,2))['catalog_sha']=='1'*64
    assert s.take_rescue(h,210,F(1,2)) is None

def test_used_catalog_zero_gain_and_unverified_cert_never_trigger_rescue():
    s=DualSearch(identity());h=[dict(method='U1',certified_gain=0)]*8
    cert=dict(PASS=True,case_sha='c'*64,exact_bound='1/2');s.record_rmp('1'*64)
    s.record_pricing({},cert,F(1,100),new_catalog_sha='1'*64)
    s.record_pricing({},cert,0,new_catalog_sha='2'*64)
    assert s.take_rescue(h,5400,F(1,2)) is None
    with pytest.raises(ValueError):s.record_pricing({},dict(PASS=False),1,new_catalog_sha='3'*64)

def test_all_search_operations_preserve_original_matrix_domain_and_types():
    p=problem();before=(p.A.copy(),{k:v.copy() for k,v in p.d.items()})
    DualSearch(identity()).select(p,{}, {'0':'64'},0,certify=exact_checker(p))
    assert (p.A!=before[0]).nnz==0
    for k,v in p.d.items():assert np.array_equal(v,before[1][k])
    # Production B2 has unbounded affine helpers. Use an independently replayed
    # implication envelope only for ranking, retaining its original domain.
    p=problem(names=('helper[0]',),rows=('helper_binding[0]',));p.d['upper'][0]=np.inf
    from v42_b2_seed_recovery_v18.certificate_box import derive,verify,check
    def envelope(A,d):
        lo,hi,proof=derive(A,d);proof['independent_replay']=verify(A,d,lo,hi,proof)
        return lo,hi,proof
    result=DualSearch(identity(),finite_box=envelope).select(p,{}, {'0':'64'},0,
        certify=lambda y:check(p.A,p.d,y,case_sha=p.case_sha))
    assert np.isinf(p.d['upper'][0]) and result['computational_box_proof']['independent_replay']['PASS']

def test_stage_and_materiality_configuration_cannot_relax_final_gap():
    with pytest.raises(ValueError):identity('A1')
    with pytest.raises(ValueError):DualSearch(identity(),max_exact=3)
    with pytest.raises(ValueError):DualSearch(identity(),max_rescues=2)
    with pytest.raises(ValueError):DualSearch(identity(),min_gain=0)
    p=problem();p.d['upper'][0]=np.inf
    r=DualSearch(identity()).select(p,{}, {'0':'64'},0,certify=lambda y:pytest.fail('unproved box'))
    assert r['status']=='NOT_RUN_FINITE_BOX_PROOF_NOT_PREPARED' and r['Global_LB_published'] is False
