# Codex 작업 지시 — V2_add PR #236 결함 수정, 원본 동등성 검증 및 IEEE8500 고제어력 시나리오 재평가

## 0. 작업 목표

저장소: `BeaverVillage/MobileESS`

현재 Draft PR: https://github.com/BeaverVillage/MobileESS/pull/236

실험 버전: **V2_add**

이번 작업은 기존 V2_add의 결함 및 미검증 항목을 정확히 해결하고, IEEE8500 Balanced 계통이 V44 r043 알고리즘의 확장성 실험에 적합한지 재평가하는 것이다.

기존 V2_add 결과는 삭제하거나 덮어쓰지 않는다.

다음 작업을 순서대로 수행하라.

1. 기존 V44 r043 목적함수와 V2_add 측정 방식의 동등성 검증 및 수정
2. IEEE8500 전압제어의 Static/TIME 계약 검증
3. 기존 V44의 AIDC Known/Unknown·QoS 정책과 V2_add Pilot 검증 조건 대조
4. MESS8 고정 Pilot의 피크 이동 문제 분석 및 실제 실행 가능한 시간 분산 Pilot
5. 추가 배경부하 Stress Scale에서 B0 최대 부하율 및 제어 민감도 측정
6. 모든 물리·입력·제어 Gate를 통과한 경우에만 시나리오 동결 및 후속 V44 알고리즘 이식 준비

**현재 V2_add의 B0 56.1469%와 MESS 개선 0.2018%p를 최종 확정값으로 취급하지 않는다.**

원본 목적함수 및 TIME 제어 계약 검증 후 수치를 재판정해야 한다.

---

# PART A. Source 및 실험 독립성

## 1. 기존 Source 동결

다음 소스들을 기준으로 사용한다.

- V44 r043: `affc7226a519adbe072d7debbc3ae25ea71c3487`
- V2_add 기존 PR #236 HEAD 및 모든 실행 Receipt
- IEEE8500 공식 Balanced 기준: PR #197
- 기존 IEEE8500 C2 PCC 연구: PR #199
- IEEE8500 정적 엔진 이식 준비: PR #200
- V1_add 입력 Source Lineage: PR #235

작업 전 현재 GitHub PR HEAD와 로컬 Worktree 상태를 확인한다.

외부에서 이미 추가된 수정이 있다면 먼저 차이를 감사하고 기존 결과를 보존한다.

### 절대 변경 금지

- V44 Production Source 및 Campaign
- V1_add Source 및 결과
- 기존 IEEE8500 연구 PR의 원본 파일
- Kestrel Job 입력
- GPU780 및 AIDC12 전력 모델
- 기존 SUMO 교통망과 Route Table
- 기존 MESS 이동시간·이동 에너지
- 원본 IEEE8500 선로·변압기 정격
- A1–M1–A2–M2 알고리즘
- K48, Adaptive Beam Search, Direct Joint MILP의 수학적 구조
- 기존 B0/B1/B2/B3 정의

MESS는 8대, 차량별 P300 kW/Q250 kvar/PCS400 kVA 및 기존 SOC 제약을 유지한다.

V2_add 전용 Worktree, Runtime 및 PR에서만 수정한다.

기존 V44 Worker·PID·원장·Native 예산·Monitor와 충돌하지 않도록 한다.

---

# PART B. 목적함수 측정 결함 수정 — 최우선

## 2. 원본 V44 목적함수 정의를 코드에서 검증

현재 V2_add의 `v2_add_preflight/physical.py`는 다음과 같이 측정한다.

`self.all_mask = [node > 0 for every original line terminal]`

즉, 원본 선로의 양단 전류를 모두 전역 최대값 계산에 포함한다.

반면 기존 PR #197의 IEEE8500 목적함수는 Source-rooted Parent Terminal 측정이고, V44 r043의 `v42_thermal/measurement.py`도 해당 선로의 Parent Bus에 대응하는 Terminal 전류를 읽는다.

다음 소스를 직접 대조하라.

