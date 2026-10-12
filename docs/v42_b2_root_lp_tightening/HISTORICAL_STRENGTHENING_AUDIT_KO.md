# 역사적 강화 후보와 이번 Fractional Grid / SOC 후보의 관계

이 감사는 PR #109/#137/#167/#169/#185/#186/#187의 공식 PR metadata와 고정 commit의 실제 코드·증명을 읽었다. Native Optimize와 FULL 행렬 로드는 0회다. 각 commit, 원문 경로, Git blob SHA256와 공식 링크는 `HISTORICAL_STRENGTHENING_AUDIT.json`에 보존했다. 역사적 하한·UB·계수·분수점은 현재 Source18r의 결과로 재사용하지 않는다.

| PR / 정확한 HEAD | 실제 조사한 강화 | 관측 결과와 한계 |
| --- | --- | --- |
| [109](https://github.com/BeaverVillage/MobileESS/pull/109) / `6dabb39e3ae6bb36c4ac47725c0e11d5bbc1b812` | 연결 인지 Mode hull S1, arc별 에너지 mass를 추가하는 S2, 양자의 S3 | S2의 Root 증가 0.0003630437로 0.001 기준 미달. S1 증가 없음. S3 overall INTERRUPTED와 BarStatus OPTIMAL을 분리하고 S2의 보수적 하한을 사용했다. 수치 crossover 실패와 메모리 비용을 보존했다. |
| [137](https://github.com/BeaverVillage/MobileESS/pull/137) / `94f8a38b7ef7b60cf5d7ffd91c86b109589fcaef` | Aggregate C/D/연결 전력 3개 계열, 정확 interval-union forward/backward SOC 도달성 envelope, arc SOC-flow EF | Mode/연결 cut Δ약 8e−11, SOC envelope Δ약 −1e−10: 수치 변동 수준. SOC-flow는 207,928 연속 열·443,344행을 추가하고 300초 내 완료 LP certificate/Primal을 확보하지 못했다. BASE 유지. |
| [167](https://github.com/BeaverVillage/MobileESS/pull/167) / `0d423626790a1102d42e6ba84beeb5f7d4ab1d4b` | Aggregate charge/discharge/connected 및 local connected power, 저장 PCS16의 양 mode를 접은 `(Pch+Pdis,Q)` hull | 10회 loop의 320행·17,837nnz에도 인증 LB 개선 0. 기존 Root 점의 분수성과 국소 상태 증명이 전체 Gap 원인을 증명하지 않았다. strict raw replay 실패는 별도 보존했다. |
| [169](https://github.com/BeaverVillage/MobileESS/pull/169) / `599d9ea67f6c348bfed9d1a594dc0d1eb3fd2768` | MESS04 69–72의 route/mode/PQ/SOC 전체 국소 joint hull과 MESS03를 포함한 2-block 확장 | 인증 ΔLB=0. 기존 zero-charge-mode incumbent를 개선해 UB는 낮췄지만 남은 Gap의 주된 원인은 확정하지 않았다. 목적함수 없는 mode만 바꾸어 국소 separator를 제거할 수 있다는 관측도 보존했다. |
| [185](https://github.com/BeaverVillage/MobileESS/pull/185) / `6d1d64beaf012d32ddf39245890785e3d8f01d4b` | 전체 96-slot 원래 물리를 유지하고 per-travel-arc SOC 출발/도착 및 travel interval 유효식 검사 | 795,944개 후보 중 저장 점 위반 651행·1,302nnz를 추가했다. 실제 삽입 행은 모두 arrival-SOC reachability였다. 다른 Native 작업 때문에 full Root 효과는 NOT_MEASURED였다. |
| [186](https://github.com/BeaverVillage/MobileESS/pull/186) / `9a1b41260aff3bc70d2e36d7e1c293c03ea114de` | May12 A-stage Phase-I / P1 exact recovery | Mode/PCS/Reachability 강화 실패 후보가 아니다. Artificial-free original-point activation과 pricing closure의 A-stage 연구다. 따라서 SOC cut의 실패 이력으로 잘못 분류하거나 현재 B2 하한으로 재사용하지 않는다. |
| [187](https://github.com/BeaverVillage/MobileESS/pull/187) / `e67ecfa827e4262c2f2df17c226d6442656af18b` | PR185의 651개 Route–SOC 행을 더한 B2 LP 단일 실행 | Native 목적값 증가 약 0.000001947. strict original row replay는 약 6.398e−8로 FAIL. sign-valid multiplier의 exact finite-box LB는 이전 LB보다 약해 누적 인증 개선 0이었다. injection_P/Q stationarity correction 손실이 수치 인증의 주요 진단 항목이었다. |

## 1. 단순 Mode/PCS cut을 새 방법으로 재제출하지 않음

PR137의 실제 `v42_strengthening/cuts.py`는 다음 세 행을 삽입한다.

- `C ≤ Pmax z`
- `D ≤ Pmax(1−z)`
- `C+D ≤ Pmax Σ_s stay_s`

PR167은 이 계열과 site별 `Pch+Pdis ≤ Pmax stay_s`, 그리고 folded PCS plane `α(Pch+Pdis)+βQ≤γstay_s`를 검증했다. 이번 후보 B는 이들을 다시 생성하지 않는다. Q/PCS 다면체를 접거나 Mode를 정수화하는 대신, 원래 SOC 전후 경계와 출발 에너지, 전체 사이트의 C/D를 결합한 두 명시적 행만 조사한다.

PR109 S1에는 `z≤Σstay`도 있다. 원문은 미연결 transit에서 unused mode를 0으로 canonicalize하면 route/PQ/SOC의 물리 projection은 같지만 **원본 unused mode-bit assignment는 제거될 수 있다**고 명시한다. 이번 요청은 원본 정수 가능점 전체를 보존하므로 이 행을 재사용하지 않는다. 후보 B는 충전이 없는 transit에서 mode가 0이든 1이든 유효해야 한다.

## 2. SOC 후보는 기존 물리 논리의 작은 명시적 사영

PR137의 SOC envelope는 경로 상태별 forward/backward 도달 SOC 구간을 계산해 시간 경계 SOC를 상태 질량의 가중 하한/상한으로 제한한다. PR185/187의 travel 강화는 각 개별 arc a의 출발·연결 도착 SOC와 원래 에너지 e를 결합한다. `D_a=E_connect−E_depart+e`의 big-M disjunction과 per-arc endpoint reachability가 실제 코드·증명에 있다.

이번 B는 동일한 원래 물리 사실을 사용하지만 행은 다음과 같다.

- `E_t ≥ E_min + β Σ_s Pdis_s + Σ_{a:depart=t} e_a f_a`
- `E_t ≤ E_max − α Σ_s Pch_s`

여기서 α와 β는 다시 계산한 이상적 효율 값이 아니라 **현재 Source18r FULL energy 행의 저장 binary64 계수**다. 각 원본 SOC/route 열과 Compact alias를 실제로 확인해야 한다. 전체 후보 768행을 자동 삽입하지 않고 현재 검증된 BASE 분수점이 실제로 위반하는 최대 32행만 고려한다.

PR167의 국소 상태 증명에는 이미 양 SOC 경계·mode·출발 에너지의 한 슬롯 물리가 있고, PR169의 joint hull에는 여러 슬롯 SOC/mode/travel 결합이 있다. 따라서 B를 새로운 물리 정리나 최초의 SOC–Mode–Travel 방법이라고 주장하지 않는다. **현재 K48에 아직 없는 작은 명시적 사영 행을 현재 실제 분수점에서 재검증하는 제한된 실험**이다. 대규모 EF 또는 과거 전체 window hull을 다시 구현하지 않는다.

## 3. B의 정수 유효성 논리와 정확한 범위

Source18r `v42_native/mess.py`에서 Pch/Pdis는 해당 slot의 STAY arc에만 접속한다. 이진 단위 경로는 하나의 시간 DAG 경로이며 이동 arc는 depart부터 connect까지 사이트 노드를 건너뛴다. 출발 에너지는 원래 `E[t+1]`에 한 번 차감된다. 한 차량이 충전 STAY를 선택하면 같은 depart slot의 travel arc를 동시에 선택할 수 없다.

원본 정수점에서 `C>0`이면 STAY가 선택되고 Mode 배타성으로 `D=0`, 유일 경로로 `T=0`이다. 에너지 식은 `E_next=E+αC`가 된다. `E_next≤E_max`가 충전 저장공간 B2를 증명하고, B1은 원래 `E≥E_min`으로 축약된다.

`C=0`이면 `E_next=E−βD−T`이고, `E_next≥E_min`이 방전·이동 가용성 B1을 증명한다. B2는 원래 `E≤E_max`로 축약된다. 이 두 경우는 unused transit mode-bit도 포함해 모든 원래 정수점에 적용된다. 원래 최소/최대 SOC, 효율, departure debit, route와 접속·Mode 행이 정확히 같은지 확인하지 않고 이 증명을 다른 Source에 적용하지 않는다.

이 행이 **모든 원본 LP 점에 이미 함의된다고 가정하지 않는다**. 분수 Mode/Location에서 C, D 또는 travel 질량을 섞으면 원래 에너지 식의 상쇄항이 단순 경계에 허용될 수 있다. 또한 분수점 위반이 있다는 사실만으로 LP 목적값 개선이 증명되지 않는다. 대체 LP 최적점이 새 행을 만족할 수 있다.

## 4. 후보 A의 신규 실험 축과 재사용 범위

PR211과 이번 A 모두 원본 Security 행을 정확히 소거하고 보수적 외향 binary64로 전달한다. 행 자체는 새 물리 제약이 아니다. 차이는 Separation 입력이다. PR211은 축소 Joint의 **정수 incumbent**를 사용했고, 이번 A는 같은 K48의 Binary만 C로 완화한 BASE가 numerical OPTIMAL로 종료해 독립 Primal/Dual/Bounds/행 잔차 검사를 통과한 **실제 분수 벡터**만 사용한다.

진행 중 Barrier나 simplex 목적값, Root IntInf만으로 분수 벡터를 추정하지 않는다. 원본 FULL helper를 복원하는 동안에도 점의 route/Mode/Node 값을 반올림하지 않는다. Family 내부의 실제 분수 위반량을 1차 순위로 하고 저장 원본 계수의 P/Q 민감도 상한을 tie-break로 기록한다. 서로 다른 물리 단위를 섞어 순위 비교하지 않는다. 민감도는 선택 진단이며 원본 계수를 대체하지 않는다.

기존 K48, Bounds, Objective, Binary를 보존하고 실제 원본 행 최대 16개만 추가한다. 원본 정수 사영 포함관계는 유지하지만, 목적값 상승·인증 하한·Runtime·메모리의 채택 판단은 현재 BASE/GRID의 완료 결과를 비교한 뒤에만 한다. 과거 정수 incumbent 위반 행이나 과거 Root 하한은 이번 분수 실험의 성과로 재사용하지 않는다.

## 5. 역사적 수치 인증 실패에서 유지할 원칙

PR187의 raw LP 목적값 증가는 exact finite-box 인증의 개선이 아니었다. 이번에도 Gurobi numerical OPTIMAL, 검증된 Primal 목적값, exact sign-valid multiplier와 모든 finite Bound를 포함한 보정 하한, exact LP optimum의 일치 증명 여부를 구분한다. 원본 MIP `ObjBound`와 새 LP 목적값을 같은 인증 수준으로 비교하지 않는다.

BASE 분수점을 유효하게 확보하지 못하면 A/SOC Native를 실행하지 않는다. Cut Native0 실패, 실제 분수 위반 없음, 또는 LP에서 이미 함의되는 행은 해당 후보를 생략한다. B1 캠페인은 우선이며 B1 Heavy Solver의 실행 종료·안전 자원 허가를 실제로 확인하기 전에는 B2 Heavy Native와 FULL CSR 중복 상주 작업을 시작하지 않는다. B1 PR212의 소스·Worker·Ledger·FAIL/PASS를 수정하거나 중지하지 않는다.
