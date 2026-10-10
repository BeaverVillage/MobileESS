"""Actual CAPI timing kernels and original AUTO regulators; no campaign gate."""
import copy
import json
from pathlib import Path

import opendssdirect as dss
import pytest

from v42_b3_joint.contracts import digest
from v42_voltage_control.capcontrol import candidate_contract, install, validate_contract
from v42_voltage_control.timecontrol import CommonClock, queue, seconds


@pytest.fixture
def kernel():
    engine = dss.NewContext()
    engine.Text.Command('New Circuit.kernel bus1=83 phases=3 basekv=4.16 pu=1.04')
    for bus in ('88','90','92'):
        engine.Text.Command(f'New Line.to{bus} bus1=83 bus2={bus} phases=3 r1=.001 x1=.001 r0=.001 x0=.001 length=.001')
    engine.Text.Command('New Capacitor.c83 bus1=83 phases=3 kvar=600 kv=4.16 numsteps=1')
    for name,bus in [('c88a','88.1'),('c90b','90.2'),('c92c','92.3')]:
        engine.Text.Command(f'New Capacitor.{name} bus1={bus} phases=1 kvar=50 kv=2.402 numsteps=1')
    engine.Text.Command('Set voltagebases=[4.16]')
    engine.Text.Command('CalcVoltageBases')
    engine.Solution.MaxIterations(15)
    engine.Solution.MaxControlIterations(100)
    yield engine
    engine.Basic.ClearAll()


def setup(engine, variant='A1', **kwargs):
    clock = CommonClock('ACTUAL','2025-05-01')
    clock.bind(engine)
    bank = install(engine,candidate_contract(engine,variant,**kwargs),clock=clock)
    return clock,bank


