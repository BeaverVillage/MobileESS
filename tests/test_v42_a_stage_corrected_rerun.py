import pytest
from types import SimpleNamespace
from v42_a_stage_early import execution
from v42_a_stage_early.policy import POLICY, OUT, STATIC

def test_rerun_authorization_excludes_p1_and_all_other_actions():
    for action in ('P1','A1','P2','ACTUAL','PLANNING_FREEZE','FRESH_AC'):
        with pytest.raises(PermissionError): execution.authorize('2025-05-19',action)
    assert execution.authorize('2025-05-19','FEASIBILITY_LP')=='2025-05-19'
    for day in ('2025-05-17','2025-05-12','2025-05-10'):
        with pytest.raises(PermissionError): execution.authorize(day,'OPTIMIZE')

def test_exact_native_scope_excludes_original_p1():
    model=SimpleNamespace(NumIntVars=0)
    token=execution._scope.set((model,'2025-05-19','ORIGINAL_P1',lambda:100))
    try:
        with pytest.raises(PermissionError): execution.guard(model,'2025-05-19')
    finally: execution._scope.reset(token)

def test_new_namespace_and_original_fixed_policy():
    assert OUT.name=='v42_a_stage_phase1_corrected_rerun_20261008'
    assert STATIC.name=='v42-a-stage-corrected-static'
    assert POLICY['negative_trigger']==16 and POLICY['fully_priced_class_trigger']==24
    assert POLICY['stagnation_resolves']==3 and POLICY['stagnation_relative_decrease']==.01
    assert POLICY['cumulative_budget_seconds']==900 and POLICY['max_pricing_workers']==4
    assert POLICY['max_P1_rounds']==0
