**공통 service authority + MIN_RHO_AIDC May-01 B0/B1**

분류: AIDC_OBJECTIVE_IMPLEMENTATION_DEFECT의 수정. 이전 ZERO_FEASIBILITY 결과와 mixed-duration 개발 시도는 새 결과의 과학적 비교 기준으로 사용하지 않는다.

| 지표 | B0 | B1 | Delta = B0 − B1 |
|---|---:|---:|---:|
| Planning | 0.59857673722892069 | 0.5920481995850182 | 0.0065285376439024878 |
| Fresh | 0.59881789822527476 | 0.5921962032844279 | 0.0066216949408468562 |
| Actual | 0.58923579670058079 | 0.58867224652411532 | 0.00056355017646547712 |

Common T_DA SHA: `2f241ec63646ebec23bad86ac69b8b92d7c9daa9f2771b7c80b0eecfafab40f1`. Job 1649; 기존 RW/RSP duration 차이 1395; 새 case별 차이 0.
B0는 RW start/site/inherited state와 common causal-safe duration이다. B1도 동일한 duration/residual 및 B0 terminal obligation을 사용한다. Realized runtime은 Planning에서 읽지 않았다.

| 결정 변화 | 개수 |
|---|---:|
| START_CHANGED_JOB_COUNT | 72 |
| START_ADVANCED_JOB_COUNT | 72 |
| START_DELAYED_JOB_COUNT | 0 |
| SITE_CHANGED_JOB_COUNT | 0 |
| MIGRATION_CHANGED_JOB_COUNT | 0 |

| 인증 단계 | incumbent | bound | OPTIMAL | work |
|---|---:|---:|---|---:|
| PRIMARY_MIN_RHO | 0.59205870578763276 | 0.59204739449075083 | False | 61.502818978 |
| PRIMARY_MIN_RHO_PROOF_WORK_180 | 0.59204739449075083 | 0.59204739449075083 | True | 8.999556181 |
| SECONDARY_RW_OCCUPANCY_DEVIATION | 992 | 992 | True | 33.964692617 |
| TERTIARY_STABLE_TIE | 6189564 | 6189564 | True | 17.769254340 |

Primary tolerance 1e-06; reference-deviation optimum 992 GPU-slots. Secondary는 certified lower bound + tolerance 이내의 primary cap을 유지한다. Objective/feasible set을 바꾸지 않고 인증 계산의 WorkLimit만 추가했다.

MIN_RHO_MAX, MIN_DEVIATION_FROM_B0, COMMON_DURATION_IDENTITY, REFERENCE_CANDIDATE_INCLUDED, B1_PLANNING_NONWORSENING, B1_B3_A0_IDENTITY, B0_B2_AIDC_REFERENCE_IDENTITY 모두 PASS. MESS OFF, ZERO_FEASIBILITY final objective NO.

Actual critical coordinates:

- B0: line.sw2 / A / slot 73 (18:15 fixed AEST), rho=0.58923579670058079; run ID `b03bbb41-ca4c-4c09-a435-c98034016d42`.
- B1: line.sw2 / A / slot 73 (18:15 fixed AEST), rho=0.58867224652411532; run ID `167e12b9-6e15-427e-a644-9f95c6b91330`.

동일한 actual background/PV/weather/mapping/ratings/control state를 검증했고 AIDC 외 input 차이는 0이다. Actual job별 runtime·GPU identity와 서비스 보존 검사가 PASS다.

**FULL_MAY_AUTHORIZED = NO. B2_B3_AUTHORIZED = NO.** MAY01_B0_B1_COMPLETE_PENDING_ACCEPTANCE_BEFORE_B2_B3. 44-case UNASSIGNED spillover blocker는 유지한다.

[전체 JSON](C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v40f_min_rho_aidc_correction/V40F_MAY01_B0_B1_FINAL_REPORT.json) · [job 결정 ledger](C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v40f_min_rho_aidc_correction/final_report/B0_B1_COMMON_SERVICE_DECISION_DELTA.csv) · [Common preflight](C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v40f_min_rho_aidc_correction/V40F_COMMON_SERVICE_PREFLIGHT.json)

검증·provenance: 관련 tests 26 PASS. Planning/Fresh 4,346개와 기존 V40E 증거 212개 diff = 0. B0/B2와 B1/B3 A0 identity는 static authority 검사이며 B2/B3를 실행한 것이 아니다. [최종 실행 source lineage](C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v40f_min_rho_aidc_correction/V40F_FINAL_EXECUTION_SOURCE_LINEAGE.json)에 Planning seal 이후 저장 형식 수정과 Actual 재개 경로를 별도로 기록했다.
