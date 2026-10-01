# 한국어 최종 검토

1. **왜 다시 B3 optimum 전체를 풀지 않았는가?**

   이번 primary question은 rho<=T point의 존재다. 원 min-rho optimum 계산 대신 exact hard-row/zero-objective decision model을 한 번 수행했다.

2. **threshold T는 정확히 어떻게 계산했는가?**

   Decimal authority로 S2 0.5722125039436496 +0.001 = 0.5732125039436496를 계산했다. binary float serialization도 THRESHOLD_AUTHORITY에 기록했다.

3. **왜 T=0.5732125039436496인가?**

   PR113 inherited S2 original-M1 LB와 사전등록 material increment0.001의 합이다. F3 값이나 결과를 보고 threshold를 바꾸지 않았다.

4. **S2 LB는 B3 lower floor인가?**

   아니다. S2는 original-M1 reference LB다. S2 relaxation과 B3 feasible set의 포함관계가 자동으로 주어지지 않으므로 partial optimum floor로 설치하지 않았다.

5. **S2를 threshold reference로 어떻게 쓰는가?**

   opt_B3-S2<=0.001의 ceiling을 검사한다. 이는 opt_B3<=S2+0.001라는 decision question이다.

6. **threshold feasibility는 scientific question과 동치인가?**

   F_B3 안에서 rho<=T인 점이 존재하면 optimum<=T다. 기존 feasible upper로 F_B3가 비어 있지 않고 변수/연속 objective는 native bounded feasible set에서 정의되므로 threshold infeasibility는 optimum>T를 의미한다.

7. **witness 하나가 왜 negative certificate인가?**

   B3-restored integrality와 모든 original row를 만족하는 점은 B3 optimum의 upper다. rho<=T면 materiality reference의 기여 ceiling0.001을 확보한다.

8. **threshold infeasibility가 왜 positive certificate인가?**

   Unrestricted F_B3와 rho<=T의 교집합이 비었다는 solver proof는 opt_B3>T를 의미한다. T를 valid LB로 사용할 수 있으나 임의 strict epsilon을 더하지 않는다.

9. **heuristic witness search는 scientific replacement인가?**

   아니다. Root-nearest route들은 제한 subset에서 feasible upper point를 찾는 generator다. Exact direct model의 graph/bounds를 제한하지 않았다.

10. **candidate 실패가 왜 negative evidence가 아닌가?**

   제한 route subset의 infeasibility는 다른 route의 존재를 배제하지 않는다. 이를 B3 전체의 material/nonmaterial certificate로 승격하지 않았다.

11. **root flow를 route candidate로 어떻게 변환했는가?**

   원 time-expanded DAG의 complete0–96 path에서 duration-weighted arc L1 distance를 최소화했다. 이는 selected duration*root-flow 합을 최대화하는 dynamic program이며 원 arc order로 tie를 고정했다.

12. **route candidate는 원 graph를 보존하는가?**

   모든 선택 arc는 native legal route/stay authority에 존재하며 출발/도착/connection/energy와 initial site에서96까지 continuity를 검증했다. 원 scientific direct graph의 arc를 삭제하지 않았다.

13. **candidate 수를 결과 후 바꾸었는가?**

   아니다. BASE F3와 S3 source 각1개, 총2개 joint candidates를 preregister했다. Exact duplicate B3 fixed-route signature만 기록 후 skip할 수 있으며 후보를 추가하지 않는다.

14. **PR113 B3 root vector를 사용했다고 주장했는가?**

   아니다. Native B3 root objective/log는 있지만 saved B3 root vector는 없다. B3_SOLUTION.npz는 최종 incumbent이며 ancestry에서 그 이름으로만 썼다. Route generation은 저장된 BASE F3와 S3 roots를 사용하고 unavailable B3 root를 꾸미지 않았다.

15. **B3 restored binary count는 그대로인가?**

   85,744개다. PR113 mask와 독립 selected-arc rule을 대조했다. 58–95 mode와 occupancy/entry-crossing/departure 관련 route binary authority를 그대로 유지했다.

