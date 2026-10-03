"""Evidence regression checks; not autonomous-control execution tests."""
import hashlib
import json
from pathlib import Path
import pytest

OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def test_source_absence_is_not_reported_as_autonomous_capacitor_success():
    a = read('REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')
    assert a['actual_static_compile'] == a['planning_static_compile']
    inv = a['actual_static_compile']
    assert inv['RegControl_count'] == len(inv['regulators']) == 7
    assert inv['CapControl_count'] == len(inv['capcontrols']) == 0
    assert inv['capacitor_banks'] == len(inv['capacitors']) == 4
    assert all(c['states'] == [1] for c in inv['capacitors'])
    assert a['capacitor_autonomy_provable'] is False
    assert a['cap_switching_target'] is a['cap_switching_deadband'] is a['cap_switching_delay'] is None


@pytest.mark.parametrize('month', ['April', 'May'])
def test_all_arms_months_share_same_unactivated_source_contract(month):
    c = read('APRIL_MAY_COMMON_GRID_CONTROL_CONTRACT.json')
    assert month in c['shared_months']
    assert c['shared_arms'] == ['B0', 'B1', 'B2', 'B3']
    assert c['same_authority_required'] and not c['production_ready']
    assert not c['reusable_production_code_updated']
    assert c['capacitor_rule'] is None
    assert c['May_scientific_execution'] == 'NOT_RUN'
    assert c['source_inventory_sha256'] == hashlib.sha256(
        (OUT/'REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json').read_bytes()).hexdigest()


def test_no_new_execution_or_fabricated_diagnostic_results():
    d = read('APRIL_15_16_30_AUTONOMOUS_CONTROL_DIAGNOSTIC.json')
    assert d['status'] == 'NOT_RUN' and not d['diagnostic_gate_PASS']
    assert d['actual_scientific_solves'] == 0
    assert [r['old_PR125_frozen']['voltage_violation_cells'] for r in d['days']] == [3,17,2]
    assert all(r['new_autonomous']['voltage_violation_cells'] is None for r in d['days'])
    f = read('FINAL_FLAGS.json')
    assert not f['production_activation'] and not f['replay_removal_implemented']
    assert f['Actual_Planning_tap_replay'] is f['Actual_Planning_cap_replay'] is None
    assert f['PR125_Actual_Planning_tap_replay'] and f['PR125_Actual_Planning_cap_replay']


def test_no_promotion_of_old_calibration_or_zero_filled_missing_artifacts():
    s = read('PR125_VOLTAGE_RESULT_SUPERSESSION.json')
    assert not s['supersedes_PR125_voltage_calibration']
    assert not s['old_candidate_bands_accepted_for_current_contract']
    assert not s['FINAL_MARGIN_ACCEPTED'] and not s['PROBLEM13_FINAL_VALIDATED']
    u = read('UNPRODUCED_SCIENTIFIC_ARTIFACTS.json')
    assert all(not r['produced'] and not (OUT/r['name']).exists() for r in u['artifacts'])


def test_all_30_pr125_freezes_receipts_read_and_kept_historical():
    a = read('PR125_DAILY_FREEZE_RECEIPT_AUDIT.json')
    assert a['planning_freezes_read'] == a['actual_receipts_read'] == 30
    assert [r['day'] for r in a['days']] == [f'2025-04-{d:02d}' for d in range(1,31)]
    assert a['old_actual_converged_slots'] == 2880
    assert a['old_actual_voltage_violations'] == 22
    assert a['new_scientific_execution'] == 'NOT_RUN'
