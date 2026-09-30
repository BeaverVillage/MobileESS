# V42 Dantzig–Wolfe LP 검토

결론: EXACT_DECOMPOSITION_VALIDATED_MAY_LP_NONCONVERGED. LP relaxation 증거이며 integer A1 계획으로 승인하지 않았다.

첫 실행은 132.297초에 Windows atomic receipt 교체 sharing violation으로 종료했다. 기존 4,088개 column과 소스를 보존하고 IO 재시도만 수정했다. 두 번째 실행은 잔여 467.453초로 column을 복원했다. 총 활성 wall은 599.735초이며 원래 600초를 늘리지 않았다. 사전등록, pricing, RC_TOL과 물리 authority를 유지했다. [IO_REPAIR_RECEIPT.json](IO_REPAIR_RECEIPT.json)에 상세 기록이 있다.

1. **Dantzig-Wolfe는 prescreening인가?**

NO. 모든 유효 궤적 공간을 implicit하게 유지하고 dual에 따라 column을 생성한다.

2. **PR99의 병목은 무엇이었나?**

9,802,075 event binaries의 전역 MILP 생성과 presolve. optimize 후 TIME_LIMIT이며 incumbent이 없었다.

3. **w binary는 몇 개였나?**

6,910,461개, event binary의 약 70.5%.

4. **D-W에서 global w 변수를 왜 제거할 수 있나?**

각 job의 WAN 선택을 exact pricing DAG에서 결정하고 선택된 완전 궤적의 usage 계수만 λ로 master에 전달한다.

5. **Column 하나는 무엇을 의미하나?**

full Q50 service와 원래 checkpoint/WAN/restart/tail을 만족하는 완전한 물리 궤적 하나.

6. **lambda는 무엇인가?**

job 궤적들의 비음수 convex combination 가중치. job별 합은 1.

7. **Master는 무엇을 결정하나?**

생성된 궤적 가중치, known load/risk, anonymous CC4 service/reserve, headroom, grid/rho.

8. **Pricing은 무엇을 결정하나?**

고정 master dual에서 job의 전체 궤적 공간 중 최소 reduced-cost 경로.

9. **각 job pricing은 독립적인가?**

YES. 하나의 immutable dual snapshot을 받은 뒤 독립적이다. worker는 1개이며 동일 cost 구조의 exact template만 재사용한다.

10. **job들 사이 coupling은 어디에 남아 있는가?**

Master의 GPU/WAN/active/risk balance와 CC4/reserve/grid 행.

11. **GPU capacity는 어디에 있는가?**

Master known_GPU bound와 compute/reserve headroom. immutable occupancy/rack/gang는 pricing의 local validity에도 적용.

12. **WAN capacity는 어디에 있는가?**

Master 링크·시각별 WAN capacity 행. local template도 immutable 잔여 capacity를 만족한다.

13. **grid/rho는 어디에 있는가?**

변경 없이 native planning_grid() master 행과 rho objective에 남는다.

14. **Runtime reserve는 어디에 있는가?**

frozen risk_exposure/gamma90 column -> master target balance -> RT reserve/shortfall.

15. **CC4는 변경했는가?**

NO. PR97 Q10/Q90 timing, depletion/work conservation/carryout/deviation을 그대로 사용.

16. **Runtime/TS는 변경했는가?**

NO. V10 T3 Isotonic Q50, gamma90=2.423057443558147, 1024/1605 TS 및 ServiceBoundary 유지.

17. **Pricing은 old physical trajectory와 exact-equivalent한가?**

YES. DAG label dominance 증명과 bounded exhaustive physical membership 검증. 전 May 궤적의 enumeration은 하지 않았다.

18. **Pricing은 exhaustive minimum reduced cost와 일치하는가?**

PASS. A–J 합성 fixture, 실제 short 두 작업 및 2-site/2-start의 migration·timeshift·157-slot carryout 작업에서 seeded dual vectors 비교.

19. **reduced cost sign 검증은 PASS인가?**

PASS. coefficient registry manual RC와 optimal-basis cloned Gurobi RC 일치. 이전 scientific locks 포함.

20. **full-column LP와 CG 결과가 일치하는가?**

PASS. bounded A–J와 실제 두 작업의 공동 native grid/CC4 모델에서 전체 scientific 목적 비교.

21. **naïve compact LP와 반드시 같아야 하는가?**

NO. conv(X_j)는 naive compact continuous relaxation보다 강할 수 있다.

22. **Phase I은 왜 필요한가?**

job별 local feasible 초기 column이 전체 capacity/grid 등을 만족한다는 보장이 없어서 scaled artificial minimum으로 full-column feasibility를 찾는다.

23. **artificial variable이 최종해에 남을 수 있는가?**

