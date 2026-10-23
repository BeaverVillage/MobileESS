IEEE8500 Source-YY Static Complete M1에서 중단되어 있던 V44 r043 A1–M1–A2–M2와 K48/Adaptive Beam/Direct Joint, Actual/Fresh 실행 경로를 같은 V2_add May01 Case에 연결했다. 현재 판정은 `READY_FOR_MAY01_CAMPAIGN_APPROVAL`이며 공식 캠페인은 실행하지 않았다. Draft를 유지한다.

### 구현 및 실제 검증

- 원본 알고리즘 파일을 수정하지 않고 Stage Adapter, 실제 Handler, 입력/결과 SHA 전달, 독립 FULL 검증기, Checkpoint/Resume와 Worker 잠금을 연결했다. 기존 Static Complete M1 1,740,213행·51,158,488 Nonzero 및 과거 증거를 보존했다.
- A1/A2는 원본 canonical active kernel 및 117개 전체 로컬 Pricing 블록 Native0, 전체 가변 AIDC 계통 연결을 검사했다. M2는 비영 유한 A2 Witness의 새 C1/RHS/Bound/정적 제거 증명으로 Native0와 독립 FULL 복원을 통과했다. Witness를 최적화 결과로 취급하지 않는다.
- K16/K32/K48은 전체 96슬롯 Helper·정확 산술·원본 Pricing 인터페이스와 실제 Gurobi Native0 행렬 Readback을 통과했다. 실제 Production K48→M1 Handler도 원본 Adaptive Beam 점수 LP 호출 직전까지 도달했다.
- Beam은 8대 각각 STAY 1개/MOVE 12개(다중 MOVE 8개)를 생성했다. Direct Joint Native0는 1,740,221행·1,011,235열·49,178,740 Nonzero이며 실제 전체 행렬 CSR·RHS·Sense·경계·형·목적함수가 원본 패킷과 일치했다. 총 238.982초, Peak RSS 3.597GiB. 점수 LP를 풀거나 유한 검증 풀을 공식 채택 풀로 승격하지 않았다.
- 실제 B0 Handler의 2,498개 Actual Job과 Carryout/GPUh/C1, 별도 B1/B3 Migration·WAN Fixture, 새 TIME 엔진 두 개의 Actual120/Fresh를 검증했다. Fresh의 전압·선로·변압기 배열 최대 오차는 0이고 Tap/Cap/Queue도 일치했다.
- 원본 Budget/Gap/Thread와 실제 재개 산술, 입력·결과 변조 거부, 중복 Worker 거부, 유한 M1 Fixture의 Production A2 유입 거부를 확인했다. Gurobi optimize/presolve 및 HiGHS solve는 0회다.

### 물리 구성 및 결과 범위

Source-YY, β_BG=2.00, Actual SVR3, GPU780, AIDC12/STA12, MESS8과 기존 3,703개 선로/1,177개 Triplex 및 전체 Parent Terminal 최대 선로부하율 목적함수를 유지한다. B0 평가96 전체/MV 최대는 75.711008%, LV는 46.810643%, 차이는 28.900365pp이며 전압은 0.951568~1.040377pu다. 원본 최종 TIME 틱을 공식 전압 기준으로 적용하고 Prefix의 저전압 23초/과전압 18초 등 이벤트 기록은 보존한다. 최적화된 B1/B2/B3의 물리 결과·수치 LB/UB/Gap은 아직 계산하지 않았다.

입력 계약 차이를 명시한다. r043 `physical_starts`가 입력 WINDOW 밖에 허용하던 121,313개 시작 선택(1,395개 Job)을 Adapter에서 원본 유한 WINDOW와 교차 제한했다. 원본 Phase-I/P1/Pricing/정수 수용 코드와 파일은 보존하지만 더 넓던 시작 도메인과 수학적으로 동일하다고 주장하지 않는다. Source 의도적 QoS 예산과 연구용 Known 정책을 구분하며 고객 SLA 인증은 주장하지 않는다.

### 공식 캠페인 메모리 정책 및 HOLD

사용자 지시에 따라 공식 캠페인의 RSS 한도, 가용 RAM 예약, 메모리 대기·거부·중단을 제거했다. 메모리는 측정만 한다. Gurobi `MemLimit`/`SoftMemLimit`는 양의 Infinity이며, 이전의 잘못된 `0=무제한` 주장은 철회했다. Native0 준비의 4GiB/가용 5GiB 보호는 유지한다. 원본 A 5,400초/Gap0.005, K48 300초, Joint 900초/단일 300초, M Gap0.03, Worker1/A Threads1/M Threads4는 보존했다.

준비 명령은 `python -m v2_add_preflight.stage_campaign plan`이다. 공식 실행은 별도 사용자 승인과 최종 인증 SHA가 일치해야 가능하며 이번 작업에서는 실행하지 않았다. `SCIENTIFIC_SIMULATION_READY=true`, `FIELD_INSTALLATION_UNVERIFIED=true`를 구분한다. V44/V1_add 및 May02~07 소스·원장·캠페인은 변경하지 않았다.

상세 근거: `docs/v2_add/static_complete/FINAL_STAGE_INTEGRATION_REVIEW_KO.md`, `FINAL_MAY01_PRESTART_GO_NO_GO.json`, `FINAL_STAGE_EVIDENCE_SEAL.json`.
