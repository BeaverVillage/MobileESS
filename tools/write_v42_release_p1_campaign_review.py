"""Append compact P1/campaign evidence; no model, solve, or campaign launch."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record,_write
from v42_integration.release_p1_acceptance import saved_a1,read
from v42_integration.release_production_campaign import production_sources,preflight,GATE_CONTRACT

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014'
PROD=BASE/'RELEASE_RECOVERY_20261015/RC02/PRODUCTION'
OUT=PROD/'FINAL_NATIVE0_AND_CAMPAIGN'


def run():
    if OUT.exists():raise FileExistsError('FINAL_REVIEW_EXISTS_USE_NEW_APPEND_DIRECTORY')
    saved=saved_a1();native=read(PROD/'NATIVE0_PRODUCTION_WINDOW_RESULT.json')
    m=native['model_builds']['M1'];a=native['model_builds']['A1']
    if (native['status']!='PASS_A1_LITERAL_REPLAY_AND_CURRENT_M1_FACTORY_ONLY'
            or native['Native_calls']!=0 or native['P2_calls']!=0
            or native['canonical_before']!=native['canonical_after']
            or file_record(native['canonical_before']['path'])!=native['canonical_before']
            or native['P1_only_handoff']!=saved['acceptance']):
        raise ValueError('ORIGINAL_NATIVE0_OR_SAVED_SOURCE_EVIDENCE_DRIFT')
    # Hash only the small proof receipts here. The 2.13GB runtime packet was
    # hashed when produced and must be authenticated again before restoration.
    packet=m['runtime_packet'];p=Path(packet['path'])
    if not p.is_file() or p.stat().st_size!=packet['bytes']:
        raise ValueError('CURRENT_M1_RUNTIME_PACKET_UNAVAILABLE')
    tests=PROD/'P1_AND_CAMPAIGN_PLANNING_ONLY_TESTS.xml'
    suites=ET.parse(tests).getroot().findall('testsuite')
    test_counts={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    if test_counts['tests']!=49 or any(test_counts[k] for k in ('failures','errors','skipped')):
        raise ValueError('FINAL_P1_AND_CAMPAIGN_TEST_EVIDENCE_NOT_PASS')
    OUT.mkdir(parents=True)
    authority=dict(day='2025-05-01',source_sha=saved['manifest']['source_sha'],
        source_identity=saved['manifest']['identity'])
    proposal=dict(schema='RELEASE_PRODUCTION_P1_SEPARATE_AUTHORIZATION_V1',approved=False,
        scope='NEW_RELEASE_P1_ONLY_HEAVY',authorization_id=None,
        authorized_ledger_path=str(BASE/'RELEASE_RECOVERY_20261015/RC02/BUDGET/NEW_MAY01_APPROVED_ONLY_LEDGER.json'),
        human_approval_reference=None,policy_sha=None,Worker=1,Threads=1,P2_calls=0,
        stage_cap_scope='PER_DATE_STAGE',stage_caps_seconds=dict(M1=180.,A2=120.,M2=180.,K48_M2=180.),
        limit_seconds=750.,return_reserve_seconds=30.,overshoot_allowance_seconds=60.,
        authorized_date_cases=[authority],allowed_stage_bindings=[],
        proposal_is_approval=False,positive_caps_are_not_approval=True,
        M1_current_Global_LB=None,M1_K48_optional_extra_seconds=180.,
        M1_K48_optional_separate_total_seconds=930.,
        measured_current_new_stage_solve_costs_available=False,
        caps_are_proposed_limits_not_certified_runtime_predictions=True,
        RC01_unused_seconds_are_not_downstream_authority=True)
    _write(OUT/'UNAPPROVED_MAY01_NATIVE_BUDGET_PROPOSAL.json',proposal)
    planning_proposal=deepcopy(proposal)
    planning_proposal['stage_caps_seconds'].pop('K48_M2')
    planning_proposal.update(limit_seconds=570.,execution_scope='PLANNING_P1_ONLY',
        K48_Actual_Fresh_calls=0,settled_16_slot_gate_required_for_planning=False)
    _write(OUT/'UNAPPROVED_MAY01_PLANNING_ONLY_BUDGET_PROPOSAL.json',planning_proposal)
    plan=dict(schema='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1',Worker=1,Threads=1,P2_calls=0,
        dates=['2025-05-01'],automatic_start=False,policy_sha=None,
        source_snapshot=production_sources(),prepared_M1_packet=packet,
        compiled_case_root=str(BASE/'RELEASE_RECOVERY_20261015/RC02/DATE_CASES/COMPILE01'))
    _write(OUT/'UNAPPROVED_REAL_CAMPAIGN_PLAN.json',plan)
    readiness=preflight(plan,proposal,{})
    _write(OUT/'CURRENT_PRODUCTION_READINESS.json',dict(readiness,
        source_snapshot_is_final_root_campaign_freeze=False,
        supplied_settled_canary_gate=False,May01_Full96_Actual_Fresh='NOT_RUN',
        all31_campaign='NOT_RUN',all31_input_compilation_is_actual_execution=False,
        Native_budget_not_approved=True))
    _write(OUT/'CURRENT_PLANNING_ONLY_READINESS.json',dict(preflight(plan,planning_proposal,{},planning_only=True),
        M1_A2_M2='NOT_RUN_NEW_NATIVE_AUTHORIZATION_REQUIRED',Actual_Fresh_K48_dispatch=False))
    owned=['v42_integration/release_p1_acceptance.py','v42_integration/release_p1_production.py',
        'v42_integration/release_production_campaign.py','tools/run_v42_production_campaign.py',
        'tools/audit_v42_release_p1_production.py','tools/write_v42_release_p1_production_review.py',
        'tools/write_v42_release_p1_campaign_review.py','tests/test_v42_release_p1_acceptance.py',
        'tests/test_v42_release_production_campaign.py']
    executed=read(saved['immutable_records'][2]['path'])
    _write(OUT/'SOURCE_AND_IMMUTABLE_PRESERVATION.json',dict(status='PASS_CURRENT_BYTES',
        M_owned_additive_sources=[file_record(ROOT/name) for name in owned],
        production_dependency_snapshot=production_sources(),
        successful_original_A1_source_and_Source13=executed,
        successful_original_A1_files=saved['immutable_records'],
        canonical_ledger=native['canonical_after'],Source13_modified=False,
        original_MESS_Beam_Joint_FULL_K48_core_modified=False,
        A1_repeated=False,P2_calls=0,Native_calls_this_review=0,
        native0_tool=file_record(PROD/'NATIVE0_PRODUCTION_WINDOW_RESULT.json'),
        final_root_cross_agent_source_freeze='PENDING_ROOT_FINAL_SNAPSHOT'))
    measured=dict(A1_literal_replay_seconds=a['wall_seconds'],
        M1_original_factory_preparation_seconds=m['wall_seconds'],
        total_native0_window_seconds=native['wall_seconds'],
        nested_times_must_not_be_added_to_total=True,
        peak=native['peak'],admission_peak_GiB_estimate=8.,
        actual_peak_exceeded_initial_estimate=native['peak']['RSS_bytes']>8*2**30,
        no_simultaneous_Native_solver=True,models_disposed_and_default_environment_freed=True)
    _write(OUT/'FINAL_M_NATIVE0_STATUS.json',dict(status='PASS_PREPARATION_AND_CONTRACTS_ONLY',
        acceptance=saved['acceptance'],current_M1_case=m,measured=measured,
        literal_A1=a,tests=dict(test_counts,report=file_record(tests)),
        protected_CORE_preserved=True,official_MESS_UB='Adaptive Beam -> 4-MESS Joint -> Original FULL -> Incumbent Registry',
        official_Global_LB_algorithm='K48',K48_current_case_Global_LB=None,
        restricted_joint_ObjBound_is_Global_LB=False,
        M1_A2_M2_current_native_execution='NOT_RUN_NOT_AUTHORIZED',
        current_K48='NOT_CERTIFIED_CURRENT_DOMAIN_PROJECTION_INCLUSION_PACKET_REQUIRED',
        original_full_unpriced_migration_global_optimality=False,
        Native_calls=0,P2_calls=0,Gate_contract=GATE_CONTRACT,
        ASOF_substep_fail_used_as_global_blocker=False,
        current_D0_settled_16_canary='NOT_SUPPLIED_TO_THIS_REVIEW',
        Actual96_Fresh96='NOT_RUN',full31_campaign='NOT_RUN',
        runtime_packet_is_source_authority=False,packet_hash_recheck_before_resume_required=True))
    text=(
        '성공 A1 P1 해를 원본 844129행에 그대로 대입하여 전체 잔차 3.819e-12와 원본 export 동등성을 확인했다. '
        'P2 출력 없이 별도 FULL 수용 계약으로 M1에 전달한다. Native Gap0는 현재 승인된 기본 A행렬 범위이며 미가격 Migration 전체 도메인의 전역 인증이 아니다.\n\n'
        f'현재 M1 원본 factory는 Native0으로 1회 완료했다. 준비 {m["wall_seconds"]:.3f}초, 전체 창 {native["wall_seconds"]:.3f}초이며 앞의 시간은 전체에 포함된다. '
        '원본 행렬 1130336×344967, 16432980 nnz와 선택 행렬 715419×354280의 Source/Case/Domain 및 P1 transport bit-exact 증거를 보존했다. '
        '캐시 packet은 재검증 가능한 실행 준비물이며 Source 권한이 아니다. 다시 모델을 만들지 않고 bytes/원본 proof를 확인해 복원한다. '
        '관측 peak RSS는 약 9.61GiB로 초기 8GiB 추정을 넘었고, 모델 및 default environment 해제를 확인했다.\n\n'
        'M1/A2/M2/K48 최적화는 승인되지 않아 실행하지 않았다. 공식 Beam→4Joint→Original FULL→Registry와 K48 코어를 바꾸지 않았다. '
        'K48 현재 Case 포함성/축/원본 row packet이 없으므로 현재 전역 LB는 null이다. 역사 UB/LB와 제한된 Joint Bound를 옮기지 않는다. '
        'May01 후속 제안 cap 합계660초+반환30초+overshoot60초=750초는 미승인 상한안이며 실측 실행시간 예측이 아니다. '
        '계획 단계만은 M1/A2/M2 cap480초+반환30초+overshoot60초=570초 미승인 별도안이다.\n\n'
        '생산 runner는 실제 OriginalP1Stages와 날짜 compiler를 직접 호출하고 Dummy 또는 주입 executor를 거부한다. 날짜 실패 시 나머지 단계를 NOT_RUN으로 기록하고 다음 날짜로 진행한다. '
        'Source/Case/parent result/원시점 SHA 및 durable Native in-flight 기록 확인 없이 재실행하지 않는다. 49개 작은 검증을 통과했지만 실제 A2/M2/Actual96/Fresh 실행 인증은 아니다.\n\n'
        '최신 Gate는 15분×96의 settle_slot→measure_full_network 정착 측정이다. ASOF substep 진단 실패는 보존하지만 Global Gate 차단 근거로 쓰지 않는다. '
        '현재 D0 SourceCase의 정착 16슬롯 Canary는 May01 Full96 Actual의 선행 조건이다. 별도 --planning-only는 이 Canary가 필요로 하는 M2를 만들기 위해 A1/M1/A2/M2까지만 실행하므로 Canary·Actual·Fresh·현재 K48 포함성을 선행 조건으로 요구하지 않는다. '
        '이 경로도 새 예산 승인과 매 단계 Original FULL 수용을 요구하며 실제 최적화는 실행하지 않았다. May01 Full96를 자기 실행의 선행 조건으로 요구하지 않는다. '
        '31일 launch에는 현재 D0 May01 Full96/Fresh PASS가 별도로 필요하다. 과거 PR223 PASS를 전이하지 않는다.\n')
    (OUT/'FINAL_M_P1_CAMPAIGN_REVIEW_KO.md').write_text(text,encoding='utf-8')
    print(json.dumps(dict(status='APPENDED_NATIVE0_AND_UNAPPROVED_CAMPAIGN_EVIDENCE',
        Native_calls=0,P2_calls=0,tests=test_counts,folder=str(OUT)),indent=2))


if __name__=='__main__':run()
