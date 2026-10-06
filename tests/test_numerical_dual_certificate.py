import numpy as np
import pytest
from scipy import sparse
from fractions import Fraction as F
from v42_m_stage_root.numerical_certificate import canonicalize,independent_csc,support,signs,down

def fixture(sign_error=1e-11):
    # Free z=lambda; <= z cap. Raw tiny sign and negative lambda RC are repaired
    # in dual multipliers, never by changing A/b/bounds or clipping RC.
    A=sparse.csr_matrix([[1.,-1.],[1.,0.],[0.,1.]])
    v=dict(pi=np.array([1e-10,sign_error,1.+2e-10]),objective=np.array([0.,1.]),
        sense=np.array(['=','<','=']),rhs=np.array([0.,2.,1.]),
        lower=np.array([-np.inf,0.]),upper=np.array([np.inf,np.inf]),constant=np.array(0.))
    return A,v
def test_exact_canonical_sign_free_stationarity_and_all_column_feasibility():
    A,v=fixture();pi,q,terms,p=canonicalize(A,v,[(0,0)],[2],True)
    qq,tt,L,free=independent_csc(A,v,pi)
    assert signs(v['sense'],pi) and pi[1]==0 and q.get(0,F(0))==qq[0]==0
    assert qq[1]>=0 and L==p['exact_value']==F(1) and free==1
    assert p['convexity_offsets'][0][1]<0
    assert v['pi'][1]==1e-11 and v['upper'][1]==np.inf
def test_small_sign_is_not_acceptance_without_authority():
    A,v=fixture()
    with pytest.raises(ValueError,match='AUTHORITY_REQUIRED'):canonicalize(A,v,[(0,0)],[2],False)
def test_large_sign_residual_cannot_be_canonicalized():
    A,v=fixture(1e-7)
    with pytest.raises(ValueError,match='OUTSIDE_AUTHORITY'):canonicalize(A,v,[(0,0)],[2],True)
def test_missing_equality_pivot_rejected():
    A,v=fixture()
    with pytest.raises(ValueError,match='INCOMPLETE'):canonicalize(A,v,[],[2],True)
def test_nonzero_infinite_support_never_ignored():
    with pytest.raises(ValueError,match='INFINITE_BOUND'):support({0:F(-1,10**15)},[0.],[np.inf])
def test_independent_checker_rejects_altered_canonical_dual():
    A,v=fixture();pi,_,_,_=canonicalize(A,v,[(0,0)],[2],True)
    pi[0]=F(1,10**15)
    with pytest.raises(ValueError,match='FREE_STATIONARITY'):independent_csc(A,v,pi)
def test_nonconvexity_matrix_cannot_be_used_for_rc_correction():
    A=sparse.csr_matrix([[1.,2.]])
    v=dict(pi=np.array([1e-10]),objective=np.array([0.,0.]),sense=np.array(['=']),rhs=np.array([1.]),lower=np.array([0.,0.]),upper=np.array([np.inf,np.inf]),constant=np.array(0.))
    with pytest.raises(ValueError,match='CONVEXITY_ROW'):canonicalize(A,v,[],[0],True)
def test_convexity_offset_proves_both_retained_columns_with_original_infinite_upper():
    A=sparse.csr_matrix([[1.,1.]])
    v=dict(pi=np.array([0.]),objective=np.array([-1e-10,-2e-10]),sense=np.array(['=']),rhs=np.array([1.]),lower=np.array([0.,0.]),upper=np.array([np.inf,np.inf]),constant=np.array(0.))
    pi,q,_,proof=canonicalize(A,v,[],[0],True)
    qi,_,L,_=independent_csc(A,v,pi)
    assert all(x>=0 for x in qi.values()) and L==F(float(-2e-10))
    assert proof['convexity_offsets']==[(0,F(float(-2e-10)))]
def test_outward_rounding_never_overstates_rational_lower_bound():
    q=F(1,10);assert F(down(q))<=q
