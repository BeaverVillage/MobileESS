# Compact AIDC state-flow 최종 검토

1. PR98은 도메인 생성 후 complete trajectory마다 binary를 추가하는 모델 구축에서 600초 제한에 걸렸다. optimize()는 호출되지 않았다.

2. 349,215,815는 전체 1,499 positive-service job의 승인된 완전한 물리 trajectory 수다.

3. start/site/checkpoint/destination/transfer-start를 곱한 trajectory마다 변수를 만들면 모델 구축이 과도해진다. 같은 경로 집합을 사건과 상태로 표현했다.

4. 그렇다. y/q/w/f0/f1은 binary, r0/h/r1은 [0,1] 연속변수이며 모든 제약은 선형이다.

5. 96개 전기적 slot을 하나의 joint MILP로 다룬다. 별도 서비스 축의 pre-H/post-H 구간도 보존한다.

6. 아니다. 모든 job을 GPU/WAN/grid/reserve 제약으로 결합한다. 작은 개별 테스트는 검증용이다.

7. y는 승인된 시작 slot과 초기 site를 선택한다. 실제 singleton은 상수로 대체한다.

8. r0는 migration 이전 source에서 계산 중인 slot 상태다.

9. q는 source 계산을 종료하는 승인 checkpoint 사건이다. destination과 transfer-start index가 없다.

10. h는 checkpoint 이후 WAN 시작 전 대기 상태다. GPU/WAN을 소비하지 않는다.

11. w는 source/destination/transfer-start 사건이다. checkpoint index가 없다.

12. r1은 결정된 restart_end부터 destination에서 계산하는 상태다.

13. f0는 비이동 완료, f1은 이동 후 완료 사건이다. 최종 site/time으로 Runtime risk를 계산한다.

14. q에서 h로 들어가고 w에서 h를 빠져나오는 보존식으로 연결했다. c×tau binary가 없다.

15. 바뀌지 않았다. PR98 transfer cache와 payload/path/rate/zero-rate wait를 그대로 사용한다.

16. 바뀌지 않았다. 1800초 물리 checkpoint와 900초 경계 올림, RUNNING elapsed phase가 같다.

17. 바뀌지 않았다. restart_end=transfer_end+기존 restart_slots다.

18. 바뀌지 않았다. V10 Q50 및 서비스 slot 수를 그대로 사용한다.

19. 바뀌지 않았다. PR98 allowed_starts와 latest_completion을 그대로 소비한다.

20. 1,024건을 유지하며 PR98 결과 파일을 바이트 그대로 보존했다.

21. sum r0+r1=d50와 source/post state conservation으로 서비스 전량을 보존한다.

22. waiting/WAN/restart 동안 r0/r1 계산 상태가 없다. 잘못 삽입한 상태는 실제 MILP 제약 테스트에서 infeasible이다.

23. 불가능하다. 이진 사건의 누적합인 [0,1] 상태는 정확히 0/1이며 한 site에 전체 G_j를 곱한다.

24. 보존된다. completion<=기존 latest_completion이며 D24를 새 deadline으로 만들지 않았다.

25. f0/f1의 final_site 및 issue-adjusted completion에 기존 risk_exposure와 gamma90를 적용해 선형 합산한다.

26. PR97 Q10/Q90, conservation, carryout, reserve timing, depletion, reference deviation을 보존했다.

27. 동일한 C1/grid 함수와 원본 계수 authority를 사용한다. known_GPU의 입력 표현만 r0/r1으로 바뀐다.

28. PASS. 모든 bounded old option의 사건/상태를 실제 compact 모델에 고정해 feasible 및 동일 physical signature를 확인했다.

29. PASS. bounded compact pool을 완전히 열거하고 기존 physical validate 및 old signature set과 비교했다.

30. A-J 전체 fixture에서 경로 집합과 6개 scientific objective 수준이 일치했다. 추가 adversarial/랜덤 물리 fixture도 통과했다.

31. 실제 May의 첫 short-service singleton-start 두 작업을 완전 도메인으로 공동 최적화했다. native grid/CC4와 6개 목적 수준이 동일했다. 다양한 real TS/migration 사례까지 검증했다고 주장하지 않는다.

32. 원래 option index는 비과학적 최종 tie다. 6개 scientific objective를 고정한 뒤 deterministic physical event-rank tie를 적용한다.

33. 6개 수준의 동등성을 검증했다. raw option index tie는 동등성 요구에서 명시적으로 제외했다.

34. 전체 기존 trajectory binary index는 349,215,815개다.

35. 전체 y index는 569,882개다.

36. 전체 q index는 590,221개다.

37. 전체 w index는 6,910,461개다.

38. f0=569,882, f1=1,161,629개다.

39. 전체 sparse event binary index는 9,802,075개다. 이는 모든 graph의 정확한 count이며, Gurobi full model 완성 여부와 구분한다.

40. 35.626723배 감소, 비율 97.193118%, 절대 339,413,740개 감소다.

41. Build PASS=True. 외부 wall=422.407000초. 전체 binary=9,802,075, continuous=2,759,286, 제약=4,070,611, nonzero=119,775,457개다.

42. 별도 presolve는 실행하지 않았다. A1 실행 시 관찰한 callback 정보만 MAY_COMPACT_PRESOLVE.json에 기록하며 정확한 presolved size가 없으면 null이다.

43. optimize() 호출=True. Build-only 실행은 최적화를 호출하지 않는다.

44. 검증/품질 승인된 A1 plan은 없다. Raw incumbent 감사=None.

45. A1 status=TIME_LIMIT, incumbent=None, bound=None, gap=None, nodes=None. 마지막 presolve 관측=164.85055479999573초다. -inf 진단 저장 오류로 최종 Runtime/node 수는 보존되지 않아 null로 남겼다.

46. 측정 blocker는 COMPACT_A1_PRESOLVE_TIME_LIMIT_DIAGNOSTIC_WRITE_FAILURE. 전체 event index 중 WAN w 비중=70.499981%다.

47. accepted A1이 없어 M1/A2/M2는 NOT_RUN이다. A2는 동일 compact job builder와 M1 P/Q anchor 인터페이스를 재사용한다.

48. Fresh AC는 NOT_RUN이다. accepted four-stage gate가 성립하지 않았다.

49. freeze하지 않았으며 FINAL_RESPONSE_KERNEL_AUTHORITY.json은 생성하지 않았다.

50. 정확한 Dantzig-Wolfe/column generation을 다음 후보로 문서화했다. 전역 정수 보장은 완전 pricing 및 branch-and-price가 필요하다. 이번에는 실행하지 않았고 CL-MC-BD도 자동 활성화하지 않았다.
