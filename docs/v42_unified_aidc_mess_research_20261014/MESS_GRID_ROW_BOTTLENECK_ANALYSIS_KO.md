> PR 중단 스냅샷 안내: 아래 초기 진행 기록은 역사 자료이며 현재 실행 상태가 아니다. 현재 결과는 [최종 검토](FINAL_UNIFIED_REVIEW_KO.md), [AIDC 실측](AIDC_SITE_ONLY_PR_SUMMARY_KO.md), [MESS 압축 실측](MESS_EXACT_COMPRESSION_BENCHMARK.json), [벡터화 실측](MESS_EXACT_VECTORIZED_PROOF_BENCHMARK.json)을 따른다. 60분/Runtime Repair/Migration·새 Known Heavy·4단계 Heavy는 중단되어 있다.

# S1 병목과 정수·물리 영역을 보존하는 압축 검토

S1에서는 후보지와 활성 차량을 줄여도 원본 Full96 계통 행이 그대로 남는 비용이 지배했다. 계통 814,560행은 전체 836,244행의 **97.407%**였다. 7,711개 변수 중 이진변수는 4,717개였고, nonzero는 23,258,846개였다. 따라서 차량·후보지 수를 줄였다는 사실만으로 모델 구성이나 Root LP가 충분히 작아졌다고 볼 수 없다.

| 구간 | 실제 측정 | 판단 |
|---|---:|---|
| Build | 79.336초 | Native 호출 이전 계통 행 구성 비용 |
| Presolve | 8.39초 | 681,899행·39열 제거 |
| Presolved | 154,345행·7,672열·3,701,053 nonzero | nonzero 84.088% 감소 |
| Root LP | 17.57초, 시간 제한 중단 | 완성된 Root LP 최적해/Root LB 아님 |
| 최초 Solver incumbent | Native 시작 후 1.242초 | 현재 FULL 재검증한 정차 시작점 |
| 최초 현재 FULL 검증 | 모델 구성 시작 후 84.629초 | 원본 현재 계통 행·4대 물리 모두 PASS |
| Native 전체 | 30.241초 | 요청 30초 대비 0.241초 초과, 공유 원장 기록 |
| FULL UB | 0.6412659669740282 | 정차해, 이동 FULL 해는 미발견 |
| 축소 문제 Global LB | 0.4661962672051837 | 해당 S1 전체 경로 MILP Solver Bound |
| Gap | 27.3006% | 3% 목표 실패, 원본 4대·24개 인증 없음 |
| 피크 RSS / Private Commit | 2.893 GB / 4.172 GB | 실제 프로세스 계측 |

시작점과 최종점의 목적값 차이는 RHO 안전 여유 1e-9에 해당한다. Raw 벡터에서는 두 좌표만 달랐으며 최대 차이는 9.466e-7이었다. 유의한 물리 제어 개선으로 주장하지 않는다. 비활성 차량의 P/Q/SOC/Mode/위치는 원본과 정확히 같았고, 전체 이동에너지는 0 kWh였다.

## 추가 Native 없이 수행한 Source 행 감사

동일 S1 전기적 계수와 고정 AIDC/비활성 MESS 입력을 읽어 슬롯마다 8,485×11 행 블록만 생성했다. 11개 좌표는 선택한 5개 사이트의 signed P/Q 합계와 RHO다. 96개 슬롯을 스트리밍했으며 Gurobi 모델 구성·Optimize·새 전체 S1 행렬 저장은 모두 0회였다. 분석 시간은 약 2.575초였다.

| 제거 후보 유형 | Source 식 기준 행 수 |
|---|---:|
| 상수만 있는 행 | 0 |
| 원본 물리의 바깥 box 전체에서 항상 만족 | 433,863 |
| 동일 signed LHS·동일 RHS | 66,144 |
| 동일 signed LHS·더 느슨한 RHS | 15,936 |
| 위 유형의 중복을 제거한 합집합 | 474,122 |

