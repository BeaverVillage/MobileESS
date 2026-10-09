"""Synthetic independent hybrid-bound attacks; no Native model creation."""
from copy import deepcopy
from fractions import Fraction as F
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_m1_hybrid.verify import (verify_decomposition,verify_global_lagrangian_bound,
                                target_thresholds,verify_full_pricing_closure,
                                verify_rmp_pricing_lower_bounds)


@pytest.fixture
def fixture():
    units=['MESS01','MESS02','MESS03','MESS04']
    names=[f'Pch[{u},STA01,66]' for u in units]+['rho_max','response_line_P[66,0]']
    # xi>=1, sum xi-rho<=0, rho<=10, grid response equality.
    A=sparse.csr_matrix(np.array([[1,0,0,0,0,0],[0,1,0,0,0,0],
        [0,0,1,0,0,0],[0,0,0,1,0,0],[1,1,1,1,-1,0],
        [0,0,0,0,1,0],[-1,-1,-1,-1,0,1]],dtype=float))
    d=dict(names=np.array(names),lower=np.array([0.,0.,0.,0.,0.,-100.]),
        upper=np.array([10.,10.,10.,10.,10.,100.]),types=np.array(['C']*6),
        objective=np.array([0.,0.,0.,0.,1.,0.]),constant=np.array(0.),
        rhs=np.array([1.,1.,1.,1.,0.,10.,0.]),sense=np.array(['>','>','>','>','<','<','=']),
        row_names=np.array([f'energy_balance[{u},66]' for u in units]+['line_thermal_face','voltage_upper','response_line_P_binding']))
    case=SimpleNamespace(A=A,d=d,case_sha='same_original_case')
    def block(unit,rows,cols):
        rows=np.array(rows,dtype=np.int64);cols=np.array(cols,dtype=np.int64)
        e={k:d[k][cols].copy() for k in ('names','lower','upper','types','objective')}
        e.update({k:d[k][rows].copy() for k in ('rhs','sense','row_names')});e['constant']=np.array(0.)
        return SimpleNamespace(unit=unit,A=A[rows][:,cols].tocsr(),d=e,original_rows=rows,original_columns=cols)
    decomp=SimpleNamespace(case_sha=case.case_sha,
        units={u:block(u,[i],[i]) for i,u in enumerate(units)},
        nonunit_block=block('NONUNIT',[5],[4,5]),coupling_rows=np.array([4,6],dtype=np.int64))
    return case,decomp,np.array([-1.,0.]),{u:np.array([1.]) for u in units},np.array([0.])


def test_exact_original_bound_from_four_blocks_grid_and_signed_coupling(fixture):
    case,blocks,prices,local,grid=fixture
    r=verify_global_lagrangian_bound(case,blocks,prices,local,nonunit_dual=grid)
    assert r['PASS'] and F(r['exact_Global_LB'])==4
    assert r['independent_decomposition']['all_original_rows_exactly_once']
    assert r['independent_decomposition']['all_original_columns_exactly_once']
    assert not r['full_pricing_closure_certified']
    assert not r['native_rounded_price_objectives_used_as_proof']
    assert r['Native_optimize_calls']==0


def test_rational_price_and_grid_seed_never_rerounded_to_native_float(fixture):
    case,blocks,_,local,_=fixture
    # Rational signed weights are assembled without casting their denominators
    # to native binary64. This mutation remains a valid but different LB.
    q=F(1,3)
    local={u:{'0':str(q)} for u in local}
    r=verify_global_lagrangian_bound(case,blocks,{'0':str(-q)},local,nonunit_dual={})
    assert r['canonical_sparse_original_row_rational_dual']['4']=='-1/3'
    assert F(r['exact_Global_LB'])==F(4,3)


@pytest.mark.parametrize('mutation',['row_missing','column_missing','coefficient','rhs','bounds','types','objective','case'])
def test_original_whole_day_partition_and_domain_mutation_rejected(fixture,mutation):
    case,blocks,_,_,_=fixture;b=blocks.units['MESS01']
    if mutation=='row_missing':b.original_rows=np.array([],dtype=np.int64)
    elif mutation=='column_missing':b.original_columns=np.array([],dtype=np.int64)
    elif mutation=='coefficient':b.A.data[0]=np.nextafter(b.A.data[0],np.inf)
    elif mutation=='rhs':b.d['rhs'][0]=np.nextafter(b.d['rhs'][0],np.inf)
    elif mutation=='bounds':b.d['upper'][0]=9.
    elif mutation=='types':b.d['types'][0]='B'
    elif mutation=='objective':b.d['objective'][0]=1.
    else:blocks.case_sha='different_frozen_day'
    with pytest.raises(ValueError,match='HYBRID_'):
        verify_decomposition(case,blocks)