- `v42_thermal/measurement.py`
- `v42_thermal/authority.py`
- 원본 V44 Planning 및 M-stage의 목적함수 생성 코드
- PR #197의 `_orient_original_lines()`
- PR #197의 `objective_line_mask`
- V2_add `physical.py`
- V2_add `vendor/ieee8500_ac.py`

### 검증할 사항

1. 실제 전원측 Parent Bus
2. Parent Terminal 선택
3. 원래 Branch/Phase 축
4. 원본 NormalAmps 분모
5. 실제 Triplex Hot Leg 및 Primary Phase 처리
6. Disabled Line 처리
7. 원본 목적함수와 Fresh AC 측정 정의
8. 변압기 정격 제약과 선로 목적함수의 분리

계통이 달라져도 **V44의 목적함수 정의 자체는 유지**해야 한다.

기존 V44의 Parent Terminal 기준이 최종 확인되면 다음처럼 구현한다.

- `rho_objective`: 원본 Parent Terminal 기준
- `rho_all_terminals`: 모든 원본 선로 양단의 최대값
- `rho_MV_objective`: MV의 Parent Terminal 기준
- `rho_LV_objective`: LV의 Parent Terminal 기준
- `all_terminal_thermal_PASS`: 양단 모든 실제 도체의 정격 검증

모든 원본 선로 및 실제 상은 유지한다.

LV/Triplex 선로를 목적함수에서 제외하지 않는다.

실제 선로 양단의 전류 안전 검증도 제거하지 않는다.

### 3. 기존 AC 저장 배열로 독립 재검산

현재 V2_add가 보존한 B0 및 Pilot `AC_FULL.npz`, Axis, Receipt를 우선 사용한다.

새 OpenDSS Solve 없이 다음을 재계산하라.

- 기존 9개 Beta의 Planning/Actual B0
- 기존 모든 MESS Pilot
- 기존 AIDC Pilot
- 기존 Joint Pilot
- 슬롯별 최대 부하율
- 일별 전역 최대 부하율
- MV/LV 최대값과 차이
- 병목 선로/상/단자
- Pilot의 실제 개선량

원본 Parent Terminal Mask와 기존 All-Terminal Mask를 동일한 전류 배열에 적용하여 결과를 비교한다.

허용오차는 원본 수치 정밀도와 저장 배열의 직렬화 오차에 근거해 사전에 명시한다.

각 결과에 다음 두 지표를 병기한다.

- `V44_CANONICAL_OBJECTIVE`
- `ALL_TERMINAL_SECURITY_DIAGNOSTIC`

기존 결과를 수정하지 말고 새로운 감사 결과 파일을 생성한다.

**반드시 확인할 질문**

"기존 56.1469%와 0.2018%p는 목적함수 정의를 바로잡아도 동일한가?"

변경되면 변경된 값과 원인을 정확히 보고한다.

원래 목적함수의 전기적 방향·상 축을 정확하게 복원하지 못하면 이후 실험을 차단한다.

---

# PART C. 전압제어 Static/TIME 계약 검증

## 4. 현재 P5 물리 설정은 유지

현재 P5 설정:

- Source = 1.04 pu
- RegControl 12개
- Vreg = 123.5 V
- CAPBank3 초기 OFF
- 원본 CapControl 9개
- 원본 선로·변압기 정격
- IEEE8500 공식 Balanced 모델

설정값을 성과가 좋아지도록 다시 조정하지 않는다.

기존 V44 IEEE123의 RegControl7/Actual43/SVR12 설비를 IEEE8500에 강제로 복사하지 않는다.

### 5. TIME 동작 검증

현재 V2_add는 `controlmode=static`을 사용한다.

반면 V44 Actual/Fresh는 시간에 따라 Tap/Cap 및 제어 상태를 갱신한다.

다음 항목을 직접 조사하라.

1. V44 Actual의 ControlMode, SolutionMode 및 시간 갱신
2. 전압조정기 Tap Delay
3. Capacitor 제어 Delay 및 Hysteresis
4. Control Queue 이벤트
5. Prefix24 → Evaluation96 상태 연속성
6. Actual/Fresh 초기 상태와 재생 방식
7. 각 15분 슬롯의 실제 시간축
8. Planning과 Actual의 독립 초기화
9. 원본 제어 동작과 V2_add static 근사의 차이

