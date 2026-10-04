1. Draft PR 게시 전; 결과 commit 게시 전; semantic 291 / full 1738 PASS. 최종 SHA/remote/clean은 최종 응답에서 확인. 사용자 정책 재설계 중단: POLICY_EXPERIMENT_PARTIAL, scientific INCONCLUSIVE. 정상 native terminate receipt 미확인; active call21 제외.
2. PR140 scientific identity PASS; 원본 10003개 파일 바이트 보존.
3. 복원 checkpoint 4+1044=1048개. 과거 pricing 재실행 및 failed terminal dual 재사용 없음.
4. Corrected-dual theorem PASS. 실제 lower bound는 exact global dual 잔차·box term·pricing1e-8 safety를 포함; native z_RMP를 lower bound에 직접 대입하지 않음.
5. Bounded enumeration 10개 PASS: full trajectory/vertex Fraction 열거, negative/zero/positive/equality/free/transit/PCS/terminal SOC 및 convergence equality.
6. Mixed-sense native Pi/convexity/ObjCon/ObjBound/RC proof PASS. 실제 RMP global/retained RC와 전체 원본 행 독립 감사 PASS.
7. 첫 RMP 목적값 0.5930269349321426; D-W root LP upper이며 original integer UB 아님.
8. 첫 corrected certified LB 0.5019536518794615.
9. 첫 D-W root interval [0.5019536518794615, 0.5930269349321426].
10. Pricing OPTIMAL 18회.
11. TIME_LIMIT_WITH_VALID_BOUND 2회; incumbent column 추가 없음.
12. Pricing UNCERTIFIED 0회.
13. Optimal pricing median/p95/max: 111.724709s / 251.253229s / 258.504828s.
14. RMP basis hint supplied median/p95/max: 17.371842s / 18.379244s / 18.589560s; cold 16.566183s / 16.566183s / 16.566183s. Native acceptance {'EXPLICITLY_DISCARDED': 5}; supplied를 accepted warm start로 해석하지 않음.
15. 새 RMP 6회.
16. 새 pricing 20회.
17. 새 validated most-negative columns 18개.
18. Best corrected certified LB 0.5104145457228156.
19. Smallest RMP upper 0.5898198735464273.
20. 최종 D-W root interval [0.5104145457228156, 0.5898198735464273].
21. Arc root LB 0.5687116103498322.
22. Certified improvement lower bound -0.05829706462701656.
23. Material threshold 0.5737116103498322.
24. Materiality INCONCLUSIVE; stop USER_STOP_FOR_PRICING_POLICY_REDESIGN.
25. Exact CG convergence False.
26. Converged certified D-W root LB None.
27. Decision heavy wall None; 총 native optimize wall 3139.995449200098/3600초; build/audit 포함 elapsed 3645.605944400013초. optimize wall은 완료된 call만 합산; 중단된 call21의 정확한 terminal wall은 NULL. 마지막 telemetry elapsed 관측값을 별도 보존.
28. PR140 RMP263회/3586.350867초 대비 새 RMP 6회. First-negative와 terminal optimal/global-bound pricing runtime은 별도 비교; 전수렴 속도 향상 주장 없음. CG iteration timing은 optimize wall 합계이며 build/audit/checkpoint는 별도. 고정 Method2 정책의 native basis discard 로그 보존.
29. Branch-and-Price NOT_RUN; production M1/P2/A2/M2/Actual/Fresh AC NOT_RUN.
30. May production optimizer/Actual/Fresh AC=0/0/0. 1458-node B3 계획 및 Actual feedback firewall 보존.

이번 작업에서는 pricing을 첫 negative reduced-cost trajectory에서 중단하지 않고 full-domain global bound까지 계산했다.

Restricted master objective는 full D-W root optimum의 upper bound이고, pricing global bounds를 이용한 corrected dual objective는 full D-W root optimum의 lower bound로 독립 검증했다.

따라서 full CG convergence 전에도 [L_corr, z_RMP]의 certified D-W root interval을 구성했다.

Top-K, route pool, Hamming restriction, site pruning, heuristic pricing은 사용하지 않았다.

Branch-and-Price, production M1, P2, A2, M2, Actual, Fresh AC 및 May production campaign은 실행하지 않았다.
