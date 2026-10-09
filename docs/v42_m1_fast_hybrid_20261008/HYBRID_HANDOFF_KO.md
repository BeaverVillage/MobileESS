# V42 M1 full-trajectory hybrid handoff

이 문서는 `hybrid_may01_20261008_5pct_pilot01`의 방법·증명·후속 실험 계약이다. 현재 Native 실행의 성능이나 최종 수치는 예측하지 않는다. 수치 판정은 실행이 자연 종료된 뒤 저장된 RAW와 독립 checker 결과를 인용하는 최종 보고서에서 수행한다. 이 문서 작성의 추가 Native 호출은 0이며, 실행 중 소스·모델·callback·파라미터·시간 계획을 변경하지 않는다.

## 1. 고정 authority와 작업공간

단일 작업공간은 `D:\MobileESS_v42`, 브랜치는 `v42`다. 신규 임시 파일·캐시·로그·증거는 D에 두고 기존 C 작업공간과 다른 M 연구의 프로세스·미완료 결과를 수정하거나 수용하지 않는다.

| 항목 | 고정 값 |
|---|---|
| 완료 기준 HEAD | `6122331841e22562d23eb054c4168b5130566f3f` |
| A-stage 완료 authority | PR186 `9a1b41260aff3bc70d2e36d7e1c293c03ea114de` |
| M-stage 완료 authority | PR188 `4b19e85089171729a3225529a40cb00bf31f43d5` |
| 원본 C3A authority | PR162 `1d922c91eb27056a5ccc79c92ef18146707099ab` |
| case SHA256 | `cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a` |
| 대상 | 2025-05-01, AIDC 1,499 jobs, 4 MESS, 24 services, 96 slots |
| 원본 목적함수 | `min rho_max` |
| C3A 행렬 파일 SHA256 | `45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8` |
| C3A 데이터 파일 SHA256 | `20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467` |
| 원본 FULL 행렬 파일 SHA256 | `35bdc6e7c2664b763d3d0456b7296b7c8830d7c7c39a61a3cb32e699f8bb2024` |
| 원본 FULL 데이터 파일 SHA256 | `ba6eacea23b71db0b5c6d4e18d6370942906ce2790276127139dbc2ece1d2912` |
| frozen bundle SHA256 | `79263899f1040d8b13b5af29dc881c52e83ac543c96f90f8e63e9061b637aa74` |
| route table SHA256 | `3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9` |
| 원본 common `mess.py` SHA256 | `547f5d7aec0572c65b96b9e61382176e269af7d93937fe71ca2a57de265217ec` |
| 원본 common `m1.py` SHA256 | `31279b85f8a69c41d80e0f19feda3cd2c9d7cd6026f1e8a4c5b046034363bae4` |
| 기존 exact repaired dual 파일 SHA256 | `e855601800fd1cd3b2aa3479b1ccd5c32567de21897c253f033f2df57c782817` |

위 hash는 immutable 과학적 입력 authority다. 새 저장 파일의 압축 방식이나 새 경로 때문에 파일 hash가 달라질 수 있으므로 동일성은 원본 파일 SHA와 CSR `indptr/indices/data`, axes, RHS/sense, bounds/types, 목적함수의 직접 일치로 각각 검사한다. 실행 소스의 정확한 hash는 [EXECUTED_SOURCE_HASHES.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/EXECUTED_SOURCE_HASHES.json)에 고정되어 있다. 새로운 실행은 현재 파일 hash와 이 receipt가 같은지 먼저 검사한다.

완료 기준에서 독립 검증된 RAW UB는 `0.6063186498423855`, 기존 repaired rational LB는 `0.5675886811427069`다. 이는 이번 Native 결과가 아니다. 해당 pair의 exact Gap은 약 `6.3877251194%`이며, 기존 UB를 유지하면 5%에 필요한 LB는 약 `0.5760027173502662`, 기존 LB를 유지하면 필요한 UB는 약 `0.597461769623902`다. 실제 목표 판정에는 저장된 rational LB와 RAW objective의 exact binary64 값을 사용한다. 이 임계값은 성능 예측이 아니다.

## 2. 완전 trajectory 열의 의미

차량별 block의 열은 96슬롯 전체의 `route_flow`, `node_activity`, `charge_mode`, `SOC`, `Pch`, `Pdis`, `Q` 원본 C3A 변수다. route_flow는 C3A가 채택한 원본 연속 type을 유지한다. node/mode binary만을 임의의 새로운 arc binary로 바꾸거나, 슬롯·arc·dispatch 조합을 삭제하지 않는다. 원본 FULL로 lift한 arc 및 다른 정수 변수의 literal 정수성은 별도로 검사한다.

