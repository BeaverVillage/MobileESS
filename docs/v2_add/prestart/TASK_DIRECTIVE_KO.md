# Codex 작업 지시 — V2_add PR #236 IEEE8500 캠페인 직전 준비 완료

## 0. 최종 목표

Repository: `BeaverVillage/MobileESS`

기존 Draft PR: https://github.com/BeaverVillage/MobileESS/pull/236

기준 커밋: `d3b9f38c473a9304a7cd1d652ba2bd51cf2f51c2`

**새로운 실험 버전이나 PR을 생성하지 말고, 같은 V2_add PR #236을 업데이트하라.**

이번 작업의 목표는 IEEE8500 Balanced 기반 AIDC–MESS 공동최적화 연구를 **공식 B0/B1/B2/B3 캠페인 실행 직전 상태까지 완성**하는 것이다.

단순 보고서 작성이 아니라 계통·전압제어·PCC·AIDC·MESS8·최적화 엔진·독립 검증기·실행 준비 상태까지 실제 구현하고 검증하라.

**공식 캠페인은 절대 시작하지 않는다.**

최종 목표 상태는 다음과 같다.

`READY_FOR_USER_CAMPAIGN_APPROVAL`

단, 필수 Gate가 미완료라면 READY라고 표시하지 말고 실제 차단 원인과 증거를 제출한다.

### 우선 유지할 연구 구성

- IEEE8500 공식 Balanced
- 전체 원본 선로·상·시간의 최대 선로부하율 목적함수
- Background β=2.00 우선 후보
- 기존 RegControl 12개와 Actual 추가 SVR 3 Bank 우선 후보
- AIDC12, STA12
- 원본 GPU780
- MESS8, 차량당 P300/Q250/PCS400
- 원본 SOC·교통망·Job·PV
- 원본 V44 r043 A1–M1–A2–M2
- K48, Adaptive Beam Search, Direct Joint MILP

이 구성은 현재 우선 후보이지 공식 동결이 아니다.

이후 단계에서 결과가 불리하다는 이유만으로 목적함수, 정격, Job, GPU 또는 Solver 알고리즘을 변경하지 않는다.

---

# GATE 1. 전압제어 및 초기 운전 상태 완전 검증

## 1. SVR3 Prefix 문제 해결

현재 S1_03, β=2.00에서:

- Actual 평가96 B0 75.710958%
- 평가96 Vmin 0.951568 pu
- 평가 이벤트 Vmax 1.049088 pu
- Prefix 저전압 23초
- Prefix 과전압 18초

가 확인됐다.

평가 구간 PASS를 전체120슬롯 PASS로 확대하지 않는다.

먼저 Prefix 위반이 다음 중 무엇인지 확인하라.

1. 동결 초기 Tap/Cap 상태와 실제 직전 운전 상태의 불일치
2. 최초 전력조류 초기화 단계의 전압 현상
3. 실제 TIME Delay 동안 지속되는 물리적 전압 위반
4. RegControl/CapControl의 감시 위치나 제어기 간 상호작용
5. 전압 의존 Load/PV 실제 출력과 명령값의 차이
6. 초기 제어 Queue 및 이전 시각 이력 부족

기존 Tap 위치를 임의 변경하거나 Prefix를 제거해 통과시키지 않는다.

기존 24 Prefix 입력 및 사용 가능한 이전 운전 이력으로 초기 상태를 인과적으로 재구성할 수 있는지 검증한다.

실제 시간에 존재하는 Native Solved State와 단순 수치 반복 중간값을 구분한다.

### 추가 SVR 검증

기존 S0/S1_03/S1_06/S1_12 결과를 보존한다.

3 Bank 구성에서 해결 가능한지 먼저 확인한다. 추가 설비가 물리적으로 필요하다는 증거가 있을 때만 신규 SVR 후보를 별도 사전 등록한다.

Source1.04 pu, P5, 원본 Tap/Delay/정격을 성과에 맞춰 임의 조정하지 않는다.

### Planning/Actual

