1. **왜 PR105 A1이 infeasible였는가?**

A1의 MESS P/Q=0에서 고정 affine 전압과 AIDC 부하 허용 범위를 대입하면 robust 상한보다 큰 145개 필요조건 모순이 있었다.

2. **PR105의 145개 contradiction은 여전히 유효한가?**

예. PR105 증거 전체는 byte-identical이며 원래 A1+zero MESS+robust band 조건에서 유효하다. Joint M1 불가능성으로 확대 해석하지 않는다.

3. **왜 0.955/1.045를 바로 완화하지 않았는가?**

최종 robust 계약을 유지하고 명시적으로 승인된 A1 bootstrap 단계만 physical band로 구분했다.

4. **새 A1 voltage band는?**

0.95–1.05 pu; squared 0.9025–1.1025.

5. **A1은 왜 bootstrap인가?**

임시 AIDC 제어/부하 anchor를 만드는 단계다. 최종 robust Planning 수락이 아니다.

6. **M1 voltage band는?**

0.955–1.045 pu; squared 0.912025–1.092025.

7. **A2/M2 voltage band는?**

둘 다 0.955–1.045 pu.

8. **Actual voltage band는?**

0.95–1.05 pu.

9. **Actual Q correction은 다시 켰는가?**

아니오. PR105 제거 상태 유지.

10. **Actual P correction은?**

아니오. PR105 제거 상태 유지.

11. **A1은 새 bootstrap band에서 feasible했는가?**

accepted=True, independent physical PASS=True, native voltage PASS=True.

12. **A1 P1 값은?**

0.6715924043100266

13. **A1 migration은?**

0.0

14. **shift는?**

387.0 (absolute slot displacement)

15. **relocation은?**

221.0

16. **A1 총 optimize time은?**

762.7908469999966 초; build 제외.

17. **1499 known jobs는 모두 복원됐는가?**

handoff=True, known_jobs=1499; 전체 개별 UID/서비스 계획으로 독립 확장·검증.

18. **117 class의 역할은?**

동일한 전체 과학적 권한의 exact class다. Stay integer histogram은 집계하고 migration lane은 개별 유지하며 작업을 삭제하지 않는다.

19. **unknown future pseudo-job을 만들었는가?**

아니오. unknown 미래 개별 UID는 없고 causal site-only policy와 anonymous CC4 상태를 저장한다.

20. **CC4 unknown 영향은 M1 anchor에 들어갔는가?**

True. Nominal anonymous GPU가 전력 anchor에 포함되며 reserve/Runtime은 상태·보고 인터페이스로 동결된다.

21. **M1에서 AIDC는 완전히 fixed인가?**

true

22. **M1 AIDC decision variable 수는?**

0

23. **M1 route가 decision인가?**

예. 원래 time-network route/stay binaries. 실행 여부=true

24. **M1 P가 decision인가?**

예. 연결된 원래 Pch/Pdis 변수, net P=Pdis−Pch.

25. **M1 Q가 decision인가?**

예. 연결된 원래 Q와 PCS inner16.

26. **M1 SOC가 decision인가?**

예. 초기/재귀/범위/terminal SOC 유지.

27. **route/P/Q/SOC가 joint인가?**

예. 같은 native MILP 안에서 route/P/Q/SOC를 joint 결정한다.

28. **M1 preflight에서 0.955–1.045 necessary condition은 PASS인가?**

true; permissive full-P/Q outer condition이며 충분조건이 아니다.

29. **PR105 node83.2 slot79 blocker가 M1에서 해결됐는가?**

true; independent incumbent에서 해결됐다. P1 품질 실패로 M1 수락은 false. Joint 해의 descriptive decomposition이며 Q-alone causal claim은 아니다.

30. **그 cell의 M1 voltage는?**

1.0407128548060747 pu (incumbent).

31. **그때 MESS route는?**

