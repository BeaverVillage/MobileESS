# PR230 Phase I 수치 정책·Global Gap 제어 복구

현재 May01 **첫 제한 Phase I LP(S0)** 에서 FAST B가 111.157초에 Optimal/Phi=0, 원본 Primal/Dual/KKT 검증을 통과했다. 같은 행렬의 EXECUTION07 기존 설정은 958.055초였다. Native는 **88.398% 감소**했다. 전체 Phase I의 원본 생략 행 종료, P1 전체 Pricing, 정수 UB, Actual96/Fresh96의 완료를 뜻하지 않는다. 캠페인은 사용자 중단 상태를 유지한다.

## 실측과 과거 결과의 구분

| 현재 May01 동일 S0 행렬 | Presolve | Feasibility/Optimality | NumericFocus | Native 초 | 결과 |
|---|---:|---:|---:|---:|---|
| FAST A 초기 | -1 | 1e-6 | 0 | 30.087 | TimeLimit, 원본 X/Pi/RC 미확보 |
| FAST B 초기 | -1 | 1e-8 | 1 | 30.075 | TimeLimit, 미인증 |
| ACCURATE C 초기 | -1 | 1e-9 | 3 | 30.658 | TimeLimit, 미인증 |
| CURRENT 초기 | 0 | 1e-9 | 3 | 43.693 | 요청 30초, 실제 overshoot 포함해 원장 기록 |
| FAST A, ScaleFlag=-1 | -1 | 1e-6 | 0 | 25.537 | 잔여 진단 cap에서 TimeLimit; 속도 순위 확정에 사용하지 않음 |
| FAST A 확장 | -1 | 1e-6 | 0 | 180.105 | TimeLimit; 이 행렬에서는 채택 안 함 |
| **FAST B 확장** | **-1** | **1e-8** | **1** | **111.157** | **Optimal, 정확 Phi=0, 원본 검증 PASS** |
| E07 CURRENT 기확보 Raw | 0 | 1e-9 | 3 | 958.055 | 동일 snapshot, Optimal/Phi=0; 생략 원본 행은 미종료 |

Method=2, Threads=1, Crossover 원본 기본값을 유지했다. ScaleFlag=2를 기본으로 사용한다. -1 실험은 짧은 진단 범위이며 우월성을 입증하지 못했다. C/CURRENT의 짧은 중단 기록을 완료 시간으로 보고하지 않는다. FAST B/기존 E07 비교는 동일 snapshot의 별도 시점 실측이며 모든 개별 파라미터의 기여도를 분리하는 factorial sweep은 하지 않았다.

현재 원본 S0는 **275,969행 / 215,725열 / 1,799,788 NNZ**, snapshot `8c857d23a3c371432db5d0c5518c66798d8591cb793ab19374b276a238633c35`이다. FAST B 자동 Presolve 후 **163,507행 / 112,996열 / 1,023,285 NNZ**, Presolve 0.43초, Barrier 27회다. Barrier 후 Crossover 및 uncrush의 추가 simplex 772회도 최종 111.157초에 포함한다. 중첩 시간을 합산하지 않는다.

FAST B 원본 CSR Replay 최대 행 위반은 **1.1482370609883219e-11**, Bound 위반 **1.6024733623387633e-12**, Dual 재구성 오차·sign·Bound RC·보완성 위반은 0이다. 가공하지 않은 Raw X/Pi/RC와 정확 Fraction Phi=0을 재계산했다. `1e-5`는 진단 비교만 했으며 채택 기준은 **원래의 1e-6 그대로**다.

진단 종료 후 RSS/Commit과 Barrier factor의 메모리 추정은 CSV/로그에 보존한다. 이 진단 프로세스의 실제 Peak RSS는 별도 수집하지 않아 **NOT_RECORDED**다. 메모리 기록만을 위해 동일 LP를 다시 최적화하지 않았다. Production 호출에는 앞으로 process Peak RSS/private Commit 및 RAM/system Commit을 기록한다.

## Source18r과 달라진 원인

사용자가 지정한 Source18r 기준은 1,499 Job/117 Class, Native 2.037초, Presolved 3,018행/51,957열이며 **Phi=0 이후 원본 잔차 7.63e-6 FAIL**이다. 이 실패를 PASS로 바꾸거나 현재 Case의 결과로 이전하지 않았다. 이번 현재 입력은 1,555 Job/229 수학적 Class이며 UID Authority와 수학적 Class를 분리한 전체 local kernel을 보존한다. 단순 Job 증가율이나 총 NNZ만으로 시간 차이를 설명할 수 없다.

