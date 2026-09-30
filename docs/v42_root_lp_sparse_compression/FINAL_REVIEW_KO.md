# Exact root-LP compression 최종 검토

1. **PR102 root LP가 왜 1557.9초 걸렸는가?**

PR102는 100.46M nonzeros, Runtime 34.92M과 tie 14.50M을 포함한 큰 LP를 처리했다. 단일 node/no incumbent는 root 처리 병목을 입증하지만, 개별 matrix family에 특정 초수를 인과적으로 배분할 증거는 없다.

2. **baseline rows/columns/nonzeros는?**

9,358,534 rows / 7,920,701 columns / 100,455,768 nonzeros.

3. **Runtime linking은 실제 몇 nonzero였는가?**

34,923,402.

4. **가장 dense한 Runtime row는 몇 항인가?**

77,795항; baseline matrix row R1121.

5. **tie는 몇 nonzero였는가?**

14,503,274.

6. **tie는 scientific objective인가?**

아니다. 마지막 event-rank는 여섯 scientific objectives와 분리된 대표 선택이다.

7. **tie를 MILP에서 제거했는가?**

true

8. **제거 후 deterministic result는 어떻게 보장했는가?**

동일 scientific class 안에서 complete physical trajectory를 정렬하고 stable UID 순서로 배정한다. 동일 aggregate의 반복 reconstruction이 같음을 검증했다. 서로 다른 solver 실행의 aggregate optimum까지 같다는 주장은 하지 않는다. 기존 rank 최소화와 동일한 대표 선택도 아니다.

9. **six scientific objectives는 동일한가?**

완전 bounded physical-set 양방향 비교, 여섯 lex 값 및 native independent certificate PASS. production lex 완료 여부는 false.

10. **Runtime completion count는 무엇인가?**

C[g,k,t] = 해당 class/site/end의 f0+f1 completion event 합. equality로 유일하게 정의된 continuous auxiliary이며 integer path에서 정수 count가 된다.

11. **Runtime grouping은 exact한가?**

전체 downstream coefficient vector의 엄격한 동일성과 Runtime provider/nominal-seconds/gamma/GPU/kernel/adjusted-end signature를 검사한다. averaging이나 tolerance grouping은 없다.

12. **Runtime nonzeros는 얼마나 줄었는가?**

34,923,402 → 2,521,610; 감소 32,401,792. 새 수치는 completion row와 count 정의의 nonzeros를 모두 포함한다.

13. **scientific class는 몇 개인가?**

117

14. **몇 jobs가 non-singleton class에 속하는가?**

1479

15. **단순 총 service aggregation을 왜 쓰지 않았는가?**

총 service만 맞추면 서로 다른 jobs의 짧은/긴 service가 상쇄될 수 있다. whole fixed-duration path histogram과 개별 migration lanes를 유지했다.

16. **class integer flow는 individual path로 분해되는가?**

PASS. integer histogram을 완전 STAY/TS paths로 확장하고 각 migration lane을 개별 validator로 확인한 뒤 UID를 배정한다.

17. **migration도 aggregate했는가?**

migration path 자체를 공동 payload flow로 aggregate하지 않았다. optional lane마다 완전 service/checkpoint/WAN/restart를 유지한다.

18. **hybrid aggregation 구조는?**

nonmigration integer Y histogram + individual optional migration lanes + exact class cardinality. 선택 여부 true.

19. **depart는 제거됐는가?**

false

20. **arrive는 제거됐는가?**

false

21. **link_bytes는 어떻게 압축됐는가?**

LINK 후보는 동일 fixed-path incidence에 한해서 공유를 구현했으나 full-May matrix 개선이 없어 선택하지 않았다. 최종 link-byte 열 감소 여부 false. F2-CRA의 WAN MiB 단위 변환 선택 여부 true; 2**20 bytes를 한 단위로 사용하며 physical byte 값과 capacity는 동일하다.

22. **f0는 제거됐는가?**

true; eligible fixed-duration nonmigration finishes and inactive optional migration-lane f0 only.

23. **r0/h/r1은 어떻게 처리했는가?**

migration r0/h/r1의 sparse local recurrence는 유지했다. certified nonmigration count lanes는 occupancy histogram/표현식 후보를 비교했다. 전체 cumulative projection은 bounded matrix 악화를 확인하여 production에서 제외했다.

24. **variable 감소 때문에 row가 dense해지지는 않았는가?**

baseline max 77,795, 선택 max 3,964; p99 76.0 → 25.0. individual auxiliary 제거로 다른 행이 길어지는 trade-off는 full census와 DA audit에 포함했다.

25. **numerical range는 개선됐는가?**

