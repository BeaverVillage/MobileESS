# Section V와 V42의 수학적 대응

검토한 1차 자료: [저자 공개본 arXiv v3, Section V](https://arxiv.org/html/2410.21510v3#S5), [IEEE DOI](https://doi.org/10.1109/TPWRS.2025.3630499). 공개본은 2025-10-27 버전이며, IEEE Early Access 출판은 2025-11-17이다. 최종 IEEE 유료 본문과 공개본의 완전한 동일성은 검증하지 않았다.

식 (20)은 고정된 제출 구간 k와 class c에 대해 다음 배치의 cluster d, 실행 구간 t를 고른다.

`argmax_(d,t) [Y*_(k,c,t,d) − Y_abs_(k,c,t,d) / sum_(i<j) u_i^vol]`

Y*는 계획된 비율, Y_abs는 이미 배치한 compute volume, 분모는 이전에 도착한 같은 k,c의 Job volume이다. class별 GPU 개수나 전체 데이터센터의 전력 비율로 분모를 바꾸면 같은 식이 아니다. 본문은 매 제출 시간 구간에 Y_abs=0 초기화를 명시하지만 첫 Job의 0/0 수치 처리 규칙은 명시하지 않는다. V42는 이전 배분량이 0이면 Actual share=0으로 정의한다. 논문은 이산 Job으로 연속 계획을 정확히 실현할 수 없음을 설명하며, 단일 시간 구간 Runtime 가정을 둔다. Section VI-A는 긴 Runtime의 연속성 확장을 논의한다.

이하 내용은 본 연구 코드의 설계이며 논문의 성능 보장을 이전하지 않는다.

| 항목 | V42 구현과 한계 |
|---|---|
| Planning | 원본 A1/A2의 `MIN_MAX_LINE_LOADING` 및 기존 `MIN_INTERVENTION` 계약 유지. DRO, Wasserstein ambiguity set, CVaR, VCC 최적화 추가 없음. 원본 producer의 P2_calls=0을 P2 인증으로 표시하지 않음. |
| 목표 | A1의 96×12 Aggregate Unknown Q50 GPU service를 GPUh로 변환하고 전체 동결 목표량으로 정규화. 미래 class별 도착량을 추정해 Y* 텐서를 만들지 않음. |
| Actual share | 실제 Submit 또는 DD00 Running 관측 후 확정한 Unknown Job의 Q50 service만 집계. 다른 정책 실행의 배분 상태를 가져오지 않음. Known은 이 분모에 넣지 않음. |
| 후보 기여 | 한 Job의 전체 예상 점유 구간에 대해 `GPU × overlap_seconds / 3600`을 적분. 시작 슬롯 한 점만 점수화하지 않음. Gang 분할 없음. |
| Greedy 점수 | 후보 전체 service 적분으로 `Target_share − Assigned_share`를 평균. 초기 Running은 관측된 elapsed를 뺀 Q50 remaining만 최초 집계. 재결정 시 같은 UID의 기존 배분을 제외하여 중복 배분을 방지. |
| 시간 집계 차이 | 일간 Aggregate site/time 서비스 배분을 추종하며 class별·제출 시간별 분모를 재구성하거나 매 시간 초기화하지 않음. 따라서 식 (20)의 정확한 재현이 아닌 Paper-inspired Tracking. |
| Physical guard | Known 확정 예약, 다른 Unknown 확정 예약, 실제 Running을 먼저 보호. Signed voltage/current/transformer와 GPU/Rack/WAN/QoS hard guard를 적용. 미래 grid 검사는 후보 구간 중 최대 16슬롯의 공개 Q50 예상 점유. 이것은 미래 실제 완료에 대한 보장이 아님. 실행 직전에 관측 점유를 재검사. |
| Ranking | Hard feasibility → 부족 배분 비율 → 예상 affine rho → loading-hours → 공개 Q90가 있으면 Runtime risk와 carry → Delay/Migration burden. GPUh와 kWh 오차는 별도 진단값. 임의 가중 합산 없음. |
| 추가 목표 | `max(Planning total − observed/committed Known, 0)` residual을 계산하고 음수 clamp량 및 Known/Unknown 오차를 별도 기록. 익명 목표를 실제 GPU 수요나 강제 실행으로 만들지 않음. |
| 계산량 | 사이트 S, 허용 시작 A, 공개 예약 J, 슬롯 H, signed row R 기준 예약 구성과 후보별 guard/점수 비용이 존재한다. Frozen 조회 시간이나 논문의 복잡도와 같다고 주장하지 않고 실제 Job별 평균/P50/P95/최대를 측정. |
| Migration | Source capability와 최초 관측 유효 CP30m, 1회 한도, 양의 transfer/restart, 실제 WAN/GPU 예약, 공유 QoS budget을 원본 `migration_guard`로 검사. 알려진 remaining Q50가 없거나 overrun이면 STAY. |

Event30 발동 임계값은 Source 미확정이다. 실행 명칭은 `OBSERVED_JOB_EVENT_TRACKING`이며, CP30m 사용만으로 Event30 연구 계약 완성을 주장하지 않는다.
