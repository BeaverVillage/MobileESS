from types import SimpleNamespace
import pytest
import v42_may12_rescue.execution as e
from v42_may12_rescue.native import Budget
from v42_may12_rescue.native import is_read_only_host_monitor
from v42_a_stage_early.native import BudgetStop

def model():
    return SimpleNamespace(Params=SimpleNamespace(Threads=1,MemLimit=float('inf'),SoftMemLimit=float('inf')),NumIntVars=0)

def test_no_ambient_may12_p1_authorization():
    with pytest.raises(PermissionError):e.authorize('2025-05-12','P1')

@pytest.mark.parametrize('action',['P2','ACTUAL','FRESH_AC','PLANNING_FREEZE'])
def test_p1_only_rejects_other_actions(action):
    t=e._scope.set((model(),'ORIGINAL_P1',lambda:1))
    try:
        with pytest.raises(PermissionError):e.authorize('2025-05-12',action)
    finally:e._scope.reset(t)

def test_other_day_and_wrong_model_rejected(monkeypatch):
    m=model();t=e._scope.set((m,'ORIGINAL_P1',lambda:1));monkeypatch.setattr(e,'read',lambda p:{'PASS':True})
    try:
        with pytest.raises(PermissionError):e.authorize('2025-05-10','P1')
        with pytest.raises(PermissionError):e.guard(model(),'2025-05-12')
        e.guard(m,'2025-05-12')
    finally:e._scope.reset(t)

def test_finite_memory_and_wrong_threads_rejected(monkeypatch):
    m=model();t=e._scope.set((m,'ORIGINAL_P1',lambda:1));monkeypatch.setattr(e,'read',lambda p:{'PASS':True})
    try:
        m.Params.MemLimit=4
        with pytest.raises(PermissionError):e.guard(m,'2025-05-12')
        m.Params.MemLimit=float('inf');m.Params.Threads=2
        with pytest.raises(PermissionError):e.guard(m,'2025-05-12')
    finally:e._scope.reset(t)

def test_old_cost_is_not_new_budget_charge(monkeypatch):
    b=Budget();b.used=123;b.native=SimpleNamespace(live_model=SimpleNamespace(Runtime=7))
    assert b.remaining()==3470
    b.call_start=123;b.call_cap=60;assert b.remaining()==53
    b.native.live_model.Runtime=61
    with pytest.raises(BudgetStop):b.remaining()

def test_actual_monitor_command_is_not_native_worker():
    p={'argv':['python.exe','-X','utf8','-m','v42_pr134_b1.host','monitor','C:/v42_pr134_sc_execution_20261007']}
    assert is_read_only_host_monitor(p)
    p['argv'][5]='run';assert not is_read_only_host_monitor(p)
    p['argv'][4]='v42_may12_rescue.runner';p['argv'][5]='monitor';assert not is_read_only_host_monitor(p)
