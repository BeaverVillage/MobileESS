"""Behavioral accounting tests with a fake solver; no native optimization."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from v42_m1_research.ledger import ResearchLedger


class FakeClock:
    def __init__(self):
        self.seconds = 0.0

    def __call__(self):
        return self.seconds

    def advance(self, seconds):
        self.seconds += seconds


class FakeModel:
    """Simulate finished and failed calls independently of requested TimeLimit."""
    def __init__(self, runtime, *, fail=None, missing=(), clock=None, wall=None):
        self.Params = SimpleNamespace(MemLimit=float('inf'), SoftMemLimit=float('inf'))
        self.Runtime = runtime
        self.Work = runtime * 2.0
        self.Status = 9 if fail else 2
        self.SolCount = 0 if fail else 1
        self.ObjVal = 0.628
        self.ObjBound = 0.568
        self.MaxMemUsed = 2.0
        self.fail = fail
        self.optimize_calls = 0
        self.clock = clock
        self.wall = runtime if wall is None else wall
        for name in missing:
            delattr(self, name)

    def optimize(self, *args):
        self.optimize_calls += 1
        if self.clock:
            self.clock.advance(self.wall)
        if self.fail:
            raise self.fail


def ledger(tmp_path, *, clock=None):
    assert tmp_path.resolve().drive.upper() == 'D:', 'TEST_TEMP_MUST_BE_D_DRIVE'
    return ResearchLedger(tmp_path / 'runtime_ledger.json', 'same_scientific_case',
                          clock=clock or FakeClock())


def persisted(account):
    return json.loads(account.path.read_text(encoding='utf-8'))


def test_default_allocation_and_two_track_cumulative_runtime(tmp_path):
    account = ledger(tmp_path)
    assert account.allocation == {'LB': 3600.0, 'UB': 1800.0}
    assert account.remaining('LB') == 3600.0
    assert account.remaining('UB') == 1800.0
    for track, runtime in [('LB', 600.0), ('UB', 120.0), ('LB', 200.0)]:
        model = FakeModel(runtime)
        row = account.optimize(model, track=track, label=track, requested_seconds=900)
        assert row['Native_Runtime'] == runtime
        assert model.Params.Threads == 1
        assert model.Params.MIPGap == 0.005
        assert model.Params.FeasibilityTol == 1e-8
        assert model.Params.OptimalityTol == 1e-8
        assert model.Params.IntFeasTol == 1e-8
        assert model.optimize_calls == 1
    receipt = persisted(account)
    assert receipt['Native_Runtime_sum'] == 920.0
    assert receipt['track_Runtime'] == {'LB': 800.0, 'UB': 120.0}
    assert receipt['Native_Work_sum'] == 1840.0
    assert account.remaining('LB') == 2800.0
    assert account.remaining('UB') == 1680.0
    assert receipt['inflight'] is None


def test_requested_time_is_clipped_to_actual_remaining_allocation(tmp_path):
    account = ledger(tmp_path)
    first = FakeModel(1750.0)
    account.optimize(first, track='UB', label='first', requested_seconds=1800)
    last = FakeModel(50.0)
    row = account.optimize(last, track='UB', label='last', requested_seconds=1000)
    assert last.Params.TimeLimit == row['allocated_native_seconds'] == 50.0
    assert account.used('UB') == 1800.0
    denied = FakeModel(1.0)
    with pytest.raises(TimeoutError):
        account.optimize(denied, track='UB', label='no_budget', requested_seconds=1)
    assert denied.optimize_calls == 0
    assert len(account.calls) == 2


def test_combined_5400_cap_remains_after_all_unused_budget_transferred(tmp_path):
    account = ledger(tmp_path)
    account.transfer('UB', 'LB', 1800.0)
    assert account.allocation == {'LB': 5400.0, 'UB': 0.0}
    account.optimize(FakeModel(5390.0), track='LB', label='full_track', requested_seconds=5400)
    last = FakeModel(10.0)
    account.optimize(last, track='LB', label='remaining', requested_seconds=100)
    assert last.Params.TimeLimit == 10.0
    assert account.used() == 5400.0
    assert persisted(account)['Native_Runtime_sum'] == 5400.0
    for track in ('LB', 'UB'):
        denied = FakeModel(1.0)
        with pytest.raises(TimeoutError):
            account.optimize(denied, track=track, label='exhausted', requested_seconds=1)
        assert denied.optimize_calls == 0


def test_unused_transfer_moves_future_budget_only_and_preserves_total(tmp_path):
    account = ledger(tmp_path)
    account.optimize(FakeModel(300.0), track='UB', label='used', requested_seconds=300)
    account.transfer('UB', 'LB', 1200.0)
    assert account.allocation == {'LB': 4800.0, 'UB': 600.0}
    assert sum(account.allocation.values()) == 5400.0
    assert account.remaining('UB') == 300.0
    assert account.remaining('LB') == 4800.0
    assert account.used() == 300.0
    assert account.transfers[0]['source_used_before'] == 300.0
    with pytest.raises(ValueError):
        account.transfer('UB', 'LB', 301.0)
    assert len(account.transfers) == 1


def test_transfer_cannot_retroactively_erase_track_overshoot(tmp_path):
    account = ledger(tmp_path)
    with pytest.raises(RuntimeError, match='LIMIT_EXCEEDED'):
        account.optimize(FakeModel(3601.0), track='LB', label='native_overshoot', requested_seconds=3600)
    assert account.used('LB') == 3601.0
    before = dict(account.allocation)
    with pytest.raises((ValueError, RuntimeError)):
        account.transfer('UB', 'LB', 100.0)
    assert account.allocation == before
    assert account.used('LB') == 3601.0


@pytest.mark.parametrize('bad', [-1.0, 0.0, float('nan'), float('inf')])
def test_invalid_transfer_never_changes_accounting(tmp_path, bad):
    account = ledger(tmp_path)
    with pytest.raises(ValueError):
        account.transfer('LB', 'UB', bad)
    assert account.allocation == {'LB': 3600.0, 'UB': 1800.0}
    assert account.transfers == []


def test_failed_native_call_is_charged_and_original_error_preserved(tmp_path):
    account = ledger(tmp_path)
    model = FakeModel(17.125, fail=RuntimeError('solver_failed_after_work'))
    with pytest.raises(RuntimeError, match='solver_failed_after_work'):
        account.optimize(model, track='LB', label='failure', requested_seconds=90)
    receipt = persisted(account)
    assert model.optimize_calls == 1
    assert receipt['Native_Runtime_sum'] == 17.125
    assert receipt['track_Runtime']['LB'] == 17.125
    assert receipt['calls'][0]['state'] == 'FAILED'
    assert 'solver_failed_after_work' in receipt['calls'][0]['error']
    assert receipt['inflight'] is None


@pytest.mark.parametrize('attribute', ['MaxMemUsed', 'ObjBound'])
def test_missing_optional_diagnostic_cannot_lose_finished_runtime(tmp_path, attribute):
    account = ledger(tmp_path)
    model = FakeModel(4.0, missing=(attribute,))
    account.optimize(model, track='UB', label='missing_optional', requested_seconds=30)
    receipt = persisted(account)
    assert receipt['Native_Runtime_sum'] == 4.0
    assert len(receipt['calls']) == 1
    assert receipt['calls'][0]['state'] == 'FINISHED'
    assert receipt['inflight'] is None


def test_failed_call_with_missing_optional_attributes_still_charged(tmp_path):
    account = ledger(tmp_path)
    model = FakeModel(8.0, fail=RuntimeError('original_solver_error'),
                      missing=('MaxMemUsed', 'ObjBound'))
    with pytest.raises(RuntimeError, match='original_solver_error'):
        account.optimize(model, track='LB', label='failed_optional', requested_seconds=30)
    receipt = persisted(account)
    assert receipt['Native_Runtime_sum'] == 8.0
    assert receipt['calls'][0]['state'] == 'FAILED'
    assert receipt['inflight'] is None


@pytest.mark.parametrize('attribute', ['MemLimit', 'SoftMemLimit'])
def test_preexisting_finite_memory_limit_rejected_before_optimize(tmp_path, attribute):
    account = ledger(tmp_path)
    model = FakeModel(10.0)
    setattr(model.Params, attribute, 2.0)
    with pytest.raises(ValueError, match='FINITE_MEMORY_LIMIT_FORBIDDEN'):
        account.optimize(model, track='UB', label='memory_invalid', requested_seconds=30)
    assert model.optimize_calls == 0
    assert account.used() == 0.0
    assert persisted(account)['inflight'] is None


def test_build_and_validation_wall_costs_do_not_consume_native_budget(tmp_path):
    clock = FakeClock()
    account = ledger(tmp_path, clock=clock)
    with account.cost('build', 'full_case', track='LB'):
        clock.advance(12.0)
    with pytest.raises(ValueError, match='checker_failure'):
        with account.cost('replay', 'integer_checker', track='UB'):
            clock.advance(8.0)
            raise ValueError('checker_failure')
    model = FakeModel(4.0, clock=clock, wall=6.0)
    row = account.optimize(model, track='UB', label='recourse', requested_seconds=30)
    receipt = persisted(account)
    assert receipt['Native_Runtime_sum'] == 4.0
    assert [c['wall_seconds'] for c in receipt['non_native_wall_costs']] == [12.0, 8.0]
    assert row['optimize_wall_seconds'] == 6.0
    assert receipt['wall_seconds'] == 26.0
    assert account.remaining('LB') == 3600.0
    assert account.remaining('UB') == 1796.0


def test_wall_practicality_failure_does_not_rewrite_native_budget(tmp_path):
    clock = FakeClock()
    account = ledger(tmp_path, clock=clock)
    with account.cost('certificate', 'large_exact_checker'):
        clock.advance(5401.0)
    receipt = persisted(account)
    assert receipt['practical_wall_PASS'] is False
    assert receipt['Native_Runtime_sum'] == 0.0
    assert account.remaining('LB') == 3600.0
    assert account.remaining('UB') == 1800.0


def test_existing_ledger_cannot_be_reset_or_overwritten(tmp_path):
    account = ledger(tmp_path)
    before = account.path.read_bytes()
    with pytest.raises(ValueError, match='NEW_LEDGER_REQUIRED'):
        ResearchLedger(account.path, 'different_case')
    assert account.path.read_bytes() == before


def test_ledger_path_outside_D_v42_rejected_without_write():
    target = Path('C:/V42_TEST_SHOULD_NOT_BE_CREATED/runtime_ledger.json')
    assert not target.exists()
    with pytest.raises(ValueError, match='D_V42_LEDGER_REQUIRED'):
        ResearchLedger(target, 'same_scientific_case')
    assert not target.exists()


def test_exact_point_transport_uses_alias_dependencies_without_rounding():
    from scipy import sparse
    import numpy as np
    from v42_m1_research.case import ResearchCase
    case = ResearchCase(sparse.csr_matrix((1, 2)), {}, sparse.csr_matrix((1, 3)), {},
                        np.array([1., 0.]), (), 'synthetic', {'C1_columns': 3},
                        np.array([0, 2]), [{'column': 1, 'constant': 2., 'terms': {'0': 1.}}])
    assert np.array_equal(case.lift(np.array([1., 0.])), [1., 3., 0.])
    # An invalid fractional candidate must remain fractional for independent
    # replay to reject it; transport may not repair it into an integer plan.
    assert np.array_equal(case.lift(np.array([0.25, 0.75])), [0.25, 2.25, 0.75])
    with pytest.raises(ValueError, match='POINT_AXIS_DRIFT'):
        case.lift(np.zeros(3))


def test_point_transport_rejects_unproved_or_cyclic_alias_mapping():
    from scipy import sparse
    import numpy as np
    from v42_m1_research.case import ResearchCase
    arguments = (sparse.csr_matrix((1, 2)), {}, sparse.csr_matrix((1, 3)), {},
                 np.array([1., 0.]), (), 'synthetic', {'C1_columns': 3}, np.array([0, 2]))
    for alias in ({'column': 1, 'constant': 0., 'terms': {'1': 1.}},
                  {'column': 1, 'constant': 0., 'terms': {'0': 2.}}):
        case = ResearchCase(*arguments, [alias])
        with pytest.raises(ValueError, match='UNPROVEN_C1_ALIAS'):
            case.lift(np.array([1., 0.]))
    duplicate = ResearchCase(*arguments, [{'column': 0, 'constant': 0., 'terms': {}}])
    with pytest.raises(ValueError, match='DUPLICATE_C1_ALIAS'):
        duplicate.lift(np.array([1., 0.]))
