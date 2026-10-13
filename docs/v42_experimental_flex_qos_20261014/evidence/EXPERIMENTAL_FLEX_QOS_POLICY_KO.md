# V42 연구용 유연성 계약

정책명은 `V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1`이다. 실제 Kestrel 요청·실행 관측과 합성 12 AIDC 연구 계약을 별도 계층으로 보존한다. 원시 QoS 필드, GPU 요구량, Runtime provider, 전체 계산 서비스량을 수정하지 않는다.

## 계약과 참여

E0는 WORKSTREAM B의 버그 수정이 포함된 Source-only 기준이다. E1은 Normal Batch 30분·Standby Batch 60분을 주 실험 계약으로 사용한다. E2는 각각 60분·120분의 민감도 계약이다. 확인된 High/Urgent/Protected 및 명시적 non-batch 요청에는 추가 유연성을 부여하지 않는다. 요청 메타데이터가 확인되지 않은 적격 작업에는 `ASSUMED_EXPERIMENTAL_BATCH_CONTRACT`를 표시한다. 기본 연구 분류는 Normal이며 기존 계획의 Standby 라벨을 관측 SLA로 승격하지 않는다.

FLEX20/30/40은 적격 작업의 연구 계약 참여 확률에 대한 가정이다. 사전 동결한 Seed와 공개 UID·episode의 SHA256 정수에 20/30/40% 임계값을 적용한다. 참여 집합은 중첩된다. 미래 Unknown 전체를 미리 읽거나 성능을 보고 참여 집합을 바꾸지 않는다. Known은 원래 issue 시점 관측으로 계약을 발급하고 Unknown은 submit 관측 이후 발급한다. 참여 작업 수 비율과 nominal GPUh 비율은 따로 보고한다.

## 지연 예산과 자원

원래 issue 계약 영수증과 총 예산 B는 불변이다. 경량 E1/E2 실행은 현재 관측된 GPU 예약만으로 계산한 grid-blind 실행 가능 기준 시작을 사용한다. 물리적으로 불가피한 대기는 의도적 지연과 분리한다. 후보마다 `누적 추가 시작 지연 + 누적 migration 중단 <= B`를 검사하고 재시도 시 예산을 재발급하지 않는다. 실제 hard release/deadline이 있으면 항상 교차 적용한다. 기존 E0의 절대 기준과 Known 고정 스케줄은 그대로 유지한다.

Pre-placement, Time-shifting, Checkpoint Migration의 capability는 분리한다. RUNNING의 사이트 변경은 실제 migration episode를 거쳐야 한다. Checkpoint 가능성은 관측 사실이 아닌 `ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT`이다. 최대 1회와 계산 30분 checkpoint 간격을 유지하며 WAN·payload·restart 수치 및 가정은 별도 물리 권한 감사에 기록한다. 준비되지 않은 물리 packet은 migration을 승인하지 않는다.

## Q50/Q90와 비교 범위

Q50은 원본 signed Grid response와 C1/PCC 모델로 남은 실행 구간의 최대 선로부하 및 전압·선로전류·변압기 제약을 평가한다. 실제 예약의 whole-gang·GPU·rack·WAN 검사도 유지한다. Q90는 익명 GPUh 유체 큐 위험 근사이며 실제 점유에 더하지 않는다. 처리능력 밖의 수요는 backlog와 96슬롯 밖 tail로 보존하고 `arrived = served + remaining`을 검증한다. 현재 관측 대기량을 과거 슬롯에서 처리하지 않는다.

Q50 최대 선로부하가 주 순위이고 동률에서 Q90 큐·계통 위험과 지연·이동 비용을 사용한다. 이는 A-stage P2가 아닌 유한 후보 제어 규칙이다. Forecast deviation은 감사 기록이며 일괄 lookup 차단 사유가 아니다. 각 행동의 현재·미래 물리 자원과 Q50 원본 제약은 계속 검사한다.

이 비교는 기존 A2/M2와 원본 계통 response를 고정한 조건부 May 이벤트 재생이다. 바뀐 Known 도메인의 A1/A2 또는 M 최적화를 새로 풀지 않으며 과거 FULL·UB·LB·Gap을 새 문제로 옮기지 않는다. Fresh AC를 실행하지 않은 경우 Actual Maximum Line Loading과 실제 전압·전류 위반은 NULL/NOT_RUN이다. 합성 fixture, 조건부 재생, 새 A/M→Actual→Fresh 인증을 구분한다. 31일 캠페인과 B2/B3 M HOLD를 유지한다.
