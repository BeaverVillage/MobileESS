# V42 B2 May01 대안 Global LB 연구 최종 검토

두 방법의 **인증된 Global LB 개선은0**이다. 기존 K48 `0.46498486997548166`와 현재 Original FULL 재검증 Moving UB `0.5398310226338695`를 보존한다. Global Gap `13.864737209%`,3% 목표 미달이며 M1/M2 통합 후보를 채택하지 않는다. A는 유효하지만 비실질, B는 실제 Root 위반이 없어 신규 Global LB를 계산하지 않았다. NOT_RUN을0이나 K48로 채우지 않았다.

| Algorithm | Valid Global LB | Delta vs K48 | Global Gap (%) | Native seconds | Peak RAM GiB | Verdict |
|---|---:|---:|---:|---:|---:|---|
| K48 Baseline | 0.464984869975 | 0 | 13.8647372085 | 360.082999945 | 1.14043807983 | BASELINE |
| Stabilized Lagrangian | 0.464984869975 | -5.55111512313e-17 | 13.8647372085 | 228.697999954 | 0.44234085083 | REJECT_NONMATERIAL |
| Multi-period Route-SOC | — | — | — | 25.3229999542 | 0.499347686768 | REJECT_NO_CERTIFIED_ROOT_VIOLATION |
| Best Certified Global LB | 0.464984869975 | 0 | 13.8647372085 | 254.020999908 | — | FINAL_BASELINE_PRESERVED |

K48 Native360.083s는 기존 PR211 K32/K48 연구 비용이며 새 비용에 합산하지 않는다. 새 A 228.697999954s + B 25.322999954s = 254.020999908s,22 Native calls, Worker1/Threads1이다. A6 weight evaluations 중 A0 네 Bound는 동일성 검증 후 cached reuse, 실제20 calls; B support2 calls와 strengthened LP0 calls다. 현재 May01 prefix1003.5010001659393s에 새254.02099990844727s를 연결한 유효 누적1257.5220000743866s로1800s 안이다. 상세 정확한 binary64 합은 원장에 있다. May02943.4019999504089s, PR221 별도 명시 승인 fresh 연구1790.1970002651215s는 보존한다. PR221 session을 다시 열거나 사용시간을 초기화하지 않았다. 이번 지시는 PR222 current campaign Case/원장에 대한 추가 연구이므로 해당1003.501s prefix에 이번 사용량을 차감한다. 다른 과거 연구가 같은1800s session이라고 가정해 합산하지 않으며 그 별도 승인 근거는 원본 PR221 ledger의 historical_before_fresh/same_fresh_used다.

## 실제 Source·Case·숫자 권위

PR222 Git HEAD12594e281bb89611331950f11f775a2612d3cb48 위 독립 research worktree다. 실제 original execution Source SHA `e0e1f615d5773bbbe86720fff69811b40a9f65de82cde215106086c1f8ad2375`, physical Source18r Git497609b46faa14ea7e32a9483a333ab32fd264ef, current Case `b6577cefde6d51eb0e0c9d274a6ad8df2dd1e461dfbf934a0696341e87bc9cad`, FULL Matrix `0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec`, named Domain `9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e`, Objective `d8cc60859a138f737c329743dd9919fb7577941a611ea5a3bd42bfdafcd2a1e3`와 연결했다.

과거 Case34c0efff...와 현재 metadata Caseb6577cef...는 같지 않다. 전체 FULL CSR/domain, Dense CSR/domain, 원래 route/battery/고정 AIDC 수치 효과와 current FULL replay의 수치 모델 동일성으로 K48를 연결했다. 다른 Case의 숫자를 임의 이전하지 않았다. 원본 Input/Source packet SHA를 execution Source SHA로 잘못 이름 붙였던 초기 metadata는 후속 Native0에서 정정했고 old packet digest 및 원래 binding은 `TRIAL_ORIGINAL_BINDING.json`에 보존했다. 모델/계수/Bounds/승수/Runtime 변경은0이다.

현재 FULL moving replay는 등록된 incumbent1개 모두 PASS, 정확한 Binary pattern 및 원본 Validator tolerance를 유지했다. MESS03 STA08→IDC06(4/6/7), IDC06→IDC05(64/66/66), IDC05→IDC01(77/79/79), 이동 에너지66.66442632042374kWh; MESS01/02/04는 원래 STA01/STA12/STA06 STAY다. 이 UB/경로는 수정하지 않았다. restricted incumbent를 FULL UB로 승격하지 않았다.

## 논문 질문15개에 대한 답