하나의 trajectory column은 장소·시간별 이동과 접속, 이동 에너지, 초기/terminal SOC, SOC 연속성, 충전/방전 mode, 연결 상태, PCS 및 P/Q를 함께 만족하는 한 차량의 전체 계획이다. 용량 스칼라, critical-window 조각, 4-slot hull, 한 슬롯의 mode 값으로 대체하지 않는다. sparse 저장은 원본 matrix의 모든 nonzero를 유지한 표현이며, 물리 영역을 줄이는 sparsification이 아니다.

원본 전체 행과 열을 incidence로 다음과 같이 분할한다.

| 블록 | 행 | 열 | nonzero |
|---|---:|---:|---:|
| MESS01 | 35,775 | 60,996 | 310,451 |
| MESS02 | 35,823 | 61,080 | 310,877 |
| MESS03 | 35,871 | 61,164 | 311,303 |
| MESS04 | 35,791 | 61,024 | 310,593 |
| NONUNIT | 433,494 | 61,776 | 원본 CSR에서 직접 재검사 |
| COUPLING | 6,054 | 전체 원본 열의 mixed support | 원본 CSR에서 직접 재검사 |

전체 C3A는 582,808행·306,040열·5,351,612 nonzero다. local 행은 support가 한 차량에만 속하고, NONUNIT 행은 support가 비차량 변수에만 속하거나 비어 있으며, 나머지는 COUPLING이다. 비차량 grid/rho 변수와 원본 grid 행을 NONUNIT에서 유지한다. 따라서 원본 feasible domain은 `4개 원본 local domain × 원본 NONUNIT domain`에 원본 coupling을 교차한 영역과 같다. 각 원본 행·열이 정확히 한 번 포함되고 모든 계수·RHS/sense·bounds/types·목적함수가 보존되어야 이 명제가 성립한다.

local column admission은 다음 조건을 모두 요구한다.

1. RAW를 변경하지 않고 local C3A 전체 행·bounds/types를 재검사한다.
2. local C3A binary가 tolerance 안에 있다는 사실과 literal `0/1`이라는 사실을 구분한다. literal gate가 실패하면 column을 수용하지 않는다.
3. 원본 FULL lift 후 해당 차량의 arc/mode 등 모든 정수 pattern이 literal 정수이고 binary는 `0/1`인지 검사한다.
4. 원본 FULL local 행과 unchanged 물리 validator로 96슬롯 경로·SOC·P/Q·PCS·접속을 replay한다. 반올림·clipping·route 추출 수리·dispatch 수리를 하지 않는다.

Native의 FeasibilityTol/OptimalityTol/IntFeasTol=1e-8과 독립 원본 FULL replay의 기존 family별 tolerance를 구분한다. C3A/local checker는 행·bounds·integrality 1e-8을 사용한다. 원본 FULL replay는 기존 mixed row tolerance를 유지하며 flow/terminal 및 해당 grid strict family는 1e-8, 그 밖의 기존 family는 1e-6이다. bounds/integrality는 1e-8이고 literal 정수 gate는 tolerance와 별개다. observed residual, outward upper enclosure, near-threshold exact dyadic 비교 및 적용 tolerance를 저장해 어느 gate에서 통과·실패했는지 밝힌다.

이 gate를 통과한 local column도 전역 UB가 아니다. 다른 차량·grid recourse와 원본 coupling을 모두 만족하고, full C3A/FULL integer·물리 replay 및 objective 동일성이 확인된 전체 RAW만 UB 후보가 된다. AIDC job과 계통 동일성은 동일 frozen matrix/data/bundle authority와 full-row replay로 확인한다.

## 3. exact LP/Lagrange LB와 정수 convex-hull LB

결합 행을 `B x [sense] b`, local domain을 `X_u`, NONUNIT domain을 `X_0`라 쓰면 minimization의 signed 가격은 `<=` 행에서 λ≤0, `>=` 행에서 λ≥0, equality에서 자유다. 가격화 목적함수는 각 원본 열의 `r = c − Bᵀλ`이고 Lagrange bound는 다음과 같다.

`ObjCon + λᵀb + Σ_u min_{x_u∈X_u} r_uᵀx_u + min_{x_0∈X_0} r_0ᵀx_0`.

현재 certificate는 각 local LP dual, 원본 NONUNIT signed dual, 모든 mixed coupling 가격을 원본 전체 행 multiplier `y`로 재조립한다. 독립 checker가 저장된 binary64를 exact rational로 해석하여 다음 수식을 원본 전체 CSR/box에서 다시 계산한다.