추가로 직접 확인한 과거 native90 May01 S0(별도 snapshot `12b5d9145b3be40c52af977dcfafb4e1e49644b8fe806bacbd5cdf9e5e2620df`, commit `1423be901`)는 15,129행/83,246열, Presolved 3,017행/51,955열, Native 2.088초다. 이것을 사용자 지정 2.037초 시도와 같은 Raw라고 주장하지 않는다. 로그의 Factor NNZ는 240,700, Factor Ops는 약 2.747e7였다. 현재 FAST A 로그의 Factor NNZ는 약 8.178e7, Factor Ops는 약 1.052e11이다. 현재의 더 많은 hard local rows·global 연결 및 계수 범위 확대로 Barrier factor fill과 연산량이 크게 커졌다. 과거 작은 presolved 행 수를 강제하는 모델 축소는 하지 않았다.

현재 계수 범위는 약 `1e-13~3e5`, Bound 최대 약 `2e6`으로, 직접 확인한 과거 로그의 `4e-10~6`, Bound 최대 약 `1e2`와도 다르다. 자동 Presolve 복원은 실제 행렬과 factor를 줄이고, 과도한 고정밀 계산 정책을 검증 기반으로 대체해 111초 결과를 만들었다. 원본 문제·정수 도메인·물리 제약을 줄여 만든 속도 개선이 아니다.

또한 E07 S0의 Phi=0 후 **생략 행 280,182개가 위반**되어 S1로 넘어갔다. S1은 **556,151행 / 497,287열 / 5,652,483 NNZ**로 커졌으며 341.441초에 사용자 중단됐다. 따라서 첫 LP의 Phi=0을 전체 Phase I 완료로 표시하면 안 된다.

## Presolve=0 도입 경위와 검증 기준

과거 commit `40b6f94dc`의 May25 수치 정책은 원본 `-4*x+y` equality의 정확 잔차 **3.814697265625e-6** 때문에 도입됐다. 약 2.9715e10 크기의 항을 복원할 때 발생한 실제 binary64 점의 위반이며 Fraction 평가에서도 같았다. 화면 반올림이나 단순 검증기 오판이 아니었다. 당시 고정밀 Presolve와 Dual Simplex 진단은 실패했고, Presolve=0/Method=2의 원본 행 정책은 잔차 7.1054e-15, Native 1.202초로 통과했다. 이 날짜의 처방이 이후 모든 5월 Phase I에 강제된 것이 이번 정책상 병목이다.

당시도 원본 Replay `1e-6`은 유지됐다. 원본 정수 FULL의 기존 `1e-5` 기준은 다른 검증 경계이며, 이를 Phase I/LB 기준으로 전용하지 않는다. 전압 0.95~1.05 pu, 선로·변압기·GPU·WAN·Deadline·SOC, 11 SVR/7 RegControl은 그대로다.

## 공통 실행 정책

`table_v_phase_policy.py`와 `CurrentNative`가 B1 A1/B3 A1/A2의 31일 공통 DW 경로에 연결된다. 날짜/Class/UID/Pricing/LB 하드코딩은 없다. 각 새 행렬에서 FAST A(30초) → FAST B(180초) → ACCURATE C(300초) → CURRENT(300초)의 서로 다른 수치 정책을 시도하되, Optimal과 원본 Primal/Dual/KKT 검증을 모두 통과해야 다음 DW 계산에 전달한다. 실패 Raw는 정책별 새 디렉터리에 남긴다. 같은 원본 행렬을 정책마다 다시 생성하지 않으며, 동일 snapshot/component/policy의 중복 Native 호출을 차단한다.

Phase I의 새 호출 누적 allowance는 최대 900초, 전체 DW는 현재 A-stage 잔여에서 원본 정수 탐색용 **1,800초를 남긴다**. 모든 호출은 기존 A-stage 5,400초 원장에 실제 Runtime으로 누적된다. 이 내부 배분은 추가 예산이 아니다. 완료하지 못한 Phi/Pricing은 인증하지 않는다. 정확 Phi=0, 생략 원본 행 종료, 전체 Pricing과 rational LB 검증을 유지한다.

OutputFlag=1/LogToConsole=0/정책별 LogFile, Barrier·Simplex의 진단 Phi/Primal/Dual/iteration을 저장한다. 진단 Phi는 인증값과 분리한다. 모니터는 진단 residual, Phase I 반복 및 현재 Case 인증 Bound를 읽는다.

## AIDC 0.5% / MESS 3% 제어

