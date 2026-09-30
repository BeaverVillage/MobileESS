# 최종 검토 — 50문항

1. 왜 D-W를 production에서 중단했는가?

사용자가 원래 full physical feasible set의 joint exact MILP를 선택했으므로 D-W는 forensic 증거로만 보존했다.

2. 최종 solver는 여전히 MILP인가?

예. quadratic/SOS/general constraint가 없는 순수 선형 MILP다.

3. 원래 PR99 w는 몇 개인가?

6,910,461개다.

4. w가 전체 binary의 몇 %인가?

9,802,075개 binary 중 약 70.50%다.

5. 현재 w index는 무엇인가?

w[j,source,destination,transfer_start]다.

6. checkpoint/start index가 왜 없는가?

y/q 및 source/wait/post 상태 보존식으로 start/checkpoint를 연결하므로 Cartesian 인덱스를 만들 필요가 없다.

7. 기존 w prescreen의 necessary condition은 무엇인가?

transfer feasible, 호환 prefix 최대 완료량의 최소 remaining bound, latest completion, 목적지 1-slot immutable fit이다.

8. destination 1-slot fit과 full remaining-service fit의 차이는?

1-slot fit은 이후 GPU 충돌을 검사하지 않는다. full fit은 정확한 남은 모든 compute slot을 검사한다.

9. exact support pruning은 휴리스틱인가?

아니다. complete physical path의 존재에 대한 정확한 단조 fit 증명과 duration-mask query다.

10. 몇 개 w를 exact하게 제거했는가?

0개다. 이 May authority에서는 기존 w가 모두 complete support를 가졌다.

11. w 제거율은?

0.000000%다.

12. false pruning은 0인가?

일반 증명과 bounded 양방향 전수검사에서 false pruning이 없다.

13. fixed-point pruning은 왜 필요한가?

unsupported event/state를 연쇄 제거한 뒤 complete-path projection을 다시 적용하여 동일 hash의 결정적 고정점을 검증한다.

14. y/q/f0/f1도 줄었는가?

y/q/f0는 그대로이며 f1은 417,968개 감소했다.

15. continuous state도 줄었는가?

r1은 24,774개 감소했고 r0/h는 그대로다.

16. exact job equivalence class는 몇 개인가?

원래 deterministic tie 계수까지 포함하면 1,499개 singleton class다. UID 문자열은 signature에 포함하지 않는다. tie 이전의 여섯 과학 목적·물리 domain만 비교하면 117개 class이며 별도 audit에 기록했다.

17. non-singleton class는 몇 개인가?

전체 목적 계수 기준 0개다. tie 이전의 여섯 과학 목적 기준으로는 97개이며 1,479개 job을 포함한다. 원래 tie 계수를 보존할 aggregate decomposition은 증명하지 않았으므로 aggregation은 구현하지 않았다.

18. aggregation을 구현했는가?

아니다.

19. 구현하지 않았다면 이유는?

원래 deterministic tie까지 모든 계수가 같아야 한다. job별 global event rank offset이 달라 audit 결과 singleton이며 aggregation을 강제하지 않았다.

20. factorized WAN formulation은 무엇인가?

unique pair + unique WAN start + active/final binary + exact remaining/sent byte recurrence + continuous site/link routing이다.

21. source×destination×time binary를 제거했는가?

예. joint pair×start binary는 0개다.

22. migration pair는 어떻게 선택하는가?

pair source는 선택 y source와 일치하며 pair 합은 checkpoint migration 합이다.

23. transfer start는 어떻게 선택하는가?

job별 wan_start[t] binary의 합이 migration 합과 같아 한 시점만 선택한다.

24. checkpoint보다 먼저 WAN이 시작될 수 있는가?

없다. q→h→source departure 보존식과 nonnegative 상태가 checkpoint 이전 departure를 배제한다.

25. destination이 transfer 도중 바뀔 수 있는가?

없다. unique pair의 destination이 모든 restart-entry와 post-run 상태를 제한한다.

26. maximal-rate semantics는 보존됐는가?

예. nonfinal sent=selected nominal bottleneck rate, final sent=정확한 residual이다.

27. zero-rate waiting은 보존됐는가?

예. zero rate이면 sent=0이며 residual과 active를 유지한다.

28. final partial transfer slot은 동일한가?

예. final partial bytes를 정확히 보낸다.

29. transfer_end는 legacy와 동일한가?

예. final active slot +1이 첫 inactive boundary다.

30. restart_end는 동일한가?

예. transfer_end+frozen restart_slots다.

31. link별 WAN bytes는 동일한가?

예. selected path membership의 exact continuous linearization으로 모든 path link의 bytes가 같다.

32. max active transfer는 동일한가?

예. fixed_active+sum wan_active<=원래 authority다.

33. source compute service는 동일한가?

예. r0 run과 physical checkpoint가 원래 source prefix를 복원한다.

34. destination compute service는 동일한가?

예. full-service 보존으로 destination duration=D-(checkpoint-start)가 강제된다.

35. carryout은 동일한가?

예. frozen latest completion 및 post-H 상태와 full service를 유지한다.

36. new->old reconstruction은 모두 PASS인가?

bounded reverse pool의 모든 해가 inherited validate와 exact transfer-template 검사를 통과했다.

37. old->new mapping은 모두 PASS인가?

bounded 모든 old trajectory를 실제 새 MILP에 고정한 mapping이 통과했다.

38. bounded feasible trajectory set이 완전히 같은가?

예. complete optimal solution pool에서 distinct physical path set이 old full enumeration과 일치했다.

39. six scientific objectives가 모두 같은가?

예. A-J/adversarial 및 complete-domain real subsets에서 여섯 레벨 integer optimum이 허용오차 내 일치했다. 별도로 원래 deterministic tie mapping도 검사했다.

40. 선택한 formulation은 무엇인가?

F2

41. 최종 binary 수는?

2,796,366개다.

42. PR99 대비 binary reduction은?

7,005,709개 감소, 71.472%다.

43. w 계열은 최종 몇 개인가?

joint w는 0개다. 대체 family별 수는 model stats/schema에 있다.

44. build time은?

선택 모델 build 331.1238250999886초다. preparation/support 및 비교 모델 build는 별도다.

45. optimize-only time limit은?

optimize-only 3600초이며 build/validation은 제외된다.

46. target global MIP gap은?

0.005, 즉 original full-problem global MIP gap 0.5%다.

47. first incumbent time은?

null이다. 실행 중 incumbent을 관찰하지 못했다.

48. final incumbent/bound/gap은?

final incumbent=null, bound=0.6716023396111563, gap=null. objective별 원래 globality 범위는 optimization receipt에 기록했다.

49. 원래 full problem의 global 0.5%를 주장할 수 있는가?

아니다. 아직 quality/physical acceptance gate를 모두 만족하지 않았다.

50. 다음 blocker 또는 다음 pipeline 단계는 무엇인가?

다음 blocker는 root 처리 중 incumbent 발견이다. 최종 node count는 1이며 branch tree 성장의 증거는 없다. 행·연속 상태 증가 및 native grid coupling의 원인별 기여는 이번 단일 실행에서 분리하지 않았다. A1은 미승인이고 M1/A2/M2/Fresh AC는 실행하지 않는다.
