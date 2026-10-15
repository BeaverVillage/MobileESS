# May01 Table V PR 중간 체크포인트 검토

2026-10-15 체크포인트. 최초 14:23 KST 작성 이후 B1 A1 종료 결과를 반영했습니다. 이 문서는 완료된 B0 결과, B1 A1의 INFEASIBLE 반환, 독립 실행을 시작한 B2 및 검증된 Source/계약·회귀를 기록합니다. **네 Arm 최종 비교 보고서나 ReleaseFreeze 승인 문서가 아닙니다.**

| Arm | Planning | Actual96 | Fresh96 | 체크포인트 판정 |
|---|---|---|---|---|
| B0 | 공통 causal Reference | FULL_PASS | FULL_PASS | 완료 |
| B1 | Full E1 A1 P1 status 3 INFEASIBLE | NOT_RUN | NOT_RUN | 현재 모델 FULL 해 없음 |
| B2 | M1 P1 독립 실행 시작, K48 별도 | NOT_RUN | NOT_RUN | 실행 결과 미정 |
| B3 | Full E1 A1 → M1 → A2 → M2 P1 대기 | NOT_RUN | NOT_RUN | 미실행 |

현재 Actual96·독립 Fresh96가 함께 통과한 Arm은 **1/4**입니다. 미실행 성능·행동 수·UB/LB·Gap을 0이나 성공으로 채우지 않았습니다. REPORT01과 이전 inflight/Native ASOF 기록은 생성 당시의 역사적 스냅샷으로 그대로 보존합니다. 최신 상태는 Arm 결과와 실행 원장의 완료 호출·현재 inflight가 기준입니다.

## 완료 증거

B0의 [최신 시도 포인터](../EXECUTION01/B0/LATEST_ATTEMPT.json)는 보존된 첫 시도와 ATTEMPT02를 구분합니다. [ATTEMPT02 결과](../EXECUTION01/B0/ATTEMPT02/ARM_OUTCOME.json)는 FULL_PASS, P2 0, R2 HOLD입니다. 최초 시도의 Source 검사 인자 오류는 덮어쓰지 않았고, append 시도에서 Native 예산을 초기화하지 않았습니다.

| B0 원본 항목 | 검산된 값 |
|---|---:|
| Actual / Fresh 슬롯 | 96 / 96 |
| 최대 선로·상 부하율 | 0.6855134731403852 pu (68.55134731403852%) |
| Vmin / Vmax | 0.9797154533228993 / 1.0461137844480979 pu |
| 실패 슬롯 | 없음 |
| Actual Compute / occupation GPUh | 10600.067777777778 / 10600.067777777778 |
| 제출 / 완료 / carryout jobs | 2320 / 922 / 1398 |
| capacity violations / dropped jobs | 0 / 0 |
| 미래 duration / completion controller reads | 0 / 0 |
| optimizer / Actual global reoptimization calls | 0 / 0 |
| 전체 Arm wall | 48.562444700015476초 |

Actual receipt의 `physical_ac_status=NOT_EXECUTED`는 event 실행과 독립 Fresh AC의 분리를 뜻합니다. 이어 실행된 Fresh96는 [원본 receipt/slot rows와 현재 trace](../EXECUTION01/B0/ATTEMPT02/FRESH_AC_RESULT.json)에 바인딩되어 PASS입니다. Planning rho를 Actual 선로부하율로 대체하지 않았습니다.

## 종료된 B1 A1

[PLANNING_NATIVE_LEDGER](../EXECUTION01/PLANNING_NATIVE_LEDGER.json)와 [원본 A1 결과](../EXECUTION01/B1/A1/P1_ONLY_RESULT.json)에 `B1:A1`의 `RELEASE_P1:A1:ORIGINAL_P1` 한 호출이 **status 3(INFEASIBLE)**로 완료됐습니다. timeout 5400초에 도달해 종료한 결과가 아닙니다. FULL-feasible point와 objective·bound·Gap이 없으므로 [Arm 결과](../EXECUTION01/B1/ARM_OUTCOME.json)는 `NOT_CERTIFIED / A_STAGE_HAS_NO_ORIGINAL_FULL_FEASIBLE_POINT`이며 Actual96·Fresh96는 미실행입니다.

| B1 A1 시간·상태 | 원본 값 |
|---|---:|
| Native Runtime | 776.2689998149872초 |
| Optimize 호출 wall | 776.3088372000202초 |
| 모델 전처리 wall | 93.91443410000647초 |
| A1 stage 전체 wall | 874.9679450000112초 |
| Arm 전체 wall | 888.2274176999927초 |
| Native status / FULL 해 | 3(INFEASIBLE) / 없음 |
| Actual96 / Fresh96 | NOT_RUN / NOT_RUN |

위 시간은 서로 다른 범위이며 Arm 전체 wall에 다시 더하지 않습니다. 실행 중 완료 Native Runtime이 0으로 보였던 과거 스냅샷은 호출 반환 전 기록입니다. 지금은 완료 1회·진행 0회이며 모니터는 `A1 / ARM_FAILED / 3 INFEASIBLE`로 구분합니다. Source/모델 원인에 대한 Native0 감사는 별도 진행하며, 이 수치 solver 상태를 원래 모든 권한 도메인의 엄밀한 불가능성 증명으로 확대하지 않습니다. B2 실행은 B1의 FULL 해를 부모로 요구하지 않으므로 독립 진행합니다.

