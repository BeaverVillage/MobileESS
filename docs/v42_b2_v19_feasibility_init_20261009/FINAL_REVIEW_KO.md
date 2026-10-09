# V42 B2 V19 최종 검토

## 결과

May03·04 모두 원본 전체 모델의 엄격한 정수 게이트와 96슬롯 물리 검증을 통과했습니다. 최종 코드에서는 F1 stationary LP 한 번으로 초기해를 채택했습니다. Seed MILP, LP 하한 인증, Adaptive 최적화는 실행하지 않았습니다.

| 날짜 | 첫 FULL 통과 단계 | Native 초 | 첫 FULL wall 초 | 모델 생성 wall 초 | 초기 UB | 호출 | FULL |
|---|---|---:|---:|---:|---:|---|---|
| May03 V19 | F1_STATIONARY_LP | 4.480 | 172.778 | 164.058 | 0.537800466212 | 1 LP / 0 MILP | PASS |
| May04 V19 | F1_STATIONARY_LP | 6.674 | 198.808 | 185.063 | 0.535346345175 | 1 LP / 0 MILP | PASS |

실행 commit: `b6ff419d81495e670ad59fc018f96daf784d368f`. 실행 source SHA: `8b72fa9aab4b27e3be6c134282505cb510a3d0d256db03d4043086d02c833184`.

독립 벤치마크 root: `initialization_benchmark_v19_03`, attempt: `seed_policy_v19_03`. 각 날짜 Native 0초부터 시작했고 합산 초기화 cap 1,500초를 사전에 고정했습니다. 잔여 초기화 Native는 May03 1,495.520초, May04 1,493.326초입니다. 기존 공식 날짜 예산을 새로 부여하거나 초기화하지 않았습니다.

모델 생성시간은 Solver Runtime과 분리했습니다. wall은 DateBudget 시작부터 첫 FULL 통과 receipt까지입니다. 모델 생성 wall의 차이는 재사용 캐시·시스템 상태의 영향을 포함하므로 초기화 알고리즘만의 인과적 개선으로 주장하지 않습니다.

## 실제 원인과 수정

1. **96번 종단 상태 누락**: V18 `values_for()`는 stay 연결을 0~95번 슬롯까지만 등록했습니다. 원본 C3A의 `node_activity[vehicle,site,96]`는 모두 0으로 고정됐습니다. 네 후보 × 네 차량의 `terminal_location` 행은 유리수로 정확히 `0 = 1`입니다. Native minimal IIS 네 개도 종단 경계의 flow 충돌을 확인했습니다. 마지막 arc의 실제 도착 장소에 종단 상태를 설정하도록 수정했습니다. 원점 복귀 조건을 추가하지 않았습니다.
2. **원본 정수 경로 표현을 충분히 고정하지 않음**: C3A의 일부 원본 FULL 이진 arc는 `route_flow` 연속 변수로 표현됩니다. 옛 함수는 `VType != C`만 고정해서 이 경로 표현을 남겼습니다. May04의 실제 point에서 `arc[MESS01,1181] = 0.9999999999999999`가 발견되어 기존 literal integer 게이트가 올바르게 거부했습니다. 새 F1/고정 후보는 원본 경로 정수 표현까지 LB=UB로 고정한 **새 LP**를 풉니다. 기존 point를 반올림하거나 검증 오차를 바꾸지 않았습니다.
3. **실측 기록의 Windows 경로 길이 문제**: 초기 V19 attempt 01은 단계 receipt의 긴 임시 파일명에서 실패했습니다. 기존 파일명 뒤에 이름·PID·UUID를 붙이는 방식을 짧은 고유 임시 이름과 Windows extended path로 수정하고, 깊은 실제 경로 테스트를 추가했습니다. 실패 결과와 Runtime 120.059초/11.719초를 보존했습니다.

증명: [May03 원본 종단 행](MAY03_ROOT_CAUSE_PROOF.json), [May04 원본 정수 값](MAY04_LITERAL_INTEGER_DIAGNOSTIC.json).

## 종료 상태와 충돌 분류

