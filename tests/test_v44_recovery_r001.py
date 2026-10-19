"""Native0 regressions for nonfinite bound telemetry and budget settlement."""
from contextlib import nullcontext
from types import SimpleNamespace
import json
import math
import pytest
from v44_recovery_r001.finite_bound import finite, nonfinite, adapted


@pytest.mark.parametrize('bound', [-math.inf, math.inf, math.nan, None, .37])
def test_diagnostic_is_json_safe_without_certifying_bound(bound):
    result = dict(Native_BestBd=finite(bound), Native_BestBd_nonfinite=nonfinite(bound))
    json.dumps(result, allow_nan=False)
    if bound is not None and not math.isfinite(bound):
        assert result['Native_BestBd'] is None
        assert result['Native_BestBd_nonfinite'] is not None
    else:
        assert result['Native_BestBd'] == bound
        assert result['Native_BestBd_nonfinite'] is None


def test_finished_native_runtime_persists_despite_unavailable_bound(monkeypatch, tmp_path):
    from v42_may_campaign_native90 import budget as module
    from v44.common import atomic, read
    monkeypatch.setattr(module, 'd_path', lambda p: p)
    monkeypatch.setattr(module, 'atomic', atomic)
    monkeypatch.setattr(module, 'native_scope', lambda *a: nullcontext())
    monkeypatch.setattr(module, 'guard', lambda m: None)
    observed = []
    ledger = module.DateBudget(tmp_path/'LEDGER.json', native_limit=900., progress=observed.append)
    method = adapted(module.DateBudget.native_optimize, "Native_BestBd=attr('ObjBound'),",
        "Native_BestBd=_finite_diagnostic(attr('ObjBound')), "
        "Native_BestBd_nonfinite=_nonfinite_diagnostic(attr('ObjBound')),")
    model = SimpleNamespace(Params=SimpleNamespace(), Runtime=6.461, Work=13.73,
        Status=9, SolCount=2, ObjBound=-math.inf, optimize=lambda callback: None)
    method(ledger, model, requested_seconds=5.956)
    saved = read(ledger.path)
    assert saved['inflight'] is None
    assert saved['measured_Native_Runtime'] == 6.461
    assert saved['calls'][0]['Native_BestBd'] is None
    assert saved['calls'][0]['Native_BestBd_nonfinite'] == '-inf'
    assert saved['calls'][0]['SolCount'] == 2
    assert ledger.remaining() == 900.-6.461
    assert observed[-1]['Native_BestBd'] is None


def test_install_retains_solver_parameters_and_restores_functions():
    from v44_recovery_r001.finite_bound import install
    from v44.frozen.v43_mess.library import load
    from v42_may_campaign_native90.budget import DateBudget
    modules = load(); engine = modules['m_engine']; adaptive = modules['m_adaptive']
    prior = (DateBudget.native_optimize, engine._native_joint, adaptive._native_joint)
    parameters = dict(engine.APPROVED_JOINT_PARAMETERS)
    with install():
        assert DateBudget.native_optimize is not prior[0]
        assert engine._native_joint is adaptive._native_joint
        assert parameters == engine.APPROVED_JOINT_PARAMETERS
    assert prior == (DateBudget.native_optimize, engine._native_joint, adaptive._native_joint)
