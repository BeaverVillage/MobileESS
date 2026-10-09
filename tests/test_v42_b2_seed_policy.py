"""Future B2 stopping/replay/diagnostic contracts; no real optimize is called."""
from contextlib import nullcontext
from fractions import Fraction
from types import SimpleNamespace
import inspect
import json

import gurobipy as gp
import numpy as np
import pytest
from scipy import sparse

from v42_b2_seed_recovery_v17 import budget as b, execution, seed_policy as seed, native_diagnostics as diag
from v42_may_campaign_native90 import m_stage as original


class Clock:
    value = 0.
    def __call__(self):
        return self.value


class Model:
    def __init__(self, clock, runtime=900., solcount=0):
        self.clock, self.Runtime = clock, runtime
        self.Params = SimpleNamespace(MIPGap=.005)
        self.SolCount, self.Status, self.Work = solcount, 9, 1.
        self.ObjVal, self.ObjBound, self.MIPGap, self.NodeCount = 1., .9, .1, 0.
        self.calls, self.disposed, self.events = 0, False, []
    def setParam(self, key, value):
        setattr(self.Params, key, value)
    def optimize(self, callback):
        self.calls += 1
        for where, values in self.events:
            self.callback_values = values
            callback(self, where)
            self.clock.value += 2
        self.clock.value += self.Runtime or 0
    def cbGet(self, key):
        return self.callback_values[key]
    def terminate(self):
        self.terminated = True
    def dispose(self):
        self.disposed = True
    def getAttr(self, key):
        assert key == 'X'
        return self.point.copy()


@pytest.fixture
def ports(monkeypatch):
    context = dict(request=dict(arm='B2', day='2025-05-01'))
    monkeypatch.setattr(execution, 'current', lambda: context)
    monkeypatch.setattr(b, 'native_scope', lambda *a: nullcontext())
    monkeypatch.setattr(b, 'guard', lambda *a: None)
    return context


@pytest.mark.parametrize('requested,spent,expected', [(900.,0.,900.), (900.,5000.,400.),
    (120.,900.,120.), (None,900.,4500.)])
def test_b2_limits_each_call_and_charges_actual_runtime(tmp_path, ports, requested, spent, expected):
    clock = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=clock)
    if spent:
        budget.charge(spent)
    model = Model(clock, expected + .25)
    if spent + expected + .25 > 5400:
        with pytest.raises(b.BudgetStop):
            budget.native_optimize(model, requested_seconds=requested, track='M_SEED')
    else:
        budget.native_optimize(model, requested_seconds=requested, track='M_SEED')
    assert model.Params.TimeLimit == expected
    assert budget.used() == spent + expected + .25  # termination overhead is charged.
    assert budget.calls[-1]['requested_seconds'] == requested
    assert budget.calls[-1]['effective_TimeLimit'] == expected
    assert budget.remaining() == max(0., 5400 - budget.used())


@pytest.mark.parametrize('requested', [0., -1., float('inf'), float('nan'), True])
def test_invalid_request_rejected_before_native(tmp_path, ports, requested):
    clock = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=clock)
    model = Model(clock)
    with pytest.raises(ValueError, match='REQUESTED_SECONDS'):
        budget.native_optimize(model, requested_seconds=requested)
    assert model.calls == 0 and budget.used() == 0


def test_b1_stopping_policy_is_unchanged(tmp_path, ports):
    ports['request']['arm'] = 'B1'
    clock = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=clock)
    model = Model(clock, 1.)
    budget.native_optimize(model, requested_seconds=900.)
    assert model.Params.TimeLimit == 5400. and model.Params.MIPGap == .005


def test_unknown_runtime_is_quarantined_and_never_reset(tmp_path, ports):
    clock = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=clock)
    with pytest.raises(RuntimeError, match='QUARANTINE'):
        budget.native_optimize(Model(clock, None), requested_seconds=900.)
    with pytest.raises(RuntimeError, match='QUARANTINE'):
        budget.native_optimize(Model(clock), requested_seconds=900.)
    with pytest.raises(PermissionError, match='NEW_DATE_LEDGER'):
        b.DateBudget(budget.path)


def test_denied_entry_does_not_charge_stale_reused_model(tmp_path, ports, monkeypatch):
    clock = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=clock)
    def deny(model):
        raise PermissionError('denied')
    monkeypatch.setattr(b, 'guard', deny)
    model = Model(clock, 900., 1)
    with pytest.raises(PermissionError):
        budget.native_optimize(model, requested_seconds=900.)
    assert model.calls == 0 and budget.used() == 0 and not budget.calls


