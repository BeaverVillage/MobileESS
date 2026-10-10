"""Source formula and honest prediction scope; Original seven controls stay AUTO."""
from copy import deepcopy
import json
import math

import pytest

from v42_voltage_control import regcontrol as subject


def row(*, voltage=115., current=(0.,0.)):
    return dict(name='creg1a',transformer='reg1a',tap=1.,min_tap=.9,max_tap=1.1,
        num_taps=32,
        phases=1,enabled=True,control_mode=0,engine_version=subject.VERSION_TOKEN,
        monitored_winding=2,tap_winding=2,tap_increment=.00625,
        monitored_winding_base_voltage_V=2400.,
        properties=dict(VReg='120',Band='2',PTRatio='20',CTPrim='700',R='3',X='7.5',
            PTPhase='1',Bus='',Reversible='No',Cogen='No',VLimit='0',LDC_Z='0',
            MaxTapChange='16',Delay='15',TapDelay='2'),
        **{subject.VOLTAGES:[[voltage*20,0.]],subject.CURRENTS:[list(current)]})


def prediction(r, **kwargs):
    return subject.predict_tap_response(dict(regulators=[r],source_SHA='a'*64),**kwargs)


def test_source_sensor_uses_into_terminal_complex_current_and_pt_ratio():
    r=row(voltage=120.,current=(-700.,0.))
    result=prediction(r)['regulators'][0]['sensor']
    assert result['voltage_PT_complex']==[120.,0.]
    assert result['current_CT_complex']==[-1.,0.]
    assert result['LDC_complex']==[-3.,-7.5]
    assert result['compensated_voltage_complex']==[117.,-7.5]
    assert result['compensated_voltage_V']==math.hypot(117.,7.5)
    assert result['current_direction']=='INTO_MONITORED_TRANSFORMER_TERMINAL'


def test_static_round_then_seventy_percent_and_physical_limit():
    r=row();p=prediction(r)['regulators'][0]
    assert p['pending_tap_change_pu']==7*.00625
    assert p['next_static_steps']==4
    assert p['predicted_tap_after_next_action']==1.025
    r['tap']=1.09375
    p=prediction(r)['regulators'][0]
    assert p['predicted_tap_after_next_action']==1.1
    r['tap']=1.1
    p=prediction(r)['regulators'][0]
    assert p['blocked_by_tap_limit'] and p['action']=='NO_ACTION'


def test_bankers_round_and_exact_deadband_boundary():
    p=prediction(row(voltage=118.125))['regulators'][0]
    assert p['pending_tap_change_pu']==2*.00625  # boost/inc=2.5, nearest even
    assert p['next_static_steps']==1
    assert prediction(row(voltage=119.))['regulators'][0]['action']=='NO_ACTION'
    r=row(voltage=121.875);r['tap_winding']=1
    assert prediction(r)['regulators'][0]['action']=='RAISE'  # other winding sign


def test_pt_max_phase_selection_uses_that_phases_current():
    r=row();r['phases']=3;r['properties']['PTPhase']='max'
    r[subject.VOLTAGES]=[[2300.,0.],[2400.,0.],[2380.,0.]]
    r[subject.CURRENTS]=[[0.,0.],[-700.,0.],[700.,0.]]
    s=prediction(r)['regulators'][0]['sensor']
    assert s['selected_phase_1based']==2 and s['LDC_complex']==[-3.,-7.5]


def test_candidate_missing_complex_current_is_unknown_without_current_state_fallback():
    r=row();candidate={'creg1a':{subject.VOLTAGES:r[subject.VOLTAGES]}}
    p=prediction(r,predicted_winding_state=candidate)
    assert p['state_basis']=='PREDICTED_WINDING_STATE'
    assert p['regulators'][0]['status']=='UNKNOWN'
    assert p['regulators'][0]['predicted_tap_after_next_action'] is None
    assert prediction(r,predicted_winding_state={})['regulators'][0]['status']=='UNKNOWN'


@pytest.mark.parametrize('field,value',[('Bus','remote.1'),('Reversible','Yes'),('Cogen','Yes'),('VLimit','126'),('LDC_Z','1')])
def test_unimplemented_native_modes_remain_unknown(field,value):
    r=row();r['properties'][field]=value
    assert prediction(r)['regulators'][0]['status']=='UNKNOWN'


