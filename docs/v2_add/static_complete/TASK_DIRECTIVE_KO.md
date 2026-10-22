# Codex 최종 작업 지시 — IEEE8500 May01 V44 r043 알고리즘 원형 보존 및 캠페인 직전 통합 완료

## 0. 작업 대상

Repository: `BeaverVillage/MobileESS`

기존 Draft PR: https://github.com/BeaverVillage/MobileESS/pull/236

현재 HEAD: `b58d35b95aa1b0322883bf7498a328b52f23e0ec`

원본 알고리즘 기준: `affc7226a519adbe072d7debbc3ae25ea71c3487`

**같은 V2_add / PR #236에서 계속 작업하라. Draft를 유지하고 새로운 PR이나 실험 버전을 만들지 않는다.**

이번 작업의 목적은 IEEE8500에 새로운 최적화 알고리즘을 개발하는 것이 아니다.

**V44 r043에서 이미 개발하고 검증한 A1–M1–A2–M2, K48, Adaptive Beam Search, Direct Joint MILP를 동일하게 적용하면서 IEEE8500 계통 규모에 적합하도록 문제의 수학적 표현만 효율화하는 것이다.**

작업을 완료한 뒤 공식 캠페인을 시작하기 바로 직전까지 모든 준비를 끝내라.

공식 캠페인은 실행하지 않는다.

---

# 1. 최상위 원칙 — 알고리즘 변경 절대 금지

이번 작업에서 가장 중요한 지시사항이다.

## 1.1 유지해야 하는 V44 r043 알고리즘

원본 소스를 직접 조사하고 정확히 유지하라.

- A1: AIDC 최적화
- M1: MESS 최적화
- A2: M1 결과를 반영한 AIDC 후속 최적화
- M2: 최종 MESS 최적화
- K48: 기존 Global Lower Bound 계산
- Adaptive Beam Search: 기존 경로 후보 탐색
- Direct Joint MILP: 기존 P/Q/SOC/Mode/이동 공동 최적화
- 기존 Global LB/UB/Gap 인증
- 기존 Solver Budget 및 Stop Conditions
- 기존 Branch-and-Bound/Presolve 설정
- 기존 AIDC Job/QoS/CC4/Runtime 정책
- 기존 MESS 이동경로·차량별 의사결정
- 기존 B0/B1/B2/B3 실행 의존성

원본 코드와 실제 수학적 알고리즘을 비교하여 유지 여부를 독립 검증하라.

## 1.2 금지하는 알고리즘 변경

다음은 명시적으로 금지한다.

1. 새로운 Grid Constraint Generation 알고리즘 도입
2. Delayed Constraint Generation을 공식 M-stage에 사용
3. Solver가 후보해를 반환할 때 Grid 제약식을 새로 추가하는 반복
4. Lazy Constraint/Callback 기반의 신규 Grid 제약 추가
5. 별도의 Benders Decomposition으로 원본 M-stage 대체
6. Sequential MILP 또는 Rolling Horizon으로 원본 Joint MILP 대체
7. Restricted Master를 원본 FULL 문제인 것처럼 사용
8. K48를 새로운 LB 알고리즘으로 대체
9. Beam Search와 MILP의 역할 변경
10. STAY 또는 MOVE 강제
11. 차량별 독립 MILP를 풀고 합쳐서 8대 공동 최적화라고 주장
12. 기존 MIPGap·Solver Budget을 성능에 맞춰 임의 변경

**V44 r043에 이미 존재하는 K48 Pricing 및 원본 Solver Presolve는 유지한다.**

금지 대상은 PR #236에서 새롭게 도입한 Delayed Grid Constraint Generation이다.

이 기능은 과거 진단 증거로만 보존할 수 있지만, 공식 최적화 실행 경로에서는 사용하지 않는다.

## 1.3 허용하는 작업

다음 작업은 허용한다.

- Static Prescreening
- Exact Compact Formulation
- 정확한 Equality Elimination
- 중복 제약 제거
- 수학적으로 증명된 Redundant Row 제거
- Exact Bound Tightening
- 원본과 동등한 Route/State 표현
- Sparse Matrix 구성
- 행렬 Factorization
- 중복 Affine Coefficient 계산 제거
- Static Presolve
- 계수 Cache 및 재사용
- 메모리 효율적인 모델 생성
- Original FULL 좌표 복원
- 독립 Original FULL 검증

