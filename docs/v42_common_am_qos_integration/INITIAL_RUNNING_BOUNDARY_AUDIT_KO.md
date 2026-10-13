# May01 초기 RUNNING 경계·인과성 감사

원본 초기 관측은 254개 RUNNING, 468 GPU다. Source18r가 보존한 210개 모델 사이트, 409 GPU는 변경하지 않았다. 누락 44개, 59 GPU의 원본 사이트는 계속 null로 보존했다. PR79의 동일 실행 Episode에서 1개 UID `8568682`, 4 GPU의 기존 **연구 Case 모델 사이트** `AIDC03`을 범위가 제한된 원장·용량·Rack 검증으로 복원할 수 있다. 실제 Kestrel 설치 위치를 발견한 결과는 아니다. 나머지 43개, 55 GPU는 별도 초기 상태 권한이 필요하다.

발행은 2025-04-30 18:00 AEST, 즉 08:00 UTC다. D-day는 2025-05-01 00:00 AEST, 즉 2025-04-30 14:00 UTC에 시작한다. 발행 원점 slot 24가 D-day slot 0이다. 전력 96슬롯은 발행 축 `[24,120)`에서 D-day 축 `[0,96)`으로 변환한다.

## 1. 누락 위치와 이전 처리의 의미

확인된 최초 누락 지점은 기존 `dayahead/v39a/spatial.py::production_activity`의 평가 구간 투영이다. 원본 예약 구간을 `[24,120)`으로 자른 뒤 구간이 비면 공간 배정 대상으로 넣지 않았다. 이후 `dayahead/v40d_actual/inputs.py::frozen_jobs`는 시간 도메인의 UID를 유지했으나 대응 공간 배정이 없어 `UNASSIGNED`가 됐다. PR93의 `v42_may01.prepare.job_ledger`는 이를 삭제하지 않고 별도의 Pre-D00 원장에 보존했다.

PR93가 요구한 `end_slot <= 24`는 `REQUESTED_REMAINING`으로 계산한 원본 Reference 예상 종료다. 실제 완료 사건의 증명이 아니다. 이후 Q50 입력 갱신은 명목 `reference_end`를 Q50 잔여량으로 바꾸면서, 이전 요청 실행시간 기반 끝을 `unresolved_external_source_service_end`에 따로 남겼다. Q50가 이미 만료된 RUNNING의 명목 종료가 0이라고 실제 GPU를 해제할 수는 없다.

기존 구현의 평가 구간 투영은 D-1 발행부터의 실제 Queue·물리 점유 전이를 인증하지 않았다. 이번 공통 Job-event Actual이 발행 원점부터 120슬롯을 인과적으로 처리하면서 이 미확인 사이트가 실제 초기 상태 문제로 드러났다.

## 2. 실제 종료와 서비스 보존

원본 Trace의 정확한 UID·source member·source row 조인으로 2,498개 Case UID를 확인했다. 초기 210개 배정 RUNNING의 실제 시작과 발행 당시 관측 elapsed에서 복원한 시작은 모두 일치했다. 44개 누락 Job도 실제 완료 사건과 제어격자 release가 모두 D-day 자정 이전이다. 가장 늦은 실제 종료는 2025-04-30 12:09:07 UTC, 즉 22:09:07 AEST다.

44개의 D-day 직접 점유와 서비스는 0 GPUh다. 그러나 발행부터 자정까지 이들이 실행한 실제 서비스는 **65.8675 GPUh**다. 이 질량을 삭제하거나 미래 Unknown으로 다시 등록하지 않는다. 요청·Reference 예상 종료, Q50 명목 종료, 실제 완료 사건, 제어격자 GPU 해제를 각각 별도 열에 기록했다.

실제 완료는 simulator의 private 환경에서만 보유하고 해당 사건 시각에 도달했을 때 공개하는 계약이다. 실제 Kestrel 스케줄러의 별도 관측 watermark는 자료에 없어 null로 기록했다. 사후에 완료 시각이 자정 전임을 확인했다고 D-1 발행 시점에 이를 알고 있었다고 처리하지 않았다.

## 3. 자정 이후 점유 0이 Queue 영향 0을 뜻하지는 않는다

독립적으로 동결된 12-AIDC 모델의 D00 Queue·실행 Episode·사이트 snapshot을 확인하지 못했다. May01 원본 snapshot은 전날 18:00, May02 snapshot은 당일 18:00 관측이다. RSP/RW·GPU/PCC 궤적은 Reference/Planning 산출물이며 D00 실제 상태 관측이 아니다.

