"""New pilot bookkeeping, using fake models only (Native optimize=0)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from v42_m1_hybrid import ledger as module


class Clock:
    def __init__(self): self.value = 0.
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class Model:
    def __init__(self, runtime, *, clock=None, wall=None, failure=None, missing=()):
        self.Params = SimpleNamespace(MemLimit=float('inf'), SoftMemLimit=float('inf'))
        self.Runtime = runtime
        self.Work = 0. if runtime is None else runtime
        self.Status = 9 if failure else 2
        self.SolCount = 0 if failure else 1
        self.ObjVal = .60
        self.ObjBound = .57
        self.MaxMemUsed = .1
        self.clock, self.wall, self.failure = clock, wall, failure
        self.optimize_calls = 0
        for name in missing: delattr(self, name)

    def optimize(self, callback):
        self.optimize_calls += 1
        if self.clock: self.clock.advance(self.wall or 0.)
        callback(self, module.gp.GRB.Callback.PRESOLVE)
        if self.failure: raise self.failure


def make_account(tmp_path, monkeypatch, clock=None):
    assert tmp_path.resolve().drive.upper() == 'D:'
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    return module.HybridLedger(tmp_path/'runtime/v42_m1_fast_hybrid/current/ledger.json',
                               'same_scientific_case', clock=clock or Clock())


def receipt(account):
    return json.loads(account.path.read_text(encoding='utf-8'))


def test_new_2700_pilot_and_tracks_preserve_old_5400_ceiling(tmp_path, monkeypatch):
    account = make_account(tmp_path, monkeypatch)
    assert module.ALLOCATIONS == {'UB': 1350., 'PRICING': 1200., 'RMP': 150.}
    for track, seconds in module.ALLOCATIONS.items():
        account.optimize(Model(seconds), track=track, label='full', requested_seconds=5000)
    data = receipt(account)
    assert data['Native_Runtime_sum'] == 2700.
    assert data['track_Runtime'] == module.ALLOCATIONS
    assert data['pilot_native_limit_seconds'] == 2700.
    assert data['original_M1_native_ceiling_seconds'] == 5400.
    assert data['budget_transfers'] == []
    for track in module.ALLOCATIONS:
        denied = Model(1.)
        with pytest.raises(TimeoutError, match='EXHAUSTED'):
            account.optimize(denied, track=track, label='denied', requested_seconds=1.)
        assert denied.optimize_calls == 0


def test_track_is_not_backfilled_from_other_unused_tracks(tmp_path, monkeypatch):
    account = make_account(tmp_path, monkeypatch)
    account.optimize(Model(149.), track='RMP', label='used', requested_seconds=150.)
    last = Model(1.)
    account.optimize(last, track='RMP', label='remaining', requested_seconds=1000.)
    assert last.Params.TimeLimit == 1.
    assert account.remaining('UB') == 1350.
    assert account.remaining('PRICING') == 1200.
    with pytest.raises(TimeoutError):
        account.optimize(Model(1.), track='RMP', label='no_transfer', requested_seconds=1.)
    assert receipt(account)['Native_Runtime_sum'] == 150.


def test_known_runtime_overshoot_is_preserved_and_quarantined(tmp_path, monkeypatch):
    account = make_account(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match='ACCOUNTING_QUARANTINED'):
        account.optimize(Model(151.), track='RMP', label='overshoot', requested_seconds=150.)
    assert account.used('RMP') == 151.
    assert receipt(account)['calls'][0]['Native_Runtime'] == 151.
    next_model = Model(1.)
    with pytest.raises(RuntimeError, match='ACCOUNTING_QUARANTINED'):
        account.optimize(next_model, track='UB', label='blocked', requested_seconds=1.)
    assert next_model.optimize_calls == 0


def test_failed_call_charged_build_validation_wall_are_separate(tmp_path, monkeypatch):
    clock = Clock(); account = make_account(tmp_path, monkeypatch, clock)
    with account.cost('model_build', 'build', track='UB'): clock.advance(12.)
    with pytest.raises(ValueError, match='validation_failed'):
        with account.cost('validation', 'failed_replay', track='UB'):
            clock.advance(8.)
            raise ValueError('validation_failed')
    failed = Model(17.125, clock=clock, wall=20., failure=RuntimeError('native_failure'))
    with pytest.raises(RuntimeError, match='native_failure'):
        account.optimize(failed, track='UB', label='failed', requested_seconds=30.)
    data = receipt(account)
    assert data['Native_Runtime_sum'] == 17.125
    assert data['calls'][0]['optimize_wall_seconds'] == 20.
    assert data['calls'][0]['state'] == 'FAILED'
    assert data['calls'][0]['measured_Native_Runtime'] == 17.125
    assert [c['wall_seconds'] for c in data['non_native_wall_costs']] == [12., 8.]
    assert data['wall_seconds'] == 40.
    assert data['inflight'] is None


@pytest.mark.parametrize('runtime', [None, -1., float('nan')])
def test_unknown_runtime_charges_allocated_reservation_and_blocks_next_call(tmp_path, monkeypatch, runtime):
    account = make_account(tmp_path, monkeypatch)
    unknown = Model(runtime); unknown.Work = 0.
    with pytest.raises(RuntimeError, match='UNKNOWN_RUNTIME_QUARANTINED'):
        account.optimize(unknown, track='PRICING', label='unknown', requested_seconds=90.)
    data = receipt(account)
    assert data['Native_Runtime_sum'] == 90.
    assert data['measured_Runtime_complete'] is False
    assert data['calls'][0]['measured_Native_Runtime'] is None
    assert data['calls'][0]['runtime_unavailable'] is True
    denied = Model(1.)
    with pytest.raises(RuntimeError, match='UNKNOWN_RUNTIME_QUARANTINED'):
        account.optimize(denied, track='UB', label='no_unknown_backfill', requested_seconds=1.)
    assert denied.optimize_calls == 0


def test_failure_without_runtime_preserves_error_then_quarantines(tmp_path, monkeypatch):
    account = make_account(tmp_path, monkeypatch)
    failed = Model(None, failure=RuntimeError('original_failure'))
    with pytest.raises(RuntimeError, match='original_failure'):
        account.optimize(failed, track='PRICING', label='failed_unknown', requested_seconds=60.)
    assert receipt(account)['Native_Runtime_sum'] == 60.
    assert receipt(account)['calls'][0]['runtime_unavailable'] is True
    with pytest.raises(RuntimeError, match='UNKNOWN_RUNTIME_QUARANTINED'): account.check()


@pytest.mark.parametrize('attribute', ['MaxMemUsed', 'ObjBound'])
def test_optional_diagnostic_failure_does_not_lose_accounting(tmp_path, monkeypatch, attribute):
    account = make_account(tmp_path, monkeypatch)
    account.optimize(Model(4., missing=(attribute,)), track='RMP', label='optional', requested_seconds=30.)
    assert receipt(account)['Native_Runtime_sum'] == 4.
    assert receipt(account)['inflight'] is None


@pytest.mark.parametrize('attribute', ['MemLimit', 'SoftMemLimit'])
def test_finite_memory_limit_rejected_before_fake_optimize(tmp_path, monkeypatch, attribute):
    account = make_account(tmp_path, monkeypatch)
    model = Model(5.); setattr(model.Params, attribute, 2.)
    with pytest.raises(ValueError, match='MEMORY_LIMIT_FORBIDDEN'):
        account.optimize(model, track='UB', label='memory', requested_seconds=30.)
    assert model.optimize_calls == 0
    assert receipt(account)['calls'] == []
    assert receipt(account)['inflight'] is None


def test_callback_scientific_params_and_global_goal_remain_distinct(tmp_path, monkeypatch):
    account = make_account(tmp_path, monkeypatch); seen = []
    def observe(model, where):
        seen.append((where, {key:getattr(model.Params, key) for key in module.PARAMETERS}))
    row = account.optimize(Model(1.), track='UB', label='callback', requested_seconds=30., callback=observe)
    assert seen[0][1] == dict(Threads=1, MIPGap=.005, FeasibilityTol=1e-8,
                              OptimalityTol=1e-8, IntFeasTol=1e-8)
    data = receipt(account)
    assert row['presolve_included_in_Native_Runtime'] is True
    assert row['presolve_callback_span_is_not_exact_presolve_runtime'] is True
    assert data['independent_global_gap_goal'] == .05
    assert data['A1_A2_gap_preserved'] == .005
    assert data['inner_solver_gap_is_not_global_acceptance'] is True
    assert data['parameters']['MIPGap'] == .005


def test_existing_new_ledger_cannot_reset_and_historical_file_stays_exact(tmp_path, monkeypatch):
    historical = tmp_path/'historical_ledger.json'
    historical.write_bytes(b'{"Native_Runtime_sum":3805.322,"immutable":true}\n')
    old_bytes = historical.read_bytes()
    account = make_account(tmp_path, monkeypatch)
    account.optimize(Model(8.), track='UB', label='own_new_call', requested_seconds=30.)
    new_bytes = account.path.read_bytes()
    with pytest.raises(ValueError, match='NO_COMPLETED_LEDGER_REUSE_OR_RESET'):
        module.HybridLedger(account.path, 'other_case')
    assert account.path.read_bytes() == new_bytes
    assert historical.read_bytes() == old_bytes
    with pytest.raises(ValueError, match='NEW_D_HYBRID_LEDGER_REQUIRED'):
        module.HybridLedger(historical, 'same_scientific_case')
    assert historical.read_bytes() == old_bytes


def test_c_path_and_nonpilot_path_rejected_without_write(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    for path in (Path('C:/V42_NEVER_CREATE/hybrid_ledger.json'), tmp_path/'wrong.json'):
        with pytest.raises(ValueError, match='NEW_D_HYBRID_LEDGER_REQUIRED'):
            module.HybridLedger(path, 'same_scientific_case')
        assert not path.exists()


def test_wall_practicality_failure_does_not_consume_or_reset_native_budget(tmp_path, monkeypatch):
    clock = Clock(); account = make_account(tmp_path, monkeypatch, clock)
    with account.cost('certificate', 'slow_independent_check'): clock.advance(5401.)
    data = receipt(account)
    assert data['wall_60_minutes_PASS'] is False
    assert data['wall_90_minutes_PASS'] is False
    assert data['Native_Runtime_sum'] == 0.
    assert data['track_Runtime'] == dict.fromkeys(module.ALLOCATIONS, 0.)


def test_enclosing_cost_separates_native_wall_and_exposes_nested_overlap(tmp_path, monkeypatch):
    clock = Clock(); account = make_account(tmp_path, monkeypatch, clock)
    with account.cost('trajectory_pricing_and_certificates', 'inclusive_parent', track='PRICING'):
        clock.advance(10.)
        with account.cost('pricing_model_and_certificate', 'inclusive_child', track='PRICING'):
            account.optimize(Model(17., clock=clock, wall=20.), track='PRICING',
                             label='fake_nested_native', requested_seconds=30.)
            clock.advance(2.)
        clock.advance(8.)
    data = receipt(account)
    child, parent = data['non_native_wall_costs']
    assert data['Native_Runtime_sum'] == 17.
    assert data['calls'][0]['optimize_wall_seconds'] == 20.
    assert child['wall_seconds'] == 22.
    assert child['nested_native_optimize_wall_seconds'] == 20.
    assert child['exclusive_non_native_wall_seconds'] == 2.
    assert parent['wall_seconds'] == 40.
    assert parent['nested_native_optimize_wall_seconds'] == 20.
    assert parent['exclusive_non_native_wall_seconds'] == 20.
    assert parent['enclosing_cost_records_may_overlap'] is True
    assert child['enclosing_cost_records_may_overlap'] is True
    # Nested exclusive figures are itemized diagnostics, not an additive total.
    assert data['wall_seconds'] == 40.
