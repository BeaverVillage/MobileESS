"""Shared policy attacks plus a real bounded Native identity/replay trial."""
from contextlib import nullcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest
from scipy import sparse

from v42_common_mess import VERSION
from v42_common_mess.budget import StageBudget, NativeBudgetExhausted
from v42_common_mess.fixed_pattern import values_for, stationary_paths
from v42_common_mess.neighborhood import select, route_witness
from v42_common_mess.storage import jsonable


class ParentBudget:
    def __init__(self, used=0., failure=False):
        self.value, self.failure, self.calls = used, failure, []
    def used(self):
        return self.value
    def remaining(self):
        return max(0., 5400. - self.value)
    def cost(self, *args, **kwargs):
        return nullcontext()
    def native_optimize(self, model, callback=None, **kwargs):
        limit = kwargs['requested_seconds']
        self.calls.append(dict(kwargs, Native_Runtime=limit + .25, runtime_unavailable=False))
        self.value += limit + .25
        if self.failure:
            raise RuntimeError('REAL_FAILED_CALL_RUNTIME_RETAINED')
        return self.calls[-1]


def test_stage_cap_includes_initialization_before_entry_and_records_overshoot():
    parent = ParentBudget(1700.)
    budget = StageBudget(parent)
    model = SimpleNamespace(Params=SimpleNamespace())
    budget.native_optimize(model, requested_seconds=900., track='M_SEED')
    assert model.Params.TimeLimit == parent.calls[-1]['requested_seconds'] == 100.
    assert budget.used() == 1800.25 and budget.remaining() == 0.
    with pytest.raises(NativeBudgetExhausted):
        budget.native_optimize(model, requested_seconds=1.)
    assert len(parent.calls) == 1


def test_failed_native_runtime_does_not_become_free_budget():
    parent = ParentBudget(10., failure=True)
    with pytest.raises(RuntimeError, match='RUNTIME_RETAINED'):
        StageBudget(parent).native_optimize(SimpleNamespace(Params=SimpleNamespace()), requested_seconds=3.)
    assert parent.used() == 13.25 and parent.calls[-1]['Native_Runtime'] == 3.25


@pytest.fixture
def route_case(tmp_path):
    from v42_native.mess import RouteArc, Battery
    routes = [RouteArc('AB', 'A', 'B', 60, 61, 61, 0., 'a' * 64),
              RouteArc('BA', 'B', 'A', 62, 63, 63, 0., 'a' * 64)]
    arcs = [(site, t, site, t + 1, None) for site in ('A', 'B') for t in range(96)]
    arcs += [(r.source, r.depart, r.destination, r.connect, r) for r in routes]
    names = [f'route_flow[U,{k}]' for k in range(len(arcs))]
    names += [f'node_activity[U,{site},{t}]' for site in ('A', 'B') for t in range(97)]
    names += [f'charge_mode[U,{t}]' for t in range(96)] + ['rho_max']
    types = np.array(['C'] * len(arcs) + ['B'] * (194 + 96) + ['C'])
    point = np.zeros(len(names)); point[:96] = 1.; point[len(arcs):len(arcs) + 97] = 1.; point[-1] = 1.
    terminal = np.zeros(len(names)); terminal[95] = terminal[191] = 1.
    A = sparse.csr_matrix([terminal])
    d = dict(names=np.asarray(names), types=types, lower=np.zeros(len(names)), upper=np.ones(len(names)),
        objective=np.r_[np.zeros(len(names) - 1), 1.], constant=np.asarray(0.),
        row_names=np.array(['terminal_location[U]']), rhs=np.array([1.]), sense=np.array(['=']))
    original_d = dict(d, names=np.array([n.replace('route_flow[', 'arc[') for n in names]),
                      types=np.r_[np.full(len(arcs), 'B'), types[len(arcs):]])
    return SimpleNamespace(A=A, d=d, original_A=A, original_d=original_d, point=point,
        lift=lambda x:x.copy(), graph=(['A', 'B'], {'U':'A'}, arcs,
            Battery(0., 100., 50., 50., 10., 10., 1., 1.), {}),
        case_sha='a' * 64, identity={'binary_count':290, 'transport':{'PASS':True}},
        output=tmp_path, bundle={'day':'2025-05-01'}, planning={})