[{"unit": "MESS01", "site": "STA01", "route_origin": "STA01", "route_destination": "STA01", "route_depart": 79, "route_connect": 80}, {"unit": "MESS02", "site": "STA12", "route_origin": "STA12", "route_destination": "STA12", "route_depart": 79, "route_connect": 80}, {"unit": "MESS03", "site": "STA08", "route_origin": "STA08", "route_destination": "STA08", "route_depart": 79, "route_connect": 80}, {"unit": "MESS04", "site": "STA06", "route_origin": "STA06", "route_destination": "STA06", "route_depart": 79, "route_connect": 80}]

32. **MESS P는?**

[{"unit": "MESS01", "P_kw": 0.0}, {"unit": "MESS02", "P_kw": 0.0}, {"unit": "MESS03", "P_kw": 0.0}, {"unit": "MESS04", "P_kw": 0.0}]; aggregate affine contribution=0.0

33. **MESS Q는?**

[{"unit": "MESS01", "Q_kvar": 268.53246005190374}, {"unit": "MESS02", "Q_kvar": -392.31411216129584}, {"unit": "MESS03", "Q_kvar": 74.93950151105054}, {"unit": "MESS04", "Q_kvar": 70.88091367663878}]; aggregate affine contribution=-0.019416753841389918

34. **Q가 PCS capability에 얼마나 가까웠는가?**

{"connected_count": 384, "connected_fraction": 1.0, "Q_active_epsilon_kvar": 1e-06, "Q_active_fraction": 1.0, "median_utilization": 0.9807852804032396, "P95_utilization": 0.9807852804032413, "max_utilization": 0.9807852804032435, "near_cap_threshold": 0.95, "near_cap_fraction": 0.6067708333333334, "formula": "abs(Q)/sqrt(max(S_nameplate^2-P_net^2,0)), connected unit/time only", "diagnostic_only": true, "production_PCS_faces": 16, "Q_penalty": false}; connected unit/time, abs(Q)/sqrt(S²−P²), diagnostic only.

35. **M1 model binary/continuous/rows/nonzeros는?**

{"binary": 208312, "continuous": 27215, "linear_constraints": 873344, "nonzeros": 138620454}

36. **M1 build time은?**

46.421486399980495

37. **presolve time은?**

178.29

38. **root LP time은?**

1600.32

39. **first incumbent time은?**

192.51700199997867

40. **P1 UB/LB/gap은?**

{"M1_P1_INCUMBENT": 0.6696147314213984, "M1_P1_BOUND": 0.28011314354280115, "M1_P1_GAP": 0.5816801357577633}

41. **movement energy는?**

0 kWh (observed incumbent; P2 미실행).

42. **movement count는?**

0 (observed incumbent; P2 미실행).

43. **M1 총 optimize time은?**

1801.1563743999868 초; build 제외, TimeLimit=1800; native termination overshoot 그대로 기록.

44. **M1 physical validation은 PASS인가?**

true

45. **robust 0.955–1.045는 PASS인가?**

true

46. **dominant bottleneck은?**

ROOT_LP; measured receipts 근거, route/SOC/PCS 원인을 추측하지 않는다.

47. **margin을 수정해야 할 직접 근거가 생겼는가?**

아니오. 현재 robust band에서 물리/grid PASS인 joint incumbent가 있다. P1 품질 실패는 전압 불가능성이나 margin 완화 근거가 아니다.

48. **A2를 왜 아직 실행하지 않았는가?**

사용자의 명시적 STOP-after-M1 계약이며, M1 P1 품질 실패로 M1_ROBUST_ACCEPTED=false라 future A2 진입 조건도 충족하지 않았다.

49. **M2도 route/P/Q/SOC full joint인가?**

예. 같은 full joint route/P/Q/SOC constructor와 robust band. Accepted A2 anchor 및 start/domain 검증이 필요하며 이번에는 실행하지 않았다.

50. **Problem 13 최종 검증까지 무엇이 남았는가?**

먼저 M1 P1/P2 quality를 충족하는 accepted M1이 필요하다. 이어 A2 robust 재최적화·독립 검증, M2 full joint robust 최적화·검증, 최종 계획 동결, frozen Actual replay 및 독립 Fresh OpenDSS physical/line/transformer 검증이 남았다. Problem13=false.
