# Codex 작업 지시 — V2_add IEEE8500 May01 단일일 전압 안정화 및 최적화 문제 규모 축소

## 0. 작업 범위와 최종 목표

Repository: `BeaverVillage/MobileESS`

기존 Draft PR: https://github.com/BeaverVillage/MobileESS/pull/236

기준 HEAD: `759dd5f87edd7340c703507e42dc36ccd32afcdc`

원본 알고리즘 기준: V44 r043 `affc7226a519adbe072d7debbc3ae25ea71c3487`

**동일 V2_add / PR #236에서 작업한다. 새로운 실험 버전·PR을 만들지 않는다.**

### 연구 범위 확정

IEEE8500 실험은 다음 단일 날짜로 한정한다.

**2025-05-01, AEST**

- Planning: 96슬롯
- Actual: Prefix24 + 평가96 = 120슬롯
- B0/B1/B2/B3
- 독립 Fresh AC
- IEEE8500 Balanced
- Background β_BG=2.00 우선 유지
- AIDC12, GPU780
- STA12, IDC12의 차량용 전기 포트
- MESS8, 차량당 P300/Q250/PCS400
- 기존 RegControl12 및 추가 SVR3 우선안
- V44 원본 A1–M1–A2–M2
- K48, Adaptive Beam Search, Direct Joint MILP

May02~07의 기존 증거·파일·SHA는 보존하지만, 이번 작업에서 신규 AC·Native·최적화를 실행하지 않는다.

### 최종 목표

1. May01의 B0 기본 계통과 MESS 유효전력·무효전력 주입 시 전압 안전성 확보
2. B0/B1/B2/B3에 동일한 Actual 전압제어 하드웨어·정책 적용
3. 원본 전체 선로 최대부하율 목적함수 유지
4. IEEE8500 FULL 문제의 Prescreening 및 Compact Formulation 구현
5. 필요할 때만 제약식을 추가하는 Constraint Generation 구현
6. MESS8의 STAY/MOVE 자유도와 AIDC FULL 제약 보존
7. 모델 규모·메모리·생성시간을 실측하고 독립 FULL 동등성 검증
8. 공식 May01 캠페인 시작 직전까지 준비

**장시간 Native 최적화 및 공식 B0/B1/B2/B3 캠페인은 실행하지 않는다.**

---

# PART A. May01 전압 문제 해결

## A1. 기존 전압 문제 재확인

현재 PR #236의 May01 B0:

- Actual 최대 선로부하율: 75.711000%
- 기존 평가 노드 Vmax: 1.049087915 pu
- 신규 IDC08 LV 포트 Vmax: 1.050523816 pu
- Actual Prefix 저전압 23초
- Actual 전체 과전압 지속시간 31초
- Planning TIME 최대 전압: 약 1.051829 pu
- 기존 MESS8 두 피크 Q50 Pilot: 73.744160%
- Pilot도 전체 TIME 물리 PASS는 아님

기존 결과를 보존하고 아래를 구분한다.

1. 초기 Tap/Cap 상태로 인한 전압 위반
2. SVR 제어 지연 중 위반
3. SVR 제어 완료 후 지속되는 위반
4. 원본 MV 버스의 위반
5. 새 IDC/STA 480V 포트의 위반
6. MESS 유·무효전력 주입으로 발생하는 위반

각 위반에 대해 Bus/Phase/Slot/물리적 시각/지속시간/상류 경로/전압을 기록한다.

## A2. IDC08 접속설비부터 감사

May01에서는 신규 `full_mobile_idc08_lv.1`이 무주입 상태에서도 1.050524 pu를 기록했다.

따라서 MESS의 Q를 줄이는 방법만으로 이 결함을 해결할 수 없다.

IDC08을 포함한 24개 차량 포트의 다음 항목을 검사한다.

