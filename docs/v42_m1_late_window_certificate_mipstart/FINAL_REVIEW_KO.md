# 한국어 최종 검토

1. **정확한 출발점과 계보는?**

   PR112 exact head c90525c330c2f8aa9971030b87cf154ecf1b284f다. 새 branch는 이 commit에서 생성했고 실행 전 checkpoint와 final commit을 그 계보 위에 쌓는다. PR111 등 다른 formulation을 새로 상속하지 않았다.

2. **scope correction은 어떻게 남겼는가?**

   원 PREREGISTRATION.json을 삭제·덮어쓰지 않았다. addendum에 timestamp, base commit, 원 파일 SHA, 사용자 correction SHA, 신규 optimization marker가 없었다는 사실과 B3-first gate를 기록했다.

3. **prepare 오류와 기존 산출물은 숨겼는가?**

   숨기지 않았다. 첫 두 native identity/row-name assertion의 history를 남겼고 correction 당시 NPZ·physical/grid·P1 CSV와 source를 별도 snapshot으로 보존했다. exact matrix 대조는 row-index alias를 명시해 마쳤으며 prepare optimization은 0이다.

4. **왜 M1은 아직 완전히 해결되지 않았는가?**

   현재 original-M1 implied gap은 3.22498964%이며 production P1/P2 acceptance certificate는 없다. 이번 B3-first certificate task의 종료와 M1 acceptance를 혼동하지 않는다.

5. **3.225% gap의 정확한 의미는?**

   PR112 validated UB 0.591281263433와 inherited S2 LB 0.572212503944의 차이를 UB로 나눈 3.22498964%다. 정확한 optimum gap이 아니라 certified original lower/feasible upper가 정의하는 implied gap이다.

6. **이번 best original feasible UB와 certified LB는?**

   UB=0.591281263433, source=PR112_P_FIXED_ROUTE; original certified LB=0.572212503944. partial feasible upper는 original binaries 모두 integer이고 full validation을 통과한 경우에만 이 UB 후보에 포함했다.

7. **F3와 S2 lower bound는 무엇이 다른가?**

   F3 LB=0.571849460202, S2 certified original-M1 LB=0.572212503944. 이번 partial models는 exact F3에 일부 integrality만 복원한다. S2 evidence는 재실행하지 않고 original global reference로 사용한다.

8. **S2를 B3 optimum interval의 lower floor로 사용해도 되는가?**

   자동으로 사용할 수 없다. S2 feasible set과 각 부분 integrality F3 model의 포함관계는 별도다. partial interval은 F3와 동일 partial model의 valid bounds를 사용하며, S2는 materiality 기준과 original global LB에만 사용한다.

9. **새 UB는 왜 original-M1 feasible인가?**

   원 binary, bounds, route flow, charge-mode, P/Q, initial/terminal SOC, recurrence, travel debit, PCS16, full96 grid 및 robust voltage/transformer를 독립 검증했다. 원 행렬에서 최대 row residual도 기록했고 clipping·repair는 하지 않았다.

10. **왜 route를 그대로 두고 UB가 크게 줄었는가?**

   PR112 retained mode가 모두 discharge mode여서 충전할 수 없었고, all-stay route와 terminal equality에서 순방전도 사용할 수 없었다. mode와 dispatch를 풀면 기존 route에서도 에너지를 저장·방전하고 P/Q를 함께 선택할 수 있다. 그 original-feasible 개선은 0.078333467988이다.

11. **mode 재최적화는 무엇을 증명하는가?**

   기존 integer mode-plan/continuous-dispatch quality가 materially suboptimal이었다는 직접 증거다. fixed-all LP는 옛 objective를 재현했고 fixed-route/free-binary-mode model만 큰 feasible 개선을 보였다.

12. **그것이 mode LP relaxation gap의 증명인가?**

   아니다. primal integer plan을 더 잘 찾는 효과와 LP hull을 강화하여 lower bound를 올리는 효과는 다르다. mode incremental contribution은 nested optimum intervals로 별도 판단한다.

13. **complete native start의 axis는 얼마나 큰가?**

   316,743개 native variable이며 original binary 208,312개를 포함한다. 각 unit의 96개 charge_mode와 97개 SOC 및 모든 native route/Pch/Pdis/Q/auxiliary 값을 정확히 복원했다.

