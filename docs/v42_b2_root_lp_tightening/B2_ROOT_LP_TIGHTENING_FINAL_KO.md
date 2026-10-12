# V42 B2 Root LP Tightening 최종 보고

작성 시각 2026-10-12T10:08:15+09:00 (Asia/Seoul). IEEE123 / B2 / 2025-05-01.

최종 판정: **ROOT_LP_SOC_NONMATERIAL_GRID_UNCERTIFIED**. 현재 완료·독립 인증된 BASE LP 목적값은 **0.4649848699754816**, exact weak-duality 하한은 **0.4649847749345196**이다. 후속 MIP 후보의 하한 개선 채택 기준 0.001을 충족한 후보는 **없음**이다. 누적 유효 Global LB는 **0.46498486997548166**, 원본 검증 U4 UB 대비 Gap은 **31.22069421%**다.

새 Native는 3회 / 최대 3회, 각 요청 최대 240초, 요청 예산 합 720초 / 최대 720초다. 실제 Native Runtime 합 222.292000초, Optimize Wall 합 226.349869초. Full MILP B&B·U4 변경·Production 통합·공식 5월 캠페인·IEEE8500·GRID+SOC 결합 실행은 0회다.

## 1. Source·기준과 실제 BASE 확보

| 기준 | commit / 값 | 역할 |
| --- | --- | --- |
| PR211 정확한 부모 | d12315a3757aec187c8da0685c28ef901466386a | K48 물리·Grid CSR/Domain 및 실행 증거 재사용 |
| Source18r 롤백 기준 / PR207 | 497609b46faa14ea7e32a9483a333ab32fd264ef | 원본 FULL 물리·계통 coefficient Authority |
| PR211 기존 Global LB | 0.46498486997548166 | 과거 수치 MIP ObjBound 계약에 따른 검증값 |
| 원본 검증 FULL U4 UB | 0.6760534504652341 | 모든 Global Gap의 유일한 UB |
| 현재 BASE Native 목적값 | 0.4649848699754816 | 실제 numerical OPTIMAL 결과; 기존 숫자를 가정하지 않음 |
| 현재 BASE exact weak-duality LB | 0.4649847749345196 | 완료 LP Pi의 sign 및 finite-box stationarity 보정 하한 |

PR211 실행에는 전체 Root fractional vector가 저장되지 않아 K48의 원본 행·RHS·Sense·Bounds·rho Objective를 그대로 복사하고 원래 9,322개 Binary만 C로 완화한 별도 BASE LP를 구성했다. 기존 route_flow는 원래 C였고 추가 물리 완화·열 삭제·Bounds 강화는 없다. LP는 실제 status=OPTIMAL(2)이며 Primal/Pi/RC를 저장해 독립 검증했다. 중단 Barrier나 simplex 로그 목적값, IntInf만으로 벡터를 만들어내지 않았다.

## 2. BASE 분수 운전 구조

| 변수 Family | 분수 개수 (1e−8 기준) | 양의 값 개수 |
| --- | --- | --- |
| node_activity | 1628 | 1652 |
| charge_mode | 121 | 128 |
| route_flow | 1928 | 1950 |

차량·slot 단위에서 C와 D가 함께 양수인 경우는 5개다. 같은 station에서 Pch/Pdis가 동시에 양수인 경우는 0개다. 이는 서로 다른 station의 분수 location과 하나의 분수 Mode가 허용한 aggregate C/D 섞임을 보여준다. 분수 개수 감소 자체를 채택 근거로 삼지 않는다.

원래 에너지 행 최대 수치 잔차는 0.000000000036다. 각 차량의 97개 SOC 경계와 원래 초기/종단 760 kWh를 inverse alias로 유지했다. retained node 이름만 집계하면 slot95의 alias된 node95→node96 상태가 빠질 수 있다. literal retained location 질량 0을 charging-in-transit의 증거로 해석하지 않는다. Original node/STAY 사영은 저장 Compact/alias 검증과 SOC 후보의 원본 route audit로 확인한다. travel 진단의 retained energy term 외에도 제거된 상수 alias의 이동 debit은 실제 행 RHS에 들어 있다. 완전한 원본 departure debit은 SOC exact 후보의 원본 행 reconstruction에 보존했다.

`SOC_BASE_FRACTIONAL_DIAGNOSTICS.json`은 alias 역매핑 후 원본 384개 차량·slot의 SOC_before/after, C/D, departure T, Mode, STAY/move/transit 질량을 별도로 기록한다. 복원 원본 arc의 분수 개수 합은 1981개이며 retained route_flow 1,928개와 축이 다르다. 충전과 출발 travel debit이 함께 양수인 분수 slot은 99개다. 원본 energy Fraction replay 최대 잔차는 0.000000000036다. 이는 분수 운전 혼합의 진단이며 실제 정수 차량이 이동 중 충전했다는 주장이 아니다.

| MESS / slot | 원본 C(kW) | 원본 D(kW) | SOC 전 / 후(kWh) | Mode | STAY / depart-move / transit 질량 |
| --- | --- | --- | --- | --- | --- |
| MESS01 / 95 | 145.791829 | 28.120602 | 732.774599 / 760.000000 | 0.14247776 | 1.00000000 / 0.00000000 / 0.00000000 |
| MESS02 / 95 | 252.377752 | 2.100283 | 700.612990 / 760.000000 | 0.25005081 | 1.00000000 / 0.00000000 / 0.00000000 |
| MESS03 / 95 | 138.648015 | 43.880828 | 738.618683 / 760.000000 | 0.14626943 | 1.00000000 / 0.00000000 / 0.00000000 |
| MESS04 / 92 | 104.591407 | 24.182856 | 574.005943 / 592.482493 | 0.11937497 | 0.42924754 / 0.00000000 / 0.57075246 |
| MESS04 / 95 | 217.047555 | 8.693088 | 710.738860 / 760.000000 | 0.16982897 | 1.00000000 / 0.00000000 / 0.00000000 |

