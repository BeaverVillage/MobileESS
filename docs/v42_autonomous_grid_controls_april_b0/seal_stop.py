"""Seal the source-authority STOP without generating scientific results."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = '043298363fe51edde0bddaa073a553e526ffef2c'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    audit = read('REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')
    inventory = audit['actual_static_compile']
    if inventory['CapControl_count'] != 0:
        raise ValueError('STOP_RECEIPT_REQUIRES_AUDITED_ABSENCE')
    daily = read('PR125_DAILY_FREEZE_RECEIPT_AUDIT.json')['days']
    common = dict(status='BLOCKED_SOURCE_CAPCONTROL_ABSENT', production_ready=False,
        same_authority_required=True, shared_months=['April', 'May'], shared_arms=['B0', 'B1', 'B2', 'B3'],
        regulator_rule='source snapshot/static maxcontroliter=100; sequential within day; fresh source initial each day',
        capacitor_rule=None, capacitor_rule_status='MISSING_SOURCE_CAPCONTROL',
        desired_regulator_control='AUTONOMOUS_BASE_CONTROL', desired_capacitor_control='AUTONOMOUS_BASE_CONTROL',
        source_inventory_sha256=hashlib.sha256((OUT/'REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json').read_bytes()).hexdigest(),
        parameter_tuning=0, May_scientific_execution='NOT_RUN', May_outcomes_used=False,
        reusable_production_code_updated=False, common_documented_interface_only=True)
    write('APRIL_MAY_COMMON_GRID_CONTROL_CONTRACT.json', common)
    write('PREREGISTRATION.json', dict(exact_base=BASE, status='AUDIT_STOP_BEFORE_EXECUTION',
        source_authority_frozen=False, regulator_authority_identified=True,
        capacitor_authority_identified=False, intended_control_contract=common,
        no_new_control_equipment_or_settings=True, no_result_driven_tuning=True,
        primary_voltage_band=[.95,1.05], primary_residual='V_ACTUAL_AC - V_PLAN (magnitude pu)',
        quantile_method_if_unblocked='higher', diagnostic_days=['2025-04-15','2025-04-16','2025-04-30'],
        all_PR125_inputs_V_PLAN_workload_capacity_arrays_must_remain_unchanged=True,
        scientific_execution_gate_admitted=False, gate_failure='CapControl source missing',
        forced_replay_removal_implemented=False, optimizer_calls=0,
        B1='NOT_RUN', B2='NOT_RUN', B3='NOT_RUN', May='NOT_RUN', M1='NOT_RUN', A2='NOT_RUN', M2='NOT_RUN'))
    write('PLANNING_GRID_CONTROL_AUDIT.json', dict(exact_base=BASE,
        observed_regulator_control='AUTONOMOUS_SOURCE_REGCONTROL', observed_capacitor_control='FIXED_ON_SOURCE_BANKS',
        RegControl_count=7, CapControl_count=0, autonomous_capacitor_claim=False,
        slot_semantics='one source-initial engine per day; sequential anchor state within day',
        sensitivity_semantics='anchor tap/cap held only during local finite differences',
        optimizer_tap_variables=0, optimizer_cap_variables=0, switching_objective_added=False,
        planning_behavior_changed=False, V_PLAN_changed=False, planning_freezes_audited=30,
        source_evidence='REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json'))
    write('ACTUAL_GRID_CONTROL_AUDIT.json', dict(exact_base=BASE,
        PR125_loop='apply_frozen_native_state inside each of 96 slots before SolveSnap',
        PR125_regulator_disabled=True, PR125_controlmode='off',
        PR125_Planning_tap_replay=True, PR125_Planning_cap_replay=True,
        forcing_function_other_physical_configuration_changes=False,
        force_removal_implemented=False, new_actual_adapter_activated=False,
        new_autonomous_regulator_status='NOT_RUN', new_autonomous_capacitor_status='BLOCKED_SOURCE_ABSENT',
        unrelated_physical_states_need_no_replacement_from_forcing_function=True,
        Actual_P_repair=0, Actual_Q_repair=0, Actual_global_reoptimization=0,
        AIDC_MESS_PQ_policy_changes=0, new_scientific_day_slot_solves=0,
        stop_conditions=audit['stop_conditions']))
    diagnostics = []
    for item in daily:
        if item['day'] in ('2025-04-15','2025-04-16','2025-04-30'):
            receipt = item['actual_receipt']
            diagnostics.append(dict(day=item['day'], old_PR125_frozen=dict(
                voltage_violation_cells=receipt['voltage_violations'], converged_slots=receipt['converged_slots'],
                line_violations=receipt['line_current_violations'],
                transformer_current_violations=receipt['transformer_current_violations'],
                transformer_kVA_violations=receipt['transformer_kVA_violations']),
                new_autonomous=dict(status='NOT_RUN', voltage_violation_cells=None,
                    converged_slots=None, tap_changes=None, cap_changes=None)))
    write('APRIL_15_16_30_AUTONOMOUS_CONTROL_DIAGNOSTIC.json', dict(status='NOT_RUN',
        diagnostic_gate_PASS=False, cause='SOURCE_CAPCONTROL_ABSENT', days=diagnostics,
        actual_scientific_solves=0, no_tuning=True, voltage_violations_are_not_gate_failure=True))
    write('GRID_CONTROL_OPERATION_SUMMARY.json', dict(status='NOT_RUN',
        regulator_tap_mismatch_slots=None, capacitor_mismatch_slots=None, total_tap_operations=None,
        total_capacitor_switching_operations=None, max_tap_deviation=None,
        days_with_autonomous_response=None, reason='No new source-authorized Actual run'))
    write('PR125_VOLTAGE_RESULT_SUPERSESSION.json', dict(
        supersedes_PR125_voltage_calibration=False, replacement_voltage_calibration_status='NOT_RUN',
        old_frozen_control_evidence_preserved=True, old_candidate_bands_accepted_for_current_contract=False,
        old_result_condition='Actual forces Planning taps/caps and disables controls',
        workload_capacity_fixes_superseded=False, new_candidate_bands=None,
        FINAL_MARGIN_ACCEPTED=False, PROBLEM13_FINAL_VALIDATED=False))
    flags = dict(status='STOP_SOURCE_CAPCONTROL_ABSENT',
        B0_AIDC_PRESENT=True, B0_WORKLOAD_PRESENT=True, Runtime_ON=True, CC4_ON=True,
        AIDC_FLEX_OPTIMIZATION=False, MESS_ACTIVE=False,
        Planning_regulator_control='AUTONOMOUS_SOURCE_REGCONTROL',
        Planning_capacitor_control='FIXED_ON_SOURCE_BANKS',
        Actual_regulator_control='NEW_RUN_NOT_RUN', Actual_capacitor_control='BLOCKED_SOURCE_CAPCONTROL_ABSENT',
        Actual_Planning_tap_replay=None, Actual_Planning_cap_replay=None,
        PR125_Actual_Planning_tap_replay=True, PR125_Actual_Planning_cap_replay=True,
        replay_removal_implemented=False, production_activation=False,
        Actual_P_repair=0, Actual_Q_repair=0, Actual_local_PQ_repair=0,
        Actual_global_reoptimization=0, Actual_AIDC_grid_reoptimization=0, Actual_MESS_reoptimization=0,
        FINAL_MARGIN_ACCEPTED=False, PROBLEM13_FINAL_VALIDATED=False,
        B1='NOT_RUN', B2='NOT_RUN', B3='NOT_RUN', May='NOT_RUN', M1='NOT_RUN', A2='NOT_RUN', M2='NOT_RUN')
    write('FINAL_FLAGS.json', flags)
    write('FINAL_VERDICT.json', dict(status='STOP_SOURCE_CAPCONTROL_ABSENT', task_complete=False,
        audit_complete=True, scientific_correction_complete=False,
        diagnostic_days_executed=0, April_days_rerun=0, Actual_scientific_solves=0,
        new_voltage_statistics=None, new_005_coverage=None, new_Q95_Q99_bands=None,
        blocker='No source CapControl equipment or threshold/delay/control-law authority',
        required_to_resume=['source-backed CapControl definitions/settings for exact banks',
            'or explicit revised contract allowing source fixed-ON capacitors with autonomous regulators'],
        old_PR125_workload_capacity_preserved=True, PR124_imports=0,
        parameter_tuning=0, May_outcomes_used_for_settings=False,
        FINAL_MARGIN_ACCEPTED=False, PROBLEM13_FINAL_VALIDATED=False))
    results = ['REGULATOR_STATE_COMPARISON.csv', 'CAPACITOR_STATE_COMPARISON.csv',
        'APRIL_B0_AUTONOMOUS_VOLTAGE_RESIDUALS.csv.gz', 'APRIL_B0_DAY_SUMMARY.csv',
        'POINTWISE_QUANTILES.csv', 'DAY_WORST_QUANTILES.csv', 'CURRENT_005_COVERAGE.json', 'CANDIDATE_BANDS.json']
    write('UNPRODUCED_SCIENTIFIC_ARTIFACTS.json', dict(status='NOT_RUN', reason='User section 25 source-authority STOP',
        artifacts=[dict(name=n, produced=False) for n in results],
        no_zero_filled_or_old_result_promoted_outputs=True,
        requested_regressions_A_to_Q='Autonomous implementation/diagnostic regressions not reached due to STOP; no PASS claimed'))
    entries = subprocess.check_output(['git','ls-tree','-r',BASE], cwd=ROOT).decode('utf-8').splitlines()
    checked = []
    for entry in entries:
        meta, name = entry.split('\t',1)
        _, kind, oid = meta.split()
        if kind != 'blob':
            raise ValueError('UNEXPECTED_BASE_TREE_ENTRY:' + name)
        data = (ROOT / name).read_bytes()
        blob = hashlib.sha1(('blob %d\0' % len(data)).encode() + data).hexdigest()
        if blob != oid:
            raise ValueError('EXACT_BASE_BYTE_DRIFT:' + name)
        checked.append(dict(path=name, bytes=len(data), git_blob_sha1=oid,
                            sha256=hashlib.sha256(data).hexdigest()))
    write('BASE_BYTE_PRESERVATION.json', dict(exact_base=BASE, PASS=True,
        method='raw file bytes hashed as Git blob; compare every exact-base ls-tree OID',
        checked_files=len(checked), files=checked))
    write('VERIFICATION.json', dict(exact_base=BASE, base_files_checked=len(checked),
        exact_BASE_bytes_preserved=True, BASE_content_changes=0,
        workload_capacity_power_V_PLAN_arrays_unchanged=True,
        PR125_old_voltage_results_unchanged=True, PR124_imports=0, raw_external_files_copied=False,
        scientific_results_estimated=False, new_scientific_execution='NOT_RUN',
        May_outcomes_used_for_construction=False, source_audit_static_compilers_equal=True))
    print('STOP sealed; exact BASE bytes preserved:', len(checked), flush=True)


if __name__ == '__main__':
    main()
