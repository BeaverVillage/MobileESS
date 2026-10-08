from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from v42_may_campaign import budget as b, execution as e
from v42_may_campaign.common import read


class Clock:
    value = 0.
    def __call__(self): return self.value


class Model:
    def __init__(self, clock, runtime=11.):
        self.Params = SimpleNamespace(Threads=8, TimeLimit=99999, LogFile='')
        self.clock, self.Runtime = clock, runtime
        self.Work, self.Status, self.SolCount, self.ObjBound = 1., 9, 1, .5
        self.calls = 0
    def optimize(self, callback):
        self.calls += 1
        self.clock.value += self.Runtime or 0.


@pytest.fixture
def ports(monkeypatch):
    monkeypatch.setattr(b, 'native_scope', lambda *args: nullcontext())
    monkeypatch.setattr(b, 'guard', lambda model: None)


def test_wall_includes_build_and_reserves_original_certification(tmp_path, ports):
    c = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=c, final_reserve=300)
    c.value = 5070
    model = Model(c)
    budget.native_optimize(model, track='M', requested_seconds=900)
    assert model.Params.Threads == 1 and model.Params.TimeLimit == 30
    assert budget.used() == 11 and budget.wall() == 5081
    assert read(tmp_path/'ledger.json')['calls'][0]['Native_Runtime'] == 11


def test_native_cumulative_budget_and_no_second_call_at_ceiling(tmp_path, ports):
    c = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=c, native_limit=20, final_reserve=0)
    first = Model(c, 15); budget.native_optimize(first, track='A')
    second = Model(c, 5); budget.native_optimize(second, track='A')
    assert second.Params.TimeLimit == 5 and budget.used() == 20
    denied = Model(c)
    with pytest.raises(b.BudgetStop): budget.native_optimize(denied, track='A')
    assert denied.calls == 0


def test_missing_runtime_quarantines_native_budget(tmp_path, ports):
    c = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=c, final_reserve=0)
    model = Model(c, None); budget.native_optimize(model, track='M', requested_seconds=42)
    assert budget.used() == 42 and budget.calls[-1]['runtime_unavailable']
    with pytest.raises(b.BudgetStop, match='QUARANTINE'):
        budget.native_optimize(Model(c), track='M')


def test_zero_remaining_reserve_never_enters_native(tmp_path, ports):
    c = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=c)
    c.value = 5100; model = Model(c)
    with pytest.raises(b.BudgetStop): budget.native_optimize(model, track='A')
    assert model.calls == 0


def test_b2_rejects_a_track_and_p2_and_cross_day(monkeypatch):
    permit = {'request': {'arm': 'B2', 'day': '2025-05-12'}}
    token = e._active.set(permit)
    model = SimpleNamespace(Params=SimpleNamespace(Threads=1))
    try:
        with pytest.raises(PermissionError, match='P1_ONLY'): e.authorize('2025-05-12', 'P2')
        with pytest.raises(PermissionError, match='DATE_CONFLICT'): e.authorize('2025-05-01', 'P1')
        with pytest.raises(PermissionError, match='AIDC_OPTIMIZATION'):
            with e.native_scope(model, 'P1', 'A'): e.guard(model)
        with e.native_scope(model, 'P1', 'M'): e.guard(model)
        with pytest.raises(PermissionError, match='MODEL_SCOPE'): e.guard(model)
    finally: e._active.reset(token)


def test_exception_records_measured_runtime_once(tmp_path, ports):
    c = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=c)
    class Broken(Model):
        def optimize(self, callback): raise RuntimeError('input mismatch')
    with pytest.raises(RuntimeError): budget.native_optimize(Broken(c, 7), track='A')
    assert budget.used() == 7 and len(budget.calls) == 1
    assert budget.calls[0]['status'] == 'FAILED'
