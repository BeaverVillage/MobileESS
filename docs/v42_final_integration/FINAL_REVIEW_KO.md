# V42 최종 인터페이스 검토

**판정: 인터페이스·증거 재현은 검증됐으나, 새 May-01 필요조건이 불가능하여 A1 전에 중단했다. Native 활성화는 OPEN이다.** 아래 구현 완료는 accepted native plan 또는 paper 결과 완료와 구분한다.

1. 최종 nominal provider는 `V10::T3_ISOTONIC_ROLLING14_calibrated`, Q50 seconds이다. 사용자가 승인한 matched fold5 모델·전처리·March31 상태의 별도 V42 study bundle이다.

2. 사용자가 현재 architecture 선택을 승인했다. Logistic와 거의 같은 MAE에서 pooled median calibration, aggregate time ratio, 장시간·시간구간 calibration 근거를 사용했다. 새 후보 검색은 없다.

3. 동일 230,237개 작업에서 Q50 MAE=**2.7273504878654937 h**를 재현했다.

4. Q50 coverage=**46.78744076755691%**이다. Fold 범위 36.3484–63.0782%, >12h 19.0128%도 별도 기록했다.

5. Q50은 조건부 중앙값이므로 calibration 기준은 50%이다. 90% planning reserve 목표와 다른 지표다.

6. Q50 aggregate time ratio=**0.853214958316662**이다. Intrinsic 지표에 GPU 가중치를 넣지 않았다.

7. Runtime 모델·Isotonic map을 재학습/재보정하지 않았다. Fold5 저장 parameter와 Q50 재현의 최대 절대오차는 각각 0이다.

8. PR94 `SELECTED_RUNTIME_MODEL=NONE`을 변경하지 않았다.

9. PR95 `PRIMARY_NOMINAL_RUNTIME_CANDIDATE=NONE`도 소급 변경하지 않았다. 현재 승인한 study authority를 별도로 저장했다.

10. Q90을 hard runtime duration으로 사용하지 않는다.

11. Q50–Q90 alpha 보간은 없다.

12. Planning runtime reserve는 empirical overrun survival과 단일 gamma의 site-local compute headroom이다. 전력 소비나 두 번째 runtime prediction이 아니다. 선형 P2 어댑터와 입력은 구현했으나 May full MILP에서는 아직 미실행이다.

13. 사용자 후속 승인에 따라 저장된 causal OOF fold1–4로 survival/gamma를 동결하고 fold5를 한 번 검증했다. gamma90=**2.423057443558147**, CAL coverage=90.0086806%, holdout=91.2431319%이다. March31 map을 과거에 소급하지 않았고 holdout 후 gamma를 바꾸지 않았다.

14. 용량의 90%를 비워두는 규칙이 아니다. OOF submission-cohort 시스템 동시 overrun의 약 90% coverage를 목표로 한다. 실제 전체 클러스터·site별 90% 보장은 아니다.

15. Actual runtime reserve는 없다.

16. 관측 RUNNING을 유지한다. 여유가 없으면 새 PENDING start를 거부하여 허용된 지연·배치·repair 계층에서 처리해야 한다. 이번에 native Actual replay를 실행하거나 repair 성능을 입증하지 않았다.

17. Q50 종료 뒤에도 관측 완료 전까지 full gang GPU를 계속 점유한다. Q50 expiry로 completion/requeue를 만들지 않는다.

18. 완료가 관측된 event 이후 첫 유효 900초 control boundary에서 반환한다. 정확히 boundary인 경우 해당 boundary에서 반환 가능하다.

19. Known PENDING은 동일 frozen V10 Q50 total seconds를 사용한다. Physical 현재 점유는 0이고, 향후 selected service는 full gang reservation이다.

20. Known RUNNING은 `max(Q50-elapsed,0)` nominal remainder와 현재 hard physical full gang을 구분한다. Expired Q50의 미래 불확실성은 planning reserve로 표현하며 최소 1-slot 서비스를 꾸며내지 않는다. 44개 외부 미배정 기록에는 기존 source exception을 유지한다.