기존 Arm별 `ACTUAL_JOB_REPLAY.json`은 정책별 고정 DayAhead 실행 결과다. 누락 44개를 `FROZEN_UNSELECTED_BACKLOG`로 남겼고 실제 사이트는 null, 실행 segment는 비어 있다. 이를 B1/B3의 사전 실행 사실이나 새 공통 Actual의 자정 Queue 인증으로 이전하지 않았다.

두 개의 **채택하지 않은 가상 초기배치**로 사이트 영향의 반례를 확인했다. 두 배치 모두 원본 210개 사이트를 고정하고, 복원 후보 `8568682`는 AIDC03에 동일하게 유지했다. 전체 254개·468 GPU, whole-gang·사이트 용량·승인된 Rack 호환성을 모두 만족하지만 AIDC01의 즉시 headroom은 각각 20 GPU와 75 GPU다. 동일하게 관측된 PENDING 21개, 총 21 GPU는 첫 배치의 즉시 용량을 초과하고 두 번째 배치에서는 충족한다. 이 검사는 순간 용량 민감도 증명이며 새 실행 권한이나 전체 연속 서비스 가능해 인증은 아니다. 실제 미래 완료·전력계통·MESS 위치·정책 결과·Solver를 사용하지 않았다.

따라서 경로 B의 개별 Job `NO_DDAY_OCCUPANCY_PROVEN` 사실은 성립하지만, 전체 Case의 `PRE_D00_NO_DDAY_EFFECT_PASS`는 아직 성립하지 않는다. 불완전한 발행 전이를 자정에서 단순 정상화해 통과시키지 않는다.

## 4. 적용 가능한 해결 범위

경로 A의 범위는 동일 UID·실행 시작·Episode 및 발행 이전 확정된 모델 배정을 갖고, 현재 사이트 용량·whole-gang·Rack 검증을 통과한 1개 Job, 4 GPU다. PR79 전체의 실패한 Reference를 production-ready로 승격하지 않았다. 원본 R0/Source18r의 null도 덮어쓰지 않고 복원 모델 사이트를 별도 열에 남겼다.

나머지 43개, 55 GPU는 사용자가 승인한 `SYNTHETIC_PREDAY_RUNNING_INITIALIZATION_V1`의 대상으로 분리할 수 있다. 이는 새 연구 초기 상태 가정이다. 배정·인과·재현성 검증 및 실제 공통 Actual 소비가 완료되기 전에는 해당 경로의 PASS를 주장할 수 없다. 채택 시 210개 기존 사이트와 복원된 Episode 사이트를 고정하고, 동일 새 초기 상태를 B0/B1/B2/B3에 사용해야 한다. 실제 Kestrel 사이트 복원, Source18r 전체 수치 동일성, 이전 PR220 UB 또는 역사 B1 결과의 자동 이전은 허용하지 않는다.

## 5. 현재 영수증의 범위

- `INITIAL_RUNNING_254_AUDIT.csv`: 전체 RUNNING·요청·Episode·예상/실제 시간·사이트·SHA·서비스 질량.
- `UNASSIGNED_RUNNING_44_LEDGER.csv`: 원본 null 보존, 1개 범위 제한 복원 및 43개 잔여 Prefix 영향.
- `PREDAY_DDAY_BOUNDARY_AUDIT.json`: 실제 종료·release·서비스, 독립 D00 상태 근거 부재, Arm별 과거 replay의 한계.
- `PREDAY_INITIAL_LAYOUT_SENSITIVITY.json`: 채택하지 않은 두 배치의 사이트 headroom/관측 PENDING admission 반례.
- `ACTUAL_EVENT_CAUSALITY_AUDIT.json`: simulator 사건 공개 계약과 실제 스케줄러 watermark 부재를 분리.
- `SITE_RECOVERY_SOURCE_AUDIT.json`, `R0_REFERENCE_SITE_RECOVERY.json`: 1개 이전 모델 사이트의 범위 제한 근거.

이 경계 감사에는 Solver 호출이 없으며 기존 원본·Raw·행렬·실행 원장을 수정하지 않았다. 원본 full96의 Queue 인과성은 아직 인증되지 않았고 기존 B2/B3 및 5월 캠페인 HOLD는 유지한다. 다음 검증 대상은 경로 C 초기 상태의 실제 이벤트·점유·전력·Fresh AC 소비이며, 그 결과는 별도 통합 실행 영수증으로 판정한다.
