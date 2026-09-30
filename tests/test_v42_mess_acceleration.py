from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import gurobipy as gp
import pytest

from v42_native.canary import fixture, mess_grid
from v42_native.contracts import Deadline
from v42_native.mess import construct, solve, validate_start
from v42_native.mess_domain import Arc, build_domain, structural, delta
from v42_native.mess_optimizer import OptimizeBudget
from v42_native.mess_audit import adversarial_cases, baseline, baseline_build, exhaustive, random_cases, diagnostic_grid


CASES = list(adversarial_cases().items()) + list(random_cases())


@pytest.mark.parametrize('name,case', CASES, ids=[name for name, _ in CASES])
def test_all_continuous_feasible_route_intervals_survive(name, case):
    assert exhaustive(case)['false_pruned'] == 0


@pytest.mark.parametrize('name,case', CASES, ids=[name for name, _ in CASES])
def test_PR99_optimal_objective_equivalence(name, case):
    sites, H, b, routes = case
    old, before = baseline().solve('M1', Deadline('M1', 20), sites, {'M': 'A'}, routes, b, H, diagnostic_grid)
    new, after = solve('M1', OptimizeBudget('M1', 20), sites, {'M': 'A'}, routes, b, H, diagnostic_grid, diagnostic=True)
    assert (old is None) == (new is None)
    if new is not None:
        assert old['lex_complete'] and new['lex_complete']
        assert old['physical_audit']['PASS'] and new['physical_audit']['PASS']
        for level in ('rho', 'reserve_shortfall', 'movement_kwh', 'movement_count', 'tie'):
            assert old['objectives'][level] == pytest.approx(new['objectives'][level], abs=3e-7)
    else:
        assert before['passes'][0]['status'] == after['passes'][0]['status'] == gp.GRB.INFEASIBLE


def test_forward_backward_structure_and_any_terminal():
    arcs = (Arc(0, 'A', 0, 'B', 2), Arc(1, 'B', 2, 'B', 3),
            Arc(2, 'C', 0, 'C', 1), Arc(3, 'A', 0, 'C', 2))
    f, b = structural(arcs, ('A', 0), {('A', 3), ('B', 3), ('C', 3)})
    assert ('C', 0) not in f and ('B', 2) in f
    assert ('C', 2) in f and ('C', 2) not in b  # authorized terminal set, actual dead-end
    assert ('B', 2) in b  # no invented return-to-A requirement
    from v42_native.mess_domain import _unit
    _, _, battery, _ = fixture()
    unit = _unit('M', 'A', ('A','B','C'), arcs, battery, 3)
    assert (3, 'BACKWARD_DEAD_END') in unit.removals
    assert 0 in unit.arc_indices and 1 in unit.arc_indices


def test_exact_duplicates_all_fields_and_no_energy_dominance():
    sites, H, b, routes = adversarial_cases()['different_energy_no_dominance']
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    assert len(d.routes) == 2 and routes[1] in d.routes
    assert any(d.arcs[k].route == routes[1] for k in d.units[0].travel_indices)
    sites, H, b, routes = adversarial_cases()['exact_duplicates_only']
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    assert len(d.routes) == 3 and len(d.duplicate_indices) == 1
    for r in d.routes:
        assert r in routes  # timing, full energy, authority unchanged
    assert replace(routes[0], arrive=routes[0].arrive) in d.routes
    numeric = (replace(routes[0], energy_kwh=0), replace(routes[0], energy_kwh=0.0))
    assert len(build_domain(sites, {'M':'A'}, numeric, b, H).routes) == 1
    timed = (replace(routes[0], arrive=1, connect=2), replace(routes[0], arrive=2, connect=2))
    assert len(build_domain(sites, {'M':'A'}, timed, b, H).routes) == 2


def test_direction_columns_removed_only_without_stay_and_transit_SOC_timing():
    sites, H, b, routes = adversarial_cases()['terminal_equality_and_transit_only']
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    u = d.units[0]
    assert u.charge_times == (4,)
    assert u.electrical_states == (('B', 4),)
    assert set(d.pq_indices) == {('M', 'B', 4)} and len(d.pcs_indices) == 16
    assert dict(u.global_soc)[1].upper < 1e-7  # full energy deducted at departure+1
    assert dict(u.global_soc)[3].upper < 1e-7
    model, _, x, stats = construct(d, diagnostic_grid)
    try:
        assert stats['per_mess'][0]['charge_mode_binaries'] == 1
        assert stats['model_size_before_solve']['constraint_families']['PCS16'] == 16
        assert not any(v.VarName.startswith('Pch[M,A') for v in model.getVars())
        assert stats['model_size_before_solve']['quadratic_constraints'] == 0
    finally:
        model.dispose()


def test_stay_efficiencies_and_travel_exact_energy():
    sites, H, b, routes = fixture()
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    assert delta(d.arcs[0], b) == (-.25 * b.p_limit / b.eta_discharge, .25 * b.eta_charge * b.p_limit)
    assert delta(d.arcs[-1], b) == (-routes[-1].energy_kwh,) * 2


def test_original_canary_moves_with_same_scientific_objectives():
    sites, H, b, routes = fixture()
    old, _ = baseline().solve('M1', Deadline('M1', 20), sites, {'M': 'A'}, routes, b, H, mess_grid)
    new, _ = solve('M1', OptimizeBudget('M1', 20), sites, {'M': 'A'}, routes, b, H, mess_grid, diagnostic=True)
    assert old['objectives'] == pytest.approx(new['objectives'], abs=3e-7)
    assert new['objectives']['movement_kwh'] > 0


