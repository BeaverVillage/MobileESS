V40B의 필수 게이트를 통과하여 Windows Task Scheduler에서 2025년 5월 캠페인을 시작했다. 현재 감독 PID는 35108, 날짜 작업은 4개, 실패는 0개다. 5회의 관측에서 heartbeat와 작업 진행이 증가했고 기존 형식의 모니터 창을 확인했다. 월 전체 계산은 계속 실행 중이다.

V40A 과학 소스 19개와 기존 생산 소스 1,123개를 유지했다. 방법 SHA는 `9af44cb41650c0e3c5643800f6600a4f8e91bb213a775a12b8d4cc47560b584a`, 현재 실행 환경 SHA는 `91266a7c196850a00627af2c1d6e72b721f963742fb1552136cb375fb74563a5`다. A0 → M1_ROUTE_PQ → A1_FEEDBACK → MF_FIXED_ROUTE_PQ, 한 번의 fleet 경로 탐색, 한 번의 A1, 한 번의 MF를 그대로 사용한다. feasible 상태에서 추가 RUNNING 이동을 허용하지 않는다.

| Case | 재사용 인증 | 새 실행 필요 |
|---|---:|---:|
| B0 | 18 | 13 |
| B1 | 18 | 13 |
| B2 | 17 | 14 |
| B3 | 0 | 31 |

15개 완료 날짜와 개별 완료 인증이 존재하는 중단 날짜의 사례를 현재 생산 로더로 읽었다. 53개 사례 모두 fingerprint, 21개 파일 해시, 입력/DA/Planning/Fresh/물리 및 현재 생산 스키마 검사를 통과했다. 단순 progress나 부분 checkpoint는 재사용하지 않는다. 기존 B3는 역사적 순차 방식 결과로만 보존한다.

회귀 날짜는 결과 확인 전에 4월 1일과 가장 이른 완료일인 5월 1일로 선언했다. 현재 beam driver가 해시를 확인한 기존 완료 stage 캐시를 사용하고 Planning과 Fresh를 새로 실행했다. 독립적인 cold optimization 반복이라고 주장하지 않는다. AIDC 결정과 MESS discrete/P/Q/SoC는 정확히 같으며, 수치 비교는 기존 4월 저장 회귀 1e-12와 기존 beam objective 1e-6을 사용했다.

| 날짜 | Case | 결과 | 최대 수치 차이 | 기존 허용오차 |
|---|---|---|---:|---:|
| 2025-04-01 | B0 | PASS | 0 | 1e-12 |
| 2025-04-01 | B1 | PASS | 0 | 1e-12 |
| 2025-04-01 | B2 | PASS | 0 | 1e-12 |
| 2025-05-01 | B0 | PASS | 0 | 1e-06 |
| 2025-05-01 | B1 | PASS | 0 | 1e-06 |
| 2025-05-01 | B2 | PASS | 0 | 1e-06 |

Python 검사 62개와 생산 B3 저장·joint/Fresh/Actual SHA 연결 검사 1개가 통과했다. 저장 연결 검사는 April fixture와 test doubles를 사용한 통합 검사이며 May 과학 결과가 아니다. 기존 모니터 liveness 9개 및 새 단계/양식 54개 검사를 통과했다. 31일 모두 승인된 A0/PCC/terminal/traffic 입력 연결을 solver-free로 확인했다. 누락된 5월 20~31일 D-1 교통 입력은 동결 모델로 생성했다.

첫 detached 실행에서는 Task Scheduler PATH에 Git이 없어 12일의 B3 시작 단계가 영향받았다. A0 완료 이전이며 route search, joint decision, May objective 결과는 0개였다. 감독과 해당 작업을 중지하고 `attempts/01_missing_scheduler_git`에 기록을 보존했다. 수정은 launcher의 Git PATH 지정뿐이다. 동일 Task Scheduler 환경에서 Git, A0 복원, Gurobi 라이선스와 4 threads를 확인한 뒤 재시작했다. 방법 SHA와 53개 baseline 재사용 인증은 유지했다. 변경 영향 및 실행 환경 SHA 갱신은 `V40B_IMPLEMENTATION_REPAIR_01.json`에 기록했다.

