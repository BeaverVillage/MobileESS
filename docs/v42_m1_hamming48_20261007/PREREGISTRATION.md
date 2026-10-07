# Hamming48 단일 primal 탐색 사전등록

- Base: PR #169 `599d9ea67f6c348bfed9d1a594dc0d1eb3fd2768`.
- Scientific authority: PR #162 selected C3A `1d922c91eb27056a5ccc79c92ef18146707099ab`.
- Center: PR169 `UB_LOCAL_NEIGHBORHOOD_POINT.npz`, rho 0.6339776033797229.
- 저장된 `solve_neighborhood.py`와 `UB_LOCAL_NEIGHBORHOOD_DEFINITION.json`을 읽어 실제 free 목록을 동일하게 복구한다. 모든 unit의 node_activity / charge_mode B 중 슬롯 64..84만 포함한다.
- 중심 해는 원래 C3A rows/bounds/integrality와 frozen original physical/grid/A1 replay를 먼저 통과해야 한다. 실패 시 solve 없이 중단한다.
- Radius 24 -> 48. 사용자의 지시에 따라 중심, outside B 고정값 및 start는 새 중심으로 갱신한다. 다른 model/physics/objective/tolerance 변경은 없다. 원래 continuous 변수는 원래 bounds 그대로 유지한다.
- Native optimize 정확히 1회: TimeLimit=300, Threads=1. H24의 Method=2, NodeMethod=1, Crossover=2, MIPFocus=3, MIPGap=.005, FeasibilityTol=OptimalityTol=IntFeasTol=1e-8, Seed=20260929, DegenMoves=0을 유지한다. build가 상속하는 나머지 defaults도 기록한다.
- 시작점을 제한 model에 replay한 뒤 공급한다. MIPSOL event마다 원래 C3A 전체 point와 시간/rho/Hamming/nodes/local bound/gap/Work를 저장한다. 관측 callback은 cuts, heuristics, termination을 수행하지 않는다.
- 원래 scientific replay PASS인 점만 valid UB로 채택한다. 개선이 없으면 0.6339776033797229를 유지한다. material ΔUB>=.001, minor 0<ΔUB<.001, otherwise no valid improvement.
- Global LB는 0.5687116003498334로 고정한다. restricted ObjBound는 global LB로 사용하지 않는다. 남은 차이를 integrality gap이라고 부르지 않는다.
- 다른 solve, parameter sweep, formulation strengthening, 다음 실험 실행은 금지한다. 다음 실험은 정확히 하나 추천만 한다.
- 재현: `python docs/v42_m1_hamming48_20261007/run_hamming48.py --prepare`, 이어 `--solve`. ONCE token이 있으면 재실행을 거부한다. 완료 자료의 `analyze.py`는 solve 없는 분석이다.