21. D-1 미제출 unknown에는 individual Runtime prediction이 없다. CC4 aggregate만 존재한다.

22. 실제 제출 후 관측 metadata를 이용해 같은 frozen V10 Q50을 호출한다. Event 시점보다 늦은 제출이나 future outcome feature는 거부한다.

23. Known/unknown submitted job의 provider는 동일하다. 동일 metadata에 동일 Q50이 나오는 live inference test를 통과했다.

24. Actual occupancy에 runtime reserve를 다시 더하지 않는다.

25. CC4 출력은 해당 시간에 제출될 작업의 **lifetime GPUh**이다.

26. 새 인터페이스에서 same-hour GPUh/1h 직접 GPU binding을 제거했다. 기존 PR93 증거는 바이트 그대로 두고 supersession sidecar로 표시했다.

27. First-fold TRAIN cutoff 2024-10-18 이전에 관측 완료된 371,713개 작업의 실제 GPU-second를 제출 상대 900초 bin에 정확히 배분했다. 151개 censored/unobserved-end 기록의 미래 실행을 만들어 넣지 않았다. CC4 모델 자체는 바꾸지 않았다.

28. 6,729-slot kernel 합은 0.9999999999999999이다. Full empirical tail을 보존하며 96-slot 이후 kernel mass는 24.5127%이다.

29. 시간 cohort GPUh를 hour-start에 두고 kernel과 convolution한 뒤 0.25h로 나눠 15분 평균 GPU occupancy로 바꾼다. May unknown nominal은 D-day 3,697.092936 GPUh, post-H 1,806.348536 GPUh이다.

30. `max(W90-W50,0)`에 같은 lag kernel을 적용해 compute reserve target으로 쓴다. Realized electrical load로 부르지 않는다.

31. 제출마다 `GPU*Q50/3600`을 해당 cohort의 Q50/Q90에서 각각 한 번 차감하고 0 아래로 내리지 않는다. Hour close에는 남은 익명 cohort를 만료시키고 explicit job은 유지한다.

32. 중복 job ID를 거부하고 explicit+remaining nominal 및 overforecast/closed-hour 경우를 검증했다. 실제 제출량이 forecast를 초과하면 explicit workload는 보존한다. 전달한 May ledger는 D-1 초기 상태이며 May Actual 제출 replay는 하지 않았다.

33. Midnight는 deadline이 아니다. Full service, nominal reservation tail과 CC4 post-H mass를 보존한다. D-day kernel로 post-H 전기 안전을 주장하지 않는다.

34. 기존 source-authorized remaining service가 D00 전에 끝나는 44 UNASSIGNED RUNNING을 외부 unresolved ledger에 보존했다. 사이트·observed completion을 만들지 않았다.

35. Source service가 active horizon에 겹치는 미배정 RUNNING은 fail closed한다. 현 source population에서 해당 overlap은 0이다.

36. Episode ledger는 job/episode/initial site/start/현재 상태와 승인 migration receipt를 보존한다. RUNNING site rewrite와 receipt 재사용을 거부한다. Native event replay까지 완료한 것은 아니다.

37. Runtime>=15min은 timeshift 기준이 아니다. Standby shortcut도 없다.

38. TRAIN의 동일 cohort에서 `Q50(W-age | W>age)`이고 N_cond>=100, PENDING/nonprotected만 허용한다. Budget은 seconds/900의 floor이다. May 결과를 보고 support나 분위수를 바꾸지 않았다.

39. Q50 local-support 재검사 후 1,605 admitted jobs 중 TS=0(0%), PS=1,395(86.9159%), MG=1,122(69.9065%)이다. Nominal GPUh share는 각각 0%, 79.5516%, 97.2124%. FLEX=1,493, FIX=112이다. **후보 mask**이며 global feasible witness·selected action 비율이 아니다. 기존 requested-duration mask는 forensic receipt로 별도 보존했다.

