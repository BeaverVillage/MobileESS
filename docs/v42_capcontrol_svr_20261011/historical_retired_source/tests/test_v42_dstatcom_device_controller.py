"""Actual DSS sign/phase/voltage/current/loss and bounded autonomous feedback checks."""
from dataclasses import replace
import math
from unittest.mock import patch

import pytest

from v42_dstatcom.settings import ControllerSettings
from v42_dstatcom.device import SiteSpec, install, bus_voltages
from v42_dstatcom.controller import LocalVoltVarController, droop_q, original_control_state,hysteretic_droop_q,network_observation,_step_is_safe


@pytest.fixture
def engine():
    from v42_regcontrol import authority
    odd,adapter,inventory=authority.compile_verified()
    try:
        yield odd
    finally:
        odd.Basic.ClearAll()


def sta08():
    return SiteSpec('STA08','mess_sta08_pcc',(1,2,3),.48/math.sqrt(3),1500,
        ('mess_sta08_tx',),750,endpoint_id='MESS')


@pytest.mark.parametrize('value,expected',[(.94,1),(.955,1),(.965,1),(.975,0),(1.,0),(1.025,0),(1.035,-1),(1.045,-1),(1.06,-1)])
def test_droop_sign_deadband_and_bounded_saturation(value,expected):
    settings=ControllerSettings();q=droop_q(value,500,settings)
    assert math.copysign(1,q)==expected if expected else q==0
    assert abs(q)<=450


def test_frozen_settings_reject_changed_actual_band_and_unphysical_time_or_gain():
    with pytest.raises(ValueError,match='ORIGINAL_VOLTAGE_BAND'):
        ControllerSettings(actual_voltage_max_pu=1.048)
    with pytest.raises(ValueError,match='DAMPING'):
        ControllerSettings(damping=1)
    with pytest.raises(ValueError):
        ControllerSettings(converter_standby_loss_fraction=0)
    with pytest.raises(ValueError,match='15_MINUTE'):
        LocalVoltVarController([type('D',(),{'spec':sta08(),'settings':ControllerSettings(feedback_step_seconds=10)})()],
            ControllerSettings(feedback_step_seconds=10))
    assert ControllerSettings.from_dict(ControllerSettings().to_dict())==ControllerSettings()


def test_distinct_idc_physical_endpoints_do_not_share_converter_capacity():
    aidc=SiteSpec('IDC01','idc_idc01_pcc',(1,2,3),.48/math.sqrt(3),750,endpoint_id='AIDC')
    mess=replace(aidc,pcc_bus='mess_idc01_pcc',endpoint_id='MESS')
    assert aidc.device_id=='IDC01_AIDC' and mess.device_id=='IDC01_MESS'
    assert SiteSpec.from_dict({**sta08().to_dict(),'inventory_only_annotation':True})==sta08()


def test_schmitt_hysteresis_holds_only_applied_q_in_narrow_strip_and_releases():
    settings=ControllerSettings()
    q,mode=hysteretic_droop_q(1.0252,500,settings,0,0.)
    assert q<0 and mode==-1
    held,mode=hysteretic_droop_q(1.0248,500,settings,mode,q)
    assert held==q and mode==-1
    released,mode=hysteretic_droop_q(1.0245,500,settings,mode,held)
    assert released==0 and mode==0
    assert hysteretic_droop_q(1.0248,500,settings,mode,held)==(0.,0)
    q,mode=hysteretic_droop_q(.9748,500,settings,0,0.)
    assert q>0 and mode==1
    assert hysteretic_droop_q(.9752,500,settings,mode,q)==(q,1)
    assert hysteretic_droop_q(.9755,500,settings,mode,q)==(0.,0)
    assert hysteretic_droop_q(1.06,500,settings,1,q)==(-450.,-1)


def test_nonintegral_anti_windup_discards_saturated_request_on_release():
    settings=ControllerSettings()
    q,mode=hysteretic_droop_q(1.0248,500,settings,-1,-1e9)
    assert q==-450 and mode==-1
    assert hysteretic_droop_q(1.02,500,settings,mode,q)==(0.,0)
    assert hysteretic_droop_q(.94,500,settings,-1,q)==(450.,1)
    with pytest.raises(ValueError,match='BOUNDED_CONTROLLER_STATE'):
        hysteretic_droop_q(1.,500,settings,0,float('nan'))


