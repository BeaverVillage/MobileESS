# Spawn 양방향 LP 실행 사전등록 — 사용자 재개 지시 반영

PR187 exact HEAD e67ecfa827e4262c2f2df17c226d6442656af18b 위 저장 작업을 이어간다. 기존 repair의 1e-4 품질 FAIL은 보존하고, 사용자의 후속 지시에 따라 1e-4를 실행 차단 조건에서 제거한다. 독립 exact weak-duality certificate PASS이면 실행할 수 있다. 원본 objective=min rho_max, 651개 기존 B2 행, 원래 변수·물리·bounds·types authority 및 모든 scientific tolerance는 보존한다.

9,322개 전수 매핑과 사전등록 점수로 고른 SELECTED_BRANCH_VARIABLES의 최상위 후보부터 진행한다. 한 scalar original binary의 bounds만 0/0 또는 1/1로 고정한다. 나머지 binary는 child LP에서만 C로 완화하며 원래 continuous는 그대로다. 전체 그룹 고정이나 추가 논리 고정, 새 cut/threshold/domain 제한은 없다.

각 pair는 multiprocessing.get_context('spawn')의 독립 Python Process 두 개다. Worker마다 독립 Env/Model을 만들고 닫는다. Env/Model을 IPC로 전달하지 않는다. 각 child TimeLimit=480, Threads=1, Method=2, NodeMethod=1, Crossover=0, MIPFocus=3, MIPGap=.005, FeasibilityTol=OptimalityTol=IntFeasTol=BarConvTol=1e-8, Seed=20260929, DegenMoves=0이다. 실제 native API에서 모두 읽어 검증한다. MemLimit/SoftMemLimit은 default infinity, RAM은 관측만 한다.

첫 pair는 두 Env/Model이 동시에 license를 획득하고 원본 transport 검증 후 READY를 보내야 시작한다. Controller가 자원을 다시 검사하고 공통 start event를 보내 두 native 호출을 동시에 시작한다. License 실패 시 우회·자동 재시도 없이 종료한다. 런타임의 실제 native overlap도 저장해 license 지원을 결과로 확인한다. 모델 로딩·build·worker wait·native·certificate·parallel wall은 분리한다.

Native optimize는 worker당 정확히 한 번, 전부 최대 6회, Runtime 합계 최대 2880초다. 각각 before-launch에서 남은 budget≥960초를 요구하며 실제 TimeLimit overshoot도 모두 차감한다. 미확정 소비나 실패한 pair가 있으면 다음 후보를 실행하지 않는다. 첫 pair 양쪽의 완료·독립 인증이 정상일 때만 나머지 사전 선정 후보 두 개를 같은 2-worker 방식으로 평가한다. 3~4 worker 확대는 이번에 하지 않는다. Sequential 반복은 하지 않으며 speedup은 미측정으로 기록한다.

별도 worker 폴더에 원시 X/Pi/RC/Slack·log·identity·tmp·dual proof를 먼저 보존한다. Raw 잘못된 sign은 거부하고 별도 sign-cone/equality multiplier로 all 306,040 finite-bound 항을 재계산한다. CSR 독립 checker를 worker마다 적용한다. 두 유효 certificate 중 강한 값은 해당 child 하한에만 쓴다. 완료되지 않은 child는 unresolved다. Native INFEASIBLE은 independent Farkas proof가 없으면 +infinity가 아니다.

Controller만 pair를 합친다. LB_pair=min(LB_z0,LB_z1), 최종 LB=max(0.5687116104049206, 완료·인증된 pair들의 LB)다. UB=0.6284141956452488은 유지한다. Native 목적값과 raw fractional point를 global bound/UB로 채택하지 않는다. Material ΔLB≥.001, M1_ACCEPTED=false 및 production/P2/downstream 금지는 그대로다.

각 실행 직전 PID·creation·command·cwd·CPU와 실제 solver 여부를 읽기 전용으로 확인한다. 다른 worker를 중지하거나 수정하지 않는다. 두 own Worker의 CPU/RSS/page-fault/I/O 및 system memory를 샘플링한다. 실제 memory-bandwidth 하드웨어 counter가 없으면 NOT_MEASURED이며 RSS/I/O를 bandwidth라고 부르지 않는다. Native Runtime 합계/실제 native span은 overlap 지표이며 순차 baseline 없는 speedup이 아니다.

## 첫 Native 호출 전 자원 판정 보완
첫 admission은 다른 May12 native 작업의 존재만으로 RESOURCE_PENDING이었다(optimize=0). 그 증거는 별도 PRE_ADMISSION 결과와 PROCESS_ISOLATION_AUDIT의 첫 snapshot에 보존한다. 사용자 지시는 다른 작업의 중지·수정을 금지하며, 다른 native 작업이 존재한다는 이유만으로 실행을 금지하지 않는다. 전체 CPU busy 85% 이하 및 미확인 active 작업 없음일 때, 독립 Threads=1 Worker 2개를 허용한다. 실제 경합은 CPU/RSS/page fault/I/O로 관측한다. RAM은 admission 또는 종료 조건에 쓰지 않는다. May12 프로세스를 수정하거나 중지하지 않는다. Sequential 비교가 없으므로 speedup을 주장하지 않는다.
