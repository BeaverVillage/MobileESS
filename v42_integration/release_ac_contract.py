"""The user-authorized original settled-slot AC evaluation contract.

ASOF substeps remain useful diagnostics. They do not change the official
15-minute, 96-slot settle_slot -> measure_full_network acceptance criterion.
"""
from copy import deepcopy
import math
import json
from pathlib import Path

from .policy import digest

CONTRACT = 'SLOTTED_SETTLED_ORIGINAL_PR223_V1'
EVIDENCE_SCHEMA = 'RELEASE_PRODUCTION_SETTLED_CANARY16_V1'
FULL96_EVIDENCE_SCHEMA = 'RELEASE_PRODUCTION_SETTLED_FULL96_V1'
VIOLATIONS = ('voltage_violation_cells','line_current_violation_cells',
    'transformer_current_violation_cells','transformer_nameplate_current_violation_cells',
    'original_transformer_nameplate_current_violation_cells',
    'added_transformer_nameplate_current_violation_cells','transformer_kva_violation_cells')


def validate_settled_fresh(receipt, rows, *, day, case_sha, initial_state_sha,
                           mess_plan_sha, trace_record, slots=96):
    """Validate the current case; never inherit a historical case's PASS."""
    if slots not in (16,96):
        raise ValueError('EXPLICIT_16_CANARY_OR_OFFICIAL_96_SETTLED_SCOPE_REQUIRED')
    if (receipt.get('day') != day or receipt.get('evaluation_case_sha') != case_sha
            or receipt.get('common_initial_state_sha') != initial_state_sha
            or receipt.get('MESS_plan_sha') != mess_plan_sha
            or receipt.get('actual_power_trace') != trace_record
            or receipt.get('executed_actual_slots') != slots or len(rows) != slots
            or receipt.get('supplied_actual_trace_slots') != slots
            or receipt.get('original_compiler_clock_SVR_and_measurement_reused') is not True
            or receipt.get('global_reoptimization') != 0 or receipt.get('MESS_PQ_repair') != 0
            or slots == 96 and receipt.get('full96_Actual_AC_established') is not True
            or receipt.get('evidence_kind') != 'REAL_DATA'):
        raise ValueError('CURRENT_CASE_ORIGINAL_SETTLED_AC_IDENTITY_AND_FULL_SCOPE_REQUIRED')
    axes = None; failures=[]; min_v=math.inf; max_v=-math.inf; max_line=0.
    for slot,row in enumerate(rows):
        clock=row.get('clock',{}); physical=row.get('physical',{}); hardware=row.get('SVR',{})
        if (row.get('slot') != slot or row.get('MESS_plan_sha') != mess_plan_sha
                or clock.get('schema') != 'V42_NATIVE_TIME_SLOT_V1' or clock.get('day') != day
                or clock.get('namespace') != 'ACTUAL' or clock.get('slot') != slot
                or clock.get('start_seconds') != slot*900 or clock.get('end_seconds') != (slot+1)*900
                or clock.get('physical_elapsed_seconds') != 900 or clock.get('PASS') is not True
                or clock.get('iteration_to_seconds_conversion') is not False
                or clock.get('manual_tap_or_cap_actions') != 0
                or not slot*900 <= clock.get('last_solve_seconds',-1) < (slot+1)*900
                or physical.get('all_original_and_added_axes_checked') is not True
                or physical.get('native_NormalAmps_and_winding_kVA_unchanged') is not True
                or physical.get('original_transformer_current_authority') != 'COMPILED_NORMALAMPS_ONLY'
                or hardware.get('original_seven_AUTO') is not True or len(hardware.get('devices',[])) != 11):
            raise ValueError('ORIGINAL_CLOCK_HISTORY_11_SVR_AUTO_AND_FULL_NETWORK_REQUIRED')
        nodes=physical.get('nodes',[]); currents=physical.get('currents',[]); transformers=physical.get('transformers',[])
        current_axes=(tuple(r['node_phase'] for r in nodes),
            tuple((r['element'],r['terminal'],r['phase']) for r in currents),
            tuple((r['element'],r['terminal']) for r in transformers))
        if not all(current_axes) or axes is not None and current_axes != axes:
            raise ValueError('SETTLED_FULL_NETWORK_MEASUREMENT_AXIS_DRIFT')
        axes=current_axes
        volts=[r['voltage_pu'] for r in nodes]
        loadings=[r['loading_pu'] for r in currents]
        ratings=[r['loading_pu'] for r in transformers]
        if not all(math.isfinite(v) for v in volts+loadings+ratings):
            raise ValueError('FINITE_FULL_NETWORK_SETTLED_VALUES_REQUIRED')
        # The original measurement's boolean/counts remain authoritative; these
        # direct array checks independently prevent a summary-only false PASS.
        numeric_ok=(min(volts)>=.95-1e-9 and max(volts)<=1.05+1e-9
            and max(loadings)<=1+1e-9 and max(ratings)<=1+1e-9)
        ok=(row.get('PASS') is True and physical.get('PASS') is True
            and hardware.get('hardware_PASS') is True and hardware.get('added_nodes_voltage_PASS') is True
            and all(physical.get(k)==0 for k in VIOLATIONS) and numeric_ok)
        if not ok:failures.append(slot)
        min_v=min(min_v,min(volts));max_v=max(max_v,max(volts));max_line=max(max_line,max(
            (r['loading_pu'] for r in currents if r['element'].startswith('line.')),default=0.))
    claimed=receipt.get('status')=='PASS' and receipt.get('PASS') is True
    if claimed != (not failures):
        raise ValueError('SETTLED_RAW_RESULT_AND_SUMMARY_STATUS_DRIFT')
    result=dict(Gate_contract=CONTRACT,status='PASS' if not failures else 'PHYSICAL_FAIL',
        day=day,case_sha=case_sha,initial_state_sha=initial_state_sha,MESS_plan_sha=mess_plan_sha,
        slots=slots,slot_seconds=900,official_Full96=slots==96,full96_claim=slots==96,
        all_nodes_phases_lines_transformer_currents_kVA_checked=True,
        node_phase_count=len(axes[0]),current_phase_terminals=len(axes[1]),transformer_terminals=len(axes[2]),
        failing_slots=failures,voltage_min_pu=min_v,voltage_max_pu=max_v,maximum_phase_line_loading=max_line,
        original_SVR_AUTO_Delay_TapDelay_history_changed=False,
        ASOF_substeps_are_additional_diagnostics=True,ASOF_substep_status_used_as_official_gate=False,
        continuous_time_voltage_safety_certified=False,old_PR223_PASS_transferred=False,
        actual_trace=deepcopy(trace_record),fresh_receipt_sha=digest(receipt),settled_rows_sha=digest(rows))
    result['certificate_sha']=digest(result)
    return result