- MV/480V 변압기 연결
- Delta/Wye 및 원본 IDC Wye/Wye 모델과의 차이
- 권선별 Base kV
- OpenDSS Voltage Base 인식
- Neutral/Grounding
- Transformer %R/%X
- 무부하 손실 및 여자전류
- 고정 Tap
- 상 순서
- MESS0 출력 시 PCC 전압
- 실제 MESS P/Q 주입 시 PCC 전압

**물리 모델의 오류라면 바로잡되, 전압을 통과시키기 위해 변압기 임피던스·정격·전압 Base를 임의 조정하지 않는다.**

원본과 다른 공학적 설비를 사용한다면 실제 설비 가정과 전기적 타당성을 명시한다.

## A3. SVR 추가·재배치 검토

기존 SVR3이 실제로 동작하는 것은 확인됐다.

그러나 단순히 기존 SVR 개수를 증가시키는 것이 최선인지는 아직 알 수 없다.

다음 대안을 사전 등록하여 비교한다.

- H0: 현재 SVR3
- H1: 현재 SVR3의 설치 위치 개선
- H2: 기존 SVR3 + 추가 1 Bank
- H3: 기존 SVR3 + 추가 2 Bank
- H4: 기존 SVR3 + 추가 3 Bank

각 대안은 단순 Bank 수 증가가 아니라, 실제 위반 Bus의 전기적 경로에 따라 위치를 결정한다.

평가 기준:

- 전체 평가96 전압 0.95~1.05 pu
- Prefix 및 Native TIME 이벤트 안전
- Planning 전압제어 안전
- MESS P/Q 주입 시 전압 여유
- Tap 동작 횟수
- Tap 포화 여부
- Control Queue와 Delay
- 선로·변압기·SVR 자체 정격
- 기존 원본 선로 임피던스·정격 보존
- 전압제어기 간 상호작용
- 최대 선로부하율 변화

기존 IEEE8500 P5 Source1.04 pu, Vreg123.5 V, CAPBank3 초기OFF를 결과에 맞춰 임의 변경하지 않는다.

추가 SVR의 설치 위치와 물리적 제어 설정은 공학적 근거를 갖춘 후보로 정의한다.

**최소한의 추가 설비로 물리 제약을 만족하는 구성을 우선 선정한다.**

선정 결과는 B0/B1/B2/B3 전체에 동일하게 적용한다. Arm별로 SVR 개수·설정·위치를 변경하지 않는다.

## A4. MESS P/Q 제어까지 고려한 전압 인증

B0가 전압 PASS하더라도 MESS8이 P/Q를 주입하면 과전압이 발생할 수 있다.

따라서 B0만 기준으로 SVR을 선정하지 않는다.

다음 조건에서 독립 TIME AC를 수행한다.

- MESS 출력 0
- 기존 두 피크 P-only Pilot
- 기존 두 피크 Q50 Pilot
- 실제 이동경로를 갖춘 유한 MESS 가능해
- IDC/STA별 물리적으로 유효한 P/Q 극한 및 중간 출력
- Q 양·음 방향 모두
- Charging/Rebound
- 각 차량 SOC/PCS/포트 정격 준수

P/Q 극한의 순간 AC PASS를 하루 전체 운전 PASS로 혼동하지 않는다.

정확한 적용가능 조합을 보존하고, 실제 시간·SOC·이동 제약을 충족하는 Schedule은 전체 Actual120/Fresh로 확인한다.

모든 가능한 임의의 P/Q 출력을 무조건 안전하게 만드는 것이 목표는 아니다.

**최적화기가 선택하는 운전점이 안전 영역 안에 있도록 모델과 물리 검증기를 정확하게 연결하는 것이 목표다.**

필요하다면 공통 Actual Q-only 안전 보정 정책도 별도 후보로 검증할 수 있다. 단, 기존 V44 정책과의 차이를 명시하고 모든 Arm에 동일하게 적용해야 하며, 특정 위반 슬롯을 사후적으로 수동 수정하는 방식은 금지한다.

### Planning/Actual 장비 계약

현재 구조는:

