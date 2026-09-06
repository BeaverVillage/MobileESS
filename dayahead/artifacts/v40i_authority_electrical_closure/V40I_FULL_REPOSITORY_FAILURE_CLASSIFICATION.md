# 전체 저장소 테스트 실패 분류

전체 저장소 2,200개 결과는 2,132 PASS, 55 failures, 9 errors, 4 skipped다. 전체 PASS로 보고하지 않는다. 실패/error 64개는 V40I 이전 H 커밋 67458be58fa5923fa27c566b1d9ff77d9d10ec0c의 독립 체크아웃에서 모두 다시 실패했다.

실패 test와 traceback에 등장하는 저장소 Python 소스는 H와 byte 동일하다. 초기 baseline의 실패 지점이 달랐던 V39H 3개는 H 코드를 유지하고 현재의 기존 artifact fixture를 읽도록 한 별도 pytest plugin에서 동일 실패를 재현했다. 이 실행의 V40I import는 0개다. 소스를 바꾸거나 과거 테스트를 통과시키기 위한 환경 설치·artifact 교체는 하지 않았다.

V33만의 문제가 아니다. 누락된 Torch, Windows POSIX-locking 부재, 과거 branch/HEAD 강제, legacy cache/결과 누락, 과거 봉인 hash/size 불일치와 V39H 상태 불일치도 포함한다. 환경 문제만 UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE로, 실제 기존 assertion/state/artifact 문제는 별도 분류했다. PFR synthetic QCP assertion의 더 세부적인 수치 원인은 미확정이며 환경 누락으로 단정하지 않았다.

| 분류 | 수 |
|---|---:|
| UNRELATED_PREEXISTING_TEST_ENVIRONMENT_FAILURE | 52 |
| UNRELATED_PREEXISTING_FROZEN_ARTIFACT_FAILURE | 8 |
| UNRELATED_PREEXISTING_LEGACY_STATE_FAILURE | 3 |
| UNRELATED_PREEXISTING_LEGACY_TEST_FAILURE | 1 |

각 test name/version/cause/V40I dependency/baseline reproduction/environment 구분과 원문 오류는 JSON 및 CSV에 모두 기록했다. 필수 V40H 106 + 기존 V40I 60의 166개 PASS를 사용자 승인 scope로 사용하며 이후 추가된 회귀도 함께 요구한다.