AIDC는 원본 FULL 정수 Branch-and-Bound를 한 번의 유지된 탐색으로 실행한다. FULL 검증한 incumbent만 UB로 인정하고, 전체 Pricing DW LB와 같은 원본 정수 모델의 Native Global Bound를 별도 출처로 보존한다. Native ObjBound/IsMIP/Status/행렬 바인딩은 Runtime과 같은 소유 원장 transaction에 기록한다. 결과 Header만 바꾸거나 다른 Arm/Case/Source/Restricted 모델의 Bound를 가져오면 거부한다. 유효 LB들의 최대값으로 0.5%를 평가하며 callback에서 목표 달성 시 종료한다. 미달이면 같은 B&B가 잔여 예산 안에서 계속된다. 정수 Bound는 수치 Solver 계약이며 exact rational B&B 증명이라고 주장하지 않는다.

MESS는 **FULL seed → 별도 K16/K32/K48 → 잔여 Adaptive Beam–Joint 탐색**으로 협조한다. K 하한을 얻은 뒤 각 FULL 검증 UB 개선에 3%를 평가한다. 원본 Case의 증명 경로는 고정하고 seed/search Raw를 서로 다른 자식 폴더에 보존한다. PR221/222 Global/Moving incumbent, pin_pools, 공동 P/Q admission, 4-MESS/384 Mode, M1→M2 새 FULL 재검증을 유지한다. Restricted Joint ObjBound는 Global LB가 아니다. M 1,800초와 별도 K 300초 원장은 합치지 않는다. LB가 약해 목표를 못 증명하면 FULL-feasible 여부와 별개로 보고한다.

모든 제어 종료는 `GLOBAL_GAP_TARGET_MET`, `NATIVE_BUDGET_EXHAUSTED`, `VALID_SEARCH_SPACE_EXHAUSTED`, `NO_FURTHER_CERTIFIED_IMPROVEMENT`, `NO_FULL_FEASIBLE_SOLUTION`, `IMPLEMENTATION_OR_NUMERICAL_FAILURE` 중 하나다. 현재 후보 생성기의 소진을 전체 원본 route domain 소진이라고 주장하지 않는다.

## B2 준비 병목 및 검증

같은 실제 C2 sparse 입력에서 정확 Presolve를 **162.650초 → 112.279초(약 31.0% 감소)**로 개선했다. dyadic primitive vector 변환만 정확한 계수 byte로 재사용하고 RHS·sense·column axis는 각 행에서 검증한다. pivot support union의 정확 cardinality도 같은 값으로 계산한다. 실제 출력 matrix/domain/alias/row proof/bound proof/pivot cost/round 결정 SHA가 모두 일치했다.

독립 C3A interval cache는 전체 실제 검증과 190,248 interval 값의 bit equality를 통과했으나 **약 442초 → 460초로 개선되지 않았다**. 이 cache와 verifier 변경은 Production에 적용하지 않았다. 기존 독립 C3A 검증을 유지한다. B2 전체 build가 31% 빨라졌다고 확대 보고하지 않는다.

기존 682개 ID 보존 및 전체 회귀 **1,172 PASS**, skip 0, 실제 Native 0. 신규 검증은 수치 실패 fallback/Raw 보존/정수 예산 reserve/정확 zero/Source drift/Gap 목표 조기 종료·지속/Bound 단조성/Stage 혼용·위조 거부/K 실패 시 FULL seed 보존 등을 포함한다. 모니터 Python 8개와 실제 DOM render도 통과했다.

## Native 원장과 미완료 상태

E07 Native **1,299.496000초**, Raw 267개와 이전 원장 byte를 보존했다. 제한 수치 진단 **451.311999초**를 같은 승인 주기의 후속 원장에 carry-forward해 현재 합계 **1,750.807999초**, A1 잔여 **3,649.192000초**다. 사용량을 0으로 만들거나 새 5,400초를 발급하지 않았다. 진단03의 160초 요청 대비 실제 160.050초 등 모든 overshoot도 실제 사용량에 포함했다.

새 Source의 전체 Phase I/P1, 원본 정수 UB, Actual96/Fresh96은 **NOT_RUN**이다. B0 과거 FULL_PASS는 보존하며 새 Release로 승격하지 않는다. B2/B3 및 May02~31 Heavy, 남은 날짜의 대형 Native0 감사는 실행하지 않았다. P2=0, R2 HOLD, Worker1/Threads1이다.

캠페인 재개 전에는 새 Release/Source/Case에 정상 Launch Gate를 다시 묶고 **진단04 원장을 predecessor로 carry-forward**해야 한다. 이전 E07 원장에서 다시 분기하면 진단 소비시간을 누락하므로 금지한다. 현재는 사용자 캠페인 중단을 유지하며, 새 Source로 자동 Heavy 재시작하지 않는다. 최종 Source freeze와 gate 검증은 별도 local receipt에 남긴다. 실측 CSV, 회귀 XML/JSON, 독립 검증 결과, 대형 Raw·로그·원장 SHA manifest를 이 폴더에서 확인할 수 있다.
