# 4-MESS Joint Critical-Grid Reduced MILP 독립 수학 검토

이 검토는 Source18r 원본 모델, PR209 차량별 원본 물리 CSR, 저장된 Source18r C2/C3A 축과 exact reduction 증거를 읽어 수행한다. 이 검토 프로그램은 Gurobi를 import하거나 optimize하지 않으며 FULL CSR을 생성하거나 적재하지 않는다. 실제 실행 가능 여부, Native readback, 메모리 게이트와 최종 Solver Bound의 수치는 별도 Native0 및 최종 인증 파일을 따른다.

## 원본에서 축소 문제로의 포함관계

원본 FULL 가능영역을 F, 차량별 원본 물리 영역을 X_m, PR209에 저장된 16개 exact thermal 식을 `rho >= b_k + sum_m a_km^T x_m`이라 하자. 이상적인 exact Joint 영역 J는 X_1 × X_2 × X_3 × X_4, 16개 개별 부등식 및 원본 rho Domain [0,1]의 교집합이다. 모든 원본 가능해는 차량별 원본 행·Bounds·정수 타입을 만족하며, helper 정의 equality를 대입한 각각의 thermal 식도 만족한다. 따라서 `pi(F) ⊆ J`이고 `min_J rho <= min_F rho`이다. 축소 문제의 incumbent는 원본 FULL 가능해 또는 새로운 UB를 인증하지 않는다.

실제 구현은 저장된 Source18r Compact/C2/C3A 모델에서 route_flow, node_activity, charge_mode, SOC, Pch, Pdis, Q만을 support로 갖는 행을 선택하고, 계통 helper 열을 제거하며, 원본 rho_max와 PR209의 K16을 추가하는 경로를 사용한다. 원본 FULL CSR과 C3A/Joint 모델을 함께 적재하거나 FULL을 다시 생성할 필요가 없다.

저장된 C3A에서 선택한 물리 블록의 실측 규모는 143,260행, 244,264열, Binary 9,322개, NNZ 1,243,224개다. 이는 rho와 새 16행을 추가하기 전의 값이다. 물리 행은 energy_balance 384개, flow 8,942개, node_activity_link 8,746개, connected_Pch/connected_Pdis/no_simultaneous_charge/no_simultaneous_discharge 각각 8,942개, PCS16 89,420개다. 물리 열은 route_flow 207,736개, node_activity 8,938개, charge_mode 384개, SOC 380개, Pch/Pdis/Q 각각 8,942개다. 8개의 초기·종단 SOC는 원본 값 760으로 exact 대입된 것으로, 단말 조건을 삭제한 것이 아니다.

원본 행을 삭제하면 원래 가능해는 남아 있고 가능영역은 넓어진다. 원본 계통 Bounds를 차량별로 복제하지 않고 injection equality도 각 차량에 중복 부과하지 않는다. 이번 모델에서는 injection_P와 injection_Q를 각각 `sum_m(Pdis-Pch)`, `sum_m Q`라는 원본 등식으로 thermal 식에 대입한다. 선택하지 않은 계통 행은 연구 모델에서만 생략한다.

## Compact 경로의 정수성과 원본 복원

기존 `v42_supercompact/formulation.py`는 원본 arc 열의 이름을 route_flow로 바꾸고, 각 실제 time-expanded graph node에 node_activity Binary와 link equality를 추가한다. 각 arc의 시간은 엄격히 증가한다. 원본 flow equality는 원점의 유량 1, 다른 내부 node의 유량 보존을 유지한다. 활성 node의 outgoing sum 또는 종점 incoming sum은 Binary node_activity와 같다. 비음수 route flow와 이 제약 때문에 단일 원점에서 시작한 유량은 한 경로를 이루며 중간 node를 분수 활성화할 수 없다. 같은 출발·도착 node 사이의 parallel arc는 기존 constructor에서 Binary로 남긴다. 따라서 nonparallel continuous route_flow도 정수 값이 되며 원본 arc 경로로 복원된다. 경로의 분수 relaxation을 차량 물리 영역으로 채택하지 않는다.