새 Task Scheduler 작업은 `MobileESS_V40A_May_20260905_204723`이다. 요청 셸은 종료됐고 실제 계산과 모니터는 Scheduler 계통에서 실행된다. 자동 두 번째 시간 트리거는 비활성화했으며 현재 실행은 유지된다. 한 감독 프로세스, 최대 네 날짜 작업, 각 모델 네 threads 조건을 유지한다. 날짜별 실패는 다른 날짜를 종료하지 않는다. 모든 날짜의 네 사례 인증과 새 B3 31건이 갖춰져야 월 완료다.

기존 May 파일 64,845개, 4,086,616,346 bytes 전체를 기존 보존 manifest와 다시 해시 대조하여 변경 0개를 확인했다. 기존 V39L 자동 재실행은 비활성화 상태이며 기존 순차 캠페인은 재시작하지 않았다.

Fresh는 joint freeze 뒤에만 실행되며 위반 시 기존 fixed-discrete P/Q AC restoration만 적용한다. Actual 검사는 기존 frozen-decision replay identity gate이며 새 물리적 realized-load/traffic 재생을 수행했다는 뜻은 아니다. Optional A0 counterfactual은 실행 지연을 피하기 위해 생략했다. 최종 우월성, A1 효익, 전역 최적성, 통계적 유의성, 월 최종 이동량에 관한 주장은 하지 않는다.

진행 JSON, 날짜 결과, 실행 중 로그 및 실행 matrix는 캠페인이 갱신한다. 이 문서와 SHA manifest는 launch 시점의 동결 증거이며, matrix의 별도 AT_LAUNCH 사본을 포함한다. 각 날짜는 완료 시 자신의 파일 해시를 포함한 독립 인증서를 저장한다.

```text
V40B_PRELAUNCH_COMPLETE = YES
V40A_METHOD_FREEZE = PASS
V40A_METHOD_SHA = 9af44cb41650c0e3c5643800f6600a4f8e91bb213a775a12b8d4cc47560b584a
B0_SOURCE_EQUIVALENCE = PASS
B1_SOURCE_EQUIVALENCE = PASS
B2_SOURCE_EQUIVALENCE = PASS
B0_NUMERICAL_REGRESSION = PASS
B1_NUMERICAL_REGRESSION = PASS
B2_NUMERICAL_REGRESSION = PASS
B0_REUSE_APPROVED = YES
B1_REUSE_APPROVED = YES
B2_REUSE_APPROVED = YES
OLD_B3_REUSE_APPROVED = NO
OLD_B0_REUSED_CASES = 18
OLD_B1_REUSED_CASES = 18
OLD_B2_REUSED_CASES = 17
NEW_B0_RUN_REQUIRED = 13
NEW_B1_RUN_REQUIRED = 13
NEW_B2_RUN_REQUIRED = 14
NEW_B3_RUN_REQUIRED = 31
MESS_FULL_DISCRETE_ROUTE_SEARCH_PASSES_PER_B3 = 1
SECOND_FULL_ROUTE_SEARCH = 0
MAX_PARALLEL_DAY_WORKERS = 4
GUROBI_THREADS_PER_MODEL = 4
DETACHED_LAUNCH_TEST = PASS
MONITOR_LIVENESS_TEST = PASS
OLD_RESULT_FILES_CHANGED = 0
MAY_RESULT_BASED_TUNING = 0
GLOBAL_JOINT_OPTIMALITY_CLAIM = NO
V40A_MAY_CAMPAIGN_LAUNCHED = YES
V40A_MAY_ORCHESTRATOR_PID = 35108
V40A_MAY_HEARTBEAT = PASS
ACTIVE_DAY_WORKERS = 4
FAILED_DATES_AT_LAUNCH = 0
OLD_SEQUENTIAL_CAMPAIGN_RESTARTED = NO
push = NO
PR = NO
```
