# M1 공동 fleet/time/grid 정식화 결과

**JOINT_FORMULATION_TRACTABILITY_FAIL**. 최종 유효 LB **0.5687116104049206**, UB **0.6306505800203936**, 전역 gap **9.821440204%**. 0.5% 목표 달성: **False**. 선택: `ORIGINAL_C3A_RETAINED`.

## 목적함수와 정수 domain

PR179 exact HEAD `f6d48e8892e1d36023f107130c2c9bfdfa5d4ebe`에 적층한다. 원본 PR162 C3A의 582808행·306040열·5351612 nnz 및 9322 binary domain을 유지한다. 목적함수는 정확히 `minimize rho_max`, ObjCon +0. 원본 계수·ObjCon·변수 축을 Git blob에서 독립 대조했으며 objective hash는 `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`다. 추가 변수는 continuous이고 목적계수는 +0. ROOT 비교에서는 원본 binary만 LP relaxation으로 푼다. 원본 full-horizon MILP projection은 바뀌지 않는다.

## 새 표현과 유효성

창은 archived ROOT의 grid dual 지지와 node_activity fractionality를 이용해 76–79로 골랐다. 후보 A는 MESS03/MESS02의 IDC01 activity 8개의 **총합** 0..8을 아홉 disjunctive term으로 분해한다. 원본 창의 flow/energy/SOC/PQ/PCS/전기 binding/critical grid 행과 모든 유한 경계를 각 term에 복제한다. 81개 slot별 word 표현은 추가 열 1199286개여서 실행 전에 크기 한계를 넘었으며, 이 실패 설계도 보존했다. A는 slot별 count hull이나 완전한 fleet integer hull이 아니다.

후보 B는 같은 네 슬롯의 MESS01..04를 포함한다. 각 unit의 첫 slot mode 및 grid dual 지지가 가장 큰 slot의 IDC01 activity, 총 8 selectors의 Boolean product를 원본 physics/grid 행과 곱한다. b 및 1-b perspective bounds, squared-b identity와 모든 selected cross-unit/time product symmetry를 함께 둔다. A와 다른 RLT 표현이며 전체 binary-word hull을 주장하지 않는다.

임의의 원본 정수 feasible x에서 A는 실제 aggregate count term의 λ=1, y=x를 선택하고 나머지는 0으로 둔다. B는 y=b*x로 lift한다. 모든 새 행을 만족하며, inverse는 추가 변수를 버리는 것이다. 전체 원본 행/경계/type을 남겨 두었으므로 원본 정수 projection은 정확히 같다. boundary SOC와 outside-window route 열은 실제 source row의 nonzero를 모두 복사하고 관측 trajectory로 고정하지 않는다. 독립 verifier가 모든 실제 새 행의 계수·RHS·경계를 정확한 Fraction 산술로 대조했다. 일반 96-slot 증명은 `VALIDITY_PROOF_KO.md`, compiled 행별 인증은 `A_EXACTNESS_VERIFICATION.json` 및 B 파일에 있다.

## Dual 인증 복구: optimize 0

48935 linked equality rows와 274743 columns의 stationarity를 joint weighted LSMR로 보정했다. PCS inequality multiplier는 유지했다. 이는 인증 복구이며 genuine LP strengthening이 아니다. 경계 reduced cost를 모두 0으로 보내는 첫 시도는 하한을 크게 악화했다. 경계에서는 native RC를 보존하고 interior만 0을 목표로 둔 두 번째 시도도 inherited LB를 넘지 못했다. 이유는 least-squares residual 최소화가 bounded-Lagrangian 값을 최대화하지 않고, 경계에서의 RC는 일반적으로 실제 비용이기 때문이다.

|Archived node|Native objective|Exact LB before|Exact LB after|전역 사용|
|---|---:|---:|---:|---|
|0|0.568711942993|0.567137476141|0.558884389961|global domain; 개선 없음|
|20|0.569079225096|0.568010353735|0.566716267902|자식 fixing domain; 전역 사용 금지|
|52|0.568821771742|0.564524855227|0.529593388380|자식 fixing domain; 전역 사용 금지|

두 correction의 원본 receipt/Pi NPZ를 모두 보존했다. 첫 실패 폴더의 source snapshot은 patch 후 복사되어 첫 실행 source와 동일하지 않음을 `SNAPSHOT_PROVENANCE.json`에 명시했다. ROOT의 injection_P/Q 최대 stationarity 잔차는 약 7.3e-11/2.4e-9지만 넓은 경계가 이를 증폭한다. PQ/SOC의 일부 RC는 실제 bound activity를 나타낸다. 원래 LP의 native 목적값 자체도 약 0.568712라서 인증만 완전히 회복해도 필요한 0.6274973에 도달하지 못한다.

## 독립 bounded exactness

