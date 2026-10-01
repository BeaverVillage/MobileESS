# 최종 검토 — 50개 질문

1. **PR110까지 해결되지 않은 핵심 문제는 무엇인가?**

   같은 UB에서 약 14.55%인 LP gap의 지배 원인이 full-grid/PQ/discrete coupling인지 아직 밝혀지지 않았다. PR110 single-slot 결과만으로 full-grid coupling을 배제할 수 없었다.

2. **현재 UB는?**

   0.6696147314213984. 기존 검증된 integer UB를 재사용했으며 새 full-M1 UB는 없다.

3. **F3 LB는?**

   0.5718494602017812.

4. **S2 reference LB는?**

   0.5722125039436496.

5. **현재 implied gap은?**

   S2 reference 기준 14.54601025%; 선택된 G0/F3 기준 14.60022706%. 기존 MIP gap과 LP implied gap은 구분한다.

6. **0.5%에 필요한 LB는?**

   동일 UB의 99.5%인 0.6662666577642914.

7. **왜 single-slot O1이 약했는가?**

   O1은 다른 시간의 grid 요구와 retained-slot voltage/transformer를 제거했다. 조건부 oracle upper가 global default보다 낮아 유효 계수가 default를 넘지 못했다.

8. **새 W7 window는 몇 번 슬롯인가?**

   원래 시간 인덱스의 40–46 inclusive, 정확히 7개다.

9. **왜 40–46인가?**

   기존 frozen critical [41,44,43,40,42,46]의 min/max다. incumbent-root loading 차이는 선택 score이며 true local optimality gap이 아니다.

10. **slot45는 왜 포함했는가?**

   연속 window를 만들기 위해서만 포함했다. 결과에 따른 재선택은 없다.

11. **W7은 어떤 MESS 물리를 full-horizon으로 유지하는가?**

   4개 unit/96-slot route flow, stay/travel 시간·energy, Pch/Pdis/Q 연결, charge mode, PCS16, SOC recurrence·초기·terminal equality·효율을 모두 유지했다.

12. **W7은 어떤 grid rows를 유지하는가?**

   40–46의 원래 non-transformer P1 faces, robust 0.955–1.045 voltage, transformer current/kVA, injection/response bindings 및 고정 AIDC/correction 항을 유지했다.

13. **W7에서 어떤 grid rows를 제거하는가?**

   40–46 밖의 grid requirements와 해당 auxiliary bindings를 제거한다. native full-horizon MESS 행은 제거하지 않는다.

14. **제거해도 lower bound가 valid한 이유는?**

   원 conditional integer plan의 투영은 W7 LP feasible이고 rho_global>=rho_window다. feasible set 확대와 integrality relaxation으로 conditional minimum은 valid lower bound다.

15. **W7 objective는 무엇인가?**

   7-slot non-transformer normalized phase-line maximum rho_W7의 최소화다. P1/P2는 바꾸지 않았다.

16. **G1은 무엇인가?**

   각 unit/frozen time/state를 조건으로 하는 W7 lower bound 기반 single-state epigraph다.

17. **G1 beta는 PR110 beta보다 강해졌는가?**

   효과적인 계수는 전부 default=0.5722125039436496으로 PR110보다 증가하지 않았다. raw W7 조건부 LP 두 개는 약 0.299390/0.270355; matched raw O1 비교는 수행하지 않았다. 모든 나머지 조건도 upper certificate로 default 이하임을 증명했다.

18. **G1 최대 root violation은?**

   -5.145727399735733e-9 (24개 precheck).

19. **G1 cut은 몇 개인가?**

   0개.

20. **G2는 무엇인가?**

   41/44/43에서 두 unit의 동시 state에 조건부 W7 beta2와 joint mass w를 사용하는 formulation이다.

21. **G2가 G1보다 추가로 보는 것은?**

   두 unit이 같은 7-slot grid 요구를 동시에 부담할 때의 conditional coupling을 본다.

22. **G2 transportation precheck 결과는?**

   18개 transport LP 모두 feasible, 모든 beta2가 default여서 RHS도 default다. 최대 violation -5.145727288713431e-9; useful violation 없다.

23. **G2 cut은 몇 개인가?**

   0개; w/linking columns·rows도 설치하지 않았다.

24. **G3는 무엇인가?**

   동일 unit의 두 시간 state pair와 원래 reachable support를 연결하는 joint v epigraph다.

25. **G3 time pair 4개는 무엇인가?**

   (40,43), (43,46), (40,46), (41,44).