def test_next_action_is_not_final_solvesnap_accuracy_and_no_change_inflation():
    r=row();p=prediction(r)
    after=deepcopy(r);after['tap']=1.05
    comparison=subject.compare_settled_taps(p,dict(regulators=[after]))
    assert comparison['regulators'][0]['next_action_to_settled_tap_difference']==pytest.approx(.025)
    assert comparison['changed_case_direction_agreement_diagnostic']==1.
    assert comparison['exact_next_action_accuracy'] is None
    assert comparison['exact_settled_tap_prediction_accuracy'] is None
    assert p['regulators'][0]['settled_tap_estimate_status']=='APPROXIMATE'
    assert p['regulators'][0]['expected_settled_tap_estimate']==pytest.approx(1.0375)
    assert comparison['approximate_settled_changed_case_tap_step_MAE']==pytest.approx(2.)
    comparison=subject.compare_settled_taps(p,dict(regulators=[r]))
    assert comparison['actual_changed_regulator_count']==0
    assert comparison['changed_case_direction_agreement_diagnostic'] is None
    assert comparison['changed_case_coverage'] is None
    assert comparison['approximate_settled_changed_case_tap_step_MAE'] is None


def test_local_settled_estimate_discloses_constant_power_assumptions_and_unsupported_winding():
    r=row();p=prediction(r)['regulators'][0]
    assert p['expected_settled_direction']=='RAISE'
    assert p['settled_local_stop_reason']=='LOCAL_SENSOR_IN_BAND'
    assert any('constant power' in a for a in p['settled_tap_estimate_assumptions'])
    assert any('No network redistribution' in a for a in p['settled_tap_estimate_assumptions'])
    r['tap_winding']=1
    p=prediction(r)['regulators'][0]
    assert p['status']=='PREDICTED' and p['expected_settled_tap_estimate'] is None
    assert p['settled_tap_estimate_status'].startswith('UNKNOWN')


def test_real_original_auto_sensor_readback_is_nonmutating_and_json_serializable():
    from v42_regcontrol import authority
    engine,_,_=authority.compile_verified()
    # One ordinary source-initial AUTO solve; no fixed/disabled/NoControl probe.
    engine.Solution.SolveSnap()
    s=authority.source();before=s['inventory'](engine)
    engine.RegControls.Name('creg1a');engine.Transformers.Name('reg2a');engine.Transformers.Wdg(1)
    engine.Circuit.SetActiveElement('Transformer.reg2a')
    old=(engine.RegControls.Name(),engine.Transformers.Name(),engine.Transformers.Wdg(),engine.CktElement.Name())
    measured=subject.snapshot(engine,source_SHA='a'*64)
    assert old==(engine.RegControls.Name(),engine.Transformers.Name(),engine.Transformers.Wdg(),engine.CktElement.Name())
    assert s['inventory'](engine)==before
    assert measured['regulator_count']==7 and all(r['enabled'] for r in measured['regulators'])
    assert measured['configured_MaxControlIterations']==100 and measured['configured_MaxIterations']==15
    assert measured['physical_solves']==measured['physical_settings_mutations']==0
    assert all(r['sensor_status']=='MEASURED_SOURCE_FORMULA' for r in measured['regulators'])
    for r in measured['regulators']:
        assert len(r[subject.VOLTAGES])==len(r[subject.CURRENTS])==r['phases']
        phase=r['sensor']['selected_phase_1based']-1
        z=complex(*r[subject.VOLTAGES][phase])/float(r['properties']['PTRatio'])
        z+=complex(float(r['properties']['R']),float(r['properties']['X']))*complex(*r[subject.CURRENTS][phase])/float(r['properties']['CTPrim'])
        # NumPy/Python complex magnitude can differ by one double-precision ULP.
        # This checks observer arithmetic, not any physical voltage/current gate.
        assert r['sensor']['compensated_voltage_V']==pytest.approx(abs(z),abs=1e-12,rel=0.)
    json.dumps(measured,allow_nan=False)
    json.dumps(subject.predict_tap_response(measured),allow_nan=False)


def test_time_sensor_is_available_but_static_action_prediction_is_unknown():
    r=row();r['control_mode']=2
    p=prediction(r)['regulators'][0]
    assert p['status']=='UNKNOWN'
    assert p['predicted_tap_after_next_action'] is None
    assert 'NATIVE_TIME_QUEUE_ACTION_IS_NOT_A_STATIC_PREDICTION' in p['unknown_reasons']