- Planning 기본 IEEE8500 RegControl 12개
- Actual 기본 RegControl 12개 + 추가 SVR 연구 구성
- 동일 Actual 설비를 B0/B1/B2/B3에 공통 적용
- Prefix24 → 평가96 Native TIME 상태 연속성
- 평가 슬롯 최종 전압과 이벤트 안전을 별도 검증
- Planning의 기존 TIME 이벤트 과전압도 별도로 감사

최종적으로 정상 초기 운전과 전체 시간축에서 전압, 선로, 변압기, PCC, SVR 자체 정격을 검증한다.

---

# GATE 2. AIDC12의 실제 제어 가능성 인증

## 2. 기존 AIDC 오류 정리

현재 확인된 문제:

- Planning Accepted Cache 414개가 원래 FULL Allowed Start Domain 밖에 있음
- Actual Known 연구정책의 QoS 사후 측정 초과 192개
- Actual 비영 AIDC 제어 미인증
- Pre-site/Migration 실제 실행 가능성 미검증

V44 r043의 수학적 Job 제약, Known/Unknown 정책, Source QoS와 연구용 Known 완화 정책을 정확히 구분한다.

Planning 414개는 캐시 수용만으로 FULL 가능해로 인정하지 않는다.

원래 FULL 모델의 허용 시작점·Job 도메인과 일치하도록 캐시 연결과 실제 A1 수용 로직을 수정·검증한다.

Actual 192개는 Known 연구정책에 의해 사후 측정된 항목이라는 사실을 유지하되 Source QoS 인증으로 간주하지 않는다.

## 3. 원본 AIDC 유연성 전체 검증

현재처럼 한 사이트당 단일 GPU Job 하나만 지연시키는 제한적인 Pilot에서 끝내지 않는다.

V44 r043의 기존 제어 영역을 실제로 복원한다.

- Time-shifting
- Pre-site
- Checkpoint Migration
- Multi-GPU Gang
- Site별 GPU Capacity
- GPUh 보존
- Window/Deadline/QoS
- WAN 및 Migration 시간
- Checkpoint/Restart
- Rack/Residency
- Actual 인과적 Job 도착
- Planning/Actual C1 전력 계산
- Rebound 및 Job Completion

Known와 Unknown을 각각 검증한다.

필요한 결과:

- 원래 Source 기준 제어 가능한 Job 수
- 실제 이동 가능한 GPUh
- 슬롯별 감소 가능 IT/Cooling kW
- 오전 슬롯31 제어 가능 전력
- 저녁 슬롯74 제어 가능 전력
- Time-shifting과 Migration별 가용량
- 실행 후 Rebound 및 Deadline 만족 여부
- 독립 FULL Job 검증

실제로 실행 가능한 비영 Actual AIDC Schedule을 확보하라.

하지만 원본 Source에서 허용하지 않는 Job 이동을 만들어내거나 QoS 제약을 완화해 비영 제어를 강제로 확보하지 않는다.

원본 Source에서 유연성이 부족하다면 원인을 수치로 증명하라.

그 경우 별도의 물리적으로 정당한 AIDC 확장 시나리오가 필요한지 판단하고, 원본 입력 실험과 구분한다.

---

# GATE 3. AIDC 위치 및 Scale 최종 검토

## 4. AIDC12 PCC 검증

현재 C2 배치를 무조건 최적 배치라고 간주하지 않는다.

각 AIDC 사이트에 대해:

- 기존 IEEE8500 MV 접속 가능성
- 정격 및 상 구성
- 주요 MV 병목과 전기적 경로 관계
- 슬롯31 및 슬롯74의 개별 민감도
- Time-shifting/Migration에 따른 선로 전류 변화
- 다른 AIDC 사이트와의 제어 중복성
- GPU 용량 및 목적지 수용 가능성
- 기존 24개 서비스 ID와 교통망 공간 관계
- 원본 위치의 상대 방향 및 공통 좌표 변환
- GIS·실제 도로 접근성의 미검증 항목

을 확인한다.

기존 C2 배치와 물리적으로 타당한 대체 PCC 후보를 비교할 수 있다.

