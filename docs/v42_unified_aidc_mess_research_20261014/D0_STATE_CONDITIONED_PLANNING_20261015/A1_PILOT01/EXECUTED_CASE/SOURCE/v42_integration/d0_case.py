"""Supervisor D0 public-state Case compiler; historical D-minus-1 is immutable."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json

import numpy as np

from .unified_contract import digest,file_sha
from .m_engine import file_record,_write
from .dday_initialization import load_dday_state

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/D0_STATE_CONDITIONED_PLANNING_20261015'
INITIAL=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
SOURCE=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
SEMANTIC='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'
INITIAL_BYTE='d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003'
SCIENCE='V42_D0_STATE_CONDITIONED_PLANNING_MAY01_V1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def seal(document,field):
    document=deepcopy(document)
    document[field]=digest(document)
    return document


def compile_contracts(*,output=REPORT):
    """Use only already public initial jobs and the frozen anonymous day forecast."""
    from .cc4_policy_inputs import load_frozen_cc4
    from .production_case import KERNEL,TIMING
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if file_sha(INITIAL)!=INITIAL_BYTE:
        raise ValueError('D0_APPROVED_INITIAL_FILE_BYTES_DRIFT')
    state=load_dday_state(INITIAL,arm='B1')
    if state['common_initial_state_sha']!=SEMANTIC:
        raise ValueError('D0_APPROVED_INITIAL_SEMANTIC_DRIFT')
    begin=state['begin_epoch_seconds'];end=begin+86400
    native=read(SOURCE)
    projection_path=Path('D:/v42_may_joint_repair_campaign_20261013/inputs/B2/2025-05-01/NATIVE_INPUT.json')
    projection=read(projection_path)
    native['D0_current_physical_projection']=file_record(projection_path)
    physical_merge=[]
    for field in ('electrical_certificate','grid_outputs','route_table'):
        if field=='route_table' and any(native[field][k]!=projection[field][k] for k in ('sha256','bytes')):
            raise ValueError('D0_ORIGINAL_DAY_ROUTE_NUMERIC_AUTHORITY_DRIFT')
        physical_merge.append(dict(field=field,original_value_sha=digest(native[field]),
            current_value_sha=digest(projection[field]),source_record=file_record(projection_path),
            source_scope='SAME_DAY_APPROVED_IEEE123_11SVR_PHYSICAL_ONLY'))
        native[field]=deepcopy(projection[field])
    cc4=load_frozen_cc4('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json',
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/CC4/DAY_20250501.json',
        kernel_path=KERNEL,runtime_integrity_path=ROOT/'v42_final/runtime_bundle/INTEGRITY.json',
        planning_bundle_path=SOURCE)
    forecast_issue=datetime.fromisoformat(cc4['issue_time']).timestamp()
    if cc4['target_day']!='2025-05-01' or forecast_issue>begin:
        raise ValueError('D0_FORECAST_EVENT_TIME_UNAVAILABLE')
    active=state['running']+state['pending']
    if any(r['submit_seconds']>begin for r in active):
        raise ValueError('D0_FUTURE_UID_IN_PUBLIC_INITIAL_STATE')
    prior_unknown=[r for r in active if r['origin_unknown']]
    if any(r['submit_seconds']>=begin for r in prior_unknown):
        raise ValueError('D0_PREOBSERVED_FORECAST_DEBIT_REQUIRES_EXPLICIT_COHORT')
    axis=dict(schema='D0_EXPLICIT_96_SLOT_TIME_AXIS_V1',planning_issue_epoch_seconds=begin,
        evaluation_begin_seconds=begin,evaluation_end_seconds=end,slots=96,dt_seconds=900,
        public_issue_ISO=datetime.fromtimestamp(begin,timezone.utc).isoformat(),
        native_internal_offset=24,native_model_slots=[24,120],
        native_slot_zero_seconds=begin-21600,physical_M_grid_slots=[0,96],
        unused_internal_prefix_slots=[0,24],unused_internal_prefix_is_evaluated=False,
        native_command_formula='D0_begin+(native_start_slot-24)*900',
        historical_six_hour_prefix_is_new_gate=False,historical_prefix_status='NOT_CERTIFIED')
    backlog=seal(dict(schema='D0_KNOWN_BACKLOG_RESEARCH_V1',policy_id='D0_BASE_BACKLOG_WINDOW_SOURCE_COMPATIBLE_V1',
        issue_seconds=begin,end_seconds=end,initial_state_sha=SEMANTIC,
        initial_backlog_optimization_authorized=True,pending_source_compatible_placement_research_authorized=True,
        site_scope='SOURCE_COMPATIBLE_ONLY',base_backlog_scheduling_window_seconds=85500,
        additional_intentional_delay_budget_seconds=0,source_QoS_budget_seconds_preserved=0,
        automatic_hard_deadline_extension=False,source_protection_confirmed_by_research=False,
        customer_SLA_claimed=False,original_wait_and_hard_contracts_preserved=True,
        initial_placement_data_scope='ORIGINAL_SOURCE_COMPATIBLE_NATIVE_DOMAIN_NO_NEW_WAN_OR_DATA_EVIDENCE',
        corrective_preplacement_source_data_authority_granted=False,
        optional_unknown_60min_delay_and_checkpoint='GATED_AFTER_BASIC_REAL_ALLOCATION',
        authorization='USER_D0_STATE_CONDITIONED_PLANNING_20261015'), 'contract_sha')
    forecast=seal(dict(schema='D0_FROZEN_CC4_DAY_REUSE_V1',issue_seconds=begin,day_begin_seconds=begin,
        forecast_source_available_seconds=forecast_issue,source_issue_time=cc4['issue_time'],
        target_day=cc4['target_day'],model_id=cc4['model_id'],prediction_index=cc4['prediction_index'],
        Q50_GPUh=cc4['q50_hourly_GPUh'],Q90_GPUh=cc4['q90_hourly_GPUh'],
        cc4_sha=cc4['prediction_sha'],runtime_sha=cc4['runtime_sha'],kernel_sha=cc4['kernel_sha'],
        original_prediction_row_sha=cc4['original_selected_row_sha'],source_receipts=cc4['source_receipts'],
        conditioned_on_initial_known=True,initial_preobserved_D1_unknown_reclassified_known=len(prior_unknown),
        conditioning_scope='PUBLIC_INITIAL_KNOWN_LEDGER_RECONCILIATION_ONLY',prediction_reconditioned_or_refit=False,
        initial_preobserved_May01_forecast_debits=0,
        preobserved_debit_reason='ALL78_SUBMIT_BEFORE_DAY_TARGET_COHORT_BEGIN',
        actual_future_UIDs_used=False,forecast_modifications=0,fit_calls=0,scaling_calls=0,clipping_calls=0,
        event_time_semantic_asof='PASS_EXPORTED_SAVED_SCOPE',
        historical_operational_ingestion_availability='NOT_CERTIFIED',
        model_selection_retrospective=cc4['selection_retrospective']), 'forecast_receipt_sha')
    campaign=read('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    physical=dict(network='IEEE123',AIDC=12,installed_GPU=780,installed_SVR=11,original_RegControl=7,
        equipment={k:campaign[k] for k in ('hardware','scenario','thermal')},
        electrical_certificate=native['electrical_certificate'],original_limits_preserved=True,
        no_hardware_change=True)
    files=[file_record(ROOT/p) for p in ('v42_integration/d0_case.py','v42_integration/d0_a_planning.py',
        'v42_integration/d0_execution.py','v42_integration/d0_resource.py',
        'v42_integration/a_engine.py','v42_root/native.py','v42_native/grid.py','v42_final/reserve.py',
        'v42_temporal/service.py','v42_two/contract.py','v42_integration/m_engine.py',
        'v42_integration/m_candidates.py','v42_integration/aidc_sensitivity_runtime.py')]
    source_freeze=dict(schema='D0_EXACT_MODEL_SOURCE_FREEZE_V1',science_version=SCIENCE,files=files,
        source_sha=digest(files),campaign_HOLD=True,campaign_auto_restart_authorized=False)
    science_payload=dict(name=SCIENCE,source=source_freeze['source_sha'],backlog=backlog['contract_sha'],
        time_axis=digest(axis),physical=digest(physical),CC4=forecast['forecast_receipt_sha'],
        known_policy='D0_OBSERVED_RUNNING_PINNED_AND_PENDING_RESEARCH_BACKLOG',
        official_MESS_UB='ADAPTIVE_BEAM_4_JOINT_ORIGINAL_FULL_INCUMBENT',official_MESS_LB='K48',
        historical_prefix_not_new_gate=True)
    science=digest(science_payload)
    public=dict(running=state['running'],pending=state['pending'],historical_completed=state['historical_completed'])
    case_payload=dict(science_sha=science,initial_semantic_sha=SEMANTIC,public_input_sha=digest(public),
        forecast=forecast['forecast_receipt_sha'],native_source=file_record(SOURCE),timing=file_record(TIMING))
    case=digest(case_payload)
    identity=dict(science_sha=science,case_sha=case,initial_state_sha=SEMANTIC,
        cc4_sha=cc4['prediction_sha'],runtime_sha=cc4['runtime_sha'])
    manifest=dict(schema='D0_STATE_CONDITIONED_PLANNING_CASE_V1',name=SCIENCE,identity=identity,
        source_sha=source_freeze['source_sha'],physical_sha=digest(physical),time_axis_sha=digest(axis),
        qos_sha=backlog['contract_sha'],response_sha=read(native['electrical_certificate']['path'])['outputs']['planning_coefficients']['sha256'],
        initial_record=file_record(INITIAL),source_native_record=file_record(SOURCE),
        historical_base_commit='4624039ca376db7aeae1e08709441d545b350eeb',
        no_historical_UB_LB_or_plan_transfer=True,historical_prefix_gate_excluded=True,
        initial_authority='APPROVED_PR223_MODEL_STATE_NOT_OBSERVED_KESTREL_SITE',
        source_freeze=source_freeze,physical=physical,time_axis=axis,
        backlog_contract=backlog,forecast_receipt=forecast,science_payload=science_payload,case_payload=case_payload,
        source_physical_merge=physical_merge,
        backlog_contract_sha=backlog['contract_sha'],forecast_receipt_sha=forecast['forecast_receipt_sha'])
    manifest=seal(manifest,'manifest_sha')
    initial=dict(status='PASS',scope='APPROVED_D0_INPUT_REUSE_NOT_A1_FULL_FEASIBILITY',
        source_record=file_record(INITIAL),semantic_sha=SEMANTIC,byte_sha=INITIAL_BYTE,
        semantic_and_byte_SHA_distinct=True,counts=state['counts'],MODEL_ASSUMPTION=True,
        KESTREL_OBSERVED_SITE=False,site_reassigned=False,elapsed_reset=False,
        prior_completed_UIDs=len(state['historical_completed']),excluded44_active_GPU=0,
        D0_known_UIDs=len(active),former_D1_Unknown_to_D0_known=len(prior_unknown),
        future_unknown_UIDs_in_planning=0,old_prefix_is_gate=False,
        actual_running_release_rule='OBSERVED_COMPLETION_ONLY',
        planning_running='PUBLIC_Q50_NOMINAL_AND_ORIGINAL_RUNTIME_HEADROOM_SEPARATE_FROM_ACTUAL_HOLD')
    for name,doc in (('D0_CASE_MANIFEST.json',manifest),('D0_INITIAL_STATE_AUTHORITY.json',initial),
        ('D0_TIME_AXIS.json',axis),('D0_BACKLOG_RESEARCH_CONTRACT.json',backlog),
        ('D0_CC4_FORECAST_RECEIPT.json',forecast),('D0_SOURCE_FREEZE.json',source_freeze)):
        _write(output/name,doc)
    return manifest,state,native,backlog,forecast,cc4


def require_case(manifest,*,stage=None):
    from .coordinator import verify_sources
    if manifest.get('schema')!='D0_STATE_CONDITIONED_PLANNING_CASE_V1' or not manifest.get('historical_prefix_gate_excluded'):
        raise ValueError('D0_EXPLICIT_NEW_STATE_CONDITIONED_CASE_REQUIRED')
    if manifest.get('manifest_sha')!=digest({k:v for k,v in manifest.items() if k!='manifest_sha'}):
        raise ValueError('D0_MANIFEST_SEAL_DRIFT')
    freeze=manifest['source_freeze'];axis=manifest['time_axis'];physical=manifest['physical']
    if (freeze['source_sha']!=digest(freeze['files']) or manifest['source_sha']!=freeze['source_sha'] or
        manifest['time_axis_sha']!=digest(axis) or manifest['physical_sha']!=digest(physical)):
        raise ValueError('D0_SOURCE_TIME_PHYSICAL_DERIVATION_DRIFT')
    state=load_dday_state(manifest['initial_record']['path'],arm='B1')
    begin=state['begin_epoch_seconds']
    if (axis['planning_issue_epoch_seconds']!=begin or axis['evaluation_begin_seconds']!=begin or
        axis['evaluation_end_seconds']!=begin+86400 or axis['native_model_slots']!=[24,120] or
        axis['slots']!=96 or axis['dt_seconds']!=900 or axis['native_slot_zero_seconds']!=begin-21600 or
        axis['historical_six_hour_prefix_is_new_gate'] is not False):
        raise ValueError('D0_ORIGINAL_APPROVED_TIME_PROJECTION_REQUIRED')
    backlog=manifest['backlog_contract'];forecast=manifest['forecast_receipt']
    if backlog.get('contract_sha')!=digest({k:v for k,v in backlog.items() if k!='contract_sha'}) or (
        forecast.get('forecast_receipt_sha')!=digest({k:v for k,v in forecast.items() if k!='forecast_receipt_sha'})):
        raise ValueError('D0_BACKLOG_FORECAST_SEAL_DRIFT')
    expected_science=dict(name=SCIENCE,source=freeze['source_sha'],backlog=backlog['contract_sha'],
        time_axis=digest(axis),physical=digest(physical),CC4=forecast['forecast_receipt_sha'],
        known_policy='D0_OBSERVED_RUNNING_PINNED_AND_PENDING_RESEARCH_BACKLOG',
        official_MESS_UB='ADAPTIVE_BEAM_4_JOINT_ORIGINAL_FULL_INCUMBENT',official_MESS_LB='K48',
        historical_prefix_not_new_gate=True)
    if manifest['science_payload']!=expected_science or manifest['identity']['science_sha']!=digest(expected_science):
        raise ValueError('D0_SCIENCE_DERIVATION_DRIFT')
    public={k:state[k] for k in ('running','pending','historical_completed')}
    from .production_case import TIMING
    expected_case=dict(science_sha=digest(expected_science),initial_semantic_sha=SEMANTIC,
        public_input_sha=digest(public),forecast=forecast['forecast_receipt_sha'],
        native_source=file_record(SOURCE),timing=file_record(TIMING))
    if manifest['case_payload']!=expected_case or manifest['identity']['case_sha']!=digest(expected_case):
        raise ValueError('D0_CASE_PUBLIC_INPUT_DERIVATION_DRIFT')
    if (forecast['cc4_sha']!=manifest['identity']['cc4_sha'] or
        forecast['runtime_sha']!=manifest['identity']['runtime_sha'] or forecast['issue_seconds']!=begin or
        forecast['forecast_source_available_seconds']>begin):
        raise ValueError('D0_FORECAST_SOURCE_IDENTITY_CLOCK_DRIFT')
    verify_sources(manifest['source_freeze'],[manifest['initial_record'],manifest['source_native_record']]+
        list(physical['equipment'].values())+[physical['electrical_certificate']]+forecast['source_receipts']+
        manifest.get('planning_power_sources',[]))
    if (physical['network'],physical['AIDC'],physical['installed_GPU'],physical['installed_SVR'],
            physical['original_RegControl'])!=('IEEE123',12,780,11,7):
        raise ValueError('D0_ORIGINAL_PHYSICAL_AUTHORITY_REQUIRED')
    native=read(SOURCE)
    if not np.array_equal(forecast['Q50_GPUh'],native['C0_Q50']) or not np.array_equal(forecast['Q90_GPUh'],native['C0_Q90']):
        raise ValueError('D0_LITERAL_UNCHANGED_CC4_FORECAST_REQUIRED')
    if (file_sha(manifest['initial_record']['path'])!=INITIAL_BYTE or
        manifest['identity']['initial_state_sha']!=SEMANTIC):
        raise ValueError('D0_APPROVED_INITIAL_BINDING_DRIFT')
    if stage is not None and stage not in ('A1','M1','A2','M2'):
        raise ValueError('D0_ORIGINAL_FOUR_STAGE_REQUIRED')
    return manifest


def build_planning_inputs(*,output=REPORT,call_cap=25.):
    """Descriptors and physical coefficients only; no native model or solver."""
    from .d0_a_planning import compile_d0_known_data,D0ACase
    from .production_case import ProductionPhysicalContext,planning_power,initial_mess,TIMING
    from .a_engine import PlanningGridContext
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage,voltage_for
    import pandas as pd
    manifest,state,native,backlog,forecast,cc4=compile_contracts(output=output)
    compiled=compile_d0_known_data(manifest['initial_record'],source_bundle=native,
        backlog_contract=backlog,source_identity=manifest['identity'],cc4_receipt=forecast)
    data,rows,audit,receipts,windows=compiled
    campaign=read('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    physical=ProductionPhysicalContext(manifest['source_freeze'],campaign,data[0])
    power,idle,swing,power_sources=planning_power(data[0],physical.certificate)
    manifest.pop('manifest_sha')
    manifest['planning_power_sources']=power_sources
    manifest=seal(manifest,'manifest_sha')
    mess=initial_mess(data[0]);limits=voltage_for(Stage.A1)
    authority=GridAuthority(physical.certificate['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
        digest(data[0]['capacities']),digest(data[0]),digest(data[0]['battery']),limits.lower_squared,limits.upper_squared,
        True,stage=Stage.A1,transformer_current_authority_sha256=physical.thermal['transformer_current_authority_sha256'],
        thermal_authority=physical.thermal,require_all_transformer_currents=True)
    timing=pd.read_csv(TIMING)
    issued_m_cases={}
    def make_a_case(stage='A1',fixed_mess=None,folder=None,upstream_m_result=None):
        if stage not in ('A1','A2'):
            raise ValueError('D0_A1_A2_STAGE_REQUIRED')
        if stage=='A1' and fixed_mess is not None and fixed_mess!=mess:
            raise ValueError('D0_A1_INITIAL_ZERO_MESS_ANCHOR_REQUIRED')
        if stage=='A2':
            from .coordinator import _full_m
            if (upstream_m_result is None or upstream_m_result.get('case_sha') not in issued_m_cases or
                issued_m_cases[upstream_m_result['case_sha']]['stage']!='M1' or
                upstream_m_result.get('D0_source_identity')!=manifest['identity']):
                raise ValueError('D0_A2_CURRENT_M1_RESULT_BINDING_REQUIRED')
            verified_mess=_full_m(upstream_m_result)
            if fixed_mess!=verified_mess:
                raise ValueError('D0_A2_FIXED_M1_ANCHOR_DRIFT')
        fixed_mess=fixed_mess or mess
        grid=PlanningGridContext(physical.coefficients,power,idle,swing,tuple(timing.Q10),tuple(timing.Q90),
            tuple(cc4['kernel']),authority,fixed_mess)
        stage_sha=digest(dict(parent=manifest['identity']['case_sha'],stage=stage,
            input_MESS_anchor=fixed_mess['plan_sha'],backlog_contract=backlog['contract_sha']))
        return D0ACase(data,grid,Path(folder or Path(output)/stage),stage_sha,stage,'B3',windows,receipts,
            call_cap=float(call_cap),d0_input_audit=audit)
    def make_m_case(stage,aidc,folder):
        from .coordinator import _full_a
        from v42_may_campaign_native90.m_model import build_case
        from .m_candidates import generate
        from .m_engine import export_plan
        if stage not in ('M1','M2'):
            raise ValueError('D0_M1_M2_STAGE_REQUIRED')
        if (aidc.get('source_identity')!=manifest['identity'] or
            aidc.get('D0_input_sha')!=audit['a_input_sha'] or
            aidc.get('stage')!=('A1' if stage=='M1' else 'A2') or
            aidc.get('D0_issue_seconds')!=manifest['time_axis']['planning_issue_epoch_seconds']):
            raise ValueError('D0_M_STAGE_CURRENT_A_SOURCE_BINDING_REQUIRED')
        if stage=='M1' and aidc.get('case_sha')!=make_a_case('A1').case_sha:
            raise ValueError('D0_M1_CURRENT_A1_STAGE_CASE_DRIFT')
        if stage=='M2' and aidc.get('input_MESS_anchor') not in (
            r['output_MESS_anchor'] for r in issued_m_cases.values() if r.get('output_MESS_anchor')):
            raise ValueError('D0_M2_CURRENT_A2_M1_ANCHOR_BINDING_REQUIRED')
        if stage=='M2' and aidc.get('case_sha')!=digest(dict(parent=manifest['identity']['case_sha'],stage='A2',
                input_MESS_anchor=aidc['input_MESS_anchor'],backlog_contract=backlog['contract_sha'])):
            raise ValueError('D0_M2_CURRENT_A2_STAGE_CASE_DRIFT')
        _full_a(aidc);sites=sorted(data[0]['capacities'])
        planning=dict(sites=sites,PCC_P_kw=np.asarray([aidc['AIDC_P_by_site'][s] for s in sites]).T.tolist(),
            PCC_Q_kvar=np.asarray([aidc['AIDC_Q_by_site'][s] for s in sites]).T.tolist(),
            complete_AIDC_anchor=aidc['aidc_anchor'],CC4_service=aidc['CC4_service'],CC4_carryout=aidc['CC4_carryout'],
            anonymous_resource_envelope=aidc['anonymous_resource_envelope'])
        payload=dict(bundle=data[0],planning=planning,identity=dict(PASS=True,day='2025-05-01',arm='B3',stage=stage,
            AIDC_anchor=aidc['aidc_anchor'],QoS_SHA=backlog['contract_sha'],parent_case_sha=manifest['identity']['case_sha']))
        case=build_case(payload,dict(day='2025-05-01',arm='B3',stage=stage,output=str(folder)),integration_context=physical)
        case.candidate_generator=generate;case.plan_exporter=export_plan
        case.mess_stage_budget_seconds=0.
        issued_m_cases[case.case_sha]=dict(stage=stage,AIDC_anchor=aidc['aidc_anchor'],output_MESS_anchor=None)
        return case
    def bind_m_result(result):
        from .coordinator import _full_m
        if result.get('case_sha') not in issued_m_cases:
            raise ValueError('D0_UNISSUED_M_STAGE_RESULT')
        plan=_full_m(result);issued_m_cases[result['case_sha']]['output_MESS_anchor']=plan['plan_sha']
        result=deepcopy(result);result['D0_source_identity']=deepcopy(manifest['identity'])
        result['D0_fixed_AIDC_anchor']=issued_m_cases[result['case_sha']]['AIDC_anchor']
        return result
    require_case(manifest)
    _write(Path(output)/'D0_PLANNING_INPUT_AUDIT.json',audit)
    _write(Path(output)/'D0_CASE_MANIFEST.json',manifest)
    return dict(manifest=manifest,state=state,data=data,classification=rows,input_audit=audit,
        receipts=receipts,windows=windows,backlog=backlog,forecast=forecast,cc4=cc4,
        physical=physical,initial_mess=mess,make_a_case=make_a_case,make_m_case=make_m_case,bind_m_result=bind_m_result)