`LB = ObjCon + bᵀy + min_original_box ((c − Aᵀy)ᵀx)`.

모든 residual을 원본 finite bounds에서 minimize하므로 incomplete LP dual, TIME_LIMIT의 유효한 signed Pi, 또는 기존 exact seed도 이 LB의 증거가 될 수 있다. objective나 최적 status를 믿는 증명이 아니다. Native에 전달된 binary64 price의 반올림은 탐색에 사용하지만 certificate에는 원본 CSR과 exact rational 가격만 사용한다. NONUNIT 기여나 residual box correction을 누락하면 전역 bound를 과대평가할 수 있다.

이 인증은 local LP relaxation에서 나온 bound다. compact LP의 정수성 손실을 제거하거나 4개 정수 trajectory convex hull을 완전히 생성했다는 증거는 아니다. 기존 multiplier의 수치 residual 손실을 줄여 LB가 좋아진 경우에는 **인증 손실 감소**로 기록하고, 정수 block을 통해 더 강한 bound를 얻은 경우와 구분한다.

정수 convex-hull LB를 주장하려면 모든 원본 정수 trajectory의 가격 최소값에 대해 별도의 exact lower certificate가 필요하다. 현재 MILP pricing의 incumbent는 유효 column 후보이며 Native `ObjBound`, native Gap, TIME_LIMIT 자체는 이러한 exact certificate가 아니다. 등록된 MILP를 제한 시간 안에 수행했다는 사실만으로 full integer pricing closure가 생기지 않는다.

## 4. 제한된 RMP와 closure gate

RMP는 발견·검증된 trajectory catalog에만 convexity weights를 둔다. 여기에 원본 NONUNIT 변수·행과 원본 coupling을 연결한다. 그 restricted LP objective를 그대로 Global LB 또는 integer UB로 승격하지 않는다. 분수 trajectory 조합은 한 차량의 실제 물리 운전과 다를 수 있고, 원본 trajectory 전체에 대한 dual feasibility가 아직 확인되지 않았기 때문이다.

RMP coupling dual로 가격을 갱신하면 exact local lower certificate β_u를 다시 계산한다. convexity dual을 η_u라 할 때 모든 차량에서 exact `β_u − η_u ≥ 0`이면 해당 원본 정수 local domain의 모든 missing columns가 negative reduced cost를 갖지 않는다는 충분조건이 성립한다. 이 조건의 검사는 저장된 원본 coupling 계수와 모든 local domain을 대상으로 한다.

한 차량이라도 lower bound가 음수이면 closure는 `NOT_PROVEN`이다. 음수 **하한**은 실제 negative column의 존재를 증명하지 않는다. 반대로 MILP가 TIME_LIMIT이어도 별도 exact LP lower certificate가 모든 차량에서 위 조건을 만족할 수는 있다. RMP primal 최적성, NONUNIT dual/residual, full original Global LB는 추가로 확인해야 하며 closure PASS만으로 native RMP objective를 인증하지 않는다.

이번 pilot은 branch-and-price 또는 반복 column generation의 완결 구현이 아니다. `pricing_closure=false`와 `integer_block_strengthening=NOT_PROVEN`을 수치 근거 없이 바꾸지 않는다.

## 5. dual 안정화와 자원·dominance 제한

안정화는 검증된 signed 가격을 중심으로 다음 가격을 선택하는 탐색 도구다. 예를 들어 exact rational α∈[0,1]의 convex mixing은 같은 inequality sign을 보존하지만 새 가격의 LB 개선은 별도 재검사가 필요하다. penalty·box·trust region 값을 원본 `min rho_max` 목적함수에 더하거나 원본 물리 제약으로 넣지 않는다. 가격 버전, exact coefficients, Native 반올림, candidate lower certificate를 각각 남긴다. 안정화가 이 사례의 속도나 5% Gap을 보장하지 않는다.

현재 pilot은 arc 삭제, SOC discretization, P/Q 대표점, SOS 변환, top-k route 제한을 적용하지 않는다. future resource oracle에서 안전 dominance를 쓰려면 제거되는 label의 **모든** 가능한 연장에 대해 살아남는 label에 같은 원본 물리 feasible continuation이 있고 exact 가격 비용이 더 크지 않다는 inclusion/extension 정리가 필요하다. label 상태에는 차량·지점·시간·접속·mode, SOC 자원, terminal SOC 도달 조건, 연속 P/Q feasible region을 포함해야 한다.