다만 PCC를 성과가 좋아 보이도록 임의로 이동시켜서는 안 된다.

기존 SUMO 서비스 위치와 교통 입력을 유지하는 상태에서 전기적 접속 위치를 변경한다면, 두 위치의 대응관계와 거리·방향 오차를 명시한다.

정합성을 입증하지 못하면 현장에 설치 가능한 배치라고 주장하지 않는다.

### 5. AIDC Scale 검토

우선 원본 AIDC12/780GPU의 실제 유연량을 인증한다.

그다음 원본 Scale의 공동제어 기여 가능성이 충분한지 판단한다.

AIDC 소비전력 증가만으로 실제 Job 유연성이 증가하는 것은 아니다.

필요하면 별도 연구 시나리오로 AIDC 용량 확대를 검토한다.

후보 예시:

- 기존 규모 ×1.00
- 물리적 Capacity 확대 ×1.25
- 물리적 Capacity 확대 ×1.50
- 물리적 Capacity 확대 ×2.00

단, 확대 모델에서는 GPU 설치용량, IT Power, C1 Cooling, 실제 수행할 Job Workload, Deadline, Rack, WAN을 서로 일관되게 검증한다.

GPU/Job UID를 단순 복제하거나 AIDC 출력 kW만 곱해 결과를 만들지 않는다.

각 규모는 독립된 Scientific Scenario로 취급하고, 기존 780GPU 결과를 변경하지 않는다.

**AIDC 확대 후보는 B3 결과를 보고 선택하지 않는다.**

원본 780GPU에서 실제 비영 제어가 불가능하거나 부족하다면 그 사실을 먼저 보고하고, 확대가 필요한 근거를 명시한다.

---

# GATE 4. STA12 및 MESS8 초기 위치 검증

## 6. 현재 초기 위치 검토

기존 초기 위치:

- MESS01 → STA01
- MESS02 → STA12
- MESS03 → STA08
- MESS04 → STA06
- MESS05 → STA02
- MESS06 → STA03
- MESS07 → STA04
- MESS08 → STA05

기존 4대와 추가 4대의 선정 근거를 구분한다.

현재 추가 4대는 사전에 정한 STA 후보이지, 8대 전체의 제어력을 최적화한 초기 배치가 아니다.

### 반드시 평가할 사항

- STA12의 물리적 480V 접속 및 전용 750kVA 변압기
- 포트 PCS/P/Q/전류 정격
- STA별 동시 차량 점유 제약
- MESS8 초기 SOC 및 종단 SOC
- 실제 Route Table의 시작 위치·경로
- ETA/접속 지연/이동 에너지
- 하루 동안의 충전·방전·이동 가능성
- 슬롯31 및 슬롯74 전기적 제어 기여
- 차량별 P/Q 민감도
- 두 피크를 서로 다른 차량으로 제어할 수 있는지
- 8대의 제어 중복성과 에너지 분산
- 다른 STA에 도달하는 MOVE의 실질적 가치

현재 STA들의 Top-20 민감도 방향 유사도가 매우 높다는 점을 고려한다.

단순 Cosine Similarity만 아니라 민감도 크기, 시간대, 실제 하류 경로, 위상, P/Q, 제어 가능 시간 및 새로운 병목 전환을 함께 평가한다.

### 초기 위치 선정 규칙

현행 8대 초기 위치를 기준 사례로 유지한다.

대체 초기 배치가 필요하면 기존 STA12 내에서 물리적으로 유효한 조합을 사전 등록해 비교한다.

위치 선정에는 Planning 시점에 사용 가능한 데이터만 사용한다. 미래 Actual 피크나 B3 결과를 이용해 초기 위치를 사후 선택하지 않는다.

선정 후 8대의 초기 위치와 배터리 상태를 동결한다.

**STAY/MOVE를 강제하지 않는다.**

초기 위치는 고정된 운전 조건이고, 이후 실제 이동 경로는 원래 MESS 최적화기가 자유롭게 결정해야 한다.

기존 Route/ETA/이동 에너지 데이터는 변경하지 않는다.

---

