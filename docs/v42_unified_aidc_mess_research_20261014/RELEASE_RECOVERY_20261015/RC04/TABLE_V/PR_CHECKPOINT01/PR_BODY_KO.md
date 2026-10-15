May01 Table V의 Reference/Flexible × MESS OFF/ON 네 비교군을 현재 D0 초기 상태와 원본 P1 실행 경로에 연결했습니다. B1/B3는 Full E1/FLEX30/R1 케이스를 사용하며, 시간 이동·계획 배치·원본 권한이 있는 checkpoint/WAN migration·runtime 제어를 연결합니다. **이 PR 업데이트는 실행 중간 체크포인트입니다. 현재 Actual96와 Fresh96가 모두 통과한 Arm은 B0 하나(1/4)이며, 전체 완료나 ReleaseFreeze 승격을 주장하지 않습니다.**

| Arm | Computing / MESS | 공식 Planning 순서 | 현재 검증 범위 |
|---|---|---|---|
| B0 | Reference / OFF | Reference | Actual96 + Fresh96 FULL_PASS |
| B1 | Full E1/FLEX30/R1 / OFF | A1 P1 | Native status 3 INFEASIBLE, FULL 해 없음, Actual 미실행 |
| B2 | B0와 같은 Reference / ON | M1 P1 + 별도 K48 | B1과 독립 실행 시작, 결과 미정 |
| B3 | Full E1/FLEX30/R1 / ON | A1 P1 → M1 P1 → A2 P1 → M2 P1 + 별도 K48 | 대기 |

B0 완료 결과는 현재 Source/Case의 Actual trace를 원래 15분×96 `settle_slot → measure_full_network`로 다시 검산한 값입니다.

| B0 실측 항목 | 값 |
|---|---:|
| Fresh96 최대 선로·상 부하율 | 0.6855134731403852 pu = **68.5513473140%** |
| 전압 최솟값 / 최댓값 | 0.9797154533 / 1.0461137844 pu |
| 물리 실패 슬롯 | 0/96 |
| 실제 Compute GPUh | 10600.067777777778 |
| 완료 / carryout jobs | 922 / 1398 |
| capacity violation / dropped jobs / Actual global reoptimization | 0 / 0 / 0 |
| Arm 전체 wall | 48.562444700015476초 |

B1 A1의 원본 P1 호출은 Native **776.2689998149872초**, status **3(INFEASIBLE)**로 종료됐습니다. FULL-feasible 해·objective·bound·Gap이 없으므로 Actual96와 Fresh96를 실행하지 않았습니다. 모델 전처리는 93.91443410000647초에 완료됐으며, Arm 전체 wall은 888.2274176999927초입니다. 이는 현재 수치 모델의 solver 반환 상태이며, 원인 분석이나 원래 모든 권한 도메인의 엄밀한 불가능성 인증을 대신하지 않습니다. B2는 이 실패와 독립적으로 실행합니다.

공통 D0 초기 상태는 RUNNING 324 UID·472 GPU, PENDING 1300 UID, Known 1624 UID, 12 AIDC·780 GPU입니다. B0/B2는 같은 Reference 결과를 사용합니다. B0/B1의 MESS는 literal P/Q OFF이며, B2/B3는 IDC와 STA 전체의 원본 MESS P/Q·경로·SOC를 전달하도록 검사합니다. B2의 실행 완료와 B3의 실제 운영 검증은 아직 미확정입니다.

MESS UB 코어는 **Adaptive Beam → 4-MESS Joint MILP → Original FULL → Incumbent registry**, LB는 **현재 Stage Case에 바인딩한 원본 K16 → K32 → K48**을 유지합니다. 제한 후보풀 Joint의 ObjBound를 Global LB로 사용하지 않습니다. FULL-feasible 해의 Actual 물리 평가는 K48 목표 Gap 미달과 분리합니다. 과거 Basic A1의 0.64211779208034, 과거 MESS UB/LB, RC03의 16슬롯 R1 진단 결과는 이번 Full E1/Table V 실적으로 전이하지 않습니다.

최신 사용자 지시에 따라 **총 Native 합산 한도는 없습니다**. 각 Arm·Stage의 누적 Gurobi Native timeout만 A1/A2 각각 5400초, M1/M2 각각 1800초로 적용합니다. K48은 각 M 단계 300초의 별도 승인·원장입니다. Build·HiGHS·Actual·AC wall은 Native timeout과 분리 계측합니다. P2 호출 0, Worker 1, Threads 1, Heavy 직렬 실행을 유지합니다. 과거 원장은 읽기 전용으로 보존합니다.

REGRESSION02는 기존 baseline 682개 ID를 유지한 **778개 테스트 PASS(신규 96개)**입니다. 실패·skip·차단된 실제 Native 시도는 모두 0이며, 회귀 자체의 Native optimize 호출은 0입니다. 기존 두 Native 원장의 before/after SHA와 바이트 동일성도 확인했습니다. 이후 Actual 어댑터의 FULL 증거 검사를 포함한 별도 27개, 모니터 상태 검사 6개도 통과했습니다. 이 검증은 B1/B2/B3의 FULL96 성공을 의미하지 않습니다.

B1 실패 후 원본 E1 도메인 감사에서 PENDING 992 UID의 합법 시작 슬롯 3,667개를 추가로 삭제한 필터를 확인했습니다. 이 커밋은 해당 실패 케이스와 실행 Source를 보존합니다. 원본 receipt 전체 도메인을 복원한 수정은 새 Source/Case에서 다시 검증하며, 이전 Native 776.269초를 같은 Arm·Stage 누적 사용량으로 유지합니다. 도메인 축소가 INFEASIBLE의 유일한 원인이라고 단정하지 않습니다. 병목 실측에서는 단일 코어 97.09%, 가용 메모리 12.48GiB, Commit 45.32%이며 측정 구간 RAM·I/O 포화 증거가 없었습니다.

원본 11 SVR·7 RegControl·AUTO·Delay/history를 유지한 settled Full96가 공식 물리 판정입니다. Substep은 별도 진단이며 공식 판정을 대체하지 않습니다. R2는 HOLD이며, 다른 5월 날짜의 캠페인은 실행하지 않았습니다.

현재 [REPORT01](docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/REPORT01/MAY01_TABLE_V_COMPARISON_KO.md)은 필수 12개 산출물의 중간 스냅샷입니다. [회귀 원본](docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/REGRESSION01/RESULTS.json), [B0 Actual](docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION01/B0/ATTEMPT02/ACTUAL_RESULT.json), [B0 Fresh](docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION01/B0/ATTEMPT02/FRESH_AC_RESULT.json)을 보존합니다. 첫 B0 시도의 입력 검사 오류도 원본 그대로 남기고 ATTEMPT02에 완료 결과를 추가했습니다. 이후 Arm 결과는 검증 후 추가 커밋으로 반영합니다. Draft PR230을 유지합니다.
