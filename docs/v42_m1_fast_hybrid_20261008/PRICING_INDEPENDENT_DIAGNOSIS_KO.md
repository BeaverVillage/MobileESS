# May01 full96 trajectory pricing 독립 진단

동일 May01/1,499-job 원본 문제의 최종 독립 검증은 **PASS**다. strict Global UB는 `0.5949967486929637`, exact signed-dual Global LB는 `0.5686444703080522`, exact Global Gap은 **4.428978552034077%**다. 5% 연구 Gap 목표는 인증했지만, full integer pricing closure와 정수 convex-hull 강화는 **NOT_PROVEN**이다. `M1_ACCEPTED=false`, `P2_certificate=null`, production default 미승격을 유지한다.

이 진단은 자연 종료한 저장 증거를 읽고 원본 물리 checker로 RAW column을 재검사한 결과다. 소스·모델·파라미터·callback 수정과 신규 Native 호출은 0이다. 최종 Global LB/UB/Gap authority는 [INDEPENDENT_FINAL_VERIFICATION.json](D:/MobileESS_v42/docs/v42_m1_fast_hybrid_20261008/INDEPENDENT_FINAL_VERIFICATION.json)이며, 이 문서는 Native objective나 BestBd를 대체 certificate로 사용하지 않는다.

## 입력과 검증 범위

- Run ID: `hybrid_may01_20261008_5pct_pilot01`.
- 기준 완료 HEAD: `6122331841e22562d23eb054c4168b5130566f3f`.
- case SHA256: `cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a`.
- 원본 C3A authority: PR162 `1d922c91eb27056a5ccc79c92ef18146707099ab`; 완료 M authority: PR188 `4b19e85089171729a3225529a40cb00bf31f43d5`.
- 원본 4 MESS·24 services·96 slots, 582,808행·306,040열·5,351,612 nonzero 및 모든 bounds/types/RHS/sense/목적함수 보존.
- 원본 FULL local 행·literal 정수·경로/SOC/접속/PQ/PCS validator 재사용. original coupling 6,054행과 NONUNIT 433,494행·61,776열도 certificate에 포함.
- 독립 최종 검증 JSON SHA256: `e581db2fbccd66ca95930ba837564f23ca89abbb2a0c87fdea60ca6456ad50dd`.

소스와 frozen input의 상세 hash, 종료 계약과 후속 admission은 [HYBRID_HANDOFF_KO.md](D:/MobileESS_v42/docs/v42_m1_fast_hybrid_20261008/HYBRID_HANDOFF_KO.md)에 있다. 새 May12/1,782-job 입력, A2/M2, 기존 27일 또는 5월 전체 캠페인으로 이 결과를 승계하지 않는다.

## 첫 가격화: 실제 Native와 exact 하한

다중 원본 coupling 가격의 active multiplier는 5,162개다. 동일 가격에서 4개의 full96 local MILP와 4개의 local LP를 각각 한 번 수행했다. 모든 Native status는 `2/OPTIMAL`이지만, MILP status는 inner MIPGap=0.005 및 solver tolerance 기준이다. 수학적 exact 정수 최적성을 의미하지 않는다.

| 차량 | MILP Native 초 | Native ObjVal | Native BestBd | RAW local column |
|---|---:|---:|---:|---|
| MESS01 | 8.047 | -0.011061506678721 | -0.011114549168278 | literal/원본 물리 PASS |
| MESS02 | 11.675 | -0.011114538251805 | -0.011114538251805 | literal/원본 물리 PASS |
| MESS03 | 8.903 | -0.011114567761359 | -0.011114567761359 | literal/원본 물리 PASS |
| MESS04 | 10.047 | -0.011086896687408 | -0.011114516223849 | literal/원본 물리 PASS |

MESS01/04는 ObjVal과 BestBd 사이 차이가 남아 있다. MESS02/03의 표시값 일치도 binary64 solver의 진단이며 exact integer lower proof가 아니다. 이 4개 BestBd를 합해 Global LB를 만들지 않았다.

