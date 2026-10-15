"""Native0 ranking-only and exact historical fallback counterexamples."""
from copy import deepcopy
from dataclasses import replace

import pytest
from v42_capacity.actual import Environment
from v42_integration.actual import run_actual
from v42_integration.isolated_unknown import (RankingOnlyPolicy,IsolatedReferenceController,
    reclassify_initial,original_driver,SCOPE)
from test_v42_aidc_followup import current_fixture,ready_data
from test_v42_integration_actual import request


def fixture(label,*,commands=None):
    provider,old=current_fixture(commands=commands,basic=False,signed=True)
    policy=RankingOnlyPolicy(old.reference,old.packet,ranking=label,
        bindings=old.bindings,expected_bindings=old.bindings,evidence_scope='NAMED_ISOLATED_NATIVE0')
    return provider,policy


def controller(provider,policy):
    return IsolatedReferenceController({'A':8,'B':8},arm='B3',qos_window_provider=provider,
        frozen_policy=policy,known_schedule=policy.reference.commands)


def test_ranking_only_same_state_generates_identical_candidates():
    snapshots=[];decisions=[]
    for label in ('C0','C1'):
        provider,policy=fixture(label);c=controller(provider,policy)
        r=request('U',origin_unknown=True,gpu=1,q50=900,compatible=('A','B'),
            can_prestart_place=True,preplacement_data=ready_data())
        c.submit(r,0);policy.observe(0,{'A':0,'B':0},c.metadata)
        decisions.append(policy.select(c.metadata['U'],c.budgets['U'],0,c.reservations,reserve=False))
        snapshots.append(policy.candidate_events[-1])
    assert snapshots[0]==snapshots[1]
    assert all(r['feasible'] for r in snapshots[0]['candidates'])
    assert decisions[0]['site']=='A'
    feasible=snapshots[0]['candidates']
    assert decisions[1]['site']==min(feasible,key=lambda r:(r['grid_peak'],r['site']!='A',r['site']))['site']


@pytest.mark.parametrize('permission,data,reason',[(False,None,'SOURCE_PREPLACEMENT_AUTHORITY_MISSING'),
    (True,None,'SOURCE_DATA_WAN_PREPARATION_NOT_OBSERVED_READY')])
def test_no_added_permission_or_invented_data_readiness(permission,data,reason):
    provider,policy=fixture('C1');c=controller(provider,policy)
    c.submit(request('U',origin_unknown=True,gpu=1,can_prestart_place=permission,preplacement_data=data),0)
    policy.observe(0,{'A':0,'B':0},c.metadata)
    event=policy.feasible_candidates(c.metadata['U'],c.budgets['U'],0,c.reservations)
    assert next(r for r in event['candidates'] if r['site']=='B')['reason']==reason


def test_common_capacity_guard_retains_current_running_and_ignores_future_booking():
    command={'K':dict(site='A',start_seconds=900,protected_segments=[
        dict(resource='gpu:A',begin=900,end=1800,quantity=8)])}
    provider,policy=fixture('C1',commands=command);c=controller(provider,policy)
    c.submit(request('U',origin_unknown=True,gpu=1,compatible=('A',)),0)
    policy.observe(0,{'A':0,'B':0},c.metadata)
    assert policy.feasible_candidates(c.metadata['U'],c.budgets['U'],0,c.reservations)['candidates'][0]['feasible']
    policy.observe(0,{'A':8,'B':0},c.metadata)
    assert policy.feasible_candidates(c.metadata['U'],c.budgets['U'],0,c.reservations)['candidates'][0]['reason']=='CURRENT_GPU_CAPACITY'


def test_exact_pr223_pre_day_command_falls_back_without_mutating_command():
    commands={'K':dict(site='B',start_seconds=-900)}
    provider,policy=fixture('C0',commands=commands);c=controller(provider,policy)
    c.submit(request('K',origin_unknown=False,gpu=1,q50=900,dday_initialization_seconds=0),0)
    policy.observe(0,{'A':0,'B':0},c.metadata)
    d=c._known_decision('K',0)
    assert d['status']=='PRE_DDAY_START_COMMAND_NOT_REPLAYED'
    assert d['site']=='A' and d['start_seconds']==0
    assert c.known_schedule==commands and c.historical_commands==commands
    assert c.effective_references['K']['reference_contract'].startswith('PR223_ACTUAL_REFERENCE_FALLBACK')