def test_native_metrics_never_become_certified_bounds(tmp_path, ports):
    clock = Clock(); updates = []
    budget = b.DateBudget(tmp_path/'ledger.json', clock=clock, progress=updates.append)
    model = Model(clock, 3., 1)
    cb = gp.GRB.Callback
    model.events = [(cb.MIP, {cb.RUNTIME:1., cb.MIP_OBJBST:1., cb.MIP_OBJBND:.98,
        cb.MIP_SOLCNT:1, cb.MIP_NODCNT:0., cb.MIP_PHASE:1, cb.MIP_ITRCNT:42., cb.MIP_NODLFT:1.})]
    budget.native_optimize(model, requested_seconds=900.)
    during = next(r for r in updates if r.get('Native_subphase') == 'MIP')
    assert during['Native_Gap'] == pytest.approx(.02)
    assert during['Native_SolCount'] == 'UNKNOWN' and during['Native_solution_count_callback'] == 1
    assert budget.calls[-1]['Native_Gap'] == .1  # actual post-return Model.MIPGap.
    assert not any({'UB','LB','global_LB','certified_gap'} & set(r) for r in updates)


def test_callback_zero_counter_does_not_claim_absent_incumbent():
    cb = gp.GRB.Callback
    values = {cb.MIPSOL_OBJBST:1., cb.MIPSOL_OBJBND:.97, cb.MIPSOL_SOLCNT:0,
              cb.MIPSOL_NODCNT:0., cb.MIPSOL_PHASE:1}
    model = SimpleNamespace(cbGet=lambda key: values[key])
    row = diag.observe(model, cb.MIPSOL, gp)
    assert row['Native_incumbent'] == 1. and row['Native_solution_count_callback'] == 0
    assert row['Native_Gap'] == pytest.approx(.03)
    assert diag.empty()['Native_SolCount'] == 'UNKNOWN'


def test_unavailable_bounds_and_root_are_unknown():
    cb = gp.GRB.Callback
    model = SimpleNamespace(cbGet=lambda key: gp.GRB.INFINITY)
    row = diag.observe(model, cb.MIP, gp)
    assert row['Native_incumbent'] == row['Native_Gap'] == 'UNKNOWN'
    assert 'Native_root_progress' not in row
    values = {cb.MIPNODE_OBJBST:1., cb.MIPNODE_OBJBND:.95, cb.MIPNODE_SOLCNT:1,
              cb.MIPNODE_NODCNT:0., cb.MIPNODE_PHASE:1}
    row = diag.observe(SimpleNamespace(cbGet=lambda key:values[key]), cb.MIPNODE, gp)
    assert row['Native_root_progress'] == 'ROOT_NODE_CALLBACK_OBSERVED'
    assert diag.relative_gap(0., 0.) == 0 and diag.relative_gap(0., 1.) == 'INFINITY'


@pytest.fixture
def seed_case(tmp_path, ports, monkeypatch):
    A = sparse.csr_matrix([[0., 1.]])
    d = dict(names=np.array(['arc[MESS01,0]', 'rho_max']), row_names=np.array(['line_thermal_face[0]']),
        lower=np.array([0.,0.]), upper=np.array([1.,1.]), types=np.array(['B','C']),
        objective=np.array([0.,1.]), constant=np.asarray(0.), rhs=np.array([.5]), sense=np.array(['>']))
    case = SimpleNamespace(A=A, d=d, original_A=A, original_d=d,
        lift=lambda x:x.copy(), case_sha='tiny_full_fixture', identity=dict(binary_count=1),
        output=tmp_path, bundle=dict(day='2025-05-01'))
    clock = Clock(); budget = b.DateBudget(tmp_path/'ledger.json', clock=clock)
    model = Model(clock, 900., 1); model.point = np.array([1.,.5])
    monkeypatch.setattr(original, '_model', lambda case, continuous=False:(model,dict(solver_parameters=dict(MIPGap=.005))))
    # Physics remains the original call site, with a controlled small-fixture verdict.
    monkeypatch.setattr('v42_m1_research.check_ub.physical_replay', lambda *a:dict(PASS=True))
    return case, budget, model


