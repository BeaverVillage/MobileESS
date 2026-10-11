# Source18r 물리 Global LB 독립 수학 검토

이 검토는 PR207의 기준 commit `497609b46faa14ea7e32a9483a333ab32fd264ef`에 있는 원본 모델 소스와 저장된 Source18r FULL CSR을 읽어 수행했다. 검토자는 Native optimize, presolve, 캠페인 실행 또는 추가 가중치 생성 없이 실제 차량 소유 support와 원본 목적함수를 독립 재집계했다. 측정 결과의 최종 수치 인증은 별도의 `INDEPENDENT_CERTIFICATE.json`을 확인해야 한다.

원본 matrix SHA는 `0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec`, domain SHA는 `9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e`이다. 저장된 case SHA는 `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`이다. 원본 CSR은 1,130,336행, 344,967열, Binary 208,312개이다. P1의 유일한 비영 목적계수는 `rho_max`의 1이고, ObjCon은 정확히 0이다. 원본 `rho_max` Bound는 [0,1]이다. movement 및 다른 P2 목적함수는 이번 P1 LB에 합산하지 않는다.

## 원본과 차량별 영역의 관계

차량 m의 열 집합 J_m은 원본 `arc`, `charge_mode`, `SOC`, `Pch`, `Pdis`, `Q` 중 이름의 첫 축이 그 차량인 열이다. 차량별 행 집합 I_m은 비영 support가 전부 J_m에 속하는 원본 행이다. D_m은 해당 원본 행, 원본 RHS와 sense, J_m의 원본 상한·하한 및 정수 타입을 그대로 만족하는 영역이다. 새 물리 제약, 경로 삭제, SOC 이산화 또는 계통 기반 C3A 강화 Bound를 추가하지 않는다.

| 차량 | 원본 행 | 원본 열 | Binary | Nonzero |
|---|---:|---:|---:|---:|
| MESS01 | 51,458 | 58,814 | 52,018 | 314,503 |
| MESS02 | 51,527 | 58,895 | 52,090 | 314,932 |
| MESS03 | 51,596 | 58,976 | 52,162 | 315,361 |
| MESS04 | 51,481 | 58,841 | 52,042 | 314,646 |

원본 가능영역을 F라 하자. 임의의 z∈F에 대해 x_m=z[J_m]는 원본에서 이미 만족한 I_m의 모든 행과 J_m의 Bounds·정수 타입을 만족하므로 x_m∈D_m이다. 따라서 차량 사영에 대해 `π_vehicle(F) ⊆ D_1 × D_2 × D_3 × D_4`이다. 하위 문제에서 생략한 공통 제약 때문에 차량별 최적값은 원본보다 낮아질 수 있지만, 원래 가능한 운전계획을 제거하지 않는다. 이 포함관계는 차량별 행의 열 제한 때 원래 Nonzero가 하나도 사라지지 않는 CSR 검사와 원본 축별 행·열·Bounds·타입의 일치 검사로 확인한다.

각 차량은 모든 96슬롯 energy_balance, SOC 97개, charge_mode 96개, 초기 SOC와 종단 SOC equality, 실제 이동 arc 이진변수, flow 및 terminal_location, P/Q 접속, 충방전 상호배타성, 개별 PCS16을 유지한다. 원본 SOC Bound는 440–1080이다. route의 flow 종점은 실제 `connect` 시점이므로 이동시간과 접속 지연을 함께 보존한다. 이동에너지는 출발 슬롯의 energy_balance에 의해 SOC[depart+1]에서 차감하는 원본 방식 그대로다. 모든 원본 귀환·재충전·Rebound 경로를 남긴다.

원본 terminal_location은 슬롯96에 끝나는 arc의 합이 1이라는 조건이다. 출발지로 복귀해야 한다는 새 조건은 없다. 이번 모델도 종단 SOC와 이 원본 위치 조건만 그대로 유지하며, 출발지 복귀를 추가하지 않는다. Solver 내부 LP relaxation과 미완료 B&B Bound는 가능하지만, 하위 문제 모델 자체의 경로 및 Mode 타입 B를 C로 바꾸지 않는다.

## 생략한 모든 결합·비차량 행

실제 혼합 support 행은 injection_P_binding 2,263개와 injection_Q_binding 2,263개, 합계 4,526개뿐이었다. 다른 차량 간 공통 물리 support 행은 실제 CSR에서 발견되지 않았다. 이 injection 정의를 각 차량에 원래 RHS 그대로 복제하면 공통 계통 정의를 잘못 부과하게 되므로 모든 차량별 가능영역에서 제거한다.

