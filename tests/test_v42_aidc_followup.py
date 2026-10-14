"""Native0 causal physical counterexamples; no May performance claims."""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from v42_capacity.actual import Environment
from v42_final.workload import ForecastBook
from v42_integration.actual import FrozenPowerModel,run_actual
from v42_integration.aidc_sensitivity_runtime import (CURRENT_EVENT_CONTRACT,
    CurrentEventSensitivityPolicy,CurrentEventJobEventController)
from v42_integration.aidc_resource_bridge import PlanningActualResourceBridge,audit_planning_capacity,IDENTITY_FIELDS
from v42_integration.policy import digest
from v42_integration.trajectory_tracking import TrackingReference
from v42_integration.unified_contract import BINDING_FIELDS
from test_v42_integration_actual import qos,request
from test_v42_aidc_sensitivity_runtime import example


def current_fixture(*,commands=None,basic=True,runtime=False,signed=False):
    _,_,_,template,_=example(two_lines=True)
    packet=deepcopy(template.packet);base=qos()
    provider=type(base)(base.stats,case_sha=digest('CURRENT_NAMED_CASE'),provider_sha=base.provider_sha)
    bindings={k:digest('CURRENT_EVENT_NAMED:'+k) for k in BINDING_FIELDS}
    bindings.update(case_sha=provider.case_sha,qos_sha=provider.stats.sha)
    packet.bindings=bindings
    if not signed:
        for t,c in enumerate(packet.coefficients):
            c.current_matrix[:]=0;c.current_constant[:]=.1
            packet.correction[t][:]=0;packet.bias[t][:]=.1
    zero=np.zeros((96,2))
    reference=TrackingReference(zero,zero,zero,zero,zero,sites=packet.sites,begin=0,
        commands=commands or {},identity={'evidence_scope':'NAMED_CURRENT_EVENT_PHYSICAL'})
    gate=dict(status='PASS',controller_contract=CURRENT_EVENT_CONTRACT,
        basic_allocation_and_corrective_fixture_PASS=True,evidence_scope='NAMED_NATIVE0')
    policy=CurrentEventSensitivityPolicy(reference,packet,bindings=bindings,expected_bindings=bindings,
        basic=basic,evidence_scope='NAMED_CURRENT_EVENT_PHYSICAL',runtime_repair=runtime,
        runtime_fixture_gate=gate if runtime else None)
    return provider,policy


def ready_data(**updates):
    data=dict(source_sha=digest('NAMED_SOURCE_DATA_READY'),observed_at_seconds=0,
        authorized_destinations=['B'],ready_at_seconds={'B':0})
    data.update(updates)
    return data


def known(uid='K',**updates):
    return request(uid,gpu=8,q50=900,origin_unknown=False,can_prestart_place=True,
        qos='normal',protected=False,reference_start_seconds=0,**updates)


def run_witness(*,data=True,alternative=True,runtime=False,transfer=False,wan_capacity=1000):
    commands={'K':dict(site='A',start_seconds=900,protected_segments=[
        dict(resource='gpu:A',begin=900,end=1800,quantity=8)])}
    provider,policy=current_fixture(commands=commands,runtime=runtime)
    proof=ready_data() if data else None
    if transfer:
        proof=ready_data();proof.update(ready_at_seconds={},payload_bytes=90000,bandwidth_bytes_per_second=100,
            preparation_seconds=300,wan_path_by_destination={'B':'AB'})
    k=known(compatible=('A','B') if alternative else ('A',),preplacement_data=proof)
    u=request('U',gpu=8,q50=450,compatible=('A',),qos='normal',protected=False,
        reference_start_seconds=0)
    power=FrozenPowerModel(.1,1.,{'A':8,'B':8},.95,lambda it,weather:np.asarray(it),'NAMED_ORIGINAL_C1')
    return run_actual({'A':8,'B':8},[u,k],Environment({'U':2250,'K':900}),begin=0,end=4500,
        arm='B1',qos_window_provider=provider,frozen_policy=policy,known_schedule=commands,
        controller_class=CurrentEventJobEventController,expected_bindings=policy.bindings,
        wan_capacities={'AB':wan_capacity},power_model=power,weather=[{}]*5),policy


