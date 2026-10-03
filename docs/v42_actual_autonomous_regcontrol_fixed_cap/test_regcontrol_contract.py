"""Regression A–W: real-source controls, frozen arrays and measured evidence.

Injected parameter/capacitor faults below occur in disposable fixture contexts
only. They are never tuning or repaired scientific Actual trajectories.
"""
import ast
import copy
import csv
import inspect
import subprocess
import sys
import numpy as np
import pytest
from v42_regcontrol.common import *
from v42_regcontrol.authority import source,common_contract,assert_inventory
from v42_regcontrol.session import AutonomousSession,replay_planning_native_state


def test_source_inventory_and_fixed_bank_authority():
    inv=source()['expected']
    assert (inv['RegControl_count'],inv['capacitor_banks'],inv['CapControl_count'])==(7,4,0)
    assert all(r['enabled'] for r in inv['regulators'])
    assert all(c['enabled'] and c['states']==[1] for c in inv['capacitors'])


def test_planning_behavior_and_V_PLAN_preserved():
    r=read(OUT/'PLANNING_GRID_CONTROL_RECHECK.json')
    assert r['PASS'] and r['behavior_unchanged'] and r['RegControl_autonomous']
    assert r['V_PLAN_bytes_unchanged'] and r['sequential_same_engine_96_slots']
    assert r['fresh_source_compile_per_day'] and r['capacitors_fixed_ON']
    assert r['tap_cap_decision_variables']==0


def test_current_actual_has_no_Planning_native_state_setter_or_controlmode_off():
    from v42_regcontrol import runner,session
    for module in (runner,session):
        tree=ast.parse(inspect.getsource(module))
        calls=[n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id
            for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,(ast.Name,ast.Attribute))]
        assert 'apply_frozen_native_state' not in calls
        assert 'Tap' not in calls and 'States' not in calls
        assert 'controlmode=off' not in inspect.getsource(module)
    with pytest.raises(ValueError,match='FORCING_FORBIDDEN'): replay_planning_native_state(None,None,0)


def native_fixture(function):
    # Real campaigns use standalone processes too. On Windows the FPC DLL's
    # initialization SEH exceptions trigger pytest's faulthandler despite
    # being handled by the DLL. Isolate native fixtures without disabling any
    # pytest assertion or changing the engine/settings.
    script=('import importlib.util; from pathlib import Path; '
        'p=Path('+repr(str(Path(__file__).resolve()))+'); '
        's=importlib.util.spec_from_file_location("native_source_fixture",p); '
        'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.'+function+'()')
    r=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout


def test_real_source_identical_inputs_and_perturbed_load_can_change_taps():
    native_fixture('_real_source_fixture')


def _real_source_fixture():
    a=AutonomousSession(); b=AutonomousSession()
    try:
        pa=a.solve_next(0); pb=b.solve_next(0)
        assert pa['actual_taps']==pb['actual_taps']
        assert a.odd is not b.odd
        previous=np.array(pb['actual_taps'])
        # Synthetic exogenous fixture load perturbation; no production setting change.
        for name in b.odd.Loads.AllNames():
            b.odd.Loads.Name(name); b.odd.Loads.kW(b.odd.Loads.kW()*1.8); b.odd.Loads.kvar(b.odd.Loads.kvar()*1.8)
        changed=b.solve_next(1)
        assert changed['previous_taps']==pb['actual_taps']
        assert not np.array_equal(changed['actual_taps'],previous)
        assert changed['all_7_RegControls_enabled'] and changed['control_mode']==0
        assert changed['capacitor_states']==[1]*4 and changed['CapControl_count']==0
        with pytest.raises(ValueError,match='SEQUENTIAL'): b.solve_next(1)
    finally: a.close(); b.close()
    fresh=AutonomousSession()
    try: assert np.array_equal(fresh.initial_taps,np.ones(7))
    finally: fresh.close()


def test_parameter_and_capacitor_drift_fail_without_state_repair():
    native_fixture('_fault_injection_fixture')


def _fault_injection_fixture():
    s=AutonomousSession()
    try:
        s.odd.Text.Command('Edit RegControl.creg1a VReg=119')
        with pytest.raises(ValueError,match='PARAMETER_OR_MODE_DRIFT'): s.solve_next(0)
    finally: s.close()
    s=AutonomousSession()
    try:
        s.odd.Capacitors.Name('c83'); s.odd.Capacitors.States([0])
        with pytest.raises(ValueError,match='CAPACITOR_STATE'): s.solve_next(0)
        s.odd.Capacitors.Name('c83'); assert s.odd.Capacitors.States()==[0]
    finally: s.close()


