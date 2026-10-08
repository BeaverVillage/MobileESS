# M1 Integer-First Exact Decomposition 사전 등록

기준 PR182 `d541a9d15a03c4a6f8dbc1906a57c7486e9700e3`, 과학적 권한 PR162 selected original C3A. 원본 objective / ObjCon / axis의 raw bytes를 검증한 뒤에만 optimize한다. 모든 새 경로는 `D:\v42_m1_route_mode_benders_20261008` 아래다. 기존 실험 프로세스를 중단하지 않는다.

1. 먼저 DAG, parallel arc, 모든 원본 vertex의 outgoing mass와 node binary 연결을 저장된 정확한 inverse로 감사한다. 마지막 graph slot 95의 stay는 원본 binary label 96에 대응한다. 시작 vertex는 unit-flow source equality로 mass 1을 보장해야 한다. 이 검사가 실패하면 optimize=0으로 원인을 수정한다.
2. 원본 feasible full vector 20개를 독립 replay하고 배정별 원본 binary 9322개만 고정한다. route_flow는 continuous를 그대로 유지하며 직접 고정하지 않는다. 각 recourse 1회, TimeLimit=120초, Threads=1, Method=2, Crossover=2, 원본 세 tolerance=1e-8, Seed=20260929. 목적은 원본 minimize rho다. 모델 build 후 objective bytes를 다시 검사한다. duals / RC / slacks / raw point / log를 검증 전에 저장한다. 재실행 및 parameter sweep은 없다.
3. median Runtime <=10초, p90 <=60초를 practical gate로 사용한다. 엄격 replay 실패, TIME_LIMIT, INFEASIBLE, 수치 인증 실패를 분리한다. 수백 초 recourse가 관측되면 장기 Benders를 실행하지 않는다.
4. finite original bounds를 포함하는 exact dyadic weak-duality cut을 인증한다. 잘못된 native inequality multiplier sign은 조용히 보정하지 않고 reject한다. transport 오차는 이산 domain 전체에서 exact envelope를 계산하여 conservative intercept로 반영한다. mixed senses / equality / stationarity / bounds / known witnesses / bounded fixtures를 확인한다.
5. 일반 integer projection, fixed-binary LP, objective epigraph, global bound 논증과 bounded route/mode/SOC/PQ/grid fixture의 독립 direct MILP 비교가 모두 통과한 경우에만 full-scale master를 실행한다. sample 20개는 full domain의 restriction이 아니다. master는 원본 flow, node activity, charge mode domain을 보존한다.
6. full-scale Benders canary는 1 campaign, native Runtime 합계와 controller wall 모두 900초를 상한으로 관리한다. solve에는 남은 budget만 부여한다. native 종료 지연과 저장 overhead는 별도 기록한다. candidate point는 integer complete assignment일 때만 recourse로 전달한다. native master bound는 모든 원본 domain과 globally valid cuts가 확인될 때만 global LB로 인정한다.
7. TIME_LIMIT는 infeasibility proof가 아니다. UB는 원본 모든 물리 / grid / A1 replay PASS만 채택한다. dual 인증 실패 시 invalid cut은 삽입하지 않는다. 반복 candidate나 unchanged LB의 원인은 실제 cut strength로 진단한다. 추가 1800초는 별도 사용자 authorization 없이는 실행하지 않는다.

초기 LB=0.5687116104049206, UB=0.6306505800203936. global gap=(UB-LB)/abs(UB). 0.5%는 목표이며 보장하지 않는다. zero scientific objective / 새로운 science cuts / Top-K / Hamming global restriction / A-stage 및 downstream 실행은 없다.

full canary 전 fixture correction 등록: barrier INFEASIBLE이 Farkas attribute를 제공하지 않은 실패를 별도 보존했다. 새로운 canary recourse는 처음부터 Method=1을 사용해 simplex certificate를 얻고, master는 Method=2를 사용한다. 기존 benchmark 20개의 solve는 재실행하지 않는다. 원본 objective / model / tolerance는 동일하다. 잘못된 multiplier는 native certificate로 먼저 reject하고, 필요시 명시적 sign-cone 투영의 새 multiplier에서 exact bound support 전체를 다시 계산한다. solver가 1e-13 미만 cut coefficient를 무시하는 문제는 1e-12 미만 항의 명시적 floating transport와 exact global error envelope로 보수적 intercept를 계산하여 처리한다. 원본 scientific coefficient 변경이나 invalid coefficient의 묵시적 clamp가 아니다. 각각 로그와 수학적 certificate를 보존한다.