26. **왜 이 4개를 사전에 고정했는가?**

   start-middle, middle-end, window endpoints, 상위 interior critical pair를 사전에 정해 temporal interaction을 검증했다. 결과 후 변경하지 않았다.

27. **route-reachable state pair는 어떻게 정의했는가?**

   원 time-expanded DAG의 initial-to-terminal route에 두 crossing-time state가 동시에 나타나는 경우다. exact DP로 unit당 200/205/625/208, 총 4,952개를 확인했다.

28. **v[a,b]는 무엇인가?**

   두 시간의 state marginal을 연결하는 nonnegative joint mass다. reachable pair에만 support를 두며 integer route는 하나의 cell을 선택한다.

29. **root marginals가 reachable-pair hull에 들어가는가?**

   예. 16개 exact-marginal feasibility LP 모두 PASS; hull violation 0개다.

30. **route-flow network 자체는 이미 integral한가?**

   순수 unit single-commodity DAG flow는 incidence TU 및 path decomposition으로 integral하다. SOC/PQ/grid를 결합한 relaxation 전체가 integral하다는 뜻은 아니다.

31. **G3 strengthening이 route 때문인가 grid coupling 때문인가?**

   route-support projection은 이미 implied라 추가 gain 0이다. conditional grid epigraph도 모두 default라 useful violation이 없다. 두 원인을 별도로 보고했다.

32. **G3 최대 epigraph violation은?**

   -5.1457271776911284e-9 (16개 supported transport precheck).

33. **G3 block은 몇 개 설치됐는가?**

   0개.

34. **원 integer feasible set은 동일한가?**

   동일하다. 원 scientific physics/domain/rows는 유지되고 추가 production cut도 0개다. retained incumbent의 독립 physical/robust voltage 검증도 PASS다.

35. **D-W/CG를 사용했는가?**

   사용하지 않았다. 저장된 경로는 reachability/증명의 witness이며 trajectory master columns가 아니다.

36. **새 full root model size는?**

   새 G1/G2/G3 full root는 미구축이다. inherited F3는 954,560 rows /316,743 columns /8,282,350 nonzeros. 별도 W7 oracle은 260,894 /241,449 /1,771,579다.

37. **새 LB는?**

   새 full root solve는 없고 선택된 G0의 inherited certified LB=0.5718494602017812다.

38. **F3 대비 gain은?**

   0. 모든 uniform cut을 가정해도 ceiling gain은 +0.0003630437418684629로 material threshold 미달이다.

39. **S2 대비 gain은?**

   -0.0003630437418684629. S2를 production base로 carry하지 않은 reference 비교이며 새 solver 결과의 하락이 아니다.

40. **0.001 material gate를 통과했는가?**

   통과하지 않았다. root 후보/600초 canary 이전에 STOP했다.

41. **LB가 0.60을 넘었는가?**

   아니오.

42. **0.62를 넘었는가?**

   아니오.

43. **0.65를 넘었는가?**

   아니오.

44. **600초 MIP canary를 실행했는가?**

   실행하지 않았다. real W7 LP 10회는 conditional 4회+upper witness 6회이며 canary가 아니다.

45. **canary BestBd/gap은?**

   NOT_RUN/null. 기존 MIP bound 0.571849460049452/gap 14.60022708%는 inherited 값으로만 남긴다.

46. **production을 실행했는가?**

   실행하지 않았다. production authorization=false; P2도 NOT_RUN이다.

47. **M1 accepted인가?**

   false. P1 0.5% quality와 P2 quality가 충족되지 않았다. 기존 plan의 physical PASS만으로 acceptance를 선언하지 않는다.

48. **full-horizon grid oracle이 다음 후보인가?**

   우선 진단 후보다. window root max 0.485963962(slot 41)보다 밖의 0.572212509(slot 89)가 높고 P1 dual mass가 거의 전부 밖에 있다. §40의 outside stress 증거에 따른 선택이며 구현하지 않았다.

49. **incumbent quality 조사가 다음 후보인가?**

   별도 미검증 미래 가설이다. tested discrete convexification은 약했지만 outside grid stress가 현재 우선 진단을 지지한다. 더 좋은 full-M1 feasible UB를 찾지 않았으므로 현 UB가 나쁘다고 단정하지 않는다.

50. **왜 A2/M2/Actual을 아직 실행하지 않았는가?**

   M1 P1/P2 quality 및 acceptance gate가 실패했기 때문이다. A2/M2/Actual/Fresh AC/IEEE8500 미실행, Actual P/Q OFF, PROBLEM13_FINAL_VALIDATED=false를 유지한다.
