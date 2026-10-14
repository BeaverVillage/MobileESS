"""Write honest source audits and named current-event fixture evidence.

No native solve, OpenDSS run, production Actual replay or forecast refit.
"""
from pathlib import Path
from copy import deepcopy
import csv
import gzip
import hashlib
import json
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP'
HISTORICAL=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/A1/A_RESULT.json')
from v42_integration.aidc_resource_bridge import audit_planning_capacity,PlanningActualResourceBridge
from v42_integration.aidc_sensitivity_runtime import (CURRENT_EVENT_CONTRACT,CurrentEventSensitivityPolicy,
    CurrentEventJobEventController,grid_numeric_fingerprint)
from v42_integration.actual import run_actual,FrozenPowerModel
from v42_capacity.actual import Environment
from v42_integration.policy import digest
from v42_integration.q90_recourse import load_nominal_service
from v42_integration.cc4_policy_inputs import load_frozen_cc4
from v42_integration.production_case import KERNEL
from test_v42_aidc_followup import current_fixture,ready_data,run_witness,bridge_fixture
from test_v42_integration_actual import request


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def record(path):
    path=Path(path);data=path.read_bytes()
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def csv_write(name,rows,fields):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)


def compare_fixture(label,gate):
    commands={'K':dict(site='A',start_seconds=900,protected_segments=[
        dict(resource='gpu:A',begin=900,end=1800,quantity=1)])}
    provider,template=current_fixture(commands=commands,signed=True)
    packet=template.packet;packet.capacities={'A':1,'B':1};packet.controls[:,:2]=0
    for t,c in enumerate(packet.coefficients):
        c.anchor[:2]=0
        c.current_constant[:]=[.8,.4] if t==0 else [.1,.1]
        packet.bias[t]=c.current_constant.copy()
    policy=CurrentEventSensitivityPolicy(template.reference,packet,bindings=template.bindings,
        expected_bindings=template.bindings,basic=label=='C0',runtime_repair=label=='C2',
        runtime_fixture_gate=gate if label=='C2' else None,evidence_scope='NAMED_CURRENT_EVENT_C1_COMPARISON')
    path=OUT/(label+'_FIXTURE_FROZEN_POLICY.json');policy.save(path)
    policy=CurrentEventSensitivityPolicy.load(path,bindings=policy.bindings).bind_runtime_packet(packet)
    u=request('U',gpu=1,q50=900,compatible=('A','B'),qos='normal',protected=False,
        can_prestart_place=True,reference_start_seconds=0)
    k=request('K',gpu=1,q50=900,compatible=('A','B'),qos='normal',protected=False,
        can_prestart_place=True,reference_start_seconds=0,origin_unknown=False,preplacement_data=ready_data())
    power=FrozenPowerModel(0.,1.,{'A':1,'B':1},.95,lambda it,weather:np.asarray(it),'NAMED_C1_COMPARISON')
    policy.bind_observed_c1(power,current_weather_provider=lambda now:{})
    result=run_actual({'A':1,'B':1},[u,k],Environment({'U':1800,'K':900}),begin=0,end=3600,
        arm='B1',qos_window_provider=provider,frozen_policy=policy,known_schedule=commands,
        controller_class=CurrentEventJobEventController,expected_bindings=policy.bindings,
        power_model=power,weather=[{}]*4)
    peaks=[]
    for t,gpu in enumerate(result['occupancy_GPU']):
        peak,_=packet._at_slot(t,gpu);peaks.append(peak)
    result['fixture_peak']=max(peaks)
    return result,policy


