# M1 gap 원인 귀속 최종 검토

초기 검증된 차이 0.1007043235258543 중 **0.0354383204959648 (35.1905%)**를 더 좋은 원래 정수 해로 줄였다. 원래 incumbent의 384개 charge_mode가 전부0이어서 Pch=0이고, 초기/종료SOC가 같으므로 비음수 방전·이동 에너지도0이다. 기존 해는 정적 무효전력 운용만 수행했다. 새 해는 mode14개와 node_activity10개를 바꾸어 유효한 충·방전과 이동을 사용한다. 고정 trajectory 연속 재최적화로는 의미 있는 개선이 없었다.

관측 개선 축은 **UB_DOMINATED**, 전체 원인에 대한 primary 분류는 **GAP_PARTIALLY_ATTRIBUTED**다. 개선된 부분은 poor incumbent에서 왔다는 증거가 있지만 남은 0.0652660030298895의 주원인을 확정하지 못했다. 새 UB도 전역 최적성 증명이 아니다. 이 부분을 전체 gap의 poor-UB dominance로 확대하지 않는다.

PR167의 원래 B9,322개 중 fractional7,454개(약79.96%), node_activity7,070개 및 charge_mode384/384 fractional, 광범위한 위치·route 분할과 MOVE/STAY 혼합 결과를 그대로 보존한다. 입증된 한 슬롯 cut320개/추가nnz17,837의 certified ΔLB0 및 `ROOT_GAP_NOT_EXPLAINED_BY_TESTED_LOCAL_HULLS` 음성 결과도 유지한다. 같은 cut loop를 반복하지 않았다.

새 두block LP는 원래/augmented rows strict replay를 통과했다. 그러나 원래 B 기준 node_activity6,585개 및 charge_mode327개가 같은1e−6 지표에서 fractional이고, 원래 integrality 최대위반0.4546563811314338이다. 이 LP 점을 원래 production UB로 승격하지 않았다. fractionality 수는 점과 solver algorithm에 의존하는 관측이며, 그 자체는 gap 기여 인증이 아니다.

| 검증된 값 | 결과 |
|---|---:|
| 초기 UB | 0.6694159238756877 |
| 초기 LB | 0.5687116003498334 |
| 초기 gap `(UB-LB)/UB` | 15.043610% |
| 최선 원래 feasible UB | 0.6339776033797229 |
| 최선 valid global LB | 0.5687116003498334 |
| 최종 gap | 10.294686% |
| 구조 강화 valid LB 증가 | 0.0000000000000000 |
| 모든 진단의 최대 valid LB 증가 | 0.0000000000000000 |
| 기존 UB 유지시 필요한 LB 증가 | 0.0973572439064759 |
| 필요한 증가 회복률 | 0.00000000% |

## 요청한 33개 질문에 대한 답변