2 MESS·4 slots·2 sites의 유리수 time-DAG fixture에서 route/mode 상태 1024개를 전수 열거했다. 256개는 원본과 A/B의 feasibility 및 최적값이 정확히 같다. 768개는 travel energy 및 terminal SOC의 명시적 모순으로 infeasible이다. 모든 feasible 해의 forward/inverse lifting, 정확한 primal/dual 및 EF optimum equality를 인증했다. 잘못된 물리 계수, 임의 perspective bound, 누락된 disjunction word도 거부했다. 완료된 검증은 작은 HiGHS LP 1027회이며 Gurobi optimize는 0회다. 실제 C3A를 축소한 수치 데이터라고 주장하지 않으며, 원본 96-slot 주장은 일반 증명과 실제 compiled verifier가 따로 담당한다.

작은 unconditioned B LP에서 개별 Pi의 분수 복원은 2.60098e-5 인증 손실을 냈고 strict equality 검사가 거부했다. 원본의 정확한 dual을 새 행에 0으로 확장한 하한과 exact feasible EF primal이 모두 7/16이므로 ambiguity 없이 optimum을 인증했다. tolerance를 완화하지 않았다. 원본 UB full C3A/route/SOC/PQ/PCS/grid/A1 및 모든 강화 행 replay는 PASS, raw row 최대 위반 5.80e-10, bound 2.16e-10, integrality 0이다.

## Paired ROOT 결과

각 모형은 fresh native optimize 정확히 한 번, TimeLimit=600s, Threads=1, Method=2, Crossover=0, BarConvTol=1e-8, 원본 feasibility/optimality/integrality tol=1e-8 및 나머지 동일 설정을 사용했다. ONCE marker, native log, 모든 barrier event와 native input transport 검증을 저장했다. Exact LB는 전체 unchanged matrix/finite bounds와 sign-corrected Pi의 dyadic bounded-Lagrangian 계산을 독립 재계산한 값이다. native objective/ObjBound를 새 global LB로 승격하지 않았다.

|모형|행 / 열 / nnz|상태|Runtime s / Work|Native objective|Exact LB|인증 손실|Fractional B|Peak RSS GiB|
|---|---|---|---:|---:|---:|---:|---:|---:|
|ORIGINAL|582808 / 306040 / 5351612|OPTIMAL|511.570 / 481.275|0.568711942993|0.567137476141|0.001574466853|7454|2.165|
|A|895739 / 439294 / 6266920|TIME_LIMIT|604.806 / 586.253|N/A|N/A|N/A|N/A|2.750|
|B|1584196 / 531992 / 8072052|TIME_LIMIT|601.177 / 413.842|N/A|N/A|N/A|N/A|4.082|

A unresolved point의 raw rho=0.576890161566, fractional original binaries=9322, original relaxed replay PASS=True, strengthened relaxed replay PASS=False. 이는 최적 목적값·LB·정수 UB가 아니며 채택하지 않았다.

A의 설정 한도는 정확히 600초다. 초과 실측 시간 4.806초는 solver의 iteration 중단·반환 시점에 생겼다. 한도 증액이나 재실행은 없었다.

B unresolved point의 raw rho=0.576420619326, fractional original binaries=9322, original relaxed replay PASS=False, strengthened relaxed replay PASS=False. 이는 최적 목적값·LB·정수 UB가 아니며 채택하지 않았다.

B의 설정 한도는 정확히 600초다. 초과 실측 시간 1.177초는 solver의 iteration 중단·반환 시점에 생겼다. 한도 증액이나 재실행은 없었다.

|후보|Paired certified ΔLB|Inherited/baseline 최선 대비|Native objective 증가|Material gate|
|---|---:|---:|---:|---|
|A|N/A|N/A|N/A|False|
|B|N/A|N/A|N/A|False|

Gate는 사전 등록대로 fresh original exact LB와 inherited valid LB 중 더 큰 값을 candidate exact LB가 0.001 이상 넘어야 한다. 요청의 paired certified ΔLB도 별도로 보고한다. 이 보수적 gate는 인증 손실을 baseline의 약함으로 숨기지 않는다. raw LP primal은 original tolerance replay와 따로 보고하며, 실패하더라도 sign-correct exact dual이 보장하는 하한과 정수 UB를 혼동하지 않는다. baseline의 raw native ObjBound는 약 -97.9922로 반환됐으며 새 LB에 사용하지 않았다. OPTIMAL label과 native objective도 수치 인증을 대신하지 않는다.

## 비용과 fractional grid support

ORIGINAL: setup 2.072s, optimize+certificate 전체 wall 526.829s, barrier iterations 112. Factor memory 로그:  AA' NZ     : 3.785e+07;  Factor NZ  : 5.717e+07 (roughly 700 MB of memory);  Factor Ops : 3.116e+10 (roughly 2 seconds per iteration). Numerical warnings: Warning: Model contains large matrix coefficient range.

