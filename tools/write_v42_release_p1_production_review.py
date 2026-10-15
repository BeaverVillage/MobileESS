"""Write compact current P1-only evidence without models or native calls."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.release_p1_acceptance import saved_a1
from v42_integration.release_p1_production import production_wiring,current_k48_gate
from v42_integration.m_engine import _write,file_record

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/PRODUCTION'


def blob(relative):
    import hashlib
    raw=subprocess.check_output(['git','show','490ff3ef7:'+relative],cwd=ROOT)
    return json.loads(raw),dict(git_ref='490ff3ef7821705fc82c3823242d79093eb480b9',
        path=relative,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def run():
    if (OUT/'P1_ONLY_STAGE_ACCEPTANCE.json').exists():raise FileExistsError('P1_REVIEW_EXISTS_USE_NEW_ATTEMPT')
    OUT.mkdir(parents=True,exist_ok=True);saved=saved_a1()
    prefix='docs/v42_may12_p1_exact_rescue_20261008/'
    decision,drec=blob(prefix+'FINAL_DECISION.json')
    downstream,crec=blob(prefix+'DOWNSTREAM_COMPATIBILITY.json')
    pricing,prec=blob(prefix+'COMPLETE_PRICING_CLOSURE.json')
    _write(OUT/'MAY12_P1_ONLY_PRECEDENT_AUDIT.json',dict(status='PASS_HISTORICAL_CONTRACT_DISTINCTION',
        sources=[drec,crec,prec],May12_classification=decision['classification'],
        original_A1_ACCEPTED=decision['A1_ACCEPTED'],separate_P1_only_accepted=decision['P1_only_accepted'],
        P2_executed=decision['P2_executed'],original_contract_requires_explicit_adapter=True,
        compatibility=downstream['downstream_compatibility'],May12_complete_pricing=pricing,
        May12_certificate_transferred_to_D0=False,
        D0_native_gap0_means='COMPLETE_SOURCE_AUTHORIZED_BASIC_CURRENT_A_MATRIX_ONLY',
        D0_unpriced_full_migration_global_optimality=False))
    _write(OUT/'P1_ONLY_STAGE_ACCEPTANCE.json',dict(status='PASS_CURRENT_A1_P1_ONLY_HANDOFF',
        contract=saved['acceptance'],immutable_original_inputs=saved['immutable_records'],
        saved_result_not_modified=True,added_RAM_metadata=['stage','case_sha','P2_calls','D0_input_sha','input_MESS_anchor'],
        P2_output_fabricated=False,M1_native_execution='NOT_RUN_NOT_AUTHORIZED',
        A2_M2_K48='NOT_RUN_NOT_AUTHORIZED',Native_calls_this_review=0))
    wiring=production_wiring();_write(OUT/'ORIGINAL_PRODUCTION_WIRING_STATUS.json',wiring)
    gate=current_k48_gate(stage='K48_M1',stage_case_sha='CURRENT_M1_CASE_REQUIRED',
        source_sha=saved['manifest']['source_sha'],full_matrix_sha=None,full_domain_sha=None)
    gate.update(exact_blockers=[
        'CURRENT_M1_FULL_FEASIBLE_POINT_AND_SOURCE_BOUND_UB_NOT_YET_AVAILABLE_NO_M1_NATIVE_APPROVAL',
        'CURRENT_K16_NORMALIZED_ORIGINAL_ROW_PACKET_NOT_REGENERATED;HISTORICAL_WEIGHTS_RHS_NOT_REUSABLE',
        'CURRENT_K32_AND_K48_VIOLATED_ORIGINAL_ROW_SELECTION_NOT_RUN',
        'CURRENT_FULL_TO_PHYSICAL_JOINT_INCLUSION_PACKET_AND_CURRENT_ALIAS_INDEPENDENT_REPLAY_NOT_RUN',
        'ORIGINAL_ORACLE_VERIFY_HAVE_SOURCE_CASE_DIMENSION_ALIAS_CENSUS_ASSERTIONS_NOT_GENERIC_CONTEXT_API',
        'CURRENT_K48_NATIVE_BUDGET_NOT_APPROVED'],
        available_after_current_M1_factory=['original_A/original_d','selected_A/d','Compact/Presolve inverse mapping',
            'current physical/STAY/MOVE/chargeMode/PQ/SOC domain','current source-specific exact transport certificates'],
        original_hardcoded_examples=dict(oracle_source_case='CASE/SAVED/COEFFICIENTS and coefficient byte SHA',
            oracle_restore_joint_columns=244265,verifier_alias_census=14618,
            verifier_source_matrix_domain='FULL_MATRIX/FULL_DOMAIN/SOURCE18R/PR210',
            verifier_expected_binary_columns=9322,
            pilot_bound_anchors='UB/OLD_LB and parent certificate; never new D0 defaults'),
        minimum_same_algorithm_steps=[
            'Serialize the already built current M1 FULL/C3A arrays and source-specific inverse axes; do not rebuild.',
            'After authorized M1 yields a current Original FULL point, regenerate original critical K16 rows using current coefficients/RHS.',
            'Use the same exact helper elimination and outward transport on the current original box; independently replay physical projection.',
            'Regenerate source-bound K32/K48 separation and inclusion receipts without inheriting an old numerical lower bound.',
            'Run only under separately approved K48_M1/K48_M2 stage budgets with native readback and fresh source hashes.'],
        new_K48_formulation=False,old_K48_core_modified=False,
        current_case_feasibility_or_LB_created=False)
    _write(OUT/'K48_CURRENT_CASE_ADAPTER_FEASIBILITY.json',gate)
    _write(OUT/'PRODUCTION_ADAPTER_SOURCE.json',dict(files=[file_record(ROOT/p) for p in (
        'v42_integration/release_p1_acceptance.py','v42_integration/release_p1_production.py',
        'tools/audit_v42_release_p1_production.py','tools/write_v42_release_p1_production_review.py')],
        Source13_and_successful_RC01_P1_untouched=True,
        Dummy_in_production='IMMEDIATE_ERROR',fixture_only_pipeline_is_production_certificate=False,
        actual_executor='ORIGINAL_FUNCTION_IDENTIFIED;FINAL_SOURCE_BOUND_A2_M2_CURRENT_AC_FACTORY_REQUIRED',
        research_R1_R2_contracts_do_not_change_Planning_MESS_or_K48=True,
        remaining_gate='M1_A2_M2_NATIVE_AUTHORIZATION_AND_FULL_RESULTS;K48_CURRENT_INCLUSION;ACTUAL_FRESH_PHYSICAL_GATES'))
    (OUT/'P1_PRODUCTION_REVIEW_KO.md').write_text(
        '신규 P1-only 수용 계약으로 기존 성공 A1을 P2 출력 없이 M1 입력 형태로 연결했다. '
        '원본 JSON/POINT/Source13/180초 원장은 수정하지 않았다. Native Gap0는 현재 D0 기본 승인 도메인 A행렬의 수치적 폐합이며 '
        '미가격 Migration 전체 도메인 또는 AIDC–MESS 공동 전역 최적성 인증이 아니다.\n\n'
        'May12는 별도의 A1_P1_ONLY_ACCEPTED 계약과 원본 전체 pricing 증거가 있었고 기존 A1_ACCEPTED는 false였다. '
        '그 Bound/Global 인증을 이번 D0에 이전하지 않는다. A2는 원본 builder/exporter를 쓰되 P1 단일 budgeted solve만 실행하는 wrapper이며 '
        '기존 P2 다중 pass 함수를 호출하지 않는다. MESS는 기존 Adaptive Beam→4Joint→Original FULL→Registry 그대로다.\n\n'
        '검증 범위는 실제 A1 literal FULL 재생, 실제 현재 M1 factory Native0, Source 및 인터페이스 검증과 명시적 fixture뿐이다. '
        'A2/M2 실제 실행, K48 현재 Case 포함성 및 Actual96/Fresh를 실행한 것으로 표현하지 않는다. '
        'K48 기존 코드의 Source/Case/축/별칭 census 고정조건 때문에 단순 globals 교체는 인증이 아니다. '
        '현재 원본 행렬/역사상/새 M1 FULL점으로 같은 알고리즘의 원본 row packet·outward projection을 별도 검증해야 한다.\n\n'
        '추가 Native 승인 없이 M1/A2/M2/K48를 실행하지 않는다. RC01 잔여129.378초는 후속 권한이 아니다. '
        '현재 물리 Canary FAIL 및 R1/R2 연구 계약 Gate와도 독립이다. CAMPAIGN_BLOCKED_WITH_EXACT_REASONS를 유지한다.\n',encoding='utf-8')
    print(json.dumps(dict(status='WRITTEN_SCOPED_EVIDENCE',P2_calls=0,Native_calls=0)))


if __name__=='__main__':run()