16. **terminal SOC를 유지했는가?**

   원 terminal equality4개와 초기 equality4개를 유지했다. SOC96=760을 원 sense/RHS/coefficients로 대조했다. TERM_RELAX는 사용하지 않았다.

17. **full96 grid를 유지했는가?**

   원954,560개 rows를 모두 exact 보존했다. 추가는 threshold row1개뿐이며 all96 voltage/line/transformer current/kVA와 individual PCS16을 유지했다.

18. **voltage 0.955–1.045를 유지했는가?**

   Planning band를 그대로 유지했다. Fresh AC0.95–1.05는 상속된 계약이며 이번에 Fresh AC를 실행하지 않았다.

19. **threshold row 외 scientific physics 변경이 있는가?**

   없다. Direct model의 변수/bounds/VTypes/original row order/senses/coefficients/RHS는 PR113 B3와 exact 일치한다.

20. **zero objective가 원 feasible set을 바꾸는가?**

   목적식은 feasible set을 바꾸지 않는다. rho epigraph 변수와 original P1 row semantics는 남으며 hard threshold row가 decision subset을 정의한다.

21. **native solver status는?**

   Direct overall status=9. Raw log와 status를 그대로 저장했고 status9/11/12를 OPTIMAL 또는 INFEASIBLE로 재표기하지 않았다.

22. **feasible witness를 발견했는가?**

   Safe independent witness=False; source=None; final classification=B3_INCONCLUSIVE.

23. **validated witness rho는 얼마인가?**

   None. Witness가 없으면 partial upper는 inherited original-feasible start 또는 별도 validated partial point의 rho만 사용한다. Best partial upper=0.5912812634331275.

24. **threshold slack은 얼마인가?**

   None. Safe certificate는 rho와 recomputed P1 모두 T-1e-6 이하일 때만 인정한다.

25. **maximum matrix residual은?**

   None. 점이 없으면 residual을0으로 꾸미지 않는다. 각 native point validation에 실제 residual을 저장한다.

26. **partial point를 original UB로 오인하지 않았는가?**

   B3 outside binaries가 fractional인 점은 partial upper만 된다. 모든208,312 original binaries integrality 및 full original matrix/graph/battery/grid 검증이 통과해야 original UB 후보가 된다.

27. **proven infeasible인가?**

   False. Only unrestricted DIRECT overall status3가 positive proof authority다. Restricted W1/W2 status3는 이 authority가 아니다.

28. **TIME_LIMIT이면 왜 inconclusive인가?**

   시간 종료는 feasible point 부재나 model infeasibility의 증명이 아니다. independently safe witness 또는 exact infeasibility proof가 없으면 INCONCLUSIVE를 유지한다.

29. **numerical warnings는?**

   PR113 basis/quad warning을 보존했다. 새 warnings는 NUMERICAL_WARNING_AUDIT의 각 run에서 actual raw log로 추출했다. Numerical contradiction=False; rational-arithmetic exact proof를 주장하지 않는다.

30. **Threads 설정 이유는?**

   Preregistration snapshot과 각 start snapshot에서 independent heavy solve를 관측했다. None이면4, heavy이면1이라는 정책을 등록했다. 실제 registered threads=4이며 성능 우월성을 주장하지 않는다.

31. **parallel resource contention이 있었는가?**

   각 run 시작 전1초 CPU/RSS snapshot을 보존했다. 등록4 threads와 heavy contention이 겹치면 실행 전 중단하는 guard가 있다. Snapshot에서 관측하지 못한 것을 전체 wall-time의 부재 증명으로 과장하지 않는다.

32. **slot58 state는 무엇인가?**

   ROOT_GUIDED_STATES.csv에 inherited BASE/S3의 SOC/mode/P/Q/site/transit mass를 보존했다. Conditional ancestry는 DIAGNOSIS_ONLY이며 실시한 경우 CAUSAL_BACKWARD_CLOSURE의 unit별 state_at_58에 기록했다.

33. **SOC58은 어떻게 형성됐는가?**

   Initial760 + slots0–57 eta-adjusted charge − discharge − departure travel-energy debit다. Diagnosis gate가 열리면 stored/reconstructed SOC와 누적 항을 unit/source별로 실제 계산한다.

