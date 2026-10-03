import copy
import numpy as np
import pytest
from scipy import sparse
from v42_postsolve import contract as module
from v42_postsolve.contract import contract,numerical_residuals,audit_point,feasible,current_certificate,STAGES

def test_solver_tolerances_remain_strict():
    c=contract()
    assert all(c[k]==1e-8 for k in ('solver_FeasibilityTol','solver_IntFeasTol','solver_OptimalityTol'))

def test_numerical_authority_is_fixed():
    assert contract()['postsolve_numerical_audit_tol']==1e-6

def fixture():
    A=sparse.csr_matrix([[1.]])
    d=dict(rhs=np.array([1.05]),sense=np.array(['<']),lower=np.array([0.]),upper=np.array([1.05]),types=np.array(['C']),objective=np.array([1.]),constant=np.array(0.))
    return A,d

def test_ratings_and_point_are_not_changed():
    A,d=fixture();point=np.array([1.05+1.423e-8]);before=point.tobytes();rhs=d['rhs'].tobytes();upper=d['upper'].tobytes()
    assert audit_point('M1',A,d,point)['NUMERICAL_AUDIT_PASS']
    assert point.tobytes()==before and rhs==d['rhs'].tobytes() and upper==d['upper'].tobytes()

def test_no_binary_rounding_or_clipping():
    A,d=fixture();d['types']=np.array(['B']);d['rhs']=d['upper']=np.array([1.]);p=np.array([1.+5e-7]);before=p.tobytes()
    result=audit_point('M1',A,d,p)
    assert result['NUMERICAL_AUDIT_PASS'] and result['residuals']['near_integer']>0
    assert before==p.tobytes()

@pytest.mark.parametrize('stage',STAGES)
def test_same_validator_for_every_stage(stage):
    assert numerical_residuals(stage,{'bound':1.423e-8})['NUMERICAL_AUDIT_PASS']
    assert not numerical_residuals(stage,{'bound':1.000001e-6})['NUMERICAL_AUDIT_PASS']

def test_above_threshold_and_nonfinite_fail():
    assert not numerical_residuals('M1',{'bound':2e-6})['NUMERICAL_AUDIT_PASS']
    assert not numerical_residuals('M1',{'bound':float('nan')})['NUMERICAL_AUDIT_PASS']

def test_physical_violation_cannot_be_hidden():
    n=numerical_residuals('M1',{'bound':1.423e-8})
    assert not feasible(n,{'PHYSICAL_AUDIT_PASS':False},solver_accepted=True)
    assert not feasible(n,{'PHYSICAL_AUDIT_PASS':True},solver_accepted=False)

def records():
    n=numerical_residuals('M1',{'bound':1.423e-8})
    r=dict(numerical=n,physical={'PHYSICAL_AUDIT_PASS':True},solver_accepted=True,solve_log_sha256='current',objective=.72)
    run=dict(bound_provenance='same_completed_solve',old_bounds_used=False,solve_log_sha256='current',solve_result_sha256='result',model_identity={'matrix':'matrix'},A1_freeze_sha256='freeze',NormalAmps_authority_sha256='rating',LB=.56,valid_global_LB=True)
    return run,r

def test_ub_requires_both_audits():
    run,r=records();cert=current_certificate(run,[r]);assert cert['UB']==.72 and not cert['M1_P1_ACCEPTED']
    r['physical']['PHYSICAL_AUDIT_PASS']=False
    assert current_certificate(run,[r])['UB'] is None
    r['physical']['PHYSICAL_AUDIT_PASS']=True;r['numerical']['NUMERICAL_AUDIT_PASS']=False
    assert current_certificate(run,[r])['UB'] is None

def test_old_certificate_cannot_supply_bounds_or_points():
    run,r=records();run['bound_provenance']='PR134'
    with pytest.raises(ValueError,match='HISTORICAL'):current_certificate(run,[r])
    run['bound_provenance']='same_completed_solve';r['solve_log_sha256']='historical'
    with pytest.raises(ValueError,match='DIFFERENT'):current_certificate(run,[r])
