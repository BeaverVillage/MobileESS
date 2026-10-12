# 원본 96-slot 정수 projection 보존 증명

과학적 모형은 원본 C3A `Ax (<=,=,>=) b`, 유한 경계 `l<=x<=u`, 원본 binary 집합 B 및 `min rho`다. 저장된 binary64 계수를 정확한 dyadic 수로 해석한다. 모든 원본 행·경계·type은 그대로 유지한다. 새 변수는 연속형이며 목적계수는 정확한 +0이다. 각 새 행은 독립 verifier가 원본 계수와 정확한 유리수 산술로 대조한다.

선택한 원본 행 집합 I에 나타나는 모든 원본 열을 J에 포함한다. outside-window 경계 SOC와 travel/flow 열도 실제 원본 행의 nonzero가 있으면 복사한다. 관측 ROOT SOC, 특정 trajectory, 임의의 도착 상태로 경계를 고정하지 않는다. 96-slot 원본 전체의 boundary route, movement, travel time/energy, SOC, P/Q, PCS, grid, robust voltage와 A1 행은 제거하거나 교체하지 않는다.

## A: 공동 fleet/time occupancy-count disjunction

두 MESS 및 네 slot의 선택 site activity 8개에 대해 `q=sum x_j`를 정의한다. 모든 원본 정수 해에서 q는 0..8 중 정확히 하나다. **아홉 값 전체**를 사용한다. 각 k의 λ_k≥0, sum λ=1 및 y^k_J를 만들고 다음을 둔다.

`A_I,J y^k (<=,=,>=) b_I λ_k`

`l_J λ_k <= y^k <= u_J λ_k`

`sum_selected y^k_j = k λ_k`, `x_J=sum_k y^k_J`.

Forward: 임의의 원본 full-horizon 정수 feasible x에 대해 실제 q=k*의 λ를 1, 다른 λ를 0으로 두고 y^k*=x_J, 나머지 y=0으로 둔다. 원본 행과 경계가 모든 새 행을 만족한다. λ=0의 유한 perspective 경계는 y=0을 강제하므로 빈 term에도 비정상 recession을 허용하지 않는다. 이것은 sample-based complete-hull 주장이 아니며, 모든 원본 trajectory가 실제 count term에 들어간다는 대수적 증명이다.

Inverse: 확장 MILP의 feasible (x,y,λ)에서 추가 변수를 버리면 모든 원본 행·경계·binary type이 남으므로 원본 feasible x다. 두 포함 관계로 **원본 정수 projection은 정확히 동일**하다. 이 증명은 slot 수나 전기 계수에 의존하지 않아 원본 96 slots에도 적용된다.

LP에서는 선택 subpolytope의 integer aggregate count union을 convexify한다. slot별 모든 count나 모든 mode/location/route의 완전한 integer hull을 주장하지 않는다. 전체 count 단일 집계의 정보 손실과 window 바깥의 fractional freedom은 성능상 한계로 측정한다. 81 slotwise words는 solve 이전에 추가 열 1199286개로 확인되어 보존하되 실행하지 않았다.

## B: 네 MESS의 공동 시간/grid/SOC boolean products

선택 원본 binary b_s마다 연속 selector copy λ_s=b_s 및 y_s,j를 만들고, 모든 선택 행을 b_s와 (1-b_s)로 곱한 두 행을 둔다. 등식의 complement는 유지된 원본 등식에서 자동으로 따라오므로 중복 생성하지 않는다.

`A_I,J y_s (<=,=,>=) b_I λ_s`

`A_I,J (x_J-y_s) (<=,>=) b_I(1-λ_s)`

`l_J λ_s<=y_s<=u_J λ_s`

`l_J(1-λ_s)<=x_J-y_s<=u_J(1-λ_s)`.

추가로 `y_s,b_s=b_s`, 다른 선택 binary 사이에 `y_s,b_t=y_t,b_s`를 둔다. 이 공유 moment가 cross-MESS/time 결정을 연결한다. 유효성은 원본 integer x에서 **y_s,j=b_s x_j**라는 명시적 lifting으로 직접 증명된다. inverse는 A와 같다. 각 inequality는 원본 유효 행에 비음수 Boolean b 또는 1-b를 곱한 것이므로 모든 원본 정수 해에 유효하다.

λ copy를 별도 열로 둬 original row의 b 계수와 RHS를 한 열에 더해 binary64 rounding을 일으키지 않는다. 기존 계수와 RHS는 그대로 복사하고 부호만 바꾼다. 선택한 physics/grid 모든 source row에 대해 validity certificate를 제공한다. 이는 single-MESS PCS hull 또는 기존 local trajectory hull 재실행이 아니라 공동 selector의 grid/SOC/route row lift와 cross-selector consistency다.

## 검증과 LB 권한

bounded small case 전체 route/mode enumeration은 구현과 부호 오류를 검증하는 보조 증거다. 96-slot validity는 위의 일반 lifting/projection 증명 및 모든 실제 compiled row의 독립 exact coefficient verifier가 제공한다. 원본 UB는 전체 원본 physics replay 후 모든 강화 행에 lift/replay한다.

OPTIMAL 강화 LP의 sign-corrected multiplier π에 대해 `r=c-A^Tπ`, `L=ObjCon+π^T b+sum_j min(r_j l_j,r_j u_j)`를 원본+검증된 강화 배열에서 dyadic 산술로 계산한다. 유한 bounds와 원본 inequality 방향이 이 값을 모든 강화 feasible point의 하한으로 만든다. 위 projection 동등성이 있으므로 이 인증만 원본 integer M1의 global LB로 옮긴다. native LP objective/ObjBound 및 제한된 자식 bound는 전역 proof로 쓰지 않는다.

Balas homogeneous representation의 배경은 [Conforti–Di Summa–Faenza, Theorem 1](https://arxiv.org/pdf/1711.00891)이다. 이 작업의 정수 projection 주장은 외부 정리를 단순 인용하지 않고 위의 명시적 forward/inverse construction으로 검증한다.