### 6. IEEE8500용 TIME Adapter

기존 P5 물리 설정과 원본 설비를 보존하면서 OpenDSS의 TIME 기반 운전이 실제로 가능하도록 V2_add Adapter를 검토하고 필요한 최소한의 수정만 수행한다.

시험은 다음 순서로 한다.

- β=1.00 B0
- β=1.50 B0
- Static과 TIME의 Tap/Cap 궤적 비교
- 96슬롯 Planning / Prefix24+96슬롯 Actual
- 독립 Fresh Replay

TIME 구현이 실제 제어기 지연 및 순차 동작을 재현하는지 확인한다.

단순히 `controlmode=static`을 `time`으로 바꾸고 PASS 처리하지 않는다.

물리적 설정의 차이와 V44의 시간적 제어 의미 차이를 각각 보고한다.

TIME 계약을 인증할 수 없으면 `TIME_CONTROL_NOT_VERIFIED`를 유지한다.

**TIME과 Static 결과가 달라지면 기존 Static B0 결과를 최종 V44 호환 B0로 사용하지 않는다.**

관련된 모든 B0 및 Pilot은 최종 승인된 TIME 계약에서 재검증해야 한다.

---

# PART D. AIDC 제약 및 QoS 검증

## 7. 기존 후보 거부 414개/192개 재감사

현재 V2_add에서는 다음을 보고했다.

- Planning 기존 Accepted 후보: Allowed Start 불일치 414개
- Actual 기존 Accepted 후보: Intentional Burden Budget 초과 192개

그러나 V44 r043은 `B1_RESEARCH_RELAXED_KNOWN_WINDOW_V1`이라는 연구용 정책을 사용한다.

반드시 다음 코드를 확인하라.

- `v43_corrective/known_window.py`
- `v44/actual_policy.py`
- 원본 A1/A2 Job Window 생성·검증
- 원본 Actual Known/Unknown 정책
- QoS Ledger 및 Source Deadline 정의

### 특히 중요한 구분

V44 Known 완화 정책은 일부 원본 Window·Deadline을 사후 측정 대상으로 취급할 수 있지만, 이는 Source에서 원래 허가된 QoS 완화를 의미하지 않는다.

실제 `policy_assumption()`에도 Source authorization 및 QoS 인증이 없다는 점이 기록돼 있다.

따라서 다음 세 가지를 구분하라.

1. `SOURCE_STRICT_COMPLIANT`
2. `V44_RESEARCH_POLICY_COMPLIANT_BUT_SOURCE_QOS_NOT_CERTIFIED`
3. `V44_POLICY_OR_PHYSICAL_VIOLATION`

414개 및 192개 Job 각각에 대해:

- Job UID
- Known/Unknown
- 원래 Allowed Starts
- 실제 Planning Start
- 실제 Actual Start
- Time-shifting 허용 여부
- 원본 Delay Budget
- Completion Deadline
- 실제 Delay 및 Intentional Burden
- 기존 V44 정책상 허용 여부
- Source의 엄격한 QoS 만족 여부
- 거부 또는 수용 근거 코드 위치

를 기록한다.

### 절대 금지

- Accepted였다는 이유만으로 모든 Job을 통과
- Strict Window 불일치만으로 기존 V44 연구정책을 결함으로 단정
- 연구용 Relaxed Known 정책을 Source QoS 승인으로 표시
- QoS Budget을 새로 늘리기
- Deadline 수정
- Missing Job 생성
- 기존 Known/Unknown 제어 알고리즘 변경
- 미검증 AIDC 제어량을 B1/B3 성과로 표시

## 8. AIDC 실제 제어 가능성 재검증

현재 V2_add의 Actual Pilot은 다음과 같이 매우 좁은 범위만 시험했다.

- 단일 GPU Job
- Site당 최대 1개 Job
- 동일 사이트 1~4슬롯 지연
- Migration 없음
- Pre-site 없음
- Multi-GPU Gang 제외

