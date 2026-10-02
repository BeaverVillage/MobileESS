# V42 exact MESS Benders 검토

1. **Q. 왜 route와 P/Q/SOC를 분해해도 joint optimization인가?**

   A. Master candidate마다 원래 전기·배터리 feasible set을 recourse가 검사하고 유효 cut으로 모든 discrete 대안을 연결한다. 최종 x/y는 같은 M-stage solution이다.

2. **Q. 물리적으로 무엇이 joint인가?**

   A. Route, stay/travel, charge mode, Pch/Pdis, Q, SOC, grid response가 원래 coupling 식을 동시에 만족한다.

3. **Q. Master 변수는 무엇인가?**

   A. Full original M1은 route 207,928개와 mode 384개, 합계 208,312 binary다. B3 diagnostic만 85,744 binary다.

4. **Q. Recourse 변수는 무엇인가?**

   A. Full M1은 108,431 continuous column이다. Pch/Pdis/Q/SOC/rho와 모든 grid auxiliary가 포함된다. B3는 outside binaries도 continuous로 남아 230,999 column이다.

5. **Q. Mode가 master인 이유는?**

   A. 충전/방전의 discrete authority를 유지하기 위해서다. Full M1에서 96 slots × 4 units 모두 binary다.

6. **Q. SOC가 recourse인 이유는?**

   A. SOC는 continuous이고 고정 x에서 효율·travel debit을 포함하는 recurrence가 선형이다.

7. **Q. Travel energy coupling은?**

   A. Departure slot의 original arc energy×x가 SOC recurrence RHS에 그대로 들어간다. Arrival 또는 connection 시점으로 옮기지 않는다.

8. **Q. Grid coupling은 어디에 남는가?**

   A. All96 voltage, line, transformer current/kVA 행이 continuous recourse에 그대로 남는다. 고정 AIDC anchor도 유지된다.

9. **Q. A1/A2는 왜 그대로 두는가?**

   A. 이번 범위는 MESS solver implementation 검증이다. Exact compact AIDC optimizer와 outer architecture는 보존한다.

10. **Q. M1/M2에만 Benders를 쓰는 이유는?**

   A. 현재 M-stage의 binary route/mode와 continuous electrical/battery 분할이 고정 x LP를 만든다는 구조를 검증했다.

11. **Q. Original feasible set을 보존하는가?**

   A. Stored matrix의 sign/duplication/column partition과 finite bounds를 exact audit했다. Full M1 모든 original binary를 master에 둔다. 모델 계수 차이는 0이다.

12. **Q. Route pruning이 있는가?**

   A. 없다. 새 Top-K, Hamming, trajectory pool, arc deletion은 없다. 기존 constructor의 original reachability authority만 그대로다.

13. **Q. D-W/CG와 다른 점은?**

   A. 전체 original discrete axis를 master에 유지한다. Trajectory column을 생성하거나 제한하지 않는다.

14. **Q. Heuristic인가?**

   A. 유효 Farkas/dual cuts를 이용하는 exact formulation이다. Timeout은 global solution 증명이 아니므로 INCONCLUSIVE로 보고한다.

15. **Q. Global optimality를 유지할 수 있는가?**

   A. Cut validity와 모든 domain 보존이 유지되면 master lower bound와 검증된 assembled UB로 원래 global gap을 증명할 수 있다. 현재 full-scale acceptance 여부는 flags를 따른다.

16. **Q. Recourse가 LP인가?**

   A. PASS. Remaining integer, quadratic, SOS, general constraint는 없다. PCS16/grid/SOC는 original linear rows다.

17. **Q. Farkas cut은?**

   A. Canonical Ay≤b−Bx에서 λ≥0, Aᵀλ=0이면 λᵀ(b−Bx)≥0은 necessary feasibility condition이다. Strict negative source margin을 검증한다.

18. **Q. Optimality cut은?**

   A. Min rho dual π≤0의 affine lower approximation을 theta≥πᵀb−πᵀBx로 master에 추가한다. Residual support와 rounding 보정도 포함한다.

19. **Q. Bound contribution은 왜 필요한가?**

   A. Finite lower/upper bounds도 feasible set과 Farkas/dual stationarity의 일부다. 빠뜨리면 valid proof를 잃는다. Fixture J가 필수 bound case를 검사한다.

