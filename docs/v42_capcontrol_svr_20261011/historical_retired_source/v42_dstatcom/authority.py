"""Explicit permits for preserved-plan development and sealed Actual evaluation."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date

from v42_pr134_b1.common import digest, read, record
from v42_common_campaign.authority import source_files

_permit = ContextVar('v42_dstatcom_actual_permit', default=None)


def checked(receipt):
    if record(receipt['path']) != receipt:
        raise PermissionError('DSTATCOM_AUTHORITY_RECEIPT_DRIFT')
    return receipt['path']


@contextmanager
def physical_permit(arm, day, source_SHA, scenario, *, namespace='ACTUAL',development=False,design_receipt=None):
    from .integration import validate_scenario
    if _permit.get() is not None or arm not in ('B0','B1','B2','B3') or namespace not in ('ACTUAL','DAYAHEAD'):
        raise PermissionError('DSTATCOM_EXPLICIT_SINGLE_ACTUAL_PERMIT_REQUIRED')
    date.fromisoformat(day)
    value, _, _ = validate_scenario(scenario)
    sources = source_files()
    if digest(sources) != source_SHA:
        raise PermissionError('DSTATCOM_ACTUAL_EXECUTION_SOURCE_SHA_DRIFT')
    if development:
        if day not in ('2025-05-01','2025-05-28') or design_receipt is not None:
            raise PermissionError('DSTATCOM_DEVELOPMENT_DISCLOSED_MAY01_MAY28_ONLY')
    else:
        design = verify_design(design_receipt, source_SHA)
        if design['scenario_SHA'] != value['scenario_SHA']:
            raise PermissionError('DSTATCOM_EVALUATION_FROZEN_HARDWARE_DRIFT')
    identity = dict(arm=arm, day=day, source_SHA=source_SHA,
        scenario_SHA=value['scenario_SHA'],namespace=namespace,development=development)
    token = _permit.set(identity)
    try:
        yield identity
    finally:
        _permit.reset(token)
        if source_files() != sources:
            raise PermissionError('DSTATCOM_ACTUAL_EXECUTION_SOURCE_MUTATED')


def authorize_physical(arm, day, source_SHA, scenario_SHA, namespace):
    permit = _permit.get()
    if permit is None or any(permit[key] != val for key,val in
        (('arm',arm),('day',day),('source_SHA',source_SHA),('scenario_SHA',scenario_SHA),('namespace',namespace))):
        raise PermissionError('DSTATCOM_SOURCE_BOUND_ACTUAL_PERMIT_REQUIRED')
    return dict(permit)


def authorize_actual(arm,day,source_SHA,scenario_SHA):
    return authorize_physical(arm,day,source_SHA,scenario_SHA,'ACTUAL')


def actual_permit(arm,day,source_SHA,scenario,**kwargs):
    return physical_permit(arm,day,source_SHA,scenario,namespace='ACTUAL',**kwargs)


def verify_design(receipt, source_SHA):
    if receipt is None:
        raise PermissionError('DSTATCOM_FROZEN_DESIGN_RECEIPT_REQUIRED')
    design = read(checked(receipt))
    if (design.get('schema') != 'V42_DSTATCOM_FROZEN_DESIGN_V1'
        or design.get('source_SHA') != source_SHA or design.get('PASS') is not True
        or design.get('Planning_band_pu') != [.95,1.05]
        or design.get('Actual_band_pu') != [.95,1.05]
        or design.get('investment_or_economic_analysis') is not False
        or design.get('MESS_PQ_repair') != 0):
        raise PermissionError('DSTATCOM_FROZEN_DESIGN_CONTRACT_REQUIRED')
    from .integration import validate_scenario
    scenario = read(checked(design['scenario']))
    _,specs,_=validate_scenario(scenario)
    expected={f'STA{i:02d}_MESS' for i in range(1,13)}|{f'IDC{i:02d}_AIDC' for i in range(1,13)}
    if len(specs)!=24 or {s.device_id for s in specs}!=expected:
        raise PermissionError('DSTATCOM_FINAL_CANONICAL_24_PCC_REQUIRED')
    if design['scenario_SHA'] != scenario['scenario_SHA']:
        raise PermissionError('DSTATCOM_FROZEN_DESIGN_SCENARIO_SHA_DRIFT')
    gates = design.get('development_gates', {})
    required={'implementation_and_units','single_device_original_auto','staged_interactions',
              'tap_prediction_and_anti_interaction','snapshot_delay_semantics',
              'forecast_and_phase_reserve','Planning_96_slot_Fresh','Actual_96_slot_Fresh',
              'Planning_Actual_state_independence'}
    if set(gates)!=required or design.get('Source_Initial_State_preserved') is not True:
        raise PermissionError('DSTATCOM_CAUSAL_AND_INDEPENDENT_PLANNING_ACTUAL_GATES_REQUIRED')
    if not gates or not all(read(checked(row)).get('PASS') is True for row in gates.values()):
        raise PermissionError('DSTATCOM_ALL_DEVELOPMENT_GATES_REQUIRED')
    if (design.get('Tap_aware_Autonomous_control') is not True
        or design.get('RegControl_7_original_automatic') is not True
        or design.get('DSTATCOM_or_Tap_MILP_variables') != 0):
        raise PermissionError('DSTATCOM_TAP_AWARE_ORIGINAL_AUTOMATIC_CONTRACT_REQUIRED')
    # The final gate must point to an actual complete paired replay. Recompute
    # literal all-node/phase voltage and all original branch overloads.
    actual_gate=read(checked(gates['Actual_96_slot_Fresh']))
    from .qualification import evaluate_stage
    measured=evaluate_stage(actual_gate['stage_result'],source_SHA=source_SHA,device_count=24,
        baseline_receipt=actual_gate['baseline_result'],require_zero=True)
    if measured['PASS'] is not True or measured['scenario_SHA']!=scenario['scenario_SHA']:
        raise PermissionError('DSTATCOM_ACTUAL_LITERAL_ZERO_PHYSICAL_GATE_REQUIRED')
    return design


def verify_physical_result(result,manifest,arm,day):
    """Join hardware receipt to the original complete AC canary authority."""
    design=verify_design(manifest['DSTATCOM_design'],manifest['execution_SHA'])
    receipt=result.get('DSTATCOM_physical_audit')
    if receipt is None or result.get('DSTATCOM_scenario_SHA')!=design['scenario_SHA']:
        raise PermissionError('DSTATCOM_REAL_CANARY_HARDWARE_RECEIPT_REQUIRED')
    audit=read(checked(receipt))
    if (audit.get('hardware_and_controller_PASS') is not True
        or audit.get('execution_source_SHA')!=manifest['execution_SHA']
        or audit.get('scenario_SHA')!=design['scenario_SHA']
        or audit.get('day')!=day or audit.get('arm')!=arm
        or audit.get('logical_Fresh_slots')!=96
        or audit.get('original_initial_physical_solve_count')!=96
        or audit.get('total_physical_SolveSnap_count')!=audit.get('completed_physical_SolveSnap_count')
        or audit.get('hardware_or_controller_failed_slots')!=[]
        or audit.get('all_seven_RegControls_enabled') is not True
        or audit.get('all_four_fixed_capacitors_on') is not True
        or audit.get('Original_Source_SHA_before_after_equal') is not True
        or audit.get('Original_Fresh_and_96_slot_body_unchanged') is not True
        or audit.get('original_input_setpoints_unchanged') is not True
        or audit.get('DSTATCOM_MILP_variables')!=0
        or audit.get('Actual_optimizer_calls')!=0 or audit.get('Actual_plan_repair_calls')!=0
        or audit.get('configured_MaxControlIterations')!=[100]
        or audit.get('configured_MaxIterations')!=[15]):
        raise PermissionError('DSTATCOM_REAL_96_SLOT_CANARY_HARDWARE_CONTRACT_REQUIRED')
    for key in ('slots_receipt','csv_receipt','physical_solve_events_receipt'):
        checked(audit[key])
    if result.get('actual_ac_physical_pass') is not True:
        raise PermissionError('DSTATCOM_ORIGINAL_AND_NEW_ALL_NODE_BRANCH_PASS_REQUIRED')
    return audit
