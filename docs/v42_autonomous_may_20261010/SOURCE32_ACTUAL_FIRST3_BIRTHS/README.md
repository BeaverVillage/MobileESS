# Source32 May01·02·03 실제 Native0 시작 증거

Source32 commit은 `6997c0ac54a8d46f345bb99d9b3cf18ffb199a30`, 실행 소스 98개의 SHA는 `9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9`다. 이 폴더는 독립 관측자가 캡처한 실제 새 프로세스의 최초 원장과 그 시점의 request/source/OS 신원 증거를 보존한다. 각 captured birth ledger의 측정 Native Runtime은 0, calls는 빈 배열, inflight는 null이며 원래 Native 예산 5400초 전부가 남아 있다. 새 request의 previous_attempts도 빈 배열이다. 이전 실패의 원장·checkpoint·Native 비용을 새 attempt에 가져오지 않았다.

| 날짜 | 캡처된 PID | 새 attempt | 초기 원장 UTC | 관측 UTC |
| --- | --- | --- | --- | --- |
| May01 | 106760 | repair_b2_v32_01_s3 | 2026-10-09T21:58:25.190624+00:00 | 2026-10-09T21:58:44.985554+00:00 |
| May02 | 95584 | repair_b2_v32_01_s1 | 2026-10-09T21:59:56.397284+00:00 | 2026-10-09T22:00:32.239174+00:00 |
| May03 | 107636 | repair_b2_v32_01_s2 | 2026-10-09T22:02:24.236259+00:00 | 2026-10-09T22:02:34.843102+00:00 |

각 milestone은 당시 실제 PID/create_time/cmdline/cwd=`D:\v42run32`, 요청 bytes/SHA, slot, Source SHA 및 원본 scope admission을 연결한다. **Native0는 위의 캡처 시각에만 해당한다. 현재 또는 이후 Native Runtime이 0이라는 주장은 하지 않는다.** request의 started_UTC는 사전에 준비된 요청의 시각이며 실제 OS 프로세스 생성·원장·관측 시각과 구분한다.

원장의 Native_ceiling_seconds=5400, P2_calls=0, prior_attempt=null, historical_costs_reused=false와 요청의 restart_from_zero=true, previous_attempts=[], native_budget_seconds=5400, target_gap=0.03, Threads=1을 검사했다. 저장 milestone의 PID/cmd/source/요청 및 raw 원장/범위 증거가 합쳐진 독립 consolidated proof와 정확히 일치한다. 패키징 중 D:\v42run32의 immutable 실행 소스 98개를 읽어 SHA를 다시 확인했다. 현재 실행 프로세스나 활성 Native 원장은 이 패키징에서 변경하지 않았다.

이것은 새 attempt가 원본 모델 생성·검증 단계에서 Native0로 시작한 증거다. 캡처된 worker의 UB/LB/Gap은 아직 UNKNOWN이며 초기해의 FULL 검증이나 날짜의 최종 과학 PASS를 주장하지 않는다. 원래 물리/정수/독립 인증/Global Gap 및 Native 예산을 유지한다. 실제 Native 계산 이후의 진행과 최종 PASS는 별도 결과로 검증해야 한다.

raw consolidated proof, authority, 날짜별 milestone, 초기 원장 세 개 및 처음 scope proof 세 개는 원본 bytes 그대로 복사했다. 기존 [SOURCE32 자료](../SOURCE32/README.md)에 있는 세 전체 request와 큰 deployment manifest는 중복 복사하지 않고 `EXISTING_SOURCE32_REQUEST_MANIFEST_REFERENCES.json`에 기존 복사본의 상대 경로/크기/SHA를 기록했다. 원래 관측 증거의 절대 경로는 그대로 유지한다. Native ledger의 현재 파일이 이후 바뀌더라도 이 폴더는 캡처된 최초 bytes를 보존한다.

`SHA_INVENTORY.json`과 `SHA256SUMS.txt`는 복사본/생성 검증 문서의 크기와 SHA를 제공한다. 저장 증거 읽기·검사 및 이 새 docs 폴더 생성만 수행했다. 운영 helper 실행, 생산 파일/API 변경, solver/Native, 프로세스 제어 및 Git 작업은 없다. 기존 Source32 또는 Monitor 문서는 수정하지 않았다.