def _checked_json(record):
    from .m_engine import file_record
    if file_record(record['path']) != record:
        raise ValueError('CURRENT_SETTLED_EVIDENCE_RAW_BYTES_DRIFT')
    return json.loads(Path(record['path']).read_text(encoding='utf-8-sig'))


def actual_evaluation_case_payload(source_case, ancestors, actual_policy, slots):
    """Bind the Actual Science separately from the unchanged Planning Case.

    A 16-slot canary and a 96-slot run deliberately have different case hashes.
    R1, R2, Source-strict and C0/C1 likewise cannot share a case identity.
    """
    if slots not in (16,96):
        raise ValueError('EXPLICIT_16_CANARY_OR_OFFICIAL_96_SETTLED_SCOPE_REQUIRED')
    if (not isinstance(actual_policy,dict)
            or actual_policy.get('mode') not in ('SOURCE_STRICT','R1','R2')
            or actual_policy.get('variant') not in ('C0','C1')):
        raise ValueError('EXPLICIT_ACTUAL_RESEARCH_POLICY_REQUIRED')
    record=actual_policy.get('research_contract')
    spec_sha=None
    if actual_policy['mode']=='SOURCE_STRICT':
        if record is not None:
            raise ValueError('SOURCE_STRICT_MUST_NOT_IMPORT_RESEARCH_ASSUMPTIONS')
    else:
        if not isinstance(record,dict):
            raise ValueError('EXPLICIT_R1_R2_RESEARCH_CONTRACT_REQUIRED')
        from .research_presite_contract import validate_spec
        from .m_engine import file_record
        spec=_checked_json(record);validate_spec(spec)
        if (spec['scenario'] != actual_policy['mode']
                or any(file_record(r['path']) != r for r in spec['source_records'])):
            raise ValueError('ACTUAL_RESEARCH_SCENARIO_OR_SOURCE_CONTRACT_DRIFT')
        date_contract=spec.get('date_contract')
        if date_contract is not None and date_contract != dict(day=source_case['day'],
                planning_identity=source_case['source_identity'],planning_source_sha=source_case['source_sha'],
                future_UID_roster_in_contract=False):
            raise ValueError('ACTUAL_RESEARCH_DATE_PLANNING_CONTRACT_DRIFT')
        spec_sha=digest(spec)
    hashes={key+'_sha':value['acceptance_sha'] if key.endswith('acceptance') else digest(value)
            for key,value in ancestors.items()}
    if set(hashes) != {'A2_result_sha','A2_acceptance_sha','M2_result_sha','M2_acceptance_sha'}:
        raise ValueError('EXACT_FINAL_A2_M2_ACTUAL_ANCESTORS_REQUIRED')
    return dict(schema='PRODUCTION_ACTUAL_EVALUATION_CASE_V1',
        planning_identity=deepcopy(source_case['source_identity']),
        planning_source_sha=source_case['source_sha'],**hashes,
        actual_policy_sha=digest(actual_policy),research_spec_sha=spec_sha,
        initial_state_sha=source_case['source_identity']['initial_state_sha'],
        slots=slots,clock_contract=CONTRACT)