1. **Exact base commit:** PR167 `0d423626790a1102d42e6ba84beeb5f7d4ab1d4b`. scientific authority는 PR162 `1d922c91eb27056a5ccc79c92ef18146707099ab` selected exact C3A다.
2. **시작 valid UB:** 0.6694159238756877.
3. **시작 valid LB:** 0.5687116003498334. 기존 native global bound provenance를 보존했다.
4. **시작 gap:** 15.043610%, 차이 0.1007043235258543.
5. **UB 독립 feasibility:** PASS. 전체 C3A rows/bounds/integrality와 저장 inverse를 통한 원래 route/movement/SOC/PQ/PCS/grid/A1 frozen interface를 검사했다. 원래 행·모델·start SHA는 BASE_IDENTITY/UB_VALIDATION에 있다.
6. **고정 discrete 연속 재최적화:** valid UB 0.6694159238674191, 개선 8.269e-12. numeric-scale로 의미 없는 개선이다. Runtime 0.679999828s. 제한 모델의 native ObjBound는 전역 LB로 사용하지 않았다.
7. **local neighborhood:** 개선됐다. 64..84의 모든 unit node/mode B 중 Hamming≤24, 나머지 B 고정, Threads1/TimeLimit300 사전등록. Runtime 112.529999971s, 원래 all-integer strict replay 및 전체 physical replay PASS. neighborhood ObjBound 0.6308160530113509는 global LB가 아니다.
8. **최선 valid UB:** 0.6339776033797229. reference 대비 0.0354383204959648 개선. 전역 최적성은 주장하지 않는다.
9. **MESS04 69–72 LP projection이 hull 안인가:** NO. 슬롯71 exact rational separator의 양의 위반을 독립 검사했다. native membership INFEASIBLE만을 근거로 하지 않았다.
10. **불가능한 물리 조합:** 각 위치 Pch/Pdis/Q를 실현하는 데 필요한 방전 mode 질량 합0.7945999363442287이 단일 unit의 가용 질량0.49639784456147973을 초과한다. 동일 mode의 위치별 PCS half-polytope를 함께 만족하지 못한다. SOC temporal impossibility나 72 방전의 도달 불가능성은 입증되지 않았다. 목적함수 계수가0인 mode71만0.5036021554385203→0.20540005838815423으로 바꾸면 그 separator가 사라지고 모든 P/Q/route/SOC 및 목적값은 bit-identical이다. 이는 전체4-slot hull membership 증명은 아니다.
11. **Exact hull 크기:** 한 block 추가 rows3,479,007/private cols1,400,080/nnz11,664,103. C3A+한block rows4,061,815/cols1,706,120/nnz17,015,715. 두block rows7,540,822/cols3,106,200/nnz28,679,818. 실제 source PCS16/efficiency/movement coefficients를 사용했다.
12. **정수 궤적 수:** mobility paths149,817 × 16 mode words =2,397,072. transit의 독립 mode cube factoring 후 disjunction232,837. SOC/PQ는 원래 연속 집합이다. 관측 SOC에 고정하지 않았으며 boundary SOC69/SOC73은[440,1080] 자유 interface다. 전체96-slot global extendability hull은 아니다.
13. **정확한 separator:** `Σ_site support_site(Pch,Pdis,Q,stay)+charge_mode[MESS04,71]≤1`. 각 support는 원래 half-PCS row의 비음수 유리수 조합이며 소거 계수 합은 u:-1,qD:0. 정확한 모든 항·원래면·multipliers는 MESS04_69_72_SEPARATION.json. 위반0.2982020917827489. 독립 verifier가 원래 모든 half-polygon vertices와 계수·mutation을 검사했다. 전체 EF는 별도 독립 모든-row verifier PASS.
14. **단일 hull 뒤 valid LB:** 0.5687116003498334. 독립 finite box 인증0.558165053005941 및 원래 homogeneous domain을 사용한 solver-free 인증0.5581653526317286 모두 기존 LB보다 약하다.
15. **단일 창 ΔLB:** 0.0000000000000000. approximate primal0.5687610859560673을 LB로 승격하지 않았다.
16. **필요 LB 증가 회복률:** 단일 창0%; 전체 관측 0.00000000%. 분모는 기존 UB 유지시0.097357243906476이며 새로운 UB의 목표와 혼합하지 않았다.
17. **substitution:** 새 approximate point에서 같은 grid row의 MESS04 효과를 다른 unit들이 보상하는9개 관측이 있다. MESS03 슬롯71 defect0.2934331526359996이 가장 커서 선택했다. 단일 point RAW FAIL이므로 엄격 feasible post-hull optimum의 대체라고 증명한 것은 아니다.
18. **multiwindow generalization:** 이 관측에 따라 허용된 한 번, MESS04+MESS03의69–72 두block만 실행했다. 최대4block 이내. 같은 exact joint hull이며 반복 one-slot cut 전략을 사용하지 않았다.
19. **multiwindow valid LB:** 0.5687116003498334, ΔLB 0.0000000000000000. ObjVal 0.5687116103495242, 실제 native ObjBound 0.5687116103495242, exact box certificate 0.5687115940354054, homogeneous domain certificate 0.5687115940355527. Runtime 3823.582000017166s/Work 4613.02788953634. RAW 결과는 아래 표와 원본 JSON에 보존한다.
20. **cross-MESS/grid coupling 유의성:** 실제72 동시 active branch는 sw1A+l3A이며 l10A는71/79에서 relevant하다. 두branch 모든 retained16faces/actual C3A binding closure/4units×24sites×2modes의 작은 exact local injection master를 검사했다. convex certificate 0.4434651896706711, local integer feasible objective 0.4436632449116690. local integrality gap의 상한 0.0001980552409979<0.001. MIPGap0.005에서 얻은 feasible integer objective를 정확한 최적값으로 부르지 않는다. 이 특정 one-time coupling은 작으나 전체 horizon/다른 grid coupling은 배제되지 않았다.
21. **긴 horizon 진단:** 단일4-slot 인증 증가0과 다음 active75–76으로 이어지는 SOC/mobility 영향을 근거로 한 번만69–76,8슬롯 선택적 정수화했다. full8-slot hull은 아니다. 8슬롯은 root crossover 도중 time limit으로 끝났으며 native bound0.3955868065146082는 baseline보다 약하다. 따라서 장기 reachability의 실제 bound 효과는 미확정이다.
22. **처음 material 강화가 생기는 horizon:** 이번 테스트에서 발견되지 않았다.8슬롯 root 미완료와4슬롯 bounded search 때문에 모든 장기 원인을 배제할 수 없다.
23. **선택적 정수화 결과:** coupling master를 포함해 정확히3회. original4-slot100B와8-slot200B를 각각300초/Threads1로 지정했다. 아래 실제 Runtime/status/bound를 보고하며 partial point를 production UB로 승격하지 않았다. material ΔLB≥0.001은 관측하지 못했다.
24. **다기간 궤적 약함에 귀속된 양:** 검증된 structural recovery 0.0000000000000000. 위반 존재와 global gap 기여는 구별한다. 첫 hull의 수치 실패와 bounded diagnostics 때문에 다기간 약함의 실제 기여를0이라고 증명한 것은 아니다.
25. **poor UB에 귀속된 양:** 최소 0.0354383204959648, 초기 검증 차이의 35.1905%. 개선된 원래 feasible point가 그만큼 기존 incumbent의 excess를 증명한다. mode14/node10 변경의 개별 기여를 분해한 실험은 하지 않았다.
26. **주원인:** 관측 개선은 UB 축이 우세하나 전체 gap의 dominant cause는 미확정이다. 원래 incumbent 선택의 명확한 약점, 국소 mode/위치/PQ defect, 수치 인증 한계가 함께 관측됐다. 숫자만으로 multi-period/cross/long-horizon/numerical dominance를 주장하지 않는다.
27. **모든 정수 schedule에 exact/valid한가:** YES, source 계수에 대한 local hull/분리 부등식은 모든 원래 global integer schedule의 projection을 보존한다. exactness는 자유 경계 local physical set에 관한 것이며 global96-slot hull 주장과 다르다. coupling master는 약한 전역 relaxation, primal neighborhood는 의도된 검색 제한이다.
28. **물리 변경:** NO. MESS수/route/time/energy/PQ/PCS/SOC/효율/초기·최종/A1/voltage/rating/P1/P2를 변경하지 않았다. EF 추가와 attribution용 integrality relaxation만 사용했다. 원래 모델 SHA 및 이전 namespace 해시 unchanged.
29. **full B&B:** NO. 새로운3600초/2시간 fullMILP/Benders/DW/B&P/tournament 없음. 허용된 제한 neighborhood1회와 selective3회 외 정수 solve 없음.
30. **다음 해결 방식:** improved primal search를 우선 권고한다. 정확히 하나의 다음 실험은 새 valid incumbent에서 같은64..84 블록/Hamming radius48/300초/Threads1, 설정·물리 유지다. 기존radius24가 포화됐고 valid UB 개선 증거가 있다. **이 실험은 실행하지 않았다.** compact/global trajectory/B&P를 채택할 dominance 증거는 아직 부족하다. static design만 TRAJECTORY_FORMULATION_DESIGN.md에 있다.
31. **최종 분류:** primary **GAP_PARTIALLY_ATTRIBUTED** 하나. LB/UB 관측 개선 축 **UB_DOMINATED**. 전체 원인 확정과 같은 의미가 아니다.
32. **최종 commit SHA:** 이 보고서와 manifest를 포함한 최종 PR HEAD. 자체 commit SHA를 그 commit 안에 쓰는 순환을 피하며 정확한 값은 PR body 및 최종 응답에 별도로 기록한다.
33. **Draft PR:** https://github.com/BeaverVillage/MobileESS/pull/169.

