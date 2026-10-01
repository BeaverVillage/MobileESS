1. Planning voltage limit은 무엇인가?

0.955–1.045 pu.

2. squared limit은 무엇인가?

0.912025–1.092025.

3. Actual physical voltage limit은 무엇인가?

0.95–1.05 pu.

4. 왜 Planning과 Actual limit이 다른가?

Planning 여유는 선형 모델 오차에 대한 robustness 가설이다. Actual은 물리 판정 기준이다. 최종 검증 전이다.

5. A1은 새 margin으로 다시 풀었는가?

새 margin으로 재구성·최적화했다. complete=False

6. A1은 feasible했는가?

아니다. solver status 3(INFEASIBLE), incumbent 없음. 독립 전압 interval에서도 불가능한 행 145개를 증명했다.

7. A1 P1 값은?

값 없음: A1 INFEASIBLE, feasible incumbent가 없다.

8. PR104 대비 P1 변화는?

PR104 baseline P1=0.6715924043100266; 새 A1은 infeasible이므로 목적값 차이는 정의되지 않는다. 기존 값을 lock으로 사용하지 않았다.

9. A1 P2 migration은?

값 없음: A1 INFEASIBLE, feasible incumbent가 없다.

10. shift는?

값 없음: A1 INFEASIBLE, feasible incumbent가 없다.

11. relocation은?

값 없음: A1 INFEASIBLE, feasible incumbent가 없다.

12. A1 총 optimize wall은?

9.980218400014564 s (P1 optimize-only). MIP-start 검증의 별도 zero-objective attempt는 9.392076 s이며 과학 목적 budget에 포함하지 않았다.

13. Actual local repair를 제거했는가?

제거했다.

14. Q correction이 남아 있는가?

남아 있지 않다.

15. P correction이 남아 있는가?

남아 있지 않다.

16. repair_pq가 active path에서 호출 가능한가?

호출 시 ACTUAL_LOCAL_PQ_REPAIR_REMOVED_IN_V42로 즉시 실패한다.

17. Fresh AC는 여전히 필요한가?

필수이며 이번 task에서는 실행하지 않았다.

18. Fresh AC 실패를 Q로 구조하는가?

구조하지 않는다. FAIL을 유지한다.

19. historical local-repair policy naming에 어떤 영향이 있는가?

M1/M3의 기존 repair 대조가 중복될 수 있다. 이름·정책은 유지하며 논문 비교 수정은 승인이 필요하다.

20. A1 provisional table을 만들었는가?

False — accepted handoff 없음; 상태/빈 schema만 기록했다.

21. 1499 known jobs를 개별 복원했는가?

미복원: feasible incumbent 없음. 구성한 모델은 1499개 작업이다.

22. 117 class는 solver compression일 뿐인가?

117 class는 정확한 solver symmetry compression이다. 이번에는 feasible incumbent가 없어 개별 handoff를 발행하지 않았다.

23. unknown future individual job을 fabricated했는가?

fabricated하지 않았다.

24. CC4 anonymous load를 M1 anchor에 넣었는가?

False — CC4는 A1 모델에 유지했으나 accepted anchor는 없다.

25. M1에서 AIDC 영향은 고정인가?

M1 구현은 고정 입력을 요구한다. 이번에는 accepted anchor가 없어 M1을 실행하지 않았다.

26. M1에 AIDC decision variable이 남아 있는가?

구현은 0개를 강제한다. 실제 native M1 census는 미실행이다.

27. M1 route는 decision variable인가?

native time-expanded arc binary이다. 구현 경로는 준비했으나 A1 INFEASIBLE로 native M1은 미실행이다.

28. M1 P는 decision variable인가?

Pch/Pdis와 charge mode가 joint decision이다. 구현 경로는 준비했으나 A1 INFEASIBLE로 native M1은 미실행이다.

29. M1 Q는 decision variable인가?

연결·PCS와 결합한 decision이다. 구현 경로는 준비했으나 A1 INFEASIBLE로 native M1은 미실행이다.

30. M1 SOC는 decision variable인가?

초기/종단·효율·이동에너지와 결합한 decision이다. 구현 경로는 준비했으나 A1 INFEASIBLE로 native M1은 미실행이다.

31. route/P/Q/SOC가 joint인가?

route/P/Q/SOC를 함께 최적화하는 구현이다. 구현 경로는 준비했으나 A1 INFEASIBLE로 native M1은 미실행이다.

32. M1 voltage authority도 0.955–1.045인가?

같은 중앙 authority이다. native M1은 미실행이다.

33. M1 P1 objective는?

MAX_LINE_LOADING.

34. M1 P2 objective는?

MIN_INTERVENTION: movement energy → movement count.

35. reserve shortfall을 optimize했는가?

아니다. report-only이다.

36. M1 model binaries/rows/nonzeros는?

{"binary": null, "linear_constraints": null, "nonzeros": null} — native M1 미구성/미측정.

37. presolve 시간은?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

38. root LP 시간은?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

39. first incumbent 시간은?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

40. P1 UB/LB/gap은?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

41. movement energy 결과는?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

42. movement count 결과는?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

43. M1 physical validation은 PASS인가?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

44. voltage constraints는 몇 개가 binding/near-binding인가?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

45. Q가 PCS 한계에 자주 닿는가?

미측정/해당 없음: native M1을 구성하거나 실행하지 않았다.

46. 30분 내 완료했는가?

complete=None, optimize=None s (build 제외). native M1 미실행.

47. dominant bottleneck은 무엇인가?

미측정: A1 infeasible로 M1 미실행.

48. 다음 exact computational modification은 무엇인가?

M1 병목 기반 exact modification은 추천할 근거가 없다. A1 불가능성은 정적 전압 interval로 증명했다. 과학 조건의 변경은 승인 전 적용하지 않는다.

49. A2를 왜 실행하지 않았는가?

A1 infeasible이면 STOP하라는 명시적 요청에 따라 M1/A2를 실행하지 않았다.

50. Problem 13을 최종 검증했다고 주장할 수 있는가?

아니다. A1 infeasible이며 A2/M2/Actual/Fresh AC가 미실행이다.