- V18R2 May03 stationary LP: 120.065초, raw 11 `INTERRUPTED_AT_POLICY_CAP`, SolCount 0. INFEASIBLE 판정이 아닙니다.
- 고정 후보 00~03: 모두 raw 3 INFEASIBLE, 각각 0.458 / 0.417 / 0.469 / 0.443초. 충돌 원인은 네 차량의 96번 종단 위치 고정과 원본 flow/terminal-location 행입니다.
- root seed: 중단 후 raw 11, SolCount 0, incumbent·Native Gap·첫 incumbent 시점 UNKNOWN, BestBd 0.286904835317072, NodeCount 1.0. 첫 정수해 부재였으며 Gap 도달 지연으로 설명하지 않습니다.
- 이 후보들에서 원본 전체 MILP가 불가능하다고 선언하지 않았습니다. Voltage/thermal/SOC/PCS/PCC 위반의 독립 증명으로 종단 IIS를 확대 해석하지 않습니다. 초기 zero-P/Q background의 voltage residual은 별도 진단 자료이며 실제 실패 LP 해의 residual이 아닙니다.
- 충돌 집중 위치: May03, 종단 96번 슬롯/직전 flow, MESS01~04, 각 차량이 선택한 마지막 도착 장소. 첫 Native IIS는 MESS01/STA01 경계 flow를 선택했습니다.
- INF_OR_UNBD·NUMERIC는 실제 네 후보에서 관측되지 않았습니다. 진단 LP raw 11은 proof 시간 초과로 그대로 기록했습니다. IIS wall과 UNKNOWN Native는 최적화 Runtime으로 중복 회계하지 않습니다.

## 성능 비교와 개발 시도 보존

| 사례 | 초기화 Native 초 | FULL | 초기 UB |
|---|---:|---|---:|
| May01 V17 기존 LP | 18.673 | PASS | 0.642675232471 |
| May02 V18R2 기존 LP | 7.639 | PASS | 0.655007499636 |
| May03 V18R2 안전 중단까지 | 836.216 | 초기해 없음 | UNKNOWN |
| May03 V19 중간 attempt 02 | 186.937 | F2 중요 모드 PASS | 1.000000000000 |
| May04 V19 중간 attempt 02 | 15.739 | 종단 복구 LP PASS | 0.460996639074 |
| May03 V19 최종 attempt 03 | 4.480 | F1 PASS | 0.537800466212 |
| May04 V19 최종 attempt 03 | 6.674 | F1 PASS | 0.535346345175 |

May04 중간 시도의 UB는 최종 F1보다 낮습니다. 이번 정책은 첫 FULL 실행 가능 해에서 측정을 종료하므로 더 좋은 초기 UB를 찾기 위한 후속 탐색을 하지 않습니다. 최종 Global Gap 3%는 이후 동결된 독립 UB/LB 인증기의 역할입니다.

May01/02는 기존 실측만 비교하며 재실행하지 않았습니다. 최신 코드에서 그 두 날짜의 새 성능은 측정하지 않았습니다. 기존 stationary 결정 패턴과 목적함수의 의미를 유지하고 원본 정수 표현의 고정을 명확하게 했습니다.

## 모델·소스·예산

- 동결 원본 scientific source **1,007개 SHA 일치**, B1 완료 결과 **31/31 SHA 일치**.
- May03는 V18R2와 original/selected matrix·domain, bundle, anchor, binary count의 7개 항목이 동일합니다.
- May04는 앞선 V19 attempt 02의 동일 날짜 원본 모델과 같은 7개 항목을 비교해 일치했습니다. May04의 이전 V18 baseline이 존재한다고 주장하지 않습니다.
- Case SHA는 출력 receipt 경로를 포함해 attempt마다 달라질 수 있습니다. 수학적 동일성은 위 matrix/domain/input 항목 및 원본 transport proof로 확인했습니다.
- May03 FULL 961,362행 / 316,664변수 / 208,248 정수·이진, May04 FULL 961,340행 / 316,993변수 / 208,580 정수·이진: 모두 PASS. 96슬롯 경로/SOC/PCS/모드/연결 검증도 PASS입니다. fresh Actual AC 평가를 실행했다는 의미는 아닙니다.
- LP의 Native Gap은 UNKNOWN입니다. 독립 Global LB·Global Gap은 이번 시험에서 산출하지 않았습니다. 최종 3% 인증을 획득했다고 주장하지 않습니다.
- [누적 회계](CUMULATIVE_NATIVE_ACCOUNTING.json)에 실패·중간·최종 attempt와 진단 LP를 합산했습니다. May03 실험/진단의 알려진 optimize subtotal은 1,388.430초, May04는 34.132초입니다. V18 lost-call 및 IIS Native는 UNKNOWN으로 남겨, May03 공식 누적/잔여 예산을 임의 확정하지 않았습니다. 공식 known prior 3,316.044초와 QUARANTINE은 보존됩니다.

## F1~F5와 후속 알고리즘