def short_fixture():
    provider,policy=current_fixture(runtime=True)
    u=request('SHORT',gpu=8,q50=1800,compatible=('A',),reference_start_seconds=0)
    waiting=request('WAIT',gpu=8,q50=900,compatible=('A',),reference_start_seconds=0)
    result=run_actual({'A':8,'B':8},[u,waiting],Environment({'SHORT':100,'WAIT':900}),begin=0,end=2700,
        arm='B1',qos_window_provider=provider,frozen_policy=policy,controller_class=CurrentEventJobEventController)
    rows={r['job_uid']:r for r in result['queue_ledger']}
    assert rows['SHORT']['release_control_time']==100 and rows['WAIT']['admitted_time']==900
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    historical=read(HISTORICAL)
    bundle=read('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    target=read(ROOT/'docs/v42_unified_aidc_mess_research_20261014/AIDC_SOURCE_DIAGNOSTIC/PLANNING_TARGET_IDENTITY.json')
    _,capacity=audit_planning_capacity(historical,bundle['capacities'])
    cc4=load_frozen_cc4('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json',
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/CC4/DAY_20250501.json',kernel_path=KERNEL,
        runtime_integrity_path=ROOT/'v42_final/runtime_bundle/INTEGRITY.json',
        planning_bundle_path='D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    if (not np.array_equal(cc4['q50_hourly_GPUh'],target['CC4_Q50'])
            or not np.array_equal(cc4['q90_hourly_GPUh'],target['CC4_Q90'])):
        raise ValueError('HISTORICAL_KNOWN_CC4_LITERAL_SOURCE_PAIR_DRIFT')
    authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha=target['cc4_sha'],
        kernel_sha=cc4['kernel_sha'],
        timing_envelope_sha=target['Timing_CDF_SHA'],aidc_anchor=historical['aidc_anchor'],
        q50_hourly_GPUh=target['CC4_Q50'],q90_hourly_GPUh=target['CC4_Q90'])
    nominal=load_nominal_service(historical,target['CC4_Q50'],target['Timing_CDF_Q10'],
        target['Timing_CDF_Q90'],source_authority=authority)
    boundary_path=ROOT/'runtime/v42_unified/FOLLOWUP_BASELINE/HISTORICAL_EXACT_BOUNDARY_AUDIT.json'
    boundary=read(boundary_path)
    attempts=[]
    for name in ('B1_NEW_A1_ATTEMPT01','B1_NEW_A1_ATTEMPT02','B1_NEW_A1_ATTEMPT03'):
        path=ROOT/'docs/v42_unified_aidc_mess_research_20261014'/name/'B1_NEW_A1_RESULT.json'
        if path.is_file():
            attempt=read(path);attempts.append(dict(name=name,status=attempt['status'],
                FULL_feasible=attempt.get('A1_FULL_feasible',False),bindings=attempt.get('bindings'),source=record(path)))
    patch=ROOT/'docs/v42_unified_aidc_mess_research_20261014/PR_PAUSED_RESEARCH/AIDC_UNVERIFIED_POST_SMOKE/RESTORE_UNVERIFIED_AIDC_POST_SMOKE.patch.gz'
    patch_text=gzip.decompress(patch.read_bytes()).decode('utf-8')
    source_audit=dict(status='PASS',scope='HISTORICAL_SAVED_PLANNING_ALGEBRA_ONLY',
        historical_A1=record(HISTORICAL),stage_case_sha=historical['case_sha'],
        aidc_anchor=historical['aidc_anchor'],FULL_feasible=historical['FULL_feasible'],
        original_FULL_max_residual=historical['FULL_max_residual'],rho=historical['rho'],
        capacity=capacity,cohort_service_replay=nominal['replay'],
        CC4_literal_source_receipts=cc4['source_receipts'],CC4_source_model_id=cc4['model_id'],
        q50_GPUh=sum(target['CC4_Q50']),saved_nominal_in_day_GPUh=sum(map(sum,historical['nominal_site_GPU'].values()))/4,
        saved_nominal_carryout_GPUh=sum(historical['CC4_carryout'].values()),
        saved_Known_UIDs=len(historical['selected_jobs']),historical_source_family='SOURCE18R_V5',
        historical_actual_handoff_status='NOT_CERTIFIED',historical_exact_Dday_boundary=record(boundary_path),
        historical_boundary_counts=boundary['counts'],original_Dday_artifact_missing=False,
        original_Dday_model_assumption=boundary['original_boundary_is_model_assumption'],
        issue_to_Dday_prefix_executed=boundary['Apr30_queue_replay_executed'],
        E60_status='SAME_CASE_A1_NOT_CERTIFIED',E60_attempts=attempts,
        latest_diagnostic_FCFS='DIAGNOSTIC_ONLY_NEVER_ACTIVE_PLANNING',
        unverified_patch=dict(source=record(patch),read_for_audit=True,applied=False,
            content_contains_conservative_future_firm_booking_audit='firm_booking' in patch_text,
            decision='Historical diagnostic probes retained as archive; new current event algorithm developed independently.'),
        Native_calls=0,Actual_May_calls=0,Fresh_AC_calls=0)
    write('KNOWN_CC4_RESERVE_CAPACITY_AUDIT.json',source_audit)
    # Validate the base witness before enabling the runtime fixture ablation.
    basic,_=run_witness()
    rows={r['job_uid']:r for r in basic['queue_ledger']}
    assert rows['U']['admitted_time']==0 and rows['K']['site']=='B' and rows['K']['admitted_time']==900
    gate=dict(status='PASS',controller_contract=CURRENT_EVENT_CONTRACT,
        basic_allocation_and_corrective_fixture_PASS=True,evidence_scope='NAMED_NATIVE0_PHYSICAL_FIXTURE',
        current_source_sha=record(ROOT/'v42_integration/aidc_sensitivity_runtime.py')['sha256'],
        basic_witness_sha=digest(basic['carryout']['controller']['current_event_state']),
        real_May_PASS=False)
    write('AIDC_BASIC_FIXTURE_GATE.json',gate)
    a,args=bridge_fixture();bridge=PlanningActualResourceBridge(a,**args)
    meta=dict(uid='OBSERVED_U',submit_seconds=0,event_seconds=0,is_observed=True,
        origin_unknown=True,state='PENDING',gpu=2,t50_seconds=900)
    bridge.observe(meta,0)
    class EmptyReservations:reservations={}
    first=bridge.snapshot(0,{'OBSERVED_U':meta},EmptyReservations())
    meta.update(state='RUNNING',current_site='B',accumulated_compute_seconds=300)
    second=bridge.snapshot(300,{'OBSERVED_U':meta},EmptyReservations())
    meta.update(state='COMPLETED',accumulated_compute_seconds=600)
    third=bridge.snapshot(600,{'OBSERVED_U':meta},EmptyReservations())
    write('AIDC_PLANNING_ACTUAL_RESOURCE_BRIDGE.json',dict(status='PASS',
        scope='NAMED_NATIVE0_FIXTURE_ACCOUNTING_AND_HISTORICAL_PLANNING_REPLAY',
        fixture=bridge.export(),historical_Planning_capacity_status=capacity['status'],
        current_E60_A1_status='SAME_CASE_A1_NOT_CERTIFIED',historical_Actual_handoff_status='NOT_CERTIFIED',
        historical_Dday_blocker_counts=boundary['counts'],actual_May_status='NOT_RUN',
        Full96_status='NOT_RUN',Fresh_AC_status='NOT_RUN',Native_calls=0))
    csv_write('CC4_FORECAST_TO_ACTUAL_OCCUPANCY.csv',[dict(status='PASS',scope='NAMED_FIXTURE',
        uid='OBSERVED_U',event_seconds=x['event_seconds'],forecast_debit_count=1,
        actual_Running_GPU=sum(x['actual_Running_GPU'].values()),actual_Committed_GPU=sum(x['actual_Committed_GPU'].values()),
        remaining_CC4_Q50_GPUh=x['remaining_CC4_Q50_GPUh'],completed_actual_GPUh=x['observed_Unknown_completed_actual_GPUh'],
        carry_computed_actual_GPUh=x['observed_Unknown_carry_computed_actual_GPUh'],forecast_physical_GPU=0)
        for x in (first,second,third)],['status','scope','uid','event_seconds','forecast_debit_count',
        'actual_Running_GPU','actual_Committed_GPU','remaining_CC4_Q50_GPUh','completed_actual_GPUh',
        'carry_computed_actual_GPUh','forecast_physical_GPU'])
    variants={};policies={};comparison=[];unknown=[];corrective=[];runtime=[];backfill=[]
    for label in ('C0','C1','C2'):
        result,policy=compare_fixture(label,gate);variants[label]=result;policies[label]=policy
        state=result['carryout']['controller']['current_event_state']
        q={r['job_uid']:r for r in result['queue_ledger']}
        base_unknown_site=None if label=='C0' else next(r for r in variants['C0']['queue_ledger'] if r['job_uid']=='U')['site']
        changed_GPUh=0. if label=='C0' or q['U']['site']==base_unknown_site else q['U']['GPU_gang']*q['U']['accumulated_compute_seconds']/3600
        comparison.append(dict(status='DIAGNOSTIC_ONLY',scope='NAMED_NATIVE0_FIXTURE',variant=label,
            observed_Unknown_UIDs=1,executed_Unknown_UIDs=int(q['U']['admitted_time'] is not None),
            Unknown_actual_site=q['U']['site'],Known_actual_site=q['K']['site'],
            Known_corrective_preplacement_UIDs=len(state['actual_corrective_commands']),
            Known_actual_start_delay_seconds=q['K']['admitted_time']-900,
            changed_GPUh=changed_GPUh,fixture_max_line_loading=result['fixture_peak'],
            May01_max_line_loading=None,Fresh_AC_status='NOT_RUN',Actual_global_MILP_calls=0,
            latency_scope='UNKNOWN_CURRENT_SITE_SELECTION_ONLY_KNOWN_CORRECTIVE_LATENCY_NOT_CERTIFIED',
            Controller_P50_seconds=float(np.percentile(policy.times,50)),Controller_P95_seconds=float(np.percentile(policy.times,95)),
            Controller_max_seconds=max(policy.times)))
        for entry in policy.audit:
            decision=entry['decision'];unknown.append(dict(variant=label,status='PASS',scope='NAMED_FIXTURE',
                uid=entry['uid'],event_seconds=entry['time_seconds'],site=decision.get('site'),action=decision['action'],
                predicted_max_phase_line_loading=decision.get('tracking',{}).get('grid_peak'),
                future_Known_speculative_veto=False,all_line_phase_rows=True))
        corrective.extend(dict(variant=label,status='PASS',scope='NAMED_FIXTURE',**row) for row in state['corrective_audit'])
        runtime.extend(dict(variant=label,status='PASS',scope='NAMED_FIXTURE',**row) for row in state['runtime_events'])
        backfill.extend(dict(variant=label,status='PASS',scope='NAMED_FIXTURE',**row) for row in state['backfill_results'])
    short=short_fixture()['carryout']['controller']['current_event_state']
    runtime.extend(dict(variant='SHORT_BACKFILL_FIXTURE',status='PASS',scope='NAMED_FIXTURE',**r)
        for r in short['runtime_events'])
    backfill.extend(dict(variant='SHORT_BACKFILL_FIXTURE',status='PASS',scope='NAMED_FIXTURE',**r)
        for r in short['backfill_results'])
    csv_write('UNKNOWN_SIGNED_SENSITIVITY_ALLOCATION.csv',unknown,['variant','status','scope','uid','event_seconds',
        'site','action','predicted_max_phase_line_loading','future_Known_speculative_veto','all_line_phase_rows'])
    csv_write('KNOWN_CORRECTIVE_PREPLACEMENT.csv',corrective,['variant','status','scope','uid','original_planned_site',
        'original_planned_start_seconds','actual_site','actual_start_seconds','trigger_seconds','reason','GPU_capacity_conflict',
        'original_grid_loading','corrected_grid_loading','transfer_seconds','preparation_seconds',
        'ready_at_seconds','qos_preparation_budget_used_seconds','grid_loading_after_actual_start',
        'completion_result','planning_command_modified'])
    csv_write('RUNTIME_SHORT_OVERRUN_EVENTS.csv',runtime,['variant','status','scope','uid','time_seconds','event',
        'elapsed_seconds','Q50_seconds','Running_gpu_preserved','release_control_seconds','actual_completion_read'])
    csv_write('BACKFILLING_QOS_RESULTS.csv',backfill,['variant','status','scope','uid','time_seconds','site','feasible','reason',
        'guaranteed_completion_claim','source_executable_event_required'])
    csv_write('AIDC_C0_C1_C2_COMPARISON.csv',comparison,list(comparison[0]))
    write('AIDC_FIXTURE_C0_C1_C2_RESULT.json',dict(status='PASS',scope='NAMED_NATIVE0_FIXTURE_ONLY',
        comparison=comparison,identical_initial_Planning_commands=True,identical_exogenous_arrivals_runtime=True,
        identical_corrective_rights=True,Actual_Known_execution_SHA_must_match=False,
        May01_real_Changed_GPUh=None,May01_real_Uknown_allocation_status='NOT_RUN',
        real_source_grid_coefficients_used_in_named_fixture=False,
        Original_C1_and_OriginalGridPacket_evaluation_contract_used=True))
    write('AIDC_FRESH_AC_VALIDATION.json',dict(status='NOT_RUN',installed_SVR=11,
        original_voltage_current_transformer_constraints_preserved=True,May01_Full96='NOT_RUN',
        same_case_handoff_status='NOT_CERTIFIED',Fresh_AC_SAFE_PERFORMANCE_PASS=False,
        source_only_historical_numeric_certificates_reused_for_new_Actual=False))
    (OUT/'AIDC_FINAL_REVIEW_KO.md').write_text(
        'Known과 CC4는 과거 같은 A1 결과의 96×12 행렬로 함께 고려되었다. '
        'Q50 Nominal은 미도착 수요의 예상 점유이며 실제 Job 예약이 아니다. '
        '저장된 과거 A1의 Achieved CC4/Runtime Reserve는 모두 0 GPU-slot이고, '
        '부족량은 각각 75,649 및 17,330 GPU-slot이다. 이를 확보된 여유로 해석하지 않았다.\n\n'
        '새 CurrentEvent 제어기는 Unknown 입장 시 현재 Running/Committed GPU와 모든 선로/상 signed loading을 사용한다. '
        '미래 Known 예약과 불확실한 Runtime의 잠재적 겹침만으로 입장을 차단하지 않는다. '
        '실제 시작 이벤트의 GPU 충돌에서만 PENDING Known을 다른 사이트로 평가한다. '
        '원래 Planning 명령은 보존하고 Actual corrective 명령을 따로 저장한다. '
        '원본 권한과 데이터 준비 증거가 없으면 Queue한다. 전송은 원본 bytes/s WAN 단위와 '
        '15분 전송 계약을 사용하고, 준비가 끝난 뒤 현재 GPU 및 계통을 다시 검사한다.\n\n'
        '명명 Native0 Fixture에서 Unknown 실행, 실제 Known 충돌과 corrective pre-placement, '
        '대체 사이트/데이터 권한/WAN 부족 시 Queue, Running 보호, QoS 준비 예산, '
        'Forecast 1회 차감과 실제 GPU 분리, Runtime overrun, 실제 Completion 즉시 GPU 해제 및 '
        '다음 합법적 15분 이벤트 backfill을 검증했다. Backfill은 선택한 각 후보 사이트의 '
        '미래 확정 예약을 검사하며 검증된 비선점 Runtime 상한이 없으면 안전 대기한다. '
        '조건부 잔여 Runtime은 NOT_CERTIFIED로 남기고 미래 실제 완료시각을 읽지 않는다.\n\n'
        'Fixture는 실제 C1 재계산 클래스와 OriginalGridPacket의 같은 평가 경로를 사용하지만 '
        '수치계수는 명명 합성 Fixture이다. 실제 May01 개선 또는 Fresh AC PASS를 의미하지 않는다. '
        'C0/C1/C2 Fixture 최대 선로부하율은 비교 CSV에 있고 실제 May01 값은 NOT_RUN이다.\n\n'
        'AIDC_ORIGINAL_COEFFICIENT_FIXTURE.json은 별도의 Native0 수치 계약 검증이다. '
        '원본 IEEE123 11-SVR 계수, C1 모델, 12 AIDC/780 GPU 및 원본 D-day 관측 점유를 '
        '사용해 현재 합성 1-GPU 제출의 모든 사이트 후보와 선로/상/변압기 행을 검사했다. '
        '후보가 전압·전류·GPU 제약에 실패하면 그대로 거부한다. '
        '이는 실제 Unknown 입장이나 같은 Case Planning–Actual 실행 인증은 아니다.\n\n'
        '기존 Source18R_V5 A1은 FULL-feasible Planning 증거가 있으나, 같은 원본 D-day 아티팩트가 '
        '존재해도 Apr30→D-day prefix 실행이 검증되지 않았고 과거 명령과 관측 Running/사이트/시작이 불일치한다. '
        '따라서 역사적 Actual handoff 역시 NOT_CERTIFIED다. 최신 E60 A1 시도 1–3은 '
        'SAME_CASE_A1_NOT_CERTIFIED다. 진단 FCFS를 Planning으로 승격하거나 명령을 현재로 이동하지 않았다.\n\n'
        '60분은 참여 Batch 연구 정책이며 고객 SLA가 아니다. 본 기본 제어의 의도적 Time-shifting과 '
        'Checkpoint Migration은 NOT_RUN/HOLD이다. 새로운 A1 Heavy solve는 하지 않았다. '
        'May01 실제 Canary, Full96, 11-SVR Fresh AC, A1–M1–A2–M2 실제 통합은 같은 Case와 '
        '검증된 초기 상태의 handoff가 복구될 때까지 인증할 수 없다.\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',scope='NAMED_FIXTURE_AND_HISTORICAL_PLANNING_AUDIT',
        C0_C1_C2_fixture_peaks=[r['fixture_max_line_loading'] for r in comparison],
        real_May_status='NOT_RUN',E60_A1='SAME_CASE_A1_NOT_CERTIFIED',Native_calls=0)))


if __name__=='__main__':main()