세부 384개 차량·slot 에너지/C/D/Q/Mode/location/travel 기록은 `BASE_FRACTIONAL_DIAGNOSTICS.json`에 있다. 어떤 분수값도 반올림·정수화하거나 Planning 가능해/Actual PASS로 승격하지 않았다.

## 3. 후보 A: 실제 Fractional Root Grid Separation

원본 Security 814560행을 검사해 4219개 확인 탐색 후보에서 16개만 선정했다. 원본 injection/response/correction 정의를 저장 FULL CSR로 재구성하고 선정 행은 Fraction 기반 원본 Row SHA·Sense·RHS·Phase·축 대조를 통과한다. 실행 전 BASE point SHA와 완료 인증, B1 안전/다른 Heavy Solver 부재를 확인한 후 FULL CSR에 접근했다. FULL CSR와 Native Solver model은 동시에 중복 상주시키지 않았다.

| Family | 원본 행 | 누락 행 | 확인 탐색 후보 | 최대 원시 위반 | 미확정/0 부근 |
| --- | --- | --- | --- | --- | --- |
| line_thermal_face | 403968 | 403932 | 3965 | 0.2877095515 | 0 |
| transformer_kVA | 235008 | 235004 | 0 | -0.0286765239 | 0 |
| voltage_upper | 80448 | 80444 | 204 | 0.7430917151 | 2 |
| voltage_lower | 80448 | 80444 | 50 | 0.2446337910 | 2 |
| NormalAmps | 14688 | 14688 | 0 | -0.2513955968 | 0 |

thermal은 부하율 pu, voltage는 원본 squared-voltage pu², transformer는 kVA, NormalAmps는 전류 부하율 pu로 기록한다. Family 내부 분수 위반 순위가 우선이며, 동률은 원본 저장 coefficient의 P/Q L1 민감도 상한과 Row ID로 정한다. 서로 다른 단위를 직접 비교하지 않는다. 민감도는 진단·tie-break이고 exact 계수 Authority를 대체하지 않는다. 기본 quota 10 thermal+2 transformer+2 upper+2 lower에서 실제 transformer 위반이 없으면 정해진 순서로 quota를 보충한다. 원본 기존 K48 행과 exact coefficient/RHS 중복은 제거하고, 실제 서로 다른 유효 행은 다양성만으로 영구 제외하지 않는다.

| 원본 FULL Row ID / 이름 | Asset / phase | Slot / facet | 원시 위반 | 정규화 위반 | 정규화 민감도 상한 |
| --- | --- | --- | --- | --- | --- |
| 927305 / line_thermal_face[75,95,14] | line.l53 / C | 75 / 14 | 0.2877095515 | 0.2877095515 | 0.0505342241 |
| 926966 / line_thermal_face[75,77,14] | line.l52 / C | 75 / 14 | 0.2867056225 | 0.2867056225 | 0.0508024388 |
| 1106151 / line_thermal_face[94,3,1] | line.sw1 / A | 94 / 1 | 0.2817729611 | 0.2817729611 | 0.0437006350 |
| 926721 / line_thermal_face[75,64,14] | line.l52 / A | 75 / 14 | 0.2762300067 | 0.2762300067 | 0.0489932843 |
| 927079 / line_thermal_face[75,83,14] | line.l53 / A | 75 / 14 | 0.2726477468 | 0.2726477468 | 0.0483944612 |
| 992657 / line_thermal_face[82,33,0] | line.sw2 / A | 82 / 0 | 0.2631753329 | 0.2631753329 | 0.0451551054 |
| 926137 / line_thermal_face[75,33,15] | line.sw2 / A | 75 / 15 | 0.2601816749 | 0.2601816749 | 0.0524236316 |
| 887970 / line_thermal_face[71,26,1] | line.l10 / A | 71 / 1 | 0.2601111531 | 0.2601111531 | 0.0478092591 |
| 992847 / line_thermal_face[82,43,0] | line.l116 / A | 82 / 0 | 0.2599272832 | 0.2599272832 | 0.0425333779 |
| 993242 / line_thermal_face[82,64,0] | line.l52 / A | 82 / 0 | 0.2589845517 | 0.2589845517 | 0.0444198732 |
| 392018 / voltage_upper[19,239] | 83 / 2 | 19 / None | 0.7430917151 | 0.7430917151 | 0.0869387820 |
| 392350 / voltage_upper[19,405] | svr_bus83_regulated / 2 | 19 / None | 0.7394353669 | 0.7394353669 | 0.0867217670 |
| 486983 / voltage_lower[29,197] | 66 / 3 | 29 / None | 0.2446337910 | 0.2446337910 | 0.0689437425 |
| 486977 / voltage_lower[29,194] | 65 / 3 | 29 / None | 0.2424139459 | 0.2424139459 | 0.0689449851 |
| 926327 / line_thermal_face[75,43,15] | line.l116 / A | 75 / 15 | 0.2583783611 | 0.2583783611 | 0.0493858064 |
| 916485 / line_thermal_face[74,26,1] | line.l10 / A | 74 / 1 | 0.2569436334 | 0.2569436334 | 0.0477008861 |