34. **SOC66 ancestry는 어디까지 이어지는가?**

   원 energy recurrence에서 SOC66→SOC65→...→SOC0로 이어진다. 실제 conditional audit 실행 여부와 source별 energy contributions는 closure file에 기록하며 certificate case에서는 Phase D를 skip한다.

35. **earliest causal predecessor slot은?**

   0. Diagnosis가 수행되면0은 structural physical dependency 결과이며 관측상의 첫 nonzero charge/travel slot과는 구분한다.

36. **58 buffer가 충분했다는 증거가 있는가?**

   단지58부터 integrality를 복원했다는 이유로 경계 ancestry가 닫혔다고 할 수 없다. Certificate가 없으면 sufficiency를 주장하지 않는다. Threshold certificate 자체도 전체 original-M1 gap의 완전 분해를 뜻하지 않는다.

37. **왜 임의 window search를 하지 않았는가?**

   1h/2h/4h/8h parameter sweep을 하지 않았다. Physics/graph predecessor closure만 계산하며 확대 experiment는 별도 사용자 승인 후다.

38. **causal backward closure의 물리적 의미는?**

   경계SOC/location에 영향을 줄 수 있는 가능한 이전 transition/dispatch/travel dependencies다. 어떤 모든 ancestor가 active/material하다는 뜻이나 Planning의 최적화 coupling을 time-forward causal effect로 읽는 증명이 아니다.

39. **line.sw1/A와 어떤 관계가 있는가?**

   Inherited late66–95 bottleneck faces는 P/Q/location에 의존한다. 그 controls의 SOC/location ancestry는 앞선 history에 이어질 수 있으나 descriptive sensitivity를 unique integer-gap cause로 승격하지 않았다.

40. **charge-mode ancestry는?**

   Pch<=P_limit*mode, Pdis<=P_limit*(1-mode), SOC recurrence를 통해 이전 dispatch에 연결된다. Outside58의 continuous mode는 scientific B3 relaxation으로 남겼다.

41. **route ancestry는?**

   Initial-site flow conservation과 time-expanded legal transitions의 backward reachable ancestry다. Crossing travel arc의 departure와 connection을 포함하며 중간 transit을 가상의 stay로 바꾸지 않았다.

42. **travel-energy ancestry는?**

   Travel energy는 departure slot SOC transition에서 차감된다. At58/66 in-transit state의 earlier departure를 누락하지 않고 graph/energy audit에 반영한다.

43. **다음 window를 확장해야 하는가?**

   Closure0이면0–95를 future candidate로 제안할 수 있지만 필요/충분/material하다는 certificate는 아니다. 이번 PR에서는 expanded-window optimize0이며 automatic 확대를 하지 않았다.

44. **exact decomposition이 필요한가?**

   Conditional design gate=True. Monolithic unfinished search가 확인된 경우에만 future exactness proof와 bounded fixture design을 NEXT_MODIFICATIONS에 기록했다.

45. **Benders feasibility decomposition은 original set을 보존 가능한가?**

   B3 restored binaries만 master로 두고 나머지 full96 constraints/continuous outside variables를 recourse로 유지하면 가능하다. Verified Farkas feasibility cuts가 모든 feasible projection을 보존해야 하며 bound/sign/ray residual audit가 필요하다.

46. **새 cut을 이번에 구현했는가?**

   없다. Threshold row는 scientific decision question의 정의다. Solver built-in cuts와 future decomposition feasibility-cut design은 구분하며 production cut/decomposition implementation은0이다.

47. **B1/B2 optimize calls는0인가?**

   둘 다0이다. PR113 inherited evidence와 별도중단된 B0/B1 comparison work를 수정하거나 실행하지 않았다.

48. **production M1을 실행했는가?**

   실행하지 않았다. Exact threshold diagnostic은 production P1/P2 acceptance solve가 아니다.

49. **M1 accepted인가?**

   M1_ACCEPTED=false다. Threshold point 또는 threshold infeasibility는 production P1/P2 certificate를 대신하지 않는다.

50. **Problem13 final validated인가?**

   PROBLEM13_FINAL_VALIDATED=false다. A2→M2→Planning→Actual replay→Fresh AC final chain을 실행하지 않았다.

