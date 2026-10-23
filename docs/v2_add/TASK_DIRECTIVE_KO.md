# Codex 작업 지시 — V2_add: IEEE8500 Balanced 기반 V44 r043 확장성 실험 및 제어 민감도 중심 부하 스케일 선정

## 0. 연구 목표

GitHub 저장소: `BeaverVillage/MobileESS`

새로운 독립 확장실험 **V2_add**를 시작한다.

이번 실험은 기존 V44 r043의 AIDC–MESS 공동최적화 알고리즘을 IEEE8500 공식 Balanced 배전계통으로 확장하는 것이다.

**최종 구성**

- 배전계통: IEEE8500 공식 Balanced 모델
- AIDC: 12곳 유지
- STA: 12곳 유지
- MESS: 8대
- 교통망: 기존 V44 r043 SUMO 및 Route Table 유지
- Job/GPU/QoS/ML: V44 r043 동결 입력 및 모델 유지
- 최적화: 기존 A1–M1–A2–M2, K48, Adaptive Beam Search, Direct Joint MILP 유지
- 목적함수: 전체 선로·상·시간의 전역 최대 선로부하율 최소화

**이번 실험에서는 배경부하 Scaling만 예외적으로 허용한다.**

그 목적은 B0 최대 선로부하율을 적절한 수준으로 높이면서도 AIDC12·MESS8의 실제 제어 가능성을 충분히 확보하는 것이다.

중요한 점은 B0/B1/B2/B3 결과의 차이를 인위적으로 만들어내는 것이 아니라, 사전에 정한 물리적 조건과 민감도 기준으로 연구 시나리오를 선정하고 동일 조건에서 네 비교군을 공정하게 평가하는 것이다.

---

## 1. 기존 소스와 독립성

### 1.1 기준 자료

다음 결과를 읽기 전용으로 조사한다.

- V44 r043 기준 SHA: `affc7226a519adbe072d7debbc3ae25ea71c3487`
- PR #197: IEEE8500 공식 Balanced / Unbalanced 비교
- PR #199: IEEE8500 공동 PCC 배치 및 B0·MESS 제어 실험
- PR #200: IEEE8500 기존 최적화 엔진 이식 준비
- PR #235: V1_add 입력 계보 및 V44 r043 원본 입력 복원

PR #197의 Balanced 계통 구조와 정격 검증을 우선 활용한다.

PR #199의 연구 구성은 참고할 수 있지만, 6대 MESS와 차량당 450 kW/600 kVA 등 **V44 r043과 다른 차량 정격이나 정책을 그대로 가져오지 않는다.**

PR #200은 정적 형상 검증만 완료됐으므로 실제 알고리즘 통합이 인증됐다고 가정하지 않는다.

### 1.2 독립성

V2_add의 Branch, Worktree, Runtime, Source, 결과 원장 및 보고서를 별도로 생성한다.

- 기존 V44 Production 변경 금지
- 기존 V1_add Greensboro 결과 변경 금지
- 기존 IEEE8500 PR #193~#200 결과 변경 금지
- 기존 Worker/PID/Native Budget/Monitor/Checkpoint 변경 금지
- 기존 캠페인의 실행 상태와 자원 사용을 먼저 확인
- GitHub 독립 Draft PR 생성

V2_add 결과를 V44 공식 캠페인 결과에 병합하지 않는다.

---

## 2. 기존 V44 알고리즘 동결

다음 사항은 절대 변경하지 않는다.

### AIDC

- AIDC01~AIDC12
- 원본 설치 GPU 780개 및 사이트별 GPU 용량
- 기존 Kestrel Job UID와 Known/Unknown 구분
- GPUh 보존
- Runtime V10 및 CC4 기존 정책
- IT Power와 C1 Cooling 모델
- Time-shifting, Migration, Pre-site 허용 조건
- QoS, Window, Deadline, Rack 및 WAN 제약
- 원본 A1/A2 정식화 및 알고리즘

### MESS

차량만 4대에서 8대로 확장한다.