def at(engine,t):
    engine.Solution.Hour(int(t//3600))
    engine.Solution.Seconds(t%3600)
    engine.Solution.SolveSnap()
    assert engine.Solution.Converged() and engine.Solution.ControlActionsDone()


def cap_state(engine,name='c83'):
    engine.Capacitors.Name(name)
    return list(engine.Capacitors.States())


def test_real_c83_is_one_600_kvar_stage_and_four_physical_ratings_unchanged(kernel):
    clock,bank = setup(kernel,'A2')
    initial = copy.deepcopy(bank.original_physical)
    result = clock.settle_slot(kernel,0,bank=bank)
    assert [e['absolute_seconds'] for e in result['events']] == [0.,300.]
    assert result['physical_solve_count'] == 2 and result['physical_elapsed_seconds'] == 900
    assert result['unsolved_hold_seconds'] == 600 and seconds(kernel) == 900
    observed = bank.measure()
    assert [r['states'] for r in observed['devices']] == [[0]]*4
    assert [r['physical_step_kvar'] for r in observed['transitions']] == [600.,50.,50.,50.]
    for before,after in zip(initial,observed['devices']):
        assert all(before[k] == after[k] for k in before if k != 'states')
    assert observed['PASS'] and len(observed['transitions']) == 4
    assert not any('dstat' in name.lower() or 'statcom' in name.lower() for name in kernel.Circuit.AllElementNames())


def test_native_300_second_open_delay_and_330_second_off_hold(kernel):
    _,bank = setup(kernel)
    at(kernel,0); bank.observe_at(0)
    assert queue(kernel)[0]['absolute_seconds'] == 300
    at(kernel,299); assert cap_state(kernel) == [1]
    at(kernel,300); bank.observe_at(300); assert cap_state(kernel) == [0]
    kernel.Text.Command('Edit Vsource.source pu=.98')
    at(kernel,301)
    assert queue(kernel)[0]['absolute_seconds'] == 630  # LastOpen+DeadTime+ONDelay.
    at(kernel,629); assert cap_state(kernel) == [0]
    at(kernel,630); bank.observe_at(630); assert cap_state(kernel) == [1]
    assert bank.measure()['transitions'][1]['previous_state_hold_seconds'] == 330
    kernel.Text.Command('Edit Vsource.source pu=1.04')
    at(kernel,631)
    assert queue(kernel)[0]['absolute_seconds'] == 931
    at(kernel,930); assert cap_state(kernel) == [1]
    at(kernel,931); bank.observe_at(931)
    assert bank.measure()['transitions'][2]['previous_state_hold_seconds'] == 301
    assert bank.measure()['minimum_hold_violations'] == []


def test_voltage_withdrawal_cancels_native_pending_open_without_python_queue_edit(kernel):
    _,bank = setup(kernel)
    at(kernel,0)
    assert len(queue(kernel)) == 1
    kernel.Text.Command('Edit Vsource.source pu=1.02')
    at(kernel,299)
    assert queue(kernel) == []
    at(kernel,300); bank.observe_at(300)
    assert cap_state(kernel) == [1] and bank.measure()['cumulative_switch_count'] == 0


def test_deadband_retains_state_and_does_not_chatter(kernel):
    _,bank = setup(kernel)
    at(kernel,0)
    kernel.Text.Command('Edit Vsource.source pu=1.02')
    for i,pu in enumerate((1.02,1.00,1.029,.995,1.005)):
        kernel.Text.Command(f'Edit Vsource.source pu={pu}')
        at(kernel,100+i*300); bank.observe_at(100+i*300)
        assert queue(kernel) == [] and cap_state(kernel) == [1]
    assert bank.measure()['cumulative_switch_count'] == 0


def test_slot_boundary_queue_uses_next_input_sample_before_due_action(kernel):
    clock,bank = setup(kernel,delay_off_seconds=900.)
    first = clock.settle_slot(kernel,0,bank=bank)
    assert first['physical_solve_count'] == 1 and cap_state(kernel) == [1]
    assert first['queue_carried_to_next_slot'][0]['absolute_seconds'] == 900
    # A new slot's input removes overvoltage. Native sampling cancels the open
    # action due at exactly this boundary, before DoActions can execute it.
    kernel.Text.Command('Edit Vsource.source pu=1.02')
    second = clock.settle_slot(kernel,1,bank=bank)
    assert cap_state(kernel) == [1] and second['queue_carried_to_next_slot'] == []
    assert second['physical_solve_count'] == 1 and bank.measure()['transitions'] == []


def test_existing_initial_solve_count_is_not_repeated_or_fabricated(kernel):
    clock,bank = setup(kernel)
    kernel.Solution.SolveSnap()
    observed = []
    native_calls = []
    def solve():
        native_calls.append(seconds(kernel))
        kernel.Solution.SolveSnap()
    result = clock.settle_slot(kernel,0,bank=bank,solve=solve,observer=observed.append,
                               initial_solve_already_done=True)
    assert native_calls == [300.] and [r['absolute_seconds'] for r in observed] == [300.]
    assert result['physical_solve_count'] == 2 and result['extra_SolveSnap_count'] == 1
    assert result['events'][0]['initial_solve_already_completed']


def test_single_phase_physical_node_two_is_monitored_terminal_phase_one(kernel):
    clock,bank = setup(kernel,'A2')
    result = clock.settle_slot(kernel,0,bank=bank)
    row = next(r for r in bank.measure()['devices'] if r['name']=='c90b')
    controller = next(r for r in bank.measure()['native_controllers'] if r['capacitor']=='c90b')
    assert row['bus'] == '90.2' and controller['pt_phase']=='1'
    assert abs(result['events'][0]['capacitors']['devices'][2]['measured_control_voltage_pu']-1.04) < .001
    assert row['states'] == [0]


@pytest.mark.parametrize('change',[
    lambda k:k['devices'][0].pop('minimum_on_seconds'),
    lambda k:k['devices'][0].update(num_steps=12),
    lambda k:k['devices'][0].update(delay_off_seconds=1),
    lambda k:k['devices'][0].update(delay_on_seconds=30.25),
    lambda k:k['development_dates'].append('2025-05-02'),
])
def test_complete_contract_rejects_missing_fields_equipment_hold_and_future_data(kernel,change):
    contract = candidate_contract(kernel,'A1')
    change(contract)
    contract['contract_SHA']=digest({k:v for k,v in contract.items() if k!='contract_SHA'})
    with pytest.raises(ValueError): validate_contract(contract)


def test_clock_rejects_out_of_order_slots_and_external_time_drift(kernel):
    clock,_=setup(kernel)
    with pytest.raises(ValueError,match='CHRONOLOGICAL'): clock.settle_slot(kernel,1)
    kernel.Solution.Seconds(1)
    with pytest.raises(ValueError,match='START'): clock.settle_slot(kernel,0)


def test_original_seven_regulators_obey_real_15s_and_2s_without_setting_taps():
    from v42_regcontrol import authority
    engine,_,before=authority.compile_verified()
    try:
        clock=CommonClock('ACTUAL','2025-05-01'); clock.bind(engine)
        def taps():
            return [r['initial_tap'] for r in authority.source()['inventory'](engine)['regulators']]
        initial=taps()
        at(engine,0)
        assert taps()==initial
        assert len(queue(engine))==7 and {r['absolute_seconds'] for r in queue(engine)}=={15.}
        at(engine,14); assert taps()==initial
        at(engine,15); first=taps(); assert first != initial
        assert min(r['absolute_seconds'] for r in queue(engine))==17.
        at(engine,16); assert taps()==first
        at(engine,17); assert taps()!=first
        after=authority.source()['inventory'](engine)
        from v42_voltage_control.integration import original_parameters
        assert original_parameters(before)==original_parameters(after)
        assert all(r['enabled'] for r in after['regulators']) and after['RegControl_count']==7
        assert after['CapControl_count']==0 and after['capacitors']==before['capacitors']
        assert engine.Solution.ControlMode()==2
    finally:
        engine.Basic.ClearAll()


def test_original_native_queue_settles_one_slot_with_event_driven_timestamp_proof():
    from v42_regcontrol import authority
    engine,_,_=authority.compile_verified()
    try:
        clock=CommonClock('ACTUAL','2025-05-01'); clock.bind(engine)
        result=clock.settle_slot(engine,0)
        event_times=[r['absolute_seconds'] for r in result['events']]
        assert event_times[:3]==[0.,15.,17.]
        assert result['converged'] and result['control_actions_done_as_of_current_time']
        assert all(t<900 for t in event_times) and result['end_seconds']==900
        assert len(event_times)==result['physical_solve_count'] < 100
        assert result['iteration_to_seconds_conversion'] is False
    finally:
        engine.Basic.ClearAll()


def test_new_planning_actual_engines_have_independent_native_cap_queue_and_states():
    from v42_regcontrol import authority
    planning,_,_=authority.compile_verified()
    actual,_,_=authority.compile_verified()
    try:
        pc=CommonClock('DAYAHEAD','2025-05-01'); pc.bind(planning)
        ac=CommonClock('ACTUAL','2025-05-01'); ac.bind(actual)
        contract=candidate_contract(planning,'A1')
        pb=install(planning,contract,clock=pc); ab=install(actual,contract,clock=ac)
        assert pb.initial_state['states']==ab.initial_state['states']
        assert pb.initial_state['namespace']=='DAYAHEAD' and ab.initial_state['namespace']=='ACTUAL'
        pr=pc.settle_slot(planning,0,bank=pb)
        assert seconds(actual)==0 and queue(actual)==[] and ab.measure()['transitions']==[]
        ar=ac.settle_slot(actual,0,bank=ab)
        assert pr['namespace']=='DAYAHEAD' and ar['namespace']=='ACTUAL'
        assert pc is not ac and pb.transitions is not ab.transitions
        assert pr['events'][0]['absolute_seconds']==ar['events'][0]['absolute_seconds']==0
        assert pr['events'][0]['capacitors']['devices'][0]['states']==[1]
        assert ar['events'][0]['capacitors']['devices'][0]['states']==[1]
    finally:
        planning.Basic.ClearAll(); actual.Basic.ClearAll()