NO. 전체 pricing과 zero 인증 후 UB=0으로 고정한다. 양수나 미인증 LP는 물리 A1 계획으로 승인하지 않는다.

24. **초기 column은 몇 개인가?**

1493개; fixed 6, priced 1493; movable당 1개.

25. **최종 column은 몇 개인가?**

13957

26. **iteration은 몇 번인가?**

두 실행에서 시작된 18회, complete sweep 16회, pricing calls 24213건. 마지막 sweep 완료=False.

27. **Master solve 총 시간은?**

242.160265초 (완료된 solve receipts).

28. **Pricing 총 시간은?**

oracle calls 105.233962초; sweep wall 230.165667초.

29. **가장 느린 pricing job은?**

{'job_id': '8665759', 'pricing_calls': 16, 'total_seconds': 1.837923699960811, 'max_seconds': 0.38147969999408815, 'nodes_sum': 38608, 'arcs_sum': 209664, 'migration_transitions': 171072, 'WAN_transitions': 171072, 'columns_generated': 10, 'template_cache_hits': 0, 'complete_graph_nodes': 2413, 'complete_graph_arcs': 13104, 'average_graph_nodes': 2413.0, 'average_graph_arcs': 13104.0}

30. **final minimum reduced cost는?**

-2.3108593956035467e-07; 마지막 sweep complete=False. 부분 sweep의 min은 convergence certificate가 아니다.

31. **Phase-I artificial objective는 0인가?**

0 도달 및 전체 pricing 인증; 마지막 LP snapshot 값 0.0.

32. **P1 rho LP는 convergence했는가?**

미수렴/완전한 pricing certificate 없음

33. **P2는?**

미수렴/완전한 pricing certificate 없음

34. **P3는?**

미수렴/완전한 pricing certificate 없음

35. **intervention objectives는?**

migration_count: 미수렴/완전한 pricing certificate 없음, shift_slots: 미수렴/완전한 pricing certificate 없음, prestart_changes: 미수렴/완전한 pricing certificate 없음

36. **600초 내 전체 scientific LP convergence했는가?**

False; external wall 599.7350000000006초.

37. **convergence하지 못했다면 bottleneck은 Master인가 Pricing인가?**

Master. Sweep non-oracle overhead 124.931705초에는 전체 profile history의 반복 serialization/fsync가 포함된다. Phase-I zero objective의 dual degeneracy로 여러 sweep이 필요했다. 두 번의 초기화 비용도 별도 기록.

38. **PR99 9.8M binary model을 RMP에 생성했는가?**

NO. RMP event/state family와 binary 수 모두 0.

39. **D-W Master의 final column 수는?**

13957

40. **모델 크기가 얼마나 줄었는가?**

PR98 349,215,815 binary, PR99 9,802,075 binary / 2,759,286 continuous / 4,070,611 rows / 119,775,457 NZ. D-W final {'columns': 13957, 'variables': 724058, 'constraints': 688209, 'nonzeros': 13977247, 'binaries': 0}. Artificial 포함 총수와 제거 전 physical RMP 수를 MODEL_SIZE_COMPARISON에 모두 기록.

41. **이 결과는 integer A1 optimum인가?**

NO. full-column LP와 bounded integer equivalence는 full May integer optimum 증명이 아니다.

42. **lambda fractional solution이 가능한가?**

YES. 마지막 진단 snapshot fractional λ count=6

43. **Branch-and-Price를 구현했는가?**

NO.

44. **restricted-master MIP를 global optimum이라고 주장했는가?**

NO. full May restricted-master MIP도 실행하지 않았다.

45. **M1을 실행했는가?**

NO. A2/M2도 실행하지 않았다.

46. **Fresh AC를 실행했는가?**

NO.

47. **response kernel을 생성했는가?**

NO.

48. **다음 단계가 Branch-and-Price인지 판단할 근거는?**

먼저 full-column scientific LP 수렴, 분수성/integrality gap, master/pricing 시간과 메모리, branch 제약을 exact oracle에 반영할 가능성을 확인해야 한다. 지금 결과에서 자동으로 다음 pipeline을 실행하지 않는다.

49. **D-W가 계산적으로 효과적이었는가?**

전역 job event binaries 제거와 bounded exactness는 입증했다. 600초 full scientific convergence 여부는 False이며, 그 이상 성능을 주장하지 않는다.

50. **다음 정확한 blocker는 무엇인가?**

P1부터 scientific pricing convergence를 완료하는 것. Phase-I feasibility는 인증됐다. 측정된 Master 비용, zero Phase-I dual degeneracy, 124.932초의 sweep non-oracle overhead를 줄일 정확한 구현이 다음 과제다. native grid/row 효과와 incremental receipt 방식을 검토한 뒤 별도 사전등록해야 한다.