# GATE 5. 두 피크를 동시에 제어하는 MESS 가능성 평가

## 7. 현재 개선량의 구조 분석

현재 S1_03/β2.00:

- B0: 75.710958%
- MESS 제한적 Pilot: 74.139349%
- 개선: 1.571609%p
- 원래 피크: 슬롯31
- 새로운 피크: 슬롯74

현재 Pilot에서는 오전 피크를 크게 낮췄으나 다른 시간대가 전역 최대값을 결정했다.

따라서 단일 피크의 순간 제어가 아니라 **96슬롯 전체 최대값을 줄이는 다시간대 운전 가능성**을 확인한다.

기존 목적함수:

`min max(line, phase, time) rho`

는 절대 변경하지 않는다.

### 검증 항목

- 오전 슬롯31 주변 피크
- 저녁 슬롯74 주변 피크
- 실제 Top-K 전역 피크 시간대
- 8대 차량별 방전 에너지 분할
- 차량별 P/Q 동시 운전
- 충전시간 분산
- Rebound
- 이동 에너지
- 종단 SOC
- 신규 병목 전환
- SVR Tap/Cap 동작에 따른 효과

원래 V44의 MESS 공동 MILP가 모든 차량의 시간·출력·이동을 최적화할 수 있도록 연결해야 한다.

제한적 Feasible Pilot은 알고리즘 이식 전 전기적 가능성 검증으로 사용하되, 별도 새로운 최적화 알고리즘으로 대체하지 않는다.

### MESS 대수

공식 연구 구성은 8대로 유지한다.

4대·6대·8대의 문제 규모 및 제어력 차이는 보조 분석할 수 있다.

10대·12대는 물리적 포트·초기 위치·SOC·Route 제약을 충족하는 경우에만 별도 Capacity Sensitivity Scenario로 검토한다.

차량을 더 추가해야 개선되는지, 8대의 기존 에너지와 시간 배분만으로 충분한지 구분한다.

특정 개선율을 강제로 달성하기 위해 대수를 늘리지 않는다.

---

# GATE 6. V44 r043 알고리즘 IEEE8500/MESS8 이식 완료

## 8. 원본 알고리즘 그대로 이식

기준:

`affc7226a519adbe072d7debbc3ae25ea71c3487`

기존 Source에 존재하는 다음 알고리즘을 그대로 포팅한다.

- A1
- M1
- A2
- M2
- K48
- Adaptive Beam Search
- Direct Joint MILP
- 원본 LB/UB/Global Gap
- 독립 FULL 검증기

차량4→8 확대, IEEE8500 계통 Adapter와 원래 시간축·PCC 연결에 필요한 변경만 허용한다.

원본 수학적 문제를 축소하거나 제약을 제거해서 빠르게 만드는 것은 금지한다.

Sparse 표현, Cache 및 불필요한 중복 계수 제거는 원본 FULL 동등성이 증명되는 경우에 한해 허용한다.

### A-stage

- 원본 Job 제약
- 진짜 FULL Feasibility
- 독립 Global LB
- 원래 Gap 기준
- Planning A1과 Actual 정책의 권한 분리
- A2에서 M1 결과의 정확한 수용
- Source QoS와 연구정책의 별도 인증

### M-stage

- MESS8 공동 변수
- 초기·종단 SOC
- 충전·방전 Mode
- P/Q/PCS16
- 12개 STA 점유 제약
- Route Flow 및 ETA
- 이동 에너지
- K48 독립 Global LB
- Beam Search 다중 차량 경로 탐색
- Direct Joint MILP
- Original FULL 독립 검증
- UB/LB/Gap
- 동일 96슬롯 전력망 제약

**8대 모두 각자의 MOVE/STAY 선택을 할 수 있어야 한다.**

하나의 차량만 이동하게 하거나 단독 이동 결과를 합쳐 공동최적화라고 주장하지 않는다.

### IEEE8500 Grid Adapter

- 원본 3,703개 선로
- 1,177개 Triplex
- Parent Terminal 목적함수
- 전체 양단 정격 안전검증
- 원본 NormalAmps
- 전압 0.95~1.05 pu
- 전체 변압기 정격
- SVR3 연구 설비 정격
- Actual TIME 및 Prefix
- Independent Fresh AC