각 critical row의 원래 signed P/Q 기여는 아래와 같다. P는 Pch/Pdis 두 항의 합이며 Q를 별도로 기록한다. fixed constant와 rho는 한 번씩만 계산하고, 정확한 signed 합이 Fraction violation과 같은지 검사했다. 기존 K48 전 행과 신규 행의 MESS별 Pch/Pdis/Q 및 fixed/rho 분해는 `FRACTIONAL_GRID_CONTRIBUTIONS.json`에 보존했다.

| FULL row | MESS01 P / Q | MESS02 P / Q | MESS03 P / Q | MESS04 P / Q |
| --- | --- | --- | --- | --- |
| 927305 | 0.000000 / 0.059964 | -0.009297 / 0.104540 | 0.000000 / 0.101801 | 1.176702e-07 / 0.076226 |
| 926966 | 0.000000 / 0.059948 | -0.009246 / 0.104510 | 0.000000 / 0.101769 | 1.172916e-07 / 0.076206 |
| 1106151 | 0.050503 / 0.020405 | 0.044977 / 0.021364 | 0.050410 / 0.020418 | 0.042725 / 0.017734 |
| 926721 | 0.000000 / 0.052795 | -0.009371 / 0.092992 | 0.000000 / 0.090500 | -1.805882e-07 / 0.067262 |
| 927079 | 0.000000 / 0.054352 | -0.009408 / 0.095620 | 0.000000 / 0.093049 | -1.009923e-07 / 0.069182 |
| 992657 | 0.087034 / -0.001325 | 0.043857 / -0.000348 | 0.000000 / 0.000000 | 0.000000 / 0.000000 |
| 926137 | 0.000000 / 0.026230 | -0.012187 / 0.046995 | 0.000000 / 0.045773 | -3.017285e-07 / 0.033292 |
| 887970 | 0.000000 / 0.000000 | 0.026493 / 0.033476 | 0.000000 / 0.016659 | 0.020951 / 0.013761 |
| 992847 | 0.087017 / -0.001466 | 0.043846 / -0.000422 | 0.000000 / 0.000000 | 0.000000 / 0.000000 |
| 993242 | 0.090718 / -0.003181 | 0.045687 / -0.001303 | 0.000000 / 0.000000 | 0.000000 / 0.000000 |
| 392018 | 0.000000 / 0.000000 | 0.162657 / 0.381628 | -0.005891 / 0.323614 | 0.000000 / 0.000000 |
| 392350 | 0.000000 / 0.000000 | 0.162423 / 0.381222 | -0.005879 / 0.322689 | 0.000000 / 0.000000 |
| 486983 | -0.000841 / -0.001571 | -0.005909 / 0.297321 | -0.002791 / 0.030407 | -0.000780 / -0.001453 |
| 486977 | -0.000841 / -0.001571 | -0.005909 / 0.297324 | -0.002792 / 0.030407 | -0.000780 / -0.001454 |
| 926327 | 0.000000 / 0.026343 | -0.012185 / 0.047183 | 0.000000 / 0.045955 | -2.943077e-07 / 0.033430 |
| 916485 | 0.000000 / 0.011740 | 0.000000 / 0.040910 | 0.000000 / 0.039764 | 0.000000 / 0.001254 |

## 4. 후보 B: SOC–Mode–Travel 유효성과 실제 선택

원본 에너지 식은 `E_next=E+αC−βD−T`다. `C=ΣPch`, `D=ΣPdis`, `T=Σ_depart e_a route_flow_a`이며 travel energy는 depart slot의 `E[t+1]`에 한 번 차감된다. α, β, e는 현재 Source18r 저장 binary64를 정확한 Fraction으로 해석했다. 이상화된 효율을 다시 계산하지 않는다. 원래 SOC Bounds, 96슬롯/97경계, Mode 배타성, STAY 접속, 단일 차량 DAG path와 Compact alias를 독립 검사했다.

`C>0`인 원본 정수점은 충전 STAY를 선택하므로 Mode 배타성으로 `D=0`, 유일 경로로 `T=0`이다. B1 `E≥E_min+βD+T`는 원래 현재 SOC 최소 Bounds가 되고, B2 `E≤E_max−αC`는 `E_next≤E_max`에서 나온다. `C=0`이면 `E_next=E−βD−T≥E_min`이 B1을 주고 B2는 원래 현재 SOC 최대 Bounds가 된다. unused transit Mode가 0이든 1이든 성립하며 새로운 복귀·접속·물리 가정을 사용하지 않는다. 모든 원본 정수점에 대한 이 증명과 단일 U4 수치 replay는 구분한다.

2×4×96=768개 exact 후보의 정수 유효성 독립 감사는 PASS다. 실제 BASE 분수점 위반은 58개이며 최대 32개 한도에서 32개만 선택했다. 선택 Family 분포는 `{'SOC_DISCHARGE_TRAVEL_AVAILABILITY': 32}`다. 이번 실제 위반과 선택은 방전·이동 가용성 B1에만 있다. 충전 저장공간 B2는 정수 유효성은 PASS했지만 BASE에서 실제 위반 0개·선택 0개이므로 B2 행의 Native 효과는 측정하지 않았다. 위반하지 않은 행은 넣지 않고 기존 LP에 함의되는지 전체를 단정하지 않는다. 새 Binary·열·Bounds·Objective 변경은 없다.

선택 행에서 독립 검증한 저장 coefficient와 SOC Bounds의 고유 조합은 다음과 같다. 개별 원본 energy 행/alias 대조는 모든 행에 대해 수행했으며 같은 값을 가정해 생략하지 않았다.