이를 AIDC의 전체 유연성으로 해석하지 않는다.

실제 V44 r043에서 허용하는 제어 권한과 Source 제약을 구분해 다음을 다시 조사하라.

- Multi-GPU Gang
- Time-shifting
- Pre-site
- Checkpoint Migration
- WAN/호환성
- GPU Capacity
- Known/Unknown 별 제어 가능성
- Original Windows 및 QoS
- Actual 런타임·도착시간 인과성
- 피크 시간대 제어 가능 전력
- Job Rebound
- 정확한 C1 사이트별 P/Q

계산해야 할 지표:

- 실제 제어 가능한 Job 수
- GPUh
- 피크 시간대 이동 가능 kW
- Time-shifting 가능 전력
- Migration 가능 전력
- Rebound 최대 전력
- 전체 시간대 에너지·서비스 보존
- 전역 최대 선로부하율에 대한 영향

이론적 Flexibility Envelope와 **Source 제약까지 만족한 실제 실행 가능한 Schedule Witness**는 반드시 구분한다.

실행 가능한 비영 Actual AIDC witness를 만들지 못하면 `ACTUAL_AIDC_NONZERO_NOT_VERIFIED`로 기록한다.

그 경우 원인이 단순히 Pilot 탐색 범위가 좁아서인지, 실제 Source 허용 유연량이 부족한 것인지 분석한다.

이번 진단을 위해 V44 A1/A2 알고리즘을 변경하지 않는다.

---

# PART E. MESS8 제어력 정확한 재검증

## 9. 기존 0.2018%p의 원인 분석

기존 β=1.50 Actual MESS Pilot은 다음과 같다.

- B0 피크 슬롯: 74
- MESS 제어 후 피크 슬롯: 76
- 새 피크: 19:00
- 고정 방전 슬롯: 68~75
- 기존 개선량: 0.2018%p

이 결과는 고정 스케줄의 한계를 보여줄 뿐, V44 Joint MILP의 최적 제어력 상한은 아니다.

기존 Pilot 기록은 보존한다.

### 10. 시간 분산 MESS Pilot

기존 동일 8대 MESS, STA12, PCS, Route, SOC 및 전력망 제약을 사용한다.

다음과 같은 제한된 진단 스케줄들을 사전 등록하고 비교하라.

- 기존 68~75 방전
- 방전 시작/종료를 1~4슬롯 늦춘 스케줄
- 19:00 이후까지 방전하는 스케줄
- 방전시간을 더 길게 하고 kW를 낮춘 스케줄
- 8대가 서로 다른 시간대에 방전하는 Staggered 스케줄
- 기존 허용 Q 운전영역 안의 물리적으로 가능한 보조 시나리오

모든 스케줄에서 실제 충전량과 방전량은 SOC 수지로 계산한다.

차량별 다음을 검증한다.

- SOC 초기값 및 종단값
- SOC Min/Max
- Pch/Pdis 동시 운전 금지
- PCS16 원본 제약
- P/Q 한계
- 충전효율 및 방전효율
- 이동 에너지
- 기존 Route Table
- STA 동시 접속 정격
- 모든 선로·상·시간의 전류
- 충전 Rebound
- 최대 부하율을 결정하는 새로운 시간·선로·상

진단 스케줄은 기존 V44 Beam Search/Joint MILP를 대체하는 새로운 최적화 알고리즘이 아니다.

이 단계에서는 제한된 후보만으로 물리적 제어 가능성을 비교한다.

B3 최적화기는 이후 기존 알고리즘 그대로 STAY/MOVE 및 P/Q/SOC를 자유롭게 결정해야 한다.

### 11. 제어력 지표

각 스케줄에서 다음을 계산하라.

- 전체 96슬롯 최대 선로부하율
- MV 최대 부하율
- LV 최대 부하율
- 기존 피크 시점의 감소량
- 새로운 피크 시각·선로
- 전체 전역 최대 부하율의 감소량(%p)
- 총 충전/방전 에너지
- MESS별 P/Q/SOC
- 물리 제약 PASS/FAIL

8대가 동일한 전기적 선로에 거의 중복된 영향을 주는지도 확인한다.