를 모두 연결한다.

Planning과 Actual 물리 구성이 다른 경우 각 Stage의 실제 계통 모델과 실시간 운전 계약을 정확히 기록한다.

기존 IEEE123의 RegControl 개수를 IEEE8500에 강제로 복사하지 않는다.

### 모델 규모와 계산 자원

다음을 측정한다.

- Binary/Continuous 변수
- 전체 제약식
- Nonzero coefficient
- 모델 생성 시간
- Peak RAM
- K48 Root/Pricing 시간
- Joint MILP 준비 시간
- 예상 Native 시간 및 Budget
- 4대 대비 8대 증가 규모
- IEEE123 대비 IEEE8500 증가 규모

기존 V44 Native Budget과 Gap 정책은 보존한다.

성능 문제가 나타나더라도 목적함수를 변경하거나 Route 후보를 임의로 제거하지 않는다.

---

# GATE 7. 캠페인 직전 독립 검증

## 9. 날짜별 입력 및 실험 동결

우선 V44 r043과 비교 가능한 **2025년 5월 1~7일**을 공식 첫 캠페인 범위로 준비한다.

원본 May01은 이미 계통 및 Scale 선정에 사용됐으므로 미노출 검증일로 주장하지 않는다.

May02~07을 이용해 선택한 구성의 날짜 간 일반화와 물리적 적합성을 확인한다.

기존 Source가 허용하는 경우 May08~31의 후속 확장 준비도 별도 기록하되 첫 캠페인과 혼용하지 않는다.

각 날짜에서:

- Planning Forecast
- Actual Realized
- PV
- Weather
- AIDC Job
- GPU/C1
- SUMO Route
- 초기 MESS SOC/위치
- 전압제어 초기 상태
- Prefix24 및 평가96
- Source SHA
- QoS/Deadline
- FULL 입력 차원

을 검증한다.

선정한 Scale, PCC, STA, MESS8, SVR 및 정책은 모든 비교군에 공통 적용한다.

부적격 날짜가 나오면 결과에 맞춰 Scale/PCC를 재선정하지 않는다. 실패를 기록하고 별도의 사전 등록된 실험 변경으로 취급한다.

## 10. B0–B3 실행 경로 완성

다음 의존성을 구현한다.

- B0: REFERENCE → ACTUAL → FRESH
- B1: A1 → ACTUAL → FRESH
- B2: REFERENCE → K48_M1 → M1 → ACTUAL → FRESH
- B3: A1_REUSE → K48_M1 → M1 → A2 → K48_M2 → M2 → ACTUAL → FRESH

B3의 A1 재사용은 같은 날짜·동일 입력·동일 수용 해시에 한정한다.

다른 날짜·다른 실험 구성의 결과를 초기해나 수용 가능해로 임의 복사하지 않는다.

모든 Stage에서 실행 준비, 중간 실패, 재시작, Checkpoint, Budget, Source SHA 및 독립 검증기 연결을 준비한다.

## 11. 캠페인 전 Dry-run

공식 캠페인 실행 없이 다음을 완료한다.

1. 입력 및 Scenario Freeze SHA 검증
2. Grid/Job/MESS8 실제 Model Build
3. Native0 모델 차원 및 원본 FULL 동등성 검증
4. 테스트용 작은 Fixture에서 A1/M1/A2/M2 호출 경로 검증
5. 실제 IEEE8500 8대 Model Build의 RAM/시간 검증
6. Actual TIME/Fresh 독립 재생 검증
7. Checkpoint 및 Resume 경로 검증
8. 실패한 날짜가 이후 날짜를 중단시키지 않는 스케줄러 로직 검증
9. Worker/Thread/Budget/중복 실행 방지
10. Monitor 및 결과 집계 준비

필요한 경우 **격리된 단일 개발일의 짧은 Native Feasibility Smoke Test**만 수행할 수 있으나, 기존 실행 보호 정책과 명시적 실행 허가를 준수한다.