def test_original_pure_grid_row_cannot_be_dropped_into_coupling_or_omitted(fixture):
    case,blocks,_,_,_=fixture
    blocks.nonunit_block.original_rows=np.array([],dtype=np.int64)
    with pytest.raises(ValueError,match='COMPLETE_96_SLOT_BLOCK_PARTITION_DRIFT'):
        verify_decomposition(case,blocks)
    blocks.coupling_rows=np.array([4,5,6],dtype=np.int64)
    with pytest.raises(ValueError,match='MIXED_ROW_PARTITION_DRIFT'):
        verify_decomposition(case,blocks)


def test_coupling_multiplier_has_original_minimization_sign(fixture):
    case,blocks,prices,local,grid=fixture;prices[0]=1.
    with pytest.raises(ValueError,match='INVALID_DUAL_ROW_SIGN'):
        verify_global_lagrangian_bound(case,blocks,prices,local,nonunit_dual=grid)


def test_missing_unit_dual_or_nonunit_grid_dual_cannot_complete_global_bound(fixture):
    case,blocks,prices,local,grid=fixture
    with pytest.raises(ValueError,match='RETAINED_NONUNIT_GRID_DUAL_MISSING'):
        verify_global_lagrangian_bound(case,blocks,prices,local)
    local.pop('MESS04')
    with pytest.raises(ValueError,match='LOCAL_DUAL_UNIT_COVER_INCOMPLETE'):
        verify_global_lagrangian_bound(case,blocks,prices,local,nonunit_dual=grid)


def test_duplicate_or_out_of_range_rational_local_dual_axis_rejected(fixture):
    case,blocks,prices,local,grid=fixture;local['MESS01']={'-1':'1'}
    with pytest.raises(ValueError,match='RATIONAL_LOCAL_DUAL_AXIS_DRIFT'):
        verify_global_lagrangian_bound(case,blocks,prices,local,nonunit_dual=grid)
    local['MESS01']={'00':'1'}
    with pytest.raises(ValueError,match='RATIONAL_LOCAL_DUAL_AXIS_DRIFT'):
        verify_global_lagrangian_bound(case,blocks,prices,local,nonunit_dual=grid)


def test_double_counting_original_objective_constant_rejected(fixture):
    case,blocks,_,_,_=fixture;blocks.units['MESS01'].d['constant']=np.array(1.)
    with pytest.raises(ValueError,match='OBJECTIVE_CONSTANT_DOUBLE_COUNT'):
        verify_decomposition(case,blocks)


def test_exact_5_percent_boundary_preserves_A_half_percent_and_P2_separation():
    r=target_thresholds(F(19,20),F(1))
    assert r['M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED']
    assert not r['historical_0p5_percent_gap_certified']
    assert r['A1_A2_target_exact']=='1/200' and r['M1_M2_research_target_exact']=='1/20'
    assert r['required_LB_at_current_UB_exact']=='19/20'
    assert r['required_UB_at_current_LB_exact']=='1'
    assert not r['M1_ACCEPTED'] and r['P2_certificate'] is None
    r=target_thresholds(F(19,20)-F(1,10**100),F(1))
    assert not r['M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED']


@pytest.mark.parametrize('status',['TIME_LIMIT','OPTIMAL','CUTOFF'])
def test_restricted_rmp_or_metadata_only_pricing_never_establishes_closure(status):
    fake={u:dict(PASS=True,status=status,min_reduced_cost=0.,all_columns=True) for u in ('a','b','c','d')}
    with pytest.raises(ValueError,match='FULL_PRICING_CLOSURE_NOT_IMPLEMENTED_OR_PROVEN'):
        verify_full_pricing_closure('same',fake,expected_units=list(fake))


