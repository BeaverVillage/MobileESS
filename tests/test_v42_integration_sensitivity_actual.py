"""Frozen ranked actions through common physical phases; synthetic evidence."""
from copy import deepcopy

import numpy as np
import pytest

from v42_capacity.actual import Environment
from v42_integration.actual import JobEventController,run_actual,FrozenPowerModel
from v42_integration.qos import QoSWindowProvider
from v42_final.workload import ForecastBook
from test_v42_integration_actual import qos,request,capability
from test_v42_integration_sensitivity_policy import fixture,compile_fixture


def provider():
    return QoSWindowProvider(qos().stats,case_sha='FIXTURE_CASE',provider_sha='provider')


def migration_policy():
    # The real signed fixture has a rebound at control slot 1; moving the
    # remaining service reduces its peak. A flat profile ties with STAY.
    values=fixture(profile='rebound',running=True)
    values[5].update(time_slots=[1],accumulated_compute_seconds=1800,
        wan_capacities={'AB':100},migration_capability=capability())
    return compile_fixture(values)


def initial_jobs():
    moving=request('moving',submit=-1800,q50=2700,source_site='A',qos='normal',protected=False,
        requested_walltime_seconds=3600,migration_capability=capability(),elapsed_compute_seconds=900)
    background=request('background',submit=-2000,q50=900,source_site='B',qos='normal',protected=False,
        requested_walltime_seconds=3600,compatible=('B',),elapsed_compute_seconds=1000)
    return moving,background


def delay_fixture():
    values=fixture(profile='placement')
    values[5].update(compatible_sites=['A'],can_prestart_place=False)
    policy=compile_fixture(values)
    pending=request('submitted',q50=900,compatible=('A',),qos='normal',protected=False,
        requested_walltime_seconds=3600,can_prestart_place=False)
    backgrounds=[request('background-'+site,submit=-1000,q50=900,source_site=site,
        compatible=(site,),qos='normal',protected=False,requested_walltime_seconds=3600,
        elapsed_compute_seconds=1000) for site in ('A','B')]
    return policy,pending,backgrounds


def test_new_policy_submit_delay_cc4_once_frozen_reload_and_physical_recompute(tmp_path):
    policy,pending,backgrounds=delay_fixture()
    path=tmp_path/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json';policy.save(path)
    from v42_integration.sensitivity_policy import FrozenSensitivityPolicy
    loaded=FrozenSensitivityPolicy.load(path,bindings=policy.bindings)
    book=ForecastBook(tuple([.1]*24),tuple([.2]*24),0)
    power=FrozenPowerModel(.1,.2,{'A':8,'B':8},.95,
        lambda it,w:np.asarray(it)+w['cooling_fixture'],'FIXTURE_C1_ONLY')
    result=run_actual({'A':8,'B':8},[pending],Environment(
        {'submitted':900,'background-A':1900,'background-B':4600},
        {'background-A':900,'background-B':3600}),arm='B1',qos_window_provider=provider(),
        frozen_policy=loaded,running=[(job,job.source_site,-1000) for job in backgrounds],
        begin=0,end=4500,forecast=book,power_model=power,
        weather=[{'cooling_fixture':.03}]*5,expected_bindings=policy.bindings)
    row=next(r for r in result['queue_ledger'] if r['job_uid']=='submitted')
    assert row['admitted_time']==900 and row['policy_action']=='DELAY'
    assert row['completion_observed_time']==1800 and row['intentional_delay_seconds']==900
    cc4=result['cc4_depletion_ledger']
    assert len(cc4)==1 and cc4[0]['uid']=='submitted' and cc4[0]['depletion_count']==1
    assert not cc4[0]['anonymous_forecast_is_physical']
    rule=next(r for r in result['rule_consumption_receipt'] if r['uid']=='submitted')
    assert rule['policy_action']=='DELAY_15' and rule['rule_id'] and rule['policy_sha']==loaded.sha
    assert rule['online_grid_horizon_evaluations']==0
    assert result['physical']['IT_recomputed_from_actual_occupation']
    assert not result['physical']['planning_power_copied']
    assert np.array_equal(result['occupancy_GPU'][:2],[[1,1],[1,1]])
    assert result['receipt']['optimizer_calls']==0
    budget=next(r for r in result['qos_ledger'] if r['uid']=='submitted')
    assert budget['total_intentional_burden_seconds']==900


def test_ranked_migration_hook_preserves_matching_frozen_phases_and_service_power():
    policy=migration_policy();moving,background=initial_jobs()
    power=FrozenPowerModel(.1,.2,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'FIXTURE_C1_ONLY')
    result=run_actual({'A':8,'B':8},[],Environment({'moving':6900,'background':10000},
        {'moving':6000,'background':9000}),arm='B3',qos_window_provider=provider(),frozen_policy=policy,
        running=[(moving,'A',-900),(background,'B',-1000)],begin=0,end=9600//900*900,
        wan_capacities={'AB':100},power_model=power,weather=[{}]*10)
    migrations=[r for r in result['migration_receipts'] if r['job_id']=='moving']
    assert len(migrations)==1
    migration=migrations[0]
    assert migration['physical_checkpoint_seconds']==900
    assert migration['control_checkpoint_seconds']==900
    assert migration['interruption_seconds']==1800
    assert migration['accumulated_compute_seconds']==1800
    assert migration['policy_rule_id'] and migration['policy_sha']==policy.sha
    ledger=next(r for r in result['queue_ledger'] if r['job_uid']=='moving')
    assert ledger['migration_count']==1
    assert ledger['accumulated_compute_seconds']==6900
    assert ledger['completion_observed_time']==7800
    rules=[r for r in result['rule_consumption_receipt'] if r['uid']=='moving']
    assert any(r['action']=='CHECKPOINT_MIGRATE' and r['observed_at_seconds']==900 for r in rules)
    assert all(r['Event30_activation'].startswith('NOT_AUTHORIZED') for r in rules)
    assert result['physical']['IT_recomputed_from_actual_occupation']
    assert not np.array_equal(result['occupancy_GPU'][:,0],result['occupancy_GPU'][:,1])


