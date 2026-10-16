# V43 Rollback 및 Resume

V43 Worktree: `D:/v43_pr189_fast_planning_20261016`. 원본 시작점: PR189 `625bbcb8b9a54a00c1660c26d96f7737c2f75457`. V42.1 freeze 태그는 `v42.1-freeze-20261016`, peeled commit은 `6473cb6dc7360358ff014b3d4bd92586b304383e`다. 외부 봉인은 `D:/v42_1_freeze_bundle_20261016`이며 SHA 검증 결과는 baseline manifest에 있다. 원래 Worktree를 reset하지 말고 별도 복원 checkout을 사용한다.

V42.2 PR231과 기존 미커밋 수정은 `D:/v42_trajectory_tracking_may01_20261014`에 보존되어 있다. 시작 시 관찰한 실행 상태와 원장 참조는 `PRESERVED_V42_STATE.json`에 있다. 오래된 HEARTBEAT의 RUNNING 문자열을 실제 실행 증거로 삼지 않는다.

재개 시 `docs/v43/CHECKPOINT.json`, 해당 attempt의 START/HEARTBEAT/progress/RESULT, `NATIVE_RUNTIME_LEDGER.json`과 실제 PID·생성시각을 함께 확인한다. 살아 있는 Worker가 있으면 소스를 수정하거나 두 번째 solve를 시작하지 않는다. Worker는 original Native90 전역 슬롯 3개와 unified heavy lock 및 V43 lock을 소유한다.

정상 중지가 필요하면 해당 attempt에 `STOP_REQUESTED.json`을 만든다. 진행 중 Native 콜백에서는 terminate 요청 후 실제 Runtime을 정산하고, 다음 호출은 거부한다. 준비 단계에서는 다음 budget check에서 멈춘다. `RECONCILIATION.json`을 확인하기 전 원장이나 출력을 재사용하지 않는다.

호스트 중단 중 inflight Native가 있었다면 Runtime을 0으로 추정하지 않는다. 원본 로그·원장을 보존하고 불명확 구간을 표시한 별도 정산을 만든다. 실패 attempt를 덮어쓰지 말고 새 번호·새 Native=0 원장으로 비교군 처음부터 재시작한다. 지원 파일 누락은 Git 원본 blob에서 동일 바이트로 복원하고 새 freeze/회귀/commit을 만든다.

Gate 순서: A(PR189 재현) → B(Unknown C0/C1) → C(MESS) → D(May01 네 비교군) → May31. 실행되지 않은 결과는 NOT_RUN, 미인증은 NOT_CERTIFIED다. 모든 후속 Gate가 확인되기 전 월간 캠페인을 자동 시작하지 않는다.