공통 원칙은 다음과 같다.

**최적화 전에 더 작은 수학적 모델을 완성하되, 원본 FULL 문제의 허용 가능한 물리적 운전과 목적함수를 바꾸지 말 것.**

---

# 2. 실험 범위 확정

IEEE8500 실험 날짜:

**2025년 5월 1일 AEST 단일일**

- Planning 96슬롯
- Actual Prefix24 + 평가96
- B0/B1/B2/B3
- IEEE8500 Balanced
- β_BG=2.00
- AIDC12
- GPU780
- STA12 + IDC12 차량 접속설비
- MESS8
- P300kW / Q250kvar / PCS400kVA
- SOC440~1080kWh
- 초기·종단 SOC760kWh
- 실제 Route/ETA/이동에너지

May02~07은 추가 실행하지 않는다.

기존 결과와 SHA는 보존한다.

모든 비교군에 동일한 실제 전압제어 하드웨어와 정책을 적용한다.

---

# 3. 먼저 V44 r043 원본 실행 경로를 정확히 감사

코드 수정 전에 원본 실행 경로를 조사하라.

특히 다음 소스를 확인한다.

- `v44/worker.py`
- `v44/stages.py`
- `v44/q250_m4.py`
- `v42_may_campaign_native90/m_model.py`
- `v42_supercompact/formulation.py`
- `v42_supercompact/presolve.py`
- 기존 K48/Beam/Direct Joint 소스

다음 질문에 답하는 감사표를 작성한다.

1. 원본 M1/M2 모델은 어떤 순서로 생성되는가?
2. 원본 Static Presolve는 무엇을 제거하는가?
3. K48은 어떤 동일 Case와 Domain을 받아 LB를 계산하는가?
4. Beam Search는 기존 어떤 Scoring/후보 확장 규칙을 사용하는가?
5. Direct Joint MILP에는 어떤 원본 제약이 전달되는가?
6. 원본의 Presolve와 새 Delayed Grid Master가 정확히 어떻게 다른가?
7. Source 변경 없이 Adapter에서 해결할 수 있는 문제는 무엇인가?

이번 작업 후 원본 알고리즘에 불필요한 분기나 별도 최적화기를 추가하지 않는다.

---

# 4. 현재 Delayed Master를 공식 경로에서 제거

현재 IEEE8500 구현에는 다음 결과가 존재한다.

### 원본 FULL Matrix Pack

- Binary: 417,296
- Continuous: 3,350,097
- Rows: 20,634,824
- Nonzero: 302,476,152

### 현재 Constraint Generation 초기 Master

- Binary: 417,296
- Continuous: 68,609
- Rows: 431,255
- Nonzero: 3,071,592

두 모델은 현재 동일한 완성 MILP가 아니다.

43만 행 Master는 원래 FULL의 제약식 일부를 아직 포함하지 않는다.

따라서 다음 작업을 수행한다.

1. 기존 Delayed Master 코드를 분석한다.
2. Static Prescreening과 정확한 Compact 기술은 재사용한다.
3. Solver 실행 후 Grid 행을 추가하는 기능은 공식 경로에서 제거한다.
4. 최적화 시작 전에 남겨야 하는 모든 제약을 생성한다.
5. 완성된 모델을 기존 r043 Solver에 전달한다.

**431,255개 행을 그대로 FULL이라고 선언하는 행위는 금지한다.**

최종 Rows와 Nonzero는 실제 완성된 정적 모델을 생성한 뒤 측정한다.

---

# 5. Exact Static Prescreening

## 5.1 기본 원칙

원본 FULL 제약식을 전부 조사하라.

각 제약은 다음 중 하나로 분류한다.

- RETAIN: 반드시 유지
- SAFE_REMOVE: 항상 만족함이 수학적으로 증명됨
- EXACT_REDUNDANT: 다른 제약으로부터 함의됨
- EXACT_SUBSTITUTION: 동등한 변수 표현으로 대체 가능
- FIXED_INFEASIBLE: 고정 조건에서 이미 위반되는 구조적 불가능성
- UNRESOLVED: 제거를 증명하지 못했으므로 유지