Smoke Test는 실제 장시간 A1/M1/A2/M2 최적화나 공식 캠페인 실행으로 간주하지 않는다. 짧은 테스트만으로 Global Gap 또는 FULL 최적화 성능을 인증하지 않는다.

장시간 Native Solver, 공식 B0/B1/B2/B3 캠페인 및 월간 Worker는 실행하지 않는다.

---

# 최종 동결 및 제출

## 12. 필수 산출물

모든 결과를 기존 PR #236에 추가한다.

최소 다음을 제출하라.

- `FINAL_ELECTRICAL_PRESTART_CERTIFICATION.json`
- `SVR3_PREFIX_AND_TIME_SECURITY_KO.md`
- `AIDC_SOURCE_QOS_AND_FLEXIBILITY_KO.md`
- `AIDC12_PCC_LOCATION_AUDIT.csv`
- `AIDC_CAPACITY_SCENARIO_REVIEW_KO.md`
- `STA12_LOCATION_AND_ELECTRICAL_RESPONSE.csv`
- `MESS8_INITIAL_SITE_SELECTION_KO.md`
- `MESS8_ROUTE_SOC_PQ_PORT_CERTIFICATION.json`
- `TWO_PEAK_CONTROLLABILITY_ANALYSIS.csv`
- `IEEE8500_V44_R043_FULL_EQUIVALENCE.json`
- `MESS8_NATIVE0_BUILD_REPORT.json`
- `MAY01_07_PRESTART_INPUT_MANIFEST.json`
- `B0_B1_B2_B3_STAGE_WIRING_CERTIFICATION.json`
- `CAMPAIGN_EXECUTION_HOLD.json`
- `FINAL_PRESTART_REVIEW_KO.md`
- `FINAL_PRESTART_GO_NO_GO.json`

### 최종 보고에서 반드시 답할 질문

1. 추가 SVR3으로 Prefix 및 모든 필요한 시간대의 전압을 인증했는가?
2. 최종 Background β는 얼마이고 모든 날짜에서 안전한가?
3. AIDC 원본 780GPU의 실제 실행 가능한 유연전력은 얼마인가?
4. AIDC Capacity 확대가 필요한가? 필요하다면 물리적 근거는 무엇인가?
5. AIDC12/STA12의 기존 C2 위치는 연구 목적과 교통망에 적합한가?
6. MESS8의 초기 위치는 그대로 유지하는 것이 적합한가?
7. MESS8이 오전·저녁 피크를 동시에 낮출 제어 가능성이 있는가?
8. 8대의 P/Q/SOC/MOVE/STAY 제약이 원본과 정확히 일치하는가?
9. A1–M1–A2–M2 및 K48/Beam/Joint MILP 이식을 완료했는가?
10. Original FULL 검증기와 UB/LB/Gap 계약이 정상인가?
11. May01~07의 모든 데이터·입력·실행 환경이 준비됐는가?
12. 공식 캠페인을 시작하기 전 남은 차단 사유가 있는가?

## 13. 최종 상태 판정

모든 필수 계약 및 사전 검증이 충족되면:

`READY_FOR_USER_CAMPAIGN_APPROVAL`

로 기록한다.

하나라도 미완료라면:

`PRESTART_BLOCKED_WITH_EVIDENCE`

로 기록하고 차단 항목별 근거를 제시한다.

코드가 컴파일되거나 단순 Fixture 테스트가 통과했다는 이유만으로 READY로 표시하지 않는다.

실제 Native 전체 성능을 검증하지 못한 항목은 별도 미인증 상태를 유지한다.

**READY여도 캠페인을 자동 실행하지 않는다.**

캠페인 실행 명령, Runtime 경로, 예상 예산, Worker 설정 및 시작 전 확인 절차만 준비하고 실행 허가를 기다리는 상태로 종료한다.

기존 V44/V1_add/IEEE8500 과거 연구와 실행 중 Worker를 보호한다.

모든 수정과 검증 결과를 동일 Draft PR #236에 커밋·Push하고, 한국어 최종 Prestart 보고서를 제출하라.