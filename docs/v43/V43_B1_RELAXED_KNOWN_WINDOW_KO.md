# B1 Known 허용창 연구 정책 — IMPLEMENTED_NOT_EXECUTED

정책: `B1_RESEARCH_RELAXED_KNOWN_WINDOW_V1`. **코드 구현과 단위 테스트만 완료했다.**
Planning 재계산 0회, 새로운 Actual96/Fresh96/Canary/최적화/전체 캠페인 0회.
현재 실행 중이던 B2 Attempt002는 중단하지 않았으며, 변경 파일은 해당 Worker의 동결 Source와 겹치지 않는다.

## 원인과 시작 처리

기존 결과의 414개 Known 거부는 `_known_decision()`의 `PLAN_OUTSIDE_AUTHORIZED_WINDOW` 검사 때문이다.
UID 8632559의 기존 18:00 허용창과 Golden003 18:30 선택 사례를 단위 테스트로 재현했다.
새 연구 정책은 별도 Controller에서 membership을 실행 차단에 사용하지 않는다. Original FULL 도메인 소속 검사를 추가하지 않는다.
Golden003의 Site/Start와 Planned Migration 명령은 복사 동결 상태로 보존한다.
실제 실행 기준은 `max(Planning Start, 현재시각, Submit, 관측시각, release, hard earliest)`이며,
15분 제어시각에만 시작한다. 계획보다 일찍 실행하지 않고, 시작 전에는 PENDING을 유지한다.
GPU/확정 예약 부족 시 QUEUE하고 후속 제어시각에 재시도한다. 새로운 시간 이동 최적화 또는 Known Corrective Pre-site는 없다.
기존 시작 시각이 D-day 경계보다 이르더라도, 미관측 과거 START를 재현하지 않고 현재 관측 이후의 실행만 시도한다.

## Deadline 사후 측정

Known 시작 직전 Hard Latest/예상 완료 Deadline 차단만 연구 정책에서 생략한다.
원본 WINDOWS, metadata Deadline, QoS Receipt는 변경하지 않는다.
`KNOWN_RESEARCH_WINDOW_ASSUMPTION`은 원래 허용 시작 목록, 계획 membership, Deadline, 원본 Receipt SHA를 남긴다.
`KNOWN_RESEARCH_QOS_MEASUREMENT`는 UID별 실제 START/COMPLETION, 계획 대비 대기,
실제 시작 membership, Hard Latest 초과초, 시작 자체의 완료 Deadline 초과초와 실제 완료 Deadline 초과초를 남긴다.
미관측 완료값은 null이며 예측 완료로 대신하지 않는다. QoS PASS는 `NOT_CLAIMED`이다.
Known의 기존 계획 Migration에서는 사본 metadata를 사용해 완료 Deadline만 측정 대상으로 전환하고,
원래 capability·checkpoint·WAN·공유 중단예산·예약·Current AC 검사를 유지한다.
계획보다 늦은 START는 기존 체크포인트를 재계산하거나 강제 Migration하지 않고
`KNOWN_DELAYED_START_INVALIDATES_PLANNED_CHECKPOINT`로 STAY 사유를 기록한다.

## 적용과 불변 범위

`CorrectiveBinding` 및 Corrective driver에 선택 인자 `known_window_policy`를 추가했다.
기본값 None은 기존 Controller를 그대로 선택하며, 정확한 정책 ID를 명시한 B1만 새 Controller를 선택한다.
B0/B2/B3에 이 연구 정책을 지정하면 거부한다. Case SHA와 새 Source freeze에는 연구 가정을 별도로 결합한다.
실행 명령은 이번 작업에서 호출하지 않았다. 후속 별도 지시 전 May01 실제 재실행을 하지 않는다.

GPU/Rack/호환성, 다른 UID의 확정 예약, 실제 RUNNING Overrun, WAN, Planned Migration 물리 조건,
전압 0.95~1.05 pu, 선로·변압기 정격, Current AC는 그대로 유지한다.
Unknown의 허용창·QoS·Signed Sensitivity·R1 참여자 Hash·R1_ASSUMED·Pre-site 알고리즘은 수정하지 않았다.
기존 185개 Unknown 실제 Pre-site START 결과는 보존했다.

## 경량 검증

**23 tests PASS**, 정적 AST parse 및 diff whitespace 검사 PASS.
`run_actual`, 실제 AC, Native solver, Heavy Lock은 사용하지 않았다. 작은 모형 Controller 메서드 테스트만 수행했다.

- UID 8632559 membership 완화, 기존 Strict 거부 유지.
- GPU 부족/실제 Overrun → PENDING QUEUE → 해제 후 START, 동일 tick 중복 GPU 사용 방지.
- 다른 UID의 확정 예약 보존, Site 호환성/Rack/Current AC/선로/변압기 차단 유지.
- Hard Latest 및 완료 Deadline 초과를 START/COMPLETION 관측 후 기록, 원본 값·Receipt SHA 유지.
- Submit/관측/Planning Start/release/hard earliest 이전 START 금지.
- Unknown Deadline 거부 결과 동일, C1 Unknown Pre-site START·참여자 Hash 동일.
- 새 admission AST는 기존 admission 대비 Known Deadline 조건 하나만 변경됨을 검증.
- 동결 Site/Start 수정 시 거부, 지연된 Known의 Planned Migration 강제 실행 금지.
- B0/B2 기본 선택 경로 유지, 연구 정책의 비-B1 선택 거부, 정책이 다른 Carryout 혼입 거부.

보존 확인: 역사 Raw·보호 Source 2405개 기록의 크기/mtime 및 주요 원장·결과 SHA가 동일하다.
B2 동결 Source 1324개 SHA를 통합 후 확인했고 변경 0개이다.
Golden003 UB 0.6718471055537026 / LB 0.6715871456570585 / Gap 0.0386933% 보존.
기존 B1 C0/C1, B0 FCFS 및 Raw 원장을 덮어쓰지 않았다.

정책 Source SHA256: `8285adf3350187f7c6eb93a5c2c0492ee04f190b56ad94c4f14f54d7f0a75d84`
Adapter Source SHA256: `de5828aafeb1d1470004fab1f86457c0ef8365f6883a6d3df1de20435dfbf9a5`
파일별 SHA와 테스트 XML은 동명 JSON에 기록했다. Commit SHA는 이 보고서와 코드를 포함한 Git commit으로 식별한다.

**414개 실제 START를 검증하지 않았으며 Known Service Equivalence는 NOT_CERTIFIED이다.**