def test_terminal_occupancy_and_continuous_FULL_route_representatives(route_case):
    ids, values = values_for(route_case, stationary_paths(route_case), lambda u, t: False)
    fixed = dict(zip(map(int, ids), values))
    names = list(route_case.d['names'])
    assert fixed[names.index('node_activity[U,A,96]')] == 1.
    assert fixed[names.index('node_activity[U,B,96]')] == 0.
    assert fixed[names.index('route_flow[U,95]')] == 1.
    assert fixed[names.index('route_flow[U,191]')] == 0.
    assert set(np.unique(values)) == {0., 1.}


def test_travel_departure_node_matches_original_outgoing_flow(route_case):
    paths = {'U': list(range(60)) + [192, 157, 193] + list(range(63, 96))}
    ids, values = values_for(route_case, paths, lambda u, t: False)
    fixed = dict(zip(map(int, ids), values)); names = list(route_case.d['names'])
    assert fixed[names.index('node_activity[U,A,60]')] == 1.
    assert fixed[names.index('node_activity[U,B,62]')] == 1.
    assert fixed[names.index('route_flow[U,192]')] == 1.
    assert fixed[names.index('node_activity[U,A,96]')] == 1.


def test_route_manifest_rejects_fully_fixed_pattern(route_case):
    assert not route_witness(route_case, route_case.point, [], 48)['PASS']


def test_route_witness_keeps_tolerated_continuous_center_residual(route_case):
    point = route_case.point.copy()
    point[-1] += 4e-12
    before = point.tobytes()
    assert 0 < point[-1] - route_case.d['upper'][-1] < 1e-8
    grid = ([dict(unit='U', site='B', slot=62, numeric_score=1.)],
            dict(active_voltage_observations=[]))
    spec = select(route_case, point, 'U4', 0, grid)
    assert spec['route_openness']['PASS'] and spec['route_openness']['route_changed']
    assert not spec['route_openness']['SOC_PQ_grid_feasibility_claimed']
    assert point.tobytes() == before


def test_route_witness_rejects_changed_continuous_route_bound_violation(route_case):
    # Continuous Compact representatives remain original FULL route binaries.
    # Every alternate path needs one of these travel arcs at value one.
    route_case.d['upper'][192:194] = .5
    assert np.all(route_case.point >= route_case.d['lower'])
    assert np.all(route_case.point <= route_case.d['upper'])
    free = np.flatnonzero(route_case.d['types'] != 'C')
    assert not route_witness(route_case, route_case.point, free, 48)['PASS']


def test_U4_no_charging_fallback_opens_actual_route_and_is_stage_equal(route_case):
    grid = ([dict(unit='U', site='B', slot=62, numeric_score=1.)],
            dict(active_voltage_observations=[]))
    specs = []
    for stage in ('B2/M', 'B3/M1', 'B3/M2'):
        route_case.identity['stage'] = stage
        specs.append(select(route_case, route_case.point, 'U4', 0, grid))
    for spec in specs:
        assert spec['hamming_radius'] == 48 and spec['lookback_slots'] == 4
        assert spec['no_charging_slots_fallback'] and spec['route_openness']['PASS']
        assert spec['route_openness']['route_changed']
        assert not spec['route_openness']['SOC_PQ_grid_feasibility_claimed']
    assert all(s['neighborhood_signature'] == specs[0]['neighborhood_signature'] for s in specs)
    assert all(np.array_equal(s['free_binary_columns'], specs[0]['free_binary_columns']) for s in specs)


