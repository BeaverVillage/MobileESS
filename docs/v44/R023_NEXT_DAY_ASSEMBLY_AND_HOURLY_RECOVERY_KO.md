# r023: 다음 날짜 재조립 개선 및 매시간 Codex 자동 복구

## 배정 상태

2026-10-18 KST 확인: May02 B3 attempt005는 봉인 r022 worker32296/coordinator34976으로 계속 실행한다. 다음 배정은 봉인 r023이며 적용 시작일은 2025-05-03이다. r022u pending은 자연 종료했고 Windows R022U task는 Disabled, R023 task는 Ready, 독립 r023 handover waiter43060이 현재 전체 Case의 자연 종료 경계를 기다린다. 이는 배타적 coordinator lease를 위한 경계이며 A2 PASS를 요구하지 않는다.

현재 미실행 May03~07 B1/B3 총10개 Case에 무조건 적용한다. B1의 실제 A1, B3의 A2 및 공통 B1 A2 경로를 지원한다. B0도 기존 공통 성능 개선 및 재조립 경로를 상속한다. 완료된 PASS와 기존 A1/M1, 원본 Scientific Freeze, Native 원장은 그대로 보존했다. 현재 A2 Native 시계를 초기화하거나 다시 실행하지 않았다.

## 변경과 검증

reference/compact 재조립에서 coupling nonzero마다 전체 행 목록을 재생성하던 부분을 재조립당 한 개 정수 배열로 바꿨다. 클래스마다 큰 빈 글로벌 CSR 행 인덱스를 할당하던 부분은 각 클래스의 coupling nonzero를 모아 하나의 글로벌 coupling CSR로 구성하도록 바꿨다. 클래스/행/열 순서, 계수, bounds, senses, objectives, descriptor, 정확한 projection proofs와 기존 후보 검산은 유지한다. 클래스 캐시와 각 후보의 exact replay, prior inclusion, Full Phi, Full Pricing, Raw primal/dual 검증을 생략하지 않는다.

실제 May02 A2의 전체138개 클래스 및 S11에서 검증된64개 물리 후보 추가 경로를 Native 호출0회로 비교했다. 전체 reference/compact fingerprint, descriptor, projection proofs, metas 모두 동일했다.

| 전체138개 클래스 재조립 | r022u | r023 |
|---|---:|---:|
| 초기 support | 89.51초 | 17.25초 |
| 실제64개 후보 추가 후 | 135.16초 | 29.87초 |

재조립 부분 단일 비교에서 각각 약5.19배/4.52배였다. 전체 A2/캠페인 배속을 의미하지 않으며 신규 생산 날짜의 종료 시간은 아직 측정하지 않았다. 기존 PASS 및 M1 원본 영수증 검산도 통과했다. 회귀250개 PASS에는 비연속/역순/중복 axis, 빈 block, 정확한 CSR bytes, 현재 날짜 보호, 미래 B1/B3 무조건 routing, Source drift 거부, 오류 격리와 다음 날짜 진행이 포함된다.

## 오류가 나도 다음 날짜 진행

Worker의 실패 결과나 launcher/Case 준비 예외는 원본 RESULT/Raw/Native 원장을 보존하고 `R023_REPAIR_QUEUE`에 원인과 영수증을 남긴다. 같은 날짜의 남은 Case는 복구 대기로 격리하고 가능한 다음 날짜를 즉시 선택한다. 수정 근거 없이 같은 오류를 연속 재시도하거나 Case의 기술 오류 하나로 전체 STOP을 만들지 않는다. 실행 중인 child가 있으면 새 worker를 중복으로 띄우지 않는다.

현재 r022 Case가 알려진 A2 기술 오류로 전체 STOP을 남기더라도, 정확한 보호 Case와 일치하고 worker/coordinator가 모두 자연 종료했을 때만 해당 STOP을 별도 보존하고 실패 날짜를 격리한 후 다음 날짜를 배정한다. 다른 사용자 STOP, Source/lease 무결성 문제는 우회하지 않는다. 물리 FAIL을 PASS로 바꾸거나 기준을 완화하지 않는다.

실패 날짜/복구 대기가 남아 있으면 28 PASS나 전체 완료로 보고하지 않는다. 남은 배정이 없더라도 coordinator는 복구 대기를 표시하고 매시간 Codex 진단·수정을 받는다. Source 무결성, OS/디스크/전원 문제까지 무조건 실행을 강제하는 의미는 아니다.

## 매시간 Codex 점검

기존 `v44-may-campaign-autonomous-recovery` 예약을 중복 생성 없이 ACTIVE/매1시간으로 변경했다. 기존 thread 대상은 유지했다. 예약은 active/pending source SHA와 permit, PID/생성시각, lease/lock, Native inflight, 최근 로그/결과를 대조하고 정지·오류를 진단한다. 건강한 느린 solver는 종료하지 않는다. 수정 가능한 오류는 별도 source revision에서 수정·검증 후 안전 경계에서 통합하고, 실패 날짜를 새 Attempt 또는 검증된 동일 날짜 checkpoint부터 재개한다. 이미 PASS한 날짜는 다시 돌리지 않는다. 변경/조치가 없는 점검은 반복 보고하지 않는다.

실패 날짜를 다시 허용할 때는 `R023_REPAIR_RELEASES/<queue파일명>.json`에 `failed_queue_receipt`, `repair_validation`, `execution_permit` 영수증과 `diagnosed_cause_fixed=true`, `allow_new_attempt=true`를 기록한다. 각각 전체 SHA를 검증하고 수정 검증 PASS 및 현재 permit 일치를 요구한다. 기존 실패 marker/RESULT/원장을 삭제하지 않는다. current-source를 고쳐야 하는 복구는 새 revision/permit으로 봉인한 다음 해당 revision을 기준으로 release한다. May02 보호 Case의 새 Attempt 재개는 별도 검증된 revision에서 동일 날짜 parent/Native 정책과 RowGen 적용 범위도 다시 확인한다.

로컬 예약에는 PC 전원과 Codex 앱 실행이 필요하다. 독립 Windows handover/supervisor는 Codex의 대화 응답 종료와 관계없이 실행된다.

## 증거

- OPS/R023_CHANGE_AND_VALIDATION.json, R023_SEALED.json, RECOVERY_R023_EXECUTION_PERMIT.json
- OPS/R023_HANDOVER_GUARD.json, R023_HANDOVER_START.json, R023_HANDOVER_HEARTBEAT.json
- OPS/R023_NEXT_DAY_ROLLOUT_READY.json 및 R023_WINDOWS_TASK.json
- docs/v44/R023_FULL_ASSEMBLY_BENCHMARK.json 및 R023_NEXT_DAY_ROLLOUT_READY.json
- D:/MobileESS_V44/development/r023/regressions.xml:250 PASS
- collector/auditor 실측:13 PASS / 1 RUNNING / 14 WAITING, active r022 / pending r023

PR #233: https://github.com/BeaverVillage/MobileESS/pull/233