MES​​S별 P/Q 민감도의 중복성, Top-K 병목에 대한 기여, 동시 운전에 따른 병목 전환을 검증한다.

순간 제어 가능성, 96슬롯 Feasible Pilot, 최적화 결과는 별도 지표로 관리한다.

---

# PART F. 추가 Background Stress Scale

## 12. 기존 Beta 범위 보존

기존 검증 완료:

`β_BG = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50]`

모든 기존 AC, Fresh, Pilot, Source SHA 및 결과는 보존한다.

기존 Pre-registration을 수정하거나 과거에 새로운 Beta가 등록돼 있었던 것처럼 기록하지 않는다.

이번 사용자 지시에 따른 신규 Stress Extension으로 별도 등록한다.

### 신규 후보

`β_BG = [1.75, 1.85, 1.90, 1.95, 2.00, 2.05, 2.10]`

이는 탐색 시작 범위이며 최종 B0 값은 실제 AC로 확정해야 한다.

원본 V44의 1.15 Background 계수가 이미 적용된 최종 배열에 이번 추가 `beta_BG`를 정확히 1회만 적용한다.

- Background P/Q만 Scaling
- PV 불변
- AIDC Job/GPU/C1 불변
- MESS 차량별 P/Q/PCS/SOC 불변
- 기존 도로망·ETA 불변
- 원본 Line/Transformer Rating 불변
- IEEE8500 Balanced 고객 상 배치 불변

새로운 Stress Case의 Background가 원본 V44와 다르다는 점을 명시한다.

### 13. 실행 전 조건

신규 Scale AC를 수행하기 전에:

1. Canonical Objective Mask 검증 PASS
2. 입력 동일성/PV/PCC Mapping PASS
3. TIME 제어 계약 검증 또는 명시적 차단 상태 확정
4. 원본 물리 정격·하드웨어 설정 SHA 확인
5. 독립 실행 자원 확인

을 완료하라.

TIME 제어 계약이 미검증이라면 신규 결과를 V44 동등 물리 운전의 공식 Screening으로 인증하지 않는다.

모든 Candidate는 다음을 평가한다.

- Planning 96슬롯
- Actual Prefix24 + 96슬롯
- 독립 Fresh
- Canonical 전체 최대 선로부하율
- MV 최대
- LV 최대
- 슬롯별 MV−LV Headroom
- Top-20 혼잡 선로
- 모든 전압 0.95~1.05 pu
- 모든 선로 정격
- 모든 변압기 정격
- 모든 STA Port
- Tap/Cap 동작
- 전력수지 및 AC 수렴

물리적으로 FAIL한 후보도 삭제하지 않는다.

### 14. Primary Scenario 선정

우선 목표:

`B0 Actual rho_max = 75~85%`

적합한 후보가 없으면:

`B0 Actual rho_max = 70~85%`

단, 부하율만 높다고 적합한 계통으로 선정하지 않는다.

선정 근거에는 다음이 반드시 필요하다.

- 최대 부하율이 MV 제어 가능한 선로에서 발생
- LV 최대 부하율과 충분한 여유
- 실제 AIDC12/STA12가 병목에 영향을 줄 수 있음
- MESS8의 실제 실행 가능한 운전영역 확인
- MV에서 LV나 다른 MV 선로로의 병목 전환
- 피크가 한 슬롯에서 다른 슬롯으로 이동하는 현상
- 실제 96슬롯 Pilot 개선량
- 물리 위반 없음

**1%p 이상의 실제 전역 개선은 선호 목표**로 두되, 이것을 보장된 결과로 만들기 위해 부하율·정격·Job·PCC를 조정하지 않는다.

동일한 선정 규칙과 고정된 PCC를 사용한다.

후보 간 차이가 작으면 사전에 선언한 규칙으로 선택한다.

B1/B2/B3 최적화 결과를 사용해 Beta를 선택하지 않는다.

적합한 후보가 없다면 `NO_QUALIFIED_SCENARIO_AFTER_EXTENSION`으로 판정한다.

---

# PART G. 알고리즘 이식 준비

