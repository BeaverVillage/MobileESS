# 최종 검토

PR #117 exact head `e2d4779685fff6d0cf022c649733b2ca41fdfc08`에서 분기했다.
이번 변경은 V42 architecture supersession이며 V41의 historical Day-Ahead
AC Validation을 오류로 재해석하지 않는다. 기존 evidence 및 report를 수정하지
않고 보존 감사에 원본 Git blob SHA와 현재 raw-byte SHA256을 기록한다.

운영구조: D-1 입력/forecast freeze → A1 → M1 → A2 → M2 전체 Day-Ahead
Planning → immutable final planning freeze → realized load/PV/AIDC state를
이용한 D-Day Actual 물리 배열 재구성 → Fresh OpenDSS 검증.
M2 종료 직후 Fresh AC 호출은 제거했다. Planning 반환에 Fresh AC PASS를
요구하지 않는다. 계획·정책·grid SHA를 저장하고 재로드 시 검증한다.

Actual은 frozen known-job schedule, route, movement, charge mode, P, Q,
SOC 및 authority를 변경할 수 없다. 로컬 P/Q repair와 global reoptimization
요청은 callback 진입 전에 거부한다. 변경된 reconstruction은 AC 전에 거부한다.
Actual 경로의 AC 호출은 한 번이며 receipt가 plan/grid/policy, 실현 입력,
물리 배열 SHA와 DDAY_ACTUAL 계층을 일치시켜야 한다. 실패는 원본 receipt와
함께 FAIL로 남기고 계획을 rescue하지 않는다.

전압 authority는 A1 기존 bootstrap 0.95–1.05 pu, M1/A2/M2 robust
0.955–1.045 pu, Actual Fresh AC 0.95–1.05 pu를 그대로 유지했다.
라인 전류·변압기 전류·변압기 kVA 위반도 각각 0이어야 한다.

현재 checkout에는 final response/event kernel 생성기가 없다. 기존
`require_kernel` 게이트에 DDAY_ACTUAL 계층을 추가하고 새
`require_dday_kernel`에서 전체 Actual 및 frozen upstream SHA를 검증한다.
Planning 완료만으로 kernel을 생성하거나 freeze하지 않는다.
기존 `KernelAnchor`는 causal policy anchor 일치 검사이며 생성기가 아니다.
새 ML 또는 unknown-job authority를 만들지 않았고 unpromoted provider는
기존 fail-closed 동작을 유지한다.

기존 보존 테스트는 새로운 source SHA 허용 목록으로 이번 architecture
supersession을 확인하며, 원래 historical manifest는 바꾸지 않았다.
기존 Benders production 바이트 게이트는 그대로 유지하고 이 successor
브랜치에서 닫힘을 검사한다. 소형 synthetic 테스트만 read-only snapshot
감사를 fixture로 사용한다. 외부 모델 캐시는 기존 historical SHA를 확인한
파일을 읽으며, 한글 경로 문제는 테스트 fixture에서만 실제 경로로 해결했다.

테스트 결과는 TEST_RESULTS.xml, 집계·raw-byte hash·diff 검증은
VERIFICATION.json에 저장했다. fake adapter와 기존 소형 synthetic fixture
테스트는 production 실행 및 Fresh OpenDSS scientific PASS의 증거가 아니다.
신뢰된 물리/OpenDSS backend의 숨은 부작용을 sandbox하는 API는 아니며
production adapter의 전기 매핑·실측 readback authority는 별도 책임이다.

V42_DAYAHEAD_PLANNING=true,
V42_SEPARATE_DAYAHEAD_AC_VALIDATION=false,
V42_DDAY_FRESH_AC_VALIDATION=true.
ACTUAL_FULL_REOPTIMIZATION=false,
ACTUAL_P_CORRECTION=false, ACTUAL_Q_CORRECTION=false.
M1_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false.

B0/B1, 새로운 M1 Benders 연구, A2/M2 production, Actual production,
Fresh OpenDSS production, 새 margin/ML은 모두 NOT_RUN.
Problem 13은 robust margin만으로 realized uncertainty에서 고정 계획이
로컬 P/Q repair 없이 Fresh AC를 통과하는지 묻는 운영질문으로 고정했다.

최종 회귀 결과: 871 PASS (새 계약 테스트 83 + 기존 테스트 788), failure/error/skip 0.
