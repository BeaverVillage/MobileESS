# C3A 분수 상태와 P1 이점의 인과 추적

이 문서는 승인된 추가 순수 LP에서 보존한 실제 barrier 점의 구조를 추적한다. 비교 상대는 검증된 정수 feasible start `UB_ref=0.6694159238756877`이며 정수 최적해가 아니다. 따라서 약 15.04%는 **LP/root lower bound와 알려진 incumbent의 차이**이고, 그 전체가 진짜 integrality gap이라고 증명된 것은 아니다.

## 수치 증거의 자격

`PURE_LP_POINT.npz`의 native status는 OPTIMAL(2), `ObjVal=0.568711942993466`, barrier 112회이다. 그러나 독립 raw C3A matrix replay의 최대 행 위반은 `2.805600374244932e-8`로 원래 기준 `1e-8`을 넘었다. Bound 위반은 0이다. 이 문서의 분수 값과 affine 기여는 **보존된 수치 점의 진단**이며 exact feasible-point certificate로 표현하지 않는다. FeasibilityTol을 변경하거나 점을 보정하지 않았다.

실제 native LP `ObjBound=-97.99221036430035`와 ObjVal을 구분한다. Native bound는 로그의 barrier iteration 8 dual objective와 출력 정밀도 내에서 일치한다. 최종 Pi에는 inequality 부호 위반이 남는다. `NUMERICAL_LP_BOUND_AUDIT.json`의 exact dyadic bounded-Lagrangian 검증은 별도 global continuous LP LB `0.5671374761409242`를 인증한다. 기존 C3A 유효 native LB `0.5687116003498334`가 이 값보다 강하다. Native 내부의 bound 갱신 기준은 기록되지 않았으므로 단정하지 않는다.

## 실제 discrete 계열과 분수 중심

PR162 `ALL_COLUMN_DECISIONS.csv`, C3A typed axis, 원래 물리 소스와 compact node 정의를 연결했다. 9,322개를 빠짐없이 매핑한 결과다.

| 실제 계열 | 원래 discrete 개수 | fractional 개수 | 비율 | Σmin(x,1−x) |
|---|---:|---:|---:|---:|
| 출발 이벤트 node activity | 8,938 | 7,070 | 79.1005% | 286.953195285 |
| 유닛/슬롯 active-power charge mode | 384 | 384 | 100% | 185.428154903 |
| 합계 | 9,322 | 7,454 | 79.9614% | 472.381350188 |

`node_activity`는 해당 DAG 노드의 outgoing arc 질량이며 terminal에서는 incoming 질량이다. 이동 구간의 모든 시각에 실제 사이트 위치를 나타내는 별도 binary로 해석하지 않는다. Route flow는 선택된 compact 모델에서 continuous이며 node integrality와 단일 시간 DAG 경로의 결합이 원래 route integrality를 복원한다. 별도 retained route selector, transit binary, connection binary, 추가 PCS mode binary는 없다. Q는 charge mode와 독립이다.

MESS02가 fractionality mass `118.435848441`로 가장 크지만 다른 유닛도 약 `117.93~118.02`로 가깝다. 큰 개별 분수 변수는 mode이며 `charge_mode[MESS04,69]=0.49990505638503346`이다. 최대 한 슬롯 block은 MESS04/69, 최대 4슬롯 window는 MESS02/73~76, mass `5.996711602240868`이다. 전체 분수 mass의 80%에 3,504개, 90%에 5,271개 변수가 필요하다. 작은 몇 개 변수만으로 전체 mass를 설명할 수 없다.

384개 유닛/슬롯 중 연결 사이트가 둘 이상인 경우는 377개, 복수 MOVE route가 동시에 출발하는 경우는 292개, 동일 source/time에서 arc가 분기하는 경우는 316개이다. 출발 MOVE와 STAY 혼합은 316개, 이미 진행 중인 transit까지 포함한 connection/transit 혼합은 352개이다. 서로 다른 사이트 STAY를 단순히 복수 이동 route로 세지 않았다.

Charge mode는 전 384개가 fractional이고 `C>1e-8, D>1e-8`도 전 384개에 존재한다. 최대 `min(C,D)`는 `78.9609593573 kW`이다. 다만 peak에서 작은 충전 값이 `1e-7 kW` 정도인 경우도 포함한다. 이 개수만으로 물리적으로 큰 동시 충전/방전이나 mode가 지배적인 gap 원인이라고 판단하지 않는다. 합법적인 정수 schedule들의 convex mixture도 fractional 위치와 서로 다른 mode의 혼합을 가질 수 있기 때문이다.

## rho를 정의하는 실제 line/time

Thermal face의 대상은 남은 response 변수 이름으로 추정하지 않았다. C3 retained row → C2 retained row → C1 original/C0 row → 원래 REDUCTION_AXES → FULL native row 축을 따라 복원했다. 예를 들어 line 3 P/Q가 남은 모델에서 transformer P/Q alias를 사용해도 대상은 원래 line 3이다.

