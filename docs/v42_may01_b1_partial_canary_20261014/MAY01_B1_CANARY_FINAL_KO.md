# PR228 후속 — May01 B1 제한 Canary

판정: **A1_NO_ACCEPTABLE_INCUMBENT**. 중단 원인: `STAGE_WALL_LIMIT_A1_BUILD_AND_NATIVE`. 원래 A1 생산자의 전체 96슬롯 Domain/Graph 생성에서 준비 단계600초 상한을 소진했다. 실제 Gurobi Optimize에는 진입하지 않았고 Native 비용은 **0.0초**, 본 Attempt 벽시계는 **645.124초**다. 0개 Partial Actual 비교가 실행됐다. 새 통합 성능, 최적성, Full96 및 May31 성과는 인증하지 않는다.

1. 새로운 E1/FLEX30 A1: 원본 생산자를 호출했다. Native Optimize 실행 여부는 원장 calls와 Runtime을 기준으로 판정한다. A1 결과 파일이 없으면 최적화 완료로 주장하지 않는다.
2. FULL-feasible 해: False. UB/LB/Gap은 None/None/None. 없으면 NULL이다. 기존 V5 해를 새 최적해로 사용하지 않았다.
3. 활성 Known 1,546개 중 새 A1/Actual 변경 수는 유효한 결과가 있을 때만 CSV로 보고한다. Source Issue 1,649 UID, Native 대상 1,499 UID를 분리했다.
4. 4시간 Unknown 관측 수: R0–R3 비교 CSV의 실제 관측 값만 사용한다. 미실행이면 NOT_RUN이며 0개의 수요로 해석하지 않는다.
5. Coverage는 PARTIAL_POLICY_COVERAGE다. Issue Known 최빈 Gang 1과 사전 정의 900초 Bucket, 처음 16개 슬롯, 모든 호환 AIDC 12개, Normal/Standby 및 Pending/Running 조건을 사전등록했다. 전체 추정 1,497,600행·37,152,000후보·최소 약38GB이므로 전체 Cartesian Product를 생성하지 않았다. 미래 Unknown UID로 Class를 선택하지 않았다.
6. Unknown 실제 조정 수는 실행 UID CSV와 최종 고유 UID 합집합으로만 보고한다. 미실행 정책의 조정 수는 NOT_RUN이다.
7. 변경 nominal GPUh와 관측 compute GPUh를 분리했다. 미실행이면 NULL이며 기존 PR226의 7.5681 GPUh를 새 결과로 이전하지 않는다.
8. 선택 후 실패는 실제 명령/예약 원장에서만 집계한다. A1 생산 또는 정책 Freeze 이전의 중단을 Unknown 실행 실패로 세지 않는다.
9. Same-row Fallback 구제는 실행된 관측 UID만 비교한다. 과거 Unknown102 전체를 구제했다고 주장하지 않는다.
10. Migration Funnel은 관측된 체크포인트 원장만 사용한다. 시도하지 않았거나 원장이 구분하지 않은 Gate는 NOT_EVALUATED/NULL이며 0건 성공·실패로 채우지 않는다.
11. R3가 실행되지 않았으면 Pre-placement/Migration 대체 관계는 NOT_RUN이다. R3의 전체 정책 효과와 개별 Job 인과 효과를 구분한다.
12. 실제 계통 개선은 실행 및 계통 검증 증거가 없으면 NOT_MEASURED다. Fresh AC rho·전압·Critical-line은 NULL이다.
13. 완료·대기·Partial Carry-out·QoS 비교는 실행된 16슬롯 원장만 사용한다. 04:00/24:00 이후 남은 서비스 자체는 QoS 위반이 아니다.
14. PR228 핵심 7개 파일, 원본 A1 생산자·REAL_DATA Full96 Gate·Fresh AC Source를 변경하지 않았다. 기존 B2 원장1257.5220000743866/1800과 통합원장621.2855198158068/3600은 별도 읽기전용으로 보존했다. 새 B1만 명시적300초 Research 계약에 귀속한다. 이전 Source18r 캠페인·Supervisor·Scheduled Task를 재개하지 않았다.
15. 회귀 **219 PASS** = 기존207 + 새12 계약이다. 초기 새 테스트3건의 SHA 재동결 오류는 수정하고 실패 XML도 보존했다. PR227의 과거29 FAIL/41 ERROR를 해결했다고 주장하지 않는다. 모든 비교는 4시간의 부분 결과이며 Full96/May31 인증은 아니다. 유효한 새 A1이 없으면 R1–R3를 실행하지 않았다.

별도 Native0 개발 검사에서 중복적인 전체 Migration Graph 확장이506.730초 소요되어 본 시험에서는 선언된 전체 Window/Source 검사 뒤 원래 생산자가 Graph를 한 번 생성하도록 했다. 개발 Native0의 별도506.730초를 본 Attempt645.124초 또는 Native0초에 숨기거나 합산해900초 안이라고 주장하지 않는다. 초기 sparse checkout 누락 파일은 복원했고, 테스트 프로세스가 남아 있던 초기 준비 호출은 Worker Gate에서 거부되었다. 모두 Native Optimize 이전의 준비 기록이며, 큰 모델의 Native 재실행은 없었다. Native0를 FULL 모델 인증으로 표시하지 않았다.

현재4시간 결과로 계통 개선 또는 Pre-placement/Migration 대체 관계를 판단할 수 없다. Full96 후속 성능 검증에 앞서, 원본 A1 전체 Domain/Graph의 생성 시간을 줄일 수 있는 동치성 보존 방법을 별도로 검증해야 한다. 이번 요청에서는 Domain을 잘라서 실행하거나 준비·Native 예산을 늘리지 않았다.