| 정확 α | 정확 β | 원래 E_min | 원래 E_max |
| --- | --- | --- | --- |
| 4278419646001971/18014398509481984 | 4740631186705785/18014398509481984 | 440 | 1080 |

| SOC 추가 행 | 원본 energy Row | BASE 위반(kWh) |
| --- | --- | --- |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,36] | 71912 | 13.95953208 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS01,80] | 43593 | 9.43745976 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,43] | 75615 | 8.54800863 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,37] | 175653 | 6.47066922 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,47] | 180943 | 6.02833886 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,84] | 200516 | 5.31710772 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,50] | 79318 | 4.72605413 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,32] | 121457 | 4.63782737 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,58] | 135211 | 4.12350262 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,43] | 178827 | 4.11904732 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,41] | 177769 | 3.96974118 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,40] | 177240 | 3.63019911 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,49] | 182001 | 3.58857411 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,39] | 176711 | 3.54697084 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,77] | 145262 | 3.53750775 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,81] | 147378 | 3.41299486 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,36] | 123573 | 3.21642755 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,34] | 70854 | 3.18466537 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,44] | 76144 | 3.14230077 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,80] | 146849 | 3.05229340 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,84] | 148965 | 2.86562254 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,76] | 144733 | 2.83755790 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS01,34] | 19259 | 2.72110902 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,34] | 122515 | 2.61425170 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,77] | 93601 | 2.47235802 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS03,47] | 129392 | 2.10623776 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,78] | 197342 | 2.08141453 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS04,65] | 190465 | 1.85635370 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS01,78] | 42535 | 1.67663616 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS01,56] | 30897 | 1.55455714 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS02,54] | 81434 | 1.38064396 |
| SOC_DISCHARGE_TRAVEL_AVAILABILITY[MESS01,48] | 26665 | 1.31666760 |

## 5. 정수 포함관계와 LP 강화의 정확한 관계

원본 FULL 정수 가능영역을 F_int, 저장된 Compact 사영을 T라 한다. BASE는 동일 K48의 Binary만 C로 바꿨으므로 `T(F_int)⊆BASE`다. 원본 실제 Grid 행의 helper/Fraction 소거는 모든 원래 정수점에서 유효하며, SOC 후보도 위 정수 disjunction으로 유효하다. 따라서 `T(F_int)⊆GRID⊆BASE`, `T(F_int)⊆SOC⊆BASE`다. SOC의 정수 유효성을 원래 Full의 모든 연속 LP 점에 대한 함의로 바꾸어 주장하지 않는다. GRID와 SOC는 서로 독립적으로 같은 BASE에 붙이며 둘 사이의 포함관계나 결합 효과는 측정하지 않았다.

추가 행 때문에 정확한 수학적 LP 최소값은 BASE보다 낮아질 수 없다. 다만 numerical ObjVal의 미소 변화와 finite-box 보정 하한의 변화는 정확한 최적값 차이가 아니다. 보정 하한이 조금 낮아져도 포함관계의 위반을 뜻하지 않으며, 작은 Δ를 정확한 LP 최적값 개선으로 승격하지 않는다.

추가 행의 정확 식을 `cᵀy≤R`, Native 계수를 c̃라 하면 유지된 finite Bounds에서 `E=Σmax((c̃−c)l,(c̃−c)u)`, `R̃=ceil_binary64(R+E)`다. `c̃ᵀy≤cᵀy+E≤R̃`이므로 원래 정수 가능해를 배제하지 않는 외향 전달이다. 모든 기존 BASE 행·RHS·Sense·Bounds·열·목적함수를 그대로 보존하고 새 행만 추가했다. 따라서 각 완료 LP의 유효 하한은 원본 정수 FULL 최적값의 하한이다.

| 모델 | Rows | Columns | 원래 Binary / 실제 LP Binary | NNZ | 추가 행 | 독립 Native0 |
| --- | --- | --- | --- | --- | --- | --- |
| BASE | 143308 | 244265 | 9322 / 0 | 1257052 | 0 | PASS |
| GRID | 143324 | 244265 | 9322 / 0 | 1261672 | 16 | PASS |
| SOC | 143340 | 244265 | 9322 / 0 | 1275516 | 32 | PASS |

| 모델 | CSR SHA | Domain SHA | CUTS_EXACT 파일 SHA |
| --- | --- | --- | --- |
| BASE | 9dd79e0f033df5317dc038ac4278f04460d36627b621cbf9834cd9928fab7b45 | 6361580fe551b0e830aee717d54001b52a6ac7f9ea1027b98880659311d5c3f3 | 해당 없음 |
| GRID | 9594a37d190cb0447e2d09400c3902611b8391dbf8566bb8a81632004ec620e0 | bfb8b0bded3f8b0910f910437f127b3dc6fa1e6c5dd619609820d3e980709230 | 862ac2a99c2972885e26dd9122525ce1cddc787a85fa32477f3435c8a6804490 |
| SOC | 8b85296afbad6337545c82de8ae58ae6383a8781546b017b9c10367a959f1167 | 22a03da2a36acead51373e85deacc061c3258825b05e44cbd54db939e6510ad1 | bc6bb9e58478df52cfc68da905bbc0961591d1bc1641fe4eb41dc2d87151569c |

## 6. 완료 LP 결과와 독립 하한 인증

세 모델 모두 Worker=1, Threads=1, TimeLimit=240초, Method=1, FeasibilityTol=OptimalityTol=1e−8을 유지했다. 실제 CSR/RHS/Sense/Bounds/types/objective/ObjCon/ModelSense 및 IsMIP=false를 Native readback으로 대조한다.