- Planning: 기존 RegControl12
- Actual: 기존 RegControl12 + 추가 SVR 연구 설비

이다.

Planning TIME 위반은 Actual 전용 SVR 추가만으로 해결됐다고 주장하지 않는다.

원래 Planning 물리 계약에서 위반을 해결할 방법을 따로 검증한다.

초기 전압 위반이 원본 이전 운전 이력 부재로 인한 경우에도 임의 Warm Start, Queue 삭제 또는 위반 시간 제외를 통해 PASS로 만들지 않는다.

물리적으로 정당한 해결책을 찾지 못하면 해당 Gate는 FAIL로 유지한다.

---

# PART B. FULL 제약식 규모 축소

## B1. 기존 FULL 문제를 Reference로 봉인

현재 완료된 FULL Matrix Pack:

- Binary: 417,296
- Continuous: 3,350,097
- 전체 변수: 3,767,393
- 전체 제약식: 20,634,824
- Nonzero: 302,476,152

단일 Gurobi 모델은 4GiB 보호 한도에서 약 23슬롯까지 생성한 후 중단됐다.

현재 원본 Matrix Pack의 다음 항목을 SHA로 봉인한다.

- 모든 행과 열의 원본 ID
- 변수 유형과 Bounds
- Row Sense/RHS
- Objective Coefficients
- Nonzero Coefficients
- Original Constraint Family
- Route/Mode/SOC/PCS
- AIDC/GRID/PCC
- Parent Terminal 목적함수
- 모든 물리 안전 제약

이번 작업은 원본 수학적 문제를 임의로 완화하는 것이 아니라 **동일한 문제를 더 작은 계산 표현으로 구성하는 작업**이어야 한다.

최적화 전에 정확한 비교 기준을 확보한다.

---

## B2. Constraint Family별 규모 분석

현재 문제가 커진 직접 원인을 실제 행렬에서 분석하라.

특히:

- Parent line thermal 16-face
- Transformer nameplate 16-face
- All-terminal current
- Parent P/Q/current-correction binding
- Voltage squared binding
- Transformer winding P/Q
- MESS Route Flow
- Charge/Discharge Mode
- SOC 및 Energy Balance
- PCS16
- STA/IDC Port
- Occupancy

의 Rows/Columns/Nonzero/RAM을 각각 집계한다.

각 Family별로 다음을 계산한다.

1. 전체 원본 행 수
2. 구조적으로 중복된 행 수
3. 실제 제어 입력에 민감하지 않은 행 수
4. 보수적 Bound로 항상 만족한다고 증명 가능한 행 수
5. 현재 반드시 유지해야 하는 행 수
6. Constraint Generation으로 처리 가능한 행 수
7. 제거 시 FULL 동등성 증명이 필요한 항목

**원래 16-face를 단순히 8-face로 줄여 문제를 변경하지 않는다.**

---

# PART C. Safe Prescreening

## C1. 전기적 제약 Prescreening

모든 선로·전압 노드·변압기에 대해 May01 96슬롯의 원본 제약을 유지한 상태에서 안전한 Screening을 구현한다.

제어 가능 범위:

- AIDC12의 실제 유효한 유연전력
- MESS8의 P/Q
- PCS 정격
- SOC
- Route/Time
- 24개 접속 포트
- Charging/Discharging
- 원본 전압/선로/변압기 조건

을 고려한다.

전기적 민감도와 변수 Bound를 이용해 각 원본 행에 대한 보수적 상·하한을 계산한다.

예:

`max_possible_row_value <= original_RHS - numerical_margin`

임을 모든 허용 제어에 대해 증명한 행은 안전하게 비활성화할 수 있다.

반대로 증명하지 못한 행은 유지하거나 Constraint Generation 대상으로 넘긴다.

### 반드시 주의할 사항

B0에서 부하율이 낮다는 이유만으로 해당 선로를 제거하지 않는다.

현재 입력에서 민감도가 작다는 이유만으로 제거하지 않는다.