40. 기존 AIDC의 complete-option binary는 start/site/optional one-migration을 공동 표현하고 singleton은 상수다. 새 nominal/risk 입력은 canonical view로 분리했다. 이번 native model 생성은 필요조건 실패로 실행하지 않았다.

41. 기존 MESS는 route/stay flow·movement/connection timing binary와 Pch/Pdis/Q/SOC를 공동 결정한다. Native 새 plan은 없다.

42. 연결 시 P/Q 둘 다 decision variable이고 transit에서는 둘 다 0이다. 기존 constructor의 회귀 테스트를 유지했다.

43. 16-face inner PCS polygon을 유지했다. Constructed regression models에서 quadratic constraint/objective, SOS, general constraint가 0임을 확인했다. 미생성 native model의 통계를 0으로 채우지 않았다.

44. A1/M1/A2/M2 모두 **NOT_RUN**, solve time/gap/bound/incumbent/node/presolve는 null이다. 예정 cap600s/optimize, target gap0.001이다. 두 느슨한 LP와 analytic certificate의 시간은 별도 receipt이며 native scalability로 제시하지 않는다.

45. Native complete-option expansion 전에 exact-safe 필요조건이 실패했다. 따라서 raw/retained option 수·binary reduction은 미측정/null이다. 100% prescreen 감소 또는 속도 향상을 주장하지 않는다.

46. **회복되지 않았다.** 05:00 AEST에서 known443 GPU 중 최대75개 gang(102 GPU)을 중단시켜도 341 GPU가 남는다. 새 CC4 nominal454.2690276을 더하면 795.2690276 GPU로 용량780보다 15.2690276 높다. Full resumed service, TS=0, WAN1, restart_end<120에서 성립하며 reserve를 0으로 완화해도 깨진다. 이전 같은시간 GPUh 오류와 다른 원인이다.

47. Accepted final plan이 없으므로 Fresh AC/OpenDSS 미실행이다. Vmin/Vmax/loading/new violations는 null이며 stale AC를 재사용하지 않았다.

48. Final response kernel은 생성·동결하지 않았다. `FINAL_RESPONSE_KERNEL_AUTHORITY.json`도 만들지 않았다.

49. 현 final kernel이 없으므로 upstream SHA-binding 완료 주장은 없다. Gate는 accepted M2와 matching Fresh AC 및 workload/placement/runtime/MESS P-Q/grid-anchor SHA를 모두 요구한다. 기존 April/B0 kernel은 final authority가 아니다.

50. 문제 1/2/3/4/5/6/8/10을 **모두 native end-to-end CLOSED라고 판정하지 않는다**. 이 작업에서 닫힌 하위 계약은 nominal provider 재현/동결, causal OOF reserve, CC4 단위·mass 보존, depletion·관측 state/episode 규칙, conditional-wait 규칙과 필요조건 판정이다. Accepted workload placement·site-local reserve의 전체 MILP binding, native state/event replay, 전기 성능·Fresh AC·response kernel, 4-block scalability는 OPEN이다. 특히 문제4의 전체 historical episode mapping을 이번 unit test로 소급 승인하지 않으며 문제10의 native runtime/gap은 미측정이다. 새 source-backed 해결 권한 없이 TS/WAN/restart/capacity/서비스를 완화하지 않는다.

검증 내역과 바이트 보존 범위는 `VERIFICATION.json` 및 `LEGACY_PRESERVATION_AUDIT.json`을 참조한다. Holdout reserve burden은 466,167.26436 GPUh, uncovered 4,393.39009 GPUh, 최대 uncovered 215.09898 GPU이며 날짜별 값은 `RUNTIME_RESERVE_TEMPORAL_VALIDATION.csv`에 있다. 이 burden은 원래 historical system 규모에서 측정했으며 May 780 GPU에 맞춰 scaling하지 않았다.