def test_future_known_is_not_unknown_admission_veto_then_actual_conflict_corrects():
    result,policy=run_witness()
    rows={r['job_uid']:r for r in result['queue_ledger']}
    assert rows['U']['admitted_time']==0 and rows['U']['site']=='A'
    assert rows['K']['admitted_time']==900 and rows['K']['site']=='B'
    assert rows['U']['completion_observed_time']==2250
    state=result['carryout']['controller']['current_event_state']
    assert state['planning_commands']['K']['site']=='A'
    assert state['planning_commands']['K']['start_seconds']==900
    assert state['actual_corrective_commands']['K']['actual_start_seconds']==900
    assert state['actual_corrective_commands']['K']['GPU_capacity_conflict']
    assert result['receipt']['optimizer_calls']==0
    assert not result['reservation_ledger']['future_Known_GPU_admission_veto']
    assert all(w['future_grid_rows_evaluated']==0 for w in policy.current_candidates)
    assert not any(d['decision'].get('reason')=='UNKNOWN_UNBOUNDED_RUNTIME_KNOWN_FIRM_BOOKING' for d in policy.audit)
    np.testing.assert_allclose(result['physical']['IT_kw'],.8+result['occupancy_GPU'])


@pytest.mark.parametrize('data,alternative',[(False,True),(True,False)])
def test_corrective_failure_queues_without_eviction_or_plan_retiming(data,alternative):
    result,_=run_witness(data=data,alternative=alternative)
    rows={r['job_uid']:r for r in result['queue_ledger']}
    assert rows['U']['completion_observed_time']==2250
    assert rows['K']['admitted_time']==2700 and rows['K']['site']=='A'
    state=result['carryout']['controller']['current_event_state']
    assert not state['actual_corrective_commands']
    assert state['Known_actual_audit'][0]['actual_start_delay_seconds']==1800
    assert state['planning_commands']['K']['start_seconds']==900


def test_preplacement_waits_for_real_transfer_preparation_and_rechecks_grid():
    result,_=run_witness(transfer=True)
    rows={r['job_uid']:r for r in result['queue_ledger']}
    correction=result['carryout']['controller']['current_event_state']['actual_corrective_commands']['K']
    assert correction['trigger_seconds']==900
    assert correction['transfer_seconds']==900 and correction['preparation_seconds']==300
    assert correction['ready_at_seconds']==2700 and rows['K']['admitted_time']==2700
    assert correction['qos_preparation_budget_used_seconds']==1800
    assert rows['K']['site']=='B'
    assert result['occupancy_GPU'][1,1]==0 and result['occupancy_GPU'][2,1]==0


def test_wan_capacity_failure_is_reported_and_original_job_survives():
    result,_=run_witness(transfer=True,wan_capacity=50)
    state=result['carryout']['controller']['current_event_state']
    assert not state['actual_corrective_commands']
    assert any(r.get('reason')=='NO_CAPACITY' for row in state['corrective_audit']
        for r in row.get('rejected_candidates',[]))
    assert next(r for r in result['queue_ledger'] if r['job_uid']=='K')['admitted_time']==2700


def test_known_without_actual_conflict_keeps_original_site():
    provider,policy=current_fixture(commands={'K':dict(site='A',start_seconds=900)})
    result=run_actual({'A':8,'B':8},[known(preplacement_data=ready_data())],Environment({'K':900}),
        begin=0,end=2700,arm='B1',qos_window_provider=provider,frozen_policy=policy,
        known_schedule=policy.reference.commands,controller_class=CurrentEventJobEventController)
    state=result['carryout']['controller']['current_event_state']
    assert not state['actual_corrective_commands'] and not state['conflict_attempts']
    assert state['Known_actual_audit'][0]['actual_site']=='A'


