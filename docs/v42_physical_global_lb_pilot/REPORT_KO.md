# Source18r 물리 기반 독립 Global LB 파일럿: NONMATERIAL

결론은 **VALID_GLOBAL_LB_NONMATERIAL**이다. 원본 FULL Root 없이 네 차량의 실제 정수 다기간 운전영역으로 유효한 Global LB를 57.092 Native 초 안에 계산했다. 그러나 **LB=0.11666465693783702**, 검증 UB=0.6760534504652341 대비 **Gap=82.7432791212658%**로 매우 약하다. 가중치 재조정·반복, DW/CG/B&P, Critical-Grid Reduced MILP 확대를 채택하지 않는다. 추가 Solver 실행은 0회다.

## 원본과 정확한 관계

기준은 PR207, Source18r `497609b46faa14ea7e32a9483a333ab32fd264ef`이다. 연구 브랜치는 `codex/v42-source18r-physical-global-lb-pilot-20261012`이며, 실제 성공 실행 전 source freeze commit은 `9e3b0912`이다. 현재 B2 May01 Forecast와 고정 AIDC 및 기존 U4만 사용했다. Source18r, U4 엔진, PR207 결과와 기존 입력은 변경하지 않았다.

Case SHA: `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`. FULL matrix SHA: `0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec`. FULL domain SHA: `9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e`.

원본 FULL의 목적은 정확히 `min rho_max`, ObjCon=0, rho Bound=[0,1]이다. 각 차량의 원본 열과 그 차량만 support에 가지는 원본 행을 모두 복사했다. RHS/sense/Bounds/Binary를 바꾸지 않았으며 C3A의 계통 기반 강화 Bound를 가져오지 않았다. 각 차량의 실제 arc Binary, 96슬롯 Mode/P/Q/energy_balance, SOC[0..96], 초기·종단 SOC, flow, 접속, 이동시간·이동에너지, PCS16, Rebound·귀환 경로 가능성을 유지했다. 원본 종단 위치 조건은 96슬롯에 끝나는 위치 하나이며 출발지 복귀를 새로 강제하지 않았다.

| MESS | 행 | 열 | Binary | NNZ |
|---|---:|---:|---:|---:|
| 01 | 51,458 | 58,814 | 52,018 | 314,503 |
| 02 | 51,527 | 58,895 | 52,090 | 314,932 |
| 03 | 51,596 | 58,976 | 52,162 | 315,361 |
| 04 | 51,481 | 58,841 | 52,042 | 314,646 |

원본 1,130,336행은 차량 행 206,062개, 혼합 행 4,526개, 비차량 행 919,748개로 완전히 분리된다. 실제 혼합 행은 injection_P_binding 2,263개와 injection_Q_binding 2,263개뿐이다. 이를 차량별로 복제하지 않았다. 비차량 행 전체를 제거했으며 여기에는 voltage_lower/upper, NormalAmps, transformer_kVA, line_thermal_face와 모든 계통 Response 정의가 포함된다. 274개의 빈 물리 flow 행은 정확한 0=0이다. 전체 생략 family별 수는 NATIVE0.json과 MATH_REVIEW_KO.md에 있다.

임의의 원본 가능해 z는 각 차량 원본 행과 Bounds 및 Binary를 이미 만족한다. 따라서 `pi_vehicle(F_FULL) subset X_01 x X_02 x X_03 x X_04`이다. 모든 단일 차량 행의 CSR과 모든 열의 Bounds·타입이 원본과 일치하므로 원래 가능한 운전계획을 제거하지 않는다. 차량 조합이 원본 계통 제약을 만족한다는 보장은 없으며, 이 하위 문제 incumbent는 원본 Planning 가능해 또는 Actual PASS로 쓰지 않는다.

## 원본 thermal 복원 및 단일 w

원본 제약은 `rho >= (cos(f)*response_P + sin(f)*response_Q)/ap + response_correction + bias`이다. `ap=branch_limit*cos(pi/16)`이고 `correction=current_matrix.T-grad`, `bias=current_constant+current_matrix.T*coefficient_anchor-max(raw_facets)`이다. Response P/Q/correction 정의의 원본 RHS에는 고정 AIDC 효과와 선형화 anchor 보정이 포함된다. 원본 injection 정의는 `P=sum_m(Pdis-Pch)`, `Q=sum_m Q`이다.

원본의 저장된 binary64 계수와 equality RHS를 정확한 Fraction으로 소거하여 모든 선택 행을 `rho >= b_k + sum_m a_km*x_m`로 복원했다. 독립 검증은 원본 RHS·부호·보조변수 축·주입 P/Q의 부호와 모든 정확한 b/계수를 재계산했다. 별도의 전기계수 NPZ 감사는 1,152개의 고정 AIDC P 제어와 현재 Forecast identity를 확인하고 P/Q·grid correction·원본 RHS를 대조했다. 그 수치 조립 차이는 최대 1.1102230246251565e-16이다. 이 수치 재현으로 원본 수학 영역을 재정의하지 않았으며 인증의 기준은 저장 FULL 계수의 정확한 유리수다.