| 차량 | LP Native 초 | Native LP objective/BestBd | exact 선택 β | Native objective−exact β |
|---|---:|---:|---:|---:|
| MESS01 | 4.704 | -0.011114608382162 | -0.011114645094749 | 약 3.6713e-8 |
| MESS02 | 5.064 | -0.011114608381214 | -0.011114653323300 | 약 4.4942e-8 |
| MESS03 | 4.874 | -0.011114608330614 | -0.011114617737250 | 약 9.4066e-9 |
| MESS04 | 5.887 | -0.011114608329308 | -0.011114618152777 | 약 9.8235e-9 |

Native 목적함수는 exact rational coupling 가격을 binary64로 반올림한 탐색 모델의 값이다. β는 반올림 가격 objective에 의존하지 않고 원본 coefficient와 signed Pi의 exact weak duality 및 finite box correction으로 검사한 값이다. 위 차이는 서로 다른 수치 표현을 포함하는 진단값이며 정수 Gap이나 순수 rounding error라고 단정하지 않는다.

4개 fresh local LP dual을 모두 채택했다. 원본 source의 local β는 각각 약 `-0.011378577732398`, `-0.011378575397613`, `-0.011378597764026`, `-0.011378572579384`였다. 이를 재최적화한 local LP dual로 교체하여, 원래 exact LB `0.5675886811427069`가 `0.5686444703080522`로 **0.0010557891653453536** 개선됐다. 이 수치는 최종 독립 checker가 원본 전체 CSR에서 다시 인증했다.

새 β의 RHS dual part는 차량별 약 `+0.012525`, finite-box residual part는 약 `-0.023640`이다. 이 음수 correction 전체를 작은 수치 오차로 간주하거나 생략하면 안 된다. 선택 β에는 남은 모든 local column residual과 원본 bounds가 포함된다. 원본 NONUNIT 기여 `0.6131030046186338`와 coupling constant 약 `-2.5053161466e-12`, 네 β의 exact 합이 full-original rational certificate와 일치한다.

이것은 동일 원본 LP/Lagrange 가격에서 더 나은 multiplier를 얻은 개선이다. 원본 domain을 강화하거나 모든 정수 trajectory convex hull을 완전히 생성한 변화가 아니다. local MILP RAW는 좋은 물리 column을 제공했지만, 그 정수 목적값에 대응하는 독립 exact MILP lower certificate는 이번 증거에 없다. 따라서 LP certificate 개선과 genuine integer-hull 개선을 분리한다.

## RAW 물리 replay와 병목 증거의 한계

읽기 전용 재검사는 4개 NPZ의 SHA를 읽기 전후 비교하고 original column axes, local C3A 전체 행·literal binary, 원본 FULL unit 정수, original FULL local 행, unchanged 96슬롯 물리 validator를 다시 확인했다. 추가 Native=0, 이 재검사의 실제 Wall은 약 6.483초다.

| 차량 | C3A local 행 | 최대 observed residual | 최대 outward upper | FULL unit discrete | FULL local 행 | literal·물리 |
|---|---:|---:|---:|---:|---:|---|
| MESS01 | 35,775 | 1.02318e-10 | 6.12687e-10 | 52,018 | 51,458 | PASS |
| MESS02 | 35,823 | 1.13687e-13 | 5.79398e-10 | 52,090 | 51,527 | PASS |
| MESS03 | 35,871 | 1.13687e-13 | 5.79455e-10 | 52,162 | 51,596 | PASS |
| MESS04 | 35,791 | 7.29869e-11 | 5.79412e-10 | 52,042 | 51,481 | PASS |

local C3A의 행·bound·integrality tolerance는 1e-8이며 literal binary/정수 gate는 tolerance와 별개다. 원본 FULL의 기존 family별 mixed row tolerance를 유지했다: local flow/terminal strict 행은 1e-8, 그 밖의 기존 local family는 1e-6, bounds/integrality는 1e-8이다. RAW를 반올림·clipping·repair하지 않았다. 모든 literal gate 및 경로/SOC/PCS/PQ/접속 replay가 통과했다.

