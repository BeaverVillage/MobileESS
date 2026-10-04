1. Draft PR [#147](https://github.com/BeaverVillage/MobileESS/pull/147); scientific payload SHA 3d41bd8874fbe758db87a81cc28a92be0e048fa3. Semantic384 / full1831 PASS, actual concurrent heavy native solve=0, 다른 Lane kill/terminate=0/0. Payload remote SHA 일치 및 clean 확인. 최종 publication metadata HEAD와 마지막 clean 확인은 PR 본문/최종 응답에 기록.
2. PR143 exact head ce5d30fb9bcb91ab8395d1313e868d24f5fde517 및 모든 old tracked bytes 보존.
3. Frozen FULL matrix 961472 rows / 316743 columns / 8587630 nnz; native relax crosscheck PASS, SOS/general/indicator/Q constructs 없음.
4. Discrete -> continuous 208312개 (binary 208312, integer 0); original LB/UB 그대로.
5. Arc pure LP status 2 OPTIMAL, Method2/Crossover0/Threads1; native original-M1 integer solve 없음.
6. Arc native optimum 0.5687116104747505.
7. Exact Fraction weak-duality certified lower 0.5687115725336208; original bounds only; free stationarity를 original equality multiplier에서 exact repair했고 pseudo-finite bound 사용 없음.
8. Primal-dual certificate gap 3.794112968247276e-08; native OPTIMAL만으로 scalar를 인증하지 않음.
9. Original affine residual 5.291838078846922e-08, bound residual 0.0, objective error 0.0.
10. Legacy 0.5687116103498322 comparison CLOSE_BUT_NOT_AUTHORITY; native difference 1.2491829792793396e-10, certificate difference -3.781621138454483e-08. Similarity는 authority 아님.
11. PR143 z_arc_LP <= z_DW_root 증명과 새 weak duality의 transitivity로 floor transfer PASS.
12. Official independent D-W floor 0.5687115725336208.
13. Official native-reference T_cert 0.5737116104747505; certified-floor-reference T 0.5737115725336208. Exact1/200 addition; material/nonmaterial comparator outward max/min 각각 0.5737116104747505 / 0.5737115725336207.
14. Pre-CG interval [0.5687115725336208, 0.5836817975103938]; checkpoint 1158 exact, old pricing replay 없음.
15. Pre-CG threshold status INCONCLUSIVE.
16. 새 Discovery rounds 6; smoothing center restore True, initial next alpha 0.125.
17. 새 validated columns 86; retained 1244; rate 8.037371776270916 columns/min, Discovery median 71.57400315001723 s.
18. Audited RMP upper trajectory [0.5836817975103938, 0.5830434913137131, 0.5824010164877231, 0.582032600300936, 0.5815672190514366, 0.5813101038234358, 0.5812261378620154]; DW_THRESHOLD_DISTANCE.csv에 시점별 lower authority/threshold distance 저장.
19. Final true-dual four-way Certification COMPLETED; pricing calls 28, fixedworkers4/Threads1/RAM1GiB, warm RMP disabled.
20. New corrected LB 0.532325936473933; exact residual/beta1e-8/downward treatment 유지.
21. Aggregated certified LB=max(new arc floor, old corrected, new corrected) = 0.5687115725336208.
22. Smallest audited RMP upper 0.5812261378620154 (DW LP upper, original integer UB 아님).
23. Final certified DW interval [0.5687115725336208, 0.5812261378620154].
24. Materiality INCONCLUSIVE.
25. Exact CG convergence False; threshold decision과 별개.
26. 다음 단일 blocker는 남은 실제 negative RC를 소진하는 CG convergence/trajectory pool. 최종 native pricing proof room 합계 0.00033132367520084804는 aggregated lower-threshold deficit 0.005000037941129687보다 작다. Incumbent는 LB에 사용하지 않았고 causal uniqueness를 주장하지 않는다. 다음 방향은 fixed4-way smoothed Discovery이며 이번 scope의 추가 optimize는 없다.
27. Branch-and-Price NOT_RUN.
28. May day workers4/1/4/1, 각31일, Threads1 보존.
29. B2 inner1 / B3 inner4; mainB0->B1->B2->B3L1 뒤L2/L3/L4, previous Planning-only firewall 보존.
30. May optimizer/Actual/FreshAC0/0/0; no productionM1/P2/A2/M2. Scientific A1/route/physics/PCS16/P1/P2 unchanged.

이번 작업에서는 frozen original M1의 모든 integrality만 relax한 실제 arc LP를 terminal OPTIMAL까지 직접 풀었으며, matrix identity와 primal/dual numerical certificate를 모두 검증한 경우에만 scalar lower floor를 채택했다.

PR143에서 증명한 z_arc_LP <= z_DW_root 관계를 이용해 certified arc-LP lower bound를 D-W root lower floor로 전이했다.

기존 0.5687116103498322는 interrupted integer MIP BestBd였으므로 수치적으로 유사하더라도 새 arc-LP certificate의 대체 authority로 사용하지 않았다.

Adaptive dual smoothing은 Discovery에만 사용했고, column acceptance와 scientific lower-bound/materiality certificate는 true RMP dual authority를 유지했다.

Branch-and-Price와 May production은 실행하지 않았다.