`abs(native Slack)<=1e-8`인 thermal face는 95개이다. Branch label은 동결 electrical certificate와 planning coefficient archive의 원래 branch axis를 해시 검증하여 읽었다.

| native line index | 동결 branch/phase | active face 수 | 슬롯 범위 | 해당 행에서 최대 incumbent−LP required rho |
|---:|---|---:|---|---:|
| 3 | `line.sw1::A` | 48 | 66~95 | 0.100703980888 |
| 15 | `line.l3::A` | 1 | 72 | 0.080210512501 |
| 26 | `line.l10::A` | 23 | 66~87 | 0.100703980887 |
| 33 | `line.sw2::A` | 9 | 80~89 | 0.076895695416 |
| 43 | `line.l116::A` | 12 | 73~86 | 0.097209486615 |
| 122 | `line.l58::A` | 2 | 77~79 | 0.042989348025 |

동결 electrical certificate SHA는 `c6b649edc1b2b3e2f324b0e41f939e397bdfcb26b64fff2c7be56d3d27424d35`, planning coefficient NPZ SHA는 `735e190e1a5e5367c26ee4848192a41bdb8cc5749ebd5e3cb177f9599a314ef7`이다. P1은 원래 stored thermal face와 correction/bias의 epigraph이며 이 표를 새로운 원형 PCS, AC load-flow 또는 다른 line-loading 정의로 해석하지 않는다.

## 직접 관측된 P/Q → critical-row 이점

대표 행 C3A `465244` / 원래 FULL native `769488`은 슬롯 72의 `line.sw1::A`이다. 원래 equality closure를 Pch/Pdis/Q로 전개하면 다음 수치가 나온다. Float affine replay이며 rational validity proof와 구분한다.

| 분해 항 | barrier 점 | validated integer start |
|---|---:|---:|
| 동결 baseline required rho | 0.667834891220 | 0.667834891220 |
| Pch 기여 | 0.000000000130 | 0 |
| Pdis 기여 | −0.100563786618 | 0 |
| Q 기여 | +0.001440838255 | +0.001581032656 |
| 합계 required rho | 0.568711942988 | 0.669415923876 |

이 행에서 `0.100703980888` 차이는 대부분 LP의 방전 배치에서 발생한다. 네 유닛 LP의 총 방전은 약 `526.539167402 kW`이고 reference integer start는 이 슬롯에서 방전 0이다. 이는 **관측된 두 점 사이의 affine 차이**다. 정수 모델이 이만큼 방전할 수 없다는 최적성 증명은 아니다.

MESS02/72를 보면 stay 질량이 약 1이지만 여덟 사이트에 분산되어 있다. 이 점의 mode는 `0.492606748435903`이다.

| 사이트 | LP stay 질량 | LP Pdis kW | LP Q kvar |
|---|---:|---:|---:|
| IDC01 | 0.210911087 | 약 0 | +25.686037 |
| IDC02 | 0.150909257 | 45.272777 | +38.454084 |
| IDC03 | 0.074259019 | 0.000605 | −29.107066 |
| IDC04 | 0.000005242 | 0.001573 | −0.001333 |
| IDC08 | 0.072195935 | 약 0 | +25.072297 |
| IDC09 | 0.158974817 | 약 0 | +62.368064 |
| STA02 | 0.136282906 | 40.884872 | −34.727056 |
| STA12 | 0.196461685 | 45.007605 | −63.992470 |

Reference start의 MESS02는 STA12 한 곳에 연결되어 있고 Pdis=0, Q=`−392.3141121612922 kvar`이다. LP는 서로 다른 사이트의 방전과 양/음 Q를 동시에 배치해 전체 grid rows를 평탄화한다. 한 실제 MESS 정수 경로가 한 슬롯에 여덟 사이트에 있을 수는 없다. 그러나 각 site power가 분수 stay에 비례하는 합법적인 schedule mixture인지, SOC가 그 mixture를 정확히 연결하는지는 별도 hull 문제다.

슬롯 79의 `line.l10::A` 행 `497237`도 같은 차이 `0.100703980887`을 보인다. LP의 Pdis 기여는 `−0.085666216095`, Q 기여는 `−0.017217961658`, Pch 기여는 `+0.000008537758`이다. 따라서 이 행에서는 유효전력과 무효전력의 사이트별 배치가 함께 중요하다. Reference start의 Q 기여는 `−0.002171659108`이고 Pdis/Pch 기여는 0이다.

현재 지지되는 사슬은 **분수 node/route/stay 상태에 대응하는 분산 P/Q 배치 → 원래 critical thermal affine rows의 required rho 감소 → 알려진 start에 대한 objective 이점**이다. 이 사슬이 전역 정수 최적값 차이 전체를 설명한다는 결론, 각 mode 분수 값이 필수라는 결론, 모든 분산 P/Q가 local convex hull 밖이라는 결론은 아직 성립하지 않는다.

