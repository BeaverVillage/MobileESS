"""Independent readback gates; a controller/test PASS is not a physical PASS."""
import math

import numpy as np

from v42_pr134_b1.common import read
from .authority import checked
from .replay import raw_metrics

VERSION = 'V42_DSTATCOM_TAP_AWARE_STAGE96_QUALIFICATION_V1'
ORIGINAL_REGCONTROL_SHA = '3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf'


def evaluate_stage(receipt, *, source_SHA, device_count, baseline_receipt, require_zero=False):
    """Retain every failure; final deployment requires strict zero violations.

    Earlier device-count stages can establish causal safety while reporting
    unresolved baseline voltage cells. They cannot certify zero violations.
    """
    result = read(checked(receipt))
    if (result.get('schema') != 'V42_DSTATCOM_SAME_FROZEN_PLAN_REPLAY_V1'
        or result.get('source_SHA') != source_SHA or result.get('Native_optimizer_calls') != 0
        or result.get('Actual_reoptimization') != 0 or result.get('MESS_PQ_repair') != 0
        or result.get('day') != '2025-05-01' or result.get('arm') != 'B2'
        or result.get('DSTATCOM_enabled') is not True or result.get('original_inputs_unchanged') is not True):
        raise PermissionError('DSTATCOM_TAP_AWARE_STAGE_EXACT_FROZEN_ACTUAL_REQUIRED')
    baseline = read(checked(baseline_receipt))
    if (baseline.get('DSTATCOM_enabled') is not False or baseline.get('OFF_original_AC_bit_exact') is not True
        or baseline.get('original_bindings') != result.get('original_bindings')
        or baseline.get('arm') != result['arm'] or baseline.get('day') != result['day']):
        raise PermissionError('DSTATCOM_TAP_AWARE_STAGE_EXACT_OFF_COMPARISON_REQUIRED')
    raw = result['metrics']['raw_AC_receipt'];checked(raw)
    metrics = raw_metrics(raw['path'])
    baseline_raw = baseline['metrics']['raw_AC_receipt'];checked(baseline_raw)
    with np.load(raw['path'],allow_pickle=False) as new, np.load(baseline_raw['path'],allow_pickle=False) as old:
        if any(not np.array_equal(new[k],old[k]) for k in
                ('node_names','node_phases','branch_names','branch_phases','branch_kinds')):
            raise PermissionError('DSTATCOM_TAP_AWARE_STAGE_ORIGINAL_AXIS_DRIFT')
        before = (old['voltage_pu'] < .95)|(old['voltage_pu'] > 1.05)
        after = (new['voltage_pu'] < .95)|(new['voltage_pu'] > 1.05)
        new_cells = int(np.sum(after & ~before))
        persistent = int(np.sum(after & before))
        resolved = int(np.sum(before & ~after))
    audit = read(checked(result['hardware_audit']))
    scenario = audit['frozen_scenario']
    devices = scenario['hardware']
    # Earlier completed diagnostics stored explicit site/endpoint coordinates;
    # derive their label for read-only auditing, never for a new execution.
    device_ids = {row.get('device_id',row['site_id']+'_'+row['endpoint_id']) for row in devices}
    if len(devices) != device_count or audit['execution_source_SHA'] != source_SHA:
        raise PermissionError('DSTATCOM_TAP_AWARE_STAGE_SOURCE_OR_DEVICE_COUNT_DRIFT')
    if device_count == 24:
        expected = {f'STA{i:02d}_MESS' for i in range(1,13)}|{f'IDC{i:02d}_AIDC' for i in range(1,13)}
        if device_ids != expected:
            raise PermissionError('DSTATCOM_TAP_AWARE_FINAL_CANONICAL_24_PCC_REQUIRED')
    elif device_count == 1 and device_ids != {'STA08_MESS'}:
        raise PermissionError('DSTATCOM_TAP_AWARE_SINGLE_STA08_REQUIRED')
    for key in ('slots_receipt','csv_receipt','physical_solve_events_receipt'):
        checked(audit[key])
    rows = read(audit['slots_receipt']['path'])
    controls = [c for row in rows for c in [row['original_initial_solve_controls'],
        *row['feedback_solve_controls'],row['settled_original_controls']]]
    original_auto = bool(controls) and all(c['regulator_settings_SHA']==ORIGINAL_REGCONTROL_SHA
        and len(c['regulator_enabled'])==7 and all(c['regulator_enabled'])
        and c['control_mode']==0 and c['capacitor_states']==[1,1,1,1] and c['CapControl_count']==0
        and c['configured_MaxControlIterations']==100 and c['configured_MaxIterations']==15
        and c['solution_converged'] and c['control_actions_done'] for c in controls)
    complete = (len(rows)==96 and [r['slot'] for r in rows]==list(range(96))
        and audit['logical_Fresh_slots']==96 and audit['original_initial_physical_solve_count']==96
        and audit['total_physical_SolveSnap_count']==audit['completed_physical_SolveSnap_count'])
    # Read each physical phase/connection check, rather than trusting only the
    # integration audit's overall bool or a regression receipt.
    hardware = complete and all(len(row['controller']['final_devices'])==device_count
        and all(device['PASS'] and len(device['phases'])==3
            and all(phase['PASS'] and all(phase['checks'].values()) for phase in device['phases'])
            and all(tx['PASS'] for tx in device['original_service_transformers'])
            and math.isfinite(device['total_converter_apparent_kva'])
            and device['total_converter_apparent_kva']<=device['converter_nameplate_kva']
            for device in row['controller']['final_devices']) for row in rows)
    converged = complete and all(row['controller']['controller_converged']
        and row['controller']['ControlActionsDone'] and row['controller']['solution_converged'] for row in rows)
    thermal_zero = not any(metrics[k] for k in ('line_current_violation_cells',
        'original_service_and_grid_transformer_current_violation_cells','original_service_and_grid_transformer_kva_violation_cells'))
    physical_zero = complete and original_auto and hardware and converged and thermal_zero and metrics['voltage_violation_cells']==0
    causal_safety = complete and original_auto and hardware and converged and thermal_zero and new_cells==0
    return dict(schema=VERSION,source_SHA=source_SHA,device_count=device_count,
        day=result['day'],arm=result['arm'],namespace='ACTUAL',scenario_SHA=result['scenario_SHA'],
        stage_result=receipt,baseline_result=baseline_receipt,raw_AC=raw,hardware_audit=result['hardware_audit'],
        PASS=physical_zero if require_zero else causal_safety,final_deployment_zero_required=require_zero,
        Full_AC_Physical_PASS=physical_zero,stage_causal_safety_PASS=causal_safety,
        complete_96_slot_Fresh=complete,Original_7_RegControl_automatic_unchanged=original_auto,
        all_physical_hardware_checks_PASS=hardware,controller_converged_all_96=converged,
        voltage_violation_cells=metrics['voltage_violation_cells'],baseline_voltage_violation_cells=int(before.sum()),
        newly_violating_node_phase_slot_cells=new_cells,persistent_baseline_cells=persistent,resolved_baseline_cells=resolved,
        original_line_and_transformer_overloads_zero=thermal_zero,metrics=metrics,
        tests_used_as_physical_evidence=False,Native_optimizer_calls=0,MESS_PQ_repair=0)