SOC가 높다는 이유만으로 낮은 SOC label을 제거하는 규칙은 여기서 정당화되지 않았다. 충전과 방전으로 SOC가 양방향 변하고 상한·terminal 조건과 P/Q 가격이 있기 때문이다. SOC bucket, epsilon rounding, 용량 합계, 미래 이동만을 고려한 dominance는 `NOT_IMPLEMENTED/NOT_PROVEN`이다.

미래 경로 lower bound를 사용한 pruning도 남은 모든 연장 경로에 유효한 exact lower certificate와 유효 local column의 exact 가격 비용을 비교해야 한다. 가격별로 조건이 달라지므로 이전 λ에서 제거한 arc를 다음 λ에서도 자동 제거하지 않는다. UB 휴리스틱용 catalog 축소와 전역 pricing oracle의 원본 domain 보존을 구분한다. 이 pilot에서 새로운 pruning rule을 도입하지 않는다.

원 논문과 이 사례에 대한 적용 판단은 [LITERATURE_REVIEW_KO.md](D:/MobileESS_v42/docs/v42_m1_fast_hybrid_20261008/LITERATURE_REVIEW_KO.md)에 분리되어 있다. 문헌의 알고리즘 성능을 이 May01 문제의 성능으로 승계하지 않는다.

## 6. 사전 등록된 시간·종료 계약

[PREREGISTRATION.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/PREREGISTRATION.json)이 이번 실행 계획의 authority다.

- UB A/B/C 각각 Native 400초: 합계 1,200초.
- 최초 pricing: 4 local MILP 각각 120초 및 4 local LP 각각 90초: 합계 840초.
- RMP 1회 Native 30초.
- 조건부 RMP-price 후속 LP: finite original-row RMP Pi가 있고 호출 전 Wall<4,800초이면 4×60초. 이 한 번의 후속 가격화 이외에 반복을 추가하지 않는다.
- 최대 요청 Native 2,310초, pilot 회계 상한 2,700초, 원래 단계 Native 누적 상한 5,400초.
- 실제 Wall 속도 목표 3,600초, 실용성 상한 5,400초. Native Runtime과 model build·validation·정확 산술·파일 저장 비용을 따로 보고한다.
- Threads=1, 기존 scientific tolerance 유지. inner Native MIPGap=0.5%와 M1/M2 research Global Gap 목표 5%를 구분한다. A1/A2의 기존 목표는 0.5%다.
- MemLimit/SoftMemLimit, 메모리 자동 종료, 과거 예산 reset, 예산 이전·미사용 예산 소진 반복은 없다. 각 Native 호출은 등록된 TimeLimit에서 자연 종료한다.

실행 중 source hash, callback, 모델, 계획은 고정이다. 증거 누락 또는 검증 실패를 발견하면 실패 내용을 기록하며 이미 실행 중인 다른 연구를 수정·중단하거나 결과를 수리하지 않는다. 다음 구현 변경은 별도 완료 HEAD와 새 ledger를 가진 새 bounded experiment로 다룬다.

## 7. 자연 종료 후 읽기 전용 진단

첫 검사는 [EXECUTED_SOURCE_HASHES.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/EXECUTED_SOURCE_HASHES.json), [NATIVE_RUNTIME_LEDGER.json](D:/MobileESS_v42/runtime/v42_m1_fast_hybrid/hybrid_may01_20261008_5pct_pilot01/NATIVE_RUNTIME_LEDGER.json), decomposition의 original CSR/domain/axes identity다. 성공 여부와 무관하게 신규 call 수, Native Runtime/Work, wall, presolve 관측의 한계, memory 진단, source drift 여부를 남긴다. solver의 rounded presolve 시간은 exact 비용 분해가 아니며 Native Runtime에 포함된다.

pricing의 각 차량에 대해 다음 evidence를 확인한다.

| 대상 | 필요한 증거 | 없을 때 판정 |
|---|---|---|
| MILP column | RAW local NPZ와 original_columns, SHA, local/FULL literal integer gate, 원본 물리 replay | column 미수용, Global UB 주장 금지 |
| LP multiplier | RAW Pi와 checked signed Pi, original_rows/columns, Native rounded objective, SHA | 기존 exact seed fallback; 새 dual gain 미인증 |
| source price | full original rational dual, 모든 coupling λ/sense/row axes, exact price와 full objective residual | 가격 provenance 또는 bound 재현 `NOT_PROVEN` |
| 전역 LB | selected 4-unit dual + 원본 NONUNIT dual + coupling exact 합성, independent original-CSR checker | native 수치를 exact LB로 대체하지 않음 |
| RMP closure | finite 원본 행 Pi, η, 모든 β−η의 exact checker 결과 | closure `NOT_PROVEN` |
| 전역 UB | 전체 RAW C3A/FULL integer·물리 replay, original objective 동일성, frozen 입력 identity | incumbent 진단값만 기록 |