14. **variable mapping에서 빠지거나 이름을 추정한 값이 있는가?**

   native 이름 누락은 0이다. 값은 PR112 source solution과 bitwise 일치한다. serialized plan의 supplemental/unreachable 키는 native axis 밖의 추가 정보이며 missing native value를 추정하거나 임의 보충하지 않았다.

15. **binary fidelity는 어떻게 점검했는가?**

   원 binary 값의 최대 fractionality가 0인 imported point를 보존했다. 실제 accepted initial vector에도 모든 original binary의 integrality를 다시 검사했다. partial incumbent에는 복원 subset과 전체 original binaries를 구분해 검사한다.

16. **bounds와 auxiliary 값은 그대로인가?**

   original MPS bounds와 native constructor bounds가 정확히 일치한다. start는 bounds와 full matrix를 만족하며 auxiliary 값도 axis에 포함한다. 임의 rounding, projection, local repair를 하지 않았다.

17. **SOC recurrence와 travel energy를 점검했는가?**

   full matrix의 original energy_balance와 native physical validator를 함께 사용했다. travel energy는 original departure convention 그대로 차감한다. deliberate terminal/route/PCS 위반점이 거부되는 새 테스트도 추가했다.

18. **PCS16과 actual circle feasibility는 보존되는가?**

   individual original PCS16 행을 모두 유지한다. 원 integer start의 native physical circle check도 통과했다. aggregate PCS로 바꾸거나 400-kVA rating을 수정하지 않았다.

19. **full-grid와 Planning voltage authority는?**

   원 96-slot voltage/line/transformer current·kVA 행을 모두 유지하고 0.955–1.045 pu의 robust Planning band를 검증했다. Actual/Fresh의 0.95–1.05 acceptance band를 Planning으로 대신 사용하지 않았다.

20. **initial/terminal SOC는 바뀌었는가?**

   네 unit 모두 original initial/terminal 760 kWh equality를 유지한다. diagnostic B3/B2/B1에 TERM_RELAX를 넣지 않았고 counterfactual reference를 production candidate로 승격하지 않았다.

21. **objective를 독립 재계산했는가?**

   imported rho=0.591281263433; 원 coefficients의 all96 non-transformer face 최대값은 0.591281263433131다. objective는 원 rho_max의 단일 minimization 계수이며 다른 목적식으로 바꾸지 않았다.

22. **native solver가 새 start를 실제 사용했는가?**

   그렇다. native B3 raw log의 Loaded user MIP start와 initial MIPSOL vector를 보존했다. accepted initial objective=0.591281263433다. 이 actual accepted point는 original full-integer physical/grid 검증도 통과했다.

23. **별도 full-binary acceptance solve를 실행했는가?**

   아니다. scope correction의 B3-first/minimal-solve 정책에 따라 acceptance를 B3 native MIP 안에 함께 기록했다. B3는 partial binary model이지만 accepted initial point 자체는 모든 original binaries가 integer이고 exact original physical rows를 만족한다. production acceptance를 주장하지 않는다.

24. **옛 UB로 fallback하는 것을 어떻게 막았는가?**

   처음 loaded start, first incumbent, SolCount 및 final incumbent<=0.5912812634331275+tolerance를 함께 검사한다. old start와 alternate start는 넣지 않는다. 이 조건이 실패하면 raw rejection evidence를 보존하고 certificate 결과로 진행하지 않는다.

25. **왜 신규 solve를 B3부터 시작했는가?**

   PR112가 이미 세 arm을 600초씩 수행했기 때문이다. strongest B3의 validated feasible upper가 가까우면 weaker B2/B1의 비물질성을 추가 optimization 없이 증명할 수 있다. unconditional 장시간 rerun은 correction으로 폐기했다.

26. **B3의 integrality domain은?**

   58–95를 점유하는 original stay/travel arcs, window node departure arcs 및 window charge modes 85,744개를 binary로 복원한다. 나머지 binary만 continuous로 완화하며 원 행·bounds·route alternatives·SOC coupling은 모두 유지한다.

27. **B2의 domain과 실행 gate는?**

   66–95 route/stay/travel 및 charge modes 67,436개다. B3 material positive certificate가 있을 때만 신규 실행한다. B3 nonmaterial upper가 검증되면 nesting certificate로 대체한다.