UNKNOWN 또는 UNRESOLVED 행을 임의로 제거하지 않는다.

## 5.2 선로 제약

IEEE8500 원본 모든 선로를 대상으로 한다.

- 3,703개 원본 선로
- Triplex 포함
- Parent Terminal 목적함수
- 양단 Current 안전
- 원본 NormalAmps
- 모든 Phase/Time
- 원본 16-face

현재 B0에서 낮은 부하율을 가진 선로라도 MESS8의 충·방전과 이동에 의해 영향을 받을 수 있다.

따라서 B0 부하율만으로 제약을 제거하지 않는다.

모든 허용 P/Q, 이동, SOC, Job 변동 범위를 고려한 보수적 Bound를 계산한다.

해당 행이 모든 허용 운전에서 안전하다는 증명이 있어야만 제거한다.

특히 목적함수 Epigraph 제약은 Ampacity 안전 제약과 별도로 처리한다.

**선로 안전 제약을 제거할 수 있다는 사실만으로 그 선로를 최대부하율 목적함수에서 제거해서는 안 된다.**

## 5.3 변압기 제약

- 원본 모든 변압기
- 신규 IDC/STA 차량 포트
- 모든 권선
- Current/kVA
- 16-face
- 물리적 Nameplate

를 유지한다.

최대 가능한 MESS/AIDC 전력으로도 정격에 도달할 수 없는 변압기 제약은 보수적으로 증명한 뒤 제거할 수 있다.

반대로 정격 초과 가능성을 배제하지 못하면 유지한다.

## 5.4 전압 제약

모든 원본 Node/Phase/Time 및 추가 차량 LV 접속점이 대상이다.

전압 범위:

`0.95 <= V <= 1.05 pu`

전압 민감도와 P/Q 범위로 최악의 전압을 계산한다.

상·하한 모두 항상 만족한다는 증명이 있는 행만 제거한다.

작은 민감도 계수를 임의로 0으로 잘라내는 것은 금지한다.

## 5.5 MESS 경로·SOC

MESS8의 다음 자유도를 유지한다.

- STAY
- MOVE
- 다중 MOVE
- CHARGE
- DISCHARGE
- P/Q
- SOC
- Route/ETA
- 이동 에너지
- 종단 SOC
- 포트 점유

원본에서 물리적으로 불가능한 Route만 제거할 수 있다.

단순히 Beam Search가 선택하지 않을 것 같거나 목적함수에 대한 기여가 작다는 이유로 Route를 삭제하지 않는다.

기존 8대 모두 자유롭게 이동 경로를 결정할 수 있어야 한다.

## 5.6 AIDC 제약

A1/A2의 원본 Job Option, GPU, WAN, Rack, Deadline, QoS, Carryout, Migration, Time-shifting을 보존한다.

B0에서 AIDC가 고정되어 있다고 해서 B1/B3에서도 같은 전력 프로파일을 강제하지 않는다.

**M1의 고정 AIDC Domain과 A1/A2의 가변 AIDC Domain을 구분해서 각각 Static Prescreening을 수행한다.**

M2에서도 A2가 결정한 실제 AIDC 계획을 정확하게 반영한다.

---

# 6. Exact Compact Formulation

## 6.1 수학적으로 동등한 정식화

Prescreening 후 남은 모델에 대해 정확한 Compact Formulation을 적용한다.

검토 대상:

1. Equality로 정의된 보조변수의 제거
2. 중복된 P/Q Response 변수 통합
3. 독립성이 없는 중복 행 제거
4. Constant/Fixed Variable 제거
5. 정확한 Affine Expression Factorization
6. 원본과 동등한 Sparse 표현
7. 기존 V44 Static Presolve 재사용
8. 원본 Route Flow의 정확한 상태 축약
9. 계수 재계산·복제 최소화
10. 필요 이상의 Auxiliary Materialization 제거

**수학적 동등성이 입증된 변환만 채택한다.**

원본 Integer 가능해가 손실되거나 새로운 가능해가 생기는 축약은 금지한다.

## 6.2 Dense Matrix 폭증 방지

