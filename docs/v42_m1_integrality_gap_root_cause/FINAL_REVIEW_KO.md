# 최종 원인 검토 — 50개 질문

1. **현재 14.6% gap의 직접적인 구성은 UB/LB 각각 얼마인가?**

   기존 verified UB=0.6696147314213984, F3 LB=0.5718494602017812 → 14.60022706%; S2 LB=0.5722125039436496 → 14.54601025%. 현재 진단 후 best validated UB=0.591281263433, best certified LB=0.572212503944다.

2. **PR110의 40–46 slot은 어떤 기준으로 골랐는가?**

   rho_inc[t]-rho_root[t] 내림차순과 작은 slot tie-break다. 당시 E1/E2 진단에 유효했으며 원 증거를 변경하지 않았다.

3. **그 기준이 root-bound attribution과 왜 다른가?**

   incumbent-root 차이는 global root epigraph의 activity/dual 기여와 다르다. 이번에는 원 계수/vector로 모든 96-slot face와 dual을 다시 계산했다.

4. **실제 root rho에 붙어 있는 slot은 무엇인가?**

   [66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95]. T_ACTIVE는 epigraph-active와 dual-active의 교집합 [66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95]다.

5. **dual mass는 어느 시간대에 집중되는가?**

   66–95의 late-horizon block; total mass=1.000000480603, active mass=1.000000328766. 상위10개 slot은 36.589527%뿐이며 90%를 담는 최소 연속구간은66–92다. 긴 block이 지배한다. 모든 contiguous window cumulative mass를 저장했다.

6. **active slot dual mass가 전체의 몇 %인가?**

   99.99998482%.

7. **같은 line/phase가 반복해서 binding인가?**

   예. line.sw1/A가 29/30개 slot에 포함된다. near-max ties도 전부 기록했다.

8. **가장 많이 binding되는 line/phase는?**

   line.sw1/A; 전체 unique binding line-phase 5개, canonical face/line switches 5회.

9. **active horizon의 시작/끝은?**

   66–95; backward buffer는 58–95다.

10. **왜 late horizon이 중요한가?**

   실제 global root maximum과 dual이 이 구간에 집중된다. root는 SOC 약1080→760 kWh 순방전하므로 terminal energy와 전기적 bottleneck의 상호작용을 별도 측정해야 한다. terminal 충전회복을 가정하지 않았다.

11. **root와 integer incumbent의 위치 분포 차이는?**

   root positive sites 평균 8.166667/unit-slot, incumbent 1.000000. stay/travel crossing mass·entropy·site detail를 저장했다. point 차이만으로 인과를 단정하지 않는다.

12. **active horizon에서 Q 분산 차이는?**

   root Q dispersion 평균 0.754982, incumbent 0.000000. 무활동이면 dispersion=0이며 원 값은 수정하지 않았다.

13. **active horizon에서 P 차이는?**

   root 평균 Pch=13.669239, Pdis=52.733743, Pnet=39.064504 kW; incumbent Pch/Pdis/Pnet은 각각 0.000000/0.000000/0.000000.

14. **SOC 차이는?**

   active 시작 root SOC는 unit당 약1079.999 kWh, incumbent760 kWh; terminal은 둘 다760. active 평균 SOC는 root835.088307, incumbent760.000000 kWh다. charge/discharge/travel 누적이 SOC 변화를 독립 재현한다.

15. **terminal SOC equality dual은 큰가?**

   native terminal equality 최대 |dual|=0.000265315905 rho/kWh; unit별 {'MESS01': -0.0, 'MESS02': -0.0002653159047412559, 'MESS03': -0.0, 'MESS04': -0.0}. S3에는 같은 RHS의 G_terminal도 있어 cancellation을 반영한 combined dual은 {'MESS01': 2.1995049071402644e-05, 'MESS02': 2.1995073827214384e-05, 'MESS03': 2.1995049060462532e-05, 'MESS04': 2.1995073784522094e-05}다. raw native 값으로 unit02 지배를 주장하지 않고 F3 equality 제거 counterfactual을 따로 측정했다.

16. **terminal SOC 제거 LP에서 rho는 얼마나 변하는가?**

   rho_TERM_RELAX=0.544918814938, F3 대비 decrease=0.026930645263. 단 한 번 LP OPTIMAL이며 production 물리는 바꾸지 않았다.

