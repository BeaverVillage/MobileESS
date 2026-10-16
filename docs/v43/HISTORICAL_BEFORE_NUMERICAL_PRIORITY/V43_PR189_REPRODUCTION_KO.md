# V43 PR189 재현

상태: Gate A HOLD — 원본 GFS06Z의 cutoff 이후 공개 기록 확인. 신규 PASS를 주장하지 않는다.

PR189 exact HEAD `625bbcb8b9a54a00c1660c26d96f7737c2f75457`에서 별도 Worktree와 `codex/v43-pr189-fast-planning-unknown-presite` 브랜치를 생성했다. 이전 결과 약 6GB는 sparse checkout에서 제외했다. 정책·입력 지원 파일만 원본 Git blob에서 선택적으로 복원했다.

May01 실제 실행의 `A_NATIVE_SOURCE_FREEZE.json`에 있는 11개 소스·정책 파일은 PR189 blob과 바이트 SHA가 일치한다. Windows 체크아웃 줄바꿈 변환은 Git 원본 바이트로 복원했다. 실행 경로는 May01에 실제 쓰인 `v42_may_campaign_native90.a_stage.run`이다. 날짜별 V10 정밀도 복구 경로를 May01에 강제로 적용하지 않는다.

동일 NATIVE_INPUT SHA는 `365824518d8b3d380b6e2cc72a78d19d27ce8d39d304acdc8ffc5b5806b342fc`, WINDOWS SHA는 `5aec44479490ea00c0532f87229850507623b3d365fcdfbd6b105208dc8317a8`이다. 전체 Known 1,649개는 `2025-04-30T08:00:00Z` 즉 AEST D-1 18:00 이전 제출을 확인했다. 원본 양의 서비스 모델은 1,499 UID, 117 Class다. 새 모델을 만든 뒤 원본 snapshot fingerprint와 비교한다.

과거 참고값은 Native 97.472초, Phase I 63.820초, UB 0.6718471055537026, LB 0.6715871456570585이다. 모두 HISTORICAL_BASELINE이며 신규 결과가 아니다. 준비 시간은 과거 1,098.747초로 Native 시간과 별개다.

V43는 원본 Fast Active Domain, SUM/Hybrid, Row Generation, 전체 Pricing, Integer Restoration 및 FULL replay를 호출한다. Source/입력 freeze, Worker1/Threads1, 공유 Native 5,400초, 원래 수치 정책을 보존한다. V42.2의 Phase I 900초 제한 및 D0/E1/FLEX30 모델은 이식하지 않았다.

Golden의 기존 fixed Actual replay/Fresh AC96은 원본 재현의 일부다. 이벤트 기반 Unknown C0/C1 검증과 prefix 상태 연속성 인증은 Gate B에서 별도로 수행해야 한다. 기존 fixed replay를 새 Unknown 제어 검증으로 표시하지 않는다.

## 실제 실행과 인과성 거부

2026-10-16 Golden attempt001은 원본 입력 로더·전기계수 96슬롯·120 변압기 상·Known/Q50/CC4 Native0 검증 후 새 모델 준비를 시작했다. 원본 GFS 06Z f008/f032 객체에 대한 공개 HEAD의 ETag가 보존된 manifest와 정확히 일치했다. Last-Modified는 각각 2025-04-30 09:35:44 UTC, 09:41:30 UTC로 cutoff 08:00 UTC 이후다. 이는 초기화 06:00 UTC만을 근거로 발행·가용성 PASS를 선언할 수 없다는 실제 출처 증거다.

공식 Stop을 요청했고 Worker는 2026-10-16 11:20:59 KST에 종료됐다. 새 Native 호출 0회, 소비 0초, inflight 없음, 총 Wall 132.525초다. 부분 모델 준비, 원본 worker 결과 및 원장은 모두 보존했다. 원본 wrapper의 중지 예외 분류는 IMPLEMENTATION_FAILURE이며, 정확한 원인 분류는 별도 `GOLDEN_ATTEMPT001_CAUSAL_STOP_CLASSIFICATION.json`의 OFFICIALLY_STOPPED_CAUSAL_INPUT_REJECTED다. 원본 Raw를 고쳐 쓰지 않았다.

기존 소스와 동일 입력의 수치적 비교는 완료되지 않았다. 이 중지를 모델 infeasible 또는 solver 성능 실패라고 해석하지 않는다. Unknown/MESS 통합과 월간 실행은 Gate A 미달 상태에서 시작하지 않는다.

## 승인된 범위의 입력 복구

동일 날짜 00Z f014/f038 객체는 03:42:45/03:48:47 UTC로 cutoff 이전임을 확인했다. 별도 V43 폴더에서 f014~f038의 150개 필요한 메시지만 byte range로 확보하고, 모든 객체 공개 시각/ETag/정확한 range/바이트 SHA를 검증한다. 기존 GRIB decoder와 습도·습구온도·15분 보간 공식을 그대로 사용한다.

이 날씨를 원래 certificate의 경로만 바꿔 끼우지 않는다. C1, B0 anchor, 전기계수를 새 Case로 재생성·검증해야 한다. 이는 원본 PR189와 입력이 다른 인과성 복구 Case이며, 과거 UB/LB·평균 68.7%나 기존 인증을 이전할 수 없다. PR189 AIDC 수학 모델·수치정책은 그대로 유지한다.
