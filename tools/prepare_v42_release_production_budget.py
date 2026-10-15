"""Write a reviewable P1-only proposal. Never approves or creates a ledger."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest
from v42_integration.release_ac_contract import CONTRACT

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
OUT=BASE/'RC02/BUDGET'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    if OUT.exists():raise FileExistsError('NATIVE_PROPOSAL_MUST_NOT_OVERWRITE')
    OUT.mkdir(parents=True)
    canonical=ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    p1=BASE/'RC01/A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json'
    old,new=read(canonical),read(p1)
    historical=[file_record(p) for p in (canonical,p1)]
    manifest=read(BASE/'RC01/A1_P1_120/CASE/D0_CASE_MANIFEST.json')
    m1=read(BASE/'RC02/PRODUCTION/M1_CURRENT_FACTORY_NATIVE0.json')
    caps=dict(M1=180.,A2=120.,M2=180.,K48_M2=180.)
    policy=dict(P1_only=True,P2_calls=0,official_AC_contract=CONTRACT,
        original_objective='MIN_MAXIMUM_PHASE_LINE_LOADING',original_Source13=manifest['source_freeze'],
        original_M_algorithm='ADAPTIVE_BEAM_4_MESS_JOINT_ORIGINAL_FULL',
        K48='SAME_CURRENT_CASE_INCLUSION_REQUIRED_NO_OLD_LB_TRANSFER',
        full_parent_required=True,Threads=1,Worker=1,dates_independent=True)
    proposal=dict(schema='RELEASE_PRODUCTION_P1_BUDGET_PROPOSAL_NOT_AUTHORIZATION_V1',approved=False,
        automatic_start=False,scope='NEW_RELEASE_P1_ONLY_HEAVY',authorization_id=None,human_approval_reference=None,
        authorized_ledger_path=str(OUT/'FUTURE_APPROVED_MAY01_NATIVE_LEDGER.json'),
        policy_sha=digest(policy),policy=policy,Worker=1,Threads=1,P2_calls=0,
        stage_cap_scope='PER_DATE_STAGE',stage_caps_seconds=caps,
        proposed_solver_seconds=sum(caps.values()),return_reserve_seconds=30.,
        overshoot_buffer_seconds=60.,proposed_total_ceiling_seconds=750.,
        planning_only=dict(stages=['M1','A2','M2'],solver_cap_seconds=480.,
            total_with_reserve_and_buffer_seconds=570.,K48_LB=None,
            settled_actual_or_Fresh_gate_not_required_before_this_planning=True,
            separate_new_approval_required=True),
        authorized_date_cases=[dict(day='2025-05-01',source_sha=manifest['source_sha'],source_identity=manifest['identity'])],
        historical_read_only=historical,old_native_seconds=old['Gurobi_Native_seconds'],
        consumed_A1_native_seconds=new['Gurobi_Native_seconds'],
        historical_combined_native_seconds=old['Gurobi_Native_seconds']+new['Gurobi_Native_seconds'],
        consumed_A1_remainder_is_other_stage_authorization=False,old_ledgers_reset_or_merged=False,
        existing_A1_will_be_reused_not_reoptimized=True,
        current_M1_factory=dict(case_sha=m1['stage_case_sha'],source_sha=m1['source_sha'],
            Native_calls=0,wall_seconds=m1['wall_seconds'],rows=m1['original_rows'],columns=m1['original_columns'],
            duplicate_build_for_identical_case_required=False,runtime_packet=m1['runtime_packet']),
        Native_runtime_for_current_M1_A2_M2_known=False,success_within_caps_guaranteed=False,
        solver_error_timeout_interruption_charged=True,
        K48_M2_execution_requires_current_FULL_and_new_inclusion_proof=True,
        optional_K48_M1=dict(additional_solver_cap_seconds=180.,total_with_reserves_seconds=930.,
            required_for_physical_M1_to_A2_handoff=False),
        campaign=dict(approved=False,automatic_start=False,May01_full96_required_before_launch=True,
            illustrative_caps_per_day=dict(A1=120.,**caps),A1_May01_skipped=True,
            Native_cap_sum_for_all31=30*120+31*sum(caps.values()),
            return_reserve_seconds=30.,illustrative_overshoot_buffer_seconds=31*60.,
            illustrative_ceiling_seconds=30*120+31*sum(caps.values())+30+31*60,
            current_case_build_and_Actual_wall_not_established_for31_days=True,
            illustrative_is_not_budget_approval=True))
    _write(OUT/'MAY01_P1_ONLY_BUDGET_PROPOSAL.json',proposal)
    report='''# 후속 P1-only Native 예산 제안 — 미승인

기존 318.681초와 별도 A1 P1 50.622초 원장은 읽기 전용이다. A1의 180초 중 잔여분은 다른 단계의 승인 예산이 아니다. A1 성공 해를 그대로 재사용한다.

| 단계 | 제안 상한(초) | 포함 범위 |
|---|---:|---|
| M1 | 180 | 원본 Beam–Joint UB 및 해당 단계 보수적 HiGHS 비용 |
| A2 | 120 | 원본 P1 한 목적함수 |
| M2 | 180 | 원본 Beam–Joint UB 및 해당 단계 보수적 HiGHS 비용 |
| K48 M2 | 180 | 현재 최종 M2 Case의 포함성 증명 후 Global LB |
| Solver 합계 | 660 | P2 0회 |
| Return reserve / overshoot buffer | 30 / 60 | 새 예산에 분리 |
| 제안 총 상한 | **750** | 아직 승인되지 않음 |

M1 자체의 Global LB도 별도로 요구하면 K48 M1 180초를 추가하여 총 930초를 제안한다. M1 Original FULL 해를 A2에 전달하는 것과 최종 M2 Case의 Global LB 인증은 구분한다.

Planning만 먼저 승인하는 최소 단위는 M1→A2→M2 480초 + Reserve/Buffer 90초 = **570초**다. K48 M2까지 포함하는 제안은 750초, K48 M1도 포함하면 930초다. 세 가지 모두 미승인이며, Planning-only 경로에서는 K48 LB를 null로 남긴다.

현재 D0 M1 원본 Case 조립·엄밀 변환 검증은 약 1,481초의 Native0 Wall이 들었다. 그 결과를 동일 Source/Case에서 캐시로 보존하므로 중복 조립은 피한다. M2와 다른 날짜는 입력이 달라 이 시간을 그대로 재사용하거나 성공 시간을 보장하지 않는다. Native 상한과 모델 조립·Actual·Fresh 전체 Wall은 별도다.

위 상한은 제한된 첫 실행을 위한 제안이며 현재 Case가 상한 안에 실행 가능해/최적성 목표를 달성한다고 보장하지 않는다. Solver 오류·중단·시간초과도 원장에 청구하며, 해가 없거나 FULL 검증에 실패하면 후속 단계를 실행하지 않는다. 현재 K48 포함성 packet은 아직 미인증이므로 예산 승인이 곧 K48 실행 허가는 아니다.

May01 후속 Planning은 별도 승인 후 먼저 수행할 수 있다. 그 결과로 현재 D0 Case의 16슬롯 Canary, Actual96와 공식 `settle_slot → measure_full_network` Fresh96을 새로 검증한다. ASOF Substep 진단 FAIL만으로 공식 평가를 차단하지 않는다.

31일 총액은 May01 결과와 전체 Wall 계측 후 확정해야 한다. 동일 상한을 단순 확장한 참고치는 Solver 24,060초 + Return 30초 + Overshoot 1,860초 = 25,950초다. 이것은 승인이나 실행 계획 확정이 아니다. 자동 캠페인은 모든 필수 Gate와 별도 캠페인 예산 승인 전 HOLD다.
'''
    (OUT/'BUDGET_PROPOSAL_KO.md').write_text(report,encoding='utf8')
    assert historical==[file_record(p) for p in (canonical,p1)]
    print(json.dumps(dict(status='UNAPPROVED_PROPOSAL_ONLY',total_seconds=750.,new_Native_calls=0,ledgers_unchanged=True)))


if __name__=='__main__':main()
