# V43 PR189 재현

상태: Gate A NOT_RUN. 신규 PASS를 아직 주장하지 않는다.

PR189 exact HEAD `625bbcb8b9a54a00c1660c26d96f7737c2f75457`에서 별도 Worktree와 `codex/v43-pr189-fast-planning-unknown-presite` 브랜치를 생성했다. 이전 결과 약 6GB는 sparse checkout에서 제외했다. 정책·입력 지원 파일만 원본 Git blob에서 선택적으로 복원했다.

May01 실제 실행의 `A_NATIVE_SOURCE_FREEZE.json`에 있는 11개 소스·정책 파일은 PR189 blob과 바이트 SHA가 일치한다. Windows 체크아웃 줄바꿈 변환은 Git 원본 바이트로 복원했다. 실행 경로는 May01에 실제 쓰인 `v42_may_campaign_native90.a_stage.run`이다. 날짜별 V10 정밀도 복구 경로를 May01에 강제로 적용하지 않는다.

동일 NATIVE_INPUT SHA는 `365824518d8b3d380b6e2cc72a78d19d27ce8d39d304acdc8ffc5b5806b342fc`, WINDOWS SHA는 `5aec44479490ea00c0532f87229850507623b3d365fcdfbd6b105208dc8317a8`이다. 전체 Known 1,649개는 `2025-04-30T08:00:00Z` 즉 AEST D-1 18:00 이전 제출을 확인했다. 원본 양의 서비스 모델은 1,499 UID, 117 Class다. 새 모델을 만든 뒤 원본 snapshot fingerprint와 비교한다.

과거 참고값은 Native 97.472초, Phase I 63.820초, UB 0.6718471055537026, LB 0.6715871456570585이다. 모두 HISTORICAL_BASELINE이며 신규 결과가 아니다. 준비 시간은 과거 1,098.747초로 Native 시간과 별개다.

V43는 원본 Fast Active Domain, SUM/Hybrid, Row Generation, 전체 Pricing, Integer Restoration 및 FULL replay를 호출한다. Source/입력 freeze, Worker1/Threads1, 공유 Native 5,400초, 원래 수치 정책을 보존한다. V42.2의 Phase I 900초 제한 및 D0/E1/FLEX30 모델은 이식하지 않았다.

Golden의 기존 fixed Actual replay/Fresh AC96은 원본 재현의 일부다. 이벤트 기반 Unknown C0/C1 검증과 prefix 상태 연속성 인증은 Gate B에서 별도로 수행해야 한다. 기존 fixed replay를 새 Unknown 제어 검증으로 표시하지 않는다.