F1은 원본 stationary 경로·모드 패턴을 고정한 LP입니다. 실패 시 종단 상태가 복구된 충전 모드 후보 LP를 시도합니다. F2는 stationary 경로의 중요 슬롯 모드를 해제한 뒤 전체 96슬롯 모드를 해제합니다. F3는 전압 P/Q 민감도 순서로 STA 4→8→전체 STA→전체 원본 장소의 route/mode 선택을 확대합니다. ETA 검증 및 단일 이동에너지≤원본 SOC 범위 검사는 원본 제약에 근거합니다. 나머지 site 제한은 초기화 heuristic이라고 기록합니다.

모든 초기화 solve의 전체 원본 행을 유지합니다. F4의 진단용 부분계·singleton 대입·Phase-I slack 해는 채택하지 않습니다. F5는 원본 bounds/type/objective를 복원하고 MIPGap 0.03, MIPFocus 1, SolutionLimit 1, 최대 300초로 실행합니다. 이 제한을 늘려 성능 개선을 대체하지 않습니다. 호출은 requested와 남은 Native의 최솟값으로 제한합니다.

F2 중요 모드의 실제 FULL PASS는 중간 May03 시도에서 확인했습니다. 최종 두 날짜는 F1에서 종료됐으므로 F2 전체 모드/F3/F4/F5의 성능 비교는 실제 실행하지 않았습니다. 해당 확장·복원·실패 경로는 경량 테스트로 검증했습니다. 모델 copy를 호출하지 않고 F1 후 보조 모델을 재사용합니다. 검증되지 않은 MIP start 및 다른 날짜의 point는 공급하지 않았습니다.

`case.point` 계약을 유지하며 운영 어댑터는 기존 `_fresh_lp_dual()`과 Adaptive로 전달합니다. 초기화 실패 후 옛 900초 seed를 중복 호출하지 않습니다. 이 인터페이스는 테스트했지만 이번 실측에서 후속 LP 하한/Adaptive는 실행하지 않았습니다.

## 검증과 그래프

원래 151개 경량 세트를 포함한 최종 회귀 **268개 PASS**. Terminal slot/실제 도착 장소, FULL route-flow 정수 표현, 중요/96슬롯 모드, F3 route 확대, F5 bounds/type/objective 복원, 첫 MIPSOL 기록, budget 회계, Windows 깊은 경로, 독립 certificate monitor와 handoff를 검증했습니다.

[시간 비교](figures/01_first_full_time.png) · [단계별 Native](figures/02_stage_native_runtime.png) · [May03 V18/V19](figures/03_may03_v18_v19.png) · [May03 차량 P/Q/SOC/경로](figures/04_may03_vehicle_dispatch.png).

`collect_results.py`는 읽기 전용으로 sealed 결과를 모으고 `plot_results.py`는 그 결과만 그립니다. plotting 의존성은 별도 tmp 경로에 설치했으며 Solver Python 환경을 변경하지 않았습니다.

## Q1~Q10

1. **안전 중단**: V18R2 May03만 정상 interrupt. Seed 714.364초와 초기화 합계 836.216초, 로그·ledger·checkpoint 보존. May02/B1/다른 연구 프로세스는 보존.
2. **진짜 원인**: 종단 96번 상태 누락으로 네 후보가 모두 원본 terminal/flow와 충돌. 원본 정수 route-flow 표현을 남긴 LP의 미세한 비정수 값도 기존 FULL 게이트가 거부. 둘 다 후보 생성에서 수정.
3. **첫 초기해 단계**: 최종 May03/04 모두 F1.
4. **시간**: May03 Native 4.480초 / FULL wall 172.778초. May04 Native 6.674초 / FULL wall 198.808초.
5. **전체 MILP 우회**: 두 날짜 모두 LP 1회, MILP 0회, 명시적 SEED_BYPASS_CERTIFIED_DISPATCH receipt.
6. **May01/02 빠른 성능**: 기존 성공 자료 보존 및 동등 패턴 유지. 사용자 지정에 따라 최신 실측은 3일/4일만 했으므로 최신 1일/2일 성능을 단정하지 않음.
7. **전체 제약**: FULL·literal integer·96슬롯 물리 모두 PASS. rounding/clipping/repair 0.
8. **Adaptive 동결**: 원본 scientific 1,007개 SHA 일치. Adaptive/Primal–Dual/Pricing/RMP/UB/LB 코드 변경 0건.
9. **인터페이스**: case.point 유지, 기존 pipeline 전달/중복 seed 금지 테스트 PASS. 이후 Adaptive는 실측 범위 밖.
10. **31일 안정성**: 아직 31일 전체 안정성을 입증하지 못함. 이번 두 날짜의 성공과 회귀 결과를 근거로 향후 날짜를 단계적으로 검증해야 함. 이번 작업은 전체 캠페인을 자동 재개하지 않음.