과거 Equality 전체 대입 시 Nonzero가 오히려 크게 증가한 결과가 있다.

그 방식을 그대로 다시 적용하지 않는다.

원래 계수의 Sparse 구조를 유지하면서 공유 가능한 Affine Block을 정확히 재사용하라.

중복 계수 계산을 줄이되, 새로운 Dense Jacobian을 구성하지 않는다.

CSR/CSC Sparse Matrix, Streaming Build, 공통 Affine Block Cache를 활용한다.

## 6.3 16-face 제약

원본 선로·변압기·PCS의 16-face 수학적 구조를 보존한다.

16-face를 8-face나 단순 선형 Approximation으로 변경하지 않는다.

각 면의 제약이 수학적으로 지배됨을 증명한 경우만 제거할 수 있다.

그 외의 면은 **Solver 시작 전에 최종 MILP에 모두 포함**해야 한다.

## 6.4 Root LP와 LB 검증

MILP의 Integer 가능해가 같다는 것만으로 K48 LB 인증까지 자동으로 같아지는 것은 아니다.

Compact Formulation이 LP Relaxation과 Bound에 주는 영향을 검증한다.

- 동일 원본 목적함수
- 동일 Full Integer Feasible Domain
- 유효한 LP Relaxation
- K48 Pricing/Global LB 증명 조건
- 독립 Original FULL UB 검증
- 기존 Gap 계산 규칙

을 유지한다.

신규 IEEE8500 Case에서 계산하지 않은 LB/UB를 이전 IEEE123 결과에서 복사하지 않는다.

---

# 7. Solver에 전달할 완성 모델 구성

Static Prescreening과 Compact Formulation이 끝나면 완성된 MILP를 생성한다.

반드시 다음 순서를 따른다.

`Original FULL`
→ `Exact Static Prescreening`
→ `Exact Compact Formulation`
→ `Original Static Presolve`
→ `Complete Native MILP Build`
→ `V44 r043 K48 / Beam / Direct Joint MILP`

실제 Solver 호출 전에:

- 전체 변수 정의 완료
- 전체 필요한 Grid 제약 구성 완료
- 전체 MESS 제약 구성 완료
- 전체 AIDC 관련 Stage 제약 구성 완료
- 원본 목적함수 정확히 연결
- 모든 제거 제약에 대한 독립 증명 완료
- 원본 좌표 복원 검증 완료
- Native 행렬 계수/RHS/Sense 검증 완료

를 충족해야 한다.

### 엄격한 금지

최적화기가 후보해를 반환한 다음:

- 빠진 Grid 행 추가
- 위반 행 추가
- 새 Master 생성
- 재최적화
- 다시 위반 행 추가

를 반복하는 구조를 사용하지 않는다.

원본 K48 Pricing을 제외한 새 Grid Row Generation 루프를 만들지 않는다.

Solver 자체의 기존 Presolve와 Branch-and-Bound는 허용한다.

---

# 8. Source-YY IEEE8500 계수 재생성

현재 May01의 Source-YY + SVR3 후보는 평가96에서:

- B0: 75.711008%
- P-only: 73.790115%
- Q50: 73.744164%

를 기록했다.

이는 제한적 유한 Pilot 결과이며 B2/B3 최적화 성과가 아니다.

변압기 모델:

- IDC 원본 Source Wye/Wye
- 원본 R/X/Neutral 기준
- IEEE8500의 실제 MV 정격전압 반영
- IDC/STA 480V 차량 접속
- 원본 IEEE8500 선로 및 정격 유지

를 우선 후보로 검증한다.

기존 Delta/Wye 모델에서 생성된 Grid Response Coefficients를 Source-YY에 재사용하지 않는다.

**최종 물리 구성을 동결한 다음 새로운 전기적 계수를 실제 IEEE8500 OpenDSS에서 생성하라.**

반드시:

- Planning96
- AIDC P/Q
- MESS24 서비스 위치의 P/Q
- 전체 원본 선로
- 모든 전압 Node/Phase
- 모든 변압기
- 신규 IDC/STA 포트
- Source-YY 설비

를 포함한다.

새 Case SHA를 만들고, 기존 DY Case SHA와 혼동하지 않는다.