비차량 support 행 919,748개도 차량별 가능영역에서 전부 제거한다. 원본 행 partition은 `206,062 차량 행 + 4,526 혼합 행 + 919,748 비차량 행 = 1,130,336 원본 전체 행`으로 완전하다.

| 제거한 비차량 행 family | 행 수 |
|---|---:|
| flow: 비영 support 없는 원본 행 | 274 |
| injection_P_binding: 차량 support 없는 정의 | 41 |
| injection_Q_binding: 차량 support 없는 정의 | 41 |
| voltage_lower | 80,448 |
| voltage_upper | 80,448 |
| NormalAmps | 14,688 |
| response_transformer_P_binding | 14,688 |
| response_transformer_Q_binding | 14,688 |
| transformer_kVA | 235,008 |
| response_line_P_binding | 25,152 |
| response_line_Q_binding | 25,152 |
| response_line_correction_binding | 25,152 |
| line_thermal_face | 403,968 |

원본 차량 열은 235,526개이고 비차량 열은 109,441개이다. 비차량 열은 injection/response 연속 helper 109,440개와 rho_max 1개이다. helper Bound 또는 계통 제약을 차량별로 복제하지 않는다. 선택 thermal 식은 가능영역의 추가 제약이 아니라 LB 목적계수의 근거로만 사용한다.

## Thermal 식과 고정항·부호

원본 구현은 `v42_m1_sparse/grid.py:add_compressed`, `v42_may_campaign_native90/m_model.py:build_case`, `v42_native/mess.py:solve`에서 확인했다. injection 정의는 `injection_P[s,t] = Σ_m(Pdis[m,s,t] − Pch[m,s,t])`, `injection_Q[s,t] = Σ_m Q[m,s,t]`이다. Fixed AIDC는 원본 Forecast의 고정 PCC 값으로 조립되며 최적화 변수가 아니다.

선로 k의 `ap_k = branch_limit_k*cos(pi/16)`라 하자. anchor에서 최대 facet의 P/Q gradient를 g_k, `d_k = current_matrix[:,k] − g_k`, `B_k = current_constant_k + current_matrix[:,k]^T*anchor − max_f(flow_face_f(anchor)/ap_k)`라 하면 원본 thermal 표현은 다음과 같다.

`rho >= (cos_f*P_line + sin_f*Q_line)/ap_k + d_k^T*(control − anchor) + B_k`.

그러므로 flow의 고정항, 고정 AIDC 제어, correction의 `−d_k^T*anchor`, current bias B_k가 모두 b_k에 들어가야 한다. 각각의 차량에서는 Pch의 injection 부호가 음, Pdis의 부호가 양이며 Q의 부호는 해당 sensitivity 그대로다. Fixed AIDC, current correction 또는 원본 thermal RHS를 누락한 단순 P/Q 식은 이번 인증 식이 아니다.

실제 인증 계산은 위 식을 부동소수점으로 다시 생성하지 않고 저장된 원본 CSR을 권위로 사용한다. helper equality가 `y − Σ_j h_j*z_j = r`이면 정확히 `y = r + Σ_j h_j*z_j`로 대입한다. 모든 원본 저장 binary64 계수와 RHS를 Fraction으로 변환한다. 선택 thermal 원본 행이 `−rho + Σ_j q_j*z_j <= r_k`이고 helper 소거 후 `−rho + c_k + Σ_m a_km^T*x_m <= r_k`이면 정확한 `b_k = c_k − r_k`이다. 이때 rho 계수가 정확히 −1이고 sense가 `<`이며, 소거 후 남은 모든 열이 차량 물리 열인지 검증한다. equality 조합은 원본 가능해에서 동일하므로 이 대입은 유효한 원본 부등식이다.

선택 행의 equality 및 injection 정의를 독립적으로 다시 소거하고 계수·RHS를 재합성하는 것이 수학 인증이다. 기존 U4 점에서 thermal 값이 일치하는 numerical replay는 별도 진단이며, 그 점에서의 일치만으로 보편적인 항등식을 증명했다고 주장하지 않는다.

## 단일 가중치와 Global LB 증명

WEIGHTS.json은 기존 Source18r U4 운전에서 각 슬롯 최대 line_thermal_face를 먼저 선정한 후 값이 큰 서로 다른 16개 슬롯의 행에 정확히 1/16을 부여하는 한 벡터다. 동률은 원본 행 번호로 결정한다. 이 규칙은 최적화 이전에 고정했으며 16개 선택과 `w_k>=0`, `Σ_k w_k=1`을 정확한 유리수로 검증한다. 선택한 time/line/facet 및 모든 b_k·계수는 WEIGHTS.json의 원본 행 좌표로 공개한다.

