# V42 May01 Trajectory Tracking 연구 계약

Scientific base는 PR228 HEAD `7f1f92308dc24096933b39dfe0666ee21089612a`이다. 별도 연구 branch에서 실행한다. PR229의 이전 모델 준비 중단 증거를 보존하며, 과거 Native 원장과 이번 원장은 합산하거나 초기화하지 않는다.

Planning 96슬롯, Actual 2025-05-01 00:00–04:00 AEST 16슬롯, 12 AIDC/780 GPU, B1/MESS OFF, E1/FLEX30으로 제한한다. B2/B3, May31, Source18r 중지 캠페인, Supervisor 또는 Windows Task Scheduler를 시작하지 않는다. Full96 Actual 자동 실행은 없다.

신규 `TrajectoryTrackingPolicy`는 `lookup_only=False`이며, `OBSERVED_JOB_AGGREGATE_GREEDY_TRACKING_V1` 명시 계약을 갖는다. 신규 `TrackingJobEventController`만 이 계약을 수용한다. 원래 Experimental Frozen Controller의 lookup-only 검사 및 legacy 진단 경로는 수정하지 않는다. Planning Frozen 표와 원래 fixed replay 검사도 보존한다.

조사·재사용한 원본 경로는 다음과 같다.

| 원본 | 적용 |
|---|---|
| a_engine.py | 전체 Known domain/graph와 원래 Solver numerical policy 유지. Native 상한 300초, Threads1/Worker1. 현재 producer의 P2_calls=0 한계도 유지·보고. |
| coordinator.py | Production Full96 gate 유지. 별도 연구 runner의 16슬롯 호출은 production 인증과 구분. |
| experimental_planning.py | Issue 시점 Known roster로 E1/FLEX30 권한 동결. Unknown Actual request bank를 Planning에서 순회하지 않음. |
| known_commands.py | 원본 native slot/absolute seconds/checkpoint 변환 그대로 사용. Start/Site/Checkpoint 명령 SHA를 모든 비교군에 공통 사용. |
| actual.py | 공통 Submit/Completion/Checkpoint event simulator, private runtime environment, whole-gang execution 및 migration phase safety 재사용. |
| experimental_actual.py | 원본 QoS projection 및 metadata overlay를 재사용. Frozen 강제 검사를 우회하지 않음. |
| reservation_state.py | Known hard 미래 예약, Unknown committed 예약, Running 실제 점유 및 동일 UID 최대 점유 union 재사용. Anonymous Q50와 runtime reserve는 실제 점유가 아님. |
| action_metrics.py | Unknown unique UID, 행동 중복, nominal GPUh와 실행 결과 분리 집계. 별도 tracking_metrics에서 Known/Unknown compute/occupation을 독립 적분하여 공통 simulator와 대조. |
| OriginalGridPacket | Signed IEEE123 voltage/current/16-face transformer rows와 원래 단위를 사용. 후보 판단은 affine 진단이며 Fresh AC 인증 아님. |
| FrozenPowerModel | 원본 C1 exact callback, 설치 GPU idle, active swing, forecast weather, PF/Q 변환으로 실제 점유에서 Actual P/Q 재계산. |

첫 새 A1은 원본 전체 모델로 시도한다. 모델 준비 포함 A1 stage를 600초로 제한하고 전체 Canary를 1,200초로 제한한다. Source graph를 축소하거나 모델 준비를 Native runtime이라고 집계하지 않는다. 모델 준비가 한도를 넘으면 자신이 만든 worker만 중단하고 실제 도달한 Native 시간·호출·inflight 상태를 보존한다.

새 A1 인증에 실패하면 `NEW_A1_NOT_CERTIFIED`로 표시한다. Source18r V5의 기존 A1을 별도 diagnostic anchor로 읽고, 96슬롯 Known service 적분과 IT/PCC P/Q, original signed rows를 독립 검사한다. 이 검사는 새 E1 Full MILP replay, global gap, P2 또는 최적성 인증이 아니다. 과거 Case SHA와 현재 Case SHA를 함께 기록한다. 저장 Anchor의 Source/Case가 달라진 것을 숨기거나 새 E1 최적해로 재명명하지 않는다.

`DAYAHEAD_TRACKING_REFERENCE.npz`는 Known/Unknown/total GPU, IT, PCC P/Q 96×12와 Known 명령, CC4 Q50/Q90, service/carry 및 CDF를 보존한다. 별도 SHA receipt에 Source/Case/Anchor/CC4/Runtime/C1/Signed authority/Target SHA를 연결한다. 미래 Actual UID와 실제 Runtime/완료시각으로 Reference를 생성하지 않는다.

Pending Unknown은 관측 후 전체 compatible site를 확인하고 원본 QoS receipt의 허용 시작시각만 평가한다. E1 normal의 0/15/30분 외의 권한을 새로 만들지 않는다. Standby와 Preplace는 Source 또는 명시된 E1 연구 권한을 표시하고 실제 Kestrel SLA라고 주장하지 않는다. Budget은 원본 reference에 고정한다. Queue로 전환하거나 예약이 거부되어도 이미 부담한 intentional delay를 환불하지 않는다.

Running Unknown은 최초 관측 유효 checkpoint, max1, Source route, 양의 payload/transfer/restart, original hold protocol, causal remaining Q50, shared delay/interruption budget 및 원래 WAN link capacity를 만족해야 Migration 후보가 된다. 선택 후에도 원본 실행 phase에서 목적지 GPU/Rack/현재 signed grid를 다시 확인한다. 다른 Job의 예약·Running을 취소하지 않는다.

C0는 동일 Known 명령과 original reference site에서 기본 배치·불가피 대기를 사용한다. C2는 tracking, C3는 Unknown Preplace만 제거한 tracking이다. 모든 실행에서 QoS provider/reference/forecast/Queue/예약을 새로 만든다. C1은 전체 Frozen grammar의 Source-only 비용 추정이 RAM/시간 한도를 넘으면 `NOT_RUN`으로 기록한다. 두 사이트 fixture를 실제 12-AIDC Frozen 표로 표시하지 않는다.

결과의 실제 P/Q를 원본 signed response에 넣어 4시간 affine rho와 critical line/phase/time, loading-hours, hard rows를 진단한다. 추종 오차 감소와 계통 성능 변화는 별도로 판단한다. 부분 trace가 원본 OpenDSS의 Full96 계약에 맞지 않으면 `PARTIAL_AC_NOT_AUTHORIZED` 및 AC NULL을 기록한다.

입력과 Reference의 같은 SHA, Known/Unknown 분리, 미래 누수0, optimizer0, 실제 점유 C1 재계산, QoS/Resource/Grid hard 검사, 메모리/시간 gate를 별도로 평가한다. 진단 Anchor 성과를 새로운 E1 최적화 통합 성과로 승격하지 않는다. 모든 gate가 확인되면 같은 May01 Full96 후속 실행 패키지만 준비하며 자동 실행하지 않는다.

Tracking share는 96슬롯 안에 있는 nominal service 적분을 기준으로 한다. 전체 Job의 GPU×Q50 nominal volume과 horizon 밖 carry는 별도 집계한다. 초기 Running의 과거 계산을 미래 배분에 다시 넣지 않는다. Migration의 GPU hold는 물리 전력에 포함하지만 nominal computing share에는 포함하지 않는다.
