"""Read immutable V5 inputs for a separate fixed-anchor research replay.

This loader performs no optimizer, model construction or AC solve. Its saved
A2/M2 are numerical reference anchors; they are not new contract optima.
"""
from copy import deepcopy
from pathlib import Path
from datetime import datetime
import pickle
import csv
import numpy as np

from .a_engine import digest
from .production_case import (STATIC,ARCHIVE,KERNEL,TIMING,ProductionPhysicalContext,
    assemble_native_bundle,planning_power,read)
from .planning_inputs import prepare_planning
from .actual_validation import prepare_actual
from .cc4_policy_inputs import load_frozen_cc4
from .sensitivity_policy import OriginalGridPacket,FrozenSensitivityPolicy
from .experimental_grid import ExperimentalGridPacket
from .m_engine import file_record
from .q90_recourse import load_nominal_service
from v42_temporal.service import validate_envelope

BASE_ATTEMPT=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01')
BASE_DOCS=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration')


def load_conditional_source():
    """Bind exact original physical coefficients and nominal public contracts."""
    freeze=read(BASE_DOCS/'SOURCE_FREEZE_DDAY_GRID_V5.json')
    planned=read(BASE_ATTEMPT/'B3/PLANNING_FREEZE.json')
    policy=FrozenSensitivityPolicy.load(BASE_ATTEMPT/'B3/OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json')
    a=read(BASE_ATTEMPT/'B3/A2/A_RESULT.json')
    m=read(BASE_ATTEMPT/'B3/M2/COMMON_M_PR222/M_STAGE_RESULT.json')['mess']
    execution=read(BASE_ATTEMPT/'B3/MESS_ACTUAL_EXECUTION_RECEIPT.json')
    with STATIC.open('rb') as stream:data=pickle.load(stream)
    projection=read(ARCHIVE/'inputs/B2/2025-05-01/NATIVE_INPUT.json')
    template=read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    bundle,merge=assemble_native_bundle(data[0],projection,template)
    issue=datetime.fromisoformat(template['issue_time'].replace('Z','+00:00')).timestamp()
    known_commands={}
    # Reuse the coordinator's native-option -> absolute execution convention.
    # Saved PLANNING_FREEZE.Known_schedule is a Native option, not a command.
    for uid,option in planned['Known_schedule'].items():
        if 'start_seconds' in option:known_commands[uid]=option
        else:
            command=dict(start_seconds=issue+option['start']*900,
                site=option['initial_site'],original_option=option)
            if option.get('checkpoint',-1)>=0:
                command.update(migration_destination=option['destination'],
                    checkpoint_control_seconds=issue+option['checkpoint']*900,
                    physical_checkpoint_seconds=issue+option['physical_checkpoint_seconds'])
            known_commands[uid]=command
    data=(bundle,)+tuple(data[1:])
    manifest=read(ARCHIVE/'CAMPAIGN_MANIFEST.json')
    physical=ProductionPhysicalContext(freeze,manifest,bundle)
    power,idle,swing,power_sources=planning_power(bundle,physical.certificate)
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage,voltage_for
    voltage=voltage_for(Stage.A1)
    authority=GridAuthority(physical.certificate['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
        digest(bundle['capacities']),digest(bundle),digest(bundle['battery']),voltage.lower_squared,voltage.upper_squared,
        True,stage=Stage.A1,transformer_current_authority_sha256=physical.thermal['transformer_current_authority_sha256'],
        thermal_authority=physical.thermal,require_all_transformer_currents=True)
    sites=tuple(sorted(bundle['capacities']))
    known=np.array([a['known_site_GPU'][s] for s in sites],float).T
    anonymous=np.array([a['nominal_site_GPU'][s] for s in sites],float).T
    packet=ExperimentalGridPacket(physical.coefficients,power,swing,bundle['capacities'],a,m,authority,
        policy.bindings,begin_seconds=planned['actual_gate']['day_begin_epoch_seconds'],known_gpu=known,
        power_factor=.95,mess_validation=execution,
        rack_compatibility={s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in sites})
    cc4=load_frozen_cc4('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json',
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/CC4/DAY_20250501.json',kernel_path=KERNEL,
        runtime_integrity_path=Path(__file__).parents[1]/'v42_final/runtime_bundle/INTEGRITY.json',
        planning_bundle_path=ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    if any(cc4[k]!=policy.bindings[b] for k,b in (('prediction_sha','cc4_sha'),('runtime_sha','runtime_sha'))):
        raise ValueError('EXPERIMENTAL_SAVED_PROVIDER_BINDING_DRIFT')
    queue_authority={k:cc4[k] for k in ('model_id','prediction_sha','kernel_sha')}
    queue_authority.update(future_Actual_or_UID_inputs_used=False,forecast_modifications=0)
    with TIMING.open(encoding='utf-8-sig',newline='') as stream:
        timing=list(csv.DictReader(stream))
    lower=np.array([float(row['Q10']) for row in timing])
    upper=np.array([float(row['Q90']) for row in timing])
    validate_envelope(lower,upper)
    if [int(row['lag_slot']) for row in timing]!=list(range(len(timing))):
        raise ValueError('ORIGINAL_TRAIN_CDF_SLOT_AXIS_DRIFT')
    # All candidates share this full-day source counterfactual. Actual submit
    # depletion belongs only to its existing ForecastBook, never this recourse.
    recourse_authority=dict(queue_authority,timing_envelope_sha=file_record(TIMING)['sha256'],
        q50_hourly_GPUh=cc4['q50_hourly_GPUh'],q90_hourly_GPUh=cc4['q90_hourly_GPUh'],
        source_receipts=[*cc4['source_receipts'],file_record(TIMING),
            file_record(BASE_ATTEMPT/'B3/A2/A_RESULT.json')])
    nominal_service=load_nominal_service(a,cc4['q50_hourly_GPUh'],lower,upper,
        source_authority=recourse_authority)
    strict_stats=BASE_DOCS/'QOS_EMPIRICAL_STATS_STRICT.json'
    provider_sha=digest(bundle['runtime_provider'])
    initial=BASE_DOCS/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'
    verified_inputs=[]

    def fresh_actual_inputs():
        # Each experiment starts with a new provider, reference and PRIVATE
        # Environment. Future arrivals enter the controller at submit only.
        # Verify and parse immutable bytes once. The cached prototype is never
        # executed; deepcopy retains the shared issuer within each experiment,
        # while isolating references, depletion and private service state.
        if not verified_inputs:
            planning=prepare_planning(ARCHIVE/'raw/2025-05-01',data,source_freeze=freeze,
                strict_stats=strict_stats,case_sha=planned['case_sha'],provider_sha=provider_sha)
            prepared=prepare_actual(ARCHIVE/'raw/2025-05-01',source_freeze=freeze,strict_stats=strict_stats,
                case_sha=planned['case_sha'],provider_sha=provider_sha,initial_state_freeze=initial,
                planning_provider=planning['qos_provider'],planning_known_receipts=planning['known_receipts'],arm='B3')
            verified_inputs.append((prepared,planning))
        return deepcopy(verified_inputs[0])

    source_receipts=[file_record(STATIC),file_record(BASE_DOCS/'SOURCE_FREEZE_DDAY_GRID_V5.json'),
        file_record(BASE_ATTEMPT/'B3/A2/A_RESULT.json'),
        file_record(BASE_ATTEMPT/'B3/M2/COMMON_M_PR222/M_STAGE_RESULT.json'),
        file_record(BASE_ATTEMPT/'B3/OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'),
        file_record(initial),file_record(TIMING),*physical.receipts,*power_sources,*cc4['source_receipts']]
    local_root=Path(__file__).parents[1]
    source_receipts.extend(file_record(local_root/name) for name in (
        'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json',
        'docs/v42_autonomous_grid_controls_april_b0/audit_sources.py',
        'docs/v42_april_b0_capacity_queue_voltage_calibration/ELECTRICAL_SOURCE_AUTHORITY.json'))
    return dict(packet=packet,aidc=a,mess=m,original_policy=policy,bindings=policy.bindings,
        frozen_anonymous_gpu=anonymous,q50_hourly=cc4['q50_hourly_GPUh'],q90_hourly=cc4['q90_hourly_GPUh'],
        kernel=cc4['kernel'],queue_authority=queue_authority,cc4=cc4,bundle=bundle,data=data,
        planning_freeze=planned,source_receipts=source_receipts,fresh_actual_inputs=fresh_actual_inputs,
        known_commands=known_commands,
        nominal_service=nominal_service,train_cdf_lower=lower,train_cdf_upper=upper,
        recourse_source_authority=recourse_authority,
        original_source_science_sha=freeze['source_sha'],original_physical_authority=physical,
        scope='FIXED_V5_A2_M2_REFERENCE_FOR_CAUSAL_CONDITIONAL_REPLAY_NOT_NEW_A_M_OPTIMUM')