def test_b2_seed_passes_original_full_strict_replay(seed_case):
    case, budget, model = seed_case
    point, receipt = seed.seed_integer(case, budget, None)
    assert model.Params.MIPGap == .03 and model.Params.TimeLimit == 900.
    assert receipt['PASS'] and receipt['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact']
    assert receipt['original_matrix_and_96_slot_physical_replay']['original_full_matrix']['PASS']
    assert receipt['exact_Global_UB'] == '1/2' and model.disposed
    assert np.array_equal(point, model.point)
    assert not (case.output/'B2_SEED_FAILURE_AND_RECOVERY.json').exists()


@pytest.mark.parametrize('attack', ['no_solution','near_integer','full_row','physical'])
def test_seed_failure_is_explicit_preserves_ledger_and_never_retries(seed_case, attack, monkeypatch):
    case, budget, model = seed_case
    if attack == 'no_solution': model.SolCount = 0
    elif attack == 'near_integer': model.point[0] = 1. - 1e-10
    elif attack == 'full_row': case.original_d = dict(case.d, rhs=np.array([.75]))
    else: monkeypatch.setattr('v42_m1_research.check_ub.physical_replay', lambda *a:dict(PASS=False))
    point, receipt = seed.seed_integer(case, budget, None)
    assert point is None and not receipt['PASS'] and not receipt['automatic_retry']
    assert receipt['certified_UB'] is receipt['certified_LB'] is receipt['certified_gap'] is None
    assert model.calls == 1 and model.disposed and budget.used() == 900.
    assert receipt['remaining_Native_seconds'] == 4500.
    saved = json.loads((case.output/'B2_SEED_FAILURE_AND_RECOVERY.json').read_text(encoding='utf-8'))
    assert saved['native_ledger']['sha256'] and not saved['runtime_reset_allowed']


def test_seed_override_is_scoped_and_final_exact_gate_is_preserved(seed_case):
    case, budget, model = seed_case
    seed.seed_integer(case, budget, None)
    assert original._seed_integer.__globals__['_model'] is original._model
    assert seed.seed_integer.__globals__['original'] is original
    assert original.TARGET == Fraction(3,100)
    source = inspect.getsource(original.run)
    assert 'check_rational_dual_certificate(case.A,case.d,dual,case_sha=case.case_sha)' in source
    assert 'gap<=TARGET and deadline_ok' in source
    assert 'Native_BestBd' not in source


@pytest.mark.parametrize('dual_value,accepted,exact_gap', [('97/100',True,'3/100'), ('0',False,'1')])
def test_actual_b2_run_decides_from_exact_certificate_even_with_tiny_native_gap(
        seed_case, monkeypatch, dual_value, accepted, exact_gap):
    from v42_b2_seed_recovery_v17 import m_stage
    from v42_m1_research.check_lb import check_rational_dual_certificate
    from v42_b2_seed_recovery_v17.common import atomic
    case, budget, model = seed_case
    case.point = None; case.planning = {}; case.identity['transport'] = dict(PASS=True)
    model.MIPGap = .001; model.ObjBound = .4995
    monkeypatch.setattr(m_stage, 'prepare', lambda *a:case)
    monkeypatch.setattr('v42_m1_hybrid.blocks.build_blocks', lambda c:SimpleNamespace(units=()))
    monkeypatch.setattr('v42_m1_hybrid.verify.verify_decomposition', lambda *a:None)
    def initial_exact_lb(case, budget, progress):
        dual = {} if dual_value == '0' else {'0':dual_value}
        cert = check_rational_dual_certificate(case.A,case.d,dual,case_sha=case.case_sha)
        cert['exact_Global_LB'] = cert['exact_bound']
        atomic(case.output/'INITIAL_EXACT_LB_CERTIFICATE.json',cert)
        return dual, cert
    monkeypatch.setattr(original, '_fresh_lp_dual', initial_exact_lb)
    def plan(case, point):
        atomic(case.output/'OPTIMIZED_MESS_PLAN.json',{})
        return {}
    monkeypatch.setattr(original, '_plan', plan)
    def no_extra_native(*a, **kw):
        raise TimeoutError('fixture adaptive boundary')
    monkeypatch.setattr('v42_m1_anytime.algorithms.dynamic_grid', no_extra_native)
    result = m_stage.run(dict(arm='B2',day='2025-05-01'),budget,None)
    assert result['PASS'] is accepted and result['exact_gap'] == exact_gap
    assert result['exact_Global_UB'] == '1/2'
    assert result['certificate']['strict_UB']['sha256'] and result['certificate']['exact_LB']['sha256']
    assert budget.used() == 900. and model.calls == 1