1. K48 정체의 직접 관측은 PR214 BASE LP objective0.4649848699754816가 PR211 MIP Global Bound와 사실상 같고, 이번 A3도 같은 수치를 재현했다는 것이다. 이번 관측에서 더 많은 B&B 시간의 효과를 보이지 않았다. exact full formulation ceiling이나 전체 hull ceiling은 미증명이다.
2. LP의 네 차량은 원본 DAG의 fractional arc/node 흐름과 fractional charge modes로 여러 site/path를 동시에 표현한다. Mode에 따라 같은 시점 charge/discharge 혼합도 가능하다. 실제 root census는 CSV에 저장했다. 중요한 MESS03은29/30에 약297.455kW 방전,31에300kW 방전하며 SOC675.565→597.225→518.947→440kWh로 내려가고32 이후 분수 recharge/travel 조합을 보인다. 이 패턴 자체를 유일한 gap 원인이라고 단정하지 않는다.
3. Lagrangian은 각 차의 전체96-slot 원래 integer arc/mode 및 SOC/P/Q/PCS/ETA/energy를 하나의 X_m으로 보존한다. 차량을 조각 ESS로 나누거나 route를 고정하지 않는다.
4. 공유 injection 정의는 exact 소거했고 grid voltage/thermal/transformer/shared electrical coupling은 해당 승수로 dualize하거나 생략했다. 원래 electrical row signs/constants를 반영했다.
5. FULL 사영⊆X_1×...×X_4이고 w simplex 및 μg≤0으로 원래 objective 아래의 Lagrangian값을 얻는다. 네 minima의 유효 global lower bound와 exact constant/rounding 보정만 합친다.
6. A0의16개1/16 uniform rows, A1의 두 critical thermal rows, A2의4-slot sparse responses, A3의 추가 voltage/transformer 가격을 비교했다. 마지막 stabilized 후보들은 크게 약했고 best candidate는 A3로 유지됐다. best와 last를 혼동하지 않는다.
7. 핵심은 slot31 line.l10 phaseA facet1 w≈0.8859562083, line.l52 phaseA facet1 w≈0.1140437917이다. 추가 전압 하한 row[31,383] μ≈0.00022899886 및 transformer_kVA[31,212,6] μ≈1.07407414e-7가 A3에서 중요했다. 실제 원본 row/phase/time과 exact prices는 catalog/history에 있다.
8. B는 여러 시간의 signed grid service를 전체96-slot 정수 운전영역에서 support 최대화하므로 ETA/energy/terminal/rebound와 단일 route를 함께 고려한다. 원래 SOC balance 합산이나 기존 single-slot 가용성 행 복제가 아니다.
9. 이번 두 방향에서는 실제 위반을 확인하지 못했다. 아래 certified upper보다 root support가 작아 두 후보 모두 기각했다.
10. 임의 FULL integer projection이 X_m에 있고 U≥max_Xm S이므로 cut을 만족한다. Exact alias/outward rounding과 작은32분기 fixture 및 current incumbent replay는 각각 별도 검사다. incumbent 만족만으로 보편적 유효성을 주장하지 않는다.
11. 새 LB 개선은 없었다. A3의 현재 두 선로와 grid 가격을 individual integer supports가 재현했고, 선택된 B signed service는 integer feasible support 안이었다. 이 limited experiment로 모든 가능한 Lagrangian/hull 방향을 기각하지 않는다.
12. 실제 Native/memory는 비교표 및 resource JSON에 있다. A2 MESS02 직전에 외부 Known/Unknown pytest가 Gurobi를 로드해 prelaunch gate가 차단했다. 종료를 관측한 후 이미 완료된 calls를 exact/objective/ledger 재검산하여 재호출 없이 미실행 차만 이어갔다. 다른 worker를 중지하지 않았다. 외부 test가 이전 호출 중 실제 Optimize했는지는 증명하지 못하므로 continuous worldwide zero-overlap 주장도 하지 않는다.
13. 최종 Global Gap은13.864737209%로 개선0, target LB는 0.523636091955 이상이다. 원래 FULL UB replay가 성공한 같은 수치 Case에 대해서만 계산했다.
14. 여기 X_m은 FULL 사영을 포함하는 무제한 original route domain이다. Restricted pool/local branching의 ObjBound를 사용하지 않는다. exact inclusion/transport는 PASS, numerical Solver bound 계약은 별도이며 exact B&B proof trace는 아니다.
15. M1/M2는 각각 고정 A1/A2 AIDC anchor, RHS/Response/MESS context 및 Source/Case/Matrix/Objective SHA가 새로 필요하다. Stage mismatch와 bound transfer를 fixture로 거부한다. 실제 M1/M2 Matrix/Heavy0; B2 material gain이 없어 후속 통합도 기각한다.

