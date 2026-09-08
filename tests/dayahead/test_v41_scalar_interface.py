from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from types import SimpleNamespace

import numpy as np
import pytest

from dayahead.v41.scalars import project, policy_inputs
from dayahead.v41.reserve import bind, cap_reserve, order_statistic, OBJECTIVE_HIERARCHY
from dayahead.paper_analysis.storage import write_json, sha
from tests.dayahead.test_v40f_min_rho import setup


def fixture():
    ctx, job = setup(equal=True)
    # Full day, with temporal flexibility. The reserve can break an electrical
    # tie without changing the existing P1 electrical equations.
    ctx.coefficients = tuple(replace(ctx.coefficients[0], slot=t) for t in range(96))
    ctx.tables = {s: np.tile([[0., 1., 2.]], (96, 1)) for s in ctx.capacity.aidc_ids}
    job.update(eligible_standby=True, RW_completion_slot=120,
               common_terminal_obligation={'must_complete_by_H': True, 'postH_profile': []},
               source_snapshot_sha256='test', duration_authority='ROLLING_Q90_TRACK_P_L2')
    capacity = np.full((96, 2), 2.)
    snapshot = dict(runtime_model_id='ROLLING_Q90_TRACK_P_L2', H4_model_id='H4_R85_B2', H24_OFF=True,
        objective_hierarchy=list(OBJECTIVE_HIERARCHY), PENDING_JOB_Q90_SECONDS={'one': 900.},
        PENDING_JOB_DURATION_SLOTS={'one': 1}, future_service_eligible_sites=list(ctx.capacity.aidc_ids),
        future_service_eligibility_authority='unit-test authoritative capacity',
        future_service_capacity_gpu=capacity.tolist(),
        **cap_reserve([16.] * 40 + [0.] * 41, [16.] * 100, capacity))
    return ctx, job, snapshot


def poison(snapshot):
    changed = deepcopy(snapshot)
    changed.update(body_tail_class='TAIL', tail_probability=.999, burst_probability=.999,
                   class_probability=[.1, .9], probability_weighted_runtime=1e12,
                   probability_weighted_workload=1e12, stochastic_scenario_selection='wrong',
                   registered_workload_service_level=.85)
    return changed


@pytest.mark.parametrize('policy', ['B0', 'B1', 'B2', 'B3'])
@pytest.mark.parametrize('stage', ['REFERENCE', 'A0', 'A1'])
def test_every_policy_and_stage_consumes_identical_scalar_projection(policy, stage):
    _, _, snapshot = fixture()
    expected = project(snapshot)
    actual = policy_inputs(poison(snapshot), policy, stage)
    assert actual == expected and actual.sha256 == expected.sha256
    assert set(actual.payload()) == {'PENDING_JOB_Q90_SECONDS', 'PENDING_JOB_DURATION_SLOTS',
                                     'H4_ACTIONABLE_RESERVE_GPUh'}
    assert all(type(v) is float for v in actual.actionable_h4_gpuh)
    with pytest.raises(FrozenInstanceError):
        actual.actionable_h4_gpuh = ()


@pytest.mark.parametrize('bad', [True, None, [900.], {'tail_probability': .9}, float('nan'), float('inf'), 0., -1.])
def test_runtime_cannot_be_probability_object_or_invalid_scalar(bad):
    _, _, snapshot = fixture()
    snapshot['PENDING_JOB_Q90_SECONDS']['one'] = bad
    with pytest.raises(ValueError):
        project(snapshot)


@pytest.mark.parametrize('seconds,slots', [(1., 1), (900., 1), (900.00001, 2), (1800., 2)])
def test_runtime_ceil_once(seconds, slots):
    _, _, snapshot = fixture()
    snapshot['PENDING_JOB_Q90_SECONDS']['one'] = seconds
    snapshot['PENDING_JOB_DURATION_SLOTS']['one'] = slots
    assert project(snapshot).pending_runtime == (('one', seconds, slots),)