모든 이동 arc의 실제 departure/connect 시점과 energy_balance의 이동에너지 계수는 원본 그대로다. 이동에너지는 원본처럼 출발 슬롯의 SOC[t+1]에서 차감한다. 실제 접속을 가리키는 stay/flow 결정과 Mode, PCS, 충방전 식도 보존된다. 원본 terminal_location은 아무 실제 site에서 H=96으로 끝나는 유량의 합이 1이라는 조건이며 출발지로 복귀해야 한다는 추가 조건은 없다. terminal_location 4행은 보존된 원본 flow equality들의 정확한 합으로 증명된 후 삭제되었기 때문에 이 조건은 계속 성립한다. 초기·종단 SOC, 96개 슬롯별 energy_balance, Rebound 및 모든 원본 복귀 경로를 유지한다.

C2의 192개 DETERMINISTIC_FLOW alias, 96개 node_activity unit alias, 4개 source node 고정, 8개 SOC endpoint 대입은 기존 exact static presolve와 역방향 복원식으로 처리한다. C3A의 53,652개 PCS16 행, 17,884개 Q 접속 행, 4개 terminal_location 행 삭제에는 저장된 exact Farkas 또는 flow-sum 증거가 있다. 남은 PCS16 89,420행은 각 접속 P/Q 블록에서 10개 facet을 남긴 표현이다. 나머지 6개 facet과 Q link는 보존한 물리 행과 원본 Bounds로부터 함의되므로 실제 16면 PCS 영역을 넓히거나 축소하지 않는다.

독립 `joint_physical_relation_audit.py`는 각 PR209 차량 CSR을 한 번에 하나씩 읽어, 보존된 C3A 물리 행의 계수·RHS·sense를 원본 행에 exact C2 alias를 대입한 결과와 일치하는지 확인한다. 추가 node_activity_link는 저장된 실제 DAG의 outgoing/incoming arc에서 재구성한다. 이 확인은 원본 가능해를 유지하는 행 선택이라는 사실을 수치 점 하나의 replay와 별도로 검사한다.

## Bounds와 좌표계

`CURRENT_C3A_AXES.columns`는 C2 기준 local identity `arange(339387)`이다. 원본 FULL 또는 C0 열 번호가 아니다. C3A는 열을 삭제하지 않았으므로 원본 열 좌표는 `CURRENT_C2_AXES.columns`를 사용한다. 원본 행 좌표는 `CURRENT_C2_AXES.rows[CURRENT_C3A_AXES.rows]`이다. 이 구분 없이 PR209 원본 열 번호를 C3A 열 번호로 직접 쓰면 서로 다른 물리 변수를 연결하게 된다.

K16의 4,608개 서로 다른 원본 Pch/Pdis/Q 열은 전부 C2에 남아 있으며 이름까지 일치한다. 따라서 K16의 차량 계수는 위 열 축으로 재번호화하면 되고 계통 helper 또는 차량 계수에 새로운 근사를 도입할 필요가 없다. 원본 rho_max의 Bounds [0,1], 연속 타입, 목적계수 1 및 ObjCon 0은 그대로 사용한다.

Source18r의 pre-C2 Bound 보정은 40개 SOC endpoint envelope, 8,942개 Q PCS envelope, 4개 source-flow node fix다. 이는 임의의 변수 고정이 아니다. SOC의 슬롯별 변화량은 원본 binary64 charge/discharge 계수를 exact rational로 해석하고 단일 차량의 300kW 접속 한계 및 해당 슬롯 최대 출발 이동에너지로 감싸며, 초기·종단 equality에서 전후방으로 전달한다. Q는 원본 PCS16과 P 한계의 exact polygon vertex에서 얻은 최소·최대 Q를 바깥 방향 binary64로 변환한다. 원점 node 값은 원본 flow에서 직접 함의된다. `security_verify.py`는 실제 원본 행으로 이 함의를 독립 검증한 Source18r 증거를 제공한다.

선택 C3A의 추가 95,122개 affine Bound 강화는 injection/response 계통 helper에만 적용되었다. 이번 연구 모델에 유지한 물리 열에는 C3A 추가 강화가 0개이고, 제거한 계통 helper Bounds를 새 물리 제약으로 전달하지 않는다. 저장된 EXACT_PHYSICAL_PRESCREEN은 SOC arc 삭제 0개, SOC Bound 변경 0개와 ANY_SITE_AT_H를 명시한다. 원본에서 함의되지 않는 arc 삭제나 Bound 강화를 추가하지 않는다.

