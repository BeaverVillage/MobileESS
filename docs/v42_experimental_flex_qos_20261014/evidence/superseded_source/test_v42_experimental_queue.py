"""Anonymous research queue conservation and unchanged-grid counterexamples."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from v42_integration.experimental_queue import fluid_queue, evaluate_q90_risk, rank_action_scores


def authority(hourly, kernel):
    return dict(model_id='NAMED_SYNTHETIC_QUEUE_FIXTURE', prediction_sha='a'*64,
        kernel_sha='b'*64, q90_hourly_GPUh=list(hourly), kernel=list(kernel),
        evidence_kind='FIXTURE', forecast_modifications=0, fit_calls=0)


def queue(hourly=None, kernel=(1.,), *, capacities=None, known=None, reserved=None, **kwargs):
    hourly = np.ones(24) if hourly is None else np.asarray(hourly, float)
    capacities = capacities or {'A':8, 'B':8}
    known = np.zeros((96, len(capacities))) if known is None else known
    return fluid_queue(hourly, kernel, capacities, known_gpu=known, reserved_gpu=reserved,
        source_authority=authority(hourly, kernel), **kwargs)


def original_grid_fixture():
    # Existing named physical-response fixture; no model/solver/AC creation.
    path=Path(__file__).with_name('test_v42_integration_sensitivity_policy.py')
    spec=importlib.util.spec_from_file_location('queue_original_grid_fixture', path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.fixture()


def action(name, primary=.5, *, carry=1., queue_area=2., risk_peak=.7,
           violations=0, burden=0., migrations=0, physical=True, q50_hard=True):
    return dict(action=name,site='A',candidate_id=name,q50_peak_score=primary,
        physical_feasible=physical,q50_hard_feasible=q50_hard,
        intentional_burden_seconds=burden,migration_count=migrations,
        q90_risk=dict(carryout_GPUh=carry,queue_GPUh_hours=queue_area,
            peak_score=risk_peak,violation_count=violations))


def test_overload_24408_lifetime_work_is_preserved_above_18720_day_capacity():
    result=queue(np.full(24,24408./24),capacities={'A':780})
    assert result['arrived_GPUh']==pytest.approx(24408.)
    assert result['total_served_GPUh']==pytest.approx(18720.)
    assert result['carryout_GPUh']==pytest.approx(5688.)
    assert result['arrived_GPUh']==pytest.approx(result['total_served_GPUh']+result['remaining_work_GPUh'])
    assert np.max(result['served_site_GPU'])==780
    assert result['conservation_PASS']
    assert result['future_individual_UIDs']==0
    assert not result['demand_backlog_is_GPU_occupancy']


def test_kernel_tail_outside96_remains_in_remaining_work():
    kernel=np.zeros(100);kernel[-1]=1
    result=queue(np.ones(24),kernel)
    assert result['total_served_GPUh']==0
    assert result['queue_at_day_end_GPUh']==0
    assert result['outside96_release_tail_GPUh']==24
    assert result['carryout_GPUh']==24
    assert sum(result['released_service_tail_GPUh'])==24
    assert result['not_yet_service_eligible_GPUh'][-1]==24


def test_known_and_explicit_reservations_are_physical_headroom_not_anonymous_forecast():
    known=np.full((96,2),3.);reserved=np.full((96,2),4.)
    result=queue(np.full(24,10.),known=known,reserved=reserved)
    assert np.max(result['served_site_GPU'])==1
    assert np.max(result['total_physical_site_GPU'])<=8
    assert result['total_served_GPUh']==48
    assert result['carryout_GPUh']==192


def test_zero_headroom_queues_all_work_without_deleting_it():
    result=queue(np.ones(24),known=np.full((96,2),8.))
    assert result['total_served_GPUh']==0
    assert result['queue_at_day_end_GPUh']==24
    assert result['carryout_GPUh']==24
    assert not result['forecast_clipping_or_scaling']


def test_source_vectors_and_inputs_are_not_mutated_or_scaled():
    hourly=np.arange(24,dtype=float);kernel=np.array([.5,.5]);known=np.zeros((96,2))
    before=(hourly.copy(),kernel.copy(),known.copy())
    result=queue(hourly,kernel,known=known)
    assert all(np.array_equal(a,b) for a,b in zip((hourly,kernel,known),before))
    assert result['forecast_lifetime_GPUh']==hourly.sum()
    assert result['model_fit_or_calibrator_calls']==0


def test_source_vector_drift_rejected():
    hourly=np.ones(24);source=authority(hourly,[1.]);source['q90_hourly_GPUh'][0]=2
    with pytest.raises(ValueError,match='VECTOR_DRIFT'):
        fluid_queue(hourly,[1.],{'A':8},known_gpu=np.zeros((96,1)),source_authority=source)


@pytest.mark.parametrize('field,value', [('future_job_ids',['FUTURE_UID']),('forecast_modifications',1),
    ('fit_calls',1),('new_calibrator_calls',1),('scaling_calls',1),('clipping_calls',1)])
def test_future_uid_and_forecast_modifications_refused(field,value):
    hourly=np.ones(24);source=authority(hourly,[1.]);source[field]=value
    with pytest.raises(ValueError):
        fluid_queue(hourly,[1.],{'A':8},known_gpu=np.zeros((96,1)),source_authority=source)


def test_non_normalized_kernel_is_refused_instead_of_rescaled():
    with pytest.raises(ValueError,match='NORMALIZED'):
        queue(kernel=[.9])


def test_past_fixed_overflow_audited_without_rejecting_future_headroom():
    known=np.zeros((96,2));known[0,0]=9
    result=queue(known=known,remaining_slot=1)
    assert result['past_fixed_capacity_violation_cells']==1
    assert result['current_future_capacity_violation_cells']==0
    assert result['conservation_PASS']


def test_current_observed_backlog_is_never_served_in_past_slots():
    result=queue(np.zeros(24),remaining_slot=90,causal_queue_start_slot=90,
        initial_backlog_gpu_h=100.)
    assert np.sum(np.asarray(result['served_site_GPU'])[:90])==0
    assert result['total_served_GPUh']==24
    assert result['carryout_GPUh']==76
    assert result['initial_backlog_release_slot']==90
    assert result['served_before_causal_start_GPUh']==0
    assert result['backlog_GPUh'][89]==0
    assert result['backlog_GPUh'][90]==96
    assert result['conservation_PASS']


def test_prior_remaining_forecast_release_queues_without_invented_past_service():
    hourly=np.zeros(24);hourly[0]=100
    result=queue(hourly,remaining_slot=90,causal_queue_start_slot=90)
    assert result['backlog_GPUh'][89]==100
    assert np.sum(np.asarray(result['served_site_GPU'])[:90])==0
    assert result['total_served_GPUh']==24
    assert result['carryout_GPUh']==76
    assert result['conservation_PASS']


def test_causal_start_cannot_precede_current_observed_event():
    with pytest.raises(ValueError,match='CANNOT_PRECEDE'):
        queue(remaining_slot=90,causal_queue_start_slot=89,initial_backlog_gpu_h=100.)


def test_offline_default_initial_backlog_reconstruction_still_starts_at_zero():
    result=queue(np.zeros(24),remaining_slot=90,initial_backlog_gpu_h=100.)
    assert result['causal_queue_start_slot'] is None
    assert result['total_served_GPUh']==100
    assert result['carryout_GPUh']==0


@pytest.mark.parametrize('slot',[1,40,95])
def test_current_future_fixed_overflow_remains_hard(slot):
    known=np.zeros((96,2));known[slot,0]=9
    with pytest.raises(ValueError,match='CURRENT_FUTURE'):
        queue(known=known,remaining_slot=1)


def test_grid_risk_uses_served_profile_replacing_Q50_not_raw_demand():
    packet,envelope,*_=original_grid_fixture()
    result=queue(np.full(24,1000.))
    anonymous=np.ones((96,2))
    risk=evaluate_q90_risk(packet,result,frozen_anonymous_gpu=anonymous)
    physical=np.asarray(result['total_physical_site_GPU'])
    direct=packet.evaluate(physical-anonymous,scenario_gpu=np.zeros((96,2)))
    assert risk['original_grid_result']==direct
    assert risk['peak_score']==direct['peak_score']
    assert not risk['hard_feasible']
    assert risk['violation_count']>0
    assert not risk['Q90_demand_added_to_physical_occupancy']
    assert not risk['backlog_hard_veto']
    assert not risk['Actual_Fresh_AC_certificate']


def test_rebound_later_slot_is_strictly_evaluated_by_original_grid():
    packet,*_=original_grid_fixture()
    delta=np.zeros((96,2));delta[0,0]=-1;delta[1,0]=1
    score=packet.evaluate(delta)
    assert score['per_slot_peak'][0]==pytest.approx(.6)
    assert score['peak_score']==pytest.approx(1.15)
    assert not score['hard_feasible']
    ranked=rank_action_scores([action('STAY',primary=.9),action('DELAY',primary=score['peak_score'],q50_hard=False)])
    assert ranked['selected']['action']=='STAY'
    assert len(ranked['rejected_actions'])==1


def test_Q50_primary_precedes_Q90_queue_risk_and_unnecessary_disruption():
    ranked=rank_action_scores([action('DELAY',.49,carry=1000.,burden=900),action('STAY',.5,carry=0)])
    assert ranked['selected']['action']=='DELAY'
    assert not ranked['original_A_stage_P2']


def test_Q50_tie_prefers_Q90_risk_then_less_migration_delay():
    ranked=rank_action_scores([action('MIGRATE',migrations=1),action('DELAY',burden=900),
        action('STAY'),action('BAD_QUEUE',carry=10.)])
    assert [r['action'] for r in ranked['ordered_actions']]==['STAY','DELAY','MIGRATE','BAD_QUEUE']


def test_near_tie_groups_are_not_transitively_chained():
    rows=[action('A',.5,carry=3),action('B',.5+0.9e-9,carry=2),action('C',.5+1.8e-9,carry=0)]
    ranked=rank_action_scores(rows,q50_tie_tolerance=1e-9)
    assert [r['action'] for r in ranked['ordered_actions']]==['B','A','C']


def test_Q90_backlog_and_grid_risk_do_not_blanket_veto_safe_Q50_action():
    result=rank_action_scores([action('START',carry=1000.,risk_peak=1.5,violations=12)])
    assert result['selected']['action']=='START'
    assert result['selected']['q90_risk']['violation_count']==12
    assert not result['Q90_backlog_blanket_veto']


def test_missing_risk_is_not_coerced_to_zero_and_physical_failure_refused():
    missing=action('MISSING');missing['q90_risk'].pop('peak_score')
    with pytest.raises(ValueError,match='COMPLETE_ACTION'):
        rank_action_scores([missing])
    result=rank_action_scores([action('UNSAFE',physical=False)])
    assert result['selected'] is None
    assert result['rejected_actions'][0]['rank_reject_reason']=='ACTUAL_RESOURCE_OR_Q50_ORIGINAL_HARD_CONSTRAINT'


def test_preregistered_site_priority_is_explicit_and_changes_only_partition():
    first=queue(allocation_priority=['A','B']);second=queue(allocation_priority=['B','A'])
    assert first['total_served_GPUh']==second['total_served_GPUh']
    assert first['carryout_GPUh']==second['carryout_GPUh']
    assert first['source_sha']!=second['source_sha']
    assert np.array_equal(np.asarray(first['served_site_GPU'])[:,0],np.asarray(second['served_site_GPU'])[:,1])
