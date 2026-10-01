# 최종 한국어 리뷰

1. PR109에서도 gap이 왜 여전히 큰가?

mode/route-energy strengthening 이후에도 동일 UB 대비 S2 implied gap은 14.546010%다. 남은 공간·시간 coupling과 incumbent quality의 기여는 아직 분리되지 않았다.

2. 현재 UB는?

0.6696147314213984; 기존 검증 정수 incumbent이며 새 feasible UB는 찾지 않았다.

3. F3 LB는?

0.5718494602017812; immutable PR109 F3 OPTIMAL artifact를 재사용했다.

4. S2 LB는?

0.5722125039436496.

5. 0.5%를 위해 필요한 LB는 대략 얼마인가?

UB×0.995 = 0.666266657764.

6. 이번 진단 root는 S2인가 S3인가?

S3의 저장된 optimal barrier interior point다. production formulation 선택이 아니다.

7. 왜 그 root를 선택했는가?

BarStatus=2, optimum interval 폭 5.1457×10⁻⁹≤10⁻⁷, 전체 행렬 재검증 최대 잔차 2.16298894884e-06≤10⁻⁵를 통과했다. overall status=11은 그대로 유지한다.

8. 한 MESS가 최대 몇 site에 fractional하게 존재하는가?

epsilon=10⁻⁶ 기준 최대 24개다. 저장된 최적점에 대한 수치이며 optimal face 전체의 인과적 측정은 아니다.

9. multiple-site slot 비율은?

384 unit-slot 중 98.1770833%다.

10. distributed-Q slot 비율은?

|Q|>10⁻⁶인 site가 둘 이상인 unit-slot은 98.1770833%다.

11. P1 slot별 root loading은 어떻게 계산했는가?

원래 non-transformer line/phase의 16개 P1 face를 동일 rating, affine correction, anchor와 bias로 평가하고 각 슬롯의 최댓값을 취했다. Transformer loading은 P1 rho 분해에서 제외한다.

12. critical slot 6개는 어떻게 고정했는가?

rho_inc[t]-rho_root[t] 내림차순, 동률은 낮은 index 순으로 [41, 44, 43, 40, 42, 46]를 고정했다. 이는 local optimality gap이 아닌 선택 score다. dual/Q/voltage는 보고만 했다.

13. E1이 무엇인가?

한 MESS의 site 또는 TRANSIT 상태에 따른 certified rho 하한을 상태 indicator와 결합하는 single-unit disjunctive epigraph 부등식이다.

14. E1은 P1/P2와 관계있는가?

E1은 내부 formulation label이다. 과학적 목적은 P1 MAX_LINE_LOADING, P2 MIN_INTERVENTION 그대로이며 P3를 만들지 않는다.

15. beta[m,t,a]는 무엇인가?

원래 full M1의 해당 상태 conditional integer objective에 대한 certified lower bound다. 이번 모든 beta는 상속 global bound 0.5722125039436496다.

16. beta가 exact optimum일 필요가 없는 이유는?

조건부 integer optimum 이하인 하한이면 해당 상태의 모든 원래 integer plan에 유효하다. exact optimum을 알 필요가 없다.

17. O1은 어떤 제약을 유지하는가?

모든 4개 MESS의 full-horizon route flow/timing/travel energy, Pch/Pdis/Q connectivity, mode, PCS16, SOC, 초기·terminal SOC·효율과 고정 AIDC anchor를 유지한다.

18. 어떤 grid rows를 제거했는가?

선택 slot의 non-transformer P1 line face만 남기고, 모든 other-time line 및 모든 voltage/transformer grid rows를 제거했다. 원래 모델에 없던 제약은 추가하지 않았다.

19. 제거해도 beta가 valid lower bound인 이유는?

원래 conditional integer plan은 이 relaxation에 투영되며 slot loading은 원래 max-over-time rho 이하이므로 O1 LP 하한도 원래 conditional objective의 하한이다.

20. TRANSIT state는 어떻게 정의했는가?

TRANSIT=1−sum site stay mass이며 depart≤t<connect인 crossing travel arc 합과 동치다. departure는 transit, connection은 stay 또는 새 departure다. 원시 두 식의 최대 차이 9.39×10⁻¹⁰을 기록하고 clipping하지 않았다.

21. E1 root 최대 violation은?

-5.14572739974e-09; 15개 LP만 실제 solve했다. 600개 reachable-state witness 전수 검증이 모든 나머지 oracle의 최적값이 default보다 낮음을 증명해 priority queue도 중단했다.

22. E1 cut은 몇 개 추가됐는가?

0개. S3 root violation≥10⁻⁵ gate를 통과한 cut이 없다.

23. E1은 integer feasible set을 바꾸는가?

바꾸지 않는다. Integer plan은 한 상태만 active여서 RHS=그 상태 beta≤plan rho이다. 실제 이번 작업에서는 어떤 cut도 설치하지 않았다.

24. E2는 왜 필요한가?

복수 MESS의 동시 fractional location averaging은 single-unit 부등식으로 남을 수 있어 pair 상태의 conditional 하한을 확인한다.

25. beta2는 무엇인가?

