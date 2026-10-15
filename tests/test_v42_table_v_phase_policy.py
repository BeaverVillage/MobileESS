from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_integration import table_v_phase_policy as policy

def snapshot():
    return LinearSnapshot(sp.csr_matrix([[1.]]),np.array([0.]),np.array([1.]),np.array(['>']),np.array([0.]),np.array(['C']),
        (Objective('Phi',((0,Fraction(1)),),Fraction(0)),)).require()

def test_fast_presolve_does_not_change_scientific_replay_threshold():
    s=snapshot();raw=dict(X=np.array([0.]),Pi=np.array([1.]),RC=np.array([0.]))
    assert policy.POLICIES[0].parameters()['Presolve']==-1
    assert policy.validate_raw(s,raw)['PASS']
    assert policy.REPLAY_TOLERANCE==1e-6

def test_fast_numerical_reconstruction_failure_requires_fallback():
    raw=dict(X=np.array([0.]),Pi=np.array([0.]),RC=np.array([0.]))
    assert not policy.validate_raw(snapshot(),raw)['PASS']

@pytest.mark.parametrize('violation',[7.63e-6,3.814697265625e-6,2e-6])
def test_old_failed_points_stay_failed_at_original_threshold(violation):
    raw=dict(X=np.array([-violation]),Pi=np.array([1.]),RC=np.array([0.]))
    assert not policy.validate_raw(snapshot(),raw)['PASS']

def test_phase_calls_leave_original_integer_native_budget():
    assert policy.allowance(4100.,0.)==900.
    assert policy.allowance(1900.,0.)==100.
    assert policy.allowance(1700.,0.)==0.
    assert policy.allowance(4000.,850.)==50.

def test_positive_tiny_phi_never_becomes_exact_zero():
    verify=policy.require_exact_zero(lambda *a,**k:dict(PASS=True,exact_arithmetic_zero=False))
    assert not verify(None,None)['PASS']

def test_exact_zero_pass_is_retained():
    verify=policy.require_exact_zero(lambda *a,**k:dict(PASS=True,exact_arithmetic_zero=True))
    assert verify(None,None)['PASS']

def test_dual_sign_violation_is_rejected_even_if_rc_reconstructs():
    raw=dict(X=np.array([0.]),Pi=np.array([-1.]),RC=np.array([2.]))
    assert not policy.validate_raw(snapshot(),raw)['PASS']

def test_missing_native_duals_cannot_certify_phase_I():
    assert not policy.validate_raw(snapshot(),dict(X=np.array([0.])))['PASS']

def test_policy_profiles_change_arithmetic_but_preserve_barrier_and_threads():
    assert len({tuple(sorted(p.parameters().items())) for p in policy.POLICIES})==4
    for p in policy.POLICIES:
        assert p.parameters()['Method']==2 and p.parameters()['Threads']==1
        assert p.seconds<=300
