import pytest
from v42_a_stage_canary import execution as e
from v42_a_stage_canary.policy import DAYS,POLICY
from v42_a_stage_lexcases.policy import POLICY as MAY19

def test_canary_cannot_authorize_before_verified_scope():
    for day in DAYS:
        with pytest.raises(PermissionError):e.authorize(day,'OPTIMIZE')

def test_scope_cannot_authorize_other_date_or_production():
    t=e._scope.set((object(),'P2',lambda:None,DAYS[0]))
    try:
        assert e.authorize(DAYS[0],'P2')==DAYS[0]
        for day in ('2025-05-19',DAYS[1],'2025-05-01'):
            with pytest.raises(PermissionError):e.authorize(day,'P2')
        for action in ('ACTUAL','FRESH_AC','PLANNING_FREEZE'):
            with pytest.raises(PermissionError):e.authorize(DAYS[0],action)
    finally:e._scope.reset(t)

def test_completed_algorithm_allocations_and_exact_order_are_unchanged():
    assert DAYS==('2025-05-17','2025-05-10','2025-05-12')
    assert POLICY['control_allocation_seconds']==MAY19['control_allocation_seconds']
    assert POLICY['case_allocation_seconds']==MAY19['case_allocation_seconds']
    assert POLICY['Threads']==MAY19['Threads']==1
