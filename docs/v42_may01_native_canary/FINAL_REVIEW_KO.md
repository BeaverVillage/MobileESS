# May-01 native canary 최종 검토

1. Known/unknown 모두 PENDING 현재 물리 GPU=0, RUNNING=전체 gang이다. RUNNING의 기존 native site와 causal elapsed/remaining을 보존했다.

2. 구분했다. 현재 Planning에서 선택한 실행 구간은 전체 gang을 예약하며, 과거 PENDING 계획은 현재 물리 점유가 아니다.

3. 없다. 모든 PENDING current_physical_occupancy=0. 현재 미래 예약은 별도 ledger에 남아 있다.

4. 321개 모두 물리 충돌로 해석할 근거가 사라진다. 단 PR79 원본은 미래 예약 충돌 표였으며, 그 표의 계획 충돌이 해결됐다고 주장하지 않는다.

5. 해당 321개 구간 중 true RUNNING 물리 충돌은 0개. 원래 계획 예약 충돌 321개는 그대로 미해결이다. 별도로 May-01 known+C0 자원 필요조건이 infeasible이다.

6. 321개 모두 PENDING 과거 예약과 물리 상태의 혼동 가능성이 분류 A이고 계획 관점은 C이다. B/D/E 물리 충돌은 0개. May-01의 별도 blocker는 고정 start, known full service, C0 nominal, 780-GPU cap의 동시 양립 불가다.

7. 아니오. RUNNING native site를 변경하지 않았다. PR79 반사실 mapping을 May native site에 덮어쓰지 않았다.

8. 아니오. GPU clipping/scaling/splitting은 없다.

9. 아니오. 입력 service/tail은 모두 보존했다. 불가능성 증명용 superset의 부하 제거는 실행 계획으로 승인되지 않았다.

10. 아니오. completion/requeue를 발명하지 않았다. UNASSIGNED 44개도 관측 완료로 판정하지 않았다.

11. 그렇다. D24=issue slot120은 전기 horizon 경계이며 서비스 종료 deadline이 아니다.

12. 보존했다. source-admitted 원래 예약의 post-H GPUh=17229.50. 선택된 새 계획은 없다.

13. T2_CONSERVATIVE_Q25: TRAIN cohort N>=100, Q25>=900초, floor(Q25/900)*900초 지연 예산. 보호/RUNNING 제외. standby 예외 없이 동일 문턱 적용. SLA가 아닌 trace-derived proxy다.

14. 아니오. 기존 pre-2025-01-01 TRAIN 통계와 membership hash를 그대로 사용했다. May는 적용 대상일 뿐 통계/규칙 조정에 쓰지 않았다.

15. TS job share=0/1605=0%. 모든 PENDING의 해당 TRAIN Q25가 900초 미만이다.

16. TS reservation GPUh share=0/40625.50=0%.

17. PS 1395/1605 jobs (86.9159%), 22530.25/40625.50 GPUh (55.4584%). 이는 source-authorized candidate mask이며 전역 feasible witness가 아니다.

18. MG 1603/1605 jobs (99.8754%), 40575.50/40625.50 GPUh (99.8769%). 이는 checkpoint/site candidate mask이며 전역 WAN/resource feasible witness가 아니다.

19. Union FLEX 1603/1605 jobs (99.8754%), 40575.50/40625.50 GPUh (99.8769%). 전역 실행 가능 비율로 해석하면 안 된다.

20. FIX 2/1605 jobs (0.1246%), 50.00/40625.50 GPUh (0.1231%). 세 candidate mask가 모두 false인 assigned 기록이다.

21. 44개 UNASSIGNED RUNNING. 전체 1649개 중 2.6683%; frozen remaining service는 D00 이전 종료로 표현되지만 실제 완료는 주장하지 않는다. 완전한 issue 물리 site authority는 unresolved이다.

22. MAY01_NATIVE_INPUT_BUNDLE.json 및 manifest. V41R3 저장소의 frozen May-01 known reference, V41R4 final alpha_BG=1.15 IEEE123 계수, V41R2 780-GPU/rack, exact traffic/MESS, frozen C0를 SHA로 연결했다.

23. IEEE123이다. IEEE8500은 실행하지 않았다.

