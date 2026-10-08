# 원본 C3A Integer-First 분해의 동치와 인증

## 정확한 권한과 이산 좌표

권한은 PR162의 selected C3A raw CSR, RHS, senses, bounds, types, objective 및 변수 axis다. matrix SHA256 `45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8`, data SHA256 `20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467`. 목적은 column 239826 `rho_max`의 계수 1과 원본 +0 ObjCon다. objective / ObjCon / axis는 독립 Git blob reader가 bit identity를 검증한다.

원본 x=(z,w), z는 원본 node_activity와 charge_mode binary 9322개 전부다. w는 원본 continuous 296718개 전부이며 route_flow 207736개도 포함한다. 목적을 min c_z z+c_w w+c0로 유지한다. 새 물리식, science cuts, route 후보 제거, flow 정수성은 없다.

## 경로의 integer projection

원본 4개 MESS의 각 route graph는 시간 순서 DAG다. 실제 53626개 arc를 검사하여 strictly forward time과 동일 endpoint pair의 parallel arc 부재를 확인했다. nonnegative unit source flow와 conservation은 source-to-terminal path들의 convex decomposition을 갖는다. 모든 nonterminal vertex의 outgoing mass가 0/1이면, 양의 weight를 갖는 모든 path는 같은 vertex들을 방문해야 한다. 시간 DAG에서 같은 방문 vertex들의 순서는 유일하다. parallel endpoint arc가 없으므로 연속 방문 vertex 사이의 arc도 유일하다. 따라서 모든 양의 weight path가 동일하고 route flow는 0/1이며 유일하다. 시간 이동 중 서로 다른 site를 동시에 점유하는 계획은 불가능하다.

실제 9216개 vertex는 explicit binary link 8746개, 정확한 inverse alias 192개, 상수 274개, source unit-flow 등식 4개로 모두 확인했다. 마지막 graph slot 95는 stay만 가능하고 node_activity label 96의 정확한 alias다. 움직임 arrival은 최대 95이므로 terminal identity를 우회하는 마지막 이동 arc가 없다. 원본 FULL의 flow 등식을 saved exact affine inverse로 운반한 결과, C3A의 flow 등식 8942개와 정확히 일치하고 274개는 zero identity가 된다. 누락/변경은 0개다. `ROUTE_PROJECTION_AUDIT.json`에 실제 검사를 보존했다.

master는 원본 flow, node_activity, charge_mode 변수의 원래 bounds/types와 이 변수만 포함하는 원본 행 17688개를 사용한다. original complete domain을 덮으며, projection의 continuous flow는 그대로다. charge mode와 flow의 물리적으로 불가능한 조합은 원본 recourse infeasibility와 globally valid cut으로 제거한다. 첫 20개 sample은 성능과 known-witness 검증 전용이며 master의 허용 도메인이 아니다.

## 고정 recourse 및 route/physics 결합

z를 complete integer assignment로 고정하면 원본 행렬 A의 모든 행, RHS, bounds, 원래 w types 및 원본 objective를 그대로 둔 LP가 Q(z)를 정의한다. 상단의 graph flow 표현과 recourse의 graph flow는 동일 z에 의해 유일하게 결정되므로 모순된 route 복제가 없다. departure-slot travel-energy, energy_balance, initial/terminal SOC, eta, Pch/Pdis mode, simultaneous PQ, PCS16, 원본 voltage/thermal/grid/A1 coupling은 원본 행을 한 개도 삭제하지 않은 recourse에 남는다. 각 accepted UB는 original raw C3A와 saved exact inverse를 통한 original physics 및 모든 grid 673920행을 다시 검사한다. integer master point만 실제 candidate로 인정한다.

## Weak duality와 exact optimality cut

원본 Aw w + Az z와 mixed senses의 RHS b를 고려한다. min objective에서 pi<=0 on <=, pi>=0 on >=, equality pi free다. 따라서 모든 feasible (z,w)에 pi^T(Aw w+Az z)>=pi^T b다. r=c_w-Aw^T pi라 놓으면

`c_z z+c_w w+c0 >= alpha + beta^T z`,

`alpha=c0+pi^T b + sum_j min(r_j*l_j,r_j*u_j)`,

`beta=c_z-Az^T pi`.

원본 C3A의 모든 continuous bounds는 finite다. r=0 stationarity를 가정하거나 reported RC를 proof로 대체하지 않는다. 각 finite-bound support term을 exact binary64 dyadic arithmetic으로 계산하므로 자유 injection, 넓은 auxiliary bounds, stationarity residual, cancellation을 누락하지 않는다. equality/inequality sign과 각 bound 선택도 exact다. infinite bound가 발견되면 이 인증 경로는 STOP한다.