| 모델 | Solver Status | Native LP ObjVal | Exact weak-duality LB | BASE 대비 ObjVal Δ | BASE 대비 인증 LB Δ | 재사용 누적 Global LB | 완료 인증 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BASE | 2 | 0.4649848699754816 | 0.4649847749345196 | 기준 | 기준 | 0.4649848699754817 | PASS |
| GRID | 11 | 미확보 | 미확보 | 미확보 | 미확보 | 미확보 | FAIL |
| SOC | 2 | 0.46498486997548155 | 0.4649847989295757 | -5.551115e-17 | 0.0000000239950561 | 0.4649848699754817 | PASS |

Native numerical OPTIMAL은 원시 목적값·Primal/Pi/RC 및 잔차가 수치 계약 안에서 완료됐다는 결과다. **Exact LP optimum이 Primal 목적값과 정확히 같다는 증명은 없다.** 여기서 비교·채택하는 독립 인증 하한은 실제 row multiplier를 sign cone에 맞춘 뒤 저장 binary64의 Fraction으로 `d=c−Aᵀπ`를 계산하고 `L=ObjCon+πᵀb+Σ_j min(d_j l_j,d_j u_j)`로 보정한 값이다. ≤ 행의 π≤0, ≥ 행의 π≥0, equality의 π free를 확인하며 모든 finite variable Bound를 포함한다. 작은 잘못된 Pi 부호는 유효 sign로 보정해 별도 보존한다. 이 weak-duality 증명은 `L≤min(stored native LP)≤min(original integer FULL)`을 준다. 현재 LP 하한은 과거 MIP ObjBound와 인증 범위가 다르고, Native LP ObjVal을 정수 FULL UB로 사용하지 않는다.

| 모델 | 최대 행 잔차 | 최대 Bound 잔차 | RC/stationarity 오차 | row complementarity | bound complementarity | Primal−exact LB |
| --- | --- | --- | --- | --- | --- | --- |
| BASE | 0.000000000036 | 0.000000000000 | 0.000000033921 | 1.148024e-17 | 0.000000033921 | 0.000000095041 |
| GRID | 미확보 | 미확보 | 미확보 | 미확보 | 미확보 | 미확보 |
| SOC | 0.000000000002 | 5.684342e-14 | 0.000000033921 | 9.836090e-17 | 0.000000031339 | 0.000000071046 |

| 모델 | U4 모델 replay 최대 잔차 | Native readback | exact weak-duality 인증 | Exact LP optimum 인증 |
| --- | --- | --- | --- | --- |
| BASE | 1.665335e-15 | PASS | PASS | 미인증(주장하지 않음) |
| GRID | 1.665335e-15 | PASS | FAIL | 미인증(주장하지 않음) |
| SOC | 1.665335e-15 | PASS | PASS | 미인증(주장하지 않음) |

U4는 기존 원본 FULL에서 검증된 상한과 point를 재사용하고 새 모델에서도 수치 replay했다. 이 연구에서 Full MILP나 Actual AC를 새로 실행해 U4를 검증했다는 뜻이 아니다. 새 LP point는 분수점이며 FULL 가능계획·Actual PASS가 아니다.

GRID는 보호 callback의 opaque 실패 신호로 약 34.988초에 INTERRUPTED(11)로 종료했다. `LP_POINT.npz`와 완료 OPTIMAL Primal/Dual을 확보하지 못해 최종 인증은 `LP_NOT_COMPLETED_OPTIMAL`로 거부했다. 로그의 중간 목적값이나 중단된 ObjBound=0을 새 LP 하한·Delta로 사용하지 않는다. Native0의 원본 정수 포함관계와 16개 Cut 유효성은 유지되며, **A의 Native 효과는 미확정, 후속 채택은 보류**다. A를 수학적으로 무효라고 기각하거나 ΔLB=0이라고 기록하지 않는다.

해당 stop receipt의 `b1_conflict_stop=true`는 gate 신호를 기록한 이름이다. 실제 B1 Heavy Native 출현/충돌이나 보호 파일 변경이 증명된 사건은 아니다. 직후 full safety 재검사는 PASS였고 원인은 당시 opaque detector만으로 확정하지 못했다. SOC 전에는 relative path 정규화·조회 중 자연 종료 처리·구조화된 거부 이유 기록을 보완했다. 원본 실패·실행 소스와 로그는 보존했고, 모델·LP 수치 설정은 변경하지 않았다. GRID는 소비한 2번째 Optimize이므로 재실행하지 않았다.

## 7. Runtime·RAM·예산과 사용자 우선순위

최초 요청은 B1 우선이었다. 이후 사용자가 **“B1 돌리지 말라고 했어. 너 작업이 우선이야. 실행할 프로세서 있으면 실행해.”**라고 지시했다. 현재 실행 계약은 이 후속 지시에 따라 B2 Root LP 연구를 우선하며 B1을 새로 시작하지 않는다. 모델·LP 설정·최대 3회/720초 계약과 B1 Source/Ledger/결과 보호는 그대로 유지한다. 알려진 read-only Native0 audit는 CPU/RAM/Commit이 안전하면 공존할 수 있지만, 실제 다른 Heavy Solver·unknown Gurobi·메모리 한계 gate는 유지한다. 원래 B1 우선 gate에 따른 이전 admission 거부를 소급해서 삭제하지 않는다.