def test_infinity_safe_json_has_no_nonstandard_float_tokens():
    encoded = json.dumps(jsonable({'bound':float('inf'), 'failed':float('nan'),
        'array':np.array([float('-inf')])}), allow_nan=False)
    assert json.loads(encoded) == {'bound':'Infinity', 'failed':'NaN', 'array':['-Infinity']}


def test_existing_LB_requires_same_case_original_dual_and_never_native_bound(route_case):
    from v42_common_mess.engine import _same_case_lb
    with pytest.raises(ValueError, match='CASE_MISMATCH'):
        _same_case_lb(route_case, dict(case_sha='different', exact_original_dual={}))
    with pytest.raises(ValueError, match='ORIGINAL_DUAL'):
        _same_case_lb(route_case, dict(case_sha=route_case.case_sha, native_best_bound=.99))
    assert _same_case_lb(route_case, dict(case_sha=route_case.case_sha, exact_original_dual={})) == 0
    evidence = json.loads((route_case.output / 'BEST_EXACT_LB_CERTIFICATE.json').read_text())
    assert evidence['Native_optimize_calls'] == 0 and evidence['no_LB_optimizer_called']


def test_near_integer_FULL_arc_cannot_be_admitted_as_LP_seed(route_case):
    from v42_common_mess.engine import _validate, _strict
    if route_case.output.drive.upper() != 'D:':
        pytest.skip('Original immutable strict verifier requires D: --basetemp under this checkout')
    point = route_case.point.copy(); point[0] -= 1e-10
    path = route_case.output / 'NEAR_INTEGER_LP_POINT.npz'
    assert _validate(route_case, point, path, _strict, StageBudget(ParentBudget()), 'FULL_integer_gate') is None
    receipt = json.loads(path.with_suffix('.REPLAY.json').read_text())
    assert receipt['error'] == 'HYBRID_FINAL_LITERAL_INTEGER_GATE_FAILED:FULL'


@pytest.mark.parametrize('mutation', [
    {'label':'previous_call'}, {'component':'OTHER'}, {'track':'M_U1'},
    {'requested_seconds':99.}, {'effective_TimeLimit':99.},
    {'status':'IN_FLIGHT'}, {'entered_native':False}, {'runtime_unavailable':True},
    {'Native_Runtime':None}, {'Native_Runtime':float('nan')}, {'Native_Runtime':3.},
])
def test_native_receipt_fallback_rejects_unmatched_or_unmeasured_row(mutation):
    from v42_common_mess.engine import _completed_native_receipt
    parent = ParentBudget(1702.25)
    parent.calls.append(dict(component='UB', track='M_U4', label='trial',
        requested_seconds=100., effective_TimeLimit=100., status='FINISHED',
        entered_native=True, Native_Runtime=2.25, runtime_unavailable=False))
    parent.calls[-1].update(mutation)
    assert _completed_native_receipt(StageBudget(parent), 0, 1700.,
        component='UB', track='M_U4', label='trial', requested_seconds=100.) is None


def test_native_receipt_fallback_requires_one_completed_call_and_no_inflight():
    from v42_common_mess.engine import _completed_native_receipt
    parent = ParentBudget(1702.25)
    row = dict(component='UB', track='M_U4', label='trial', requested_seconds=100.,
        effective_TimeLimit=100., status='FAILED', entered_native=True,
        Native_Runtime=2.25, runtime_unavailable=False, error='measured solver exception')
    parent.calls.append(row)
    budget = StageBudget(parent)
    arguments = dict(component='UB', track='M_U4', label='trial', requested_seconds=100.)
    assert _completed_native_receipt(budget, 0, 1700., **arguments) == row
    assert _completed_native_receipt(budget, 1, 1700., **arguments) is None
    parent.inflight = dict(row)
    assert _completed_native_receipt(budget, 0, 1700., **arguments) is None
    parent.inflight = None
    parent.calls.append(dict(row))
    assert _completed_native_receipt(budget, 0, 1700., **arguments) is None