| RAW 파일 | SHA256 |
|---|---|
| MESS01_MILP_RAW_COLUMN.npz | `b4af4e4b8e3ee6188bcb418d88649214b566fdf557e38fb77802cbe0318cac92` |
| MESS02_MILP_RAW_COLUMN.npz | `da7e08d34f93030ce34fad178ee58553f669a9a980dbae030f5f7df72dc24db7` |
| MESS03_MILP_RAW_COLUMN.npz | `78ebe56238ddbfef245c1d97769d98128447947504262d5cc8064b5be75fe5b6` |
| MESS04_MILP_RAW_COLUMN.npz | `a8b1752334b2144b6cb3b4fe82ce8ceeacb9237a07646df31a7b0eca79c6ed9c` |

local column replay에서는 grid coupling을 강제하지 않는다. 따라서 위 4개 local PASS를 Global UB나 서로 동시에 가능한 fleet 운전으로 승격하지 않는다. 최종 UB는 별도 전체 RAW의 C3A/FULL literal 정수·full matrix·물리 replay에서 인증됐다. 이번 local 증거에는 물리 위반, RAW column 거부, 경로 불가능성의 증거가 없다. Gap이 남았다는 이유로 SOC/PCS 또는 fleet coupling이 특정한 전역 불가능성을 만든다고 단정하지 않는다.

## RMP 한 차례 가격 갱신

restricted RMP는 차량별 2개 column, 합계 8개 catalog와 원본 NONUNIT/coupling을 사용했다. Native Runtime은 1.019초, Native objective는 `0.6063186498423844`였다. 이 값은 restricted catalog의 수치 진단이며 Global LB/UB 또는 full pricing closure 증거가 아니다.

RMP 가격의 active coupling multiplier는 239개로, 첫 가격의 5,162개와 다르다. 이 새 가격에서 등록된 4개 LP를 각각 한 번 수행했고 Runtime은 6.205 / 5.216 / 4.878 / 5.046초, 합계 **21.345초**였다. 모두 Native OPTIMAL이며 exact 가격 β는 다음과 같다.

| 차량 | exact complete-domain 가격 β | convexity dual η | exact β−η | missing-column closure |
|---|---:|---:|---:|---|
| MESS01 | -0.116768920531557 | 0.003919842999813 | -0.120688763531370 | NOT_PROVEN |
| MESS02 | -0.116768920531468 | 0.041690699946604 | -0.158459620478072 | NOT_PROVEN |
| MESS03 | -0.116768920531477 | 0.003446548203147 | -0.120215468734624 | NOT_PROVEN |
| MESS04 | -0.116768920531447 | 0.023383407789155 | -0.140152328320602 | NOT_PROVEN |

독립 checker는 **FULL_PRICING_CLOSURE_NOT_PROVEN**으로 판정했다. 모든 β−η 하한이 음수이므로 모든 missing columns의 nonnegative reduced cost를 보증하는 충분조건이 실패한다. 음수 lower bound 자체는 실제 negative 정수 column의 존재도, 원본 정수 문제의 infeasibility도 증명하지 않는다. 반복 수렴·dual 진동·fleet convex hull 자체의 한계를 판정하기에는 한 차례 RMP 갱신만으로 부족하다.

이 새 가격의 full-original exact LB는 **0.06680246877771547**이다. 인증 자체는 원본 전체 문제에 유효하지만 첫 가격의 LB보다 약해 최종 max에 채택하지 않았다. RMP-price 결과의 `independently_certified_LB_gain=7.93819026843134`는 이 새 가격에서 local seed multiplier=0의 매우 약한 baseline 대비 개선이다. 이전 완료 연구나 첫 가격의 LB를 그만큼 개선했다는 뜻이 아니다.

실행된 RMP catalog에는 최신 UB feedback도 포함되지 않았다. `FINAL_STRICT_UB_POINT.npz`의 차량별 vector SHA를 catalog와 비교하면 4대 모두 일치하는 열이 없다. catalog는 기존 strict seed와 첫 pricing RAW로 구성됐다. 따라서 최신 전역 UB의 trajectory를 RMP에 전달한 뒤의 성능은 이 pilot에서 **NOT_RUN**이다. 이 확인된 범위가 RMP 목적값 정체나 약한 dual의 원인이라는 인과 증명은 없다. 다음 bounded 실험에서 검증된 최신 UB column을 catalog에 넣는 방향은 검토할 수 있지만, 현재 실행 소스나 결과를 수정하지 않는다.