def test_droop_target_is_separate_from_physical_apparent_current_and_ramp_caps(engine):
    settings=ControllerSettings();device=install(engine,sta08(),settings);engine.Solution.SolveSnap()
    target=droop_q(1.06,device.phase_rating_kva,settings)
    assert target==-450 and device._capacity(1.)>400
    applied=device.apply_q([target,0,0],dt_seconds=1)
    assert applied['applied_Q_supply_kvar'][0]==-50
    applied=device.apply_q([0,0,0],dt_seconds=1)
    assert applied['applied_Q_supply_kvar'][0]==0
    assert len(device.q_state)==3 and all(q==0 for q in device.q_state)


def test_real_original_dss_generator_sign_current_units_phase_and_positive_loss(engine):
    original=set(engine.Circuit.AllElementNames());controls=original_control_state(engine)
    settings=ControllerSettings();device=install(engine,sta08(),settings)
    assert original<=set(engine.Circuit.AllElementNames())
    assert device.installation_receipt['original_service_capacity_not_bypassed']
    assert len(device.names)==3 and len({n['transformer'] for n in device.names})==3
    assert engine.Solution.Convergence()==.0001
    engine.Solution.SolveSnap()
    before=bus_voltages(engine,'mess_sta08_pcc',(1,2,3),sta08().nominal_kv_ln)
    for q in (25.,-25.):
        device.apply_q([q,0,0]);engine.Solution.SolveSnap();result=device.measure()
        phase=result['phases'][0]
        assert result['PASS']
        assert phase['nominal_Q_readback_kvar']==q and phase['nominal_P_readback_kw']==0
        assert phase['Q_supply_kvar']*q>0
        assert abs(phase['Q_supply_kvar']-q)<=phase['power_readback_comparison_tolerance_kva']
        assert abs(phase['converter_current_a']*phase['converter_voltage_pu']*sta08().nominal_kv_ln
            -phase['converter_apparent_kva'])<1e-9
        assert phase['converter_loss_kw']>0 and phase['coupling_transformer_loss_kw']>0
        assert all(abs(p['Q_supply_kvar'])<1e-8 for p in result['phases'][1:])
        assert result['original_service_transformers'][0]['original_winding_kva']==750
        assert result['original_service_transformers'][0]['original_rating_changed'] is False
        assert len(result['original_service_transformers'][0]['windings'])==2
        assert all(w['PASS'] and len(w['actual_phase_current_a'])==3
            for w in result['original_service_transformers'][0]['windings'])
    assert original_control_state(engine)['regulator_settings_SHA']==controls['regulator_settings_SHA']
    assert engine.Solution.Convergence()==.0001