@pytest.mark.parametrize('bad', [True, None, [.9], {'burst_probability': .9}, float('nan'), float('inf'), -1.])
def test_h4_requires_one_finite_nonnegative_scalar_per_window(bad):
    _, _, snapshot = fixture()
    snapshot['H4_ACTIONABLE_RESERVE_GPUh'][0] = bad
    with pytest.raises(ValueError):
        project(snapshot)


def test_hist_cap_uses_registered_finite_sample_order_statistic():
    assert order_statistic(list(range(100))) == (99., 100)
    assert order_statistic([3.]) == (3., 1)
    cap = cap_reserve([100.] * 81, [7.] * 500, np.ones((96, 1)))
    assert cap['H4_RAW_R85_B2_GPUh'] == [100.] * 81
    assert cap['H4_CAP_PHYS'] == [4.] * 81
    assert cap['H4_ACTIONABLE_RESERVE_GPUh'] == [4.] * 81


def bound(tmp_path, snapshot, ctx):
    path = tmp_path / 'snapshot.json'
    write_json(path, snapshot)
    bind(ctx, path, sha(path))


def test_real_a0_solver_result_ignores_legacy_probabilities(tmp_path):
    from dayahead.v40g.optimizer import solve
    results = []
    for label, injected in [('clean', False), ('poisoned', True)]:
        ctx, row, snapshot = fixture()
        folder = tmp_path / label
        bound(folder, poison(snapshot) if injected else snapshot, ctx)
        pcc = np.zeros((96, 2)); pcc[0, 0] = 1.
        results.append(solve([row], pcc, ctx, folder / 'solve'))
    assert results[0]['jobs'] == results[1]['jobs']
    assert results[0]['OBJECTIVE_VECTOR'] == results[1]['OBJECTIVE_VECTOR']
    assert results[0]['jobs'][0]['start_slot'] >= 79
    assert results[0]['reserve_diagnostics']['mean_xi_GPUh'] == 0.
    assert results[0]['grid']['rho_max'] <= results[0]['primary_optimum'] + 1e-10


def test_real_a1_solver_result_ignores_legacy_probabilities(tmp_path, monkeypatch):
    from dayahead.v40g_segments.canonical import import_frozen, occupancy
    import dayahead.v40h.feedback as feedback
    from dayahead.v33m.mess_trajectory import MessTrajectory
    # Numeric occupancy/PCC fixture is linear; use the same values as the real
    # optimizer's PWL. M1 is identically zero, frozen throughout both calls.
    def power(jobs, ctx):
        gpu = occupancy(jobs, ctx.capacity.aidc_ids)[0]
        return gpu.astype(float), gpu
    monkeypatch.setattr(feedback, 'pcc_from_jobs', power)
    monkeypatch.setattr(feedback, 'controls_from_trajectory',
                        lambda coefficients, pcc, slots: np.column_stack([pcc, np.zeros(96)]))
    results = []
    for label, injected in [('clean', False), ('poisoned', True)]:
        ctx, row, snapshot = fixture()
        bound(tmp_path / label, poison(snapshot) if injected else snapshot, ctx)
        result = feedback.solve_feedback(import_frozen([row]), MessTrajectory(()), ctx)
        results.append(result)
    assert results[0]['jobs'] == results[1]['jobs']
    assert results[0]['grid'] == results[1]['grid']
    assert results[0]['reserve_diagnostics'] == results[1]['reserve_diagnostics']
    assert results[0]['reserve_diagnostics']['mean_xi_GPUh'] == 0.
    assert results[0]['jobs'][0]['start_slot'] >= 79
    assert [stage['requested_relative_gap'] for stage in results[0]['solver'][:2]] == [.03, .03]


def test_snapshot_mutation_rejected_at_optimizer_entry(tmp_path):
    from dayahead.v41.scalars import validate_bound
    ctx, _, snapshot = fixture()
    bound(tmp_path, snapshot, ctx)
    ctx.v41_ml_snapshot['PENDING_JOB_Q90_SECONDS']['one'] = 9000.
    with pytest.raises(ValueError, match='ML_SNAPSHOT_MEMORY_DRIFT'):
        validate_bound(ctx)
