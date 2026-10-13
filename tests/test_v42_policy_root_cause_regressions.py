"""Masked V5 conditions; explicit synthetic inputs, never May action evidence."""
import numpy as np
import pytest

from test_v42_integration_sensitivity_policy import fixture, compile_fixture, metadata, receipt
from v42_integration.policy import ReservationLedger
from v42_integration.sensitivity_policy import FrozenSensitivityPolicy


@pytest.mark.parametrize('batch', [None, False])
def test_same_start_source_authorized_preplacement_does_not_require_delay_batch_rights(batch):
    policy = compile_fixture(fixture(profile='placement'))
    observed = metadata()
    observed['batch_eligible'] = batch
    result = policy.select(observed, receipt(0), 0, ReservationLedger({'A': 8, 'B': 8}))
    assert result['action'] == 'PREPLACE'
    assert result['site'] == 'B' and result['additional_start_delay_seconds'] == 0
    assert observed['can_prestart_place'] is True and receipt(0)['budget_seconds'] == 0
    assert result['online_grid_horizon_evaluations'] == 0


@pytest.mark.parametrize('batch', [None, False])
def test_positive_delay_keeps_independent_batch_authority_requirement(batch):
    values = fixture(profile='placement')
    values[5].update(compatible_sites=['A'], can_prestart_place=False)
    policy = compile_fixture(values)
    observed = metadata()
    observed.update(compatible_sites=['A'], can_prestart_place=False, batch_eligible=batch)
    candidates, reason = policy.candidates(observed, receipt(), 0)
    assert reason == 'MATCH'
    assert candidates and all(r['additional_start_delay_seconds'] == 0 for r in candidates)
    selected = policy.select(observed, receipt(), 0, ReservationLedger({'A': 8, 'B': 8}))
    assert selected['policy_action'] == 'START_NOW'
    observed['batch_eligible'] = True
    permitted = policy.select(observed, receipt(), 0, ReservationLedger({'A': 8, 'B': 8}))
    assert permitted['policy_action'] == 'DELAY_15'


@pytest.mark.parametrize('source_site', ['A', None])
@pytest.mark.parametrize('batch', [None, True])
def test_explicit_preplacement_permission_required_even_without_source_site(source_site, batch):
    policy = compile_fixture(fixture(profile='placement'))
    observed = metadata()
    observed.update(source_site=source_site, can_prestart_place=False, batch_eligible=batch)
    candidates, _ = policy.candidates(observed, receipt(0), 0)
    assert all(r['action'] != 'PREPLACE' for r in candidates)
    result = policy.select(observed, receipt(0), 0, ReservationLedger({'A': 8, 'B': 8}))
    assert result['policy_action'] == 'START_NOW' and result['site'] == 'A'


@pytest.mark.parametrize('protected', [None, True])
def test_preplacement_fix_preserves_confirmed_nonprotected_scope(protected):
    policy = compile_fixture(fixture(profile='placement'))
    observed = metadata()
    observed.update(protected=protected, batch_eligible=None)
    result = policy.select(observed, receipt(0), 0, ReservationLedger({'A': 8, 'B': 8}))
    assert result['action'] == 'QUEUE' and result['reason'] == 'ACTION_QOS_AUTHORITY_UNCONFIRMED'


def test_running_batch_authority_guard_is_unchanged():
    values = fixture(profile='placement', running=True)
    policy = compile_fixture(values)
    observed = metadata()
    observed.update(state='RUNNING', current_site='A', t50_seconds=2700,
                    accumulated_compute_seconds=1800, batch_eligible=None)
    result = policy.select_migration(observed, receipt(), 0, ReservationLedger({'A': 8, 'B': 8}))
    assert result['action'] == 'STAY' and result['reason'] == 'ACTION_QOS_AUTHORITY_UNCONFIRMED'


@pytest.mark.parametrize('stress_slot', [0, 2, 3, 95])
def test_capacity_horizon_ignores_only_past_and_retains_current_future_stress(stress_slot):
    values = list(fixture(profile='placement', q90_extra=3))
    values[5]['time_slots'] = [2]
    stress = np.zeros((96, 2))
    stress[stress_slot, 1] = 12
    values[-1]['stress_site_GPU'] = stress.tolist()
    values[-1].update(stress_allocation_source='A_STAGE_OPTIMIZED_RESERVE',
                      allocation_aidc_anchor=values[-2]['aidc_anchor'],
                      stress_profile_GPU=stress.sum(axis=1).tolist(), stress_carryout_GPUh=0.)
    packet = values[0]
    future_grid = packet.evaluate(np.zeros((96, 2)), remaining_slot=2, scenario_gpu=stress)
    policy = compile_fixture(values)
    template = policy.document['templates'][0]
    assert len(template['scenario_comparisons']) >= 2
    if stress_slot < 2:
        assert future_grid['hard_feasible']
        assert template['ordered_actions']
        assert all(row['hard_feasible'] for row in template['scenario_comparisons'])
    else:
        assert not template['ordered_actions']
        assert all(not row['hard_feasible'] for row in template['scenario_comparisons'])
        assert any(v['reason'] == 'WHOLE_GANG_SITE_GPU_CAPACITY'
                   for rejection in template['rejected_candidates']
                   for scenario in rejection.get('scenarios', {}).values()
                   for v in scenario['violations'])


def test_action_specific_rights_and_capacity_scope_survive_frozen_reload(tmp_path):
    policy = compile_fixture(fixture(profile='placement'))
    path = tmp_path / 'POLICY.json'
    policy.save(path)
    loaded = FrozenSensitivityPolicy.load(path, bindings=policy.bindings)
    observed = metadata()
    observed['batch_eligible'] = None
    before = policy.select(observed, receipt(0), 0, ReservationLedger({'A': 8, 'B': 8}), reserve=False)
    after = loaded.select(observed, receipt(0), 0, ReservationLedger({'A': 8, 'B': 8}), reserve=False)
    assert before == after and loaded.sha == policy.sha
