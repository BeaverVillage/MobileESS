"""Comparison receipt and residual checks; no optimizer invocation."""
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from v44 import root_lp_compare


def test_primal_check_rejects_unavailable_point_and_measures_original_rows():
    assert root_lp_compare.primal_check(SimpleNamespace(SolCount=0))==dict(primal_point_available=False)
    model=SimpleNamespace(SolCount=1,X=[1.,2.],RHS=[3.,.5],Sense=['=','<'],
        LB=[0.,0.],UB=[2.,3.],Obj=[1.,0.],ObjCon=0.,Status=2,
        getA=lambda:sparse.csr_matrix([[1.,1.],[1.,0.]]))
    result=root_lp_compare.primal_check(model)
    assert result['row_violation']==.5 and result['bound_violation']==0.
    assert result['objective']==1. and result['solver_status_OPTIMAL'] is True


def test_comparison_is_equal_budget_cold_lp_and_cannot_promote_production():
    value=root_lp_compare.authorization()
    assert value['methods']==[2,1] and value['seconds_per_method']==300.
    assert value['independent_cold_copies'] and value['common_MIP_presolve']
    assert value['per_method_Presolve']==0 and value['Threads']==1
    assert value['MIP_optimization'] is False and value['production_setting_changed'] is False