차량별 기존 V44 r043 물리 조건을 유지한다.

- P 최대: ±300 kW의 기존 충전·방전 정책
- Q 한계: ±250 kvar
- PCS: 400 kVA
- 기존 P/Q 동시 운전 제약
- 기존 SOC 상·하한, 초기·종단 SOC 정책
- 기존 충전·방전 효율
- 기존 이동 에너지 및 ETA
- 기존 이산 Route/Mode/SOC 제약
- K48, Beam Search, Joint MILP 및 검증 방식

추가 4대에도 동일 차량 모델을 적용한다.

초기 위치는 실제 STA12 중 물리적으로 적합한 위치를 사전에 선정하고, 해당 위치와 기존 Route Table의 연결을 인증한다.

**STAY/MOVE를 강제로 결정하지 않는다. 실제 이동 여부는 기존 최적화기가 결정해야 한다.**

### 비교군

원본 V44 Stage Chain을 그대로 유지한다.

- B0: REFERENCE → ACTUAL → FRESH
- B1: A1 → ACTUAL → FRESH
- B2: REFERENCE → K48_M1 → M1 → ACTUAL → FRESH
- B3: A1_REUSE → K48_M1 → M1 → A2 → K48_M2 → M2 → ACTUAL → FRESH

A1/A2와 M1/M2의 원래 Gap, Runtime, 독립 FULL 검증 및 LB/UB 인증 기준을 유지한다.

목적함수도 변경하지 않는다.

`min max_{t, line, phase} (abs(I_line_phase_t) / original_NormalAmps_line)`

**모든 원본 IEEE8500 선로를 목적함수와 물리 검증에 포함한다.**

저압 Triplex 선로를 제외하거나 정격을 변경하지 않는다.

---

# PART A. IEEE8500 Balanced 모델 준비

## 3. 공식 Balanced 모델 복원

PR #197을 우선 참고해 실제 공식 IEEE8500 Balanced Master/Loads를 확인한다.

다음을 검증한다.

- Electrical Nodes: 기존 연구 기준 8,531
- 전체 선로: 3,703
- Triplex 선로: 1,177
- 변압기: 1,190
- 원본 LineCode, 임피던스 및 정격
- 원본 각 상 및 전압 계급
- RegControl/CapControl
- 고객별 부하·PV 연결 모델

실제 OpenDSS에서 재측정하여 확정하고 PR #197과 SHA 및 물리 모델을 비교하라.

Balanced 모델은 공식 고객 부하 연결 모델로 사용한다.

이것은 V2_add의 사전 고정된 연구 가정이며, MESS가 고객 상을 동적으로 변환했다는 의미가 아니다.

원본 Unbalanced 모델과 결과를 혼동하지 않는다.

## 4. V44 r043 입력 연결

V44 r043 May01~07의 기존 데이터를 복원한다.

V1_add에서 검증된 May01 동결 입력 배열과 Source Authority를 재사용할 수 있다.

각 날짜의 실제 권위 파일은 다시 SHA 검증한다.

- Planning Forecast 배경 P/Q
- Actual Realized 배경 P/Q
- Rooftop PV P/Q
- 실제 날씨
- AIDC12 사이트별 P/Q
- 기존 FCFS Job 및 Optimized Job 입력
- 기존 SUMO Route/ETA/이동 에너지
- 24 Prefix 및 96 평가 슬롯
- D-1 정보제약

IEEE8500의 원본 고객 부하 정보는 공간 배분과 공식 Balanced 상별 연결 규칙에 사용한다.

V44 r043의 시간별 입력을 연결할 때 버스별 전력수지와 고객별 P/Q 배분을 검증한다.

기존 V44의 `alpha_BG=1.15` 등 정규화가 이미 적용된 최종 전력 배열을 기준으로 한다. 해당 계수를 중복 적용하지 않는다.

PR #197의 `BG=0.552` 또는 PR #199의 `BG=0.85`를 V44의 신규 Scale과 동일한 의미의 계수로 가정하지 않는다.

---