특히 모든 선로가 목적함수에 포함되므로, **열 정격을 만족하는 선로라도 최대부하율 목적함수를 결정할 수 있다.**

목적함수 Epigraph 행과 물리 안전 제약을 구분하여 처리한다.

목적함수 행을 제거할 경우 원래 전체 선로·상·시간 최대값을 여전히 정확하게 계산할 수 있어야 한다.

제거된 행은 모두 원본 ID·증명 Bound·제거 사유·복원 방법을 기록한다.

확실한 수학적 증거가 없는 행은 삭제하지 않는다.

---

## C2. MESS 경로 Prescreening

기존 8대의 STAY/MOVE 자유를 보존한다.

Route 24개 서비스 위치와 실제 교통 데이터를 변경하지 않는다.

다음 조건으로 물리적으로 불가능한 경로 조합만 제거할 수 있다.

- 출발시각 이전 이동 불가능
- 실제 ETA 위반
- 이동 에너지 부족
- SOC 범위 위반
- 원본 Route Arc 불가능
- 종료 시각에 도착 불가능
- 접속 가능한 물리 포트 부재
- 원본 Source에서 허용하지 않는 Mode

단, 정당한 이동 경로를 단순히 계산량이 많다는 이유로 삭제하지 않는다.

모든 차량은 다음을 자유롭게 선택해야 한다.

`STAY / MOVE / CHARGE / DISCHARGE / Q`

차량마다 서로 다른 이동 경로와 다중 MOVE를 선택할 수 있어야 한다.

기존 STAY 해만 남도록 하는 Prescreening은 금지한다.

### 정확성 증명

Prescreening 전후에 다음을 비교한다.

- 유효 Route 수
- 제거 Route 수
- 차량별 도달 가능한 상태
- 최소/최대 SOC Reachability
- 이동 에너지
- 종단 SOC
- 모든 차량의 STAY/MOVE 가능성
- Original FULL Validator

가능한 경로가 제거되지 않았음을 원본 데이터와 독립적으로 검증한다.

---

## C3. AIDC Prescreening

원본 A1/A2 Job 도메인과 QoS·Capacity·Deadline을 보존한다.

다음 항목으로 불가능한 Job Option을 제거한다.

- GPU Site 비호환
- 원본 Allowed Start 위반
- GPU/Rack Capacity 초과
- Deadline 위반
- Residency 위반
- WAN 불가능
- Checkpoint/Migration Capability 부재
- 완전 서비스/Rebound 불가능

단순히 현재 Accepted Cache에 없다는 이유로 가능한 옵션을 제거하지 않는다.

기존 Golden414 캐시는 FULL 불가능으로 거부된 상태를 유지한다.

AIDC 시간 이동·사전배치·Migration의 모든 원래 가능한 선택지를 보존한다.

---

# PART D. Compact Formulation

## D1. 불필요한 연속 보조변수 제거

현재 FULL 모델에는 Grid 전기량을 표현하기 위한 P/Q/current/voltage 보조변수와 다수의 Equality Binding이 존재한다.

다음 방법을 우선 검토하라.

### 1. Equality Elimination

명시적 Equality로만 정의되는 보조변수를 원본 제어변수의 Affine Expression으로 정확히 대체할 수 있는지 확인한다.

예:

`y = a + Bx`

를 별도 y변수·Equality로 두지 않고, 필요할 때 해당 Expression을 원래 행에 대입한다.

단, 대입 결과가 지나치게 Dense해져 Nonzero/RAM이 증가한다면 대체하지 않는다.

각 제거된 변수는 원본 좌표로 정확히 복원할 수 있어야 한다.

### 2. Constant Electrical Rows

유효한 제어 도메인 전체에서 전기적 응답이 정확히 0인 행을 확인한다.

- 고정 전압 행
- 고정 선로 전류
- 제어 입력과 독립적인 변압기 행

을 식별한다.

안전 제약의 경우 상시 만족이 증명되면 제거한다.