## 수치·capture 제한

| 점 | strict original C3A | strict augmented | valid LB 권위 |
|---|---|---|---|
| PR167 pureLP | FAIL2.805600374244932e-8 | 해당 없음 | 기존 native global LB 보존 |
| MESS04 단일 창 | FAIL2.3785754346083987e-5 | FAIL0.01889765176353009 | exact certificate0.558165053005941, carry LB_ref |
| multiwindow | {'PASS': True, 'finite': True, 'max_constraint_violation': 7.488010211886831e-11, 'max_bound_violation': 0.0, 'max_integrality_violation': None, 'objective': 0.5687116103495242} | {'PASS': True, 'finite': True, 'max_constraint_violation': 7.488010211886831e-11, 'max_bound_violation': 0.0, 'max_integrality_violation': None, 'objective': 0.5687116103495242} | 두 exact certificate와 기존 LB 최대값 |

단일 창은 native optimize를 정확히 한 번 끝낸 후 제 postprocessing 코드의 types 누락으로 receipt 작성이 실패했다. primal과 dual/RC/slack은 이미 저장됐으며 읽기 전용으로 회수했다. native API ObjBound와 정확한 API Runtime/Work는 손실됐고, Runtime826.38/Work1200.23은 완료 로그의 **소수2자리 값**이다. barrier 마지막 dual 열을 ObjBound로 추정하지 않았다. 재solve하지 않았으며 실패 코드/로그를 failed_capture_provenance에 보존했다. 이 capture 항목은 미완전이며 all-PASS로 숨기지 않는다.