## K16의 정확한 식과 Native 반올림

PR209의 WEIGHTS.json에 저장된 16개 원본 `line_thermal_face` identity 및 exact rational b_k·a_km를 그대로 사용한다. 고정 AIDC/Forecast, injection P/Q, response_line P/Q, response_line_correction, 원본 RHS 및 rho 계수를 포함한 원본 helper equality 소거의 결과다. 이번에는 16개 행을 각각 같은 rho 아래에 적용하며 1/16 가중합으로 대체하지 않는다.

exact 부등식을 `a_k^T x-rho <= r_k`, `r_k=-b_k`라 하자. Native에 넣는 binary64 계수를 ahat_k라 하고 `delta_j=ahat_j-a_j`라 하면, 유지한 유한 변수 Bounds에 대해 `E_k=sum_j delta_j*(u_j if delta_j>=0 else l_j)`는 모든 해당 x에서 `(ahat_k-a_k)^T x <= E_k`를 보장한다. 따라서 실제 Native RHS rhat_k가 exact rational `r_k+E_k` 이상이 되도록 바깥 방향으로 반올림하면, 원본 exact 부등식을 만족하는 점은 Native 행도 만족한다. rho 계수 -1은 정확히 표현되므로 오차 0이다. 아주 작은 계수를 임의로 삭제하지 않고 Native readback에서 CSR·RHS·Bounds·Types·Objective의 실제 저장값까지 확인해야 한다.

이론 비교는 exact J에 대한 명제다. 보수적 Native RHS 보정은 J를 미세하게 넓힐 수 있으므로 Native 최적값에 exact J의 가중합 우위를 반올림 오차 없이 엄격히 강제하지 않는다. 보정량과 변수 Bounds로 그 차이를 따로 감쌀 수 있다. Global LB의 유효성에는 원본 가능영역이 Native 영역에 포함되는 방향이 핵심이다.

## PR209와의 비교 및 인증 범위

정확한 `w_k=1/16`에 대해 J의 모든 점은 `rho >= sum_k w_k b_k + sum_m sum_k w_k a_km^T x_m`을 만족한다. 각 x_m은 X_m에 있으므로 `min_J rho >= L_w*`, 여기서 `L_w*=sum_k w_k b_k + sum_m min_(x_m in X_m) sum_k w_k a_km^T x_m`이다. PR209에서 보정해 인증한 LB는 L_w* 이하인 값이다. 따라서 exact Joint의 최적값은 그 PR209 LB 이상이다.

Joint MILP가 TIME_LIMIT로 끝나면 반환 Solver Bound는 Joint 최적값의 하한이다. Joint 최적값이 L_w* 이상이라는 사실은 미완료 Bound도 그 이상이라는 뜻이 아니다. 반환 Bound에 PR209 LB를 직접 강제하거나 incumbent를 LB로 사용해서는 안 된다.

독립 exact 인증은 원본 식의 유리수 항등식, 사영 포함관계, 원본 물리 영역의 exact compact 변환·역변환 및 binary64 입력의 보수적 RHS 보정을 인증한다. Gurobi B&B의 전체 exact proof trace를 검증하거나 exact 최적성 인증을 발급하는 것은 아니다. 실제 유한 Solver Bound의 전역 유효성은 실행 상태, 수치 오류 부재, readback 및 Gurobi의 수치적 global-bound 계약을 전제로 별도 보고한다. Source18r Full Solver ObjBound 0.28940049108548904도 같은 구분으로 표시한다.

크기 또는 메모리 게이트 실패 시 optimize하지 않고 종료해야 한다. 실행은 게이트 PASS 후 Native optimize 최대 1회, 90초, Worker 1, Threads 1이며 이후 재실행·시간 연장·K16 확대를 승인하지 않는다. 수치 실용성 판정은 새 Bound가 현재 Full Solver Bound보다 최소 0.001 개선하는지와 3% Global Gap 목표 달성 여부를 각각 측정한 뒤 결정한다.