NUMERICAL_SCALING_AUDIT.json 참조. exact WAN remaining/sent quantum을 유지했다. 선택 matrix 범위 {"minimum_abs": 1.0005387532580141e-13, "maximum_abs": 305175.78125}. WAN MiB 변환 여부 true; frozen small grid coefficients가 남아 있으므로 numerical warnings가 사라졌다고 주장하지 않는다.

26. **eligible formulations는 무엇인가?**

["F2-BASE", "F2-T", "F2-R", "F2-TR", "F2-A", "F2-C", "F2-CRA"]

27. **어떤 후보가 Pareto set에 남았는가?**

["F2-A", "F2-CRA"]

28. **production formulation selection rule은?**

lowest completed LP wall; within 5% stronger bound, within 1e-7 fewer presolved nonzeros/rows+columns, numerical risk, simplicity

29. **최종 formulation은?**

F2-CRA

30. **최종 binary 수는?**

2223230

31. **integer 수는?**

41685 (general integer; binary 제외).

32. **continuous 수는?**

5184087

33. **rows는?**

9126514

34. **nonzeros는?**

53621850

35. **presolved rows/columns/nonzeros는?**

{"seconds": 71.72, "rows": 7239919, "columns": 6658595, "nonzeros": 31459420}

36. **새로운 root LP 시간은?**

첫 production MIP root relaxation은 86.83초. 별도의 continuous-P1 LP 전체 optimize wall은 100.56초이며 LP presolve를 포함한다.

37. **1557.9초 대비 speedup은?**

기존 1,557.90초 / 새 86.83초 = 17.94배의 관측 시간 비율. 새 production에는 검증된 full MIP start가 있으므로 formulation 단독의 인과적 speedup으로 해석하지 않는다. 동일 설정의 별도 LP 비교에서는 A가 3,600초 시간 초과, CRA가 100.56초 optimal이었다.

38. **root lower bound는 약해졌는가?**

기존 기록은 0.6716023396111563; 새 continuous LP는 0.6715871458371275로 차이 -1.5193774e-05. 새 P1 MIP 최종 bound는 0.6715924043100266로 차이 -9.93530113e-06. 관측 bound가 소폭 낮으므로 '전혀 약해지지 않았다'고 주장하지 않는다. 수치 오차와 relaxation 구조의 영향을 분리한 증거는 없다. Integer physical set 및 여섯 scientific objective의 exactness는 별도 양방향 검증과 독립 물리 certificate로 확인했다.

39. **validated MIP start가 있는가?**

true

40. **MIP start는 full Runtime/CC4/grid를 통과했는가?**

true

41. **Gurobi가 MIP start를 accept했는가?**

true

42. **first incumbent은 몇 초인가?**

0.48979759999201633

43. **UB는?**

0.6715925043100266

44. **LB는?**

0.6715924043100266

45. **final gap은?**

최종 schedule의 원래 P1 global gap은 1.48899815447e-07 (fraction), 즉 1.48899815e-05%. 첫 P1 solve 자체는 gap 0. P2의 gap 100%와 구분한다.

46. **node count는?**

P1 1 node; P2 1 node. 두 개의 root 처리 기록이며, 이것을 branch-tree의 2 nodes 진행으로 합산 해석하지 않는다.

47. **B&B가 실제로 진행됐는가?**

아니다. 두 단계 모두 1 node이고, branch-tree progression은 관측되지 않았다. P1은 root에서 완료됐으며 P2는 root LP 도중 시간 제한에 도달했다.

48. **0.5% global gap을 달성했는가?**

true

49. **A1은 accepted인가?**

P1 global gap ≤0.5%와 최종 독립 물리 PASS라는 A1 기준은 충족했다. 다만 P2는 시간 제한(incumbent 768.1501457253, bound 0, gap 100%)이고 나머지 네 lex 단계는 시작되지 않았다. LEX_COMPLETE=false; 여섯 목적 전체 최적화 완료를 주장하지 않는다.

50. **현재 다음 계산 병목은 무엇인가?**

P1 root 처리 병목은 해소됐다. 남은 계산 병목은 P1 lock 아래의 P2 reserve_shortfall root LP다: presolve 뒤 root relaxation이 2904.19초, 420,473 iterations 후 시간 제한으로 끝났다. Branch-tree explosion을 입증하는 데이터는 없다. M1/A2/M2/Fresh AC는 실행하지 않았다.

후처리 근거: FINAL_FLAGS.json의 per-level scope, TELEMETRY_COVERAGE_AUDIT.json 및 native Gurobi 로그. 누적 optimize-call wall은 3,601.3247초이며 3,600초 제한에 대한 native 반환 초과 1.3247초를 숨기지 않았다. 사전 등록된 5초 반환 grace 안에 있다.