목적함수의 경우 고정된 선로 부하율이 원본 최댓값 계산에 계속 반영되도록 고정 하한으로 정확히 집약한다.

고정 위반이 발견되면 제거하지 말고 구조적 불가능성으로 보고한다.

### 3. 중복·종속 제약 제거

원본과 동일한 제약을 여러 번 생성한 경우에만 중복 제거한다.

동일한 수식처럼 보여도 시간·상·Terminal·정격이 다르면 중복으로 처리하지 않는다.

### 4. Sparse Assembly

- CSR/CSC Sparse Matrix
- 필요한 행만 동적 생성
- Dense Array 복제 방지
- 중복 계수 합산
- 정확한 Variable Mapping
- Slot별 Streaming Assembly
- Peak RAM 감소

를 적용한다.

원본 민감도 계수를 임의로 0으로 처리하거나 Solver 허용오차를 변경해서 Sparse하게 만드는 방법은 금지한다.

---

## D2. 16-face 제약의 Compact 처리

현재 Parent thermal 및 Transformer 정격 16-face 제약이 전체 Rows의 큰 부분을 차지한다.

**16-face의 원래 수학적 의미를 유지하면서 계산 표현을 축소하라.**

검토할 방법:

1. 동일 P/Q Affine Expression 재사용
2. 원본 16-face 중 수학적으로 지배되는 행만 증명 후 제거
3. 실제 위반 가능성이 있는 Family/Slot 우선 활성화
4. 나머지 행을 정확한 Constraint Generation 대상으로 분리
5. 재생성 가능한 원본 Face Index 보존

기존 16-face를 다른 다각형이나 다른 전류 근사식으로 바꾸지 않는다.

모든 16-face에 대한 최종 FULL Separation을 수행할 수 있어야 한다.

---

# PART E. Exact Constraint Generation

## E1. 초기 Compact Master 구성

Prescreening으로 안전하다고 증명되지 않은 행 중 주요 전압·선로·변압기 제약을 초기 Master에 포함한다.

목적함수는 원본과 동일하다.

`min max(line, phase, time) loading`

처음부터 모든 2,063만 행을 Gurobi에 생성하는 방식에서 벗어나야 한다.

대신 원본 FULL 제약의 일부만 포함하는 초기 Master와 전체 FULL Separation Oracle을 분리한다.

## E2. 위반 제약 추가

Master에서 후보해를 얻을 때마다 원본 전체 행렬에 후보해를 대입한다.

다음 전체를 검사한다.

- 모든 원본 선로 Parent objective
- 모든 선로 양단 전류
- 모든 전압 Node/Phase
- 모든 변압기 Current/kVA
- 전체 16-face
- 모든 IDC/STA Port
- PCS/SOC/Route/Occupancy
- AIDC Job/QoS

위반된 원본 행의 정확한 Row ID와 Coefficients를 Master에 추가한다.

이 과정을 원본 FULL 제약이 만족될 때까지 반복할 수 있도록 구현한다.

### Global LB/UB 주의

Minimization에서 원본 FULL 제약의 일부를 제외한 Master는 일반적으로 Relaxation이다.

따라서 그 Relaxation에서 정확하게 인증한 하한은 적절한 조건 아래 원본 FULL의 하한으로 사용할 수 있지만, Restricted Master의 가능해를 곧바로 원본 FULL의 UB로 사용할 수는 없다.

- LB: 유효한 Relaxation 및 Solver Bound 근거 필요
- UB: 원본 FULL 가능해 인증 필요
- Global Gap: 동일 원본 목적함수와 Bound 근거 필요
- AC Physical PASS: 별도 독립 Fresh 필요

K48 Lower Bound도 동일한 원본 문제에 대해 유효함을 증명해야 한다.

완결되지 않은 Pricing, 누락된 제약, Restricted Master 목적값을 인증 Global LB라고 보고하지 않는다.

### 중요

Constraint Generation의 최종 결과를 FULL과 동등하다고 주장하려면:

1. 원본 전체 행에 대한 Separation 완료
2. 추가해야 할 위반 행 0
3. 원본 도메인 복원 PASS
4. 원본 목적함수 완전 복원 PASS
5. 원본 FULL 가능해 검증 PASS
6. 유효한 Global LB/UB 및 Gap 근거

를 충족해야 한다.

---

# PART F. 독립 동등성 검증

## F1. Compact 모델 검증

기존 `FULL96_MATRIX_PACK_CERTIFICATION.json`을 원본 비교 기준으로 사용한다.

Prescreened/Compact 모델의 후보해를 반드시 원본 전체 변수·행 좌표로 복원한다.

다음 검증을 독립적으로 수행한다.

- 모든 원본 Row Residual
- 모든 원본 Bound
- Integrality
- Parent Terminal 목적함수
- 양단 Current
- Voltage
- Transformer
- 16-face
- PCS16
- SOC
- Route/Movement
- IDC/STA Occupancy
- AIDC 원본 FULL Job

STAY Witness뿐 아니라 MOVE Witness, P/Q 양·음 방향, Charging/Rebound, 경계 SOC 등의 반례도 검사한다.

새 모델이 원본보다 작은 목적값을 만들었다면 그것이 실제 개선인지, 누락된 제약을 이용한 가짜 개선인지 확인한다.

**원본 FULL 위반이 발견된 후보해는 절대 UB로 수용하지 않는다.**

## F2. Before/After 규모 비교

다음 표를 실제 생성 결과로 작성한다.

| 지표 | 원본 FULL | Prescreened | Compact | Constraint Generation 초기 |
|---|---:|---:|---:|---:|
| Binary | | | | |
| Continuous | | | | |
| Rows | | | | |
| Nonzero | | | | |
| Peak RSS | | | | |
| Build Wall | | | | |
| FULL 복원 | | | | |
| 독립 동등성 | | | | |

수치가 없으면 추정값을 PASS로 표시하지 않는다.

다음 개선량도 계산한다.

- Rows 감소율
- Nonzero 감소율
- 연속변수 감소율
- 모델 생성시간 감소율
- 메모리 감소율

**가능하면 기존 개발용 4GiB 보호 한도 안에서 Compact Native0 전체 모델 생성까지 완료한다.**

보호 한도를 임의로 높이거나 기존 Worker를 중단해서 통과시키지 않는다.

단일 Gurobi 전체 모델 생성이 여전히 어렵다면 원본 제약을 검증 가능한 Oracle로 보유하는 Delayed Constraint Generation 구조를 구축하고, 미완료 인증 범위를 정확하게 보고한다.

---

# PART G. May01 캠페인 직전 통합

## G1. 최종 물리 구성 동결

May01 기준으로 적격한 전압제어 구성이 확인되면 이를 동결한다.

- β_BG=2.00
- AIDC12/GPU780
- STA12/IDC12 차량 포트
- MESS8
- 최종 SVR 구성
- P5 및 원본 물리 설정
- 공통 Actual 정책

동결 전에는 실제 AC/Fresh 안전성과 제어 가능성을 함께 평가한다.

동결 이후 B0/B1/B2/B3별 결과에 따라 SVR 위치·수·전압설정을 다시 바꾸지 않는다.

## G2. 원본 알고리즘 연결

축소된 전기 모델을 다음에 연결한다.

- A1
- M1
- A2
- M2
- K48
- Adaptive Beam Search
- Direct Joint MILP
- Global LB/UB/Gap
- Actual TIME
- Independent Fresh AC

원본 A1/A2 Job 제약과 MESS8의 MOVE/STAY 자유는 유지한다.

기존 B0와 AIDC 정책의 의미를 변경하지 않는다.

May01 B0가 안전하고, MESS 유한 Pilot이 안전해졌다고 해서 B1/B2/B3 최적화 결과까지 인증하지 않는다.