51. **다음 정확한 작업은 무엇인가?**

   Threshold question은 INCONCLUSIVE다. Dependency closure의 earliest slot은0이며 후보 window는0–95다. 이는 가능한 물리 ancestry이고 전체 과거 integrality 복원이 필요·충분하거나 material하다는 증명이 아니다. 확대 B3를 이번에 실행하지 않는다. 사전등록 결과의 root/search/resource 병목을 감사하고 별도 후속 exact feasibility decomposition의 exactness와 bounded fixtures를 먼저 검토한다.

52. **기존 original UB/LB와 현재 값은?**

   Inherited UB=0.5912812634331275, S2 LB=0.5722125039436496. Current validated original UB=0.5912812634331275, certified original LB=0.5722125039436496, implied gap=3.22498964%. Partial upper와 zero-objective bound를 original integer UB/LB로 오인하지 않았다.

53. **row aliases 때문에 exactness가 약해졌는가?**

   Native duplicate row-name alias map은 PR113 그대로다. 원 ordered CSR data/indices/indptr, RHS/senses/bounds/variable axis와 같은 순서의954,560 rows를 exact 비교했다.

54. **same complete start를 threshold에서 accepted라고 주장했는가?**

   아니다. PR113 native B3 acceptance evidence를 보존하지만 rho0.591281은 T를 초과한다. Threshold에는 partial binary seed 또는 independent threshold witness만 넣으며 native rejection/acceptance log를 보존한다.

55. **zero-objective BestBd0은 rho LB인가?**

   아니다. Feasibility objective의 bound는 constant0에 대한 값이다. P1 rho lower certificate는 threshold infeasibility의 논리적 T lower bound 또는 inherited B3/S2 bounds에서만 나온다.

56. **Root relaxation log line만 있으면 root completion인가?**

   아니다. Frozen runner의 root_completed 필드는 log line 존재 관측이며 interrupted/time-limit line도 포함할 수 있다. ROOT_COMPLETION_AUDIT는 completed objective line과 time-limit/interrupted line을 독립 구분하고 FINAL_FLAGS의 DIRECT_ROOT_COMPLETED를 계산한다. 원 receipt/source/status는 수정하지 않았다.

57. **threshold 경계 tolerance를 어떻게 처리했는가?**

   Hard row는 exact T를 유지한다. Native FeasibilityTol/IntFeasTol1e-7, independent matrix1e-6, integer1e-7, epigraph recomputation1e-7 및 safe margin1e-6을 실행 전에 등록했다. Ambiguous near-boundary point는 certificate로 승격하지 않는다.

58. **objective recomputation residual은 어떻게 정의하는가?**

   Zero objective에서는 rho epigraph가 tight할 필요가 없다. All96 original line faces의 maximum을 독립 재계산하고 max(0,recomputed-rho)를 violation으로 기록한다. rho-recomputed는 allowable epigraph slack이다.

59. **solver proof와 IIS/Farkas를 혼동했는가?**

   Native unrestricted MIP INFEASIBLE status는 branch-and-bound proof authority다. LP FarkasDual은 full MIP의 직접 proof가 아니다. IIS API 가능 여부와 미계산 이유를 보존하고 expensive MIP IIS나 extra LP를 자동 실행하지 않았다.

60. **execution source를 결과 후 바꾸었는가?**

   EXECUTION_FREEZE의 optimizer/validator/route/preflight test source를 pre-execution commit에서 동결했다. Actual run markers가 그 commit과 preregistration SHA를 결합한다. Report/closure/verification은 별도 postprocessing source다.

61. **기존593 tests와44 bounded checks는?**

   1464 inherited tracked 파일의SHA를 검증하고 기존593 test suite를 전체 다시 실행한다. Inherited44 bounded check receipt/source도 그대로 보존한다. 추가 execution-evidence tests를 함께 기록한다.

62. **범위 밖 numbered Problems를 건드렸는가?**

   Problems1,2,3,4,5,6,8,13을 보존했다.7,9,10,11,12의 새 실험/redesign/학습은0이다. Runtime/carry-over/known-unknown/response/A1→M1→A2→M2/flexibility contracts를 byte 보존했다.
