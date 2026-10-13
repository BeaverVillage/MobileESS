# V42 계통 민감도 조건부 정책 알고리즘

알고리즘은 `V42_GRID_SENSITIVITY_AWARE_CONDITIONAL_POLICY_V1`이다. 기존 A-stage의 익명 시간·사이트 배분과 최종 MESS 계획을 고정한 뒤, 개별 미래 UID 없이 제한된 작업군 조건의 행동을 Offline 비교한다. 원본 전력계통 근사식을 검사하고, 실제 사건에서는 동결 후보 순위와 기존 QoS·GPU/WAN·Checkpoint Guard를 조회한다.

기존 Compiler는 작업 서비스 동안의 signed effect vector를 합산하고 사전식으로 정렬했다. 따라서 현재 계통 기준 부하, 미래 전체 선로 최대값, 지연 후 Rebound, Q50/Q90 스트레스를 함께 최소화한 정책과는 구분한다. 기존 Queue·QoS·Reservation·Migration 구현은 재사용한다.

## 동결 입력과 점수

Production에서는 원본 CC4 v2.1 `LGBM_weighted_c1_s20260924`의 예측·Runtime·TRAIN Kernel SHA를 검증한다. 이 디렉터리의 숫자는 독립적인 합성 2-site/2-branch Fixture이며 실제 May 예측값이나 실제 A/M 최적해가 아니다. 실제 CC4·Source18r signed response 감사는 별도 `CC4_POLICY_SOURCE_AUDIT` 산출물에 있다.

CC4 Q50/Q90은 Hourly Lifetime GPUh이다. A-stage가 배분한 익명 Q50 서비스와 Carryout의 합을 Q50 원본 작업량과 맞춘다. Q90 스트레스는 Q90−Q50의 별도 시나리오이며 Actual 점유에 더하지 않는다. 최적화한 Reserve Timing은 원본 CDF 및 전체 A-row 검증 근거와 함께 소비한다. Reserve의 `arrival_target_GPU`는 스트레스 수요 목표다. 용량으로 뒷받침된 실제 GPU 점유로 표현하지 않는다. 사이트별 스트레스 배분 근거가 없으면 `INSUFFICIENT_SOURCE_SITE_DISTRIBUTION`으로 차단한다. 검증된 TRAIN Burst가 없으면 `INSUFFICIENT_SUPPORT`이고 임의 벡터를 만들지 않는다.

후보의 서비스는 기준 익명 Gang/Service를 빼고 행동 후 서비스를 넣는 `after − reference` 차이로 반영한다. Known 서비스는 빌려 쓰거나 변경하지 않는다. Pending 시작·지연·Pre-place와 Running STAY·Checkpoint Migration을 구분한다. Running Migration은 Source Hold, Transfer, Destination Restart와 남은 Compute를 모두 포함한다. 유용한 Compute 서비스 보존과 GPU의 Restart 점유를 구분한다.

원본 C1 endpoint secant의 `slope × swing_kW_per_GPU`로 ΔP를 계산한다. AIDC의 `aidc_load_kw` 응답 열은 PF=.95의 Q 변화까지 이미 결합한 원본 열이므로 별도의 Q 응답을 다시 더하지 않는다. MESS P/Q는 최종 고정 계획의 원본 부호로 입력한다.

원본 `v42_native.grid.add_grid`의 16개 Thermal Face, 기준 Anchor에서의 signed current 보정, Squared-pu 전압 밴드, 모든 원본 변압기 전류 및 kVA Face를 그대로 평가한다. 목적은 각 시나리오에서 남은 모든 시간·선로의 최대 부하율을 계산한 후 그 시나리오 최대값을 최소화하는 P1이다. P2, 임의 가중치, Global LB 또는 Joint MILP 최적성 증명은 없다.

## 압축과 실행 경계

기본 Coverage는 고정 Planning Peak의 중요 8개 시점, GPU 1/4/16, Runtime 상한 900/3600/14400초의 조건이다. Pending/Running을 합해 최대 144개 Prototype으로 제한한다. 사이트·Rack 권한을 먼저 확인하고, 결정론적인 호환 사이트 순서로 연속 익명 Envelope에 맞는 기준 사이트를 정한다. 미래 UID나 실제 Runtime은 사용하지 않는다. Prototype에 맞지 않는 관측 상태는 `NO_MATCHED_FROZEN_TEMPLATE`로 Queue 또는 STAY 한다.

Runtime Bucket은 관측 Q50을 바꾸는 도구가 아니다. Offline에서 Bucket 양 끝과 15분 단위 Piecewise 경계를 평가한다. Actual 예약은 관측된 Q50 그대로 실행한다. 정책은 현재 Job의 단일 QoS 영수증, Shared Delay/Interruption 예산, 원본 호환 사이트·Whole Gang, GPU/WAN Atomic Reservation, Checkpoint, Restart, Hard Completion 및 Carryout을 다시 검사한다.

Running 후보는 익명 Envelope의 실제 지원이 필요하다. 지원 없이 Known 집합을 빼서 얻은 점수는 허용하지 않는다. Migration의 실제 Hold Contract와 상대 Phase Timing이 평가한 Template과 다르면 STAY 한다. Grid에 정렬되지 않은 Checkpoint는 현재 부분 슬롯의 최대값을 인증하지 못하므로 이 새 Grid-ranked 정책에서 STAY 한다. 기존 Physical Guard의 별도 Off-grid 회귀는 이 정책의 Grid Score 인증이 아니다.

관측 Resource가 동결 시나리오 Support 밖에 있으면 Guard가 Queue/STAY 한다. Support 범위 안이라는 조건도 Actual 전력계통 안전 인증은 아니다. 모든 선택은 근사 점수이며 Actual IT/PCC 재계산과 Fresh OpenDSS가 별도로 필요하다.

Event30은 원본 30분 Control-clock 계약이며 Execution-start에 고정된 1800초 Checkpoint와 별개다. 현재 Production의 Threshold 및 Deviation Metric/단위 권한이 없으므로 Event30 활성화를 주장하지 않는다. 임의 Threshold를 만들지 않았다.

컴파일은 NumPy와 고정 시나리오 Cache를 사용한다. 변경하지 않은 시간대의 모든 선로 Peak를 보존하고, 영향을 받는 서비스 구간만 원본 전체 제약으로 다시 계산한다. Runtime은 고정 Template 인덱스와 순위, 기존 Guard를 조회하며 96슬롯 계통 재평가·Gurobi·Electrical P/Q Repair를 호출하지 않는다.

정책의 의미 SHA는 동결 입력·후보·순위·Compiler Source를 식별한다. 성능 측정값은 의미 SHA에서 분리하고 전체 문서 Content SHA로 검증한다. Reload 후 모든 A/M/CC4/Runtime/QoS/Response/초기 상태 Anchor와 후보 순위를 확인한다.
