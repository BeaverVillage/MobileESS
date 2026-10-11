# Source18r 물리 Global LB 단일 파일럿

기준은 PR207의 `497609b46faa14ea7e32a9483a333ab32fd264ef`이다. 새 연구 브랜치는 `codex/v42-source18r-physical-global-lb-pilot-20261012`이다. U4 및 원본 수학 소스는 변경하지 않는다.

Native0에서 원본 FULL CSR의 차량 소유 열과 단일 차량 support 행을 모두 유지한다. 이동 이진변수는 원본 타입 B 그대로이고, 원본 초기·종단 SOC, 모든 96슬롯 energy_balance, 접속·Mode·PCS16·경로·이동에너지를 유지한다. 원본 terminal_location 의미를 그대로 두며 출발지 복귀를 새로 강제하지 않는다. 모든 혼합 support 행과 비차량 행을 제거한다. 공동 계통 제약을 차량별로 복제하지 않는다. 원본 상한·하한을 그대로 복사하고 C3A의 계통 기반 강화 Bounds는 쓰지 않는다.

원본 등식의 저장된 binary64 계수와 RHS를 Fraction으로 소거하여 `rho >= b + sum_m a_m*x_m`를 구성한다. 별도 Native0 검증기가 원본 등식을 다시 소거하고 원본 단일 차량 행·열·Bound·Binary를 재검사한 후에만 실행한다. 증명은 모든 원본 가능해의 차량 사영이 각 하위 문제에 포함된다는 포함관계와 convex 가중합이다. 원본 min rho의 ObjCon은 정확히 0이다.

단일 w는 기존 frozen U4에서 각 슬롯의 최대 line_thermal_face를 고른 후 값이 가장 큰 16개 서로 다른 슬롯에 각각 정확히 1/16을 부여한다. 동률은 원본 행 번호 순서로 결정한다. 이는 실행 전 고정한 선택 규칙이며 선택·가중치 최적화/반복은 없다. 이 파일럿에서 MATERIAL은 검증 UB 대비 Gap <=3%를 충족하는 것으로 정의한다. NONMATERIAL이면 후속 확대를 기각한다.

MESS01부터 04까지 독립 worker 프로세스를 하나씩 실행한다. Threads=1, 실제 TimeLimit=29초로 30초 상한에 1초 여유를 둔다. optimize 4회 이하, 총 120초 이하이다. 순차 호출마다 model 생성시간, Native Runtime, Solver ObjBound/ObjBoundC, incumbent, gap, Windows 프로세스 peak RSS/private commit과 Gurobi MaxMemUsed를 저장한다. model과 원본 CSR/RHS/sense/Bounds/types/objective의 readback을 optimize 전에 검증한다. Full MILP·Full Root·원본 Root LP·campaign 실행은 0회다.

최적해가 없으면 유한한 현재 Solver Bound를 사용한다. 정확한 목적계수와 Solver의 반올림 목적계수 차이는 원본 Bound의 정확한 min-box로 보정한다. Solver Bound가 없는 경우 유한성이 증명된 원본 Box 하한만 허용하며, 무한값을 임의로 유한하게 만들지 않는다. 메모리 부족, Gurobi NUMERIC/MEM_LIMIT, 예외는 stop latch 및 증거로 보존하고 뒤 차량을 실행하지 않는다. 실행 시작 latch가 있으면 다시 optimize할 수 없다.

독립 인증 범위는 원본 행·좌표·RHS·부호·고정항·차량 분리·가중치·목적 반올림 보정·Solver Bound 전달 및 합산이다. Gurobi B&B 자체의 exact proof trace를 인증했다고 주장하지 않는다. 사용자가 허용한 Solver의 유효 Global Bound와 수치 계약을 전제로 한다.

5월 캠페인 HOLD와 예약 Disabled/heartbeat PAUSED는 읽기만 확인한다. Source18r 및 PR207 자료는 수정하지 않는다. PR147/203의 기존 LB·Column·Dual·Pricing을 현재 수치로 사용하지 않는다. DW/CG/B&P/가중치 반복 또는 추가 solver 실험은 하지 않는다. 결과를 Commit/Push하고 Draft PR로 제출한다.