def require_current_settled_evidence(evidence_record, *, source_case, ancestors, slots=16,
                                     expected_actual_policy=None):
    """Read the raw body and exact A2/M2 chain, rather than caller PASS flags."""
    from .release_p1_production import require_production_acceptance
    body = _checked_json(evidence_record)
    if slots not in (16,96):
        raise ValueError('EXPLICIT_16_CANARY_OR_OFFICIAL_96_SETTLED_SCOPE_REQUIRED')
    schema=EVIDENCE_SCHEMA if slots==16 else FULL96_EVIDENCE_SCHEMA
    proof_key='canary_proof_sha' if slots==16 else 'full96_proof_sha'
    if (body.get('schema') != schema or body.get('Gate_contract') != CONTRACT
            or body.get('source_sha') != source_case.get('source_sha')
            or body.get('source_identity') != source_case.get('source_identity')
            or body.get('day') != source_case.get('day') or body.get('executed_actual_slots') != slots
            or source_case.get('day') not in {f'2025-05-{n:02d}' for n in range(1,32)}
            or not source_case.get('source_sha') or not source_case.get('source_identity')
            or not body.get('evaluation_case_sha')
            or body.get(proof_key) != digest({k:v for k,v in body.items() if k!=proof_key})):
        raise ValueError('CURRENT_D0_SETTLED_RAW_BODY_SOURCE_CASE_AND_SCOPE_REQUIRED')
    a = ancestors['A2_result']; aa = ancestors['A2_acceptance']
    m = ancestors['M2_result']; ma = ancestors['M2_acceptance']
    identity=source_case['source_identity']
    require_production_acceptance(aa,stage='A2',identity=identity,result=a)
    require_production_acceptance(ma,stage='M2',identity=identity,result=m)
    if (aa['source_sha'] != source_case['source_sha'] or ma['source_sha'] != source_case['source_sha']
            or ma['parent_acceptance_sha'] != aa['acceptance_sha']
            or ma['AIDC_anchor'] != aa['AIDC_anchor'] or ma['MESS_anchor'] != m['mess']['plan_sha']
            or any(body.get(key+'_sha') != (value['acceptance_sha'] if key.endswith('acceptance') else digest(value))
                   for key,value in ancestors.items())):
        raise ValueError('CURRENT_SETTLED_FINAL_A2_M2_FULL_ANCESTOR_CHAIN_REQUIRED')
    policy=body.get('actual_policy')
    if expected_actual_policy is not None and policy != expected_actual_policy:
        raise ValueError('CURRENT_SETTLED_EXPECTED_ACTUAL_POLICY_DRIFT')
    payload=actual_evaluation_case_payload(source_case,ancestors,policy,slots)
    if (body.get('evaluation_case_payload') != payload
            or body['evaluation_case_sha'] != digest(payload)
            or body.get('research_contract') != policy.get('research_contract')):
        raise ValueError('CURRENT_SETTLED_CANONICAL_ACTUAL_EVALUATION_CASE_REQUIRED')
    receipt=_checked_json(body['raw_fresh_receipt']);rows=_checked_json(body['raw_slot_rows'])
    execution=_checked_json(body['raw_actual_execution_receipt'])
    if (execution.get('schema') != 'RELEASE_PRODUCTION_ACTUAL_EXECUTION_V1'
            or execution.get('fixture') is not False
            or execution.get('Actual_global_MILP_calls') != 0
            or execution.get('private_Environment_identity_preserved') is not True
            or execution.get('Original_event_driver_reused') is not True
            or execution.get('source_sha') != source_case['source_sha'] or execution.get('source_identity') != identity
            or execution.get('evaluation_case_sha') != body['evaluation_case_sha']
            or execution.get('evaluation_case_payload') != payload
            or execution.get('actual_policy') != policy
            or execution.get('research_contract') != policy.get('research_contract')
            or execution.get('initial_state_sha') != identity['initial_state_sha']
            or execution.get('MESS_plan_sha') != ma['MESS_anchor']
            or any(execution.get(key+'_sha') != body[key+'_sha'] for key in ancestors)
            or execution.get('actual_trace') != body['raw_actual_trace']):
        raise ValueError('CURRENT_SETTLED_ACTUAL_EXECUTION_SOURCE_ANCESTOR_TRACE_REQUIRED')
    actual_source=_checked_json(execution['actual_specific_source_freeze'])
    if (actual_source.get('planning_identity') != identity
            or actual_source.get('planning_source_sha') != source_case['source_sha']):
        raise ValueError('CURRENT_SETTLED_ACTUAL_SPECIFIC_SOURCE_BINDING_REQUIRED')
    from .m_engine import file_record
    files=actual_source.get('files',[])
    if (not files or actual_source.get('source_sha') != digest(files)
            or any(file_record(r['path']) != r for r in files)):
        raise ValueError('CURRENT_SETTLED_ACTUAL_SPECIFIC_SOURCE_BYTES_DRIFT')
    result=validate_settled_fresh(receipt,rows,day=source_case['day'],case_sha=body['evaluation_case_sha'],
        initial_state_sha=identity['initial_state_sha'],mess_plan_sha=ma['MESS_anchor'],
        trace_record=body['raw_actual_trace'],slots=slots)
    if file_record(body['raw_actual_trace']['path']) != body['raw_actual_trace']:
        raise ValueError('CURRENT_SETTLED_ACTUAL_TRACE_BYTES_DRIFT')
    if result['status'] != 'PASS':
        raise ValueError('CURRENT_SETTLED_AC_NOT_PASS')
    if body.get('official_certificate') != result or body.get('status') != 'PASS':
        raise ValueError('CURRENT_SETTLED_INDEPENDENT_CERTIFICATE_REPLAY_DRIFT')
    return result