이 새로운 계수를 대상으로 Prescreening/Compact Proof를 재생성한다.

기존 DY 기준으로 제거된 제약을 증명 없이 그대로 제외하지 않는다.

---

# 9. May01 전압 평가 계약

전압은 96개 평가 틱과 Native TIME 초 단위 이벤트를 명확히 분리한다.

### Primary 96틱 평가

May01 96개 슬롯의 원래 V44 r043 평가 기준을 조사하여 그대로 적용한다.

- 각 틱의 원래 정의된 전압 측정 시점
- 모든 Node/Phase
- 0.95~1.05 pu
- 전체 선로 최대부하율
- 변압기·선로·PCS 정격

을 검사한다.

원본 목적함수의 측정 시점도 변경하지 않는다.

### Native TIME 이벤트

초 단위의 Tap/Cap 동작과 제어 지연 중 전압 위반은 별도 기록한다.

현재:

- Prefix 저전압 23초
- Prefix 과전압 18초
- Planning 초기 과전압 15초

가 남아 있다.

원래 V44 실험 계약에서 이러한 이벤트를 필수 안전 Gate로 정의했는지 확인한다.

**원래 계약이 96슬롯 평가만 요구한다면 초 단위 진단을 임의로 새로운 최적화 제약에 추가하지 않는다.**

반대로 원래 계약이 전체 TIME 안전을 필수로 요구한다면 이를 조용히 삭제하거나 평가 기준을 완화하지 않는다.

기존 계약과 충돌하는 변경이 필요하다면 임의 승인하지 말고 명확한 Blocking Issue로 기록한다.

현재 SVR3의 평가96 PASS와 전체120 TIME FAIL을 반드시 구분한다.

최종 B0/B1/B2/B3는 동일한 실제 설비와 공통 평가 정책을 적용해야 한다.

전압을 맞추기 위해 SVR 개수나 Tap을 결과에 맞춰 변경하지 않는다.

---

# 10. 원본 A1–M1–A2–M2 통합

이제 실제 Stage Adapter를 완성하라.

## 10.1 A1

- 원본 Job FULL Domain
- GPU/Rack/WAN/QoS
- Known/Unknown
- CC4/Runtime 정책
- 실제 가변 AIDC P/Q
- IEEE8500 Grid Response
- 원본 A-stage LB/UB/Gap
- 독립 FULL 수용 검증

을 연결한다.

원본 FCFS B0와 AIDC 최적화 정책을 혼동하지 않는다.

기존 START_WINDOW 위반 캐시414개는 그대로 거부한다.

## 10.2 M1

A1 또는 B0의 실제 AIDC 결과를 받아 8대 MESS를 최적화한다.

- Source-YY 계수
- Static Compact FULL
- K48
- Beam Search
- Direct Joint MILP
- MESS8 Route/PQ/SOC
- 기존 원본 FULL Validator

를 같은 Case/Domain으로 연결한다.

원래 STAY/MOVE 자유를 보존한다.

## 10.3 A2

M1에서 실제 채택한 MESS 계획을 정확히 고정하고 기존 A2를 수행한다.

A2에서 M1 P/Q/Route를 임의로 변경하거나 다른 날짜·다른 Case의 계획으로 대체하지 않는다.

## 10.4 M2

A2 결과를 고정한 원래 M2 Joint MILP를 수행할 수 있도록 연결한다.

M1과 동일한 V44 r043 알고리즘을 재사용한다.

A2 이후 바뀐 AIDC 전력에 대한 Current Case Coefficients/Bounds를 정확하게 연결한다.

## 10.5 K48

원본 K48 알고리즘을 그대로 유지한다.

IEEE8500/MESS8의 새로운 원본 Case/Domain과 정확히 연결하고 Global LB 증명 인터페이스를 검증한다.

Restricted Master 목적값이나 과거 IEEE123 LB를 새로운 IEEE8500 Global LB라고 주장하지 않는다.

---

# 11. 계산 규모 실측 및 IEEE123 비교

원본 IEEE123 M1 FULL 기준:

- Binary: 208,312
- Continuous: 108,431
- Rows: 961,472
- Nonzero: 8,587,630