def test_current_committed_gpu_is_checked_without_future_known_veto():
    provider,policy=current_fixture(commands={'K':dict(site='A',start_seconds=1800,
        protected_segments=[dict(resource='gpu:A',begin=1800,end=2700,quantity=8)])})
    controller=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule=policy.reference.commands)
    u=request('U',gpu=8,compatible=('A',),reference_start_seconds=0)
    controller.submit(u,0);policy.observe(0,{'A':0,'B':0},controller.metadata)
    assert controller.reservations.reserve('COMMITTED',[dict(resource='gpu:A',begin=0,end=900,quantity=1)])[0]
    assert controller.admit(0)==[]
    assert controller.decisions['U']['reason']=='GPU_CAPACITY_RUNNING_RETAINED'


def test_runtime_overrun_hold_and_offgrid_short_completion_release():
    result,_=run_witness(runtime=True)
    state=result['carryout']['controller']['current_event_state']
    assert any(e['event']=='OVERRUN_RUNNING_HOLD' and e['uid']=='U' for e in state['runtime_events'])
    provider,policy=current_fixture(runtime=True)
    u=request('SHORT',gpu=8,q50=1800,compatible=('A',),reference_start_seconds=0)
    v=request('WAIT',gpu=8,q50=900,compatible=('A',),reference_start_seconds=0)
    result=run_actual({'A':8,'B':8},[u,v],Environment({'SHORT':100,'WAIT':900}),begin=0,end=2700,
        arm='B1',qos_window_provider=provider,frozen_policy=policy,controller_class=CurrentEventJobEventController)
    rows={r['job_uid']:r for r in result['queue_ledger']}
    assert rows['SHORT']['release_control_time']==100
    assert rows['WAIT']['admitted_time']==900
    assert result['occupancy_GPU'][0,0]==pytest.approx(8*100/900)
    state=result['carryout']['controller']['current_event_state']
    assert any(e['event']=='RUNTIME_SHORT_COMPLETION' for e in state['runtime_events'])
    assert any(e['uid']=='WAIT' and e['feasible'] for e in state['backfill_results'])


def test_runtime_gate_prevents_unvalidated_activation():
    provider,policy=current_fixture()
    with pytest.raises(ValueError,match='RUNTIME_CONTROL_REQUIRES'):
        CurrentEventSensitivityPolicy(policy.reference,policy.packet,bindings=policy.bindings,
            expected_bindings=policy.bindings,evidence_scope='NAMED',runtime_repair=True)


def test_current_all_lines_minimax_and_policy_reload(tmp_path):
    provider,policy=current_fixture(basic=False,signed=True)
    controller=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule={})
    u=request('U',can_prestart_place=True,reference_start_seconds=0)
    controller.submit(u,0)
    assert controller.admit(0)==['U'] and controller.audit['U']['site']=='B'
    assert controller.decisions['U']['tracking']['grid_peak']==pytest.approx(.6)
    policy.save(tmp_path/'current.json')
    reloaded=CurrentEventSensitivityPolicy.load(tmp_path/'current.json',bindings=policy.bindings).bind_runtime_packet(policy.packet)
    assert reloaded.controller_contract==CURRENT_EVENT_CONTRACT