physical bottleneck은 실제 실패 행·변수, 경로/접속/SOC/PCS 위반, exact/observed residual과 적용 tolerance를 확보한 경우에만 말한다. no incumbent, TIME_LIMIT, presolve 비용, no Pi는 물리 불가능성의 증거가 아니다. 한 local column의 실패는 전체 원본 물리 문제의 infeasibility도 증명하지 않는다. accepted 후보의 active thermal/voltage/transformer 행은 그 한 점의 병목 진단이며 모든 가능한 운전의 전역 하한은 아니다.

## 8. 다음 bounded experiment 결정 순서

1. **same-case/source/integer/physical identity가 실패한 경우:** bound·UB gain 주장을 중지하고 실패한 불변조건을 좁힌다. 새 Native 호출을 시작하지 않고 optimize=0 재현과 독립 검증부터 수행한다.
2. **exact Global Gap≤5%인 경우:** RAW UB와 exact LB를 독립 checker로 확정하고 Native/Wall 기준을 함께 보고한다. research gap 판정만 확정하며 P2 및 `M1_ACCEPTED`를 자동 변경하지 않는다.
3. **유효 UB가 좋아졌으나 5%에 못 미친 경우:** 필요한 LB/UB 임계값을 새 exact pair로 다시 계산한다. 실제 accepted trajectory·dispatch 변화와 active grid 행으로 다음 하나의 bounded UB neighborhood를 설계하고 별도 ledger에서 사전 등록한다. 이번 ledger를 재개하거나 예산을 옮기지 않는다.
4. **local LP dual이 좋아진 경우:** compact LP 대비 값과 source dual residual 손실을 구분한다. 원본 전체 dual certificate 개선이면 먼저 그 개선을 보존한다. 이를 정수 hull 강화라고 이름 붙이지 않는다.
5. **새 pricing column은 있으나 물리/literal gate를 통과하지 못한 경우:** RAW를 보존하고 실패를 보고한다. soft integer 반올림이나 경로 수리로 certificate gate를 우회하지 않는다. 별도의 원본 model 구현 검증 또는 새로운 UB 실험을 사전 등록한다.
6. **RMP와 LP certificate만으로 closure/Gap이 불충분한 경우:** 필요한 β−η 개선량과 부족한 unit을 exact 값으로 기록한다. 다음 실험은 완전 local-domain lower proof의 구현·검증 가능성을 먼저 검토한다. exact interval/rational leaf certificate를 가진 bounded integer-pricing proof 또는 inclusion/extension theorem이 검증된 resource oracle을 준비할 수 있으나, 현재 미구현 방법의 성공을 전제하지 않는다.
7. **source seed 대비 아무 유효 개선이 없는 경우:** finite `NOT_PROVEN` 결과로 종료한다. 동일 scalar/count/hull 방향, 실패 solver, 미사용 예산 소진 반복, 5월 전체 캠페인으로 확대하지 않는다. 과학적으로 다른 한 후보가 준비되었을 때만 새 계획을 작성한다.

## 9. acceptance와 최종 handoff

이 연구는 P1-only/M1 gap 실험이다. P2 certificate는 `null`, `M1_ACCEPTED=false`를 유지한다. P1-only Accepted와 기존 four-objective `A1_ACCEPTED`를 혼동하지 않고, 실행하지 않은 P2 또는 다른 단계의 최적화·인증을 생성하지 않는다. 5% 연구 목표 달성만으로 Planning Freeze/Actual/Fresh AC/Validation 전체 pipeline 완료를 주장하지 않는다.

최종 handoff에는 완료된 정확한 `v42` HEAD, source/case/input SHA, 등록 call 전체와 실제 Runtime, independent LB/UB/Gap, selected trajectory와 원본 물리 replay, pricing closure의 별도 판정, 연구 Wall 기준, 미해결 정수성·P2 상태를 담는다. 진행 중 M 연구의 미완료 파일은 이 결과의 authority가 아니다. 그 연구가 끝난 뒤 마지막 완료 HEAD 이후의 검증된 신규 변경분만 파일·proof·tests 단위로 검토하며, 기존 frozen authority와 과거 Git/예산 기록을 보존한다.