`b_w=Σ_k w_k*b_k`, `c_m=Σ_k w_k*a_km`라 하자. 임의의 원본 가능해에 대해 `rho >= b_w + Σ_m c_m^T*x_m`이고 x_m∈D_m이다. 각 L_m이 `L_m <= inf_{x_m∈D_m} c_m^T*x_m`인 검증된 하한이면

`inf_{z∈F} rho >= b_w + Σ_m inf_{x_m∈D_m} c_m^T*x_m >= b_w + Σ_m L_m`.

원본 P1의 ObjCon은 0이므로 다른 고정항을 추가하지 않으며 b_w를 차량마다 반복하지 않는다. 기존 원본 rho lower bound 0을 이용할 경우에만 `max(0, raw_sum)`이 추가로 유효하다. 음수 또는 무한 raw 결과를 성능상 편의를 위해 임의의 유한 값으로 바꾸는 행위는 허용하지 않는다. 실용성은 실제 LB와 검증 UB 0.6760534504652341을 비교해 판단하며 3% 목표 달성을 전제하지 않는다.

## Native 목적계수와 Solver Bound 전달

정확한 c_m은 원본 binary64 수들의 유리수 곱·합이므로 Native에 전달되는 binary64 목적계수 ĉ_m과 미세하게 다를 수 있다. 실제 model readback으로 원본 CSR/RHS/sense/Bounds/types와 ĉ_m이 일치하는지 먼저 확인한다. 원본 유한 Bounds l_j,u_j를 사용해 `δ_j=c_j−ĉ_j`, `E_m=Σ_j δ_j*(l_j if δ_j>=0 else u_j)`를 정확히 계산한다. 모든 x∈D_m에 대해 `c_m^T*x >= ĉ_m^T*x + E_m`이다. 따라서 현재 Native 최소화 문제의 유효 Global Solver Bound β_m으로부터 `L_m=β_m+E_m`을 얻는다. 이 파일럿의 모든 원본 차량 Bounds는 유한하므로 이 보정은 유한성이 증명된다.

Solver Bound가 없으면 `Σ_j c_j*(l_j if c_j>=0 else u_j)`라는 원본 유한 Box의 하한을 정확히 계산할 수 있다. 이 값은 PCS/경로/SOC를 활용하지 않아 약할 수 있으므로 Bound의 출처와 실용성은 별도로 보고해야 한다. Solver 무한대 sentinel 또는 수치 오류를 유한 Bound로 인증하면 안 된다. NUMERIC, 메모리 부족 또는 예외는 증거와 중단 latch를 남기고 다음 차량을 실행하지 않는다. 실패한 현재 차량의 측정 Runtime 또는 unknown 상태도 전체 Native Ledger에 포함해야 한다.

여기서 β_m의 유효성은 사용자가 허용한 Gurobi의 현재 Global B&B Bound와 수치 계약을 전제로 한다. 검토 범위는 정확한 원본 모델 관계, 부호·RHS·고정항, 차량별 포함관계, 가중치, Native 목적계수 readback, 반올림 보정 및 Bound 합산이다. Gurobi B&B 자체를 exact proof trace로 독립 인증한 것은 아니다. 최종 독립 인증은 네 차량의 실제 상태·Bound·Runtime을 확인하고 합산 LB가 검증 UB를 초과하지 않는지도 확인해야 한다.

## 범위와 검토 결론

현재 구조는 거대한 Full MILP 또는 Full Root를 호출하지 않고, 네 대의 실제 전체 기간 정수 물리 영역을 네 개의 목적문제로 분리하는 유효한 Global LB 방식이다. DW Master, Column Generation, Pricing iteration, Branch-and-Price 또는 가중치 반복을 개발하거나 실행하지 않았다. PR147/203의 과거 LB·Column·Dual·Pricing 값을 현재 Source18r 수치로 재사용하지 않는다. U4 엔진과 Source18r 기존 자료는 수정하지 않는다.

수학적 분리 및 목적식에 실행을 차단할 오류는 발견하지 않았다. 실용적인 시간·RAM에서 유의미한 LB를 얻는지는 이번 한 번의 측정과 최종 독립 결과 인증에 따라 결정한다. NONMATERIAL이면 후속 확대를 기각하고 종료한다. MATERIAL인 경우에만 선택 계통 제약과 원본 차량 물리를 유지하고 나머지 계통 행을 제거한 Critical-Grid Reduced MILP를 후속 후보로 검토할 수 있다. 행 삭제에 따른 `F ⊆ F_reduced` 포함관계가 하한 용도에 필요한 증명이며, 그 모델의 점을 원본 Planning 가능해나 Actual PASS로 사용하지 않는다. 이번 검토와 파일럿 범위에서 그 후속 Solver 실행은 없다.
