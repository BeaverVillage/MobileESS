# V43 공식 재개 절차

Worktree D:/v43_pr189_fast_planning_20261016, Draft PR232. 원본 PR189 base 625bbcb8b9a54a00c1660c26d96f7737c2f75457, V42.1 freeze tag v42.1-freeze-20261016의 peeled commit은 6473cb6dc7360358ff014b3d4bd92586b304383e다. D:/v42_1_freeze_bundle_20261016과 V42.2 원본/미커밋 작업을 보존한다. 원본 Worktree를 reset하지 않는다.

최신 권한은 OFFICIAL_EXECUTION_POLICY.json과 USER_STEERING_PR189_NUMERICAL_PRIORITY.txt다. CHECKPOINT와 현재 attempt의 START/HEARTBEAT/progress/RESULT, 실제 PID·생성시각 및 NATIVE_RUNTIME_LEDGER를 함께 확인한다. 살아 있는 worker의 source를 수정하거나 중복 solve를 실행하지 않는다. 필요 시 attempt/STOP_REQUESTED.json을 만들고 RECONCILIATION을 확인한 뒤 새 독립 attempt로 재개한다. 이전 Native 소비나 불명확 구간을 삭제하지 않는다.

Golden001 중지/Native0 원장은 보존했다. Golden002가 현재 공식 실행이다. GFS06Z 및 기존 C1/전기계수, D-1 18:00 AEST를 유지한다. GFS 공개시각은 NOT_CERTIFIED로 별도 보고하며 이를 이유로 수치 재현을 HOLD하지 않는다. 개별 미래 Unknown UID/실제 도착/Runtime/Completion은 차단한다.

GFS00Z 복구와 C1/B0/전기계수 재생성은 사용자 지시로 공식 중단됐다. 해당 파일·코드·오류·원장은 역사적 자료다. NEXT_ELECTRICAL_REPAIR_RECIPE.md는 폐기된 작업 방향의 기록이며 실행 지시가 아니다. 새 GFS 다운로드나 전기계수 재생성을 하지 않는다.

기존 자동 감독 v43-pr189는 10분마다 Golden과 실제 오류 복구를 확인한다. 상태 변화가 없으면 알림을 생략한다. 수치 재현 성공 후 Unknown C0/C1, 최신 K48/Beam/4-MESS Joint, May01 네 비교군 및 전체 5월 캠페인을 계속한다. 검증된 동일 Source/Case 증거는 SHA로 재사용하고 중복 빌드·테스트를 최소화한다. Main merge는 금지한다.
