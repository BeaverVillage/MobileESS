# V42 B2/B3 공통 MESS U4 Anytime 알고리즘

알고리즘 버전은 `V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1`이다. B2 M과 B3 M1/M2가 `v42_common_mess.optimize_case`를 호출한다. Stage 이름은 증거 연결에만 쓰며 Neighborhood 후보, 반경, 목적함수, 탐색 순서와 시간 배분을 분기하지 않는다. B3의 Stage별 원본 수치 정책은 유지한다.

원본 4대 MESS·96슬롯 문제의 목적함수, C3A 행, Bounds, 원본 정수 도메인을 유지한다. PR #126/#198의 helper 재구성, 출발 슬롯 occupancy, terminal slot 96, FULL route_flow 대표 정수 좌표를 보존한다. FULL/C3A/FULL 원본 동치성 및 Literal Integrality 검증을 통과한 점만 최선 UB로 저장한다. 반올림·클리핑·물리 제약 완화는 하지 않는다.

현재 Stage의 초기 점은 새 고정 입력 아래 독립 FULL Replay 후 재사용한다. 검증된 점이 있으면 Seed MILP를 생략한다. 없으면 종단을 복원한 stationary 고정 패턴 LP 120/60/60초, stationary free-mode MILP 180초, 당일 sensitivity로 제한한 route-site MILP 240초, 마지막 원본 unrestricted MILP 순으로 초기해를 시도한다. 마지막 호출에는 남은 누적 예산만 부여한다. 고정 패턴 LP가 유효 원본 FULL 해를 반환하면 바로 U4로 진행한다.

U4는 현재 Planning Grid의 thermal/voltage 병목을 사용한다. Actual 정보를 읽지 않는다. 선별한 슬롯과 이전 이동창의 Arc, charge mode 및 활동 대표 좌표를 원본 도메인으로 열고, 나머지 대표 이진 좌표를 고정한다. route-flow helper는 대표 좌표에서 재구성한다. Hamming 반경 48/96/144와 이동창 4/8/16을 사용하며, 각 Box의 원본 이동경로 변경 가능성을 따로 검증한다. 실제 경로를 바꿀 수 없는 Box는 실행하지 않는다.

초기 U4 요청은 90초이며, 개선 후 요청은 300초, 정체 시 요청은 180초이다. 두 번의 정체 후 새로운 U1 탐색을 한 번만 조건부 실행한다. 동일 점·동일 Neighborhood의 실패를 반복하지 않는다. Fixed-route dispatch는 현재 운전과 병목 진단에 기회가 있을 때 한 번만 최대 60초 실행한다. 이 모든 호출의 실측 Native Runtime 합은 각 M 단계의 1,800초 예산에 포함된다.

다음 Native TimeLimit은 항상 요청시간과 남은 누적 예산의 최솟값이다. 각 Solver는 Threads=1이다. Runtime/Work, 실제 초과분, 실패 비용은 Ledger에 영속화하고, 실측 Runtime이 없는 중단 호출은 격리한다. 모델 생성·읽기·검증·저장·Actual·Fresh의 Wall Time은 별도 집계한다. 제한시간 직전 Callback과 최종 Solver incumbent를 원본 FULL에서 재검증한다. POLLING에는 지원되지 않는 Callback 속성을 요청하지 않는다.

`feasible_accepted`는 FULL 행·Bounds·Literal Integrality·이동/에너지·SOC·PCS/PQ·계통 제약·고정 Stage 입력·원본 목적함수·SHA 검증으로 결정한다. `global_gap_certified`는 동일 Case의 독립 UB/LB 인증이 있고 Gap이 3% 이하일 때만 참이다. 기본 LB와 Gap은 UNKNOWN이다. 제한 Neighborhood의 Native BestBound는 진단으로만 기록한다. 기존 같은 Case의 원본 Dual 증거를 제공하는 경우 독립 검증만 수행하며 LB Solver를 호출하지 않는다. L1~L4, DW/CG/Benders와 PR #202/#203 연구 알고리즘은 Production 경로에서 호출하지 않는다.

B3는 기존 순서 A1→M1→A2→M2를 유지한다. A1/A2의 Complete-domain·Pricing·Recovery, 0.5% 인증 및 기존 5,400초 예산을 유지한다. M1 FULL 가능해가 A2의 전체 MESS 고정 계획이 되며, M2는 A2의 새로운 AIDC 결정 아래 Case를 다시 만든다. Stage SHA와 Fixed-input SHA는 원본 SourceCoordinator가 검증한다.

Canary는 실제 당일 원본 모델·최적화·FULL 검증·Planning Freeze·고정 Actual Replay·96슬롯 Fresh OpenDSS까지 수행해야 한다. B2/B3 두 Canary의 소스 및 독립 증거가 일치해야 정식 Campaign Manifest를 발행한다. 그 후 B2 최대 3개 Worker의 첫 31일 Sweep을 마치고 B3 Worker 1개로 31일을 수행한다. 기존 Supervisor와 과거 결과는 보존한다. 구현 결함을 수정할 때는 새 Source Epoch로 재검증한다.

Actual 최대선로부하율은 원본 Fresh phase current와 동일 선로별 상 정격으로 계산한다. 변압기 부하율은 별도로 기록한다. Actual 재최적화·P/Q Repair는 0회이다. 원본 B0/B1 SHA를 확인하고 실패·미완료 값은 공란으로 유지한다. 날짜별 결과가 실제 종결 상태로 확인되기 전에는 완료로 선언하지 않는다.

최종 통합 회귀 검사 272개가 통과했으며, 마지막 소스 고정 후 공통 엔진 11개를 다시 확인했다. 실제 소형 Gurobi 최적화도 포함했다. 이는 구현 Gate이며 실제 Canary·31일 완료 증거와 구분한다.