20. **Q. Equality sign 처리는?**

   A. 각 original equality를 정방향과 역방향 두 inequality로 보존한다. > row는 전체 부호를 반전한다.

21. **Q. Numerical ray 검증은?**

   A. Sign, stored sparse products의 exact rational residual, bound support, strict margin, generated affine와 every known feasible assignment를 독립 검사한다. Infinite required support이면 NO CUT/STOP이다.

22. **Q. Bounded fixture exactness는?**

   A. True. A–L 12개 case, 각각 128개, 총 1,536 assignments를 두 LP representation으로 열거했다.

23. **Q. Monolithic optimum과 일치하는가?**

   A. 모든 fixture에서 native census, canonical census, monolithic MILP, Benders P1 optimum과 selected route/mode optimum equivalence가 일치한다. 이것은 full M1 optimum claim이 아니다.

24. **Q. Adversarial fixtures는?**

   A. SOC/grid/terminal/PCS16/upper voltage/transformer/threshold/degeneracy/near-zero/bounds/travel energy/route-dependent PQ를 포함한다. 48 payload mutations와 near-zero guard를 거부했다.

25. **Q. B3 threshold 결과는?**

   A. B3_INCONCLUSIVE; native status STOP_UNCERTIFIABLE.

26. **Q. PR114보다 진전됐는가?**

   A. Registered progress gate=False. Master가 candidate를 반환한 사실만으로 성능 향상을 주장하지 않는다.

27. **Q. B3 witness/proof가 나왔는가?**

   A. Certificate valid=False. Threshold T=0.5732125039436496; zero-objective master bound는 rho LB가 아니다.

28. **Q. Full M1 canary를 실행했는가?**

   A. False; authorization/result files에 이유를 기록했다.

29. **Q. Full M1 UB/LB는?**

   A. Original validated UB=0.5912812634331275, best valid global LB=0.5722125039436496. B3 fractional point를 original UB로 승격하지 않는다.

30. **Q. Gap은?**

   A. 0.03224989640084286, 즉 3.22498964%.

31. **Q. 0.5%에 도달했는가?**

   A. False.

32. **Q. P1 accepted인가?**

   A. False. Good incumbent만으로 acceptance하지 않는다.

33. **Q. P2를 실행했는가?**

   A. False. Production P1 acceptance 뒤에만 허용된다.

34. **Q. Movement ordering은?**

   A. Inherited final contract movement energy → movement count다. Legacy reserve/tie를 P2 scientific tuple에 추가하지 않는다.

35. **Q. P1 lock은 유지되는가?**

   A. P2 recourse에 rho≤accepted P1+1e-7를 넣는다. Energy component lock tolerance는 inherited 1e-8이다. 새 relaxation은 없다.

36. **Q. M1 accepted인가?**

   A. False. P2 lex completion도 필요하다.

37. **Q. A2를 실행했는가?**

   A. False. 이번 PR에서 자동 downstream production은 허용하지 않는다.

38. **Q. M2를 실행했는가?**

   A. Production False. Reusable interface와 bounded tests만 구현한다.

39. **Q. M2도 route/P/Q/SOC joint인가?**

   A. 동일 engine이 explicit new anchor/state의 native model을 만든다. Route/mode/P/Q/SOC는 모두 의사결정 변수다.

40. **Q. M1 route를 M2에 고정했는가?**

   A. 아니다. 모든 original route bounds와 domain을 유지한다.

41. **Q. Warm start와 fixing의 차이는?**

   A. Start는 solver hint다. LB/UB나 flow/domain을 바꾸지 않는다. Full M1 existing point는 exact axis와 physical/grid validation을 통과했다.

42. **Q. Outer iteration 의미는?**

   A. A1→M1→A2→M2는 AIDC/MESS block-coordinate co-optimization이다. Accepted block의 footprint를 다음 block에서 freeze한다.

43. **Q. Inner decomposition 의미는?**

   A. M-stage 내 master(route/mode)↔recourse(P/Q/SOC/grid)의 exact solver 반복이다. 물리적 최종 M-stage solution은 joint다.

