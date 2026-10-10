# B3 향후 검증 — 이번에는 실행하지 않음

모든 항목의 현재 상태는 `DEFERRED_RESOURCE_PROTECTION` 또는 `NOT_RUN`이다. B1/B2 실행 중에는 B3 Native production이나 대규모 preflight를 시작하지 않는다. 별도 B3 실행 승인과 원본 stage-correct bridge 구현/검토 후 순차 검증한다. 이 목록은 실행 승인이 아니다.

| 검증 대상 | 현재 상태 | 향후 필요한 증거 |
|---|---|---|
| 실제 A1 → M1 anchor 변환 | DEFERRED_RESOURCE_PROTECTION | 같은 날짜의 full job decisions, 원본 GPU/known_gpu·IT·PCC P/Q materializer, source/input/replay SHA 동일성 |
| 실제 M1 → A2 원본 모델 | DEFERRED_RESOURCE_PROTECTION | 고정 route/location/Pch/Pdis/Q/SOC·이동 에너지를 원본 A grid·pricing·정수/물리 검증에 반영한 모델 |
| 실제 A2 → M2 원본 모델 | DEFERRED_RESOURCE_PROTECTION | A2 anchor 고정, 실제 M2 stage routing, original variable families/원본 transport/voltage row 유지 |
| FULL/Compact/C3A 동치성 | NOT_RUN | 모든 original row/box/목적 및 exact transport proof, stage-specific model SHA |
| 정수/원본 물리 완전성 | NOT_RUN | GPU/Rack/WAN/QoS/service/PCS/배터리/차량/traffic/charger/SOC/계통 replay와 full variable coverage |
| Native LP/MILP/QCP·pricing 회귀 | DEFERRED_RESOURCE_PROTECTION | stage-correct 원본 solver adapter, complete pricing, integer recovery, strict UB/global dual 검증 |
| 단계별 exact Global LB/UB | NOT_RUN | 같은 stage·date·fixed input·model·decision에 대한 독립 증명, A 0.5% / M 3%, P2=0 |
| Planning freeze/Actual/Fresh AC | NOT_RUN | 원본 freeze/unknown arrival/CC4/runtime causal authority, frozen controls 보존, repair=0, 실제 fresh OpenDSS 물리 검증 |
| B0/B1/B2/B3 동일 May 날짜 공정성 | NOT_RUN | 동일 원본 입력·forecast vintage·grid/NormalAmps·전압·PCC/차량/traffic·runtime/QoS authority |
| 31일 B3 Production | DEFERRED_RESOURCE_PROTECTION | 별도 승인, 날짜별 immutable ledger·실패 격리·checkpoint·독립 인증·actual AC 결과 |
| 전체 Scientific Regression | DEFERRED_RESOURCE_PROTECTION | 원본 scientific regression 전체 목록과 영향 검사, full suite 별도 실행 |
| 실제 Runtime 및 Peak RSS | NOT_RUN | 각 stage optimize Runtime 5400s ceiling, 실패 Runtime/unknown quarantine, build/인증/Actual/Fresh wall 분리, 실제 peak RSS 측정 |

현재 작은 합성 fixture의 Gap은 시험 문자열이며 실제 성능 수치가 아니다. 4개의 조건부 Global Gap은 전체 공동 MILP의 전역 최적성 증명이 아니다. 과거 May01/May12의 해·LB·UB·Runtime을 새 날짜나 단계 인증에 사용하지 않는다.