raw native multiplier의 wrong sign은 먼저 reject한다. 필요하면 공개적으로 sign cone에 속하는 **새 수학적 multiplier**를 구성하고 원본 A,b,c,l,u에서 모든 cut coefficient와 bound-support를 다시 exact 계산한다. 원본 matrix, native Pi 파일, science objective, cut slope를 임의 clamp하지 않는다. 이 작업은 native optimize=0이다. 투영만으로 tightness나 separation을 보장하지 않으므로 known witnesses와 source separation은 별도로 검사한다. native rejected certificate와 새 accepted certificate를 서로 다른 기록으로 보존한다.

## Feasibility certificate

같은 sign convention의 pi에 대해, certificate derivation에서 비용을 수학적으로 0으로 두면 feasible recourse의 0 >= L0(z)가 성립한다. 이것은 **zero-objective solve가 아니며** 실제 recourse는 계속 min rho다. L0(z*)>1e-8인 exact Farkas separation만 채택한다. feasibility cut은 L0(z)<=0이다. raw FarkasDual의 opposite convention을 명시적으로 뒤집고 exact original support를 계산한다. near-zero ray, wrong sign, missing ray, TIME_LIMIT, source separation 실패는 cut의 근거가 아니다. barrier infeasibility가 ray를 제공하지 않았던 bounded-fixture 실패를 보존하고, 이후 새로운 recourse는 처음부터 simplex certificate policy를 사용한다. 동일 original assignment를 재최적화하지 않는다.

## Binary64 transport

정확한 beta를 floating beta_hat로 운반할 때 e=beta_hat-beta를 exact로 구한다. 모든 original binary bounds에서 E=sum max(e_j*l_j,e_j*u_j)를 계산한다. alpha_hat을 alpha-E 이하로 outward-round하면 모든 domain z에서 alpha_hat+beta_hat z <= alpha+beta z다. original objective나 물리식은 바꾸지 않는다. transport로 인한 안전 손실을 기록한다. feasibility에도 같은 보수적 lower affine function을 사용하며 source separation을 다시 검사한다.

## Objective epigraph와 global bound

complete dual family의 supremum은 feasible bounded LP의 Q(z)와 strong duality로 같다. 모든 infeasible z는 bounded Farkas separation family로 제거된다. 따라서 complete family의 `min theta` epigraph는 original `min rho`와 동치다. **유한 cut registry의 master는 그 exact formulation의 relaxation**이며, 모든 recourse를 평가하기 전부터 exact optimum을 구했다고 주장하지 않는다. finite master BestBd는 original complete domain과 모든 valid cuts가 유지될 때에만 original global LB다. 모든 원본 feasible integer solution이 대응하는 master feasible point를 갖고 theta=original rho로 놓을 수 있기 때문이다.

초기 theta floor 0.5687116104049206은 사용자가 제공한 유효 global LB이며 PR179/182의 same-scientific-model receipt와 raw original identity를 확인했다. current sample의 restricted recourse ObjBound는 global LB로 사용하지 않는다. global gap은 (validated UB-certified LB)/abs(UB)다. native master BestBd를 사용할 때는 inherited native certificate contract와 numerical warning 검사를 함께 기록한다. exact weak-duality cut validity와 native MIP bound tolerance contract를 혼동하지 않는다.

## 독립 bounded 검증과 한계

1 MESS / 2 slots / 2 sites 및 2 MESS / 3 slots / 2 sites의 bounded **algebraic validation fixture**에서 route/travel, SOC, P/Q, PCS16, mode, grid/epigraph coupling을 검사했다. 이것은 과학적 raw input을 새로 합성하거나 원본 network를 대체하는 데이터가 아니다. 독립 direct monolithic MILP의 목적과 반복 master/recourse의 LB/UB가 1e-8 이내에서 일치했고 optimality 및 feasibility cut 양쪽을 검사했다. 실제 full C3A의 20개 known feasible assignments에서도 accepted cut을 모두 검사한다. 작은 fixture만으로 full scale 동치를 주장하지 않고 위의 전체 graph와 original matrix / weak-duality 증명을 함께 요구한다.

모델 동치나 valid cut은 실용적 속도를 보장하지 않는다. full canary는 별도 900초 budget이며, 0.5% target의 미달은 그대로 보고한다. 추가 budget과 production 통합은 이번 권한에 포함되지 않는다.