합집합은 계통 행의 약 58.21%다. 변압기 kVA 206,084행, 변압기 current 14,427행, thermal face 135,704행, 전압 upper/lower 117,907행이 후보에 포함된다. 작은 민감도를 0으로 만들거나 전압·정격을 완화한 결과가 아니다. signed 계수는 모두 유지했다.

**이 수치는 원본 Source 식과 Native 행 수의 감사이며, 실제 Native CSR 비트 동등성 인증이 아니다.** 최초 S1 실행에서 A/d 행렬을 저장하지 않았으므로 Native의 부동소수 상수 결합 순서를 사후 비트 단위로 비교할 수 없다. 후보 행은 이번 Solver에서 제거하지 않았다. 이후 Supervisor가 실제 행렬을 캡처해 Source 식과 정확히 비교한 경우에만 채택한다. 이미 실행한 S1의 UB/LB·원장·Raw는 변경하지 않는다.

## 포함관계와 채택 조건

원본 활성 2대의 물리 영역에서 각 사이트의 aggregate P는 [-600,600] kW, Q는 [-800,800] kvar 안에 있다. 이 box는 모든 사이트가 동시에 최대값을 가질 수 있다고 허용하므로 원본 route/Mode/PCS/SOC 영역의 바깥 근사다. RHO의 원래 범위 [0,1]을 그대로 사용한다. 기존 UB나 LB를 box 경계로 복사하지 않는다.

각 원본 signed 행을 `a·z ≤ b`로 쓸 때, box support의 상향 enclosure `u`가 `u ≤ b`이면 모든 원본 정수·물리 해가 그 행을 만족한다. 따라서 그 행을 제거해도 원본 물리 영역과 교차한 feasible set은 바뀌지 않는다. 구현은 저장된 dyadic 계수의 곱과 합마다 `nextafter(+∞)`를 사용한다. 0이 아닌 계수를 epsilon으로 지우지 않는다.

두 행의 LHS가 정확히 같으면 더 작은 RHS를 유지한다. 같은 RHS는 중복이고, 큰 RHS는 논리적으로 함의된다. 양의 비례행은 정확한 rational 검증이 있어야 삭제할 수 있으며 이번에는 NOT_RUN이다. 가까운 행·비슷한 상·비슷한 민감도는 동일한 행으로 취급하지 않는다.

채택 순서는 현재 Stage의 Source/Case/Anchor 확인 → 실제 원본 Native CSR와 domain 캡처 → 삭제 행의 exact support/동일 LHS 증명 → 변환·복원 witness 비교 → 원본 FULL raw validator다. Anchor가 바뀌는 M2에서는 RHS와 증명을 새로 생성한다. M1의 LB·UB·행 삭제 인증을 복사하지 않는다.

## Beam/Joint와 선택적 계통 행의 역할

기본 구조 `Physical Prescreen → Adaptive Beam → Joint P/Q/SOC MILP → FULL Validator → Incumbent Registry`는 유지한다. 위의 증명된 행 압축은 경로 제한과 별개다. Beam 경로 pool은 원본의 부분집합이므로 그 Bound는 원본 Global LB가 아니다.

선택적 계통 행으로 후보를 먼저 생성하는 방법은 검토할 수 있다. 모든 계통 행에 대한 원본 FULL 검증을 통과한 raw 해만 UB로 받아들이고, 누락 행의 위반을 발견하면 해당 행을 추가한다. 제한된 경로 pool과 누락된 계통 행을 동시에 쓰면 원본과 단순한 포함관계를 주장할 수 없으므로 Bound는 진단값으로 유지한다. 전체 축소 경로 영역에 대해 일부 계통 행만 제거한 relaxation은 별도 포함관계 증명이 있어야 축소 문제 LB로 인정할 수 있으며, 원본 4대·24개 Global 인증으로 승격하지 않는다.

현재는 압축 후보의 Source Native0 감사까지만 완료했다. 추가 Heavy 실행 없이 Native 결과를 만들지 않는다. S2–S7을 실행하지 않았으므로 차량 수와 후보지 수 중 어느 것이 더 큰 실제 병목인지 아직 분리할 수 없다.