| Unit / window | Root support | Certified upper | Violation | Adopted |
|---|---:|---:|---:|---|
| MESS03 / 29–32 | 0.049108909127 | 0.072224872032 | -0.023115962906 | false |
| MESS03 / 27–34 | 0.023792909646 | 0.073742469545 | -0.049949559899 | false |

## 검증·실행 한계

Native0 identity, original slice/full coefficient mapping, current FULL UB replay, exact weak-duality recalculation, exact original equality-multiplier repair, outward support transport, small exhaustive fixture 및 독립 최종 인증을 저장했다. 원시 solver logs/Point/Bound/CSR/data/parameters/resource gate를 모두 보존했다. Actual/Full96/OpenDSS fresh validation, 전체May31 restart, B1/B3 최적화는 실행하지 않았다. 기존 HOLD와 Supervisor disabled는 유지했다.

신규 집중 tests는 실행 전10개 PASS, 이후 추가 quarantine/부호 gate 포함12개 PASS다. 전체 회귀 최초 collection은 기존 missing tmp/v29_projection_cache_draft/original_loader.py와 동명test_certificate 충돌로 중단됐다. importlib 모드로 계속한 전체 회귀 결과는 `FULL_REGRESSION_RESULT.json` / `FULL_REGRESSION_CONTINUED.log`에 실제 pass/fail/skip/collection error를 기록한다. Gurobi optimize/presolve가 필요한 test는 budget 보존용 guard로 SKIP하며 PASS로 세지 않는다. 전체 suite PASS를 주장하지 않는다.

검증 수준: A Level1(유효 Numerical Global LB), Level2/3/4 FAIL. B Native0/support validity만 PASS, 위반 cut 및 신규 LB 없음. 알고리즘 둘 다 M1/M2 통합용 material acceptance REJECT다. 계산시간 확대나 K64/K96 전환은 이번 negative result의 정당한 후속이라고 가정하지 않는다.

## 최종 회귀 기록과 제출 제한

전체 회귀는 두 번 모두 전수 실행을 시도했고 PASS가 아니다. C: 임시 경로 실행은3517 PASS/431 FAIL/186 ERROR/2 SKIP였다. 원래 D: 경로 계약에 맞춘 재실행은 **3908 PASS/29 FAIL/41 ERROR/160 SKIP**,405.61s였다. 원래 누락된 projection-cache fixture, 오래된 fixture/schema 및 source-seal 기대값과 native-evidence 환경의 실패를 보존한다. OpenDSS backend import에서 Windows exception 로그도 관측됐으며 actual AC validation을 추가 실행한 것은 아니다. 수정된 파일은 신규 연구 도구·증거·테스트뿐이고 원래 tracked source diff는0개다. 기존 모든 실패가 baseline에서 재현됐다고 별도 clean checkout 실험을 주장하지는 않는다.

관련 회귀는 **27/27 PASS**: 신규 연구12개, PR209 symbolic7개, 기존 incumbent/dispatch8개다. 새 Gurobi Optimize/Presolve 호출0이다. 별도 원본 전체 회귀를 통과했다고 표시하지 않고 Draft로 제출한다. 로그·JUnit XML·분류는 `REGRESSION_AUDIT.json` 및 같은 디렉터리에 보존한다.

연구의 수학 포함관계/반올림/원본 helper 승수 repair와 측정 Bound 재합산은 independent PASS다. Native numerical-bound 계약과 exact B&B trace는 다르다. 새로운 연구 runner 전체의 실행 전 별도 cryptographic anchor는 없었으므로 그런 attestation을 주장하지 않는다. 핵심 research source는 A/B 시작 receipt SHA와 byte가 일치하는 epoch으로 복원했고, 초기 native/math runner는 기록된 patch로 복원했다. 이후 quarantine/authority/callback/raw-bound 진단 보강은 신규12개 fixture/compile만 검증했고 Native 재실행은0이다.

Global registry의 registration은 GLOBAL_LOWER_BOUND scope, 검증된 전체-domain inclusion, 허용 algorithm 및 동일 source/case/matrix/domain/objective/anchor를 요구한다. Restricted route-fixed Bound와 미등록 후보는 거부한다. 다음 실행을 자동 승인하거나 남은 시간으로 연구를 확대하지 않는다. B2/B3 HOLD 및 보호된 UB/Native prefix는 유지한다.