17. **terminal SOC가 root objective에 material한가?**

   0.001 objective-decrease 기준 material=True. 이는 equality가 F3 LP를 제약하는 정도이며 integer gap의 단독 원인이라는 뜻은 아니다.

18. **R_ROUTE_ONLY는 무엇을 integer로 복원했는가?**

   W_ACTIVE를 점유하거나 그 안 node에서 출발하는 원 route/stay/travel 67316개를 binary로 복원했다. charge_mode와 outside 나머지는 continuous다.

19. **왜 R_ROUTE_ONLY의 BestBd가 원 문제의 valid LB인가?**

   모든 원 integer plan이 partial-integrality feasible set에 포함되기 때문이다. full96 grid/물리 행을 유지하고 일부 integrality만 완화했으므로 certified BestBd는 원 integer optimum의 valid LB다.

20. **R_ROUTE_ONLY LB gain은?**

   600초 진단의 raw BestBd=0.571849462550, inherited F3와 결합한 valid LB=0.571849462550, gain=0.000000002348. COMPUTATIONALLY_INCONCLUSIVE.

21. **R_ACTIVE는 무엇을 추가로 복원했는가?**

   같은 window의 charge_mode까지 binary로 추가하여 총 67436개를 복원했다.

22. **R_ACTIVE LB gain은?**

   600초 진단의 raw BestBd=0.571849462550, inherited F3와 결합한 valid LB=0.571849462550, gain=0.000000002348. COMPUTATIONALLY_INCONCLUSIVE.

23. **charge_mode integrality의 추가 효과는?**

   측정된 certified-bound 차이는 0.000000000000. time-limited bound의 차이이며 optimum의 mode 기여를 정확히 분리했다는 뜻은 아니다.

24. **R_BUFFER의 목적은?**

   8-slot/2시간의 고정 backward buffer로 pre-window route/SOC coupling을 점검한다. 1h/4h parameter/window search는 하지 않았다.

25. **R_BUFFER LB gain은?**

   600초 진단의 raw BestBd=0.571849476968, inherited F3와 결합한 valid LB=0.571849476968, gain=0.000000016767. COMPUTATIONALLY_INCONCLUSIVE.

26. **partial-integrality negative certificate가 있는가?**

   충분한 negative certificate가 없다. 각 arm의 negative flag는 R_ROUTE_ONLY=False, R_ACTIVE=False, R_BUFFER=False.

27. **없다면 왜 negative 결론을 내리면 안 되는가?**

   600초 안에 BestBd가 움직이지 않아도 미탐색 tree가 남을 수 있다. optimal interval 또는 feasible partial upper-F3<=0.001가 없으면 COMPUTATIONALLY_INCONCLUSIVE다.

28. **특정 MESS가 gap을 주도하는가?**

   MESS01: NOT_RUN; MESS02: NOT_RUN; MESS03: NOT_RUN; MESS04: NOT_RUN. gate가 미달이면 unit 원인을 측정하지 않았다고 명시한다.

29. **multi-MESS synergy 증거가 있는가?**

   unit-arm bounds와 all-unit bound를 비교하되 낮은 단일-unit time-limited LB만으로 synergy를 증명하지 않는다. 정확한 optimum/upper interval 없이는 인과 분해가 제한된다.

30. **기존 incumbent route를 고정하고 continuous를 다시 풀면 UB는?**

   P_FIXED_ALL validated original UB=0.669614731429. 모든 route와 charge_mode를 고정해 continuous dispatch만 다시 최적화했다.

31. **같은 route에서 charge mode를 다시 최적화하면 UB는?**

   P_FIXED_ROUTE validated original UB=0.591281263433. 전체 원 mode binary와 P/Q/SOC를 유지/재최적화했다.

32. **late-window route를 다시 선택하면 UB가 개선되는가?**

   P_LATE_ROUTE_NEIGHBORHOOD의 직접 solver UB=0.669614731421; fixed-route feasible point를 포함하므로 best known model upper=0.591281263433다. 직접 solver 결과와 transferred feasible upper를 구분한다. Hamming/Top-K pruning은 없다.

33. **best new feasible UB는?**

   0.591281263433; source=P_FIXED_ROUTE. 모든 accepted UB는 original binary, native physical, reconstructed full-grid voltage/transformer와 SOC 검증을 통과했다.