# PART B. 배경부하 스케일 선정

## 5. Scaling 원칙

이번 V2_add에서는 **배경부하 P/Q에만 추가 Stress Scale을 적용**한다.

추가 계수는 `beta_BG`로 정의한다.

각 슬롯에서:

`P_BG_V2(t) = beta_BG × P_BG_V44_frozen(t)`

`Q_BG_V2(t) = beta_BG × Q_BG_V44_frozen(t)`

다음은 Scaling하지 않는다.

- AIDC12의 GPU와 Job
- AIDC IT 및 Cooling 전력 모델
- PV P/Q
- MESS 대수 외 차량별 용량
- MESS PCS/P/Q/SOC
- 도로망, 이동시간 및 이동 에너지
- 기존 선로·변압기 정격

Planning과 Actual에는 동일한 `beta_BG`를 적용하되 서로의 원본 Forecast/Realized 입력을 섞지 않는다.

즉, 계수는 같아도 Planning과 Actual의 전력 시계열은 서로 다르다.

`beta_BG != 1`인 결과는 **V44에서 유도한 부하 Stress Scenario**로 명시한다. V44와 총 배경부하가 완전히 동일한 실험이라고 주장하지 않는다.

## 6. Scale 후보 탐색

먼저 `beta_BG=1.00`을 정확한 기준 사례로 계산한다.

이후 다음 후보를 사전 등록한다.

`beta_BG = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50]`

우선 1.00~1.30 범위에서 탐색한다.

필요하면 1.40, 1.50을 추가 Stress 후보로 확인한다.

허용 범위 안에 적합한 시나리오가 없으면 무조건 더 큰 배율로 확장하지 말고 필요한 배율의 추정치, 물리적 문제 및 연구 한계를 보고한다.

**B1/B2/B3 최적화 성과를 보고 Scale 후보를 추가하거나 선택 기준을 변경하지 않는다.**

## 7. B0 최대 선로부하율 목표

우선 목표:

`75% <= rho_max_B0_Actual <= 85%`

후보가 없다면:

`70% <= rho_max_B0_Actual <= 85%`

범위까지 검토한다.

목표는 연구에 적합한 운전점을 찾기 위한 사전 시나리오 기준이며, 이를 맞추기 위해 원본 정격이나 계통 입력을 임의 조작하지 않는다.

모든 후보에서 다음을 확인한다.

- Planning 96슬롯 Fresh AC
- Actual 24 Prefix + 96슬롯 Fresh AC
- 전압 0.95~1.05 pu
- 모든 선로 정격
- 모든 변압기 정격
- OpenDSS 수렴
- Native Tap/Capacitor 동작
- 원본 전력수지
- AIDC/STA PCC 정격

모든 비교군에 동일한 계통과 하드웨어 설정을 사용한다.

기존 IEEE8500 연구의 P5 전압제어 설정은 고정된 사전 참고 구성으로 검토할 수 있지만, Source/Vreg/Capacitor를 Scale별로 재조정해서 성과를 높이지 않는다. V44 Planning/Actual 물리 계약과의 차이는 별도로 검증한다.

---

# PART C. 가장 중요한 MV/LV 최대 부하율 민감도

## 8. 전압 계급별 최대 부하율

각 후보 Scale의 96슬롯에서 다음 세 지표를 모두 계산한다.

`rho_MV_max = max over all MV primary line-phase/time`

`rho_LV_max = max over all original LV/Triplex line-phase/time`

`rho_global_max = max over all original line-phase/time`

또한 슬롯별:

`H_MV_LV(t) = rho_MV_max(t) - rho_LV_max(t)`

일별:

`H_daily = rho_MV_max - rho_LV_max`

를 계산한다.

PR #197 Balanced Actual에서는:

- MV 최대: 57.0975%
- Triplex 최대: 46.7036%
- 최대값 차이: 약 10.39%p

였다.

하지만 이는 기존 PR #197 조건의 결과이므로 V2_add에서도 같은 차이가 발생한다고 가정하지 않는다.