## 실제 local hull 위반과 강화 실험의 역할

원래 integer unit path와 exclusive mode로부터 증명한 `ΣC<=300 mode`, `ΣD<=300(1−mode)`, `Σ(C+D)<=300Σstay`, `C_site+D_site<=300 stay_site`를 시험했다. Aggregate connected cut은 local connected cuts의 합이다.

Fresh baseline 수치 점에서 mode aggregate 두 계열은 위반되지 않았다. Aggregate connected는 250개, local connected는 5,871개가 위반된다. 이 basic connected 위반은 모두 슬롯 66 이전이다. 따라서 이들 cut의 peak rho 영향이 있다면 이전 슬롯 power/SOC와 이후 방전 사이의 coupling을 통해 발생해야 한다. 현재 point에서 basic cut이 직접 peak line row를 제한한다고 말하지 않는다.

추가로 실제 stored binary64 PCS half-planes에서 두 integer direction half-polygons의 정확한 rational union hull을 구했다. `α(C+D)+βQ<=γ stay`의 네 nonzero-Q facet은 실제 target site의 original vertices로 독립 검증했고 coefficient rounding을 RHS 방향으로 보수화했다. 삼각함수 대칭을 가정하거나 baseline 점에 맞춰 coefficient를 학습하지 않았다.

이 folded PCS 계열의 baseline 위반은 2,323개이며 이 중 29개가 critical 시간 범위 66~95에 있다. 최대 위반은 MESS04/65/IDC01의 `16.7177797095`이다. 이 계열은 net P=`D−C` 상쇄가 absolute active power=`C+D`와 Q의 PCS 용량을 느슨하게 만드는 disjunction을 겨냥한다. 증명된 facet의 실제 위반은 해당 local PCS-mode hull 밖임을 뒷받침한다. 단 raw feasibility FAIL을 무시해 exact baseline feasible witness라고 선언하지 않으며, 작은 수치 위반과 큰 structural violation을 구분한다.

1슬롯 audit는 원래 power/Q/SOC bounds와 energy transition, 실제 reachable route 및 두 mode의 연속 vertices를 포함한다. Boundary SOC를 원래 bounds 안에서 자유롭게 두는 보수적 local projection이고 전역 96슬롯 hull이라고 주장하지 않는다. Global prior/future SOC와 grid coupling은 이 finite local audit에 포함되지 않는다.

Cut 위반은 LB 개선을 보장하지 않는다. Loop의 각 round에서 native LP bound, exact bounded-Lagrangian certificate, 이전 C3A 유효 bound를 구분하여 기록한다. ObjVal의 수치 변화만으로 material improvement를 선언하지 않는다. Selective-integrality 실험이 끝나기 전에는 location 또는 mode가 가장 큰 gap 기여 계열이라고 확정하지 않는다.

## 현재까지 남은 인과 한계

증거는 location/route mixture, PCS-mode의 local hull 누락, peak P/Q affine 이점이 함께 존재함을 보여준다. 0.6694159 reference가 최적해인지, 이 local 누락을 제거하면 얼마나 global LB가 오르는지, 시간 전반 SOC/route와 다수 critical grid rows의 coupling이 얼마나 남는지는 진행 중인 제한된 실험 결과로 판단해야 한다.

이 문서는 완료되지 않은 LP loop나 selective-integrality 결과를 만들어 넣지 않는다. 최종 선택·bound 변화·분류는 실제 완료 receipt와 `FINAL_REVIEW_KO.md`에서 확정한다. 과거 `HISTORICAL_PROXY_*` 결과는 별도 provenance이며 이 문서의 fresh census와 합치지 않았다.

## 완료 실험 결론

10회 작은 batch LP 강화에서 총 320행, 17,837 nnz를 추가했다. 최고 유효 global LB는 0.568711600349833, ΔLB=0이며 마지막 approximate primal rho는 0.568711662530299다. Primal proxy·native barrier ObjBound·exact bounded-Lagrangian certificate를 분리했다. 이 실험은 한 슬롯 connection/mode/PCS hull의 제한적 강화로 gap을 설명하는 material 하한 상승을 입증하지 못했다.

두 제한 시험에서 지배적인 gap 기여 계열을 확정할 만큼의 전역 하한 상승을 얻지 못했다. TimeLimit 결과는 해당 계열의 무관함을 증명하지 않는다. 마지막 저장 cut LP 점의 원래 discrete 중 7,454개가 여전히 분수다. 시험 후보 중 241개는 아직 미선택 위반으로 남았다. 이 값은 남은 후보의 효과나 gap 원인 증명이 아닌 point census다.

최종 분류는 `ROOT_GAP_NOT_EXPLAINED_BY_TESTED_LOCAL_HULLS`이다. 조건부 native root-only는 실행하지 않았다. 다음 미해결 결합은 시간 간 SOC/route/mode와 다수 critical grid rows이다. 권고한 하나의 후속 4슬롯 joint hull 실험도 실행하지 않았다.