기존 U4에서 슬롯별 최대 thermal facet을 선택하고 상위 16개 서로 다른 슬롯에 각각 정확히 **w=1/16**을 부여했다. 생성 벡터 1개, 가중치 반복 0회다. 슬롯·facet·branch index는 0부터 시작하는 원본 축이다.

| 슬롯 | 원본 Branch index | Branch | Facet | w |
|---:|---:|---|---:|---:|
| 33 | 33 | line.sw2::A | 15 | 1/16 |
| 31 | 26 | line.l10::A | 1 | 1/16 |
| 24 | 26 | line.l10::A | 1 | 1/16 |
| 29 | 26 | line.l10::A | 1 | 1/16 |
| 34 | 33 | line.sw2::A | 15 | 1/16 |
| 73 | 64 | line.l52::A | 15 | 1/16 |
| 83 | 64 | line.l52::A | 15 | 1/16 |
| 70 | 26 | line.l10::A | 1 | 1/16 |
| 72 | 26 | line.l10::A | 1 | 1/16 |
| 74 | 64 | line.l52::A | 15 | 1/16 |
| 89 | 64 | line.l52::A | 14 | 1/16 |
| 32 | 33 | line.sw2::A | 15 | 1/16 |
| 79 | 64 | line.l52::A | 15 | 1/16 |
| 76 | 64 | line.l52::A | 15 | 1/16 |
| 75 | 26 | line.l10::A | 1 | 1/16 |
| 67 | 26 | line.l10::A | 1 | 1/16 |

정확한 행 번호, b_k, 전체 원본 열 계수와 weight는 WEIGHTS.json, 전기계수·Forecast/RHS 연결은 GRID_PROVENANCE_AUDIT.json에 있다. 고정 가중합은 **0.5743359823311205**이다. 목적계수의 native double 반올림 차이는 원본 유한 Bound에서 exact min-box를 계산해 각 차량 LB에 약 -8.991e-17을 보정했다. 원래 목적상수는 0으로 한 번만 처리했다.

## 실제 Solver 결과와 자원

MESS01→04, 순차 독립 프로세스 1 Worker, Threads=1이다. 실제 TimeLimit=29초로 30초 상한에 여유를 두었다. 네 모델 모두 OPTIMAL(Status=2), Local Gap=0이며 무한대·임의 유한 fallback 없이 각 실행의 현재 Global Solver Bound를 사용했다. 아래 LB는 목적계수 반올림 보정과 아래 방향 반올림을 포함한다.

| MESS | Solver Bound / incumbent | 검증 LB | Native 초 | 생성·readback 초 | Peak RSS MiB | Peak private MiB | Gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| 01 | -0.11441770278501288 | -0.11441770278501298 | 8.091 | 0.236387 | 252.406 | 1306.973 | 0% |
| 02 | -0.11441787420275673 | -0.11441787420275683 | 27.921 | 0.215049 | 354.684 | 1484.012 | 0% |
| 03 | -0.11441787420275674 | -0.11441787420275684 | 8.934 | 0.226198 | 257.383 | 1308.789 | 0% |
| 04 | -0.11441787420275676 | -0.11441787420275686 | 12.146 | 0.209842 | 305.953 | 1385.820 | 0% |

Native 합계는 **57.091999769210815초**, 모델 생성/readback 합계는 **0.8874763998901471초**다. Peak RSS는 371,912,704 bytes, Peak private commit은 1,556,099,072 bytes다. Gurobi MaxMemUsed 최대는 0.42033454 GB이다. RSS와 private commit 및 Gurobi memory는 서로 다른 지표이며 합산하지 않는다. 차량별 Windows 프로세스 peak를 독립 프로세스에서 측정했다. 모델 추출/Native0 wall 37.9467초 및 독립 Native0 재검사 15.7914초는 Native Runtime과 구분한다. 차량별 실제 Solver API Runtime·Gurobi log·입력 readback·incumbent 벡터를 모두 보존했다.

원본 FULL CSR로부터 모델을 직접 분리해 생성했다. solver의 내부 local LP/B&B는 사용했지만, 원본 경로 Binary를 C로 바꾸지 않았다. Full-size C3A MILP/Full Root/원본 Root LP 호출 **0회**, campaign 실행 **0회**, 추가 Solver 실행 **0회**다. 메모리 부족·수치 오류는 없었다.

## 독립 Global LB 인증과 판단

Convex w의 합은 정확히 1이고 모두 비음수다. 임의의 원본 가능해에 대해 `rho >= sum_k w_k*b_k + sum_m c_m*x_m >= fixed + sum_m LB_m`이다. 차량 목적의 최솟값 또는 유효한 Native Global Bound에 exact 목적 반올림 보정을 적용하므로 합산값은 원본 Source18r FULL P1의 하한이다.