### 중요한 선정 조건

B0 전체 최대값이 75~85%여도 LV 선로가 바로 새로운 병목이 된다면 적절하지 않다.

따라서 다음도 확인한다.

1. 최대 부하율을 결정하는 선로가 MV인지 LV인지
2. 일별 MV/LV 최대값의 차이
3. B0 최상위 혼잡 시간대의 슬롯별 MV/LV 차이
4. Top-20 선로들의 전압 계급
5. 전역 최대값이 다른 선로로 전환되는 조건
6. 저압 Triplex에서 제어 불가능한 부하율 Floor가 있는지

연구용 우선 선정 기준으로 **일별 MV 최대와 LV 최대 사이 5%p 이상의 여유**를 선호한다.

그러나 이 값만으로 판정하지 않는다. 제어한 뒤 새로운 LV 또는 MV 병목으로 넘어가는지도 검증해야 한다.

## 9. Top-K 병목의 전기적 제어 가능성

현재 B0 전역 최대 부하율을 결정하는 선로와 가까운 혼잡 선로들을 대상으로:

- 상류/하류 PCC
- MV/LV 전압 계급
- AIDC12의 전기적 영향
- STA12의 전기적 영향
- MESS P/Q의 상별 영향
- 3상 자원과 단상 병목의 결합
- 여러 자원이 동일한 선로만 제어하는 중복성
- 다른 분기의 새로운 병목 전환

을 분석한다.

한 선로의 로딩 감소가 아니라 전체 선로 최대값 감소를 측정한다.

`rho_global_max`는 비미분적 Max 함수이므로 단일 선로의 국부 선형 민감도만으로 최종 제어 가능성을 판정하지 않는다.

---

# PART D. AIDC12 및 MESS8의 실제 제어력

## 10. PCC 선정

AIDC12/STA12는 항상 유지한다.

기존 V44 교통망 서비스 ID와 Route Table은 절대 수정하지 않는다.

PR #199의 C2 공동 PCC 배치를 우선 참고하되, 해당 배치와 전용 포트 하드웨어가 V44 MESS8의 P300/Q250/PCS400 조건을 만족하는지 새로 검증한다.

PR #199의 6대 MESS 450 kW 모델을 그대로 사용하지 않는다.

또한 기존 위치 관계, 24개 서비스 ID, 교통망 연결, STA 접근 가능성을 검증한다.

**PCC와 Scale을 동시에 임의로 계속 조정하여 B3 개선이 큰 조합만 선택하는 방식은 금지한다.**

먼저 물리적으로 타당한 PCC를 사전 고정하고, 그 PCC에서 Scale을 탐색하는 것을 기본 원칙으로 한다.

물리적 PCC가 불가능한 경우에만 실패 원인을 남기고 사전에 정의된 대체 후보를 조사한다.

## 11. AIDC 제어력

AIDC12의 순간 총 소비전력이 아니라, 실제로 스케줄을 변경할 수 있는 유효전력을 계산하라.

확인할 항목:

- Time-shifting 가능 Job
- Migration 가능 Job
- Pre-site 가능 Job
- 실제 GPUh 보존
- QoS/Deadline/WAN
- 각 사이트 GPU 용량
- 병목 시간대에 감소·이전 가능한 kW
- 이동 후 다른 시간/사이트에서 증가하는 Rebound

AIDC가 최적화 대상이더라도 실제로 이동 가능한 Job이 거의 없다면 AIDC 효과가 작다는 것을 명확히 보고한다.

Job 수, GPU 수, Deadline, Flexibility Mask를 인위적으로 늘리지 않는다.

특히 B0 피크 시간대에 실제 제어 가능한 AIDC 전력량과 상별 선로 민감도를 함께 기록한다.

## 12. MESS8 제어력

MESS 8대에 대해 다음을 확인한다.

- 차량별 P/Q/PCS 운전영역
- 충전/방전 효율
- 초기 및 종단 SOC
- 실제 이동 경로와 ETA
- 충전 Rebound
- 각 STA의 전력 수용 가능성
- 8대의 동시 운전 가능성
- 병목 시간대에 공급 가능한 실제 P/Q
- 여러 차량의 민감도 중복