## 15. 모든 사전 Gate를 통과한 뒤 G4 준비

시나리오 선정에 성공하면 아래 항목을 독립 감사한다.

- 원본 V44 r043 A1/M1/A2/M2 Source SHA
- IEEE8500 전기적 Grid Adapter
- 전체 선로의 Canonical 목적함수
- 모든 선로 양단·상 전류 안전 제약
- 8대 MESS 변수/제약 차원
- Route/SOC/Mode/P/Q/PCS 연결
- K48 하한의 원본 FULL 동등성
- Beam Search 경로 Pool 및 8대 공동 탐색
- Direct Joint MILP
- A1/A2의 원본 Job 도메인
- LB/UB/Global Gap
- Planning/Actual/Fresh
- Actual TIME 제어
- 독립 FULL AC 검증기

Source 변경은 Grid 및 차량 차원 Adapter 등 필수 이식에 한정한다.

원래 V44 알고리즘을 임의로 새로 구현하지 않는다.

기존 Known/Unknown 정책의 연구적 한계와 QoS 미인증 사항도 그대로 표시한다.

이 단계에서는 Native0 Model Build, 변수/제약/Nonzero/RAM 추정 및 경량 동등성 테스트까지만 수행한다.

**G4의 실제 장시간 A1/M1/A2/M2 Native 최적화 및 B0/B1/B2/B3 캠페인은 별도의 명시적 실행 승인 전까지 시작하지 않는다.**

---

# PART H. 독립 검증 및 회귀 테스트

## 16. 필수 검증 테스트

반드시 다음 테스트를 추가하라.

### Objective

- 원본 Parent Terminal 선택 일치
- Triplex Phase/Hot Leg 축 일치
- Disabled Line 유지
- NormalAmps 정격 무변경
- 모든 선로 양단의 별도 안전 검증
- 저장된 배열에서 전역 최대값 재계산 일치
- MV/LV 분류 및 Top-K 순위 검증
- Canonical과 All-Terminal 수치 혼용 방지

### Physical

- PV2,354 연결·총량·설치용량
- AIDC12 및 STA12
- 차량8대 정격 및 PCS16
- P5 설정 SHA 일치
- Static/TIME 차이 및 제어 이벤트
- Actual Prefix24 상태 연속성
- Fresh AC 독립 재계산
- Tap/Cap 및 Control Queue
- 선로·변압기·전압·포트
- 전력수지 및 Source 입력 적용

### AIDC

- Known/Unknown 경계
- 414개 Allowed Start 불일치 재분류
- 192개 Intentional Burden 초과 재분류
- Strict Source QoS와 V44 연구정책 구분
- GPUh/Capacity/WAN/Checkpoint
- C1 Planning/Actual 계산 일치
- Rebound
- Actual 비영 witness 검증

### MESS

- 8대 초기 위치
- STAY/MOVE 도메인 유지
- 96슬롯 SOC 및 종단 제약
- 충전/방전 Rebound
- P/Q/PCS 및 Port 제약
- 피크 이동
- 전역 최대 부하율 계산
- 다중 차량 중복 민감도

### Regression

- 기존 V44 Source Byte 무변경
- 기존 V1_add Source 무변경
- 기존 PR #236 실행 증거 무변경
- 신규 Source SHA 기록
- 동일 입력에 대한 독립 Fresh Replay
- 실패한 Pilot/Scale 결과 보존
- 실행 Worker/Native 원장 무변경

검증기와 결과 생성 코드가 동일한 잘못된 Mask나 임시 배열을 공유해 동시에 PASS하는 일이 없도록 독립 산술 검증을 수행한다.

---

# PART I. 보고 및 산출물

## 17. 필수 결과

V2_add의 기존 결과를 보존하고 신규 감사 버전을 별도 저장한다.

다음 산출물을 작성하라.

