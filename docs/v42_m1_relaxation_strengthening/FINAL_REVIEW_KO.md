# PR108 successor: M1 relaxation strengthening

Tested mode-disjunction and route-energy-pooling mechanisms do not materially explain the current root gap.

Selected=S2; LP LB=0.5722125039436496; gain=0.0003630437418684629; implied gap=14.546010%. M1_ACCEPTED=False.

Baseline fingerprint는 PR108처럼 검증된 MIP start를 적용한 상태에서 비교한다. Gurobi의 signed integer를 unsigned 32-bit hexadecimal로 표시한다. 행/열/nonzero와 default-path incumbent validation도 동일해야 PASS다.

S3의 첫 crossover cleanup은 큰 primal infeasibility가 지속되어 중단했다. 약 1737.4334151744843초의 비용과 원본 로그/소스를 보존했다. 기존 식이 이미 함의하는 G의 [0,Emax] variable bounds만 명시해 동일 LP projection으로 복구했으며, solver 설정은 변경하지 않았다. 비교표의 total LP wall에는 이 중단 시간 추정치도 포함한다.

G bounds 표현 보정 후에도 crossover cleanup에서 큰 dual infeasibility가 반복돼 약 2714.160523891449초의 두 번째 시도를 중단했다. Crossover=0 시도도 약 27 GB factor memory가 예상돼 중단했다. 최종 S3는 기본 Crossover 설정에서 barrier 해를 캡처했고, 전체 solver 상태는 INTERRUPTED(11), BarStatus는 OPTIMAL(2)로 실제 값을 기록했다. S2의 OPTIMAL 하한과 full-matrix feasible BarX를 이용한 optimum interval이 1e-7 이내일 때만 numerical optimality PASS로 판정한다. Method=2/Threads=1 및 모든 MIP proof policy는 유지했다. BarStatus=OPTIMAL, 전체 행렬 residual, dual residual 및 optimum interval 검증을 요구한다. API 캡처 수정 시도를 포함해 S3는 총 5회 optimize를 호출했으며, 네 중단 시도의 비용 추정치를 모두 포함한다. Solver parameter grid/search는 실행하지 않았다.

1. **현재 blocker는 왜 단순 solver runtime 문제가 아닌가?**
동일한 feasible UB가 있고 root LP는 이미 완료되지만, PR108의 두 600초 proof에서 LB가 동일하고 nodes=1이었다. 핵심은 전역 bound 강도다.

2. **PR108 UB는?**
0.6696147314213984

3. **PR108 LB는?**
0.571849460049452

4. **현재 gap은?**
14.600227083478131% (PR108); selected LP implied gap=14.546010251445928%.

5. **0.5%를 위해 대략 어느 LB가 필요한가?**
0.6662666577642914 이상. 동일 UB 기준의 충분 LB 수준이다.

6. **baseline F3 root LP를 정확히 재현했는가?**
PASS. fingerprint=0x9cfd10ec, binaries=208312, continuous=108431, rows=954560, nonzeros=8282350. LP OPTIMAL 0.5718494602017812, 203.379초; 목적값 허용오차 1e-7.

7. **root에서 fractional stay arc는 몇 개인가?**
6766

8. **fractional travel arc는?**
1604

9. **fractional charge_mode는?**
311

10. **한 시점에 최대 몇 site로 fractional split되는가?**
24

11. **route splitting이 얼마나 빈번한가?**
multiple positive stay sites: 97.9167% MESS-slot; fractional travel departure: 75.7812%. LP 진단이며 splitting 자체를 물리 위반이라고 부르지 않는다.

12. **H1/H2/H3 valid inequality는 무엇인가?**
H1: z<=y. H2: ΣPch<=Pmax*z. H3: ΣPdis<=Pmax*(y-z). y=Σx_stay.

13. **baseline root가 H1을 위반하는가?**
{'violation_count': 33, 'maximum_violation': 0.9214467521227543, 'mean_positive_violation': 0.34920865141053337, 'total_positive_violation': 11.523885496547601}

14. **H2를 위반하는가?**
{'violation_count': 247, 'maximum_violation': 168.32760682132601, 'mean_positive_violation': 118.42309560116587, 'total_positive_violation': 29250.50461348797}

15. **H3를 위반하는가?**
{'violation_count': 33, 'maximum_violation': 286.4553991202763, 'mean_positive_violation': 112.18476619283116, 'total_positive_violation': 3702.0972843634286}

16. **최대 위반량은?**
H1은 무차원 mass, H2/H3은 kW. 각 최대값: {'H1': 0.9214467521227543, 'H2': 168.32760682132601, 'H3': 286.4553991202763}; 혼합 단위 최대를 물리량 하나로 해석하지 않는다.

17. **mode hull을 왜 실행하거나 생략했는가?**
baseline 최적점에서 위반이 있어 S1을 실행했다. 위반 발견 자체는 objective 개선을 보장하지 않는다.

18. **mode hull은 integer feasible set을 바꾸는가?**
route/P/Q/SOC의 integer physical projection은 동일하다. transit 중 unused z=1 배정은 H1에 의해 z=0으로 바뀔 수 있다. 전체 auxiliary bit 배정 집합의 동일성은 주장하지 않는다.