28. **B1의 domain과 실행 gate는?**

   66–95 route/stay/travel 67,316개이며 mode는 relaxed다. B2 material certificate가 있을 때만 신규 실행한다. B2 또는 B3 stronger feasible upper가 nonmaterial이면 추가 solve 없이 upper를 전달할 수 있다.

29. **feasible-set 포함관계는?**

   F_original_integer ⊆ F_B3 ⊆ F_B2 ⊆ F_B1 ⊆ F_F3다. 복원 binary 집합은 반대 방향으로 더 커진다. independently enumerated occupancy/departure rule을 inherited exact domains와 대조해 strict nesting을 확인했다.

30. **각 partial BestBd가 왜 original-M1 valid LB인가?**

   모든 original integer feasible point가 각 partial model에 들어간다. 따라서 partial optimum 및 그 certified lower bound는 original integer optimum 이하이다. 원 constraints를 유지하고 integrality 일부만 완화했으므로 이 방향이 성립한다.

31. **B3 lower bound를 B1/B2로 전달할 수 있는가?**

   안 된다. stronger feasible set의 minimum은 weaker minimum보다 높을 수 있다. lower bound는 weaker에서 stronger로만 전달한다. upper는 stronger feasible point가 weaker에서도 feasible이므로 반대 방향으로 전달한다.

32. **B3 nonmaterial certificate는 B1/B2를 어떻게 대신하는가?**

   검증된 B3 point가 upper U를 제공하면 opt_B1<=opt_B2<=opt_B3<=U다. U-S2<=0.001이면 세 optimum 모두 같은 reference에 대한 contribution ceiling을 만족한다. 이 경우 B1/B2 execution은 NOT_RUN_NESTING_CERTIFIED로 기록한다.

33. **negative certificate의 정확한 정의는?**

   solver-validated partial feasible upper에서 upper-S2<=0.001가 성립하거나 그와 동등한 certified optimum interval로 같은 ceiling을 증명해야 한다. OPTIMAL 또는 좁은 interval이라도 optimum이 높으면 positive 결과이며 자동 negative가 아니다.

34. **positive certificate 기준은?**

   valid partial lower bound-S2>=0.001다. 이 threshold를 넘어선 rigorous solver bound를 보존한다. positive partial materiality와 route/mode/buffer의 incremental attribution은 별도 판정한다.

35. **timeout과 negative certificate는 왜 다른가?**

   timeout은 남은 search tree/optimum interval을 닫지 못한 computational 상태다. BestBd 정체만으로 더 좋은 partial solution이나 높은 optimum을 배제할 수 없다. feasible upper ceiling 또는 충분한 optimum evidence가 없으면 INCONCLUSIVE다.

36. **interrupted run을 OPTIMAL로 바꾸었는가?**

   아니다. native status를 그대로 저장한다. callback의 positive/negative certificate candidate stop은 INTERRUPTED일 수 있으며 final bound와 saved point 검증으로 certificate validity를 판단한다. BarStatus도 overall status로 대체하지 않는다.

37. **B3의 실제 결과는?**

   RUN; status=9; new native BestBd=0.5718504565144596; partial optimum interval=[0.571850456514, 0.591281263433], width=0.019430806919; material=False, negative certificate=False (INCONCLUSIVE).

38. **B2의 실제 실행/결과는?**

   NOT_RUN_GATE_B3_INCONCLUSIVE; status=NOT_RUN_GATE_B3_INCONCLUSIVE; new native BestBd=None; partial optimum interval=[0.571849462550, 0.591281263433], width=0.019431800883; material=False, negative certificate=False (INCONCLUSIVE).

39. **B1의 실제 실행/결과는?**

   NOT_RUN_GATE_B2_INCONCLUSIVE; status=NOT_RUN_GATE_B2_INCONCLUSIVE; new native BestBd=None; partial optimum interval=[0.571849462550, 0.591281263433], width=0.019431800883; material=False, negative certificate=False (INCONCLUSIVE).