순간 정격 합계 2.4 MW를 실제 96슬롯 운전 가능량으로 간주하지 않는다.

새로운 MESS 제어 알고리즘을 개발하지 말고, 기존 물리 제약을 만족하는 제한된 진단용 운전 후보로 전역 부하율 변화만 검증한다.

## 13. 민감도 기반 Preflight

선정 후보에서 다음을 비교한다.

- AIDC-only의 실현 가능한 제어
- MESS-only의 실현 가능한 제어
- AIDC+MESS의 실현 가능한 공동 제어

소규모 P/Q 교란과 실제 허용 운전영역 내의 유한 AC 응답을 구분한다.

Planning/Actual 각각에서 실제 전역 최대 부하율을 측정하고, 무제어 재계산의 수치적 노이즈와 Tap/Capacitor 불연속을 기록한다.

가능하면 96슬롯 전체에서 SOC·Route·Job·Rebound 제약을 만족하는 Feasible Pilot을 구성한다.

이 Pilot은 사전 제어 가능성 조사일 뿐이며 B1/B2/B3의 실제 최적화 성과가 아니다.

### 제어력 선정 목표

실제로 운전 가능한 공동 제어 Pilot을 통해 **전역 최대 선로부하율 1%p 이상 감소**가 관측되는 후보를 우선 선호한다.

2%p 이상의 감소가 가능하면 높은 제어력을 가진 후보로 별도 기록한다.

이는 사전 연구 목표이지 보장된 결과나 보편적 학술 기준이 아니다.

실제 Pilot에서 1%p 미만만 관측돼도 원인과 최적화 단계의 추가 가능성을 분석한다. 허위 제어량을 추가하거나 원본 정격·Job 제약을 완화하지 않는다.

---

# PART E. 최종 Scale 선정 규칙

## 14. B0 및 민감도만으로 선정

Scale 선정은 다음 순서로 수행한다.

1. 원본 입력·물리 모델 검증 PASS
2. 96슬롯 전압·선로·변압기 제약 PASS
3. B0 Actual 최대 선로부하율 75~85% 우선
4. 적합한 후보가 없으면 70~85% 검토
5. MV 병목과 LV 병목 사이 충분한 여유
6. AIDC/MESS의 실제 접근 가능한 PCC 확인
7. 물리적으로 실행 가능한 전역 부하율 개선 가능성
8. 과도한 Background Scaling보다 작은 배율 우선

후보마다 별도의 결과를 저장하고 실패 후보도 보존한다.

전역 B0–B3 비교 결과는 Scale 선정에 사용하지 않는다.

동일 우선순위 후보가 복수라면 사전 기록된 결정 규칙으로 하나의 Primary Scenario를 선정한다.

이후:

- `beta_BG` 동결
- PCC24 Mapping 동결
- MESS8 초기 위치 동결
- 계통/하드웨어 동결
- 입력 SHA 동결

하고 B0/B1/B2/B3 수행 중 변경하지 않는다.

적합한 후보가 없으면 `NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO`로 보고하고, 스케일 또는 알고리즘을 무단 조정하지 않는다.

---

# PART F. V44 r043 알고리즘 이식

## 15. 동일 알고리즘의 8대 확장

Scale/PCC/물리 Gate를 통과한 뒤 기존 V44 r043 알고리즘을 IEEE8500에 이식한다.

알고리즘 자체를 재설계하지 않는다.

필요한 변경은 다음에 한정한다.

- IEEE8500 계통 Adapter
- 원본 IEEE8500 선로/전압/변압기 제약 연결
- PCC 전기적 Mapping
- 원본 4대 → 8대 차량 차원 확장
- 전압·전류 민감도 생성
- 8대 MESS Route/SOC/Mode/PQ 변수와 검증기 차원
- 새로운 계통에 필요한 하드웨어 적용 계층