def bridge_fixture():
    sites=('A','B');zeros={s:[0.]*96 for s in sites};nominal=deepcopy(zeros);nominal['A'][0]=4.
    achieved=deepcopy(zeros);achieved['B'][0]=1.
    a=dict(FULL_feasible=True,FULL_max_residual=0,case_sha=digest('A_CASE'),aidc_anchor=digest('A_ANCHOR'),
        resource_sites=list(sites),known_site_GPU=deepcopy(zeros),nominal_site_GPU=nominal,
        reserve_site_GPU=deepcopy(achieved),achieved_CC4_reserve_site_GPU=achieved,
        achieved_runtime_reserve_site_GPU=deepcopy(zeros),CC4_reserve_shortfall_GPU_slots=9.,
        runtime_reserve_shortfall_GPU_slots=2.,CC4_service={'(0, 0)':1.},CC4_carryout={str(h):0. for h in range(24)})
    q50=[1.]+[0.]*23;q90=[2.]+[0.]*23
    identity={k:digest('BRIDGE:'+k) for k in IDENTITY_FIELDS};identity['stage_case_sha']=a['case_sha']
    authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha=identity['cc4_sha'],
        kernel_sha=digest('KERNEL'),timing_envelope_sha=digest('CDF'),aidc_anchor=a['aidc_anchor'])
    args=dict(identity=identity,expected_identity=deepcopy(identity),capacities={'A':8,'B':8},
        q50=q50,q90=q90,timing_lower=[1.],timing_upper=[1.],cc4_source_authority=authority,
        begin_seconds=0,required_site_count=2)
    return a,args


def test_saved_known_unknown_achieved_reserve_capacity_not_target_reserve():
    a,args=bridge_fixture();a['known_site_GPU']['A'][0]=3
    a['reserve_site_GPU']['A'][0]=100
    _,audit=audit_planning_capacity(a,args['capacities'],required_site_count=2)
    assert audit['status']=='PASS' and audit['CC4_reserve_shortfall_GPU_slots']==9
    a['achieved_CC4_reserve_site_GPU']['A'][0]=2
    with pytest.raises(ValueError,match='PLANNING_CAPACITY_VIOLATION'):
        audit_planning_capacity(a,args['capacities'],required_site_count=2)


def test_forecast_observed_physical_and_completed_carry_service_are_separate():
    provider,policy=current_fixture()
    a,args=bridge_fixture()
    for k in ('science_sha','initial_state_sha','time_axis_sha','cc4_sha','runtime_sha'):
        args['identity'][k]=policy.bindings[k];args['expected_identity'][k]=policy.bindings[k]
    args['cc4_source_authority']['prediction_sha']=policy.bindings['cc4_sha']
    a['aidc_anchor']=args['cc4_source_authority']['aidc_anchor']=policy.bindings['aidc_anchor']
    bridge=PlanningActualResourceBridge(a,**args)
    controller=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule={},resource_bridge=bridge,actual_identity=args['identity'])
    u=request('U',gpu=2,q50=900,reference_start_seconds=0)
    controller.submit(u,0)
    assert bridge.book.consumed[0]==.5
    before=bridge.snapshot(0,controller.metadata,controller.reservations)
    assert before['remaining_CC4_Q50_GPUh']==.5
    assert before['actual_Running_GPU']=={'A':0.,'B':0.}
    assert before['not_yet_arrived_forecast_GPU_96'][0]==[2.,0.]
    assert controller.admit(0)==['U']
    after=bridge.snapshots[-1]
    assert after['actual_Running_GPU']=={'A':2.,'B':0.}
    assert not after['physical_GPU_includes_forecast']
    with pytest.raises(ValueError,match='DEBITED_ONCE'):bridge.observe(controller.metadata['U'],0)
    controller.ledger.complete('U',600,600);controller.metadata['U'].update(state='COMPLETED',accumulated_compute_seconds=600)
    after=bridge.snapshot(600,controller.metadata,controller.reservations)
    assert after['observed_Unknown_completed_actual_GPUh']==pytest.approx(1/3)
    assert after['carry_remaining_actual_GPUh'] is None
    assert bridge.source==a


@pytest.mark.parametrize('field',IDENTITY_FIELDS)
def test_resource_bridge_rejects_mixed_source_case_science_initial_axis(field):
    a,args=bridge_fixture();args['expected_identity'][field]=digest('MISMATCH')
    with pytest.raises(ValueError,match='SAME_CASE_PLANNING_ACTUAL_IDENTITY'):
        PlanningActualResourceBridge(a,**args)


