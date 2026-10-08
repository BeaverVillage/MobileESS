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

def test_reviewed_postprocessor_versions_and_source_drift(tmp_path,monkeypatch):
    import v42_may12_rescue.native as native
    from v42_pr134_b1.common import atomic,record
    root=tmp_path/'repo';source=root/'v42_b2_root_validation/analysis.py'
    source.parent.mkdir(parents=True);source.write_text('old reviewed version')
    out=tmp_path/'reports';monkeypatch.setattr(native,'OUT',out)
    old=record(source)
    atomic(out/'PRE_PRICING_START_GATE_FAILURE2/READ_ONLY_M1_ANALYSIS_IDENTITY.json',
        dict(source=old,optimize_forbidden_by_entrypoint=True))
    process=dict(argv=['python','-u','-m','v42_b2_root_validation.analysis'],cwd=str(root))
    assert native.is_read_only_host_monitor(process)
    source.write_text('new reviewed version')
    assert not native.is_read_only_host_monitor(process)
    atomic(out/'PRE_PRICING_START_GATE_FAILURE3/READ_ONLY_M1_ANALYSIS_IDENTITY.json',
        dict(source=record(source),optimize_forbidden_by_entrypoint=True))
    assert native.is_read_only_host_monitor(process)
    process['cwd']=str(tmp_path/'another_repo')
    assert not native.is_read_only_host_monitor(process)

def test_git_receipt_requires_reviewed_script_dependency_and_cwd(tmp_path,monkeypatch):
    import v42_may12_rescue.native as native
    from v42_pr134_b1.common import atomic,record
    script=tmp_path/'tmp/final_git_receipt.py';script.parent.mkdir()
    dependency=tmp_path/'repo/package.py';dependency.parent.mkdir()
    script.write_text('reviewed git receipt');dependency.write_text('reviewed optimize-forbidden audit')
    out=tmp_path/'reports';monkeypatch.setattr(native,'OUT',out)
    atomic(out/'PRE_PRICING_START_GATE_FAILURE4/READ_ONLY_GIT_RECEIPT_IDENTITY.json',
        dict(source=record(script),dependency=record(dependency),script_argument=str(script),
            dependency_forbids_optimize=True,cwd=str(dependency.parent)))
    process=dict(argv=['python',str(script)],cwd=str(dependency.parent))
    assert native.is_read_only_host_monitor(process)
    dependency.write_text('unreviewed new audit')
    assert not native.is_read_only_host_monitor(process)