기존 K48, Beam Search, Direct Joint MILP, A1/A2 정식화, LB/UB, FULL 검증, Solver Budget/Gap 정책은 동일하게 유지한다.

K48/RMP/Price 모델과 원본 FULL 제약의 관계를 재검증한다.

IEEE123 전용으로 하드코딩된 Node, Branch, RegControl, Transformer 축을 그대로 사용하지 않는다.

수학적으로 동일한 Sparse 표현이나 행렬 생성 최적화는 가능하지만, 원본 FULL 목적함수 및 제약식의 동등성을 검증해야 한다.

### 규모 검증

다음을 산출한다.

- 변수 수
- Binary/Continuous 변수 수
- 제약식 수
- Nonzero coefficient 수
- Native 모델 생성 시간
- Peak RAM
- K48 시간
- Joint MILP 시간
- UB/LB/Gap
- AC/Actual/Fresh 검증 시간

IEEE123의 4대 결과와 IEEE8500의 8대 결과를 비교할 때 계통 규모 증가와 차량 증가가 동시에 발생한다는 사실을 명시한다.

필요하면 IEEE8500 4대의 보조 규모 분석을 추가하되, 공식 MESS8 연구 구성을 변경하지 않는다.

---

# PART G. B0/B1/B2/B3 최종 비교

## 16. 동일 조건에서 네 비교군 실행

Preflight 통과 및 독립 실행 자원·허가 조건 충족 후, 동결한 단일 Primary Scenario로 B0/B1/B2/B3를 평가한다.

우선 May01 단일일의 전체 알고리즘 및 Actual/Fresh 검증을 확인한 뒤 May01~07 확대를 수행한다.

기존 V44 Production과 충돌하는 장시간 Native 실행은 금지한다. 별도 작업 실행 허가가 필요한 경우 기존 보호 Gate를 우회하지 않는다.

모든 비교군에서 반드시 동일하게 유지한다.

- Background Scale
- PV
- AIDC/STA 위치
- MESS8 및 차량 정격
- Job 입력
- 교통망
- 전압제어 하드웨어
- 선로·변압기 정격
- 목적함수
- Actual Realized 입력

## 17. 비교군 간 개선량

다음을 모두 산출한다.

- B0 → B1
- B0 → B2
- B0 → B3
- B1 → B3
- B2 → B3

각 비교에서:

- Planning 최대 선로부하율
- Actual 최대 선로부하율
- MV 최대 선로부하율
- LV 최대 선로부하율
- 전체 최대값을 결정한 선로 및 상
- 전압 최소/최대
- 변압기 최대 부하율
- Job 실행량 및 QoS
- MESS SOC/이동/P/Q
- 계산시간
- UB/LB/Global Gap

을 기록한다.

특히 연구 목표는 **B3의 공동 제어가 실제로 유의미한 추가 개선을 보이는지 확인하는 것**이다.

하지만 B3가 B1/B2보다 반드시 좋도록 값을 조작하지 않는다.

차이가 작으면 다음 중 실제 원인을 분석한다.

- 실제 Job 유연성 부족
- STA 전력 정격 부족
- MESS 에너지/SOC 제약
- 제어 가능한 선로와 병목의 전기적 분리
- MV→LV 병목 전환
- MESS 간 민감도 중복
- 알고리즘의 UB 개선 부족
- Gap 또는 시간 제한

관측된 결과와 이론적 제어 가능성을 반드시 구분한다.

---

# PART H. 최종 산출물

## 18. 필수 보고서

모든 문서와 결과는 V2_add 전용 경로에 저장한다.

다음 파일을 생성한다.

