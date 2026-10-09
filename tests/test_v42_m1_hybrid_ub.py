"""Original-source UB identity and strict admission attacks; Native optimize=0."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from v42_m1_hybrid.neighborhood import grid_candidates, select, signed_support_score
from v42_m1_hybrid.ub import build_model, validate_strict
from v42_m1_research.ub import binary_inventory, select_neighborhood
from v42_m1_research.check_ub import vector_sha


ROOT = Path(__file__).resolve().parents[1]
PROJECTION = ROOT/'docs/v42_m1_joint_gap_research/GRID_ROW_PQ_PROJECTION_PROOF.json'


@pytest.fixture(scope='module')
def case():
    from v42_m1_hybrid.case import load_case
    return load_case(ROOT/'tmp/hybrid_ub_pytest_case')


def test_signed_active_and_reactive_direction_changes_grid_priority():
    # Identical |P|/|Q| sites can have opposite effect on this signed grid row.
    # The candidate proxy preserves exclusive charging/discharging and permits
    # both Q directions; a zero-mode surrogate would lose this opportunity.
    corners = [(F(-1), F(-1)), (F(1), F(1))]
    opportunity, support = signed_support_score((F(-3), F(3), F(2)), 0, corners)
    reversed_opportunity, reversed_support = signed_support_score((F(-3), F(3), F(-2)), 0, corners)
    assert support == -5 and opportunity == 5
    assert reversed_support == -1 and reversed_opportunity == 1
    assert opportunity != reversed_opportunity


@pytest.mark.parametrize('matrix,field', [
    ('C3A', 'integer_pattern_exact'), ('C3A', 'exact_binary_0_1'),
    ('original_full_matrix', 'integer_pattern_exact'),
    ('original_full_matrix', 'exact_binary_0_1')])
def test_scientific_tolerance_PASS_does_not_admit_nonliteral_integer(monkeypatch, matrix, field):
    # This reproduces the old capture-vs-RAW issue independently of any producer
    # PASS flag: one tiny lifted arc must reject the full-source admission.
    raw = np.array([.6, 1.])
    receipt = dict(PASS=True, objective=.6,
        C3A=dict(integer_pattern_exact=True, exact_binary_0_1=True),
        original_full_matrix=dict(integer_pattern_exact=True, exact_binary_0_1=True))
    receipt[matrix][field] = False
    monkeypatch.setattr('v42_m1_hybrid.ub.validate_candidate', lambda c, x: deepcopy(receipt))
    fake = SimpleNamespace(d=dict(objective=np.array([1., 0.]), constant=0.))
    before = vector_sha(raw)
    result = validate_strict(fake, raw)
    assert not result['PASS'] and not result['full_exact_integer_PASS']
    assert result['independent_replay']['PASS']
    assert result['repairs'] == result['rounding'] == result['clipping'] == 0
    assert vector_sha(raw) == before


def test_real_signed_targets_are_verified_original_row_site_time_projection(case):
    targets, proof = grid_candidates(case, case.point, PROJECTION)
    assert proof['exact_source_recombination_checker']['PASS']
    assert len(proof['original_PCS16_score_rows']) == 16
    assert {r['row'] for r in targets} == {465244, 492778, 520001, 546995}
    assert {r['slot'] for r in targets} == {72, 78, 84, 90}
    assert {r['unit'] for r in targets} == set(case.graph[1])
    assert all(F(r['potential_exact']) >= 0 and r['numeric_score'] > 0 for r in targets)
    assert all(not r['attainable_96_slot_dispatch_claimed'] for r in targets)
    assert not proof['physical_or_objective_coefficients_changed']
    assert proof['score_is_candidate_priority_only_not_cut_or_LB']


def test_A_reuses_current_U2_selection_exactly(case):
    old = select_neighborhood(case, case.point, 'U2')
    new = select(case, case.point, 'A', PROJECTION)
    assert np.array_equal(old['free_binary_columns'], new['free_binary_columns'])
    assert np.array_equal(old['fixed_binary_columns'], new['fixed_binary_columns'])
    assert new['hamming_radius'] == 96


@pytest.mark.parametrize('method', ['A', 'B', 'C'])
def test_every_original_binary_accounted_and_seed_feasible_without_forced_routes(case, method):
    spec = select(case, case.point, method, PROJECTION)
    inventory = binary_inventory(case.d)
    free, fixed = set(spec['free_binary_columns']), set(spec['fixed_binary_columns'])
    assert not free & fixed and free | fixed == {r['column'] for r in inventory}
    assert len(free) + len(fixed) == 9322
    assert np.isin(case.point[list(fixed)], (0., 1.)).all()
    modes = [r for r in inventory if r['family'] == 'charge_mode' and r['column'] in free]
    assert {r['unit'] for r in modes} == set(case.graph[1])
    assert spec['source_seed_restricted_feasible'] and not spec['forced_route_removal']
    assert spec['full_original_flow_route_SOC_rows_and_arcs_preserved']
    assert spec['original_all_96_slot_continuous_bounds_preserved']
    assert 'NEVER_GLOBAL_LB' in spec['bound_scope']
    if method == 'C':
        assert len(spec['selected_route_targets']) == 3
        assert all(r['route_removal_is_optional_not_forced'] for r in spec['selected_route_targets'])
        assert all(set(r['role_substitution_units']) == set(case.graph[1]) for r in spec['selected_route_targets'])


def test_real_model_keeps_full_original_source_and_continuous_domains_without_optimize(case, monkeypatch):
    import gurobipy as gp
    def forbidden(*args, **kwargs):
        pytest.fail('No Native optimize or presolve is authorized by this test')
    monkeypatch.setattr(gp.Model, 'optimize', forbidden)
    monkeypatch.setattr(gp.Model, 'presolve', forbidden)
    strict = validate_strict(case, case.point)
    assert strict['PASS'] and strict['full_exact_integer_PASS']
    assert strict['independent_replay']['C3A']['checked_binary_columns'] == 9322
    assert strict['independent_replay']['original_full_matrix']['checked_binary_columns'] == 208312
    before = vector_sha(case.point)
    model, variables, spec = build_model(case, case.point, 'B', ROOT/'tmp/hybrid_ub_pytest_build', PROJECTION, start_replay=strict)
    try:
        assert all(spec['source_checks'].values())
        assert model.NumVars == 306040 and model.NumConstrs == 582809
        assert model.Runtime == 0 and model.Params.MIPGap == .005
        assert model.Params.Threads == 1 and model.Params.IntFeasTol == 1e-8
        assert model.Params.MemLimit == model.Params.SoftMemLimit == float('inf')
        assert spec['start_vector_sha256'] == before == vector_sha(case.point)
    finally:
        model.dispose()