@pytest.mark.parametrize('lb,ub',[(2,1),(-1,1),(0,0)])
def test_invalid_exact_bound_order_rejected(lb,ub):
    with pytest.raises(ValueError,match='EXACT_LB_UB_ORDER_INVALID'):
        target_thresholds(lb,ub)


def test_complete_original_lp_pricing_lb_proves_missing_columns_nonnegative(fixture):
    case,blocks,_,local,_=fixture
    # λ=-1 gives each price objective xi. Unit constraints xi>=1 imply β=1.
    # η=1 makes every original column's reduced cost >=0, even if the producing
    # local MILP terminated on TIME_LIMIT: its status is not used by this proof.
    report=verify_rmp_pricing_lower_bounds(case,blocks,{'4':'-1'},local,{u:'1' for u in local})
    assert report['full_unit_missing_column_pricing_closure_certified']
    assert all(F(c['exact_complete_domain_price_LB'])==1 and F(c['exact_missing_column_reduced_cost_LB'])==0
               for c in report['unit_certificates'].values())
    assert report['RMP_primal_optimality_or_native_objective_certified'] is False
    assert report['Global_LB_requires_separate_original_signed_dual_certificate']


def test_negative_pricing_lower_bound_is_not_a_proven_negative_integer_column(fixture):
    case,blocks,_,local,_=fixture
    report=verify_rmp_pricing_lower_bounds(case,blocks,{'4':'-1'},local,{u:'2' for u in local})
    assert not report['full_unit_missing_column_pricing_closure_certified']
    assert report['status']=='FULL_PRICING_CLOSURE_NOT_PROVEN'
    assert all(c['status']=='NOT_PROVEN_NEGATIVE_LOWER_BOUND_IS_INCONCLUSIVE' for c in report['unit_certificates'].values())


def test_missing_column_cost_uses_exact_coupling_and_finite_box_not_rounded_price(fixture):
    case,blocks,_,local,_=fixture
    # Arbitrary signed π is usable; wrong stationarity gets an exact box cost.
    local={u:{} for u in local}
    report=verify_rmp_pricing_lower_bounds(case,blocks,{'4':'-1/3'},local,{u:'-1/5' for u in local})
    for c in report['unit_certificates'].values():
        assert F(c['exact_complete_domain_price_LB'])==0
        assert F(c['exact_missing_column_reduced_cost_LB'])==F(1,5)
    # Reverse local equality sign cannot be smuggled into a ≥ native row.
    local['MESS01']={'0':'-1'}
    with pytest.raises(ValueError,match='INVALID_DUAL_ROW_SIGN'):
        verify_rmp_pricing_lower_bounds(case,blocks,{'4':'-1/3'},local,{u:'0' for u in local})


def test_price_certificate_case_axis_and_local_physics_multiplier_mutations_rejected(fixture):
    case,blocks,_,local,_=fixture
    with pytest.raises(ValueError,match='RMP_PRICE_CASE_MISMATCH'):
        verify_rmp_pricing_lower_bounds(case,blocks,dict(case_sha='wrong',multipliers={'4':'-1'}),local,{u:'1' for u in local})
    with pytest.raises(ValueError,match='RMP_PRICE_ROW_IS_LOCAL_UNIT_PHYSICS'):
        verify_rmp_pricing_lower_bounds(case,blocks,{'0':'1'},local,{u:'1' for u in local})
    with pytest.raises(ValueError,match='RATIONAL_DUAL_AXIS_DRIFT'):
        verify_rmp_pricing_lower_bounds(case,blocks,{'99':'1'},local,{u:'1' for u in local})
    missing=deepcopy(local);missing.pop('MESS04')
    with pytest.raises(ValueError,match='FOUR_UNIT_CERTIFICATE_COVER_INCOMPLETE'):
        verify_rmp_pricing_lower_bounds(case,blocks,{'4':'-1'},missing,{u:'1' for u in local})


def test_pricing_closure_source_coefficient_mutation_is_independently_rejected(fixture):
    case,blocks,_,local,_=fixture
    blocks.units['MESS01'].A.data[0]=.9999999999999999
    with pytest.raises(ValueError,match='ORIGINAL_BLOCK_CSR_COEFFICIENT_DRIFT'):
        verify_rmp_pricing_lower_bounds(case,blocks,{'4':'-1'},local,{u:'1' for u in local})
