# V42 공통 A/M·QoS·Job Actual 연구 정책

현재 Science: `V42_COMMON_AM_JOB_ACTUAL_EMPIRICAL_QOS_DDAY_GRID_POLICY_V5`.
V1 통합 및 V2 합성 초기화 실험의 Source freeze·비용·실패는 이력으로 보존한다.
QoS: `EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1`.
기준 커밋은 PR222 `12594e281bb89611331950f11f775a2612d3cb48`이며, 과거 실행 파일과 원장을 수정하지 않는다.

B0/B2는 같은 인과적 비계통 기준 AIDC 정책, B1/B3는 같은 A 코어를 사용한다. B2/M1/M2는 같은 M 코어를 호출한다. B3 순서는 A1→M1→A2→M2이다. 이 교대 과정과 제한 경로 Joint 결과는 AIDC–MESS 전체의 전역 최적성 증명이 아니다.

Known과 제출이 관측된 Unknown에 같은 정책을 적용한다. TRAIN 완료 Job의 서로 다른 UID를 표본으로 하고, 완료·관측 시각이 cutoff 전에 확인되고 요청 provenance가 지원될 때만 허용 통계에 넣는다. L0=(qos,protected,partition,GPU bucket,walltime bucket), L1=(qos,protected,GPU bucket,walltime bucket), L2=(qos,protected,walltime bucket), L3=(qos,protected) 순서에서 N≥100인 가장 세밀한 cohort를 선택한다. PR75의 GPU/요청 walltime bucket을 그대로 사용한다. QoS/보호 등급을 섞지 않는다.

시간은 초다. `W=start−submit`, `T=end−start`, `Z=W/max(T,900)`, `q=Q90_higher(Z)`이다. 동결 nominal T50와 인과적 shadow reference s0에 대해 `W0=s0−submit`, `Wemp=q×max(T50,900)`, `B=900×floor(min(max(0,Wemp−W0),3600)/900)`로 한 번 발급한다. Q50 서비스 자체를 900초로 바꾸지 않는다. 연구용 60분/100UID/Q90을 실제 SLA나 위반확률 보장으로 표현하지 않는다.

보호·high·urgent·batch 미확인·보호등급 미확인·통계 지원 부족은 의도적 추가 예산 0이다. 기준 과도대기는 별도 이유를 남긴다. 기존 UID 영수증을 A2/재시작/반복 사건에서 재사용한다. 허용 시작은 관측 release/dependency·실제 hard 계약·유한 representation과 latest-start의 교집합이다. 요청 walltime·자정·representation ceiling은 고객 deadline이 아니다. 실제 hard completion 계약은 nominal 계획에 적용하고 Actual 초과를 별도로 기록한다.

PR75 원자료에는 요청 버전과 관측 시점이 확인되지 않는다. 439,534개의 완료 고유 UID는 **기술적 통계 proxy**로 보존하지만, strict 권한 통계는 0이다. proxy 표본을 issuer에 전달하지 않는다. 이 데이터 부족을 May outcome으로 보정하거나 Job 삭제·전 실험 중단으로 바꾸지 않는다.

원본 도메인 생성·class·정수 복원·FULL validator는 새 QoS 시작 집합을 소비한다. 새 도메인은 의도된 연구 모델 변경이며 옛 인증을 이전하지 않는다. class에는 정책·허용 집합·관측 상태·서비스·hard 계약·사이트/checkpoint 권한이 들어간다. 현재 연결은 원래 F2-CRA 전체 도메인 native 경로이며, 옛 lazy pricing 인증이나 과거 bound를 새 결과에 재사용하지 않는다. P1=min rho만 최적화하고 P2 호출은 0이다.

Unknown 정책 `V42_GRID_SENSITIVITY_AWARE_CONDITIONAL_POLICY_V1`은 최종 A의 anonymous_GPU·reserve·Known 배분과 최종 M의 모든 P/Q·경로·SOC·Mode를 재사용한다. 동결 LightGBM Q50/Q90 및 원본 signed 16-face 계통식으로 유한 익명 후보들을 오프라인 비교하고, 남은 96슬롯의 최대 선로부하율을 시나리오별 계산한다. 미래 UID를 생성하지 않는다. 온라인에서는 reload한 순위와 실제 whole-gang·GPU/rack·WAN·checkpoint·공동 QoS 예산을 검사한다. 지원하지 않는 규칙/자원/권한/관측 편차는 이유를 남기고 Queue 또는 STAY를 사용한다. 이 fallback의 계통 안전을 보장하지 않는다. 온라인 전역 최적화와 P/Q repair는 0이다.

PREPLACE와 CHECKPOINT_MIGRATION을 구분한다. migration은 누적 compute 기준 1800초 checkpoint, 최대 1회, 확인된 목적지·GPU/rack/gang·residency·WAN path/bandwidth/payload·restart·예약 계약을 모두 요구한다. 미확인 capability를 invent하지 않는다. 추가 시작 지연과 WAN wait/transfer/restart가 같은 B를 소비한다. checkpoint→source wait→transfer→restart→destination RUNNING을 실제 원장에 남기며 compute를 두 곳에 중복 수행하지 않는다.