IEEE8500 원본 FULL:

- Binary: 417,296
- Continuous: 3,350,097
- Rows: 20,634,824
- Nonzero: 302,476,152

현재 Delayed 초기 Master:

- Binary: 417,296
- Continuous: 68,609
- Rows: 431,255
- Nonzero: 3,071,592

이번 작업에서는 **새로운 Static Complete MILP**의 실제 수치를 제출한다.

다음을 구분하여 측정한다.

| 지표 | IEEE123 FULL | IEEE8500 원본 FULL | IEEE8500 Static Complete |
|---|---:|---:|---:|
| Binary | | | |
| Continuous | | | |
| Rows | | | |
| Nonzero | | | |
| Model Build | | | |
| Peak RSS | | | |
| Original FULL 동등성 | | | |

중요:

**기존 431,255개 Delayed Master를 Static Complete 모델의 성과로 보고하지 않는다.**

변수와 제약을 전부 구성한 실제 Native0 결과만 사용한다.

현재 개발 환경의 4GiB 보호 한도와 다른 Worker의 자원 보호 정책을 유지하면서 모델을 생성한다.

초과하면 다음을 조사한다.

- 중복된 Equality
- 과도한 Auxiliary Variable
- Duplicate Rows
- 불필요한 Response Variable
- 반복되는 Dense Coefficients
- 안전하게 제거 가능한 물리 행
- 원본 기존 Static Presolve 적용 누락
- 비효율적인 Sparse Assembly
- 불필요한 Matrix Copy

단, 문제가 크다는 이유로 알고리즘이나 물리적 자유도를 변경해서는 안 된다.

완성 모델 생성이 여전히 불가능하면 원인을 실측하고 BLOCKED로 보고한다.

---

# 12. 독립 수학적 동등성 검증

Static Complete 모델에서 생성한 후보를 원래 FULL 좌표로 복원한다.

검증 대상:

- 원본 전체 행
- 원본 모든 변수 Bound
- Integer Domain
- 목적함수
- Parent Line Loading
- 모든 전압
- 선로 양단 Current
- 변압기 정격
- 전체16-face
- MESS8 P/Q/PCS
- Route/ETA
- SOC 및 이동 에너지
- IDC/STA 포트 및 점유
- AIDC Job/QoS/Carryout

다음 사례를 독립 검증한다.

- STAY
- 다중 MOVE
- 충전
- 방전
- 양의 Q
- 음의 Q
- SOC 경계
- 변압기 정격 근접
- 전압 상·하한 근접
- 선로 부하율 상한 근접

세 개 가능해가 통과했다고 전체 정식화가 동등하다고 선언하지 않는다.

제거된 각 제약의 수학적 정당성 및 변수 복원 관계를 독립적으로 검증하라.

아직 Solver를 실행하지 않은 상태에서는 Global Gap을 만들어내지 않는다.

최적화 결과의 실제 LB/UB/Gap 인증은 캠페인 실행 단계에서 원본 알고리즘이 수행하도록 준비한다.

---

# 13. 캠페인 직전 테스트

다음 항목을 실제 구현하고 확인한다.

### Model Build

- A1 FULL Native0
- M1 Static Complete Native0
- A2 FULL Native0
- M2 Static Complete Native0
- K48 동일 Case Interface
- Beam 동일 Case Interface
- Direct Joint 동일 Case Interface

### 실행 경로

- B0 → Actual → Fresh
- B1 → A1 → Actual → Fresh
- B2 → Reference → K48 → M1 → Actual → Fresh
- B3 → A1_REUSE → K48 → M1 → A2 → K48 → M2 → Actual → Fresh

### 운영 검증

- 원본 Budget 보존
- Thread/Worker 설정 보존
- Checkpoint/Resume
- Native Ledger
- 중복 Worker 차단
- Case SHA
- Input SHA
- 독립 Original FULL Validator
- Fresh AC
- 실패 Stage에서 적절한 중단
- 원본 결과 보존
- 기존 Worker와의 자원 격리

실제 May01 A1/M1/A2/M2/K48/Joint 장시간 Solver는 실행하지 않는다.

Native0 및 격리 Fixture 테스트를 수행한다.