def test_trial_recovers_durable_no_return_ledger_receipt(tmp_path, monkeypatch):
    from v42_common_mess import engine
    from v42_common_mess.storage import write
    model = SimpleNamespace(Params=SimpleNamespace(), SolCount=0, Status=9,
        Work=1., dispose=lambda:None)
    monkeypatch.setattr(engine, 'build', lambda *args, **kwargs:(model, None, {}))
    class NoReturnBudget(ParentBudget):
        def native_optimize(self, model, callback=None, **kwargs):
            self.value += 2.25
            self.calls.append(dict(kwargs, effective_TimeLimit=model.Params.TimeLimit,
                status='FINISHED', entered_native=True, Native_Runtime=2.25,
                runtime_unavailable=False, precision_parameters={'FeasibilityTol':1e-9}))
            write(tmp_path / 'DURABLE_LEDGER.json', dict(calls=self.calls, measured=self.value))
            return None
    parent = NoReturnBudget(1700.)
    case = SimpleNamespace(case_sha='b' * 64)
    point, strict, row = engine._trial(case, StageBudget(parent), tmp_path / 'trial',
        validator=lambda *args:pytest.fail('No incumbent to validate'), seconds=900.,
        spec={'method':'U4'})
    durable = json.loads((tmp_path / 'DURABLE_LEDGER.json').read_text())
    assert point is strict is None
    assert row['native_receipt'] == durable['calls'][-1]
    assert row['native_receipt']['requested_seconds'] == 100.
    assert row['Native_Runtime'] == 2.25 and row['cumulative_native_runtime_seconds'] == durable['measured']
    parent.calls[-1]['precision_parameters']['FeasibilityTol'] = .1
    assert row['native_receipt']['precision_parameters']['FeasibilityTol'] == 1e-9


def test_real_native_trial_keeps_original_rows_and_never_promotes_bound(tmp_path):
    from v42_common_mess.engine import _trial
    from v42_m1_research.check_ub import vector_sha
    A = sparse.csr_matrix([[0., 1., 0.], [1., -1., 0.], [0., -2., 1.]])
    d = dict(names=np.array(['charge_mode[U,0]', 'rho_max', 'grid_helper[0]']), types=np.array(['B', 'C', 'C']),
        lower=np.array([0., 0., -np.inf]), upper=np.array([1., 1., np.inf]),
        objective=np.array([0., 1., 0.]), constant=np.asarray(0.),
        row_names=np.array(['grid_floor[0]', 'mode_grid_coupling[0]', 'grid_helper_binding[0]']),
        sense=np.array(['>', '<', '=']), rhs=np.array([.5, 0., 0.]))
    case = SimpleNamespace(A=A, d=d, original_A=A, original_d=d, identity={},
        case_sha='b' * 64, output=tmp_path, lift=lambda x:x.copy())
    class RealBudget(ParentBudget):
        def native_optimize(self, model, callback=None, **kwargs):
            model.Params.TimeLimit = kwargs['requested_seconds']; model.Params.OutputFlag = 0
            try:
                model.optimize(callback)
            finally:
                self.value += model.Runtime
                self.calls.append(dict(kwargs, Native_Runtime=model.Runtime, runtime_unavailable=False))
            return self.calls[-1]
    def validator(case, path, evidence):
        with np.load(path) as archive:
            raw = archive['point'].copy()
        residual = case.A @ raw - case.d['rhs']
        violation = np.where(case.d['sense'] == '=', abs(residual),
            np.where(case.d['sense'] == '<', residual, -residual))
        assert np.max(violation) <= 1e-8
        assert raw[0] in (0., 1.) and np.all(raw >= case.d['lower']) and np.all(raw <= case.d['upper'])
        exact = Fraction(float(raw[1]))
        return dict(PASS=True, Global_UB=float(exact), exact_Global_UB=str(exact),
            point_vector_sha256=vector_sha(raw), strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
            original_matrix_and_96_slot_physical_replay=dict(PASS=True, case_sha=case.case_sha))
    budget = StageBudget(RealBudget())
    initial = np.array([0., .75, 1.5])
    seed_packet = tmp_path / 'valid_seed.npz'; np.savez_compressed(seed_packet, point=initial)
    seed_strict = validator(case, seed_packet, {})
    point, certificate, row = _trial(case, budget, tmp_path / 'actual_native',
        validator=validator, seconds=2., point=initial, strict=seed_strict)
    assert certificate['exact_Global_UB'] == '1/2'
    assert np.array_equal(point, np.array([0., .5, 1.]))
    assert row['Native_Runtime'] >= 0 and len(budget.calls) == 1 and row['Global_LB_candidate'] is None
    assert not row['restricted_BestBound_is_Global_LB']
    identity = json.loads((tmp_path / 'actual_native' / 'MODEL_IDENTITY.json').read_text())
    assert all(identity['checks'].values()) and identity['objective'] == 'minimize rho_max'
    assert identity['equality_defined_helper_rows'] == 1
    assert identity['mip_start_helper_equalities_checked_by_original_FULL_replay']
    assert VERSION == 'V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1'