1. `V2_ADD_EXPERIMENT_IDENTITY.json`
2. `IEEE8500_BALANCED_SOURCE_AUDIT.md`
3. `V44_R043_INPUT_BINDING_AUDIT.json`
4. `BACKGROUND_SCALE_PREREGISTRATION.json`
5. `BACKGROUND_SCALE_SCREENING.csv`
6. `MV_LV_LOADING_COMPARISON.csv`
7. `TOP20_GLOBAL_CRITICAL_LINES.csv`
8. `AIDC12_STA12_PCC_MAPPING.csv`
9. `MESS8_INITIAL_STATES_AND_PORTS.json`
10. `AIDC_MESS_SENSITIVITY.csv`
11. `FEASIBLE_96SLOT_CONTROL_PILOT.csv`
12. `SELECTED_SCENARIO_FREEZE.json`
13. `V44_TO_IEEE8500_8MESS_PORT_AUDIT.md`
14. `B0_B1_B2_B3_COMPARISON.csv`
15. `FINAL_V2_ADD_REVIEW_KO.md`
16. `FINAL_GO_NO_GO.json`

없는 결과를 임의로 채우지 말고 NOT_VERIFIED와 실패 사유를 기록한다.

### 그림

Python/SVG로 생성한다.

- IEEE8500 Balanced 전체 토폴로지
- AIDC12+STA12 위치
- MV/LV 선로별 히트맵
- Scale별 MV/LV 최대 선로부하율
- Scale별 전역 제어 민감도
- Top-K 병목 선로 및 PCC의 전기적 위치
- B0/B1/B2/B3 시간별 최대 선로부하율
- B0/B1/B2/B3의 평균 및 일별 최대 선로부하율

이미지 생성 AI는 사용하지 않는다.

---

## 19. 최종 보고에서 답해야 할 질문

한국어로 다음 질문에 수치와 물리적 근거를 들어 답하라.

1. 기존 V44 r043 입력을 IEEE8500 Balanced에 어떻게 적용했는가?
2. `beta_BG=1.0`의 B0 최대 선로부하율은 얼마인가?
3. 최종 선정한 `beta_BG`는 얼마이고, 선정 근거는 무엇인가?
4. B0 최대 부하율 75~85% 목표를 달성했는가?
5. MV와 LV 최대 부하율 차이는 몇 %p인가?
6. 병목 선로의 하류에 실제 제어 가능한 AIDC·MESS가 존재하는가?
7. 기존 AIDC12의 실제 Job 유연량은 얼마인가?
8. MESS8이 이동·SOC·PCS 제약 내에서 제어할 수 있는 전력은 얼마인가?
9. 실제 가능한 96슬롯 제어 Pilot의 전역 최대 부하율 감소는 얼마인가?
10. B0/B1/B2/B3 사이의 실제 최대 부하율 차이는 얼마인가?
11. B3에서 AIDC–MESS 공동최적화의 추가 효과가 확인됐는가?
12. IEEE123 대비 계산시간·문제 크기·최적성 Gap은 어떻게 달라졌는가?

### 절대 금지

- LV 선로를 목적함수에서 제거
- 원본 선로 정격 변경
- GPU/Job/Deadline 임의 변경
- MESS8을 기존 6대 450 kW 모델로 대체
- 기존 SUMO 경로 또는 ETA 재생성
- B3 결과에 맞춘 Scale 재선정
- B0/B1/B2/B3별 다른 배경부하 사용
- 비교군 차이가 커 보이도록 숫자 보정
- 실패한 물리 검증 숨기기
- 기존 V44 또는 V1_add 캠페인 변경
- AC Pilot 결과를 최적화 성과로 표시

**최종 연구 목표**

"IEEE8500 공식 Balanced 배전계통에서 전체 원본 선로를 그대로 포함한 전역 최대 선로부하율 목적함수를 유지하면서, 적절한 배경부하 수준과 실제 AIDC12·MESS8 제어력을 확보하고, V44 r043의 동일 공동최적화 알고리즘이 대규모 계통에서도 의미 있는 선로 혼잡 완화 효과를 보이는지 검증한다."

먼저 Scale–MV/LV 병목–PCC 제어 민감도 Preflight를 완료하고, 그 결과에 근거해 시나리오를 동결한 뒤 알고리즘 이식 및 비교군 검증으로 진행하라.

진행 상태와 차단 원인을 독립 Draft PR에 기록한다.