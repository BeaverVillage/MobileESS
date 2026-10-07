# M1 gap 원인 귀속 사전등록

기준은 Draft PR #167 exact head `0d423626790a1102d42e6ba84beeb5f7d4ab1d4b`, 과학 권위는 PR #162 selected C3A다. UB=0.6694159238756877, 보수적 LB=0.5687116003498334를 별도로 검증한다. 저장 barrier ObjVal은 근사 primal proxy이며 하한으로 쓰지 않는다. PR167의 한 슬롯 320 cut 음성 결과를 보존하며 반복하지 않는다.

모든 새 산출물은 이 namespace에만 쓴다. 기존 worktree와 실행 중인 A-stage 작업을 종료하거나 수정하지 않는다. 동시 실행을 기록하며 Runtime 비교를 통제 성능 실험으로 주장하지 않는다. 원래 physics, objective P1/P2 및 tolerance 1e-8을 유지한다.

1. 원본 incumbent의 전체 C3A raw rows/bounds/integrality와 원본 inverse/route/movement/SOC/PQ/PCS/grid/A1 frozen interface를 재검증한다. LB provenance와 저장 pure LP 수치 실패를 각각 기록한다.
2. incumbent의 모든 mobility arc/node 및 charge-mode 경로를 고정하고 연속 dispatch를 LP 한 번 재최적화한다. Threads=1, Method=2, Crossover=0, 원래 tolerance, P1 그대로. 해를 검증 전에 먼저 저장한다. 목적 변화와 엄격 feasibility를 따로 보고한다.
3. 그 결과 및 저장 LP에 근거한 하나의 정수 neighborhood를 별도 JSON으로 **solve 전** 고정한다. 원래 모델을 제한한 탐색 한 번, TimeLimit=300, Threads=1. 실패는 optimality 증명이 아니다. 새 UB는 원래 all-integer 물리 replay PASS일 때만 채택한다.
4. MESS04 0-based 69–72의 모든 시간-DAG 경로를 경계에서 진행 중인 이동까지 열거한다. SOC69/SOC73은 원래 bounds의 자유 인터페이스다. mode/PQ/SOC 및 출발 이동 에너지의 정확한 polyhedral disjunction을 만들고 Balas extended hull로 표현한다. 원본 binary64 계수를 exact Fraction으로 읽는다. 외부 96-slot SOC/grid extendability는 고정하지 않는다. 이 국소 집합은 해당 원본 국소 물리 전체이며 모든 전역 정수 경로의 projection을 포함한다.
5. 생성기와 독립인 경로/계수 검증 및 mutation 거부를 통과한 뒤 membership/separation 진단을 한다. baseline raw point의 미세 affine 오차만으로 구조적 불가능을 주장하지 않는다.
6. 원래 C3A에 이 블록 hull만 추가한 LP **한 번**, Method=2/Threads=1/Crossover=0/tolerance=1e-8. primal/dual/RC/slack/native ObjBound 저장, raw replay와 독립 exact bounded-Lagrangian certificate를 분리한다. finite bounds를 EF에도 제공하고 valid global LB=max(LB_ref, certificate)로 비교한다. material ΔLB≥0.001.
7. 새 점의 substitution을 측정한다. 위반된 단일 블록에서 material gain 없이 대체가 실제 관측되면 새 점으로 정한 최대 네 MESS/window 블록의 controlled generalization 한 번만 한다. 무차별 96-slot 확장은 하지 않는다.
8. 결과가 요구하는 작은 critical cross-MESS coupling master와 하나의 evidence-driven longer horizon 진단만 수행한다. selective-integrality는 최대 세 번, 각 TimeLimit=300/Threads=1이며 partial integer 해를 production UB로 쓰지 않는다. 각 진단의 정의는 실행 전에 봉인한다.

새 full 3600s MILP, full native B&B, solver sweep, Benders/DW/Branch-and-Price는 금지한다. hull membership/coupling 등 소형 진단 solve도 별도 token과 receipt로 센다. 기존 한 시간 중단 run은 이번 solve가 아니다. 원인 분류는 결과 뒤에 선택한다. 시간 제한은 실제 native Runtime을 잘라 보고하지 않는다.