def test_arc_mapping_screen_actually_removes_an_impossible_arc():
    case = adversarial_cases()['different_energy_no_dominance']
    sites, H, b, routes = case
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    assert any(reason == 'ARC_SOC_MAPPING_EMPTY' for _, reason in d.units[0].removals)
    assert exhaustive(case)['false_pruned'] == 0


def test_explicit_shared_domain_rejects_changed_authority_before_build():
    sites, H, b, routes = fixture()
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    def forbidden(model, p, q):raise AssertionError('MODEL_MUST_NOT_BE_BUILT')
    with pytest.raises(ValueError, match='AUTHORITY_DRIFT'):
        solve('M1', OptimizeBudget('M1', 20), sites, {'M': 'A'}, routes, replace(b, terminal=11.), H, forbidden, domain=d)


def test_domain_immutable_deterministic_reused_without_grid_anchor():
    sites, H, b, routes = fixture()
    d = build_domain(sites, {'Z': 'B', 'M': 'A'}, routes, b, H)
    assert build_domain(sites, {'M': 'A', 'Z': 'B'}, routes, b, H) is d
    with pytest.raises(FrozenInstanceError):
        d.sha256 = 'bad'
    first_hash = d.sha256
    from v42_native.mess_domain import _cached
    _cached.cache_clear()
    assert build_domain(sites, {'M': 'A', 'Z': 'B'}, routes, b, H).sha256 == first_hash
    assert d.input_sha256 != build_domain(sites, {'M': 'A', 'Z': 'B'}, routes, replace(b, initial=11.), H).input_sha256


@pytest.mark.parametrize('mutation', ['domain', 'SOC', 'Pch', 'Q', 'direction', 'missing', 'arc', 'authority'])
def test_invalid_full_warm_start_rejected_without_clipping(mutation):
    sites, H, b, routes = fixture()
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    first, _ = solve('M1', OptimizeBudget('M1', 20), sites, {'M': 'A'}, routes, b, H, mess_grid, diagnostic=True, domain=d)
    bad = deepcopy(first)
    if mutation == 'domain': bad['domain_sha256'] = 'f' * 64
    elif mutation == 'SOC': bad['values']['SOC[M,0]'] += 1
    elif mutation == 'Pch': bad['values']['Pch[M,A,0]'] = 5.
    elif mutation == 'Q': bad['values']['Q[M,A,0]'] = 100.
    elif mutation == 'direction': bad['values']['charge_mode[M,0]'] = .5
    elif mutation == 'missing': del bad['values']['Pch[M,A,0]']
    elif mutation == 'arc': bad['chosen_arcs']['M'].append(9999)
    else: d = build_domain(sites, {'M': 'A'}, (replace(routes[0], authority_sha256='b' * 64), routes[1]), b, H)
    unchanged = deepcopy(bad)
    with pytest.raises(ValueError): validate_start(bad, d)
    assert bad == unchanged


def test_M1_M2_full_warm_start_same_optimum_with_dynamic_grid():
    sites, H, b, routes = fixture()
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    first, _ = solve('M1', OptimizeBudget('M1', 20), sites, {'M': 'A'}, routes, b, H, mess_grid, diagnostic=True, domain=d)
    def second_grid(model, p, q):
        return diagnostic_grid(model, p, q)
    cold, _ = solve('M2', OptimizeBudget('M2', 20), sites, {'M': 'A'}, routes, b, H, second_grid, diagnostic=True, domain=d)
    warm, receipt = solve('M2', OptimizeBudget('M2', 20), sites, {'M': 'A'}, routes, b, H, second_grid, first, diagnostic=True, domain=d)
    assert receipt['warm_start_physical_validation']['PASS']
    assert receipt['warm_start_values_applied'] >= sum(row['total_columns'] for row in receipt['per_mess'])
    assert receipt['warm_start_accepted'] and warm['objectives'] == pytest.approx(cold['objectives'], abs=3e-7)
    assert receipt['shared_domain_supplied']


def test_optimize_budget_excludes_domain_and_build_even_if_old_deadline_expired():
    clock = [0.]
    budget = OptimizeBudget('M1', clock=lambda: clock[0])
    clock[0] = 9000.
    assert budget.remaining == 1800.
    budget.begin(); clock[0] += 30.
    assert budget.remaining == 1770.
    assert not budget.receipt()['build_included'] and budget.receipt()['presolve_included']
    sites, H, b, routes = fixture()
    legacy = Deadline('M1', 20, clock=lambda: clock[0])
    clock[0] += 100.
    _, receipt = solve('M1', legacy, sites, {'M': 'A'}, routes, b, H, mess_grid)
    assert receipt['budget_seconds'] == 20 and receipt['budget_origin'] == 'FIRST_OPTIMIZE'
    assert receipt['target_MIPGap'] == .005
    assert receipt['model_build_seconds'] > 0 and receipt['solve_wall_seconds'] > 0


def test_PR99_model_size_measured_and_reduction():
    sites, H, b, routes = adversarial_cases()['terminal_equality_and_transit_only']
    before = baseline_build(sites, {'M': 'A'}, routes, b, H)
    d = build_domain(sites, {'M': 'A'}, routes, b, H)
    model, _, _, after = construct(d, lambda m, p, q: [('rho', gp.LinExpr(0)), ('reserve_shortfall', gp.LinExpr(0))])
    try:
        assert before['family_columns']['charge_mode'] == H
        assert after['per_mess'][0]['charge_mode_binaries'] == 1
        assert before['model_size_before_solve']['nonzeros'] > after['model_size_before_solve']['nonzeros']
    finally: model.dispose()