현재 Full E1 모델의 Native readback은 1,699,066행·600,284열·15,446,607 nonzero입니다. Stage Case는 `6a5f4ee46f02d014b2475ea99cd07261da8732721c6b85e803e2785e93cabd57`, matrix SHA는 `a3d85bf6ff39dc3c8ec8bfb668f2e99ca6e2fa5d8088f982d3400184408cb603`, domain SHA는 `c9a8c347a098d2e93ce98cdafb9550a731e110166619b409406ff7f4aec02c1a`입니다. 과거 Basic A1과 동일한 도메인·성공 결과로 취급하지 않습니다.

## 회귀와 보존

[REGRESSION01/RESULTS.json](../REGRESSION01/RESULTS.json)은 baseline commit `6a12d503a`의 **682개 ID 보존 + 신규 90개 = 772개 PASS**를 기록한 보존 스냅샷입니다. 실패·skip·차단된 실제 Native 시도는 빈 목록이며 회귀 Native optimize 호출은 0, wall은 45.05462790001184초입니다. 보존 기준 baseline XML SHA는 `9ff81a044c8e44002a491c5b9602fa08258c15e1cedcce4f7088c7ba4115efae`입니다. 이후의 모니터 진행·종료 표시 수정은 별도 작은 테스트 6개 PASS(0.21초)로 검증했습니다.

| 보존 원장 | before = after SHA-256 |
|---|---|
| 기존 UNIFIED_NATIVE_RUNTIME_LEDGER.json | `96dafdd5a0f261e2446d66de8070d604c588a8cbf8bfd9e4960f5c20730deadc` |
| RC01 A1_P1_120 별도 180초 원장 | `1f26c7f0a0f5e20f93b758cc94d319bb5eb749ad6c55a6ffdf224e3368a555f7` |

작성 중 직접 읽은 현재 파일 SHA도 위 값과 같습니다. 기존 원장의 사용량·잔여량을 새 실행 권한에 합치지 않았습니다. 성공한 Basic A1 원본과 과거 RC03 진단도 보존합니다.

## 실행 정책과 남은 검증

최신 정책은 **합산 총량 제한 없음**입니다. A1/A2 각 Arm·Stage 누적 Gurobi Native 5400초, M1/M2 1800초, K48 각 M 단계 별도 원장 300초입니다. Build·HiGHS·Actual·AC는 별도 wall로 기록하며 Native timeout에서 제외합니다. 전체 wall에 Native·Presolve·Root 등 중첩 시간을 다시 더하지 않습니다. P2 0, Worker 1, Threads 1, Heavy 직렬 실행을 유지합니다.

원본 MESS UB 경로인 Adaptive Beam → 4-MESS Joint MILP → Original FULL → Incumbent registry와 현재 Case의 K48을 연결했습니다. Reference M1은 가짜 A1 FULL metadata 없이 별도 causal Reference 증거를 받습니다. 물리 도메인은 4 MESS·24 노드·96 슬롯, STAY/MOVE, 원본 Pch/Pdis/Q·SOC·PCS·travel·terminal 규칙을 유지합니다. 현재 Source/Case/Anchor와 raw FULL 증거가 일치해야 후속 단계로 갑니다. 제한 후보풀 bound를 Global LB로 쓰지 않으며, FULL-feasible 상태에서 K48 목표 Gap 미달만으로 Actual을 막지 않습니다.

다음 항목은 아직 실행 완료로 인증하지 않습니다.

- B1 A1의 현재 INFEASIBLE 원인 검증과 필요한 후속 조치. 현재 실행에서는 Original FULL 해와 실제 행동 funnel·Actual96·Fresh96를 얻지 못했습니다.
- B2 현재 Reference 기반 M1, 현재 Case K48, all-IDC+STA MESS 주입 및 Actual96·Fresh96.
- B3 A1→M1→A2→M2 전체 부모 연결, 현재 Case K48와 Actual96·Fresh96.
- 네 Arm 간 실제 Compute GPUh·QoS·시간 이동·배치·R1 Pre-site·허용 Running migration의 비교와 해석.
- May01 통합 ReleaseFreeze와 다른 5월 날짜 캠페인. 다른 날짜는 이번에 실행하지 않았습니다.

공식 물리 판정은 원본 11 SVR·7 RegControl·AUTO·Delay/history의 15분×96 settled full-network 측정입니다. Substep은 별도 진단이며 연속시간 안전을 인증하지 않습니다. R2는 HOLD입니다. 과거 RC03의 R1 31건 변경은 **16슬롯 역사적 진단**이며, 이번 Table V나 31일 캠페인 실적이 아닙니다.

현재 [REPORT01](../REPORT01/REPORT_GENERATION_RECEIPT.json)은 필수 12개 파일을 제공하는 중간 스냅샷입니다. 이후 결과를 새 스냅샷과 추가 커밋으로 보존하고 기존 Draft PR230을 계속 업데이트합니다. 이 체크포인트 문서 작성은 solver/model/실행 Source/monitor Source를 수정하거나 Git·PR을 직접 변경하지 않았습니다.