24. May-01 동적 입력과 source-backed static authority를 구분했다. 사라진 경로는 SHA가 같은 파일로만 복구했다. PR79 historical mapping과 혼합하지 않았다. full grid/MESS model 결합 검증은 upstream infeasibility로 미실행이다.

25. 그렇다. current frozen T0/B0 C0 Q50와 Q90, May-01 index412. Q50는 same-hour nominal, Q90-Q50만 P2 uncertainty다.

26. 아니오. semantic ML merge/학습은 없다.

27. 아니오. 기존 known service authority를 사용했다. RUNTIME_PROVIDER_READY=false는 이번 known-population 검사 차단 사유가 아니다.

28. 아니오. future realized runtime/completion을 decision에 사용하지 않았다. causal elapsed, frozen known service, TRAIN 통계만 사용했다.

29. 1605개 native admitted population을 자원 필요조건 모델에 연결했다. complete-option AIDC/grid MILP 전체를 구축·실행했다고 주장하지 않는다.

30. PR91 inner16 MILP 구현은 그대로 보존하고 회귀 검증했다. native M1/M2 모델은 A1 infeasibility 때문에 구축하지 않았다.

31. 보존된 MESS formulation/test의 QConstr=0. native M1/M2 실제 QConstr 측정값은 null(미구축); 둘을 구분했다.

32. 전체 A1 크기는 null. 필요조건 LP만 continuous=1605, binary=0, rows=97, nonzeros=62024로 측정했다.

33. M1 전체 모델 크기 null: upstream A1 infeasibility로 미구축.

34. A2 전체 모델 크기 null: upstream A1 infeasibility로 미구축.

35. M2 전체 모델 크기 null: upstream A1 infeasibility로 미구축.

36. raw/retained 옵션 및 reduction은 null. 전역 exact-safe 필요조건이 먼저 infeasible이어서 개별 complete-option 열거까지 진행하지 않았다. null을 0 또는 100%로 대체하지 않았다.

37. A1 자원 검사 외부 wall=5.062s, solver=0.012000s, status=INFEASIBLE. 전체 A1 runtime/gap=null. 최초 파일출력 실패도 보존했다.

38. M1 NOT_RUN_UPSTREAM_A1_INFEASIBLE, runtime/gap=null.

39. A2 NOT_RUN_UPSTREAM_A1_INFEASIBLE, runtime/gap=null.

40. M2 NOT_RUN_UPSTREAM_A1_INFEASIBLE, runtime/gap=null.

41. 시간 병목 block은 판정 불가. 현재 blocker는 계산시간이 아닌 known+C0 GPU 자원 infeasibility이다.

42. 아니오. A1 incumbent가 없어 A2 미실행. warm start 효과는 측정하지 않았다.

43. 아니오. M1/M2 미실행. warm start 효과는 측정하지 않았다.

44. 아니오. 모든 block의 target은 .001이지만 완료된 full MILP가 없다. LP infeasible에 MIP gap을 만들지 않았다.

45. timeout은 없었다. 60/180/300/600초 gap은 모두 null이며 0으로 대체하지 않았다.

46. 입력 불가능성을 약 5초의 감독된 검사로 조기에 입증했지만, 과거 수시간 MILP의 속도 개선 또는 전체 4-block tractability를 입증한 것은 아니다.

47. 아니오. 최종 accepted candidate가 없어 Fresh OpenDSS를 실행하지 않았다. PASS=false는 미검증을 뜻한다.

48. 승인된 모델/계획의 hard physical limits를 완화하지 않았다. 수학적 superset은 infeasibility 증명에만 사용했고 실행 계획으로 채택하지 않았다.

49. 현재는 아니다. accepted final planning과 Fresh PASS 이후에만 해당 anchor의 response kernel 재생성이 필요하다. kernel은 이번 planning 선행조건으로 삼지 않았다.

50. Round1 준비 미완료. TS=0 fixed starts와 C0 nominal의 GPU 필요조건이 28개 슬롯에서 깨진다. 최악 excess=456.672583 GPU. 이 source-bound 양립 문제를 정식 authority로 해결한 후 full 4-block/Fresh 검증이 필요하다. 임의 규칙 완화는 하지 않았다.
