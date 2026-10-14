"""Native0 one-event fixture with literal IEEE123/C1/780-GPU coefficients.

This verifies the numerical contract, not an executable May Planning handoff.
No Actual arrival bank, Environment, native model, solver or OpenDSS is used.
"""
from pathlib import Path
from copy import deepcopy
import json
import sys
from time import perf_counter

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.production_case import (ProductionPhysicalContext,planning_power,initial_mess,read)
from v42_integration.actual_validation import _power_model,_weather
from v42_integration.sensitivity_policy import build_grid_packet
from v42_integration.policy import digest
from v42_integration.cc4_policy_inputs import audit_signed_grid
from v42_integration.m_engine import file_record
from v42_native.grid import GridAuthority
from v42_native.voltage import Stage,voltage_for

REPORT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP'
SOURCE=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration')
ARCHIVE=Path('D:/v42_may_joint_repair_campaign_20261013')
HISTORICAL=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/A1/A_RESULT.json')


def main():
    began=perf_counter();REPORT.mkdir(parents=True,exist_ok=True)
    bundle=read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    projection=read(ARCHIVE/'inputs/B2/2025-05-01/NATIVE_INPUT.json')
    for key in ('electrical_certificate','grid_outputs','route_table'):bundle[key]=deepcopy(projection[key])
    manifest=read(ARCHIVE/'CAMPAIGN_MANIFEST.json')
    freeze=read(SOURCE/'SOURCE_FREEZE_DDAY_GRID_V5.json')
    physical=ProductionPhysicalContext(freeze,manifest,bundle)
    power,idle,swing,power_receipts=planning_power(bundle,physical.certificate)
    a=read(HISTORICAL);mess=initial_mess(bundle)
    initial=read(SOURCE/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
    begin=float(initial['begin_epoch_seconds']);sites=tuple(sorted(bundle['capacities']))
    bindings=dict(science_sha=freeze['source_sha'],case_sha=a['case_sha'],qos_sha=digest('NO_QOS_ISSUANCE_NUMERIC_FIXTURE'),
        aidc_anchor=a['aidc_anchor'],mess_anchor=mess['plan_sha'],cc4_sha=digest('UNCHANGED_SAVED_CC4_NUMERIC_FIXTURE_ONLY'),
        runtime_sha=digest('NO_RUNTIME_PROVIDER_QUERIED'),response_sha=physical.coefficients[0].coefficient_sha256,
        initial_state_sha=initial['common_initial_state_sha'])
    voltage=voltage_for(Stage.A1)
    authority=GridAuthority(physical.certificate['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
        digest(bundle['capacities']),digest(bundle),digest(bundle['battery']),voltage.lower_squared,voltage.upper_squared,
        True,stage=Stage.A1,transformer_current_authority_sha256=physical.thermal['transformer_current_authority_sha256'],
        thermal_authority=physical.thermal,require_all_transformer_currents=True)
    known=np.asarray([a['known_site_GPU'][s] for s in sites],float).T
    packet=build_grid_packet(physical.coefficients,power,swing,bundle['capacities'],a,mess,authority,bindings,
        begin_seconds=begin,known_gpu=known,
        mess_validation=dict(plan_sha=mess['plan_sha'],frozen_execution_validated=True),
        rack_compatibility={s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in sites})
    model,c1_receipts=_power_model(read(ARCHIVE/'raw/2025-05-01/POWER_AUTHORITY.json'),bundle['capacities'])
    weather,weather_receipt=_weather(read(ARCHIVE/'raw/2025-05-01/SOURCE_PROVENANCE.json'),begin,begin+900)
    current={s:0. for s in sites};observed_rows=[]
    for row in initial['running']:
        current[row['site']]+=row['gpu']
        observed_rows.append(dict(uid=row.get('uid',row.get('job_uid')),site=row['site'],gpu=row['gpu']))
    base=np.asarray([current[s] for s in sites]);exact=model.recompute(base[None,:],sites,weather)
    cols=[packet.control_names.index('aidc_load_kw['+s+']') for s in sites]
    base_delta=(exact['PCC_P_kw'][0]-packet.controls[0,cols])/packet.p_slope[0]
    baseline_peak,baseline_bad=packet._at_slot(0,base_delta)
    candidates=[];pq_error=0.;signed_error=0.
    c=packet.coefficients[0]
    for site in sites:
        j=sites.index(site);gpu=base.copy();gpu[j]+=1
        values=model.recompute(gpu[None,:],sites,weather)
        delta=(values['PCC_P_kw'][0]-packet.controls[0,cols])/packet.p_slope[0]
        peak,bad=packet._at_slot(0,delta)
        # Compare the literal normalized signed-current derivative at the
        # unchanged original polygon face. Evaluate all source line/phase
        # faces separately for the actual minimax ranking and hard guards.
        dp=values['PCC_P_kw'][0]-exact['PCC_P_kw'][0]
        dq=values['PCC_Q_kvar'][0]-exact['PCC_Q_kvar'][0]
        pq_error=max(pq_error,float(np.max(np.abs(dq-dp*np.tan(np.arccos(.95))))))
        control=packet.controls[0].copy();control[cols]=values['PCC_P_kw'][0]
        direct=c.current_constant+c.current_matrix.T@control
        original_control=packet.controls[0].copy();original_control[cols]=exact['PCC_P_kw'][0]
        original_direct=c.current_constant+c.current_matrix.T@original_control
        predicted=c.current_matrix[cols].T@dp
        signed_error=max(signed_error,float(np.max(np.abs(direct-original_direct-predicted))))
        gpu_ok=gpu[j]<=bundle['capacities'][site] and 1<=max(packet.rack_compatibility[site])
        candidates.append(dict(site=site,GPU_gang=1,current_Running_GPU=current[site],
            site_capacity=bundle['capacities'][site],current_GPU_rack_feasible=bool(gpu_ok),
            PCC_delta_P_kw=dp.tolist(),PCC_delta_Q_kvar=dq.tolist(),
            predicted_max_phase_line_loading=peak,grid_guard_status='PASS' if not bad else 'FAIL',
            violations=bad,admissible=bool(gpu_ok and not bad),
            all_original_line_phase_rows=True,all_original_transformer_rows=True,
            future_Known_runtime_overlap_veto=False,forecast_GPU_in_actual=0))
    feasible=[r for r in candidates if r['admissible']]
    choice=min(feasible,key=lambda r:(r['predicted_max_phase_line_loading'],r['site'])) if feasible else None
    signed_source=audit_signed_grid(bundle['electrical_certificate']['path'],manifest['thermal']['path'])
    receipt=dict(schema='AIDC_ORIGINAL_C1_IEEE123_CURRENT_EVENT_NUMERIC_FIXTURE_V1',status='PASS',
        scope='ORIGINAL_NUMERICAL_AND_CURRENT_EVENT_CONTRACT_ONLY_NOT_MAY_EXECUTION',
        observed_job='NAMED_SYNTHETIC_ONE_GPU_SUBMITTED_AT_CURRENT_EVENT',current_event_seconds=begin,
        original_A1= file_record(HISTORICAL),original_stage_case_sha=a['case_sha'],
        original_source_sha=freeze['source_sha'],original_Dday_snapshot= file_record(SOURCE/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'),
        Dday_state_is_original_model_assumption=initial.get('MODEL_ASSUMPTION',True),
        original_coefficients=physical.receipts[-1],original_C1_receipts=c1_receipts,
        original_planning_C1_secant_receipts=power_receipts,current_tick_weather=weather_receipt,
        current_tick_weather_only_delivered=True,actual_future_arrival_bank_read=False,
        sites=12,installed_GPU=sum(bundle['capacities'].values()),installed_SVR=11,
        original_voltage_lower_squared=packet.voltage_lower,original_voltage_upper_squared=packet.voltage_upper,
        line_phase_count=len(packet.line_indices),transformer_phase_count=len(packet.transformer_indices),
        current_Running_GPU_by_site=current,physical_GPU_from_observed_Running_only=True,
        Planning_Q50_GPU_also_present_but_not_added_to_actual={s:a['nominal_site_GPU'][s][0] for s in sites},
        observed_occupancy_GPU_sha=digest(observed_rows),original_saved_Planning_occupancy_is_not_actual=True,
        exact_C1_PQ_coupling_max_error_kvar=pq_error,literal_signed_current_derivative_max_error=signed_error,
        original_signed_face_algebra=signed_source,baseline_max_phase_line_loading=baseline_peak,
        baseline_grid_violations=baseline_bad,candidates=candidates,
        selected_site=None if choice is None else choice['site'],
        action='QUEUE' if choice is None else 'NUMERIC_FIXTURE_PREPLACE_NOT_EXECUTED',
        all_sites_evaluated=len(candidates)==12,Native_calls=0,Actual_calls=0,Fresh_AC_calls=0,
        actual_May_Unknown_UID=None,May_Actual_performance_status='NOT_RUN',May_handoff_status='NOT_CERTIFIED',
        wall_seconds=perf_counter()-began)
    if pq_error>1e-10 or signed_error>1e-10:raise ValueError('ORIGINAL_C1_SIGNED_NUMERIC_FIXTURE_ALGEBRA_FAIL')
    (REPORT/'AIDC_ORIGINAL_COEFFICIENT_FIXTURE.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'],scope=receipt['scope'],candidate_sites=12,
        admissible_sites=len(feasible),action=receipt['action'],baseline_grid_guard='PASS' if not baseline_bad else 'FAIL',
        C1_PQ_error=pq_error,signed_error=signed_error,Native_calls=0,wall_seconds=receipt['wall_seconds'])))


if __name__=='__main__':main()