Actual은 PR125 Controller/Environment/EpisodeLedger와 ForecastBook을 재사용한다. 네 Arm에서 같은 private trace-derived compute를 사용하고 Q50 overrun 중 GPU를 유지하며 실제 완료 관측 후 제어격자에 해제한다. IT/PCC는 실제 점유와 동결 C1/날씨로 재계산한다. forecast/reserve는 실제 부하가 아니다. 하루 내부 사건·carryout 재시작은 이어지지만 독립 일별 비교를 31일 연속 운전이라고 주장하지 않는다.

최신 사용자 지시에 따라 실제 평가 범위는 May01 00:00~24:00 AEST의 96슬롯이다. 4월 30일에 완료된 사이트 미확인 RUNNING 44개·59 GPU는 `PRE_DDAY_COMPLETED_EXCLUDED_FROM_DDAY_ACTUAL` 원장에 보존하며 D-day 활성 GPU·IT/PCC·Unknown 등록·CC4 차감에서 제외한다. 복원된 1개·4 GPU의 PR79 합성 사이트는 역사 증거로만 남긴다. 원본 null 사이트와 UID·Gang·시작·완료 이력은 바꾸지 않는다.

`SYNTHETIC_PREDAY_RUNNING_INITIALIZATION_V1` 정책은 취소됐다. 기존 43개 합성 배치와 해당 초기 상태의 Actual·Fresh AC는 `SUPERSEDED_BY_DDAY_BOUNDARY_POLICY`이며 현재 정책의 실행 증거로 사용하지 않는다. 4월 30일 Queue 재생, 사이트 배정, R0/PR79 재생성은 수행하지 않는다.

Planning에는 D-1 18:00에 동결된 reference·V10 Q50·GPU/서비스만 들어간다. 44개의 당시 예상 종료가 issue slot 24 이전이라는 자료는 D-day nominal 점유 0의 근거다. 실제 완료시각과 자정 관측 상태는 Planning/QoS 계산에 넘기지 않는다. 자정의 source-prefix audit은 Actual 초기 상태 인증에만 사용한다.

원본 Trace의 자정 상태와 합성 12-AIDC의 Queue/사이트 권한은 다르다. 최신 사용자 권한에 따라 자정 RUNNING 324개·472 GPU는 기존 151개·296 GPU를 보존하고, PR129의 독립 검증을 통과한 20개·20 GPU를 모델 사이트로 재사용하며, 나머지 153개·156 GPU는 기존 PR125 Grid-blind 규칙으로 배치한다. PENDING 1,300개·1,313 GPU는 공통 FCFS Queue로 동결한다. 이는 Kestrel 실제 지리·Queue 복원이 아닌 명시적 `MODEL_ASSUMPTION`이다. 공통 초기 상태 SHA는 `5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573`이며 네 Arm이 동일 파일을 reload한다. 과거 `INITIAL_QUEUE_UNVERIFIED` 결과는 역사 진단으로 보존한다.

CC4는 실제 May에 연결된 `LGBM_weighted_c1_s20260924`의 Hourly Lifetime GPUh 원본이다. 모델·예측·Runtime·TRAIN Execution-lag Kernel을 재학습, Scaling, Clipping, May 재선택 없이 검증한다. Q50 nominal과 Q90 stress는 별도 시나리오이며 Q90-Q50을 Actual GPU에 더하지 않는다. Burst의 시점·작업군 근거가 부족하므로 `INSUFFICIENT_SUPPORT`이다. PR64의 Offline DeepAR 선택을 현재 LightGBM 소비와 혼동하지 않는다.

Event30 원본은 15분 격자의 짝수 슬롯에서 관측 편차가 동결 threshold보다 엄격히 큰지를 검사한다. 현재 source에 threshold와 편차 측정 단위의 승인 근거가 없어 Event30 활성화를 인증하지 않는다. Job별 1800초 compute checkpoint와 최대 한 번 migration 계약은 별개로 유지한다.

A 모델 성능 개선은 자유 PCC 변수와 원래 C1 식의 정확한 등식으로 반복 계수를 공유한다. 원본 모든 행은 투영 후 동일하며 도메인이나 물리 제약을 삭제하지 않는다. 현재 사례의 원래 reference 선택을 임시 모델에서 완성하여 모든 자유 모델 행·bounds·integrality를 replay한 점만 Start로 넣는다. 이 임시 제한 모델의 bound는 전역 LB가 아니다. 최종 전체 도메인은 자유이며 검증된 incumbent를 단조 보존한다.

MESS는 PR222 FULL 검증점의 단조 보존, 완성 경로 pinning, 원본 행의 Exact Direct 치환, 자유로운 charge mode/P/Q/SOC를 사용한다. Start 속성 readback과 Optimize 중 처리 결과를 구분한다. scorer LP는 admission용 완화이며 LB/UB 인증이 아니다. 동일 수치 Case 외의 registry/bound는 이전하지 않는다.

새 검증 비용은 한 원장에 Gurobi Native와 다른 solver wall을 분리하고 합계 3600초를 보수적으로 제한한다. AC 시간은 별도다. 운영 A=5400초, M=1800초는 유지한다. TIME_LIMIT는 INFEASIBLE이 아니다. fixture·실제 입력·FULL·gap·QoS·Actual·AC를 독립 상태로 보고한다. B2/B3와 31일 campaign HOLD는 유지한다.