## 시간과 최종 해석

첫 pricing 8회의 실제 Native Runtime은 **59.201초**, 해당 pricing 함수 Wall은 **147.372초**, optimize API Wall은 **59.269초**다. 나머지 약 **88.103초**는 가격/원본 증거 저장, model build, RAW 물리 검사, exact certificate와 NONUNIT 산술 등의 비용이며 세부 record는 겹칠 수 있으므로 별도 값들을 다시 합산하지 않는다. 모든 local Native가 등록 상한 전에 자연 종료했다. 성능이 느려 pricing closure를 못 증명했다고 말할 근거는 없다.

전체 pilot은 등록된 16회가 자연 종료했고 누적 Native Runtime **549.057초**다. independent final verifier는 Native=0, checker Wall 약 **75.404초**, issues=[]로 종료했다. 최종 회귀는 root가 수집한 **649 PASS / 12 SKIP**이며 SKIP을 PASS로 세지 않는다. Native phase Wall과 final checker/회귀 비용의 전체 연속 elapsed 판정은 [FINAL_RESEARCH_STATUS.json](D:/MobileESS_v42/docs/v42_m1_fast_hybrid_20261008/FINAL_RESEARCH_STATUS.json)을 따른다. 가격화 함수 시간만으로 전체 연구 Wall을 대신하지 않는다.

최종 strict UB는 이전 완료 UB보다 **0.011321901149421776** 낮고, exact LB는 **0.0010557891653453536** 높다. 두 독립 개선의 결과로 5% 연구 Gap을 달성했다. 초기 source LB만으로도 새로운 UB에서 약 4.61% Gap이므로, 5% threshold 통과는 UB 개선의 역할이 크다. 새로운 local LP certificate는 그 Gap을 추가로 낮췄다. 이 해석은 full integer hull 생성이나 complete DW 해결을 주장하지 않는다.

다음 실험을 한다면 source 가격의 exact LB를 fallback으로 보존하고, 최신 검증 UB의 전체 trajectory feedback과 명시한 가격 안정화를 별도의 completed HEAD·새 ledger로 사전 등록하는 것이 한 후보다. 원본 가격 벡터와 complete-domain lower proof를 유지하고 β−η를 다시 검사한다. SOC bucket, top-k arc, 대표 P/Q, 검증되지 않은 dominance 또는 실패 solver로 domain을 축소하지 않는다. 현 단계에는 추가 Native를 소진하는 반복이나 production 자동 전환이 없다.

## 재현 evidence

| 증거 | SHA256 또는 경로 |
|---|---|
| initial PRICING_RESULT.json | `8ccd8ec9bab18fdb8912b1ef117c63a212428d55ef4f57485543674281a3c90b` |
| RMP-price PRICING_RESULT.json | `ee3303e574bee61bba1cf8f48327e4ff3f3fc082f549116efbbcde63875e7524` |
| RMP_RESULT.json | `3b44b6171b8813e4be83f2da0b3b13c028e005d0ddd0c9695212809ea26da927` |
| 실행 소스 고정 | [EXECUTED_SOURCE_HASHES.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/EXECUTED_SOURCE_HASHES.json) |
| 최초 pricing | [PRICING_RESULT.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/pricing_initial/PRICING_RESULT.json) |
| 조건부 RMP 가격화 | [PRICING_RESULT.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/pricing_rmp/PRICING_RESULT.json) |
| 원본 full-domain LB/Gap 및 closure | [독립 최종 검증](D:/MobileESS_v42/docs/v42_m1_fast_hybrid_20261008/INDEPENDENT_FINAL_VERIFICATION.json) |

이 문서의 소수 표시는 읽기 위한 값이다. source rational β, λ, η, original row mappings와 canonical full original dual은 저장된 JSON/NPZ와 독립 검증 receipt를 authority로 사용한다.