def test_observed_resource_outside_literal_scenario_support_blocks_ranked_action():
    policy=migration_policy();moving,background=initial_jobs()
    extra=request('excess',submit=-2000,q50=900,source_site='B',qos='normal',protected=False,
        requested_walltime_seconds=3600,compatible=('B',),elapsed_compute_seconds=1000)
    result=run_actual({'A':8,'B':8},[],Environment({'moving':7700,'background':10000,'excess':10000},
        {'moving':6000,'background':9000,'excess':9000}),arm='B1',qos_window_provider=provider(),
        frozen_policy=policy,running=[(moving,'A',-900),(background,'B',-1000),(extra,'B',-1000)],
        begin=0,end=1800,wan_capacities={'AB':100})
    assert not result['migration_receipts']
    rule=next(r for r in result['rule_consumption_receipt'] if r['uid']=='moving')
    assert rule['reason']=='OBSERVED_RESOURCE_OUTSIDE_FROZEN_TEMPLATE_SUPPORT'
    assert rule['outside_support_sites']==['B'] and not rule['grid_safety_guaranteed']
    assert rule['observed_GPU_by_site']=={'A':1,'B':2}


@pytest.mark.parametrize('arm',['B0','B2'])
def test_nonflexible_arms_do_not_call_ranked_migration_or_activate_event30(arm):
    policy=migration_policy();moving,background=initial_jobs()
    result=run_actual({'A':8,'B':8},[],Environment({'moving':7700,'background':10000},
        {'moving':6000,'background':9000}),arm=arm,qos_window_provider=provider(),frozen_policy=policy,
        running=[(moving,'A',-900),(background,'B',-1000)],begin=0,end=1800,wan_capacities={'AB':100})
    assert not result['migration_receipts'] and not result['rule_consumption_receipt']


def test_known_frozen_stay_command_not_replaced_by_unknown_ranking():
    policy=migration_policy();moving,background=initial_jobs()
    moving=type(moving)(moving.uid,moving.submit,moving.gpu,moving.compatible,moving.q50,
        moving.source_site,dict(moving.metadata,origin_unknown=False))
    result=run_actual({'A':8,'B':8},[],Environment({'moving':7700,'background':10000},
        {'moving':6000,'background':9000}),arm='B3',qos_window_provider=provider(),frozen_policy=policy,
        known_schedule={'moving':dict(site='A',start_seconds=-900)},
        running=[(moving,'A',-900),(background,'B',-1000)],begin=0,end=1800,wan_capacities={'AB':100})
    assert not result['migration_receipts']
    assert any(r.get('reason')=='KNOWN_FROZEN_STAY_COMMAND' for r in result['job_event_ledger'] if r['uid']=='moving')


def test_serial_admission_snapshot_matches_full_episode_readback_each_whole_gang(monkeypatch):
    capacities={'A':3,'B':2}
    from v42_integration.policy import compile_policy
    policy=compile_policy([dict(site=site,slot_start=0,slot_end=900,gpu_capacity=cap,
        source_variable='FIXTURE',carryout_end=900) for site,cap in capacities.items()],
        dict(science_sha='science',qos_sha='qos',case_sha='case',aidc_anchor='aidc',mess_anchor='mess'),
        {(site,0):[0.] for site in capacities})
    monkeypatch.setattr(policy,'resource_support_at',lambda now:dict(
        lower_by_site={'A':0,'B':0},upper_by_site=capacities,
        source_sha='FIXTURE_LITERAL_CAPACITY_SUPPORT',scenario_ids=['FIXTURE']),raising=False)
    controller=JobEventController(capacities,arm='B1',qos_window_provider=qos(),frozen_policy=policy)
    jobs=[request(str(i),gpu=gpu,qos='normal',protected=False,requested_walltime_seconds=3600,
                  can_prestart_place=True)
          for i,gpu in enumerate((2,1,2))]
    for job in jobs:controller.submit(job,0)
    full_read=controller.ledger.physical;original_guard=controller._policy_resource_guard
    observations=[];calls=[]
    def counted_physical(now):
        calls.append(now)
        return full_read(now)
    def audited_guard(now,**kwargs):
        assert kwargs['observed_use']==full_read(now)
        result=original_guard(now,**kwargs)
        observations.append(result[1])
        return result
    monkeypatch.setattr(controller.ledger,'physical',counted_physical)
    monkeypatch.setattr(controller,'_policy_resource_guard',audited_guard)
    assert controller.admit(0)==['0','1','2']
    # One admission-pass read plus the inherited safety read inside every
    # EpisodeLedger.start; no per-UID duplicate controller/guard reads remain.
    assert calls==[0]*4 and full_read(0)=={'A':3,'B':2}
    # Stored diagnostic dicts must not change when the pass snapshot advances.
    assert [r['observed_GPU_by_site'] for r in observations]==[
        {'A':0,'B':0},{'A':2,'B':0},{'A':3,'B':0}]
    assert not controller.pending