def test_resource_bridge_preserves_and_requires_shortfall_and_full_authority():
    a,args=bridge_fixture();del a['runtime_reserve_shortfall_GPU_slots']
    with pytest.raises(ValueError,match='SHORTFALL_MUST_BE_EXPLICIT'):PlanningActualResourceBridge(a,**args)
    a,args=bridge_fixture();a['FULL_feasible']=False
    with pytest.raises(ValueError,match='SAME_CASE_A1_NOT_CERTIFIED'):PlanningActualResourceBridge(a,**args)
    a,args=bridge_fixture();args['required_site_count']=12
    with pytest.raises(ValueError,match='EXACT_SITE_AXIS'):PlanningActualResourceBridge(a,**args)


def test_active_controller_rejects_diagnostic_fcfs_known():
    commands={'K':dict(site='A',start_seconds=0,
        execution_rule='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL')}
    provider,policy=current_fixture(commands=commands)
    with pytest.raises(ValueError,match='DIAGNOSTIC_FCFS'):
        CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
            frozen_policy=policy,known_schedule=commands)


@pytest.mark.parametrize('bad_value',[float('nan'),float('inf'),-1,0,1.5])
def test_resource_bridge_capacity_fails_closed(bad_value):
    a,args=bridge_fixture();args['capacities']['A']=bad_value
    with pytest.raises(ValueError,match='FINITE_POSITIVE_WHOLE'):
        PlanningActualResourceBridge(a,**args)


@pytest.mark.parametrize('bad_residual',[float('nan'),float('inf'),-1])
def test_resource_bridge_full_residual_fails_closed(bad_residual):
    a,args=bridge_fixture();a['FULL_max_residual']=bad_residual
    with pytest.raises(ValueError,match='SAME_CASE_A1_NOT_CERTIFIED'):
        PlanningActualResourceBridge(a,**args)


def test_resource_bridge_cannot_be_attached_to_another_actual_case():
    a,args=bridge_fixture();bridge=PlanningActualResourceBridge(a,**args)
    provider,policy=current_fixture()
    with pytest.raises(ValueError,match='RESOURCE_BRIDGE_CURRENT_POLICY_IDENTITY_DRIFT'):
        CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
            frozen_policy=policy,known_schedule={},resource_bridge=bridge,actual_identity=args['identity'])


def test_source_data_watermark_and_byte_units_are_required():
    provider,policy=current_fixture(commands={'K':dict(site='A',start_seconds=900)})
    c=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule=policy.reference.commands,wan_capacities={'AB':100})
    c.submit(known(preplacement_data=ready_data()),0)
    c.metadata['K']['preplacement_data']['observed_at_seconds']=float('nan')
    assert c._preparation('K','B',0)[1]=='SOURCE_DATA_PREPARATION_AUTHORITY_MISSING'
    c.metadata['K']['preplacement_data']=dict(source_sha=digest('SOURCE'),observed_at_seconds=0,
        authorized_destinations=['B'],ready_at_seconds={},payload_GB=900,bandwidth_GBps=1,
        preparation_seconds=0,wan_path_by_destination={'B':'AB'})
    assert c._preparation('K','B',0)[1]=='SOURCE_TRANSFER_TIME_WAN_AUTHORITY_MISSING'


def test_runtime_backfill_checks_selected_destination_and_may_select_safe_alternative():
    commands={'FUTURE':dict(site='B',start_seconds=1800,protected_segments=[
        dict(resource='gpu:B',begin=1800,end=2700,quantity=8)])}
    provider,policy=current_fixture(commands=commands,basic=False,runtime=True,signed=True)
    c=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule=commands)
    c.submit(request('U',can_prestart_place=True,reference_start_seconds=0),0)
    c.released_since_control=['SHORT_COMPLETED']
    assert c.admit(0)==['U']
    assert c.audit['U']['site']=='A'
    assert any(r['site']=='B' and not r['feasible'] for r in c.backfill_audit)