| 모델 | Native(초) | Optimize Wall(초) | 모델 추출(초) | Gurobi 생성(초) | Peak RSS(GiB) | Peak Private Commit(GiB) | 최소 RAM Available(GiB) | 최소 Commit Available(GiB) | Gurobi MaxMemUsed(원시 GB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BASE | 86.840000 | 88.180294 | 1.006532 | 0.395401 | 0.5058 | 1.5665 | 15.5985 | 25.2901 | 0.394753 |
| GRID | 34.988000 | 35.832484 | 0.929943 | 0.386048 | 0.5046 | 1.5605 | 15.0422 | 25.1817 | 0.390966 |
| SOC | 100.464000 | 102.337091 | 1.032450 | 0.394611 | 0.5070 | 1.5690 | 15.6161 | 25.6662 | 0.398159 |

Oracle Wall 17.379052초, SOC integer proof 생성 10.041726초, 독립 SOC 정수 유효성 검증 9.406394초. 각 Native Worker의 RSS/Private Commit, 시스템 Available RAM과 Commit Available, Gurobi 보고 메모리는 서로 구분한다. 보고한 Native peak를 모든 검증 프로세스의 전체 peak로 확대하지 않는다. 모델 생성 후 4 GiB RAM·6 GiB Commit reserve와 max(2 GiB, 관측 생성 Private 증가×4)의 추가 여유를 유지했다. 메모리 reserve, 실제 다른 Heavy Solver/unknown Gurobi 또는 보호 파일 drift가 관측되면 B2만 정상 terminate한다. 후속 우선순위 변경 계약에서 구분한 알려진 Native0 audit와 실제 Solver를 구분한다.

| 모델 | 원시 로그 callback 비용(초) | 관측된 보호 gate 실패 | Actual Heavy Native 충돌 확정 |
| --- | --- | --- | --- |
| BASE | 8.72 | 0 | 0건 관측 |
| GRID | 3.77 | 1 | 미확정: opaque stop |
| SOC | 30.82 | 0 | 0건 관측 |

BASE callback 비용은 8.72초, SOC는 30.82초다. SOC 전 detector 보완으로 보호 관측 비용이 달라졌고 외부 자원 조건도 동일 통제하지 않았다. 따라서 Native Runtime 100.464초와 BASE 86.840초의 차이를 SOC 정식화만의 인과적 비용이나 속도 개선으로 해석하지 않는다.

B1의 실제 상태는 `GLOBAL_INTEGRITY_ERROR`이며 date 결과는 `{'FAIL': 2, 'PASS': 1, 'NOT_EXECUTED': 28}`다. 1 PASS·2 FAIL·28 미실행으로 31일 캠페인을 완료했다고 주장하지 않는다. 기존 global integrity error guard가 새 dispatch 전에 반환하는 상태에서 B1 Native Worker/Supervisor 부재와 자원 안전을 실제 확인했다. 본 B2 연구는 B1 PR212 Source·Worker·Ledger·원본 FAIL/PASS·예약·프로세스를 변경하지 않았다. 후속 관측의 B1 예약 Disabled는 이후 별도로 사용자가 승인한 중단 상태이며 이 연구가 변경한 상태가 아니다. 원래 예약 Actions, Source, Ledger 및 원본 FAIL/PASS는 보존했다.

| 모델 | 보호 gate 실패 관측 | B1 보호 변경 | 보호 gate 위반 시 B2 정상 종료 | guard stop flag | RAM stop |
| --- | --- | --- | --- | --- | --- |
| BASE | 0 | 0 | PASS | False | False |
| GRID | 1 | 0 | PASS | True | False |
| SOC | 0 | 0 | PASS | False | False |

BASE/SOC에서 실제 Heavy Solver 충돌은 0건 관측됐고 GRID에는 원인이 미확정인 보호 gate 실패 1건이 있다. 실제 B1 Heavy Native 충돌을 확정한 증거는 없으며 opaque 실패를 충돌 확정으로 바꾸지 않는다. `RESOURCE_GATE_TESTS.json` PASS: B1 Worker/Supervisor 출현, 보호 SHA drift, unknown process scan 오류, RAM/Commit 한계 위반의 거부를 검증했다. 테스트는 함수 대체와 읽기 전용 관측이며 실제 B1 파일/프로세스/예약을 바꾸지 않았다.

GRID 최초 admission은 B1 Gurobi module을 로드한 pricing qualification audit 때문에 거부됐고, 다음 admission은 약 1.65 GiB private commit의 B1 history model audit 때문에 거부됐다. 둘 다 `Native_optimize_started=false`이며 실제 Optimize 0회, 예산/latch를 소비하지 않았다. 실패 영수증은 `NATIVE_FAILURE_FIRST_ADMISSION_REJECTED.json`과 `NATIVE_FAILURE_SECOND_ADMISSION_REJECTED.json`에 보존했다. 첫 거부 뒤에는 실제 해당 audit 종료와 fresh 안전 확인을 기다렸다. 후속 사용자 우선순위 지시 뒤에는 알려진 Native0 audit 공존만 명시적으로 허용하고 실제 Heavy Solver·unknown Gurobi 및 RAM/Commit gate를 유지했다. 이 admission 거부와 실행 중 Heavy Solver 충돌은 구분한다. B1 캠페인을 새로 실행하지 않았다.

## 8. 역사적 강화 실험과 이번 범위

역사적 감사 PASS: 7개 PR의 pinned HEAD와 14개 원문 코드/증명 Git blob SHA를 보존했다. `HISTORICAL_STRENGTHENING_AUDIT_KO.md`에 수학식·실패 범위·Source 차이를 정리했다.

| PR | 조사 계열 | 이번 실험과의 관계 |
| --- | --- | --- |
| 109 | connection-aware Mode hull + arc-energy mass EF | unused transit mode canonicalization은 원본 bit assignment를 제거할 수 있어 재사용하지 않음 |
| 137 | aggregate C/D/connected power, DP SOC envelope, SOC-flow EF | 동일 단순 Mode cut 재제출 없음; B는 원래 SOC 경계에 C/D/T를 직접 결합한 작은 사영 |
| 167 | connected power + folded PCS local hull | 예전 single-slot 상태 증명은 이미 SOC/Mode/Travel 논리를 포함; 새로운 물리 정리라고 주장하지 않음 |
| 169 | 4-slot joint route/mode/PQ/SOC hull | B는 기존 국소 joint hull 논리와 관련된 명시적 작은 행; window EF를 다시 구현하지 않음 |
| 185 | per-arc departure/arrival SOC reachability | 현재 B의 aggregate D+T와 charge headroom은 행 형태가 다르지만 기존 물리 사실을 재검증 |
| 186 | May12 A-stage Phase-I/P1 exact recovery | M-stage Mode/PCS/Reachability 실패 후보가 아님 |
| 187 | 651개 Route–SOC 행 LP 단일 검증 | raw ObjVal 미소 증가가 독립 인증 개선은 아니었음; 현재도 exact finite-box 하한을 따로 계산 |

A는 원본 Grid 행 자체가 새롭지 않다. PR211의 정수 incumbent 대신 현재 완료·인증된 실제 BASE 분수점에서 원래 Grid 위반과 sensitivity를 조사한 실험 축이다. B는 최초의 SOC–Mode–Travel 정리라고 주장하지 않고 현재 K48에 없는 작고 명시적인 정수 유효 행을 실제 Root 분수점에서 검증한 후보다. 과거 결과를 현재 Source18r 성과로 재사용하지 않는다.

## 9. 채택·기각 및 실제 미완료 사항

| 후보 | 완료 인증 | BASE 대비 인증 ΔLB | 하한 개선≥0.001 | 후속 MIP 후보 판단 |
| --- | --- | --- | --- | --- |
| GRID | FAIL | 미확보 | 미확보 | 완료 인증 실패: 효과 미확정 |
| SOC | PASS | 0.0000000239950561 | FAIL | 기각: 완료·인증 개선 기준 미달 |

계산시간 또는 메모리 감소만으로 채택하지 않는다. 이 경로에는 유의미한 자원 개선과 LP/정수 동등성의 독립 증명이 필요하다. 새 행이 BASE의 수치 분수점을 배제했고 단지 같은 LP 목적값이 관측됐다는 사실은 LP 가능영역 동등성 증명이 아니다. 세 모델 각각의 실제 완료 결과를 비교하며 Native0 행 수·분수 개수·위반 개수만으로 효과를 주장하지 않는다.

SOC의 현재 완료 Native 목적값 변화는 -5.551115e-17, exact weak-duality 하한 변화는 0.0000000239950561다. 두 Native 목적값은 사실상 같고 약 2.4e−8의 보정 하한 차이는 dual correction 손실 차이다. Global 강화나 정확한 LP 최적값 상승으로 주장하지 않는다. SOC는 0.001 기준 미달로 후속 MIP 후보에서 **기각**한다. GRID는 완료·인증된 효과를 확보하지 못해 **보류**한다. 두 후보를 합쳐서 실행하거나 새로운 물리 가정을 도입하지 않았다.

SOC 종료점의 Native0 재검사에서는 선택하지 않은 방전·이동 B1 행 41개가 여전히 위반되고 최대 위반은 7.35333196 kWh다. 선택 32행의 최대 Fraction 잔차는 6.607474e-14로 수치 허용오차 안이며 충전 저장공간 B2의 실제 위반은 0개다. 이 결과는 이번 32행 강화 뒤에도 원래 정수 운전과 다른 분수 상태가 남는다는 진단이다. 남은 41행을 추가하면 하한이 개선된다는 근거는 아니며 추가 Cut·Native 실행을 하지 않았다. 이번 기각은 시험한 SOC 32행의 Material 성과에 대한 판단이며 전체 768행이나 모든 joint hull의 효과를 판정하지 않는다.

현재 인증된 비교 효과는 BASE 대비 SOC의 개별 효과이며 GRID 효과는 미확정이다. 결합 효과·Full MIP B&B 개선·Production 효율·3% Global Gap 달성·원본 FULL integer optimum·Actual OpenDSS PASS는 미검증이다. 이번 승인된 최대 3회 LP 연구에서 종료하고 Native retry·모델 추가 확대·Production 통합을 하지 않는다.

## 10. Source·B1 보존 및 증거

| 보존 항목 | 실행 전 감사 | 실행 후 감사 |
| --- | --- | --- |
| PR207/209/210 HEAD clean | PASS | PASS |
| PR211 정확한 HEAD clean | PASS | PASS |
| May 기존 HOLD marker 동일 | PASS | PASS |
| 기존 Supervisor/Monitor 두 예약 Disabled | PASS | PASS |
| 현재 PR212 자동화 PAUSED 및 frozen | PASS | PASS |
| B1 실제 실행 종료 및 error guard quiescent | PASS | PASS |

PR212의 이전 승인된 B1-only 자동화 prompt가 과거 PR209 prompt와 달라졌다는 사실은 `historical_PR209_automation_check`에 그대로 보존했다. 이번 연구는 현재 B1 보호 baseline의 PAUSED bytes를 유지하며 prompt·예약·프로세스를 변경하지 않는다. Source18r·U4·PR207/209/210/211·B1 PR212, StageBudget, NativeStopRequested, A1/A2/M-stage 예산 및 Planning/Actual 코드는 수정하지 않았다.

보존 산출물: 원문 요청·TASK_CONTRACT, source/history SHA, 각 LP_A/DATA/AXES/ORIGINAL_BINARY, 실제 x/Pi/RC, Native0/독립 Native0, exact Cut packet, source Full Row SHA, U4 replay, Native readback, resource/B1 preflight, B1/memory trace, native log, durable started latch, 단계별 RESULT/독립 최종 인증, 전체 NATIVE_LEDGER, 전후 source/B1 audit 및 FINAL_RESULT. 새 Draft PR은 PR211 연구 브랜치를 Base로 하고 기존 Source나 과거 증거를 덮어쓰지 않는다.

최종 의사결정 영수증:

```json
{
  "PASS": true,
  "classification": "ROOT_LP_SOC_NONMATERIAL_GRID_UNCERTIFIED",
  "base_PR211": "d12315a3757aec187c8da0685c28ef901466386a",
  "Source18r": "497609b46faa14ea7e32a9483a333ab32fd264ef",
  "Global_LB": 0.46498486997548166,
  "PR211_Global_LB": 0.46498486997548166,
  "UB": 0.6760534504652341,
  "global_gap": 0.31220694213527517,
  "Global_Gap_percent": 31.22069421352752,
  "Global_LB_improved": false,
  "stages": [
    {
      "kind": "BASE",
      "model_dimensions": {
        "rows": 143308,
        "columns": 244265,
        "binary": 0,
        "nnz": 1257052
      },
      "Native_status": 2,
      "Native_Runtime": 86.83999991416931,
      "optimize_wall_seconds": 88.18029440008104,
      "LP_ObjVal": 0.4649848699754816,
      "LP_lower_bound": 0.4649847749345196,
      "certificate_PASS": true,
      "certificate_sha256": "a9680e5629213e1e13f1cd83f742780049204804f0bc0d1110258e21ac669d96",
      "Delta_LP_objective": null,
      "Delta_LP_lower_bound": null,
      "decision": "BASE_REFERENCE",
      "original_integer_projection_preserved": true
    },
    {
      "kind": "GRID",
      "model_dimensions": {
        "rows": 143324,
        "columns": 244265,
        "binary": 0,
        "nnz": 1261672
      },
      "Native_status": 11,
      "Native_Runtime": 34.98800015449524,
      "optimize_wall_seconds": 35.83248390001245,
      "LP_ObjVal": null,
      "LP_lower_bound": null,
      "certificate_PASS": false,
      "certificate_sha256": "bb92b70f349ee82d0aa74aeec7eb2f5b57ae60967dcc283dbacc38be79810577",
      "Delta_LP_objective": null,
      "Delta_LP_lower_bound": null,
      "decision": "GRID_EFFECT_UNCERTIFIED_ADOPTION_DEFERRED",
      "original_integer_projection_preserved": true
    },
    {
      "kind": "SOC",
      "model_dimensions": {
        "rows": 143340,
        "columns": 244265,
        "binary": 0,
        "nnz": 1275516
      },
      "Native_status": 2,
      "Native_Runtime": 100.46399998664856,
      "optimize_wall_seconds": 102.33709050004836,
      "LP_ObjVal": 0.46498486997548155,
      "LP_lower_bound": 0.4649847989295757,
      "certificate_PASS": true,
      "certificate_sha256": "d5a1bf54b7f106db9525c25c9dc6e9730422a6ff4b86cb68f54ee0da4b5ee42e",
      "Delta_LP_objective": -5.551115123125783e-17,
      "Delta_LP_lower_bound": 2.3995056108727653e-08,
      "decision": "REJECT_SOC_NONMATERIAL",
      "original_integer_projection_preserved": true
    }
  ],
  "adopted_candidates": [],
  "SOC_decision": "REJECT_NONMATERIAL",
  "GRID_decision": "EFFECT_UNCERTIFIED_ADOPTION_DEFERRED",
  "combined_candidate_decision": "NO_COMBINED_EXPERIMENT_OR_ADOPTION",
  "Native_calls": 3,
  "requested_Native_seconds": 720,
  "actual_Native_Runtime": 222.2920000553131,
  "optimize_wall_seconds": 226.34986880014185,
  "peak_process_RSS_bytes": 544415744,
  "peak_private_commit_bytes": 1684721664,
  "minimum_RAM_available": 16151392256,
  "minimum_commit_available": 27038646272,
  "source_integer_binary_count": 9322,
  "LP_binary_count": 0,
  "additional_binary_count": 0,
  "full_MILP_calls": 0,
  "campaign_calls": 0,
  "IEEE8500_calls": 0,
  "B1_Native_launches_by_this_task": 0,
  "GRID_consumed_call_not_restarted": true,
  "extra_Native_calls": 0,
  "production_integration": false,
  "original_source_ledger_results_mutations_by_this_task": 0,
  "B2_priority_override_sha256": "8a022499f2672383d697e150c6bb4d21857a4111ce3742f3ced6f3217442094b",
  "numerical_OPTIMAL_is_exact_LP_optimum_claim": false,
  "exact_weak_duality_certificates": [
    "BASE",
    "SOC"
  ],
  "legacy_GRID_guard_trigger_not_actual_collision_proof": true,
  "scope": "SOC preserved all original integer points and cut the validated BASE point, but did not improve the numerical LP optimum. Its tiny corrected dual-bound gain is certificate quality, not material formulation improvement. GRID has valid cuts but no completed candidate LP, so its effect remains unmeasured. No fourth call or automatic budget reset."
}
```
