# Stabilized Lagrangian Dual 수학 계약

원본 P1은 min rho_max, ObjCon0, rho∈[0,1]이다. 저장 binary64 CSR/RHS를 정확한 유리수로 해석한다. 선택된 선로행은 원본 injection/response binding 등식으로 소거하여 rho ≥ b_k + Σ_m a_kmᵀx_m를 얻는다. 부호와 상수는 독립된 세 구현으로 재도출했다. Pdis 양/ Pch 음 injection과 correction 및 고정 AIDC는 모두 원본 행에 들어 있다.

각 X_m은 FULL의 해당 차량 arc/charge_mode/SOC/Pch/Pdis/Q 열과 비영 support가 그 차량에만 속하는 모든 행, 원래 Bounds/정수 타입을 그대로 유지한다. 임의 FULL 정수해의 차량 사영은 X_m에 포함된다. Initial/terminal SOC,96 energy rows,97SOC, PCS16, charge/discharge 배타성, 원래 flow/terminal 의미와 이동 ETA/energy를 제거하지 않는다. FULL의 mixed injection 정의 및 다른 Grid 행을 차량별로 복제하지 않는다.

추가 결합행은 원래 sense가 <이면 그대로, >이면 부호를 뒤집어 g_j≤0으로 정규화한다. Equality는 비음수 부등식 승수에 넣지 않는다. w≥0,Σw=1 및 μ≥0에 대해 L=b_w+Σμg_const+Σ_m inf_Xm (a_wm+Σμg_jm)ᵀx_m 이고, L≤FULL optimum이다. mu g≤0이므로 결합 제약을 완화한 목적값은 원래 rho를 넘지 않는다. Σw=1을 정확히 유지해 남는 rho 최소화항은0이다. 합이 달라지는 일반화라면 min_{rho∈[0,1]}(1−Σw)rho를 포함해야 하며 본 구현은 그러한 입력을 거부한다.

Native 목적계수 ĉ와 exact c의 차이 δ=c−ĉ에 대해 E_min=Σmin(δ_j l_j,δ_j u_j)를 exact 계산한다. 원래 유한 차량 Bounds만 사용하며 L_m=Native global minimization bound+E_min이다. Incumbent Objective는 LB로 쓰지 않는다. GLOBAL bound의 유효성은 원래 Gurobi numerical contract에 의존하며 exact B&B proof trace가 아니다. 정수 영역 포함 및 transport 증명과 이 Numerical trust 단계를 분리한다.

A0는 PR209의 동일 객관계수와 현재 FULL slice를 재대조한 뒤 네 기존 인증값을 재사용했다. A1은 raw Pi를 거부하고 별도 sign-cone vector의 finite-box weak duality 값을 재검산한 초기가격이다. A2는 실제 signed critical response의 다시간 sparse objective, A3는 전압·변압기 승수를 포함한다. weight simplex의 projected ascent와 L2 trust radius.15, μ∈[0,100] clipping, 고정 선택/seed0, exact normalization, 중복 SHA,6 evaluations 및360s cap을 사용한다.

업데이트 점은 numerical local incumbent를 사용한 휴리스틱 후보 생성이다. OPTIMAL이어도 exact mathematical subgradient라고 주장하지 않는다. 미완료 incumbent는 global bound 또는 exact oracle로 쓰지 않는다. 두 stabilized 후보는 서로 다른 물리 단위를 가진 μ의 비정규화 gradient 때문에 너무 큰 가격을 만들었고 인증값이 크게 약화됐다. 이 negative result를 보존하며 같은 예산의 자동 추가 탐색은 없다. Scale-aware coupling stabilization의 효과는 이번에 측정하지 않았다.

원래 helper에 대한 정확한 equality 승수 repair도 Native0으로 수행했다. helper h의 +1 pivot equality 승수에 현재 d_h를 더하고 residual에서 d_h A_h를 빼면 해당 helper residual이0이 된다. 원래 acyclic definition graph를 따라 반복해 모든 injection/response helper residual과 rho residual이 exact0, 물리 목적계수 및 상수가 decomposition과 정확히 같음을 검증했다. 원래 무한 Bound는 바꾸지 않았다. `EXACT_HELPER_MULTIPLIER_REPAIR.json`에 실제 승수와 검산을 저장했다.