반드시 같은 설비에서 Arm별 최종 FULL 결과를 따로 검증해야 한다.

## G3. May01만 실행 준비

공식 후보:

- May01 B0
- May01 B1
- May01 B2
- May01 B3

그 외 날짜의 신규 실행은 금지한다.

현재 May01 B0 및 MESS8 유한 Pilot AC/Fresh는 기존 결과를 보존하고, 신규 전압 설비 구성에 대해서만 독립 재검증한다.

알고리즘 통합 완료 전까지 장시간 Native Solver 호출을 하지 않는다.

작은 Fixture와 Native0 모델 생성, 유한 물리 Pilot, 독립 AC 검증만 수행한다.

필요한 경우 별도 승인 없이 공식 M1/M2 Solver Budget을 소비하지 않는다.

---

# PART H. 최종 보고 및 GO/NO-GO

동일 PR #236에 다음 결과를 제출한다.

1. `MAY01_VOLTAGE_ROOT_CAUSE_KO.md`
2. `MAY01_SVR_HARDWARE_COMPARISON.csv`
3. `MAY01_ALL24_PORT_VOLTAGE_CERTIFICATION.json`
4. `MAY01_MESS_PQ_TIME_SECURITY.json`
5. `FULL_CONSTRAINT_FAMILY_CENSUS.csv`
6. `PRESCREENING_PROOF_AND_REMOVED_ROWS.csv`
7. `COMPACT_FORMULATION_EQUIVALENCE.json`
8. `BEFORE_AFTER_MODEL_SIZE.csv`
9. `FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json`
10. `MESS8_COMPACT_NATIVE0_BUILD_REPORT.json`
11. `MAY01_B0_B1_B2_B3_STAGE_READINESS.json`
12. `FINAL_MAY01_PRESTART_REVIEW_KO.md`
13. `FINAL_MAY01_PRESTART_GO_NO_GO.json`

### 최종 보고 필수 질문

1. May01 B0의 IDC08 무주입 과전압 원인은 무엇이었는가?
2. 기존 SVR3으로 해결 가능한가?
3. 추가 SVR이 필요하다면 몇 Bank가 어느 위치에 필요한가?
4. MESS8의 P/Q 운전에서 전압 문제가 해결됐는가?
5. Prefix·Planning·Actual 이벤트 위반이 모두 해결됐는가?
6. 원본 2,063만 제약을 얼마나 줄였는가?
7. Binary/Continuous/Nonzero는 얼마나 감소했는가?
8. Prescreening에서 제거한 행은 왜 안전한가?
9. Compact Formulation은 원본 FULL과 정확히 동등한가?
10. Constraint Generation에서 누락된 위반 행은 없는가?
11. K48의 Global LB는 여전히 유효한가?
12. 8대 MESS의 MOVE/STAY/P/Q/SOC가 전부 보존됐는가?
13. May01 B0/B1/B2/B3 실행 준비가 모두 완료됐는가?
14. 공식 May01 캠페인 시작 전에 남은 결함은 무엇인가?

### 최종 판정

전압 안전, 원본 FULL 동등성, 실제 Stage 연결, 독립 검증 및 실행 안전 Gate가 모두 통과하면:

`READY_FOR_MAY01_CAMPAIGN_APPROVAL`

그 외에는:

`PRESTART_BLOCKED_WITH_EVIDENCE`

를 유지한다.

**결과를 PASS시키기 위해 기존 전압제약 0.95~1.05 pu를 완화하거나, 원본 선로·변압기·차량 제약을 삭제하는 행위는 금지한다.**

원본 FULL과 동등한 Compact 모델을 만드는 것이 목표이며, 단순히 더 작은 근사 문제를 푸는 것은 완료로 인정하지 않는다.

모든 결과를 동일 PR #236에 Commit/Push하고, 기존 Worker·원장·V44/V1_add 및 저장된 실험 증거를 보호하라.

공식 May01 캠페인은 사용자 별도 승인 전까지 실행하지 않는다.