def test_device_current_and_total_apparent_caps_and_ramp_are_real_limits(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap()
    first=device.apply_q([1e9,-1e9,1e9],voltage_pu=[.8,.8,.8],dt_seconds=1)
    assert first['applied_Q_supply_kvar']==[50.,-50.,50.]
    second=device.apply_q([-1e9,1e9,-1e9],voltage_pu=[.8,.8,.8],dt_seconds=1)
    assert second['applied_Q_supply_kvar']==[0.,0.,0.]
    long=device.apply_q([1e9]*3,voltage_pu=[.8]*3,dt_seconds=15)
    for q,power in zip(long['applied_Q_supply_kvar'],long['converter_loss_kw']):
        assert math.hypot(q,power)<=(500*.95)*.8+1e-8
    assert long['total_converter_apparent_kva']<=1500*.9
    assert all(long['Q_saturated'])


def test_real_coupling_transformer_derived_normalamps_readback_failure_is_not_hidden(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap();device.apply_q([25,0,0]);engine.Solution.SolveSnap()
    name=device.names[0]['transformer'];engine.Text.Command('Edit Transformer.'+name+' normhkva=.48')
    result=device.measure()
    assert result['phases'][0]['coupling_transformer_current_rating_a']==pytest.approx(.48/sta08().nominal_kv_ln)
    assert result['phases'][0]['checks']['coupling_transformer_current'] is False
    assert result['PASS'] is False


def test_dss_kvar_accessor_ulp_roundtrip_does_not_hide_nominal_command_drift(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap()
    device.apply_q([-4.310568888804728,0,0]);engine.Solution.SolveSnap()
    phase=device.measure()['phases'][0]
    assert phase['PASS']
    assert abs(phase['nominal_Q_readback_kvar']-phase['Q_command_kvar'])<=2*math.ulp(phase['Q_command_kvar'])
    engine.Generators.Name(device.names[0]['generator']);engine.Generators.kvar(device.q_state[0]+1e-6)
    engine.Solution.SolveSnap()
    phase=device.measure()['phases'][0]
    assert phase['checks']['Q_P_sign_and_constant_power_readback'] is False


def test_actual_added_converter_nameplate_drift_is_not_hidden_by_spec_rating(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap()
    engine.Generators.Name(device.names[0]['generator']);engine.Generators.kVARated(501.)
    phase=device.measure()['phases'][0]
    assert phase['nominal_converter_kva_readback']==501.
    assert phase['checks']['converter_nameplate_kva_unchanged'] is False and phase['PASS'] is False


def test_original_service_winding_rating_drift_and_secondary_overcurrent_fail(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap()
    assert device.measure()['original_service_transformers'][0]['PASS']
    engine.Transformers.Name('mess_sta08_tx');engine.Transformers.Wdg(2);engine.Transformers.kVA(.01)
    engine.Solution.SolveSnap();result=device.measure()
    service=result['original_service_transformers'][0]
    assert service['original_rating_changed'] and service['PASS'] is False and result['PASS'] is False
    assert service['windings'][1]['original_rating_changed']
    assert max(service['windings'][1]['actual_phase_current_a'])>service['windings'][1]['nameplate_phase_current_a']


def test_invalid_actual_bus_or_nominal_ln_voltage_is_rejected(engine):
    with pytest.raises(ValueError,match='BUS_NOT_FOUND|PHASE_NOT_FOUND'):
        install(engine,replace(sta08(),pcc_bus='not_an_existing_bus'))
    with pytest.raises(ValueError,match='NOMINAL_LN_BASE'):
        install(engine,replace(sta08(),nominal_kv_ln=.48))


def test_original_dss_controller_converges_preserves_state_and_counts_extra_solves(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap();settings=ControllerSettings()
    controller=LocalVoltVarController([device],settings,source_SHA='a'*64)
    solution=engine.Solution;solution_class=type(solution);original_solve=solution_class.SolveSnap;counted=[]
    def observe(instance):
        if instance is solution:counted.append(True)
        return original_solve(instance)
    with patch.object(solution_class,'SolveSnap',observe):
        first=controller.settle_slot(engine,0)
        assert first['additional_feedback_solve_count']==len(counted)
    assert first['PASS'] and first['controller_converged'] and first['ControlActionsDone']
    assert first['total_physical_solve_count']==1+first['additional_feedback_solve_count']
    assert first['simulated_feedback_elapsed_seconds'] is None
    assert first['physical_timing_compliance'].startswith('UNKNOWN_STATIC')
    assert first['computational_AC_trial_count']==first['additional_feedback_solve_count']
    assert first['final_fullnetwork']['PASS'] and first['final_fullnetwork']['thermal_violation_count']==0
    assert first['final_devices'][0]['PASS'] and first['original_controls_preserved']
    assert first['Native_optimizer_calls']==0 and first['MESS_PCS_capacity_shared'] is False
    assert first['hysteresis_enabled'] and first['integral_accumulator_present'] is False
    assert first['anti_windup']=='TRACK_LIMITED_APPLIED_COMMAND_NO_UNSATURATED_INTEGRAL_STATE'
    modes={key:list(value) for key,value in first['final_controller_modes_by_device'].items()}
    saved=list(device.q_state);engine.Solution.SolveSnap();second=controller.settle_slot(engine,1)
    assert second['initial_Q_state_by_device'][sta08().device_id]==saved
    assert second['initial_controller_modes_by_device']==modes
    with pytest.raises(ValueError,match='SEQUENTIAL'):
        controller.settle_slot(engine,1)


def test_controller_iteration_failure_remains_visible_despite_electrical_convergence(engine):
    settings=ControllerSettings(maximum_feedback_iterations=1)
    device=install(engine,sta08(),settings);engine.Solution.SolveSnap()
    result=LocalVoltVarController([device],settings).settle_slot(engine,0)
    assert result['solution_converged'] and result['ControlActionsDone']
    assert result['PASS'] is False and result['controller_converged'] is False
    assert result['convergence_reason']=='MAXIMUM_TAP_AWARE_NETWORK_FEEDBACK_ITERATIONS'
    assert result['additional_feedback_solve_count']==1 and result['iterations']==1


def test_real_original_engine_integration_counter_restores_solution_class(engine,tmp_path):
    import numpy as np
    from types import SimpleNamespace
    from v42_b3_joint.contracts import digest
    from v42_dstatcom.integration import PhysicalScenario,SCHEMA,record,scenario_identity
    from v42_regcontrol import authority
    connection=tmp_path/'connection.json';connection.write_text('{}',encoding='utf8')
    scenario=dict(schema=SCHEMA,hardware=[sta08().to_dict()],controller=ControllerSettings().to_dict(),
        connection_manifest=record(connection))
    scenario['scenario_SHA']=digest(scenario_identity(scenario))
    audit=PhysicalScenario(scenario,tmp_path/'actual',source_SHA='a'*64,arm='B2',day='2025-05-01')
    arrays={key:np.zeros((96,1)) for key in ('pcc_p_kw','pcc_q_kvar','mess_p_kw','mess_q_kvar','mess_locations_96x4')}
    trajectory=SimpleNamespace(namespace='ACTUAL',case='B2',day='2025-05-01',**arrays)
    identity=dict(day='2025-05-01',arm='B2',slot=0,trajectory=trajectory)
    audit.install_actual(engine,identity,authority,LocalVoltVarController)
    engine.Solution.SolveSnap();original=type(engine.Solution).SolveSnap
    audit.settle_actual(engine,identity,authority)
    row=audit.rows[0];controller=row['controller']
    assert type(engine.Solution).SolveSnap is original
    assert controller['PASS'] and row['PASS']
    assert row['additional_feedback_solve_count']==controller['additional_feedback_solve_count']
    assert len(audit.physical_solve_events)==1+controller['additional_feedback_solve_count']
    assert all(event['completed'] and event['controls']['control_actions_done'] for event in audit.physical_solve_events)


def test_fullnetwork_observer_includes_remote_lines_all_tx_windings_and_added_buses(engine):
    device=install(engine,sta08());engine.Solution.SolveSnap()
    observed=network_observation(engine,ControllerSettings())
    raw=dict(zip(engine.Circuit.AllNodeNames(),engine.Circuit.AllBusMagPu()))
    assert observed['voltages']=={name.lower():value for name,value in raw.items() if int(name.rsplit('.',1)[1]) in (1,2,3)}
    assert all(f'{device.converter_bus}.{phase}' in observed['voltages'] for phase in (1,2,3))
    assert all(f'transformer.mess_sta08_tx/winding{w}/phase{phase}/current' in observed['thermal']
        for w in (1,2) for phase in (1,2,3))
    assert device.measure()['PASS']
    # This remote line is outside the local device audit. A real nameplate
    # readback failure must still fail the complete network observation.
    engine.Lines.Name('l53');engine.Lines.NormAmps(.01)
    failed=network_observation(engine,ControllerSettings())
    assert failed['summary']['thermal_violation_count']>0
    assert failed['summary']['maximum_line_current_utilization']>1
    assert failed['summary']['PASS'] is False and device.measure()['PASS']
    assert failed['ratings_SHA']!=observed['ratings_SHA']


def test_safety_rejects_new_remote_failures_even_when_total_voltage_error_falls():
    settings=ControllerSettings()
    before=dict(voltage_excess={'old.1':.01,'remote.2':0.},thermal_excess={'line.x':0.},
        summary=dict(PASS=False,hard_constraint_merit=.0001,maximum_voltage_exceedance_pu=.01))
    after=dict(voltage_excess={'old.1':.001,'remote.2':.0001},thermal_excess={'line.x':0.},
        summary=dict(PASS=False,hard_constraint_merit=.00000101,maximum_voltage_exceedance_pu=.001))
    safety=_step_is_safe(before,after,settings)
    assert safety['hard_merit_improved'] and not safety['accepted']
    assert safety['newly_failed_voltage_nodes']==['remote.2']
    after['voltage_excess']['remote.2']=0.;after['thermal_excess']['line.x']=.01
    assert not _step_is_safe(before,after,settings)['accepted']


def test_crossphase_repair_can_trade_existing_errors_inside_initial_slot_envelope():
    settings=ControllerSettings()
    before=dict(voltage_excess={'a.1':.004,'b.2':.004},thermal_excess={},
        initial_slot_exceedance_envelope_pu=.007,
        summary=dict(PASS=False,hard_constraint_merit=.000032,maximum_voltage_exceedance_pu=.004))
    after=dict(voltage_excess={'a.1':.00401,'b.2':.002},thermal_excess={},
        summary=dict(PASS=False,hard_constraint_merit=.0000200801,maximum_voltage_exceedance_pu=.00401))
    assert _step_is_safe(before,after,settings)['accepted']
    after['summary']['maximum_voltage_exceedance_pu']=.00701
    assert not _step_is_safe(before,after,settings)['accepted']
    before['summary'].update(maximum_voltage_exceedance_pu=.010,hard_constraint_merit=.0002)
    after['summary'].update(maximum_voltage_exceedance_pu=.009,hard_constraint_merit=.0001)
    safety=_step_is_safe(before,after,settings)
    assert safety['accepted'] and safety['recovery_after_irreversible_automatic_control_history']


def test_real_rejected_step_rolls_back_q_only_and_resolves_original_automatic_controls(engine):
    settings=ControllerSettings(maximum_feedback_iterations=2)
    device=install(engine,sta08(),settings)
    # A deliberately elevated frozen test input supplies a real AC violation;
    # this test is not an official trajectory replay or network approval.
    engine.Generators.Name('mess_dis_sta08');engine.Generators.kvar(200.)
    engine.Solution.SolveSnap()
    before=original_control_state(engine)
    assert network_observation(engine,settings)['summary']['voltage_violation_count']>0
    tx_class=type(engine.Transformers);original_tap=tx_class.Tap
    def forbid_tap_setting(instance,*args):
        assert not args,'Python tap setting is forbidden in autonomous feedback'
        return original_tap(instance)
    solution=engine.Solution;original_solve=type(solution).SolveSnap;calls=[]
    def observe(instance):
        if instance is solution:calls.append(list(device.q_state))
        return original_solve(instance)
    # Force one real improving probe to be rejected, so restoration semantics
    # are tested independently of which native nonlinear response occurs.
    with patch('v42_dstatcom.controller._step_is_safe',return_value=dict(accepted=False)),patch.object(tx_class,'Tap',forbid_tap_setting),patch.object(type(solution),'SolveSnap',observe):
        result=LocalVoltVarController([device],settings).settle_slot(engine,0)
    assert len(calls)==2 and any(q!=0 for q in calls[0]) and calls[1]==[0.,0.,0.]
    assert [row['kind'] for row in result['iteration_trace']]==['CAUSAL_Q_TRIAL','Q_ONLY_ROLLBACK']
    assert result['iteration_trace'][1]['tap_history_restored'] is False
    assert result['PASS'] is False and result['final_fullnetwork']['voltage_violation_count']>0
    assert result['tap_setter_calls']==result['fixed_tap_powerflow_calls']==0
    assert result['original_controls_preserved'] and result['additional_feedback_solve_count']==2
    assert original_control_state(engine)['regulator_settings_SHA']==before['regulator_settings_SHA']
    assert device.q_state==[0.,0.,0.]


def test_real_planning_actual_engines_start_independent_q_modes_and_controls(engine,tmp_path):
    import numpy as np
    from types import SimpleNamespace
    from v42_b3_joint.contracts import digest
    from v42_dstatcom.integration import PhysicalScenario,SCHEMA,record,scenario_identity
    from v42_regcontrol import authority
    actual,_,_=authority.compile_verified()
    try:
        initial_planning=original_control_state(engine);initial_actual=original_control_state(actual)
        assert initial_planning['regulator_taps']==initial_actual['regulator_taps']
        connection=tmp_path/'connection.json';connection.write_text('{}',encoding='utf8')
        scenario=dict(schema=SCHEMA,hardware=[sta08().to_dict()],controller=ControllerSettings().to_dict(),connection_manifest=record(connection))
        scenario['scenario_SHA']=digest(scenario_identity(scenario))
        contexts=[]
        for namespace,owned in [('DAYAHEAD',engine),('ACTUAL',actual)]:
            audit=PhysicalScenario(scenario,tmp_path/namespace,source_SHA='a'*64,arm='B2',day='2025-05-01',namespace=namespace)
            arrays={key:np.zeros((96,1)) for key in ('pcc_p_kw','pcc_q_kvar','mess_p_kw','mess_q_kvar','mess_locations_96x4')}
            trajectory=SimpleNamespace(namespace=namespace,case='B2',day='2025-05-01',**arrays)
            identity=dict(day='2025-05-01',arm='B2',slot=0,trajectory=trajectory,namespace=namespace)
            audit.install_actual(owned,identity,authority,LocalVoltVarController)
            contexts.append((audit,identity,owned))
        planning=contexts[0][0].sessions[id(engine)][1]
        actual_session=contexts[1][0].sessions[id(actual)][1]
        assert planning is not actual_session
        assert planning.devices[0] is not actual_session.devices[0]
        assert actual_session.devices[0].q_state==[0.,0.,0.]
        engine.Solution.SolveSnap();actual.Solution.SolveSnap()
        planning.devices[0].apply_q([-2.5,0,0]);engine.Solution.SolveSnap()
        for audit,identity,owned in contexts:audit.settle_actual(owned,identity,authority)
        assert planning.devices[0].q_state==[-2.5,0,0]
        assert actual_session.devices[0].q_state==[0.,0.,0.]
        assert actual_session.phase_modes[sta08().device_id]==[0,0,0]
        assert actual_session.response_columns=={}
        assert all(audit.rows[0]['controller']['original_controls_preserved'] for audit,_,_ in contexts)
    finally:actual.Basic.ClearAll()