1. `OBJECTIVE_CONTRACT_AUDIT_KO.md`
2. `CANONICAL_VS_ALL_TERMINAL_RESULTS.csv`
3. `RECALCULATED_B0_AND_PILOT.csv`
4. `STATIC_VS_TIME_CONTROL_AUDIT.csv`
5. `TIME_CONTROL_FRESH_CERTIFICATION.json`
6. `AIDC_WINDOW_POLICY_414_REAUDIT.csv`
7. `AIDC_QOS_BUDGET_192_REAUDIT.csv`
8. `AIDC_REAL_FEASIBILITY_REPORT_KO.md`
9. `MESS8_TEMPORAL_PILOT_COMPARISON.csv`
10. `MESS8_PEAK_SHIFT_ANALYSIS.csv`
11. `EXTENDED_BETA_PREREGISTRATION.json`
12. `EXTENDED_BETA_B0_RESULTS.csv`
13. `EXTENDED_BETA_MV_LV_HEADROOM.csv`
14. `EXTENDED_BETA_GLOBAL_SENSITIVITY.csv`
15. `SELECTED_SCENARIO_FREEZE.json`
16. `V44_IEEE8500_G4_READINESS_AUDIT.md`
17. `FINAL_V2_ADD_CORRECTION_REVIEW_KO.md`
18. `FINAL_V2_ADD_GO_NO_GO.json`

결과를 생성하지 못하면 빈 수치와 `NOT_VERIFIED`, 구체적인 차단 사유를 기록한다.

필요한 그림은 Python/SVG로 생성한다.

### 최종 보고 내용

아래 사항을 한국어로 수치와 실제 Source 근거를 제시해 보고하라.

1. 기존 V2_add 목적함수 Mask는 원본과 일치했는가?
2. 기존 B0 56.1469%는 원본 목적함수에서 얼마인가?
3. 기존 MESS 0.2018%p 감소는 재계산 후 얼마인가?
4. Static/TIME에서 최대 부하율 및 Tap/Cap 궤적 차이는 얼마인가?
5. AIDC 414개/192개는 실제 결함인가, 정책 차이인가?
6. Source QoS와 기존 V44 연구정책 중 무엇이 인증됐는가?
7. 실제 가능한 Actual AIDC 유연량은 얼마인가?
8. MESS 방전 시간을 조정하면 19:00 피크 이동 문제가 완화되는가?
9. MESS8의 가장 좋은 실행 가능한 Pilot 개선량은 얼마인가?
10. 추가 Beta 중 B0 75~85%를 만족하는 후보가 존재하는가?
11. 그 후보의 MV/LV 최대 부하율 차이는 몇 %p인가?
12. 실제 제어 가능한 병목 선로는 어디인가?
13. 최종 선정한 Beta/PCC는 무엇이며 선정 근거는 무엇인가?
14. G4 이식 전에 남은 결함은 무엇인가?

### 최종 판단

다음 상태를 명확하게 구분한다.

- `OBJECTIVE_CERTIFIED`
- `TIME_CONTROL_CERTIFIED`
- `SOURCE_QOS_CERTIFIED` 또는 `RESEARCH_POLICY_ONLY`
- `B0_PHYSICAL_CERTIFIED`
- `FEASIBLE_CONTROL_PILOT_CERTIFIED`
- `SCENARIO_SELECTED`
- `G4_READY_NATIVE0`
- `G4_NOT_READY`

모든 항목을 강제로 PASS시키지 않는다.

## 18. 완료 기준

이번 작업의 성공은 B0 80% 또는 MESS 개선 2%p라는 특정 수치를 반드시 달성하는 것이 아니다.

**기존 V44 r043과 수학적·물리적 측정 기준을 정확히 일치시키고, IEEE8500 Balanced에서 실제 실행 가능한 AIDC–MESS 제어력이 어느 정도인지 신뢰할 수 있는 수치로 검증하는 것**이 성공 기준이다.

현재 V2_add에 기록된 연구 결과는 전부 보존한다.

결함이 확인되면 독립 V2_add 코드에서 최소 수정하고, 수정 전후 SHA, 원인, 영향받는 수치 및 재검증 결과를 기록한다.

G4의 장시간 최적화는 시작하지 않는다.

최종적으로 PR #236을 업데이트하고 독립 검토 가능한 증거와 한국어 상세 보고서를 제출하라.