def test_unvalidated_conditional_remaining_after_q50_is_explicit_unknown():
    from v42_integration.aidc_sensitivity_runtime import conditional_remaining_runtime
    remaining=conditional_remaining_runtime(dict(t50_seconds=900,accumulated_compute_seconds=1800,state='RUNNING'))
    assert remaining['conditional_remaining_Q90_seconds'] is None
    assert remaining['running_hold_required'] and not remaining['quantile_is_completion_guarantee']


def test_current_runner_requires_certified_handoff_before_reading_arguments():
    from v42_integration.aidc_sensitivity_runtime import run_current_event_actual
    _,policy=current_fixture()
    class PrivateBankMustNotBeRead:
        def get(self,*args):raise AssertionError('Future Actual bank read before handoff')
    with pytest.raises(ValueError,match='SAME_CASE_PLANNING_ACTUAL_HANDOFF_NOT_CERTIFIED'):
        run_current_event_actual(PrivateBankMustNotBeRead(),frozen_policy=policy,resource_bridge=None,
            expected_bindings=policy.bindings,handoff_gate={'status':'NOT_CERTIFIED'})


def test_current_b3_controller_preserves_arm_without_actual_global_optimizer():
    provider,policy=current_fixture()
    c=CurrentEventJobEventController({'A':8,'B':8},arm='B3',qos_window_provider=provider,
        frozen_policy=policy,known_schedule={})
    c.submit(request('U',reference_start_seconds=0),0)
    assert c.admit(0)==['U']
    assert c.arm=='B3' and c.snapshot(0)['current_event_state']['actual_global_MILP_calls']==0


def test_current_unknown_reference_fcfs_wait_is_not_source_release_veto():
    provider,policy=current_fixture()
    c=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule={})
    c.submit(request('U',reference_start_seconds=5400,release_seconds=0,
        hard_earliest_start_seconds=0),0)
    assert c.admit(0)==['U']
    assert c.budgets['U'].reference_start_seconds==5400
    assert c.audit['U']['intentional_delay_seconds']==0


def test_current_unknown_still_obeys_explicit_source_release():
    provider,policy=current_fixture()
    c=CurrentEventJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule={})
    c.submit(request('U',reference_start_seconds=0,release_seconds=900),0)
    assert c.admit(0)==[] and c.admit(900)==['U']


def test_current_planning_binding_keeps_original_four_stage_engines_and_fails_before_actual_bank():
    from test_v42_aidc_sensitivity_runtime import binding_fixture
    from v42_integration.aidc_sensitivity_runtime import bind_current_event_planning
    case,jobs,shared,calls=binding_fixture()
    bound=bind_current_event_planning(case,jobs,shared)
    assert bound.research_contract_binding['active_Actual_controller']==CURRENT_EVENT_CONTRACT
    assert bound.research_contract_binding['legacy_Actual_runner_active'] is False
    a1=bound.make_a_case('B3','A1',bound.initial_mess,None)
    m1=bound.make_m_case('B3','M1',{'aidc_anchor':digest('A1_RESULT')},None)
    a2=bound.make_a_case('B3','A2',{'plan_sha':digest('M1_RESULT')},None)
    m2=bound.make_m_case('B3','M2',{'aidc_anchor':digest('A2_RESULT')},None)
    assert [r[0] for r in calls]==['A1','A1','M1','A2','M2']
    assert a1.window_slots['K'] and a2.window_slots['K']
    with pytest.raises(ValueError,match='FINAL_CURRENT_EVENT_A_STAGE_POLICY_NOT_FROZEN'):
        bound.prepare_research_actual_arguments()
    with pytest.raises(ValueError,match='SAME_CASE_A1_NOT_CERTIFIED'):
        bound.control_policy_factory(aidc={'FULL_feasible':False})
    with pytest.raises(ValueError,match='SUPERVISOR_SAVED_PLANNING_RUNNER_REQUIRED'):
        bound.unified_actual_runner()


