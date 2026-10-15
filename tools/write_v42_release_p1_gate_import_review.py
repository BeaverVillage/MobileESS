"""Append read-only Gate/import audit, preserving prior Native0 evidence."""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.release_p1_acceptance import saved_a1,read
from v42_integration.release_production_campaign import production_sources,preflight

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014'
PROD=BASE/'RELEASE_RECOVERY_20261015/RC02/PRODUCTION'
OUT=PROD/'GATE_IMPORT_V3'


def run():
    if OUT.exists():raise FileExistsError('APPEND_NEW_AUDIT_DIRECTORY_REQUIRED')
    saved=saved_a1();native=read(PROD/'NATIVE0_PRODUCTION_WINDOW_RESULT.json')
    if (file_record(native['audit_tool']['path'])!=native['audit_tool']
            or file_record(native['canonical_before']['path'])!=native['canonical_before']):
        raise ValueError('ORIGINAL_NATIVE0_EXECUTED_TOOL_OR_CANONICAL_LEDGER_CHANGED')
    protected=read(BASE/'RELEASE_RECOVERY_20261015/RC01/MESS/FINAL/FROZEN_SOURCE_BYTE_PROOF.json')
    checked=[]
    for row in protected['before']['files']:
        expected=row['current'];actual=file_record(expected['path'])
        if any(actual[k]!=expected[k] for k in ('path','sha256','bytes')):
            raise ValueError('FROZEN_ORIGINAL_MESS_K48_CORE_BYTES_DRIFT:'+row['relative'])
        checked.append(actual)
    tests=PROD/'P1_GATE_IMPORT_V4_TESTS.xml'
    suites=ET.parse(tests).getroot().findall('testsuite')
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    if counts['tests']<75 or any(counts[k] for k in ('failures','errors','skipped')):
        raise ValueError('GATE_IMPORT_REGRESSION_NOT_PASS')
    OUT.mkdir(parents=True)
    files=['v42_integration/release_p1_acceptance.py','v42_integration/release_p1_production.py',
        'v42_integration/release_production_campaign.py','tests/test_v42_release_production_campaign.py',
        'tools/run_v42_production_campaign.py','tools/write_v42_release_p1_gate_import_review.py']
    _write(OUT/'SOURCE_AND_PROTECTED_BYTES.json',dict(status='PASS_CURRENT_PROTECTED_BYTES',
        M_owned_sources=[file_record(ROOT/p) for p in files],production_dependency_snapshot=production_sources(),
        original_protected_files=checked,original_protected_count=len(checked),
        successful_A1_files=saved['immutable_records'],
        original_Native0_tool_and_model_evidence_unchanged=True,
        Native0_evidence=file_record(PROD/'NATIVE0_PRODUCTION_WINDOW_RESULT.json'),
        canonical_ledger=native['canonical_before'],successful_A1_source13_unchanged=True,
        cross_agent_final_freeze='ROOT_FINAL_SNAPSHOT_REQUIRED_AFTER_ACTUAL_PRIVATE_FACTORY_FREEZE'))
    _write(OUT/'GATE_AND_IMPORT_AUDIT.json',dict(status='PASS_NATIVE0_CONTRACT_AND_NAMED_FIXTURES_ONLY',
        tests=dict(counts,report=file_record(tests)),Native_calls=0,model_builds=0,Actual_runs=0,P2_calls=0,
        original_MESS_UB='Adaptive Beam -> 4-MESS Joint -> Original FULL -> Incumbent Registry',
        original_Global_LB_method='K48',current_Global_LB=None,
        new_formulation_or_scoring_or_physics=False,
        physical_gate_body=dict(current_D0_SourceCase=True,raw_file_hashes=True,
            canonical_Actual_evaluation_case=True,actual_policy_distinct_from_planning_policy=True,
            A2_M2_FULL_ancestors_from_authenticated_planning_checkpoint=True,
            literal_original_settled_receipt_and_slot_arrays_replayed=True,
            actual_specific_source_bytes_rechecked=True,
            canary16_schema='RELEASE_PRODUCTION_SETTLED_CANARY16_V1',
            Full96_schema='RELEASE_PRODUCTION_SETTLED_FULL96_V1',
            ASOF_substep_FAIL_is_global_blocker=False),
        planning_import=dict(complete_A1_M1_A2_M2_required=True,raw_point_and_source_hashes_rechecked=True,
            consumed_native_ledger_and_authorization_claim_pinned=True,unreconciled_inflight_rejected=True,
            native_case_parent_matrix_domain_threads_cost_checked=True,
            imported_stages_Native_calls=0,required_new_caps_exclude_only_verified_stages=True,
            old_used_ledger_added_as_read_only_to_new_budget=True,
            M1_case_released_before_M2_normal_build_and_restoration=True,
            date_finally_releases_context_engine_result_and_case_on_all_exits=True),
        dated_Actual=dict(plan_field='Actual_policy_by_day',gate_field='actual_policy_by_day',
            current_day_policy_selected_on_local_copy=True,May01_launch_policy_preserved=True,
            all_non_May01_dates_require_verified_May01_Full96_launch=True,
            additional_daily_canary16_is_mandatory=False,
            original_each_day_A2_M2_FULL_and_Actual96_Fresh96_still_required=True),
        actual_production_import_executed=False,full96_campaign_executed=False,
        current_M1_A2_M2_optimization='NOT_RUN_NO_NEW_NATIVE_APPROVAL',
        current_K48='NOT_CERTIFIED_CURRENT_CASE_INCLUSION_AND_EXECUTOR_REQUIRED',
        historical_UB_LB_transferred=False))
    _write(OUT/'CURRENT_SEPARATE_BUDGET_FLOW.json',dict(approved=False,Native_calls=0,
        planning=dict(stage_caps_seconds=dict(M1=180,A2=120,M2=180),cap_sum=480,
            reserve=30,overshoot_buffer=60,proposed_separate_limit=570),
        K48_followup=dict(stage_caps_seconds=dict(K48_M2=180),reserve=30,overshoot_buffer=60,
            proposed_separate_limit=270,requires_current_case_inclusion_packet_and_separate_approval=True),
        two_separate_proposed_limits_sum=840,limits_are_not_measured_runtime_predictions=True,
        consumed_planning_ledger_is_read_only_for_followup=True,
        previous_750_single_ledger_proposal='PRESERVED_HISTORY_SUPERSEDED_FOR_SEPARATE_LEDGER_FLOW',
        old_RC01_remaining_seconds_are_not_new_authority=True))
    plan=dict(schema='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1',dates=['2025-05-01'],
        Worker=1,Threads=1,P2_calls=0,automatic_start=False,source_snapshot=production_sources())
    _write(OUT/'NO_APPROVAL_READINESS.json',dict(
        planning=preflight(plan,dict(approved=False),{},planning_only=True),
        production=preflight(plan,dict(approved=False),{}),
        no_new_budget_balance_or_authority_created=True))
    (OUT/'GATE_IMPORT_REVIEW_KO.md').write_text(
        '파일 SHA만 맞는 과거 Fresh PASS에 현재 Source 표지를 붙이는 경로를 닫았다. 현재 D0 계획 체크포인트에서 A1→M1→A2→M2의 FULL 수용, 부모 해시, P/Q/MESS 앵커, 원시점 및 Source bytes를 순서 검증한 뒤 A2/M2 조상을 얻는다. 사용 Native 원장은 별도 파일 SHA·승인 claim·Source/Case/parent·모델 binding·유한 비용·in-flight 해소를 확인한다.\n\n'
        '정착 Gate는 실제 raw Fresh receipt와 16개/96개 slot rows를 다시 읽고 원본 측정 검증기를 적용한다. Actual 전용 Source freeze와 원시 trace도 재검증한다. Planning Case와 Actual evaluation Case는 구분하며 R1/R2/Source-strict, C0/C1, 16/96 범위는 canonical payload의 서로 다른 SHA를 갖는다. Actual 정책과 Native Planning 승인 정책을 혼동하지 않는다. ASOF substep FAIL은 공식 Global Gate를 차단하지 않는다.\n\n'
        'Full production은 검증된 planning checkpoint를 별도 output에 복원해 이미 끝난 4단계 최적화를 반복하지 않는다. 새 예산은 검증된 단계만 cap 요구에서 제외하고 이전 사용 원장을 읽기 전용으로 보호한다. 현재 Case K48 포함성과 executor는 아직 인증되지 않았으므로 Full production은 계속 차단된다. Planning-only는 이를 선행 조건으로 요구하지 않지만 새 Native 승인과 각 단계 Original FULL을 반드시 요구한다.\n\n'
        '현재 구현에 맞는 미승인 제안은 먼저 Planning 570초(단계 cap합480+반환30+overshoot60), 이후 현재 K48 packet 인증 뒤 별도270초(cap180+반환30+overshoot60)다. 두 상한합840초는 실행시간 예측이나 실제 사용량이 아니다. 이전750초 single-ledger 안은 원문 그대로 역사 자료로 보존하고 현재 분리 원장 승인의 근거로 쓰지 않는다.\n\n'
        'A2 FULL 뒤 M1의 큰 케이스를 정상·복원 경로 모두 해제한다. 날짜별 finally에서 context/engine/result/case를 정리하므로 실패나 복원 오류도 다음 날짜로 큰 객체를 누적하지 않는다. 날짜 순서를 바꿔도 다른 날짜 실행에는 May01 Full96 원시 launch 증거가 필요하다. 각 날짜 Actual 정책을 local gate copy에 선택하며 다른 날짜 16슬롯 검증을 새 필수로 발명하지 않는다. 각 날짜 자체 A2/M2 FULL과 Actual96/Fresh96는 별도로 검증해야 한다.\n\n'
        f'새 검증 {counts["tests"]}개가 통과했다. 큰 모델 생성·최적화·Actual·AC는 이번 감사에서 모두 0회다. 원본 103개 보호 파일과 Source13·성공 A1·기존 Native0 실행 도구/결과·원장 bytes가 보존됐다. 실제 생산 import/후속 최적화/Actual96/Fresh96 실행 인증을 주장하지 않는다. 이전 보고와 Source snapshot은 덮어쓰지 않았다. 최종 cross-agent Source freeze는 Root가 Actual/private factory 동결 뒤 작성해야 한다.\n',encoding='utf-8')
    print(json.dumps(dict(status='APPENDED_GATE_IMPORT_AUDIT',tests=counts,Native_calls=0,P2_calls=0,folder=str(OUT)),indent=2))


if __name__=='__main__':run()
