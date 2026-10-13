# V42 계통 민감도 조건부 정책

기존 제어표는 A 자원 envelope를 직렬화하고 제출 시 자원·QoS guard를 검사하는 규칙이었다. 새 `V42_GRID_SENSITIVITY_AWARE_CONDITIONAL_POLICY_V1`은 동일 동결 입력에서 여러 행동의 오프라인 목적값을 실제 비교한다. 이 비교는 전체 Joint MILP의 최적성이나 Global LB를 증명하지 않는다.

`cc4_policy_inputs.load_frozen_cc4`는 원본 LightGBM `LGBM_weighted_c1_s20260924` 예측 행과 TRAIN kernel을 SHA로 검사한다. `PlanningGridContext.bind`는 기존 `bind_forecast`에서 Hourly Lifetime GPUh를 서비스 변수·carryout으로 변환한다. `optimize_aidc`는 최적화한 nominal/reserve 사이트 GPU·서비스·carryout·Known 점유를 내보낸다. 생산 factory는 질량과 사이트 합계를 검증한 뒤 final A/M 결과를 정책 compiler에 연결한다. B3는 A2와 M2, B1은 A1에서 생성하며 B0/B2는 Grid-aware 정책을 사용하지 않는다.

유한 익명 prototype은 시간·GPU gang·Runtime 구간·상태를 나타내고 미래 UID가 아니다. 후보는 START_NOW, 허용된 DELAY_15~60, PREPLACE, CHECKPOINT_MIGRATE, STAY, QUEUE이다. QoS, whole-gang/rack, WAN path/payload/global transfer, checkpoint, restart, 서비스·carryout을 검사한다. Runtime을 bucket 값으로 실제 실행하거나 Q50을 900초로 바꾸지 않는다. 승인 구간의 piecewise 서비스 경계들을 후보 평가에 포함하며 실제 실행은 원래 nominal을 사용한다.

행동은 기존 anonymous reference 서비스를 실제 prototype 서비스로 교체한다. 같은 익명 수요에 prototype을 추가하지 않는다. 변화량은 `P_after−P_reference`, Q는 원본 고정 power factor와 동일하다. 원래 signed 16-face 선로식의 전류 보정항·NormalAmps, 전압 제곱식, 모든 변압기의 전류와 kVA 면을 사용한다. 점수는 각 Q50/Q90 시나리오에서 남은 전체 슬롯과 모든 선로의 최대 부하율이며, 후보는 시나리오 최대값을 최소화하는 순서로 정렬된다. 변경 구간만 재계산하더라도 변경하지 않은 미래 최대값을 유지하므로 Rebound가 사라지지 않는다.

Q50 nominal과 Q90 stress는 분리된다. Q90은 동시 보장 상한이나 Actual 부하가 아니다. Burst는 검증 가능한 TRAIN 제출 패턴 근거가 부족하여 `INSUFFICIENT_SUPPORT`로 표시한다. May 미래 UID·도착·완료·실측 Runtime은 오프라인 정책 선택에 들어가지 않는다.

Frozen policy는 CC4/Runtime/QoS/A/M/Response/초기 상태/Compiler SHA를 포함한다. 새 Load는 stale anchor와 내용 SHA를 거부한다. Actual은 순위를 조회하고 당시 GPU/rack/WAN/QoS 상태를 검사하며 예약을 원자적으로 갱신한다. 초기 RUNNING을 새 제출로 등록하지 않는다. Unknown 제출은 ForecastBook에서 한 번 차감하고 실제 예약·점유로 대체한다. 남은 budget은 지연과 migration 중단에 공동으로 사용한다.

RUNNING의 과거 start는 바꾸지 않는다. 1800초 compute checkpoint와 최대 1회 migration, source wait→WAN→restart→destination RUNNING의 원본 물리 계약을 유지한다. Event30은 원본 threshold·관측 편차 단위의 승인 근거가 없어 `NOT_AUTHORIZED_THRESHOLD_METRIC_SOURCE_MISSING`이다. 별도 cooldown이나 threshold를 발명하지 않는다.

지원되지 않는 prototype·관측 편차·자원·권한은 `NO_MATCH` 또는 `NO_FEASIBLE_ACTION`과 이유를 남기고 Queue/STAY를 사용한다. 근사식 PASS와 fallback은 Actual 계통 안전 보장이 아니다. 실제 전력은 실제 점유와 C1/날씨로 계산하고 Full96 Fresh AC를 별도로 판정한다. 온라인 Gurobi/Global MILP와 Electrical P/Q repair는 0이다.

Fixture의 C_FIXED/C_GREEDY/C_GRID 비교와 새 May 실행 결과는 별도 증거 파일에 기록한다. 과거 PR129 AC, V2 초기 상태의 Actual 또는 기존 B1 고정 궤적을 새 정책의 결과로 이전하지 않는다. 실행·FULL feasibility·gap·QoS·Actual·AC·계통 성능을 각각 구분한다.