def test_missing_individual_known_command_still_uses_original_reference():
    provider,policy=fixture('C0');c=controller(provider,policy)
    c.submit(request('K',origin_unknown=False,gpu=1),0)
    policy.observe(0,{'A':0,'B':0},c.metadata)
    d=c._reference_decision('K',0)
    assert d['site']=='A' and d['status']=='CAUSAL_REFERENCE_START'


def test_original_submit_uid_queue_order_has_no_new_known_first_priority():
    provider,policy=fixture('C0');c=controller(provider,policy)
    c.submit(replace(request('U',origin_unknown=True,gpu=1,compatible=('A',)),submit=-10),0)
    c.submit(request('K',origin_unknown=False,gpu=1,compatible=('A',)),0)
    # A later Known must not jump the earlier submit tuple. Independent
    # electrical guards may still keep the second gang in the queue.
    assert c.admit(0)[0]=='U'


def test_private_future_runtime_fields_rejected_before_selection():
    provider,policy=fixture('C1');c=controller(provider,policy)
    c.submit(request('U',origin_unknown=True),0)
    metadata=deepcopy(c.metadata['U']);metadata['actual_runtime_seconds']=10
    policy.observe(0,{'A':0,'B':0},c.metadata)
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        policy.select(metadata,c.budgets['U'],0,c.reservations)


def test_initial_reclassification_preserves_opaque_environment_and_fixed_history():
    class Opaque:
        def __deepcopy__(self,memo):raise AssertionError('private bank copied during public projection')
    a=request('R',origin_unknown=True,gpu=2,q50=900,elapsed_compute_seconds=123,episode_id='episode')
    p=request('P',origin_unknown=True,gpu=1)
    future=replace(request('U',origin_unknown=True),submit=901)
    env=Opaque();args=dict(environment=env,begin=0,running=[(a,'A',-123)],requests=[p,future])
    state=dict(running=[{'uid':'R'}],pending=[{'uid':'P'}],excluded_44uids=[])
    out,audit=reclassify_initial(args,state)
    assert out['environment'] is env and out['running'][0][1:]==('A',-123)
    assert out['running'][0][0].metadata['elapsed_compute_seconds']==123
    assert out['running'][0][0].metadata['episode_id']=='episode'
    assert out['running'][0][0].metadata['origin_unknown'] is False
    assert out['requests'][1] is future and audit['initial_Known']==2
    assert audit['reclassified_initial_Unknown']==2 and audit['initial_forecast_debits']==0


def test_same_engine_forecast_once_per_observed_uid_and_no_initial_debit():
    from v42_final.workload import ForecastBook
    for label in ('C0','C1'):
        provider,policy=fixture(label)
        result=run_actual({'A':8,'B':8},[
            request('K',origin_unknown=False,gpu=1,q50=100),
            replace(request('U',origin_unknown=True,gpu=1,q50=100),submit=10)],
            Environment({'K':100,'U':100}),begin=0,end=1800,arm='B3',qos_window_provider=provider,
            frozen_policy=policy,known_schedule={},controller_class=IsolatedReferenceController,
            forecast=ForecastBook((10.,)*24,(20.,)*24,0),expected_bindings=policy.bindings)
        assert [r['uid'] for r in result['cc4_depletion_ledger']]==['U']
        assert result['receipt']['capacity_violations']==0 and result['receipt']['dropped_jobs']==0
        assert result['receipt']['future_duration_controller_reads']==0
        state=result['carryout']['controller']['isolated_reference_state']
        assert state['Actual_global_MILP_calls']==0
        assert [r['time_seconds'] for r in state['control_tick_timings']]==[0,900]
        assert all(r['wall_seconds']>=0 and r['scope'].startswith('ENTIRE_CONTROLLER_ADMIT')
            for r in state['control_tick_timings'])


def test_real_pr223_driver_receipt_is_exact_and_rule_is_preserved():
    assert original_driver().JobEventController._known_decision.__code__.co_filename.endswith('actual.py')
    assert SCOPE=='PR223_REFERENCE_DIAGNOSTIC_ACTUAL'
