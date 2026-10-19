import ast
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import csr_matrix
import v44_recovery_r044
from v44_recovery_r044.numerical import fixed_model,adapt_tree
from v44_recovery_r044 import operations as op
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective


def model():
    return LinearSnapshot(csr_matrix([[4.,1.]]),np.array([0.,0.]),np.array([2.,10.]),
        np.array(['>']),np.array([8.5]),np.array(['I','C']),
        (Objective('rho',((1,Fraction(1)),)),))


def test_exact_integer_candidate_still_gets_continuous_repair_and_certified_floor():
    s=model();x=np.array([2.,.4999998]);fixed,integer,residual,j=fixed_model(s,x,Fraction(1,2))
    assert residual==0 and np.array_equal(integer,[True,False]) and j==1
    assert fixed.lower[0]==fixed.upper[0]==2 and fixed.lower[1]==.5
    assert np.array_equal(fixed.upper,s.upper) and all(fixed.vtypes=='C')
    assert fixed.matrix is s.matrix and fixed.rhs is s.rhs and fixed.objectives is s.objectives
    assert x[1]==.4999998 and s.lower[1]==0


def test_repair_rejects_unsupported_bound_and_objective():
    with pytest.raises(ValueError,match='DYADIC'):fixed_model(model(),np.array([2.,.5]),Fraction(1,3))
    s=replace(model(),objectives=(Objective('rho',((1,Fraction(2)),)),))
    with pytest.raises(ValueError,match='DYADIC'):fixed_model(s,np.array([2.,.5]),Fraction(1,2))
    with pytest.raises(ValueError,match='OUTSIDE'):fixed_model(model(),np.array([2.,.5]),Fraction(11))


def test_original_bound_conflict_physical_gap_and_identity_checks_remain():
    from v44.frozen.v43_a2 import adapter
    from v42_may_campaign_native90 import a_stage
    tree=adapt_tree(adapter.source_tree(a_stage,'run'));body=ast.unparse(tree)
    assert '_r044_repair' in body and '_r044_load_state' in body and '_r044_priced' in body
    for required in ('A_CERTIFIED_LB_UB_CONFLICT','physical.verify(point)','primal_replay(typed, point)',
                     'acceptance = contract(', 'A_ORIGINAL_NATIVE_P1_OBJECTIVE_IDENTITY_FAIL',
                     'A_COMPLETE_ORIGINAL_P1_PRICING_CLOSURE_REQUIRED'):
        assert required in body
    assert "native.solve(typed" not in body
    compile(ast.fix_missing_locations(ast.Module(body=[tree],type_ignores=[])),'<r044-test>','exec')


def test_unknown_dispatch_source_is_rejected():
    with pytest.raises(ValueError,match='BOUNDARY_DRIFT'):adapt_tree(ast.parse('def run():\n    return None').body[0])


def test_retry_authority_only_extends_explicit_target_location(monkeypatch):
    calls=[]
    monkeypatch.setattr(op,'_week_authority',lambda r:calls.append(r))
    monkeypatch.setattr(op,'read',lambda p:dict(sources=['sealed'],validation=dict(path='tests'),PASS=True))
    monkeypatch.setattr(op,'record',lambda p:dict(path=str(p)))
    monkeypatch.setattr(op,'verify',lambda r:None)
    monkeypatch.setattr(op,'sources',lambda:['sealed'])
    r=dict(day='2025-05-08',arm='B3',case_root=str(op.TARGET),R044_authorization=dict(path=str(op.PERMIT)),R044_parent=str(op.PARENT))
    op.request_authority(r)
    assert calls==[dict(r,case_root=str(op.PARENT))] and r['case_root']==str(op.TARGET)
    r['R044_authorization']={}
    with pytest.raises(PermissionError,match='AUTHORITY'):op.request_authority(r)


def test_normal_case_uses_original_request_authority(monkeypatch):
    calls=[];monkeypatch.setattr(op,'_week_authority',lambda r:calls.append(r))
    r=dict(day='2025-05-09',arm='B3',case_root=str(op.CAMPAIGN/'2025-05-09/B3/attempt001'))
    op.request_authority(r);assert calls==[r]
