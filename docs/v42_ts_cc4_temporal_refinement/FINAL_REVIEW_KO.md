# V42 TS / CC4 temporal refinement 최종 검토

1. 아니다. Runtime, CC4, TS, CC4 timing 모두 새 ML 학습은 FALSE이다.

2. 정확 cohort와 W>age 조건이 support를 줄였다. 이번 PENDING age는 120,931~291,228초이고, L4에서도 N_cond가 3/8/50뿐이라 단순 세분화만이 원인은 아니다.

3. L0=qos/protected/partition/workload_class/gpu_bucket/wall_bucket/requested_nodes; L1은 nodes 제거, L2는 partition 제거, L3은 workload_class 제거, L4는 gpu_bucket 제거이다. L4 이후 backoff는 없다.

4. 합치지 않았다. 모든 level에 QoS와 protected가 남고 high/urgent/protected는 fail-closed이다.

5. 최소 N_cond=100이다. W>age를 만족하는 TRAIN 관측만 센다.

6. 0/1,605건, 0%이다.

7. 0/10,582.75 nominal reserved GPUh, 0%이다.

8. 선택된 level이 없다. 1,395건 모두 L4까지 조회했지만 support에 실패했다.

9. 1,395건이다. 다른 210건은 state/protection 경계에서 제외됐다. age-cap 실패는 0건이다.

10. 아니다. 결과는 여전히 TS=0이며 preregistered rule을 결과 확인 뒤 바꾸지 않았다.

11. 사용하지 않았다. Runtime>=15min도 standby shortcut도 없다.

12. CC4 ML과 B0/C0 Q50/Q90 forecast 값은 변경하지 않았다.

13. 버리지 않았다. 기존 6,729-slot kernel의 bytes/mass를 그대로 보존했다.

14. 고정 equality 대신 비음수 x[h,t], 누적 Q10/Q90 envelope, work conservation, carryout과 soft L1 reference-deviation을 사용한다.

15. GPUh이다. 15분 slot GPU는 GPUh/0.25이다.

16. 각 cohort마다 active x의 합+carryout=remaining W50이다. 저장된 LP witness에서도 검증했다.

17. 보존한다. 24:00은 전기 평가 경계이며 workload completion deadline이 아니다.

18. 기존 kernel과 동일한 fold1 TRAIN parquet에서 완료된 submission-hour cohort 3,748개의 정확 GPU-second overlap CDF를 계산했다. 불완전 21개와 zero-work 4개를 제외했다. lag별 observed support만 사용했다.

19. 사용자가 지정한 단 하나의 preregistered Q10/Q90이다. 다른 폭을 시험하지 않았다.

20. May outcome을 사용하지 않았다. May 입력은 이미 알려진 issue metadata와 기존 forecast만 읽었다. VALID tuning도 없다.

21. 없다. 지원 lag의 모든 cumulative lower/upper bound가 선형 제약이다.

22. P1 grid security와 P2 reserve shortfall 다음, 기존 migration/shift/placement/tie 이전이다.

23. TS는 이미 제출된 개별 PENDING job의 empirical 추가 대기 budget이다. CC4는 아직 개별 identity가 없는 anonymous aggregate GPUh의 서비스 시점이다.

24. 유지한다. DeltaW=max(W90-W50,0)을 별도 동일 envelope timing target으로 다룬다. reserve는 IT load가 아니다.

25. 유지한다. ForecastBook을 수정하지 않았고 제출마다 한 번만 감소하며, explicit job과 중복 계산하지 않는다. 현재 자료는 D-1 initial ledger이며 event replay 완료 주장은 없다.

26. V10 T3 Isotonic Q50 provider와 기존 파일 모두 그대로이다.

27. gamma90=2.423057443558147 그대로이다. 기존 CAL 약90.01%, fold5 약91.24% 검증값을 다시 보정하지 않았다.

28. 780 GPU 그대로이다. capacity scaling, gang 완화, job drop은 없다.

29. 795.2690276>780의 PR96 05:00 증거는 byte-preserved이다. 새 receipt에만 SUPERSEDED_BY_TS_AND_CC4_TEMPORAL_FLEXIBILITY_INTERFACE라고 표시했다.

30. 독립 slot 하한의 최댓값은 2025-05-01 23:45 AEST, Dday slot95/issue slot119이다.

31. 해당 slot known GPU lower bound는 509이다.

32. 해당 slot의 minimum anonymous CC4 GPU는 0이다. 이 개별 slot 최소가 모든 slot에서 동시에 성립한다는 뜻은 아니며 별도 joint LP를 통과했다.

33. TS relief는 0 GPU이다.

34. 최대 necessary lower bound는 509 GPU이다.

35. 진단용 하한은 780 이하이고 joint necessary LP도 PASS이다. full native feasibility를 뜻하지 않는다.

36. reserve=0으로 명시한 diagnostic relaxation은 PASS이다. full A1 adapter에는 실제 Runtime/CC4 Planning reserve target과 P2 shortfall을 유지했다.

37. 필요조건 PASS에 따라 A1 실행이 authorized되었다.

38. A1 worker를 실행했다. 그러나 600초 bounded complete-option 생성에서 중단되어 full model과 optimize()는 실행 완료되지 않았다. 종료=EXTERNAL_HARD_WALL_TIMEOUT.

39. A1 accepted incumbent가 없어서 M1/A2/M2는 NOT_RUN이다. 단계 순서를 건너뛰지 않았다.

40. A1 partial build wall=600.016000초. solve time/gap/bound/nodes/최종 binary·continuous·presolved size는 null이다. 마지막 관측은 325 / 1499 jobs, retained options 92656; 미완료 job의 수를 최종 총수로 해석하지 않는다.

41. Fresh OpenDSS AC는 NOT_RUN이다. accepted four-stage plan이 없다.

42. 최종 response kernel을 만들거나 freeze하지 않았다. FINAL_RESPONSE_KERNEL_AUTHORITY.json은 없다.

43. 테스트와 necessary LP witness에서 conservation violation은 없다. 아직 native accepted plan의 전역 conservation 완료를 주장하지 않는다.

44. 새 통계는 TRAIN만 사용했다. May future outcome read는 없고, 기존 retrospective case-study authority의 한계를 그대로 유지한다.

45. 없다. TS 비율, envelope 폭, gamma, capacity를 결과에 맞춰 조정하지 않았다.

46. TS hierarchy audit, TRAIN timing-envelope construction, linear service/carryout/deviation interface, 새 necessary-condition 판정과 legacy preservation 하위 문제를 닫았다. 전체 native execution은 아니다.

47. Problem 3을 end-to-end CLOSED라고 판단하지 않는다. 개별/aggregate 시간 유연성 interface는 구현됐지만 native accepted schedule이 없다.

48. Problem 8도 end-to-end CLOSED가 아니다. MESS/전력/AC를 포함한 accepted 실행 검증이 남아 있다.

49. Problem 10은 후보 생성의 bounded failure wall을 측정했다. native optimizer runtime/gap와 전체 A1/M1/A2/M2 scalability는 아직 측정할 수 없다.

50. 다음 blocker는 A1_COMPLETE_OPTION_GENERATION_600S_TIMEOUT이다. 기존 complete-option 생성이 600초 안에 완료되지 않는다. 이는 새 resource infeasibility 증명이 아니다. 추가 rescue나 solver sweep 없이 중단했다.