두block의 새 LP에서는 이 correctness issue 때문에 Crossover0→1만 변경했고 tolerance1e-8은 그대로다. native OPTIMAL은 설정 tolerance를 기준으로 한 종료이며 strict raw PASS와 같지 않다. [Gurobi status 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/statuscodes.html), [ObjBound 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound).

| 선택적 진단 | Status | native Runtime(s) | native ObjBound | valid global LB |
|---|---:|---:|---:|---:|
| SELECTIVE_MESS04_69_72 | 9 | 300.2149999141693 | 0.5687116103498294 | 0.5687116003498334 |
| SELECTIVE_MESS04_69_76 | 9 | 300.2430000305176 | 0.3955868065146082 | 0.5687116003498334 |
| CROSS_MASTER_INTEGER | 2 | 0.032000064849853516 | 0.44346518968518533 | 0.5687116003498334 |

각 native TimeLimit은300이며 종료 정리로 Runtime이 limit을 초과하면 실제 값을 그대로 보존한다. 실행 중인 다른 A-stage worker는 종료하거나 수정하지 않았다. concurrency snapshot을 저장했으며 겹친 Runtime을 통제 성능 비교로 사용하지 않는다.

## 저장 LP의 실제 물리·grid 수치

다음 값은 저장된 approximate LP의 물리 좌표이며 valid UB/LB가 아니다. 단순 row 기여와 counterfactual gap 귀속을 구별한다.

| 슬롯 | SOC 전→후(kWh) | Pch(kW) | Pdis(kW) | Q(kVAr) | 가중 이동에너지(kWh) |
|---|---|---:|---:|---:|---:|
| 69 | 1053.814539148→1033.811182926 | 0.767412989 | 73.946193853 | 12.389424347 | 0.726092006231 |
| 70 | 1033.811182926→1002.836354519 | 0.000000136 | 117.704347981 | 33.170922120 | 0.000000000000 |
| 71 | 1002.836354519→982.688521395 | 22.977842106 | 97.299268297 | 235.642369142 | 0.000000000000 |
| 72 | 982.688521395→948.696373911 | 0.000000176 | 129.170160522 | 31.059420176 | 0.000000000000 |

69 출발 route 질량은 IDC12→IDC01 0.13388158283044294(원래에너지3.1203025798640622), IDC12→STA02 0.05229735420371386(3.090518352649966), STA12→IDC03 0.07149082674352064(2.05222168563522)다. 원래arrival70/connect71을 유지한다. 슬롯71의 주요 stay/location 질량은 다음과 같다. 모든 작은 질량과 exact separator 항은 원본 JSON에 남긴다.

| site | stay 질량 | Pch | Pdis | Q | 필요한 방전mode 질량 |
|---|---:|---:|---:|---:|---:|
| IDC01 | 0.205400052680 | 22.977841999 | 0.000000004 | 77.702879362 | 0.000000000025 |
| IDC02 | 0.151061490884 | 0.000000004 | 21.695167642 | 55.159976669 | 0.151061490883 |
| IDC03 | 0.071490830095 | 0.000000004 | 5.578867687 | 28.046861510 | 0.071490830068 |
| IDC08 | 0.090050113488 | 0.000000004 | 7.027162297 | 35.327930305 | 0.090050113457 |
| IDC09 | 0.157472436708 | 0.000000004 | 12.288539416 | 61.778659170 | 0.157472436661 |
| STA02 | 0.134230765687 | 0.000000004 | 23.630748257 | 47.211271899 | 0.134230765618 |
| STA12 | 0.190288520816 | 0.000000005 | 27.078328033 | -69.587475742 | 0.190288519909 |

MESS04의 t72 sw1A 대표 active face 기여는 Pdis −0.0246705821384319, Q +0.0005768856148293971, Pch +3.298340163974514e−11, 합 −0.024093696490619102이다. 모든 unit과 frozen grid 항을 합친 required rho는0.568711942987684다. 이 기여 자체는 hull 밖 행동의 causal advantage가 아니다. mode-only 대조는 이 P/Q 기여를 전혀 바꾸지 않고 separator를 제거한다. l10A의71/79와 l3A의72를 포함한 실제 동시 active faces 및 새 approximate 점의 보상은 CRITICAL_GRID_COUPLING_AUDIT.csv / MESS04_GRID_EFFECT.json에 보존했다.

`GAP_ATTRIBUTION.csv`는 valid 회복만 집계한다. `VERIFICATION.json`은 proof/hash/workflow와 strict raw 수치/capture 결과를 분리한다. `SHA256_MANIFEST.json`은 자신과 Python cache 및 lossless 분할로 대체한 local ZIP을 제외한 파일을 봉인한다. optimize 포함 코드는 ONCE 토큰을 삭제하거나 재실행하지 않는다.