44. **Q. Full-grid rows는 어디에 있는가?**

   A. Canonical recourse에 original coefficient/RHS/sense를 유지한다. Discrete-only 행만 master에도 중복한다.

45. **Q. Planning voltage는?**

   A. 0.955–1.045 pu 그대로다. Eventual Fresh AC acceptance 0.95–1.05 pu와 혼동하지 않는다.

46. **Q. Terminal SOC는?**

   A. 모든 unit의 original equality와 96-slot recurrence를 유지한다. Relaxation 없다.

47. **Q. PCS16은?**

   A. Individual 16-face linear inner polygon을 그대로 보존한다. 새 circle approximation 또는 capacity increase는 없다.

48. **Q. Line.sw1/A bottleneck은?**

   A. Original line-face loading/rho 행과 fixed AIDC contribution에 포함된다. 특정 bottleneck row만 고르거나 다른 line을 삭제하지 않는다.

49. **Q. Recourse count는?**

   A. 1 B3 calls. Full M1 count는 별도 result의 executed 여부를 따른다.

50. **Q. Feasibility cut 수는?**

   A. 0 B3 cuts. Fixture census certificates와 full-scale cuts를 구분한다.

51. **Q. Optimality cut 수는?**

   A. 0 B3 cuts. Threshold feasibility stage는 optimality cut이 필요 없다. Fixture P1에서는 dual cuts를 검증했다.

52. **Q. Master iterations는?**

   A. 1 B3 iterations.

53. **Q. Master time은?**

   A. 0.011999845504760742 seconds; total wall에는 build/loop/certificate overhead가 포함된다.

54. **Q. Recourse time은?**

   A. 1433.5810000896454 seconds; solver-reported sum이다.

55. **Q. Root bottleneck이 완화됐는가?**

   A. Registered gate=False. Terminal recourse/proof/witness가 없는 첫 master solve만으로는 통과하지 않는다.

56. **Q. Numerical warnings는?**

   A. PR113/114 warnings를 원문 receipt/hash와 함께 보존한다. 첫 B3 LP는 INFEASIBLE이었으나 ray sign 검증에 실패했다. Kappa=5.11554e15 warning이 있었다. Cut은 0개다. V1 rejected raw ray vector/hash/minimum은 저장되지 않아 복구할 수 없다. 이 한계를 REJECTED_B3_RAY_AUDIT에 명시했으며 V2는 검증 전에 입력을 저장한다. 추가 full optimize는 하지 않았다.

57. **Q. Thread 설정은?**

   A. 4 maximum configured threads. Sequential loop이며 recourse 동시 병렬 실행은 없다. Snapshot을 continuous absence proof로 표현하지 않는다.

58. **Q. Current root-cause interpretation은?**

   A. Exact domain에서 제한된 수치/시간 budget만 관찰한다. Incomplete LP의 phase-I objective 또는 ancestry slot0은 integrality materiality/proof가 아니다.

59. **Q. Next step은?**

   A. Equivalent native-bound LP representation과 certified residual handling을 별도 preregister/test할 수 있다. 현재 gate가 실패하면 full M1/A2/M2를 우회하지 않는다.

60. **Q. PROBLEM13_FINAL_VALIDATED인가?**

   A. False. 이번 decomposition 검증만으로 Fresh AC/Actual/downstream acceptance를 증명하지 않는다.

61. **Q. Cut aging/deletion은?**

   A. 없다. Exact coefficient hash deduplication만 허용한다. 모든 provenance와 active/inactive history를 보존한다.

62. **Q. Uncertifiable cut을 사용했는가?**

   A. 없다. Strict certificate 실패는 cut을 추가하기 전에 STOP한다. Full experiment의 stop reason은 progress/result에 남긴다.

63. **Q. 기존 tests/44 checks는?**

   A. 전체 708 tests PASS: inherited 643 + new 65. Inherited log1p warning 1개를 보존한다. Original 44 bounded-check receipt와 bytes를 검증했고 무단 재실행/수정하지 않았다.

64. **Q. Exact base와 bytes는?**

   A. PR114 exact 964b2c65964ff38089dab53c4e2fa03149d729f7에서 새 branch를 생성했다. Inherited 1,533 tracked file SHA와 Git diff를 검증한다.
