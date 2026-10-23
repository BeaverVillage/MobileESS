공식 V2_add 캠페인에서는 사용자의 2026-10-22 추가 지시에 따라 메모리 기반 실행 거부·대기·중단을 사용하지 않는다. RSS 상한, 여유 RAM 하한, 메모리 watchdog을 캠페인 승인 조건으로 사용하지 않으며 Gurobi MemLimit/SoftMemLimit은 모두 양의 Infinity(무제한)이다.

이전 커밋 dbb287498의 "0=무제한" 설명과 검증 주장은 철회한다. 0은 0GB 제한이며, 설치된 Gurobi 13.0.2의 getParamInfo 및 [공식 파라미터 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter:MemLimit)에서 두 기본값이 Infinity임을 확인했다. 공식 Solver 실행 전에 수정했으며 기존 캠페인에는 해당 잘못된 설정이 실행되지 않았다.

RSS, Peak RSS, 프로세스 Commit, 시스템 여유 RAM 및 시스템 Commit은 관측 로그로 남긴다. 원본 Native Runtime 예산·Gap·Thread 정책, Source/입력 SHA 검증 및 Worker 중복 방지 잠금은 유지한다. 이 설정은 공식 캠페인의 실행 승인이 아니다.

현재 Native0 준비 검증에는 기존 RSS 4GiB 및 시스템 여유 5GiB 보호를 유지한다. 과거 보호 중단 기록과 이미 완료한 증거도 보존한다.

실행 Adapter는 `v2_add_preflight.stage_resources.campaign_scope()`에서 공식 정책을 적용한다. 원본 DateBudget의 승인 Context를 먼저 통과한 뒤 Solver의 두 메모리 제한만 해제하며 원본 Solver 함수 본문·원장은 변경하지 않는다. 자식 Worker에서도 이 Scope를 명시적으로 적용해야 한다.

경계 검증: RAM을 실제로 고갈시키지 않고 RSS 128GiB·여유 RAM 0의 관측값을 주입했다. 공식 정책은 이를 수용하고 Native0 정책은 거부했다. 실제 Gurobi Native0 모델에서 MemLimit/SoftMemLimit 해제 및 Threads/TimeLimit/MIPGap 보존을 확인했다. Solver optimize/presolve 호출은 0회다. 결과는 `CAMPAIGN_MEMORY_POLICY.json`에 기록했다. 이 검증은 메모리 정책의 검증이며 전체 Stage 통합 READY를 의미하지 않는다.
