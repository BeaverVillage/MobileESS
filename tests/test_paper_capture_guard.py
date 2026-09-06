from types import SimpleNamespace
import pytest


def fake():
    return SimpleNamespace(Params=SimpleNamespace(),ModelName="observer_probe",Status=2,Work=0.,Runtime=0.,SolCount=1)


def test_observer_preserves_outer_no_optimization_guard(tmp_path,monkeypatch):
    import gurobipy as gp
    from dayahead.paper_analysis.live import capture
    calls=[]
    def forbid(*a,**k):
        calls.append(1);raise RuntimeError("GUARDED")
    monkeypatch.setattr(gp.Model,"optimize",forbid)
    with pytest.raises(RuntimeError,match="GUARDED"):
        with capture(tmp_path):gp.Model.optimize(fake())
    assert calls==[1] and gp.Model.optimize is forbid


def test_nested_original_solver_observer_does_not_recurse(tmp_path,monkeypatch):
    import gurobipy as gp
    from dayahead.v40a import observability
    from dayahead.paper_analysis.live import capture
    calls=[]
    def original(*a,**k):calls.append(1);return "result"
    monkeypatch.setattr(observability,"_original",original)
    monkeypatch.setattr(gp.Model,"optimize",observability.counted_optimize)
    with capture(tmp_path):assert gp.Model.optimize(fake())=="result"
    assert calls==[1] and gp.Model.optimize is observability.counted_optimize