두 MESS가 상태 (a,b)를 동시에 점유할 때 원래 full M1 conditional objective의 하한이다. 모든 11250개 조합은 default global lower bound를 사용한다.

26. w[a,b]의 의미는?

두 상태 marginal을 연결하는 연속 비음수 joint mass다. Integer 상태에서는 해당 한 cell이 1로 강제된다.

27. pairwise marginal linking은 어떻게 하는가?

sum_b w[a,b]=y_m[a], sum_a w[a,b]=y_n[b]를 사용한다. 실제 full model에는 w를 추가하지 않았고 작은 transportation precheck에서만 사용했다.

28. E2 root 최대 violation은?

-5.14572728871e-09. top 3 slot×6 pair의 18개 transportation precheck다. Pair O1 LP는 0회이며, 모든 pair의 feasible upper witness 결합 증명으로 계산을 멈췄다.

29. E2 cut은 몇 개 추가됐는가?

0개. 모든 precheck가≤10⁻⁷이고 default 이상의 beta가 나올 수 없다는 universal certificate도 있다.

30. D-W/CG를 사용했는가?

사용하지 않았다. trajectory columns/master/branch-and-price를 만들지 않았다.

31. heuristic cut을 사용했는가?

사용하지 않았다. cut coefficient는 상속 certified global LB와 조건부 LP dual 하한만 사용한다. Upper witness 값은 오직 stopping proof다.

32. 새 rows/columns/nonzeros는?

full model 추가 rows/columns/nonzeros=0/0/0이다. E1/E2는 미구축이다. O1 template은 210544 rows, 235527 continuous columns, 2468066 nonzeros이고 조건 row는 별도다.

33. F3 대비 새 LB는?

E0 sparse F3의 상속 LB 0.571849460202, 새 gain=0이다. E1/E2 full root LP는 gate 미통과로 NOT_RUN이다.

34. S2 대비 새 LB는?

Sparse E0 reference는 S2보다 -0.000363043742 낮다. 새 solve가 나빠진 것이 아니라 F3 base 비교값이다. S2 상속 하한은 그대로 보존했다.

35. delta LB가 0.001 이상인가?

아니다. 새 material gain=0<0.001이다. 단순 default 부등식이 F3에서 줄 수 있는 최대 개선도 기존 S2의 0.0003630437 이하다.

36. LB가 0.60을 넘었는가?

아니다. E0=0.5718494602다.

37. 0.62를 넘었는가?

아니다.

38. 0.65를 넘었는가?

아니다.

39. implied gap은?

E0 F3 동일 UB 대비 14.60022706%; 참고 S2는 14.54601025%다. LP implied gap이며 MIP certificate를 갱신하지 않는다.

40. 600초 canary를 실행했는가?

실행하지 않았다. useful cut gate와 0.001 material gate 모두 실패했다.

41. canary BestBd/gap은?

NOT_RUN: BestBd/gap은 null이며 측정값을 만들지 않았다.

42. production이 authorized됐는가?

아니다. canary가 없고 production gate도 열리지 않았다.

43. production P1 UB/LB/gap은?

production은 NOT_RUN이다. Retained incumbent UB=0.6696147314213984, 기존 MIP LB=0.5718494600494520, 기존 gap=14.60022708%를 별도로 유지한다.

44. P2를 실행했는가?

실행하지 않았다. P1 0.5% quality certificate가 없고 production도 미실행이다.

45. M1 accepted인가?

아니다. M1_ACCEPTED=false다.

46. 물리/robust voltage validation은?

새 production incumbent는 없다. 기존 incumbent의 route/timing/travel/Pch/Pdis/Q/PCS16/mode/SOC/terminal/AIDC 및 line/transformer/robust 조건을 독립 재검증해 PASS했다. Band는 0.955–1.045다. Retained MIP incumbent node83.2/slot79=1.040712854806 pu이며 cut tuning에 쓰지 않았다.

47. incumbent quality가 다음 문제일 가능성이 있는가?

가능하지만 미검증이다. 새 UB가 없으므로 incumbent quality가 dominant라고 결론낼 근거도 없다. 이번에는 heuristic/search 전략을 바꾸지 않았다.

48. 남은 gap은 local spatial coupling인가 multi-time/global coupling인가?

이번 single-slot O1 cuts는 gain을 설명하지 못한다. 그러나 다른 시간의 grid obligation을 제거한 O1 자체가 약하므로 full-grid spatial mechanism을 배제할 수 없다. 다음 가설은 MULTI-TIME / GLOBAL DISCRETE EPIGRAPH COUPLING이다.

49. 다음 exact computational step은 무엇인가?

여러 critical slot 또는 전체 grid horizon을 유지하는 conditional relaxation을 별도 preregister하고 exact lower certificate를 생성하는 단계다. 이번 작업에서는 구현하지 않았다.

50. A2를 왜 아직 실행하지 않았는가?

M1 P1/P2 quality acceptance가 성립하지 않았다. A2/M2/Actual/Fresh AC/IEEE8500은 NOT_RUN, Actual P/Q correction OFF, PROBLEM13_FINAL_VALIDATED=false다.