def test_shared_engine_order_budget_and_acceptance_are_identical_for_all_stages(route_case, monkeypatch):
    from copy import copy
    from v42_common_mess import engine
    from v42_m1_research.check_ub import vector_sha
    from v42_common_mess.storage import write
    grid = ([dict(unit='U', site='B', slot=62, numeric_score=1.)], dict(active_voltage_observations=[]))
    monkeypatch.setattr(engine, 'current_grid', lambda *args:grid)
    calls = []
    def trial(case, budget, path, **kwargs):
        spec = kwargs['spec']
        calls.append((spec['method'], spec['hamming_radius'], kwargs['seconds'],
                      spec['neighborhood_signature']))
        budget.native_optimize(SimpleNamespace(Params=SimpleNamespace()),
            requested_seconds=kwargs['seconds'], track='M_' + spec['method'])
        return kwargs['point'], kwargs['strict'], dict(method=spec['method'],
            certified_gain=0., Native_status=2, native_best_bound_diagnostic=.999,
            Native_Runtime=budget.calls[-1]['Native_Runtime'])
    monkeypatch.setattr(engine, '_trial', trial)
    def validator(case, path, evidence):
        with np.load(path) as archive:
            point = archive['point']
        assert np.array_equal(case.A @ point, case.d['rhs'])
        assert np.isin(point[case.original_d['types'] == 'B'], (0., 1.)).all()
        return dict(PASS=True, Global_UB=1., exact_Global_UB='1',
            point_vector_sha256=vector_sha(point), strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
            original_matrix_and_96_slot_physical_replay=dict(PASS=True, case_sha=case.case_sha))
    def exporter(case, point):
        value = dict(case_sha=case.case_sha, synthetic_fixture_only=True)
        write(case.output / 'OPTIMIZED_MESS_PLAN.json', value)
        return value
    results, sequences = [], []
    for arm, stage in (('B2', 'M'), ('B3', 'M1'), ('B3', 'M2')):
        case = copy(route_case); case.output = route_case.output / stage
        calls.clear()
        result, point = engine.optimize_case(case, ParentBudget(),
            stage_identity=dict(arm=arm, stage=stage), strict_validator=validator, plan_exporter=exporter)
        results.append(result); sequences.append(list(calls))
        assert np.array_equal(point, route_case.point)
        assert result['feasible_accepted'] and result['status'] == 'FEASIBLE_ACCEPTED'
        assert not result['global_gap_certified']
        assert result['certified_Global_LB'] is result['certified_gap'] is None
        assert result['native_best_bound_diagnostic'] == .999
        assert result['LB_optimizer_calls'] == result['DW_CG_Benders_calls'] == 0
    assert sequences[0] == sequences[1] == sequences[2]
    assert [(r[0], r[1], r[2]) for r in sequences[0]] == [('U4', 48, 90.), ('U4', 96, 180.), ('U1', 144, 180.)]
    assert len({r['native_runtime_seconds'] for r in results}) == 1
