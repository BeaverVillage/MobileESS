"""Versioned recovery evidence; never transfer historical/fixture PASS to May."""
from pathlib import Path
import argparse
import csv
import json
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP'
RUN=OUT/'RECOVERY_01'
SNAP=ROOT/'runtime/BOUNDARY_RECOVERY_SUPERVISOR/START_SNAPSHOT.json'
from v42_integration.unified_contract import file_sha, digest
from v42_integration.actual_validation import record


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require_new_report(path):
    path=Path(path)
    protected={name.replace('\\','/') for name in read(SNAP)['prior_followup_files']}
    if str(path.relative_to(ROOT)).replace('\\','/') in protected:
        raise ValueError('PRIOR_FOLLOWUP_REPORT_MUST_NOT_BE_OVERWRITTEN')
    return path


def write(path,value):
    path=require_new_report(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')


def cc4_report():
    from v42_integration.aidc_resource_bridge import audit_planning_capacity
    from v42_integration.cc4_policy_inputs import load_frozen_cc4
    from v42_integration.q90_recourse import load_nominal_service
    from v42_integration.production_case import KERNEL
    from v42_integration.coordinator import _full_a
    target=read(ROOT/'docs/v42_unified_aidc_mess_research_20261014/AIDC_SOURCE_DIAGNOSTIC/PLANNING_TARGET_IDENTITY.json')
    native=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    capacities=read(native)['capacities']
    cc4=load_frozen_cc4('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json',
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/CC4/DAY_20250501.json',
        kernel_path=KERNEL,runtime_integrity_path=ROOT/'v42_final/runtime_bundle/INTEGRITY.json',
        planning_bundle_path=native)
    if (not np.array_equal(cc4['q50_hourly_GPUh'],target['CC4_Q50']) or
            not np.array_equal(cc4['q90_hourly_GPUh'],target['CC4_Q90'])):
        raise ValueError('HISTORICAL_CC4_LITERAL_SOURCE_DRIFT')
    stages={}
    for stage in ('A1','A2'):
        path=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')/stage/'A_RESULT.json'
        a=read(path);_full_a(a)
        matrices,capacity=audit_planning_capacity(a,capacities)
        authority=dict(model_id=cc4['model_id'],prediction_sha=target['cc4_sha'],
            kernel_sha=cc4['kernel_sha'],timing_envelope_sha=target['Timing_CDF_SHA'],
            aidc_anchor=a['aidc_anchor'],q50_hourly_GPUh=target['CC4_Q50'],q90_hourly_GPUh=target['CC4_Q90'])
        nominal=load_nominal_service(a,target['CC4_Q50'],target['Timing_CDF_Q10'],
            target['Timing_CDF_Q90'],source_authority=authority)
        stages[stage]=dict(source_record=record(path),stage_case_sha=a['case_sha'],
            aidc_anchor=a['aidc_anchor'],FULL_feasible=a['FULL_feasible'],
            FULL_max_residual=a['FULL_max_residual'],capacity=capacity,
            Known_plan_GPUh=float(matrices['known_site_GPU'].sum()/4),
            Unknown_Q50_nominal_in_day_GPUh=float(matrices['nominal_site_GPU'].sum()/4),
            CC4_nominal_carryout_GPUh=float(sum(nominal['carryout_GPUh_by_hour'])),
            original_CDF_service_carry_replay=nominal['replay'])
    result=dict(status='PASS',scope='PR223_A1_AND_FINAL_A2_SAVED_RESOURCE_ALGEBRA_ONLY',
        source_family='SOURCE18R_V5',stages=stages,CC4_source_receipts=cc4['source_receipts'],
        nominal_forecast_is_physical_GPU=False,Unknown_site_marginal_is_actual_command=False,
        observed_UID_debit_contract='ONCE_AT_PUBLIC_ACTUAL_SUBMIT',
        original_planning_preserved=True,achieved_reserve_required=True,
        fixture_debit_evidence=record(OUT/'AIDC_PLANNING_ACTUAL_RESOURCE_BRIDGE.json'),
        current_May01_handoff_status='NOT_CERTIFIED',Actual_May01_runs=0,
        native_calls=0,future_actual_completion_read_by_controller=False)
    write(OUT/'CC4_NOMINAL_TO_ACTUAL_GPU_BRIDGE.json',result)
    return result


def empty_real_ledgers():
    fields={
        'AIDC_REAL_EVENT_ALLOCATION_COMPARISON.csv':[
            'variant','uid','episode_id','event_seconds','reference_site','actual_site',
            'GPU_gang','changed_GPUh','max_line_loading','controller_seconds','source_sha','case_sha'],
        'KNOWN_CORRECTIVE_PREPLACEMENT_EVENTS.csv':[
            'uid','episode_id','event_seconds','original_site','corrective_site','ready_seconds',
            'GPU_gang','authority_sha','data_source_sha','WAN_bytes','actual_command_sha','source_sha','case_sha']}
    for name,columns in fields.items():
        path=require_new_report(OUT/name)
        with path.open('w',encoding='utf8',newline='') as stream:
            csv.writer(stream).writerow(columns)


def verify_history():
    start=read(SNAP)
    drift=[name for name,sha in start['prior_followup_files'].items()
        if not(ROOT/name).is_file() or file_sha(ROOT/name)!=sha]
    ledger_path=ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    ledger=read(ledger_path)
    if ledger['calls'][:len(start['calls'])]!=start['calls'] or ledger['conservative_solve_seconds']<start['used']:
        raise ValueError('HISTORICAL_NATIVE_USAGE_OR_CALLS_REWRITTEN')
    if drift:
        raise ValueError('PRIOR_REPORT_BYTE_DRIFT:'+','.join(drift))
    result=dict(status='PASS',prior_reports_verified=len(start['prior_followup_files']),
        prior_report_byte_drift=drift,base_commit=start['base_commit'],
        native_prior_call_prefix_preserved=True,usage_reset=False,
        Native_before_seconds=start['used'],Native_used_seconds=ledger['conservative_solve_seconds'],
        Native_added_seconds=ledger['conservative_solve_seconds']-start['used'],
        Native_limit_seconds=ledger['limit_seconds'],
        Native_remaining_seconds=ledger['limit_seconds']-ledger['conservative_solve_seconds'],
        inflight=ledger['inflight'],canonical_ledger=record(ledger_path))
    write(RUN/'HISTORY_AND_NATIVE_PRESERVATION.json',result)
    write(RUN/'UNIFIED_NATIVE_LEDGER.json',ledger)
    write(OUT/'UNIFIED_NATIVE_LEDGER_RECOVERY_01.json',result)
    return result


def final_reports(history):
    prefix=read(OUT/'PLANNING_ISSUE_TO_DDAY_PREFIX_RECONCILIATION.json')
    binding=read(OUT/'ORIGINAL_SAME_CASE_A1_ACTUAL_BINDING.json')
    initial=read(OUT/'PR223_DDAY_INITIALIZATION_REUSE_AUDIT.json')
    regression=read(RUN/'REGRESSION_RESULTS.json')
    independent=read(RUN/'INDEPENDENT_PR223_SAVED_EVIDENCE_AUDIT.json')
    compression=read(OUT/'MESS_BEAM_COMPRESSION_FOLLOWUP.json')
    global_lb=read(OUT/'MESS_GLOBAL_LB_RESEARCH_STATUS.json')
    oracle=read(OUT/'MESS_S1_INTEGER_ORACLE_CONTINUATION_01.json')
    gate=dict(schema='AIDC_MAY01_RECOVERY_CANARY_GATE_V1',status='NOT_CERTIFIED',
        approved_initialization_reused=initial['status']=='PASS',
        all_original_A1_and_A2_UIDs_explained=all(s['all_UIDs_explained'] for s in prefix['stages'].values()),
        initial_source_semantic_and_file_SHA_distinct=True,
        original_Known_command_and_initial_state_preserved=True,
        verified_issue_running_continuation_UIDs=103,
        original_optimized_pending_prefix_certified=False,
        Gate_A='NOT_CERTIFIED',Gate_B='FIXTURE_PASS_REAL_NOT_RUN',
        Gate_C='ORIGINAL_PHYSICAL_REPLAY_PASS_RESEARCH_PARTIAL',Gate_D='NOT_CERTIFIED',
        first_legal_event='NOT_RUN',short_prefix='NOT_RUN',May01_16_slots='NOT_RUN',
        May01_Full96='NOT_RUN',same_current_trace_Fresh_11SVR='NOT_RUN',
        C0_C1_C2_comparison='NOT_RUN_REAL_SOURCE_BOUNDARY_BLOCKED',
        actual_runs=0,actual_global_MILP_calls=0,new_A1_native_calls=0,
        actual_measurements=dict(Unknown_changed_UIDs=None,Unknown_changed_GPUh=None,
            Known_corrective_preplacement_UIDs=None,actual_GPU_occupancy=None,
            runtime_overrun_short=None,queue_carry=None,QoS_risk_violations=None,
            max_line_loading=None,voltage_current_transformer=None,controller_runtime=None),
        real_event_CSV_rows=0,corrective_event_CSV_rows=0,
        original_historical_Full96_status=independent['historical_Full96_Actual_Fresh_status'],
        historical_and_fixture_PASS_transferred=False,source_binding=record(OUT/'ORIGINAL_SAME_CASE_A1_ACTUAL_BINDING.json'),
        no_retiming=True,no_FCFS_Known_replacement=True,no_running_forced_completion=True,
        no_job_deletion=True,no_new_Known_schedule_optimization=True,
        additional_60min_delay_and_checkpoint='NOT_ENABLED_BEFORE_REAL_BASIC_ALLOCATION_GATE')
    write(OUT/'AIDC_MAY01_CANARY_GATE.json',gate)
    decision=dict(status='REVIEWABLE_PROPOSAL_NOT_EXECUTED',
        current_original_case_optimized_prefix='NOT_CERTIFIED',
        approved_initial_state=record(Path(initial['initial_file_record']['path'])),
        initial_semantic_sha=initial['semantic_sha'],original_plans_read_only=binding['original_A_stage_records'],
        preserve_original_case_physical_evidence=True,
        legal_current_adapter='Source-verified already-running continuation plus exact frozen boundary; reject missing past Pending execution.',
        A1_past_Pending_original_window_summary=prefix['stages']['A1']['past_pending_QoS'],
        A2_past_Pending_original_window_summary=prefix['stages']['A2']['past_pending_QoS'],
        new_science_case_required_if_changing_planning_or_boundary_disposition=True,
        proposal='Keep all approved Dday sites, states, GPU gangs, elapsed episodes and completed exclusions fixed. Define a separate Dday planning/overdue-command disposition Case with explicit original QoS and corrective authority. Preserve the old A1/A2 commands as historical intentions. Resolve expired original start domains explicitly before any new Known solve; do not reset protection or SLA assumptions.',
        user_authorization_needed_for_new_Known_schedule_solve=True,new_Known_solve='NOT_RUN',
        prefix_fabricated=False,initial_state_reassigned=False,remaining_native_seconds=history['Native_remaining_seconds'])
    write(RUN/'BOUNDARY_CASE_DECISION.json',decision)
    required={
        'APPROVED_DDAY_INITIALIZATION_REUSED':('PASS',record(OUT/'PR223_DDAY_INITIALIZATION_REUSE_AUDIT.json')),
        'PR223_ORIGINAL_ARTIFACT_SHA_VALID':('PASS',record(RUN/'INDEPENDENT_PR223_SAVED_EVIDENCE_AUDIT.json')),
        'PLANNING_ISSUE_DDAY_CAUSAL_PREFIX':('PARTIAL_103_RUNNING_FULL_PENDING_NOT_CERTIFIED',record(OUT/'PLANNING_ISSUE_TO_DDAY_PREFIX_RECONCILIATION.json')),
        'RUNNING_253_MISMATCH_EXPLAINED':('PASS_ROOT_CAUSE_ONLY',record(OUT/'KNOWN_UID_EPISODE_BOUNDARY_COMPARISON.csv')),
        'PENDING_886_MISMATCH_EXPLAINED':('PASS_ROOT_CAUSE_ONLY',record(OUT/'KNOWN_UID_EPISODE_BOUNDARY_COMPARISON.csv')),
        'NO_ARBITRARY_RETIMING':('PASS_NATIVE0_AND_IMMUTABLE_SOURCE',record(RUN/'REGRESSION_RESULTS.json')),
        'NO_FCFS_AS_OPTIMIZED_KNOWN':('PASS_CURRENT_GATE_LEGACY_FALLBACK_DISCLOSED',record(OUT/'ORIGINAL_SAME_CASE_A1_ACTUAL_BINDING.json')),
        'NO_FUTURE_JOB_INFORMATION_LEAK':('PASS_CONTINUATION_SOURCE_SCOPE',record(OUT/'PLANNING_ISSUE_TO_DDAY_PREFIX_RECONCILIATION.json')),
        'SAME_CASE_PLANNING_ACTUAL_BINDING':('NOT_CERTIFIED',record(OUT/'ORIGINAL_SAME_CASE_A1_ACTUAL_BINDING.json')),
        'SOURCE_SEMANTIC_AND_FILE_SHA_DISTINCT':('PASS',record(RUN/'REGRESSION_RESULTS.json')),
    }
    for name in ('KNOWN_CC4_CAPACITY_HANDOFF','FORECAST_ACTUAL_ONCE_ONLY_DEBIT','NO_DOUBLE_GPU_OCCUPANCY',
            'UNKNOWN_SIGNED_SENSITIVITY_ALLOCATION','NO_FUTURE_KNOWN_SPECULATIVE_VETO',
            'REAL_PENDING_KNOWN_COLLISION_TRIGGER','CORRECTIVE_PREPLACEMENT_PHYSICAL_AUTHORITY',
            'ORIGINAL_KNOWN_COMMAND_IMMUTABLE','RUNTIME_OVERRUN_RUNNING_PROTECTED','RUNTIME_SHORT_SAFE_BACKFILL'):
        required[name]=('PASS_NATIVE0_FIXTURE_REAL_MAY_NOT_RUN',record(RUN/'REGRESSION_RESULTS.json'))
    required['ORIGINAL_11SVR_AUTHORITY_PRESERVED']=('PASS_ORIGINAL_SAVED_CASE_ONLY',record(RUN/'INDEPENDENT_PR223_SAVED_EVIDENCE_AUDIT.json'))
    for name in ('ORIGINAL_BEAM_JOINT_UNCHANGED','SAME_POOL_INTEGER_LP_EQUIVALENCE','COMPRESSION_TOTAL_WALL_MEASURED',
            'BEST_FULL_MOVING_INCUMBENT_PRESERVED','RESTRICTED_BOUND_NOT_GLOBAL_LB','ORIGINAL_ROUTE_SOC_PQ_REPLAY',
            'NO_NEW_UNRESTRICTED_FULL_MILP'):
        required[name]=('PASS_STATED_ORIGINAL_OR_REDUCED_SCOPE',record(OUT/'MESS_GLOBAL_LB_RESEARCH_STATUS.json')
            if name in ('RESTRICTED_BOUND_NOT_GLOBAL_LB','ORIGINAL_ROUTE_SOC_PQ_REPLAY','NO_NEW_UNRESTRICTED_FULL_MILP')
            else record(OUT/'MESS_BEAM_COMPRESSION_FOLLOWUP.json'))
    write(RUN/'REQUIRED_VALIDATION_EVIDENCE.json',dict(requirements={k:dict(status=v[0],evidence=v[1]) for k,v in required.items()},
        Native0_regression=regression,fixture_PASS_is_May01_certification=False))
    pending=prefix['stages']['A1']['past_pending_QoS']
    text=f'''# May01 경계 복구 및 AIDC–MESS 후속 검증

승인된 PR223 초기화와 저장 실행 증거를 복구했고, 253/886의 UID·Episode별 원인을 분해했다. 실제 Pending 최적 명령 Prefix는 복원되지 않아 Gate A/D는 NOT_CERTIFIED다. 새 May01 첫 이벤트·16슬롯·Full96·Fresh AC는 실행하지 않았다.

## PR223에서 이미 완료한 범위

324 Running /472GPU /1300 Pending, 기존151건/296GPU + PR129 20건/20GPU + PR125 153건/156GPU를 원래 loader와 원본 SHA로 검증했다. 제외44건은 재활성화하지 않았고 전체 완료 이력178건을 보존했다. 초기 사이트는 승인 모델 가정이며 Kestrel 사이트 관측값으로 바꾸지 않았다.

원본 A1→M1→A2→M2 FULL feasibility와 Full96 Actual/Fresh 영수증은 원본 V5 평가 Case에서 유효하다. 활성2320·완료1690·Carry630, GPU 위반0·Drop0, 설치11SVR·기존7 RegControl 보존을 독립 Byte/Source 검증했다. 현재 코드가 원본 실행 코드와 다르므로 현 코드로 재생한 결과라는 주장은 하지 않는다. 최종 Known 계획은 A2다.

검증된 Semantic SHA는 `5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573`, 초기 파일 Byte SHA는 `d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003`다. 사용자 붙여넣기 Semantic 값은 원본과 달라 별도 입력 불일치로 기록했다. Stage/Planning/Evaluation Case 식별자 차이는 승인 변환 계보로 검증했다.

## 경계 원인과 진단 오류 수정

| A1 분류 | UID | 해석 |
|---|---:|---|
| Issue Running 연속 실행 | 103 | 133GPU, 과거 Start와 elapsed/site/Episode 일치. start=0은 잔여 서비스 좌표다. 관측 과거6h는798GPUh다. |
| Issue Pending → Dday Running | 150 | 관측 시작이 계획보다108건 먼저·42건 늦다. 사이트40건 일치·110건 차이. 기존 초기 배치를 유지한다. |
| 과거 계획인데 Dday Pending | 886 | 명목 구간714건 종료·172건 활성. 실제 실행 Prefix 증거가 없다. |
| Q50 명령 밖 Known Running | 48 | 163GPU를 실제 완료까지 유지한다. 명목 만료로 완료시키지 않는다. |
| 명령 영역의 관측 과거 완료 | 1 | Issue Running 이후 관측 완료 이력이며 새로운 START로 해석하지 않는다. literal 시작 인증은 별도다. |

원본 Producer는 Issue-relative 슬롯을 사용하고 Dday는 native24, 전력망·MESS 96슬롯은 native[24,120]이다. 00:00으로 원점을 옮기는 해석은 원본 계약이 아니다. 원본 Actual은 과거 Pending 명령을 `PRE_DDAY_START_COMMAND_NOT_REPLAYED`로 Reference Queue에 넘겼다. 이는 원본 물리 PASS의 실행 규칙이며 최적 명령 Prefix 실행 인증이 아니다.

886건 중 원래 허용 시작이 Dday 이후에도 있는 Job은 {pending['allowed_start_at_or_after_Dday_UIDs']}건, 모두 과거인 Job은 {pending['no_original_allowed_start_at_or_after_Dday_UIDs']}건이다. 추가 시작 예산은 모두0/PROTECTION_UNCONFIRMED이며 자동 Retiming 권한을 부여하지 않았다. A2에는 과거 Pending888건과 사이트 차이112건이 있어 A1 숫자를 최종 Actual 결과로 이전하지 않았다.

## 실제 구현 수정

Semantic SHA와 파일 SHA를 같다고 요구하던 인계 오류를 수정했다. 승인 초기화 loader를 통한 정규화와 원본 Source 재검증을 추가했다. 103개 이미 Running인 Job은 Source/Case/명령 SHA와 과거 elapsed를 재검증하는 typed continuation으로 연결한다. 남은 Pending 명령은 보존하고 gate를 통과시키지 않는다.

실제 JobRequest의 UID·Episode·site·start·elapsed·GPU·submit·Q50·compatible 계약을 검사하고 중복/재등록을 거부한다. 독립 리뷰에서 발견한 Q50/submit 검증 누락과 실제 `compatible` 필드 연결도 수정했다. 이 검증은 Native0 입력 연결이며 새 Actual 실행이 아니다.

## AIDC 검증 범위

저장 A1/A2의 Known + Unknown Q50 + Achieved CC4/Runtime Reserve 용량 관계와 CC4 CDF/서비스/Carry를 재검산했다. 둘 다 Achieved Reserve는0이며 Target Reserve나 Shortfall을 물리 점유로 바꾸지 않았다. Unknown 한번 차감·현재 GPU·signed 전체 선로 minimax·실제 Pending 충돌·WAN/QoS 권한·Running 보호·안전 Backfill은 기존 및 신규 Native0 회귀에서 검증했다. 실제 May01 정책 효과, Changed UID/GPUh, 교정 이벤트 및 Fresh 성능은 NOT_RUN이다. 두 실제 이벤트 CSV는 헤더만 포함하며 행0이다.

## MESS 후속 연구

공식 Adaptive Beam→4-MESS Joint MILP→Original FULL→Incumbent Registry를 유지했다. 원래 압축 총 고정 Pool 비용25.705→36.177초의 불리한 결과를 보존하고 기본 비활성화했다. 같은 Source/Case/Pool의 외부 SHA로 봉인한 완전 증명 패킷 재사용은 {compression['complete_cache_reuse_wall_seconds']:.6f}초였다. 이는 캐시 단계 측정이며 새 Native/전체 Beam 속도 개선 인증이 아니다. 새 다양한 Beam 실행과 UB 개선은 NOT_RUN이다.

원본 S1 전체 경로 Integer Oracle을40초 cap으로 한 번 실행해 실제 Native {oracle['Native_Runtime']:.6f}초를 공유 원장에 추가했다. 시간 제한으로 UB {oracle['ObjVal']:.15f}, Bound {oracle['same_S1_full_domain_ObjBound']:.15f}, Gap {oracle['MIPGap']*100:.6f}%이며 Integer 최적값은 NOT_CERTIFIED다. 원본 물리/행렬 replay와 literal Integer를 검증했고 새로운4대·24노드 Bound로 쓰지 않았다. 새 SOC/경로 Hull384개는 실제 Root 위반0으로 추가 Solver 실험을 하지 않았다. 기존 Mode Hull384 실험도 반복하지 않았다. 후속 DW 연구의 완전 Pricing 인증 전에는 Restricted Master를 Global LB로 인정하지 않는다.

원래4대·24노드의 UB0.5398310226338695 / K48 LB0.46498486997548166 / Gap13.864737209%는 원래 Case의 역사 인증값으로 보존했다.

## 현재 Gate와 다음 필요한 결정

Gate A: 승인 초기화·UID 원인·103 연속성은 확인됐지만 최적 Pending Prefix 연결은 NOT_CERTIFIED. Gate B: Native0 Fixture PASS / 실제 May01 NOT_RUN. Gate C: 원본 물리/동등성 검증 PASS, 새 Beam 성능 및 Global 최적성은 미인증. Gate D: NOT_CERTIFIED.

`RECOVERY_01/BOUNDARY_CASE_DECISION.json`에 승인 초기 상태를 고정한 별도 Dday Planning/과거 명령 처리 Case의 구체적인 범위를 남겼다. 만료된 허용 시작과 교정 권한을 먼저 명시해야 하며 새 Known 최적화는 실행하지 않았다. 없던 Prefix 생성, FCFS 최적 계획 치환, 초기 재배치, 완료 강제, Job 삭제로 숫자를0으로 만들지 않았다.

## 회귀·예산·보존

기존522개를 정확히 보존한 최종 Native0 회귀: {regression['passed']} PASS / 실패{len(regression['failed'])} / Skip{len(regression['skipped'])}, 금지 Solver 시도{len(regression['blocked_native_attempts'])}. 추가 {regression['added_tests']}개 검증을 포함한다.

Native {history['Native_before_seconds']:.6f}→{history['Native_used_seconds']:.6f}/360초, 잔여{history['Native_remaining_seconds']:.6f}초. 과거 Call prefix와 부모 원장을 보존했고 inflight는 없다. 기존 FOLLOWUP {history['prior_reports_verified']}개 파일 Byte SHA를 그대로 보존했다. 새 Native snapshot은 RECOVERY_01에 저장했다. Worker1/Threads1, May31·IEEE8500·Scheduler HOLD를 유지한다.
'''
    require_new_report(OUT/'FINAL_RECOVERY_AND_CONTINUATION_KO.md').write_text(text,encoding='utf8')
    return gate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc4-only',action='store_true')
    parser.add_argument('--final',action='store_true')
    args=parser.parse_args()
    result=cc4_report();empty_real_ledgers()
    if not args.cc4_only:
        history=verify_history()
        if args.final:
            print(json.dumps(final_reports(history),indent=2))
        else:
            print(json.dumps(history,indent=2))
    else:
        print(json.dumps(dict(status=result['status'],stages=list(result['stages']),Actual_May01_runs=0)))


if __name__=='__main__':
    main()
