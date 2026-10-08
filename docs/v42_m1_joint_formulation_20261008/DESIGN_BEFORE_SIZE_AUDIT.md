# M1 공동 fleet/time/grid exact formulation — 사전 등록

기준 PR179 HEAD `f6d48e8892e1d36023f107130c2c9bfdfa5d4ebe`. PR162 C3A의 목적함수는 `minimize rho`, 모든 원본 행·경계·변수 의미·정수 type과 전체 96-slot domain을 유지한다. 이전 OPEN tree는 재개하지 않는다. A-stage와 May/downstream은 실행하지 않는다.

1. Step1은 저장된 OPTIMAL ROOT와 대표 자식 쌍대 벡터의 joint equality-block 보정 및 독립 exact bounded-Lagrangian 인증이다. Gurobi optimize를 금지한다. 자식 fixing-domain 인증을 전역 LB로 사용하지 않는다. 실패한 보정도 보존한다.
2. 후보 A는 ROOT 증거로 고른 76–79 슬롯, MESS03/MESS02, IDC01의 slot별 fleet-location count 전체 `0..2`를 81개 word로 완전 분해한다. 각 term은 원본 창의 SOC/travel-energy/PQ/PCS/flow/grid 행과 원본의 유한 경계를 homogeneous하게 복제한다. sampling된 경로 집합을 hull로 주장하지 않는다. 다른 location/mode binary까지 전부 convexify한 fleet hull로도 주장하지 않는다.
3. 첫 후보가 exactness와 certified Delta-LB >=0.001을 통과하지 못하면, 구조가 다른 후보 B 한 개를 시험한다. B는 같은 4-slot 창의 4 MESS location/mode selectors와 모든 선택 physics/grid 행의 Boolean product RLT이며, cross-MESS/time product symmetry를 공유한다. full trajectory word를 열거하는 A의 단순 radius/parameter sweep이 아니다.
4. 개별 표현에 추가 columns 300000, 추가 rows 1500000, 추가 nnz 15000000 한계를 둔다. 넘으면 표현 폭증을 기록하고 그 후보를 solve하지 않는다. 이 한계로 원래 정수 feasible trajectory를 잘라내지 않는다. 4-MESS count word 방식은 625 terms가 필요하므로 동일 exact census로 비교하고, 실험 B는 더 작은 RLT 표현으로 확장한다.
5. 검증은 독립 행 계수/Algebra checker, bounded two-MESS four-slot 전체 route/mode state enumeration, original 및 EF feasibility/optimum 비교, forward/inverse lifting, boundary SOC/terminal/travel-energy/PCS/PQ/grid 및 원본 UB full replay를 포함한다. exactness 실패 시 전체 optimize를 금지한다.
6. 원본 baseline ROOT LP 1회와 후보별 ROOT LP 1회만 수행한다. 모두 TimeLimit=600, Threads=1, Method=2, Crossover=0, BarConvTol=1e-8, FeasibilityTol/OptimalityTol/IntFeasTol=1e-8, Seed=20260929, DegenMoves=0 및 나머지 inherited settings 동일. 각 fresh call을 exclusive ONCE marker로 기록하며 재실행하지 않는다.
7. native LP ObjBound 및 primal objective를 독립 인증값으로 사용하지 않는다. OPTIMAL 후 변경 없는 원본+검증된 EF의 exact dyadic bounded-Lagrangian 인증만 사용한다. paired Delta는 inherited/독립 original global LB 중 최선과 candidate valid LB를 비교한다. coefficient/ObjCon/원본 variable axis의 bit identity와 추가 objective 0을 확인한다.
8. exactness와 certified Delta >=0.001일 때만 strengthened original-objective MILP canary를 최대 900초, 1회 실행한다. full replay-PASS 원본 UB를 lift해 complete MIP start로 공급한다. 원본 integral domain을 보존한다. P2/M2/May는 실행하지 않는다.

조건부 canary를 제외한 새 전체 native solve의 최대 수는 baseline 1 + 후보 2 = 3회다. 추가 파라미터 sweep, old external B&B, 새 artificial LB cut, Target-rho 또는 objective 변경은 없다. 인증 복구와 genuine relaxation strengthening을 별도로 보고한다.
