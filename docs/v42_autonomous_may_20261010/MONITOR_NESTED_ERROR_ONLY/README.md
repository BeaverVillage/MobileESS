# Monitor의 nested scientific error 표시 수정 증거

`v42_autonomous_monitor/monitor.py`는 SHA 및 날짜/arm 검증을 통과한 `RESULT.scientific.error`를 읽어 날짜별 오류에 표시한다. 기존 최상위 `RESULT.error`와 모니터의 무결성 오류가 우선한다. 원래 worker의 오류 문자열을 그대로 표시하며 PASS 판정, RETRY_PENDING, Native 시간, Global Gap 및 과학 계산을 변경하지 않는다. Root가 보고한 코드 commit은 `46bd8dc8`이다.

## 실제 결함과 검증

수정 전 실제 Source30 May01/02/03은 원본 RESULT에 `PASS:false`, `INPUT_OR_CERTIFICATION_FAILURE`, `scientific.error: PermissionError: RMP_PRESOLVE_ORIGINAL_BUDGET_OR_SCOPE_CLOSURE_DRIFT`가 있었지만 live HTTP의 날짜별 `error`는 null이었다. 세 RESULT의 실제 SHA는 당시 checkpoint의 봉인 SHA와 모두 일치한다. 원본 RESULT를 수정하지 않았다.

Native 모델 생성을 강제로 거부한 검증에서 관련 테스트 **39/39 PASS, 0.76초**, 모델 생성 시도와 Native 호출 0이다. 여섯 개의 추가 검사 사례는 세 날짜의 cached API 오류 표시, top-level 오류 우선순위, scientific 필드가 없거나 잘못된 형식인 경우 및 봉인 SHA 오류의 우선순위를 확인한다. 같은 실행의 actual RESULT 읽기와 Snapshot API 비교도 PASS이며, 세 원본의 SHA와 테스트/소스 SHA가 실행 전후 동일하다. 이 검증은 운영 모니터를 재시작하지 않았다.

최초 pytest 실행은 `--basetemp D:/v42_monitor_error_audit_20261010_01/pytest_tmp`의 부모 폴더가 없어서 **22 PASS + 17 setup ERROR**로 끝났다. 테스트 및 monitor 코드를 바꾸지 않고 감사 디렉터리를 만든 뒤 전체 39개를 다시 실행했다. 최초 실패의 수/원인/exit code는 원래 `tests/MONITOR_SEALED_SCIENTIFIC_ERROR_AUDIT_02.json`의 `earlier_harness_run`에 보존되어 있다. 최초 전체 터미널 출력은 도구 대화에만 있었으며 이 패키지에 raw 파일로 존재한다고 주장하지 않는다. `MONITOR_ERROR_TEST_OUTPUT_02.txt`는 실제 두 번째 전체 실행의 원본 출력이다.

## 모니터만 한 번 교체한 이력

Root의 2026-10-09 21:59:01 UTC 이전 증거와 21:59:23 UTC 검증은 기존 Monitor PID75212/create1791571284.1808343을 정확히 확인한 후 새 PID102084/create1791583141.483806으로 한 번 교체했음을 기록한다. 두 프로세스의 원래 명령과 cwd는 같으며 포트는 `127.0.0.1:8794`이다. 과학 worker와 Supervisor를 종료하거나 재시작하지 않았다. 새 host가 같은 monitor 코드 SHA를 사용하고 실제 HTTP가 원본 오류를 표시함을 읽기 전용 후속 검사로 확인했다.

보존된 helper 세 개는 당시 실행 자료다. 초기 첫 helper의 외부 스크립트 import 경로 오류, 두 번째 실행 시 checkpoint가 가리킨 PID75836의 자연 종료, 세 번째 실행 전 새 Source32 날짜에는 더 이상 과거 `result` 키가 없는 점을 다룬 준비 오류는 모두 운영 프로세스 교체 전에 발생했다. 수정된 `_03` helper가 owned Monitor를 한 번 교체했지만, 새 server receipt가 원자적으로 갱신되기 전 기존 PID를 조회한 시작 경합에서 `psutil.NoSuchProcess`가 밖으로 전파됐다. Root는 helper를 다시 실행해 두 번째 교체를 하지 않았다. 읽기 전용 후속 관측으로 실제 새 host와 HTTP를 확인해 검증 영수증을 봉인했다. 원래 helper들과 Root 검증 영수증을 변경 없이 보존한다. 이러한 초기 helper 오류의 전체 stderr는 도구 대화에 있고, `reload/MONITOR_SCIENTIFIC_ERROR_RELOAD_VERIFICATION.json`에는 구체적 원인과 후속 검증 범위가 기록되어 있다.

Root의 교체 직후 snapshot에서는 May01의 Source32가 RUNNING/error=null이고 May02/03/04의 Source30 실패 오류가 표시된다. 그 뒤 별도 독립 live 검사에서는 May01/02의 Source32가 RUNNING/error=null, May03/04/05의 Source30은 RETRY_PENDING/원래 PermissionError, May06은 RUNNING/error=null이었다. May05가 교체 후 종료되고 May02가 시작된 진행을 서로 다른 시각의 관측으로 구분한다. 새 attempt에 이전 attempt의 오류를 현재 오류로 옮겨 표시하지 않는다. 이전 May01/02/03의 실패 RESULT 세 개는 이후 독립 검사에서도 SHA가 그대로다.

독립 post-reload 감사는 **13개 검사 PASS**이며, 실제 PID/create/cmd/cwd, 소유한 loopback LISTEN, HTTP200/read_only, 테스트된 소스 SHA, 원래 세 RESULT SHA 및 현재 날짜에 속한 오류를 확인했다. Root 교체 증거 시점에 살아 있던 worker의 신원과, 독립 검사 시점에도 살아 있는 worker의 신원을 구분해 기록한다. 이후 PID가 없다는 관측만으로 종료 원인을 증명했다고 주장하지 않는다.

## 파일 보존 범위

이 폴더의 raw 파일은 원래 바이트 그대로 복사했다. `SHA_INVENTORY.json`이 원래 절대 경로와 복사본의 상대 경로/크기/SHA를 연결하고 `SHA256SUMS.txt`가 README 및 인벤토리를 포함한 체크섬을 제공한다. mutable server receipt와 log를 복사한 경우 그 복사 시점의 bytes/SHA를 기록한 것이다. helper는 복사·검토만 했고 이 패키징 과정에서 실행하지 않았다. 13MB RESULT 세 개는 복사하지 않았으며 영수증에 원래 경로와 SHA를 보존한다.

이 패키지는 Source32 과학 코드나 그 문서, queue, manifest, checkpoint, 기존 증거 및 운영 프로세스를 수정하지 않았다. Git 작업/커밋/푸시는 Root가 담당한다. GUI 렌더링, 실제 날짜 최종 과학 PASS, Global Gap 달성 또는 solver 성능 향상을 이 모니터 표시 검증의 결과로 주장하지 않는다.