최적화 실행 없이 실제 수치 LB/UB/Gap을 검증할 수는 없으므로, **Prestart 인터페이스 준비 완료와 캠페인 실행 후 수치 인증을 구분**한다.

---

# 14. 완료 판정 조건

다음이 모두 충족되어야 한다.

1. V44 r043 알고리즘 변경 없음
2. 새 Grid Constraint Generation 공식 경로 사용 0
3. Prescreening 수학적 증명 PASS
4. Exact Compact Formulation PASS
5. 최적화 전 모든 필요 제약 구성 완료
6. 실제 Static Complete Native0 생성 PASS
7. 원본 FULL 변수·제약·목적함수 동등성 PASS
8. MESS8의 모든 이동·SOC·P/Q 자유 보존
9. Source-YY IEEE8500 계수 갱신 PASS
10. A1/M1/A2/M2 실제 Stage Adapter 연결 PASS
11. K48/Beam/Joint 원본 Interface 연결 PASS
12. May01 물리적 평가 계약 및 독립 AC 검증 PASS
13. B0/B1/B2/B3 동일 하드웨어·정책
14. Checkpoint/Worker/Budget 실행 준비 완료
15. 공식 캠페인 미실행

성공했다면:

`READY_FOR_MAY01_CAMPAIGN_APPROVAL`

로 판정한다.

다만 실제 최적화에서 계산될 LB/UB/Gap은 Prestart에서 수치가 없다는 이유만으로 자동 실패 처리하지 않는다. 대신 실제 인증 코드를 올바르게 연결했는지 검증한다.

하나라도 필수 전제조건이 미완료라면:

`PRESTART_BLOCKED_WITH_EVIDENCE`

를 유지한다.

Fixture 결과를 실제 FULL 인증으로 승격하지 않는다.

---

# 15. 반드시 제출할 최종 산출물

기존 PR #236에 다음 자료를 추가한다.

1. `V44_R043_ALGORITHM_IDENTITY_AUDIT.json`
2. `NO_NEW_GRID_CONSTRAINT_GENERATION_PROOF.json`
3. `IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json`
4. `IEEE8500_EXACT_COMPACT_EQUIVALENCE.json`
5. `IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json`
6. `FULL_CONSTRAINT_FAMILY_BEFORE_AFTER.csv`
7. `IEEE123_IEEE8500_MODEL_SIZE_COMPARISON.csv`
8. `SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json`
9. `A1_M1_A2_M2_ORIGINAL_STAGE_INTEGRATION.json`
10. `K48_BEAM_JOINT_ALGORITHM_PRESERVATION.json`
11. `MAY01_PHYSICAL_EVALUATION_CONTRACT.json`
12. `MAY01_CAMPAIGN_PRESTART_READINESS.json`
13. `FINAL_PRESTART_GO_NO_GO.json`
14. `FINAL_PRESTART_REVIEW_KO.md`

최종 한국어 보고서에는 반드시 다음을 수치로 명시한다.

- 원본 V44 r043 대비 알고리즘 변경 여부
- 신규 Constraint Generation 사용 여부
- 실제 Static Complete 모델의 Rows/Nonzero
- 변수 및 제약 감소량과 수학적 증거
- IEEE123 FULL 대비 규모
- Native0 Peak RAM/Build Time
- Original FULL 동등성
- AIDC/ESS Stage 연결 결과
- Source-YY 전기계수 인증
- May01 평가96 및 Native TIME 전압 상태
- 캠페인 시작 직전 남은 차단 사유

모든 결과를 동일 PR #236에 Commit/Push한다.

**공식 캠페인 실행, 장시간 Native 최적화, 임의 Solver Budget 변경은 금지한다.**

기존 V44/V1_add/Worker/원장/Source와 과거 실험 증거를 보호한다.

## 최종 명령

**알고리즘을 새로 만들지 마라.**

**V44 r043의 원래 알고리즘을 IEEE8500에 그대로 이식하라.**

**Prescreening과 Compact Formulation으로 동일한 물리적·수학적 문제를 더 효율적으로 표현하되, Solver 실행 전에 완성된 모든 제약식을 구성하라.**

**그 상태에서 캠페인 시작 명령만 남기고 작업을 종료하라.**