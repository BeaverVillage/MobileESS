# V42 M1 Fast Certified Primal–Dual Hybrid 결과

판정: **CERTIFIED_5_PERCENT_WITHIN_90_MINUTES**. 동일 May01/1,499-job 원본 문제에서 strict integer UB와 독립 exact Global LB를 별도 검증했다. P2 certificate가 없으므로 **M1_ACCEPTED=false**이며 production backend를 변경하지 않았다.

| 지표 | 이전 완료 연구 | 이번 검증 결과 |
|---|---:|---:|
| Strict integer UB | 0.6063186498423855 | 0.5949967486929637 |
| Fresh exact Global LB | 0.5675886811427069 | 0.5686444703080522 |
| Certified Global Gap | 6.3877251194% | 4.4289785520% |
| UB 개선폭 | — | 0.0113219011494218 |
| LB 개선폭 | — | 0.0010557891653454 |
| 검증 포함 Wall | 79.71분 | 20.109분 |

5% Gap과 90분 동시 달성: **True**. 5% Gap과 60분 동시 달성: **True**. 과거와 다른 유한 파일럿의 실제 시간을 비교한 것이며 일반적인 Solver speedup을 주장하지 않는다. 이전 Native LB 0.5687116104는 fresh exact LB로 재분류하지 않았다.

## 기준 및 정확한 목표

기준 완료 HEAD `6122331841e22562d23eb054c4168b5130566f3f`, Run ID `hybrid_may01_20261008_5pct_pilot01`, scientific case SHA `cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a`. D 드라이브 독립 clone `D:\MobileESS_v42`에서만 개발·검증했다. A1/A2 목표 0.5%는 보존하고 M1/M2 연구 목표만 5%로 설정했다. 이전 historical ledgers·원본 데이터·PR189 및 A1 P1-only 인터페이스는 보존했다.

기존 UB에서 필요한 LB는 **0.5760027173502662**, 기존 LB에서 필요한 UB는 **0.597461769623902**이다. 임계값과 최종 Gap은 binary64 입력을 exact rational로 해석하여 독립 계산했다. 정확한 최종 UB `41869173995317/70368744177664`와 LB `2157593600007090506212008624915956538114167372545848383663881393915962103305378061/3794275180128377091639574036764685364535950857523710002444946112771297432041422848`는 [독립 검증 JSON](INDEPENDENT_FINAL_VERIFICATION.json)에서 확인할 수 있다.

## UB 후보 비교

A는 기존 U2 baseline, B는 실제 grid 행 계수와 주입 부호를 사용하는 임계 선로·시간 민감도, C는 4대 역할 교환과 선택적 이동·재배치다. 세 후보는 동일 strict U2 RAW와 각 400초 제한으로 시작했다. 전체 원본 행·continuous box·binary type을 유지하고 UB 탐색에만 neighborhood를 제한했다. 모든 candidate를 원본 FULL 정수 literal 0/1, full matrix, 경로·SOC·P/Q·PCS·계통 replay로 검사했으며 실패 RAW는 repair/rounding 없이 거부했다. 최선 UB보다 나쁜 후보는 승격하지 않았다.

| 방법 | 검증된 UB | UB 개선폭 | Native 초 | Work | 거부 RAW 수 |
|---|---:|---:|---:|---:|---:|
| A | 0.6056492196962 | 0.0006694301462 | 64.07 | 140.7056 | 2 |
| B | 0.6063186498424 | 0.0000000000000 | 3.29 | 4.5745 | 0 |
| C | 0.5949967486930 | 0.0113219011494 | 400.13 | 946.2671 | 3 |

후보별 실제 signed line/time selection 근거, 경로 연결시각과 원본 time-dependent table 보존은 `artifacts/UB/*_NEIGHBORHOOD_IDENTITY.json`에 있다. [동일 seed 비교 CSV](artifacts/UB/UB_METHOD_COMPARISON.csv)와 [단조 incumbent pool](artifacts/UB/UB_INCUMBENT_POOL.json)이 admission 근거다. Native restricted ObjBound는 Global LB로 사용하지 않았다. 후보 처리·검증 시간은 Native 외 비용이며 UB 개선 속도는 각 실제 Native Runtime과 개선폭을 함께 제시한다.

## 차량별 전체 trajectory Pricing

원본 582,808행·306,040열·5,351,612 nonzero의 C3A를 4개의 full96 차량 block, nonunit 계통 block, 6,054 coupling 행으로 분할했다. Route/이동 에너지/접속 지연/충방전 mode/SOC/PQ/PCS16을 포함한 원래 모든 정수 계획이 각 Pricing domain에 포함됨을 독립 검증했다. 임의 arc 삭제와 SOC 이산화는 하지 않았다. 계통의 다중 선로·시간 P/Q 쌍대벡터로 exact 가격을 재구성하고, Native binary64 가격은 진단에만 사용했다.

| 가격 단계 | 차량 | 문제 | Native 초 | Work | Native 상태 | 인증 수준 |
|---|---|---|---:|---:|---:|---|
| PRICING | MESS01 | MILP | 8.047 | 18.11077 | 2 | NATIVE_DIAGNOSTIC_ONLY |
| PRICING | MESS01 | LP | 4.704 | 11.61552 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| PRICING | MESS02 | MILP | 11.675 | 27.66615 | 2 | NATIVE_DIAGNOSTIC_ONLY |
| PRICING | MESS02 | LP | 5.064 | 11.92891 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| PRICING | MESS03 | MILP | 8.903 | 20.16069 | 2 | NATIVE_DIAGNOSTIC_ONLY |
| PRICING | MESS03 | LP | 4.874 | 11.57736 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| PRICING | MESS04 | MILP | 10.047 | 23.35312 | 2 | NATIVE_DIAGNOSTIC_ONLY |
| PRICING | MESS04 | LP | 5.887 | 11.42900 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| RMP_PRICING | MESS01 | LP | 6.205 | 8.50152 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| RMP_PRICING | MESS02 | LP | 5.216 | 7.04291 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| RMP_PRICING | MESS03 | LP | 4.878 | 6.55134 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |
| RMP_PRICING | MESS04 | LP | 5.046 | 6.67125 | 2 | EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY |

MILP incumbent는 물리적 열 후보이고 Native BestBd는 별도 exact certificate가 아니다. LP signed dual과 원본 finite box residual로 모든 정수 trajectory를 포함하는 하한을 exact rational로 계산했다. 최종 original-row dual을 원본 전체 CSR에 재조립해 Global weak duality를 독립 재검증했다. 제한 Master 목적값은 Global LB/UB로 사용하지 않았다. Missing-column 인증 상태는 `FULL_PRICING_CLOSURE_NOT_PROVEN`이며 차량별 β−η 검사값을 독립 JSON에 기록했다. TIME_LIMIT은 완전 탐색·불가능성 증명이 아니다.

## 결과 해석과 다음 연구

`PRICING_RUNTIME_CERTIFICATION.csv`는 각 Pricing의 실제 시간, Native objective와 exact local LB의 차이, 선택한 dual 및 strict raw-column admission을 분리한다. full block MILP의 Native 종료만으로 정수 convex hull의 강화나 완전 Pricing closure를 주장하지 않는다. 새로운 유효 LB가 기존 fresh exact LB보다 높은 경우에만 개선으로 기록했다. Signed multiplier 수정/finite-box 수치 인증과 구조적 정수영역 강화는 구분한다.

한 차례 RMP 가격 업데이트는 dual 진동의 장기 수렴을 평가하기에 충분하지 않다. 전역 grid, 시간별 line loading, fleet relocation과 SOC/PCS의 coupling을 원본 행으로 유지했으며, 차량별 convex hull 자체가 부족한지 증명하지 않았다. 인증 실패 원인을 느린 MILP Pricing, 약한 LP 가격 하한, exact residual loss, 미확인 dual 수렴으로 구분해 평가해야 한다. 이유와 증명 수준을 확인하기 전 전체 Branch-and-Price나 production을 자동 실행하지 않는다. 문헌과 안전한 dominance/자원 bound 적용 조건은 [문헌 검토](LITERATURE_REVIEW_KO.md), 후속 admission은 [handoff 계약](HYBRID_HANDOFF_KO.md)을 따른다.

이번 관측에서는 Pricing이 느리지 않았다. 초기 LP의 Native objective와 exact β 사이 차이는 약 9.4e-9~4.5e-8이며, 채택한 LB 개선은 같은 grid 가격에서 local LP dual을 재최적화한 결과다. RMP 새 가격의 exact Global LB 0.06680246877771547은 기존 LB보다 약해 거부했다. RMP에는 차량당 기존 seed와 Pricing RAW의 2개 열만 있었고, 새 best UB의 4개 unit trajectory는 포함되지 않았다. 이는 확인된 제한 catalog의 한계이며 그 자체가 fleet coupling이나 차량 convex hull 부족의 증명은 아니다. 실제 β−η는 네 차량 모두 음수인 하한이어서 missing-column closure가 입증되지 않았다. 음수 하한만으로 정수 negative column의 존재를 주장하지 않는다. [독립 Pricing 진단](PRICING_INDEPENDENT_DIAGNOSIS_KO.md)에 수치와 원인을 분리했다.

UB의 실제 signed 후보는 sw1 A상 슬롯72·90, sw2 A상 슬롯78·84의 원본 계수에서 유도됐다. 이동 경로·연결시각·SOC·PCS와 계통 행을 유지한 accepted point의 관측과 dispatch 변화는 [원본 물리 진단](FULL96_PHYSICAL_DIAGNOSTICS.json)에 있다. 이 선로·시간의 point 진단을 전역 LB의 유일한 제한 원인이나 개별 차량 변경의 인과효과로 해석하지 않는다. 어떤 물리 결합이 integer-hull LB를 제한하는지 확정하려면 완전 정수 Pricing 인증과 별도의 inclusion 보존 분석이 필요하다.

## 시간과 회귀 검증

Native 16회, 누적 Runtime **549.057초**, Work **1257.378577**, optimize API Wall **549.105초**. 최종 검증까지 연속 Wall **1206.536초**이며 model build·exact checker·full replay·최종 회귀를 포함한다. 신규 ledger 제한 2,700초, 요청 상한 2,310초, 원래 M1 단계 상한 5,400초는 보존한다. Threads=1, 원래 tolerance 1e-8, inner MIPGap 0.5%를 유지했다. MemLimit/SoftMemLimit과 RAM 자동 종료는 사용하지 않았다. 과거 Runtime/예산을 초기화하지 않았다.

CSR, verified D frozen files, static graph, strict incumbent는 SHA 확인 후 재사용했다. Presolve는 Native Runtime에 포함되어 있으며 로그의 반올림 시간과 callback span은 별도 참고값이다. 중첩 비용 record를 합산해 Wall을 부풀리지 않는다. 상세 비용은 [COST_BREAKDOWN.json](COST_BREAKDOWN.json)에 있다.

최종 회귀 **649 PASS / 12 SKIP / 0 FAIL**, 테스트 Native=0. 기존 549 PASS를 보존하고 신규 독립 scientific checker를 추가했다. SKIP은 PASS로 세지 않았다. May12/1,782-job M1, A2/M2, 27일 캠페인 또는 다른 입력에 성능이나 acceptance를 전용하지 않는다.