@pytest.mark.parametrize('arm',['B0','B1','B2','B3'])
def test_all_arms_share_authority_and_reject_override(arm):
    common=common_contract(arm)
    assert common==common_contract('B0')
    with pytest.raises(ValueError,match='ARM_SPECIFIC'): common_contract(arm,regulator_sha='0'*64)
    with pytest.raises(ValueError,match='ARM_SPECIFIC'): common_contract(arm,capacitor_sha='0'*64)


@pytest.mark.parametrize('day',DAYS)
def test_full_day_convergence_axes_PQ_and_fixed_source_controls(day):
    path=output_day(day); old=OLD/'BUNDLE'/day_folder(day)
    a=np.load(path/'V_ACTUAL_AC.npz'); p=np.load(old/'V_PLAN.npz'); ph=np.load(old/'ACTUAL_PHYSICAL.npz')
    assert np.array_equal(a['node_names'],p['node_names'])
    assert a['V_ACTUAL_AC'].shape==(96,len(p['node_names']))
    assert a['converged'].all() and np.all(a['capacitor_states']==1)
    assert np.array_equal(a['PCC_P_kw'],ph['PCC_P_kw'])
    assert np.array_equal(a['PCC_Q_kvar'],ph['PCC_Q_kvar'])
    logs=read(path/'RAW_CONTROL_LOG.json')['slots']
    assert len(logs)==96 and all(r['all_7_RegControls_enabled'] and r['CapControl_count']==0 for r in logs)
    assert np.array_equal(a['actual_previous_taps'][0],np.ones(7))
    assert np.array_equal(a['actual_previous_taps'][1:],a['regulator_taps'][:-1])
    physical=read(path/'RAW_PHYSICAL_INPUT_LOG.json')['slots']
    assert all(r['all_MESS_PQ_zero'] for r in physical)
    receipt=read(path/'FRESH_ACTUAL_AC_RECEIPT.json')
    assert receipt['Actual_P_repair']==receipt['Actual_Q_repair']==receipt['Actual_global_reoptimization']==0
    assert not receipt['Actual_Planning_tap_replay'] and not receipt['Actual_Planning_cap_replay']


def test_diagnostic_gate_does_not_require_zero_voltage_violations():
    from v42_regcontrol import runner
    body=inspect.getsource(runner.diagnostic)
    assert 'voltage_violations' not in body.split('passed=')[1].split('write(')[0]
    gate=read(OUT/'APRIL_15_16_30_DIAGNOSTIC.json')
    assert gate['PASS'] and [r['converged_slots'] for r in gate['days']]==[96]*3
    assert gate['voltage_violations_do_not_fail_gate']
    assert gate['tap_logging_complete'] and gate['no_tuning']


def test_NON_GRID_identity_and_full_point_alignment():
    r=read(OUT/'PR125_NON_GRID_STATE_IDENTITY.json')
    assert r['PASS'] and r['all_base_files']==3590
    assert r['Actual_PCC_PQ_unchanged'] and r['V_PLAN_bytes_unchanged'] and r['CC4_queue_results_unchanged']
    a=read(OUT/'EXACT_VOLTAGE_AXIS_ALIGNMENT.json')
    assert a['PASS'] and a['rows']==30*96*386 and a['dropped_rows']==0


def test_May_and_other_arms_not_run_and_final_margin_not_accepted():
    with pytest.raises(ValueError,match='MAY_NOT_RUN'): require_april('2025-05-01')
    f=read(OUT/'FINAL_FLAGS.json')
    assert all(f[k]=='NOT_RUN' for k in ('May','B1','B2','B3','M1','A2','M2'))
    assert not f['FINAL_MARGIN_ACCEPTED'] and not f['PROBLEM13_FINAL_VALIDATED']
    assert not f['MESS_ACTIVE'] and f['Actual_AIDC_grid_reoptimization']==0
    assert f['Actual_P_repair']==f['Actual_Q_repair']==f['Actual_global_reoptimization']==0


def test_parameter_integrity_and_grid_baseline_is_not_optimizer_objective():
    i=read(OUT/'REGCONTROL_PARAMETER_INTEGRITY.json')
    assert i['PASS'] and i['parameter_tuning_count']==0 and i['unexpected_capacitor_state_count']==0
    assert common_contract('B0')['tap_cap_optimization_variables']==0
    assert 'P1' not in inspect.getsource(AutonomousSession) and 'P2' not in inspect.getsource(AutonomousSession)
