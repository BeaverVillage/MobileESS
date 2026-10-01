# PR106 successor: M1 exact sparse compression

M1 accepted=False; nonzero reduction=94.025160%; selected=M1-F3; Threads=1.

## 1. PR106 M1의 진짜 병목은 무엇이었는가?

미완료 ROOT_LP: 1600.32초, 217,222 iterations, node 1.

## 2. binary 208k가 주 병목이라는 증거가 있는가?

없다. 현재 측정은 root LP와 반복 grid 행렬이 병목임을 보여 준다.

## 3. baseline nonzero는?

138,620,454.

## 4. presolved nonzero는?

32,447,186.

## 5. 가장 큰 row family는?

line_thermal_face: 403,968 rows / 112,597,568 nonzeros.

## 6. 가장 많은 coefficient occurrence를 가진 variable family는?

Q: 45,808,436회. Pch/Pdis는 각각 45,797,854회.

## 7. MESS P/Q 표현이 몇 번 반복됐는가?

grid의 Pch/Pdis 계수 91,291,680회, Q 계수 45,665,364회.

## 8. site/time P_MESS는 어떻게 정의했는가?

P_MESS[s,t] = sum_m(Pdis[m,s,t] - Pch[m,s,t]); exact equality.

## 9. site/time Q_MESS는 어떻게 정의했는가?

Q_MESS[s,t] = sum_m Q[m,s,t]; exact equality.

## 10. 이것이 approximation인가?

아니다. 유일한 affine auxiliary 값으로 정의한 exact extended formulation이다.

## 11. line response factorization은 어떻게 했는가?

각 line P/Q와 기존 current correction을 한 번씩 equality로 묶고 모든 16면을 보존했다.

## 12. transformer factorization은?

binding+downstream nonzero가 줄어드는 P/Q response만 선택했다. 한 번 사용하는 current는 그대로다.

## 13. voltage factorization은?

affine voltage를 한 번 묶는다. F4는 두 짧은 행, FCRA는 동일한 robust squared variable bounds를 사용한다. 선택된 M1-F3에서 voltage response factoring 사용=False; 미선택이어도 F4/FCRA 구현과 exactness 검증은 완료했다.

## 14. auxiliary가 늘었는데 왜 더 빠를 수 있는가?

추가 continuous column보다 반복되는 coefficient를 훨씬 많이 제거한다. 실제 속도는 LP와 root canary로 확인했다.

## 15. original physical feasible set은 동일한가?

실수 계수에 대한 old→new와 new→old 대입 증명으로 integer 및 LP projection 모두 동일하다.

## 16. bounded equivalence는 PASS인가?

PASS. 20개 fixture, 6개 후보, 모든 완전 route pattern의 feasibility/P1/P2를 비교했다. continuous fiber는 equality 제거 증명으로 동일하다.

## 17. PR106 incumbent를 정확히 재현했는가?

PASS. 모든 후보 full matrix에서 동일 route/P/Q/SOC/rho를 exact auxiliary 값으로 확장해 검증했다.

## 18. AIDC anchor는 동일한가?

동일한 PR106 accepted anchor/handoff/CC4/Runtime을 byte 보존했다. A1 optimize 0회.

## 19. route domain은 동일한가?

동일하다. 원본 native route constructor를 byte 변경 없이 사용한다.

## 20. SOC physics는 동일한가?

동일하다. 초기/종단 equality, 효율, 여행 에너지, 개별 recurrence를 보존했다.

## 21. PCS16은 동일한가?

동일한 individual inner16, 연결 상태, 400 kVA. site aggregation으로 PCS를 대신하지 않았다.

## 22. robust voltage band는 동일한가?

동일한 0.955–1.045, squared bounds 0.912025–1.092025.

## 23. selected formulation은?

M1-F3

## 24. 새 binary 수는?

208,312

## 25. 새 continuous 수는?

108,431

## 26. 새 row 수는?

954,560

## 27. 새 nonzero 수는?

8,282,350

## 28. nonzero는 몇 % 줄었는가?

94.025160%.

## 29. 최대 row density는 얼마나 줄었는가?

전체 최대 602 (원본 602): 가장 조밀한 SOC row는 변경하지 않아 최대값은 유지한다. P99는 289→49.0; grid row density는 family census 참조.

## 30. numerical coefficient range는?

{"min_abs": 1.0006451962467139e-13, "max_abs": 400.0, "ratio": 3997420879052299.5}

## 31. scaling을 사용했는가?

사용하지 않았다. exact MW 변환의 양방향 식을 감사했으나 warning 감소/속도 개선의 선택 근거가 없어 원 단위를 유지했다.

## 32. root LP diagnostic 시간은?

production root LP 180.04초, completion=True. 별도 연속 LP wall은 P1_LP_RELAXATION_COMPARISON.csv, 전체 root 처리 wall은 1787.3630481000046초.

## 33. PR106 1600.32초 대비 몇 배인가?

8.888691401910686배의 관측 시간 비율. PR106 root는 미완료이므로 동일한 최적 완료 작업의 speedup으로 해석하지 않는다. Method 변경 효과도 포함하므로 matrix 압축만의 causal speedup이라고 주장하지 않는다.

## 34. root bound strength는 동일한가?

exact LP projection 동일; 완료된 diagnostic LP objective spread=2.5600044306628433e-10. Actual MIP root bound/cuts는 별도 기록한다.

## 35. Threads는 몇 개인가?

1

## 36. 왜 그 Threads를 선택했는가?

Actual single-thread MIP root LP completed within 300s; no four-thread test. Root cut/processing wall reported separately.

## 37. PR106 incumbent를 MIP start로 넣었는가?

검증된 전체 PR106 incumbent와 exact auxiliary 값을 Start로 입력했다. 변수 고정/도메인 제한은 없다.

## 38. Gurobi가 accept했는가?

True

## 39. first incumbent 시간은?

0.05214699998032302초.

## 40. P1 UB는?

0.6696147314213984

## 41. P1 LB는?

0.5718494710510547

## 42. P1 gap은?

14.600225441%

## 43. 0.5%를 달성했는가?

False

## 44. P2까지 실행됐는가?

실행 pass 수=1, P2 complete=False. P1 quality 실패 시 P2를 실행하지 않았다.

## 45. movement energy/count는?

incumbent movement energy/count = 0 kWh / 0; P2 완료=False.

## 46. physical validation은?

True

## 47. robust voltage validation은?

PASS=True; voltage min/max=0.9549999999996363 / 1.0449999999997646.

## 48. Q saturation은 최종 accepted 해에서도 남는가?

accepted=False; connected incumbent Q active=1.0, median=0.9807852804032396, P95=0.9807852804032413, max=0.9807852804032435, near-cap=0.6067708333333334. 미수락이면 accepted 해의 결과라고 주장하지 않는다.

## 49. node83.2 slot79 전압은?

1.0407128548060747 pu; robust resolved=True.

## 50. 다음 병목은 무엇인가?

POST_LP_ROOT_PROCESSING; 결과 후 같은 작업에서 과학 모델을 재설계하지 않았다.