34. **UB improvement는 material한가?**

   UB gain=0.078333467988; >=0.005 material=True. 개선 실패가 global incumbent optimality 증명은 아니다.

35. **현재 gap은 LB weakness가 주원인인가?**

   measured partial LB gain=0.000000016767. class=CASE_E_INCONCLUSIVE; missing negative certificates가 있으면 LB weakness를 배제하거나 지배 원인을 확정하지 않는다.

36. **UB quality가 주원인인가?**

   직접 검증된 UB quality gain=0.078333467988. material flag=True; LB track만으로 UB quality를 추정하지 않았다.

37. **둘 다인가?**

   혼합 기여 classification 여부=False. 두 positive threshold가 충족될 때만 MIXED로 분류한다.

38. **terminal SOC coupling이 중요한가?**

   terminal equality 제거의 LP decrease=0.026930645263, material=True. root는 late 순방전하며 recurrence/terminal dual과 함께 해석하되 integer-gap attribution과 구분한다.

39. **특정 late-horizon line bottleneck이 중요한가?**

   예. line.sw1/A가 대부분 active slot에 반복되고 full P1 dual mass가 그 block에 집중된다. 특정 feeder sensitivity bottleneck이 관찰되지만 discrete causal 효과는 arm certificate로만 판단한다.

40. **root active plateau는 실제로 몇 slot 연속인가?**

   30개 연속 slot; independently recomputed active_contiguous=True.

41. **이전 E1/E2가 왜 그 원인을 못 잡았을 수 있는가?**

   E1/E2는 incumbent-root 차이가 큰 40–46을 선택했고 single-slot oracle은 다른 시간의 grid와 해당 voltage/transformer까지 제거했다. 실제 late-root bottleneck의 full-horizon 부담을 직접 측정하는 실험이 아니었다.

42. **이것이 solver runtime 문제인가 formulation gap 문제인가?**

   root fractional averaging은 관찰됐다. 그러나 solver-certified positive LB 또는 negative upper가 없으면 formulation gap과 600초 computational limitation을 분리하지 못한다. 실제 arm interval로 판정한다.

43. **numerical artifact 가능성을 어떻게 배제했는가?**

   exact F3 fingerprint/행렬, root optimal barrier interval, 원 coefficients face 재계산, immutable summary와 agreement, dual axis/finite 검사, SOC balance 및 새 upper의 independent full-grid/physical 검증으로 점검했다. tolerance와 solver status를 명시했다.

44. **scientific physics를 바꿨는가?**

   production scientific physics는 바꾸지 않았다. TERM_RELAX만 명시적으로 허가된 diagnostic counterfactual로 terminal equality4개를 제거했다. partial/UB models는 전부 원 full grid/물리를 유지한다.

45. **새 cut을 만들었는가?**

   만들지 않았다. epigraph/disjunctive/trajectory cuts, D-W/CG/master 또는 heuristic cut을 구현하지 않았다.

46. **production M1을 돌렸는가?**

   production M1은 돌리지 않았다. 지정된 partial-integrality 및 restricted-feasible UB diagnostic MIP만 각1회 실행했다.

47. **M1 accepted인가?**

   false. 완전한 기존-authority P1/P2 acceptance certificate를 만들지 않았고 P2를 실행하지 않았다.

48. **가장 근거가 강한 root-cause classification은?**

   CASE_E_INCONCLUSIVE. positive LB gain=0.000000016767, UB gain=0.078333467988, negative certificates=False의 사전 rules에 따른 결과다.

49. **다음 정확한 수정 방향은 무엇인가?**

   Resolve the remaining partial-integrality optimum intervals with a preregistered exact bound/certificate strategy before choosing a cut remedy. Preserve the independently validated same-route full-integer dispatch as a future MIP start with its complete 96-slot mode/PQ/SOC values. In a separately authorized experiment, use that feasible upper to seek a tight late-window partial-integrality interval before choosing route, mode or trajectory cuts; keep original terminal SOC and all full-grid constraints. 이번 PR에서 remedy를 구현하지 않았다.

50. **A2를 왜 아직 실행하면 안 되는가?**

   M1의 기존 P1/P2 quality와 acceptance가 완료되지 않았기 때문이다. A2/M2/Actual/Fresh AC/IEEE8500 미실행, Actual P/Q OFF, PROBLEM13_FINAL_VALIDATED=false를 유지한다.