40. **mode-only incremental 기여는 얼마까지 증명되는가?**

   {'lower': 0.0, 'upper': 0.019431800883200512, 'exact_optima_required': False, 'formula': 'max(0,L_stronger-U_weaker) <= opt_stronger-opt_weaker <= U_stronger-L_weaker'}. lower=max(0,L_B2-U_B1), upper=U_B2-L_B1를 사용한다. time-limited BestBd끼리의 차이를 optimum 차이로 표현하지 않는다.

41. **buffer incremental 기여는 얼마까지 증명되는가?**

   {'lower': 0.0, 'upper': 0.019431800883200512, 'exact_optima_required': False, 'formula': 'max(0,L_stronger-U_weaker) <= opt_stronger-opt_weaker <= U_stronger-L_weaker'}. 추가 58–65 mode/route 및 crossing actions가 기존 full96 SOC/terminal coupling과 결합하는 공동 효과다. interval이 허용하지 않으면 material increment 또는 특정 SOC 단독 원인을 단정하지 않는다.

42. **terminal-SOC counterfactual reference는 무엇인가?**

   PR112에서 original F3 terminal equality4개만 제거한 LP rho=0.5449188149384189, F3 대비 감소=0.026930645263362307였다. terminal equality가 LP objective를 material하게 제약한다는 evidence이며 integer gap 단독 원인 증명은 아니다. 이번에는 재실행하지 않았다.

43. **terminal SOC를 제거하면 안 되는 이유는?**

   original scientific battery contract와 feasible-set 정의를 바꾸기 때문이다. 그런 point는 original feasible UB가 아니며 기존 acceptance에 사용할 수 없다. 이번 primary B3에는 original terminal equality를 유지한다.

44. **late horizon은 필수 충전 회복 구간인가?**

   그렇게 주장하지 않는다. frozen root는 slot66에서 약1080 kWh를 보유하고 terminal760까지 약320 kWh 순방전한다. 충전/방전·travel recurrence를 실제 값으로 해석하며 late charging recovery라는 예시를 관측 사실로 바꾸지 않는다.

45. **line.sw1/A bottleneck의 물리적 의미는?**

   PR112 root의 phase-A feeder sensitivity가 active late block의 대부분 P1 face를 정의한다. line.sw1/A가 30개 중29개 slot에서 binding이다. P/Q와 위치가 affine current를 바꾸지만 단일 feeder 관측만으로 discrete optimum 원인을 확정하지 않는다.

46. **왜 66–95이고 40–46이 아닌가?**

   원 coefficients/vector의 all96 epigraph slack과 absolute dual mass로 찾은 primary T_ACTIVE가66–95다. P1 dual mass99.99998482%가 이 구간에 있다. PR110의40–46은 incumbent-root loading 차이 ranking이므로 historical evidence로만 보존한다.

47. **fractional location/Q가 gap 원인을 바로 증명하는가?**

   아니다. root는 site mass와 P/Q를 분산하지만 descriptive averaging과 optimum materiality는 다르다. 원 physics를 유지한 partial-integrality certificates로 lower/upper interval을 확인해야 한다.

48. **incumbent quality와 bound quality를 어떻게 분리했는가?**

   PRIMAL_QUALITY_COMPARISON에는 original-feasible UB, physical/grid/binary validity와 route/mode/P/Q/SOC difference를 기록한다. DUAL_BOUND_COMPARISON에는 certified global LB, partial interval, status/time/nodes/root와 negative certificate를 별도로 기록한다.

49. **numerical artifact 가능성은 어떻게 점검했는가?**

   native/MPS matrix 계수·RHS·sense·bounds·순서를 exact 비교하고 original name axis, independent face objective, physical/grid validation, binary fidelity를 검사한다. deliberate corrupted terminal/route/PCS points는 거부된다. NUMERICAL_WARNING_AUDIT에 basis/quad precision 등 실제 native warnings를 보존하며 미완료 root의 중간 LP 값은 certificate로 쓰지 않는다. 이는 exact rational bound proof를 뜻하지 않으며 numerical failure를 과학적 결과로 포장하지 않는다.

50. **4 threads가 이전 1 thread보다 우수하다고 주장하는가?**

   주장하지 않는다. complete new start와 여러 preregistered solver controls가 함께 바뀌었으므로 단일 parameter 효과를 분리한 비교가 아니다. certificate validity는 thread count가 아니라 unchanged feasible sets, valid solver bound와 saved-point 검증에 근거한다.

