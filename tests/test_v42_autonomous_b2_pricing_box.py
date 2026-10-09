from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse

from v42_autonomous_b2 import pricing_box
from v42_b2_seed_recovery_v18 import certificate_box
from v42_m1_hybrid.blocks import build_blocks
from v42_m1_hybrid.bound import local_exact_price_bound,assemble_full_dual
from v42_m1_hybrid.pricing import make_prices


def case_with_globally_implied_box(objective=1.):
    matrix=np.zeros((5,5))
    for j in range(4):matrix[j,j]=1.
    matrix[4,0]=-1.;matrix[4,4]=1.
    d=dict(names=np.array([f'route_flow[M{i},0]' for i in range(1,5)]+['original_helper']),
        lower=np.array([0.,0.,0.,0.,-np.inf]),upper=np.array([1.,1.,1.,1.,np.inf]),
        types=np.array(['B','B','B','B','C']),objective=np.array([0.,0.,0.,0.,objective]),
        rhs=np.zeros(5),sense=np.array(['>','>','>','>','=']),
        row_names=np.array([str(i) for i in range(5)]),constant=np.array(0.))
    return SimpleNamespace(A=sparse.csr_matrix(matrix),d=d,case_sha='original_case')


@pytest.mark.parametrize('objective',[1.,-1.])
def test_actual_infinity_error_and_projected_exact_global_sum(objective,tmp_path):
    case=case_with_globally_implied_box(objective);decomp=build_blocks(case)
    prices=make_prices(case,decomp,{})
    block=decomp.nonunit_block
    with pytest.raises(OverflowError,match='Infinity'):
        local_exact_price_bound(block,prices.nonunit_exact_objective,{})
    before=(case.d['lower'].copy(),case.d['upper'].copy(),block.d['lower'].copy(),block.d['upper'].copy())
    authority=pricing_box.ProjectionAuthority(case,decomp,tmp_path,local_exact_price_bound)
    nonunit=authority.local_bound(block,prices.nonunit_exact_objective,{})
    assert nonunit['exact_bound']==('0' if objective>0 else '-1')
    assert nonunit['standalone_nonunit_domain_lower_bound_claimed'] is False
    assert nonunit['standalone_nonunit_pricing_closure_claimed'] is False
    assert nonunit['rounded_or_artificial_bounds_used'] is False
    unit_duals={u:{} for u in decomp.units}
    full=assemble_full_dual(case,decomp,{},unit_duals,{})
    global_cert=certificate_box.check(case.A,case.d,full,case_sha=case.case_sha)
    exact_sum=Fraction(nonunit['exact_bound'])
    for unit,unit_block in decomp.units.items():
        actual=authority.local_bound(unit_block,prices.exact_objectives[unit],{})
        original=local_exact_price_bound(unit_block,prices.exact_objectives[unit],{})
        assert actual['exact_bound']==original['exact_bound']
        assert 'certificate_scope' not in actual
        exact_sum+=Fraction(actual['exact_bound'])
    assert exact_sum==Fraction(global_cert['exact_bound'])
    after=(case.d['lower'],case.d['upper'],block.d['lower'],block.d['upper'])
    assert all(np.array_equal(a,b) for a,b in zip(before,after))


def test_box_proof_does_not_invent_finite_endpoint_without_original_equalities(tmp_path):
    case=case_with_globally_implied_box()
    case.d['sense'][4]='<'
    with pytest.raises(ValueError,match='DO_NOT_PROVE_FINITE_HELPER_BOX'):
        pricing_box.ProjectionAuthority(case,build_blocks(case),tmp_path,local_exact_price_bound)


@pytest.mark.parametrize('mutate',['matrix','bound','nonunit_box','case_sha','decomp_sha'])
def test_proved_box_cannot_admit_changed_original_case_or_block(tmp_path,mutate):
    case=case_with_globally_implied_box();decomp=build_blocks(case)
    authority=pricing_box.ProjectionAuthority(case,decomp,tmp_path,local_exact_price_bound)
    if mutate=='matrix':case.A.data[0]=2.
    elif mutate=='bound':case.d['upper'][0]=2.
    elif mutate=='case_sha':case.case_sha='other_case'
    elif mutate=='decomp_sha':decomp.case_sha='other_case'
    else:decomp.nonunit_block.d['lower'][0]=-.5
    with pytest.raises(ValueError,match='PRICING_BOX_.*DRIFT'):
        authority.local_bound(decomp.nonunit_block,{0:Fraction(1)},{})


def test_false_implication_witness_is_rejected_by_independent_checker(tmp_path,monkeypatch):
    case=case_with_globally_implied_box();original=certificate_box.derive
    def false_proof(*args,**kwargs):
        lo,hi,proof=original(*args,**kwargs)
        proof['steps'][0]['exact_upper']='1/2'
        return lo,hi,proof
    monkeypatch.setattr(certificate_box,'derive',false_proof)
    with pytest.raises(ValueError,match='HELPER_BOX_EXACT_ENDPOINT_DRIFT'):
        pricing_box.ProjectionAuthority(case,build_blocks(case),tmp_path,local_exact_price_bound)


def test_scoped_run_retains_original_pricing_and_local_exact_code():
    from v42_m1_hybrid import pricing
    routed=pricing_box.scoped_pricing(pricing.run_pricing,local_exact_price_bound,lambda p:p)
    assert routed.original_pricing.__code__ is pricing.run_pricing.__code__
    assert routed.original_local_bound.__code__ is local_exact_price_bound.__code__
    assert 'LOCAL_PRICE_SUM_AND_FULL_ORIGINAL_CERTIFICATE_DISAGREE' in pricing.run_pricing.__code__.co_consts