19. **energy pooling hypothesis는 무엇인가?**
단일 E[m,t]가 fractional 경로들 사이에서 에너지를 합산하여, 분기별 경로 일관 SOC로 분해되지 않는 dispatch를 허용할 수 있다는 가설이다.

20. **fixed-root energy-flow LP는 feasible했는가?**
feasible=False; certified infeasible=True; status=3. IIS도 저장했다.

21. **infeasible이면 무엇을 의미하는가?**
이 고정 baseline optimum의 x/Pch/Pdis는 동일한 Emin/Emax/초기/terminal 조건의 path-consistent arc-energy flow로 확장될 수 없다. MESS01/STA02/t=71–86의 node 식을 합하면 운반 가능한 에너지 범위보다 49.98350934959893 kWh 더 방전해야 하는 독립 산술 모순이 나온다. 허용오차 크기의 충돌이 아니다.

22. **feasible이면 왜 S2를 실행하지 않는가?**
feasible이면 같은 optimum이 추가식에서도 남으므로 그 식만으로 root 목적값을 높일 수 없다. 이번에는 infeasible이므로 S2를 실행했다.

23. **arc-energy G 변수의 물리적 의미는?**
fractional arc의 출발 노드에서 운반되는 에너지 mass, 단위 kWh.

24. **travel arc에서 energy는 어떻게 변하는가?**
A=G-travel_energy*x.

25. **stay arc에서 energy는 어떻게 변하는가?**
A=G+0.25*(0.95*Pch-Pdis/0.95).

26. **terminal SOC는 어떻게 보존되는가?**
terminal H 노드의 incoming A 합을 battery.terminal=760 kWh로 고정하고 원본 terminal SOC equality도 유지했다.

27. **S2가 original SOC를 대체했는가?**
대체하지 않았다. 원본 SOC 변수와 모든 recurrence를 유지한 추가 강화다.

28. **integer physical projection equivalence는 PASS인가?**
True; 구성적 증명과 20개 사례의 모든 tiny route path 비교를 함께 기록했다.

29. **PR108 incumbent는 모든 candidate에서 feasible한가?**
True; 각 후보의 기존 route/P/Q/SOC/rho를 보존하고 S2/S3의 정확한 G를 구성했다.

30. **각 candidate의 rows/columns/nonzeros는?**
S0: 954560/316743/8282350; S1: 955712/316743/8319270; S2: 1795492/524671/10614268; S3: 1796644/524671/10651188

31. **각 candidate의 root LP LB는?**
S0=0.5718494602017812; S1=0.5718494600493583; S2=0.5722125039436496; S3=0.5722125039436496

32. **각 candidate의 delta LB는?**
S0=0.0; S1=-1.5242285211769513e-10; S2=0.0003630437418684629; S3=0.0003630437418684629

33. **implied gap은?**
S0=0.14600227060729357; S1=0.14600227083492123; S2=0.1454601025144593; S3=0.1454601025144593 (동일 PR108 UB 대비, 비율). LP만으로 MIP certificate를 주장하지 않는다.

34. **selected strengthening은?**
S2

35. **selection 이유는?**
integer physical equivalence를 통과한 후보 중 최고 root LB, 낮은 implied gap, 이후 wall/matrix 순서로 선택했다.

36. **LB가 0.62 이상 올라갔는가?**
False

37. **LB가 0.65 이상 올라갔는가?**
False

38. **root strengthening이 material했는가?**
False; 사전 기준 delta_LB>=0.001.

39. **MIP canary를 실행했는가?**
False

40. **canary 300초 BestBd/gap은?**
미실행. material bound gate가 통과되지 않았다.

41. **canary 600초 BestBd/gap은?**
미실행. 600초 solve를 소비하지 않았다.

42. **production이 authorized됐는가?**
False; {"authorized": false, "reason": "No authorized proof canary", "canary_run": false}

43. **production을 실행했는가?**
False

44. **final P1 gap은?**
14.600227083478131%; source=PR108 retained incumbent. production P1 quality=False

45. **P2를 실행했는가?**
False; P2 complete=False

46. **physical validation은 PASS인가?**
True; source=PR108 incumbent independently revalidated

47. **robust voltage는 PASS인가?**
True; source=PR108 incumbent independently revalidated; band=0.955–1.045 pu.

48. **original route/SOC/PCS physics가 바뀌었는가?**
변경 없음. default hook=None 모델 identity와 incumbent residual까지 동일하다.

49. **아직 남은 relaxation weakness는 무엇인가?**
selected root fractional stay/travel/mode=(6586, 5609, 293); 분산 위치/Q 지원과 averaged grid-feasible trajectory의 정수 분해 가능성이 다음 진단 우선순위다. 후자는 아직 가설이다.

50. **A2를 왜 실행하지 않았는가?**
명시적인 STOP-before-A2 범위다. M1/P2 acceptance와 Problem13 최종 검증을 혼동하지 않는다.
