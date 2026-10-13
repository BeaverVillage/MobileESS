# May01 자정 공통 초기상태 복구 — Native0 검증

May01 00:00 AEST의 연구용 공통 초기조건을 완성했다. 초기조건의 상태는 `DDAY_INITIAL_STATE_AUTHORIZED`이며, 사이트와 대기열의 권한 범위는 `MODEL_ASSUMPTION`이다. 실제 Kestrel 12 AIDC 위치나 시설별 대기열을 관측했다는 의미가 아니다.

- RUNNING 324개/472GPU를 보존했다. 기존 사이트가 있는 151개/296GPU의 사이트 변경은 0이다.
- PR129 동결 Reference와 324개를 대조했다. 301개 UID가 존재하고 23개 자정 이전 도착 UID는 없었다. 기존 151개 중 103개는 과거 Reference 사이트와 달랐으므로 현재 사이트를 유지했다.
- 사이트 미확정 150개 전체의 과거 배치를 가져오면 AIDC06/07/08이 용량을 초과한다. 이 세 그룹은 전체를 채택하지 않았다. 10개 재사용 조건과 공동 용량 검사를 통과한 AIDC01 5개, AIDC05 15개, 총 20개/20GPU만 재사용했다.
- 남은 153개/156GPU는 변경하지 않은 PR125 `v42_capacity.reference.build_reference`로 배정했다. 자정 RUNNING만 입력했고, 고정 사이트를 먼저 고정한 뒤 원본 결정론적 사이트 순서를 사용했다. 전력계통·MESS·미래 완료시각은 배치 선택에 사용하지 않았다.
- PENDING 1,300개/1,313GPU 전체를 관측된 제출시각, UID 순서로 보존했다. `COMMON_GRID_BLIND_FCFS_QUEUE_V1`을 공통 연구용 대기열로 사용하며, 초기 admission이나 Apr30 18:00~24:00 운전을 재생하지 않았다.
- 이미 완료된 44개/59GPU는 제외 원장에 보존했다. 활성 RUNNING과 대기열에 없고, Unknown 재등록과 CC4 중복 차감은 0이다. 자정까지 완료된 전체 178개는 역사 기록으로 유지한다.

12개 AIDC의 초기 사용량은 80, 40, 69, 28, 65, 53, 24, 54, 0, 41, 14, 4GPU이다. 각 사이트의 원본 용량과 비가산 논리 Rack의 작업별 whole-gang 호환성을 만족한다. 이 초기 RUNNING 집합을 해제하지 않고 같은 사이트에 96슬롯 유지하는 보수적 용량 검사도 PASS이다. 자정 이후 admission과 migration은 별도 Actual의 순간 용량 검사를 통과해야 한다.

네 Arm의 공통 초기 상태 SHA는 `5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573`, 전체 Freeze SHA는 `f90d2f64be0efaa76884f7d3b63b22fd7d7cf9caad2242653354be9f29adb6f2`이다. 이전 자정 candidate의 `e018c86a…7f61a`와 과거 합성 preday 배치 파일은 삭제하지 않는다.

추가 초기화 회귀 9개가 통과했다. 독립 검토는 23개 Freeze source/policy receipt, 네 Arm reload, 두 SHA의 독립 재계산, 20개 재사용 작업의 직접 UID/Episode/Source 대조와 10개 조건, PR129의 14개 receipt 및 12개 정확한 Git blob 증거를 확인했다. 초기화와 독립 검토의 Native Optimize, Actual, Fresh AC 실행은 모두 0이다.

Planning은 Apr30 18:00 당시 입력을 유지한다. Actual의 평가 구간은 May01 00:00~24:00 AEST, 96개 15분 슬롯이다. 자정까지 발생한 사건은 초기상태 감사에만 사용하며, 자정 이후 완료와 실제 남은 서비스는 Simulator 내부에만 둔다. 자정 이전부터 실행 중인 작업은 PENDING으로 바꾸거나 과거 배치를 다시 실행하지 않는다.

이 문서는 초기조건 검증 결과다. 새 Case의 A/M 최적화·실제 96슬롯 전력·Fresh AC PASS를 인증하지 않는다. Freeze 생성 시 이 결과들은 `NOT_RUN`이며 이후 독립 실행 결과를 참조해야 한다. 과거 PR129 B0의 Actual·AC와 과거 PR220/PR222 UB는 새 Case 결과로 자동 이전하지 않는다. PR222 Warm/Cold 결과와 기존 공유 Solver 비용은 그대로 보존한다. B2/B3 캠페인 HOLD, 기존 모니터와 자동 재시작 차단, 사용자 승인 전 5월 전체 캠페인 금지는 유지한다.

공통 Freeze와 초기화 증거는 `D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/`의 `V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json`, `INITIAL_SITE_PROVENANCE_LEDGER.csv`, `DDAY_INITIAL_QUEUE_LEDGER.csv`, `INITIAL_STATE_CAPACITY_AUDIT.json`, `INITIAL_STATE_CAUSALITY_AUDIT.json`, `FOUR_ARM_COMMON_INITIAL_STATE_AUDIT.json`에 저장했다.
