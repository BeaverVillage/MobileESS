"""Actual native line cuts and additive DTOs; no official-day qualification."""
import copy
import math
from pathlib import Path

import pytest

from v42_regcontrol import authority
from v42_voltage_control import siting, svr
from v42_voltage_control.timecontrol import CommonClock, queue


@pytest.fixture(scope='module')
def inventory():
    engine, _, _ = authority.compile_verified()
    try:
        return siting.original_inventory(engine, source_receipts=[siting.receipt(
            Path(__file__).resolve().parents[1]/'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')])
    finally:
        engine.Basic.ClearAll()


@pytest.fixture(scope='module')
def four(inventory):
    value = siting.development_contract(inventory, candidates=('STA01','STA06','STA08','BUS83'))
    value['status'] = 'FROZEN'
    return value


@pytest.mark.parametrize('alternative', ('BUS48','BUS50'))
def test_additive_exact_old_four_and_only_one_alternative(inventory, four, alternative):
    before = copy.deepcopy(four)
    seven = siting.additive_svr7_contract(four, inventory, alternative=alternative)
    assert four == before
    assert seven['units'][:4] == before['units']
    assert len(seven['units']) == 7
    assert [u['id'] for u in seven['units'][4:]] == ['BUS79','BUS108',alternative]
    assert seven['status'] == 'DEVELOPMENT_NOT_FROZEN_NOT_CANARY'
    assert svr.validate_contract(seven) == seven
    assert seven['tap_optimization_variables'] == 0 and seven['Q_injection_devices'] == 0


@pytest.mark.parametrize('candidate,element,upstream,downstream', (
    ('BUS79','Line.l79','78','79'), ('BUS108','Line.l105','105','108'),
    ('BUS48','Line.l47','47','48'), ('BUS50','Line.l49','49','50')))
def test_exact_existing_lines_nominal_phases_and_finite_capacity(inventory, candidate, element, upstream, downstream):
    unit = siting.line_candidate_unit(inventory,candidate)
    assert unit['cut_element'].lower() == element.lower()
    assert unit['cut_terminal'] == 2 and unit['series_orientation'] == 'DOWNSTREAM_OF_EXISTING_BRANCH'
    assert unit['original_bus_spec'] == downstream+'.1.2.3'
    assert unit['sensed_bus'] == downstream and unit['phases'] == [1,2,3]
    assert upstream not in unit['direct_downstream_bus_coverage']
    assert downstream in unit['direct_downstream_bus_coverage']
    assert unit['nominal_kv_ln'] == pytest.approx(4.16/math.sqrt(3))
    assert unit['phase_kva']/unit['nominal_kv_ln'] == pytest.approx(400)
    assert unit['ctprim'] == 400 and unit['min_tap'] == .9 and unit['max_tap'] == 1.1
    assert unit['delay_seconds'] == 30 and unit['tap_delay_seconds'] == 2


def test_two_candidates_have_distinct_real_downstream_service_coverage(inventory):
    a = set(siting.line_candidate_unit(inventory,'BUS48')['direct_downstream_bus_coverage'])
    b = set(siting.line_candidate_unit(inventory,'BUS50')['direct_downstream_bus_coverage'])
    assert {'idc_idc06_pcc','mess_idc06_pcc'} <= a
    assert 'idc_idc04_pcc' not in a
    assert {'idc_idc04_pcc','mess_idc04_pcc','idc_idc02_pcc','mess_idc02_pcc','151'} <= b
    assert 'idc_idc06_pcc' not in b


@pytest.mark.parametrize('corruption', ('missing_line','wrong_terminal','wrong_phases','invalid_normal','inconsistent_nominal'))
def test_new_candidate_requires_original_native_topology_evidence(inventory,corruption):
    value = copy.deepcopy(inventory)
    line = next(r for r in value['original_branches'] if r['element'].lower() == 'line.l79')
    if corruption == 'missing_line':
        value['original_branches'].remove(line)
    elif corruption == 'wrong_terminal':
        line['buses'][1] = '80.1.2.3'
    elif corruption == 'wrong_phases':
        line['phases'] = 1
    elif corruption == 'invalid_normal':
        line['norm_amps'] = float('inf')
    else:
        endpoint = next(r for r in value['original_endpoints'] if r['mv_parent_bus'].split('.')[0]=='79')
        endpoint['source_branch']['windings'][0]['kv'] = .48
    with pytest.raises(ValueError):
        siting.line_candidate_unit(value,'BUS79')