51. **solver strategy는 결과를 보고 반복 선택했는가?**

   아니다. primary joint strategy를 실행 전에 source checkpoint에 동결했고 fallback은0개다. Method2/NodeMethod1, Threads4, Seed20260929, MIPFocus1, Heuristics0.1, DegenMoves0, CutPasses1, MIPGap0, absolute gap0.0005 및1800초 optimize-only를 사용한다.

52. **native builtin cutting planes가 새 formulation remedy인가?**

   solver 내부의 mathematically valid branch-and-cut 과정과 저장소에 새 hand-designed cuts를 구현하는 것은 다르다. 이번 code에는 user/lazy/heuristic formulation cut, Top-K, Hamming restriction, 새 trajectory master가 없다.

53. **build time과 optimize time은 구분했는가?**

   model read, mapping, domain checks의 build time과 optimize 호출 wall/native runtime을 별도로 저장한다. root barrier/crossover/relaxation, branch node events, peak RSS 및 actual-observation progress도 보존한다.

54. **production M1 결과는?**

   NOT_RUN이다. scope correction 이후 이번 PR은 sequential certificate와 reporting까지만 진행한다. production authority file은 이 결정을 명시하며 original preregistration의 earlier gate가 superseded됐음을 기록한다.

55. **P1이 0.5% acceptance에 도달했는가?**

   current original implied gap=3.22498964%다. production P1 acceptance는 false이며 B3 diagnostic 또는 native start acceptance를 production acceptance로 대신하지 않는다.

56. **P2를 실행할 자격이 생겼는가?**

   production P1 accepted 이전에는 P2를 실행하지 않는다. 이번에는 P2_RUN=false다. 후속 P2는 original MIN_INTERVENTION movement energy→movement count tuple과 P1 objective lock, fixed AIDC anchor를 유지해야 한다.

57. **M1_ACCEPTED와 PROBLEM13_FINAL_VALIDATED는?**

   둘 다 false다. M1은 P1/P2 acceptance를 모두 요구한다. Problem13 최종 validation에는 그 후 A2→M2→frozen Planning→Actual replay→Fresh AC가 필요하므로 이번 certificate 결과로 true를 설정하지 않는다.

58. **A2 또는 downstream으로 넘어가도 되는가?**

   안 된다. A2/M2/Actual/Fresh AC/IEEE8500/final kernel/May·sensitivity campaign은 실행하지 않았다. Actual P/Q correction도 OFF다. primary certificate task의 종료는 downstream gate 통과가 아니다.

59. **가장 근거가 강한 root-cause class는?**

   CASE_E_INCONCLUSIVE다. threshold crossing만으로0.001 이상의 incremental effect를 주장하지 않고 certified intervals가 허용하는 범위로 분류했다. 부족한 certificate가 있으면 INCONCLUSIVE를 유지한다.

60. **다음 정확한 remedy 방향은?**

   B3의 남은 optimum interval을 먼저 줄여 positive bound 또는 가까운 validated partial upper certificate를 확보해야 한다. 현재 증거로 route/mode/trajectory cut을 선택하지 않는다. 새 original-integer start는 보존하되 추가 arm·fallback·production을 자동 실행하지 않는다.

61. **numbered Problems와 기존 architecture를 바꾸었는가?**

   대상은1,2,3,4,5,6,8,13이며 직접 연구 대상은Problem13 M1이다. Problems7,9,10,11,12의 새 연구·redesign·학습·실험은 없다. Runtime/carry-over/causality/response/flexibility 및 A1→M1→A2→M2 contract는 기존 tracked bytes로 보존했다.

62. **PR112 evidence와 execution source의 보존은?**

   1400개 inherited tracked 파일 SHA를 확인한다. original preregistration과 prepare snapshot도 SHA로 대조한다. EXECUTION_FREEZE와 actual execution marker commit이 optimization source를 결합하며 postprocessing source는 별도로 SOURCE_MANIFEST에 기록한다.

63. **새 partial incumbent를 언제 original UB로 채택하는가?**

   모든 original binaries의 integrality, full matrix, route/mode/SOC/PCS 및 reconstructed original grid validation이 통과할 때만 채택한다. fractional-outside partial point는 partial feasible upper certificate로만 사용하며 원 integer UB로 오인하지 않는다.