독립 최종 인증 **PASS**: INDEPENDENT_CERTIFICATE.json은 원본 SHA·완전한 단일 차량 행/열·모든 Bounds/정수 타입·소거 식·weight·native readback·source freeze SHA·Bound 전달·정확한 합산·UB 및 Gap을 재검사했다. 각 하위 문제 incumbent도 자체 원본 물리 행렬/Bounds/정수 축으로 독립 replay했다. 인증은 Gurobi의 유효 Global Bound 수치 계약을 전제로 하며, B&B의 exact proof trace 자체를 인증했다고 주장하지 않는다. 원본 stored affine Planning 모델의 인증이며 비선형 Actual AC의 인증으로 사용하지 않는다.

정확한 합산값은 `1300854394022345696354583004709271319915531/11150372599265311570767859136324180752990208`이고, 아래 방향 보고값은 **0.11666465693783702**다. 검증된 U4 UB **0.6760534504652341** 대비 Gap **82.7432791212658%**다. 3%에 필요한 LB 약 **0.655771846951277**은 성능 목표이며 이 방법이 달성한다고 가정하지 않았다. 사전등록에서 MATERIAL 기준을 이 3% 목표 충족으로 고정했다.

고정한 w에 대해 네 하위 문제 모두 최적해가 확인됐다. 따라서 더 긴 동일-w 차량 B&B로 해결할 약함이 아니다. 단일 가중합과 대부분 계통 제약을 제거한 차량 직적은 서로 다른 원본 계통 병목을 충분히 제한하지 못했다. 이번 데이터는 다른 w나 DW 확대로 개선된다는 근거를 제공하지 않는다. **후속 확대 기각**, Critical-Grid Reduced MILP는 이번 후속 후보로 채택하지 않는다. 추가 가중치 생성·Iteration·DW Master·CG·B&P·Reduced MILP 개발/실행을 하지 않았다.

## PR147/203 및 보존

PR147은 과거 FULL 원본 Arc LP에서 모든 Binary를 완화하고 전체 grid 행을 유지해 exact-rational LP 하한을 인증했으며 별도로 DW/CG를 실행했다. PR203은 과거 full96 차량 궤적을 DW Master의 모든 계통 coupling/nonunit 행과 연결하고 true-dual pricing·Column·CG 기구를 사용했다. 이번 모델은 Source18r의 선택 thermal 행을 정확히 소거한 한 번의 convex 가중합에 대해 실제 Binary 차량 물리 모델 네 개의 support 최소만 합한다. Master, Dual, Column, Pricing/CG 반복은 없다. 과거 두 PR의 수치 LB·Column·Dual·Pricing 결과는 현재 하한 계산에 사용하지 않았다.

첫 실행은 Gurobi10013으로 한글 absolute LogFile을 열지 못해 **최적화 전** 중단했다. 당시 Native Runtime=0, optimize_calls=0이고 STARTED가 없었다. 실패 로그/ERROR/STOP/ledger를 failed_pre_native_logpath/에 그대로 보존했다. exact 동일 모델·w를 유지한 ASCII 상대 LogFile만 수정하고 guard로 0회·0초를 확인했다. PRE_NATIVE_LOGPATH_REPAIR.json은 이 I/O 실패만 허용하며 수치·메모리·실행 중 실패에는 적용할 수 없다. Native 예산 reset은 없고 성공 실행 4회·57.092초가 전부다.

HOLD_READONLY.json 및 HOLD_POST_PILOT.json에서 5월 HOLD, campaign worker 0, Windows 예약 2개 Disabled, heartbeat PAUSED를 읽기만 확인했다. 마지막 스냅샷의 controller 7개는 중지 상태다. 첫 사후 스냅샷에서 일시적 status 변화와 0.015625초 단위 CPU 증가가 관측되어 연속 zero-CPU 중지 보존까지 인증하지는 않는다. 모든 dispatch 금지·HOLD marker·예약·자동화 상태는 동일했고 worker/후손 실행은 관측하지 못했으며 process 상태를 변경하지 않았다. PR207 기존 Source18r head와 결과, 기존 Source17/Source18 파일 및 Frozen 입력을 수정하지 않았다. 연구 worktree의 일부 상속 파일은 Git checkout의 CRLF/LF 표현만 다르며 normalized 내용과 Git blob은 동일하다. 현재 결과 source·수학·Native 증거는 독립 새 브랜치에서 Commit/Push 및 Draft PR로 제출한다.

회귀 검사는 신규 symbolic/adversarial 7개 PASS, 별도 독립 verifier의 3개 corruption rejection과 정확한 substitution self-test PASS다. Native0/전기계수 provenance/독립 최종 인증 PASS이고 기존 full suite·전체 캠페인을 실행하지 않았다.