def test_two_alternatives_or_wrong_old_four_rejected(inventory,four):
    with pytest.raises(ValueError,match='ONE_DECLARED_ALTERNATIVE'):
        siting.additive_svr7_contract(four,inventory,alternative='BUS48+BUS50')
    value = copy.deepcopy(four);value['units'][3]['id']='STA12'
    with pytest.raises(ValueError,match='ORIGINAL_FOUR_ORDER'):
        siting.additive_svr7_contract(value,inventory,alternative='BUS50')


@pytest.mark.parametrize('alternative', ('BUS48','BUS50'))
def test_real_unsolved_seven_install_keeps_every_line_impedance_and_original_controls(inventory,four,alternative):
    engine,_,initial = authority.compile_verified()
    try:
        clock = CommonClock('ACTUAL','2025-05-01');clock.bind(engine)
        contract = siting.additive_svr7_contract(four,inventory,alternative=alternative)
        old_lines = {name:svr._existing_branch(engine,'Line.'+name) for name in engine.Lines.AllNames()}
        controls = svr._original_regulators(engine)
        bank = svr.install(engine,contract)
        assert svr._original_regulators(engine) == controls
        assert engine.RegControls.Count()==28 and engine.CapControls.Count()==0
        assert len(bank.installation_receipt['added_transformer_names']) == 21
        for name,before in old_lines.items():
            after = svr._existing_branch(engine,'Line.'+name)
            assert svr._branch_static(after) == svr._branch_static(before)
            unit = next((u for u in contract['units'] if u['cut_element'].lower()=='line.'+name.lower()),None)
            expected = before['buses'].copy()
            if unit:
                expected[unit['cut_terminal']-1] = unit['upstream_new_bus']+'.1.2.3'
            assert after['buses'] == expected
        for name in bank.installation_receipt['added_transformer_names']:
            engine.Transformers.Name(name)
            for winding in (1,2):
                engine.Transformers.Wdg(winding)
                assert engine.Transformers.Tap()==1
        assert queue(engine)==[] and engine.Solution.Hour()==0 and engine.Solution.Seconds()==0
        assert engine.Solution.ControlMode()==2
        observed = authority.source()['inventory'](engine)
        assert observed['capacitors']==initial['capacitors']
        originals=[r for r in observed['regulators'] if r['name'] in svr.ORIGINAL_REGCONTROLS]
        assert [r['initial_tap'] for r in originals] == [1.]*7
    finally:
        engine.Basic.ClearAll()


@pytest.mark.parametrize('power', (900.,-900.))
def test_real_new_line_bank_bidirectional_power_and_native_time(inventory,four,power):
    # Synthetic finite signed power-flow model test. Not May01 Actual evidence.
    engine,_,_ = authority.compile_verified()
    try:
        clock = CommonClock('ACTUAL','2025-05-01');clock.bind(engine)
        contract = copy.deepcopy(four)
        contract['units'] = [siting.line_candidate_unit(inventory,'BUS79')]
        bank = svr.install(engine,contract)
        engine.Text.Command(f'New Load.svr7_signed_unit_test Bus1=79.1.2.3 Phases=3 Conn=wye kV=4.16 kW={power} kvar={power/3} Model=1')
        result = clock.settle_slot(engine,0)
        assert result['PASS'] and engine.Solution.Converged()
        measured = bank.measure()
        assert measured['hardware_PASS']
        assert measured['whole_original_network_PASS'] is None
        assert all(p['terminals'][0]['P_into_kw']*power>0 for p in measured['devices'][0]['phases'])
        assert all(p['losses_kw']>0 and p['tap_range_PASS'] for p in measured['devices'][0]['phases'])
        assert engine.Solution.Hour()==0 and engine.Solution.Seconds()==900
        assert engine.Solution.ControlMode()==2
        assert measured['original_seven_AUTO']
    finally:
        engine.Basic.ClearAll()
