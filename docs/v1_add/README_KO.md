# V1_add — 독립 Greensboro 확장실험

**실험명/버전: V1_add.** V44 r043 (`affc7226a519adbe072d7debbc3ae25ea71c3487`)은 동결 알고리즘·입력의 기준 출처다. V1_add의 브랜치, worktree, runtime과 결과는 V44 Production 캠페인으로부터 분리한다. V44 Source·Worker·원장·PID·결과는 변경하지 않았다.

- 독립 브랜치: `codex/v1-add-gso-substation2-preflight`
- 독립 코드: [v1_add_preflight](../../v1_add_preflight)
- [우선 Source Lineage 보고서](../smartds_gso_substation2_v44_r043/SOURCE_LINEAGE_REVIEW_KO.md)
- [최종 Preflight 상태](../smartds_gso_substation2_v44_r043/FINAL_PREFLIGHT_REVIEW_KO.md)
- [실험 식별·분리 선언](../smartds_gso_substation2_v44_r043/EXPERIMENT_IDENTITY.json)
- [원본 최종 전기 입력 배열](../smartds_gso_substation2_v44_r043/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz)
- [입력 비교 SHA·최대 오차](../smartds_gso_substation2_v44_r043/INPUT_COMPARISON_ARRAY_DIGESTS.json)
- [원본/새 입력 및 생성 코드 SHA](../smartds_gso_substation2_v44_r043/SOURCE_AND_INPUT_SHA256.json)

현재 상태는 `INPUT_MAPPING_NOT_VERIFIED`, `B0_NOT_BUILT`, `INSUFFICIENT_EVIDENCE`다. 같은 2025 입력의 P/Q 분배 산술 검증과 실제 PV/PCC 물리 검증을 구분한다. 입력 동일성 Gate 통과 전 Greensboro 운영 AC·민감도·Pilot 결과를 인증하지 않는다. A1/M1/A2/M2, K48, Beam 및 Joint MILP는 실행하지 않았다.

자료 디렉터리의 `v44_r043` 표기는 기준 출처를 나타내며, 해당 자료는 이 독립 브랜치에서 생성한 V1_add 감사 산출물이다. 원본 IEEE123 배열은 V1_add의 입력 출처이며 Greensboro의 AC 결과가 아니다.