def test_missing_independent_handoff_does_not_read_actual_bank_even_after_current_policy_freeze(monkeypatch):
    from types import SimpleNamespace
    from v42_integration.aidc_sensitivity_runtime import bind_current_event_planning
    a,args=bridge_fixture();_,old=current_fixture()
    old.bindings['aidc_anchor']=a['aidc_anchor'];old.packet.bindings=old.bindings
    z=np.zeros((96,2));nominal=np.asarray([a['nominal_site_GPU'][s] for s in ('A','B')]).T
    identity=dict(CC4_Q50=args['q50'],CC4_Q90=args['q90'],Timing_CDF_Q10=[1.],Timing_CDF_Q90=[1.],
        CC4_source_authority=dict(args['cc4_source_authority'],prediction_sha=old.bindings['cc4_sha']))
    old.reference=TrackingReference(z,nominal,z,z,z,sites=('A','B'),begin=0,commands={},identity=identity)
    reads=[]
    def legacy_bind(case,*ignored):
        case.control_policy_factory=lambda **kwargs:old
        case.prepare_research_actual_arguments=lambda:reads.append('PRIVATE_BANK_READ')
        case.research_contract_binding={}
        return case
    monkeypatch.setattr('v42_integration.aidc_sensitivity_runtime.bind_unified_planning',legacy_bind)
    case=SimpleNamespace(evidence_kind='NAMED_FIXTURE',planning_slot_zero_seconds=-21600,
        source_freeze={'source_sha':digest('INDEPENDENT_SOURCE')})
    bound=bind_current_event_planning(case,{}, {})
    policy=bound.control_policy_factory(aidc=a)
    assert isinstance(policy,CurrentEventSensitivityPolicy)
    authority=policy.spec['site_authority']
    assert authority['source_customer_permission_claim'] is False
    assert authority['Known_corrective_permission_granted'] is False
    assert authority['candidate_axis']=='SOURCE_COMPATIBLE_SITES_ONLY' and authority['max_sites']==12
    assert policy._study_site_authorized(dict(uid='U',origin_unknown=True,state='PENDING',can_prestart_place=False))
    assert not policy.corrective_allowed(dict(uid='K',origin_unknown=False,state='PENDING',can_prestart_place=False))
    assert bound.research_contract_binding['Unknown_site_authority_sha']==digest(authority)
    with pytest.raises(ValueError,match='CURRENT_EVENT_SUPERVISOR_HANDOFF_FACTORY_REQUIRED'):
        bound.prepare_research_actual_arguments()
    assert not reads


def test_current_case_default_loader_uses_followup_contract_and_keeps_explicit_manifest(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from v42_integration.aidc_sensitivity_runtime import build_current_event_case
    from v42_integration.followup_contract import load_followup_contracts,REPORT
    from v42_integration.unified_contract import load_contracts
    import json
    shared=load_followup_contracts()
    interface=json.loads((REPORT/'UNIFIED_INTERFACE_CONTRACT.json').read_text(encoding='utf8'))
    assert shared['bindings']['interface_sha']==digest(interface)
    assert interface['policy']=='CURRENT_EVENT_UNKNOWN_PENDING_KNOWN_CORRECTIVE'
    assert shared['bindings']['interface_sha']!=load_contracts()['bindings']['interface_sha']
    received=[]
    case=SimpleNamespace(qos_provider=object())
    monkeypatch.setattr('v42_integration.production_case.build_integration_case',lambda **kwargs:case)
    monkeypatch.setattr('v42_integration.production_case.read',lambda path:{})
    monkeypatch.setattr('v42_integration.partial_canary.source_known_records',lambda *args:{})
    def binding(target,records,manifest,**kwargs):
        received.append(manifest)
        return target
    monkeypatch.setattr('v42_integration.aidc_sensitivity_runtime.bind_current_event_planning',binding)
    assert build_current_event_case(tmp_path/'DEFAULT') is case
    assert received[0]==shared
    explicit={'NAMED_EXPLICIT_CALLER_MANIFEST':'PRESERVE_OBJECT'}
    assert build_current_event_case(tmp_path/'EXPLICIT',shared_manifest=explicit) is case
    assert received[1] is explicit