A: setup 4.171s, optimize+certificate 전체 wall 609.610s, barrier iterations 80. Factor memory 로그:  AA' NZ     : 4.664e+07;  Factor NZ  : 9.162e+07 (roughly 1.2 GB of memory);  Factor Ops : 9.249e+10 (roughly 5 seconds per iteration). Numerical warnings: Warning: Model contains large matrix coefficient range.

B: setup 7.015s, optimize+certificate 전체 wall 609.219s, barrier iterations 32. Factor memory 로그:  AA' NZ     : 7.348e+07;  Factor NZ  : 1.690e+08 (roughly 2.0 GB of memory);  Factor Ops : 2.055e+11 (roughly 12 seconds per iteration). Numerical warnings: Warning: Model contains large matrix coefficient range.

`CRITICAL_GRID_ROW_COMPARISON.csv`는 원본 critical row ID의 sense-correct slack/Pi를 비교한다. `CRITICAL_WINDOW_FRACTIONAL_SUPPORT.csv`는 unit/site/retained-slot의 Pch/Pdis/Q와 node/mode fractionality, `CRITICAL_GRID_NONZERO_CONTRIBUTIONS.csv`는 실제 원본 row coefficient 기여를 보존한다. frozen C3A generic row 이름에는 물리 line ID가 없으며 retained-variable slot은 alias representative일 수 있다. 따라서 물리 line/time 식별자를 추측해 만들지 않았다. incomplete root의 unresolved point는 certificate/UB로 사용하지 않는다.

실제 조건부 source 범위는 A 3514행/14805열, B 6806행/28243열이다. 원본의 rho를 직접 포함하는 행은 324871개이며 각 후보의 source에는 그중 두 thermal 행만 있다. 7 upper-voltage, 1 lower-voltage, 4 transformer 행은 rho에 대한 효과가 원본 전기 binding을 통해 전파된다. 새 continuous 변수는 A 133254개, B 225952개이고 모두 objective 0이다. `ACTUAL_COUPLING_SCOPE.json`과 `ACTUAL_BOUNDARY_SOC_ENERGY_ROWS.json`에 실제 coupling과 boundary energy 식을 보존했다. 이 제한된 블록은 전체 joint integer hull을 표현하지 않는다.

## 알고리즘 선택과 중단

두 후보 모두 등록된 ROOT 예산 안에서 요구된 인증 gain을 입증하지 못했다. 추가 계산 비용의 production 이점을 확인하지 못해 원본 C3A를 유지한다.

Canary executed: False, optimize calls: 0. native 총 호출 3. old tree, A-stage, M2/P2/May 실행은 0이다.

인증된 material gain gate를 통과하지 않아 900초 MIP canary를 실행하지 않았다. 원본 정수 projection exactness와 LP strength/practicality는 별개다. 9-term aggregate는 시간별 mode/location의 joint integrality 정보를 많이 남기고, 81/625-term 상세 count는 크기가 폭증한다. 선택 RLT는 더 많은 결합을 강제하지만 예산 내 종료·유효 gain이 입증돼야 production으로 채택할 수 있다.

두 강화 LP의 최적값과 certified Delta는 미확정이다. 이번 실험이 입증한 병목은 추가 fill/factor 비용과 예산 내 ROOT 종료 실패다. A에서는 barrier 목적값·잔차가 크게 악화되는 구간을 관측했으나 solver가 explicit numerical-trouble 경고를 출력하지는 않았다. bounded fixture 검증은 실제 C3A 데이터의 축소 실험이 아니므로 물리 숫자에 대한 일반화 한계도 있다. 96-slot exactness의 근거는 compiled 계수 검증과 전체 정수 projection 증명이다.

새 global LB gain 0, UB gain 0. 0.5% gap에는 현재 UB에서 LB ≥ 0.6274973271203가 필요하다. 이번 작업은 production 성공이나 0.5% 달성을 주장하지 않는다.

다음 권고 한 가지: 추가 solve 전에, 저장된 원본 OPTIMAL ROOT point/dual·강화모형의 미완료 point·원본 행렬만 사용해 critical joint block의 fractional support를 분리하는 exact valid inequality를 도출하고, 독립 계수·projection 증명 및 arithmetic-only separation 효과를 먼저 확인한다. 이번 작업에서 실행하지 않는다.

## Git와 증거

변경 범위는 `docs/v42_m1_joint_formulation_20261008/`뿐이다. PR179 원본 문서/행렬/old checkpoint는 수정하지 않았다. `.gitattributes`로 새 증거 파일의 raw byte를 보존하고 `SHA256_MANIFEST.json`으로 모든 산출물을 검증한다. 최종 HEAD, Draft PR URL, remote equality와 clean tree는 publication 이후 `GIT_COMPLETION.json` 및 최종 사용자 답변에 기록한다. commit 자신의 hash를 같은 commit 파일에 넣는 순환 참조는 만들지 않는다.
