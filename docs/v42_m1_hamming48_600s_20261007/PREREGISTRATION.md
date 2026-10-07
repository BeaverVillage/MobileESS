# M1 Hamming48 / 600초 단일 primal 탐색 사전등록

- Exact base: PR170 `bf455bbea26d644d8952d1d2da90f8f645cf0df1`의 격리 worktree.
- Scientific authority: PR162 selected C3A `1d922c91eb27056a5ccc79c92ef18146707099ab`; C3A matrix/data/inverse/A1 authority 모두 유지.
- Center/start/outside B fixed values: PR170 `BEST_VALID_POINT.npz`, x, rho=0.6324498168172089, SHA256=f9192e2d6a8eb04b4096f983bdc1abbf65c1abab5613e02cd759713299d5c6cc.
- PR170 실제 실행 코드/저장 restriction을 읽고 동일 free set 순서와 indices를 검증한다. 슬롯64..84, 모든4 MESS node_activity2016 + charge_mode84 =2100 B. Outside B7222개를 새 center로 고정. 원래 continuous296718개 bounds 그대로.
- Hamming radius48: center B=0이면 x, B=1이면1−x의 합≤48. Center original C3A rows/bounds/B integrality, frozen route/movement/SOC/PQ/PCS/grid/A1 replay PASS와 H=0 제한 model start PASS를 모두 요구한다. 실패 시 optimize0으로 중단.
- 실험 policy 변경은 TimeLimit300→600뿐이다. 사용자 지시로 center/start/outside fixed values 및 Hamming 기준점을 PR170 최선 해로 갱신하므로 서로 다른 center의 순수한 시간 효과 실험이라고 주장하지 않는다.
- Threads1, Method2, NodeMethod1, Crossover2, MIPFocus3, MIPGap.005, FeasibilityTol/OptimalityTol/IntFeasTol1e−8, Seed20260929, DegenMoves0 유지. 모든 effective params를 PR170과 대조하여 TimeLimit/LogFile 이외 차이가 없어야 한다.
- Native optimize 정확히1회. Exclusive ONCE token와 single-call guard; 별도 presolve call0. Parameter sweep, radius 확대, full global B&B, 수동 LB cuts/hulls, formulation 변경, 재실행 금지.
- MIPSOL event마다 전체 원래 C3A point와 runtime/Work/rho/Hamming/node count/restricted bound/gap를 저장한다. 모든 full validation은 native 종료 후 수행하며 관측 callback은 solver 탐색을 변경하지 않는다.
- Best solver point를 원래 C3A 및 frozen full physics/grid validator로 independently replay한다. FAIL point는 UB로 채택하지 않는다. 다른 저장 improving incumbent가 필요하면 objective 순으로 검증한다. valid improvement 없으면 UB0.6324498168172089 유지.
- Global LB0.5687116003498334 고정. Restricted ObjBound는 global LB가 아니다. 전역 최적성 또는 integrality gap 증명 없음.
- ΔUB≥.001: HAMMING48_600_PRIMAL_IMPROVEMENT_CONFIRMED; 0<ΔUB<.001: HAMMING48_600_MINOR_IMPROVEMENT; 개선 없음: HAMMING48_600_NO_VALID_IMPROVEMENT.
- H24/112.53초, H48/300초, 이번 H48/600초를 비교하고 H boundary, discrete/physical/grid 변화를 기록한다. 다음 행동은 결과에 따라 정확히1개 추천만 한다. 다른 실험 실행0.
- 재현: `python docs/v42_m1_hamming48_600s_20261007/run_hamming48.py --prepare`, 이어 `--solve`. 완료 namespace의 ONCE token이 있으면 추가 실행을 거부한다. `analyze.py`와 봉인/검증 스크립트는 solve가 없는 분석이다.
