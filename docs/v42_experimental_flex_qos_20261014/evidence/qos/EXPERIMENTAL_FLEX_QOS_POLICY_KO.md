# 실험용 QoS 계약 — Phase A Native0

E0는 기존 Source-only issuer를 그대로 사용한다. E1은 Normal 30분·Standby 60분, E2는 Normal 60분·Standby 120분을 연구용 추가 지연 상한으로 부여한다. 실제 Kestrel SLA를 관측한 값이 아니다. 확인된 High/Urgent/Protected 및 명시적 non-batch 권한은 유지한다.

May01 요청 QoS는 UNCONFIRMED이며 보호·Batch 권한도 확인되지 않았다. 본 연구의 주 가정은 ASSUMED_NORMAL_BATCH다. 기존 Planning 도메인의 Standby 라벨을 관측된 요청 QoS로 승격하지 않는다. 원시 관측값은 별도로 유지한다.

참여 Seed는 May 성능 실험 전 고정했다. UID fallback과 SHA256 임계값으로 FLEX20/30/40를 중첩 선택한다. 미래 Unknown 전체를 보고 정확한 비율을 맞추지 않는다. Known 1,649건은 원래 issue 정보로 결정하고, Unknown 774건은 제출·초기 관측 후에만 결정했다. D-day 활성 Known은 1,546건이며 완료된 103건의 원래 receipt는 보존한다. 실제 참여 Job 비율과 total Q50 nominal GPUh 비율은 CSV 및 manifest에서 별도로 보고한다.

발급 시 원래 기준 시작·계약 B는 불변이다. 경량 replay는 현재 관측된 grid-blind feasible reference를 후보별로 기록하여 불가피한 용량 대기를 의도적 지연과 분리한다. 이전 의도적 지연과 모든 Migration 중단은 같은 B에서 계속 차감하고 재발급하지 않는다.

Native 도메인은 원래 1,499개 modeling Job의 GPU·서비스·RUNNING 경계를 보존하며 원본 physical_starts·static_sites·GPU mask로 local hard-valid STAY 후보를 셌다. E0의 완전한 개별 후보 열거 결과 825,572개와 같은 수를 확인했고, 각 도메인의 양 끝 Option은 원본 validate로 재검증했다. 연구용 Checkpoint 가능성은 참여 집단에 가정하며 원래 WAN/Payload/Restart 모델을 유지한다. 확대된 Native Migration 도메인 열거는 NOT_RUN이며 별도 bounded control replay에서 확인한다. local 후보 수는 공동 스케줄 가능성의 증명이 아니다. 새로운 QoS 도메인에는 새로운 Case SHA가 필요하며 이전 A/M FULL·LB·Gap을 이전하지 않는다.

이 산출물은 Phase A Source 및 Native0 감사다. Native Optimize, Actual 실행, Fresh AC는 0회다. 별도 경량 replay 및 새 통합 Full96 결과는 이 문서의 검증으로 주장하지 않는다. B2/B3 M 및 전체 캠페인 HOLD는 유지한다.

| 정책 | FLEX20 참여 | FLEX30 참여 | FLEX40 참여 |
|---|---:|---:|---:|
| E0 추가 연구 계약 | 0 | 0 | 0 |
| E1 활성 D-day 참여 | 457 | 674 | 890 |
| E2 활성 D-day 참여 | 457 | 674 | 890 |

활성 2,320개 작업 기준 Job 참여율은 19.6983%·29.0517%·38.3621%다. 같은 Seed와 참여 집단에서 E1/E2의 계약 상한만 달라진다. 이는 계약에 참여한 수이며 실제 실행된 지연·이동 수가 아니다.
