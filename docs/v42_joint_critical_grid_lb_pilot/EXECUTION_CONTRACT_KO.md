# Joint16 단일 Native 계약

이 연구 브랜치는 PR209 `9383a99f1bdcabbd49c79b3ad9f9ee36d523868a`에서 시작한다. 롤백 Source18r은 PR207 `497609b46faa14ea7e32a9483a333ab32fd264ef`이다. 사용자 후속 요청에 따라 PR209의 NONMATERIAL 결론 이후 새 Joint 실험을 단 한 번 수행한다.

기존 K16을 각각 같은 rho에 적용하며 평균으로 대체하지 않는다. 저장된 Source18r Node-Activity Compact와 정확한 Static Presolve/C3A 증명을 재사용한다. FULL 가능해를 제거하는 새 경로 고정·삭제·Bound 강화는 없다. 저장 FULL 행렬을 SHA 확인용으로만 읽었고 FULL 모델 재생성은 0회다. 첫 Native0 시도에서 저장 요약의 PASS 필드 스키마 차이를 만났으며 BUILD_FAILURE.json에 보존했다. 이는 Optimize 전에 발생한 오류로, 필드 경로를 바로잡은 두 번째 추출·SHA 확인이 PASS했다. C3A 배열을 읽고 물리 행을 추출한 프로세스는 Native 프로세스와 분리한다. 두 전체 모델의 동시 상주는 없다.

Native0, 별도 물리 행 provenance 감사, 독립 Native0, 모델의 실제 Gurobi 입력 Readback을 모두 요구한다. Binary≤10000, Rows≤300000, NNZ≤3000000 크기 제한을 지킨다. 실제 Windows 메모리는 모델 생성 후 Available RAM≥4GiB 및 Commit Available≥6GiB에 더해 예상 성장 `max(2GiB, 모델 생성 Private Commit 증가의 4배)`가 들어갈 여유를 요구한다. 시작 직전 같은 프로세스에서 자기 PID를 제외한 Gurobi/Native Worker 목록을 재확인한다.

Worker=1, Gurobi Threads=1, TimeLimit=90초, MIPGap=0.03, MIPFocus=3, Seed=42. FeasibilityTol/IntFeasTol/OptimalityTol=1e-8을 유지한다. 외부 BLAS/OMP 환경은 1 Thread로 실행한다. 메모리 callback은 시스템 RAM·Commit 및 프로세스 RSS/Private를 관측하며 4/6GiB reserve를 침해하면 `terminate()`로 정상 중단한다. 수치 오류 또는 메모리 오류는 보존하고 종료한다.

`PILOT_STARTED.json`을 배타 생성한 다음 Optimize를 호출한다. 이 파일은 재실행을 금지하는 durable latch다. TIME_LIMIT·예외·중단 뒤 연장이나 재실행하지 않는다. 별도 Root LP, FULL Optimize, 캠페인, 가중치 반복, 16→32 확대, DW/CG/Benders/Branch-and-Price 실행은 0회다.

Global LB는 유효한 Solver ObjBound이며 incumbent는 LB나 원본 UB로 사용하지 않는다. 정확한 유리수 모델 포함관계/반올림 증명과 수치적 Solver Bound를 구분한다. 독립 exact B&B trace를 새로 만든다고 주장하지 않는다. material 기준은 현재 FULL ObjBound 0.28940049108548904보다 최소0.001 개선이며, 3% 목표는 별도다.

5월 HOLD, Supervisor/Monitor Disabled, 관련 자동화 PAUSED를 유지한다. Source18r, U4 엔진, PR209 기존 코드·결과, StageBudget/NativeStopRequested와 원본 예산·캠페인 코드는 수정하지 않는다. 결과에 관계없이 증거와 한국어 보고서를 commit/push하고 PR209 브랜치를 base로 새 Draft PR을 생성한다.
