1. Draft PR publication pending, final SHA publication pending; semantic 334, full 1781 PASS; 최종 clean/remote 검증은 PUBLICATION.json.
2. PR141 exact head cae31ce64c83d1e94c158a46e2739fd2ff7e7da3: PASS.
3. Checkpoint 1078개, 제외된 old TIME_LIMIT/interrupted/uncertified points 승격 없음.
4. RAM floor 1 GiB; old8GiB/15% superseded.
5. 실제 four-way native optimize overlap 132.40914550004527초; PASS True.
6. Four-way 실제 optimize 교집합 sampled total-tree peak RSS 11948105728 bytes; 정확한 unsampled peak 아님.
7. 실제 four-way samples min available RAM 6706819072 bytes.
8. 실제 four-way samples max system commit 84.10723125837684%.
9. Four-way first→last sample pagefile delta 6144000 bytes; within-batch 최대 delta 0 bytes; 지속적인 pagefile증가+hardpaging 결합 failure 없음.
10. 선택 pricing concurrency 4.
11. Discovery rounds 5.
12. Pricing calls 28 (four-way 28).
13. Validated added columns 80; retained 1158.
14. 선택한 multi-column/call mean 4.0, max 4; 전역 optimum/top4/rank 주장 없음.
15. Columns/min PR141 .80998069224726 → 6.9100104199372385.
16. Discovery median PR14188.07946670003003 → 70.3343452999834초 (warm canary와 감사 포함).
17. Cold RMP median 33.99590095001622초.
18. Warm RMP median 38.94264135000412초.
19. Warm basis accepted [True, True].
20. Warm median wall reduction -0.1455099074226931; selected False.
21. 연속 dual L1/L2/Linf·normalizedL2·grid variation·turnover·near-duplicate·RC variance 6행: DW_DUAL_OSCILLATION_AUDIT.csv.
22. Stabilization tested True, selected True; mandatory adaptive smoothing, alpha initial.30 / final 0.125; box/proximal/trust-region 실행 없음.
23. Best corrected LB 0.5215744487783405.
24. Min audited RMP upper 0.5836817975103938 (D-W LP upper).
25. Final interval [0.5215744487783405, 0.5836817975103938].
26. Materiality INCONCLUSIVE; T 0.5737116103498322; root optimum/convergence False.
27. May day workers B0/B1/B2/B3 =4/1/4/1, 각31일; original1458-node plan/feedback firewall 유지.
28. B3 inner workers 4, Threads1, B2 inner1.
29. Branch-and-Price·productionM1·P2/A2/M2 실행 안 함.
30. May optimizer/Actual/FreshAC =0/0/0.


Smoothing enabled=true; alpha initial=.30 / final=0.125; normalized true change median=0.8120439109695525, max=1.104161632760677. Smoothed discovery에서 실제 추가한 열 80, true RC에서 거절 14. RMP round count PR141 7 → 7; rounds/10columns 5.833333333333333 → 0.875. Bracket narrowing/min 0.0009265559546360159 → 0.0003084346916241318. Comparable old near-duplicate metric는 없어 감소를 주장하지 않음.

Best LB 0.5215744487783405는 PR141에서 보존한 certificate이다. 이번 두 true-dual Certification의 새 LB는 [0.5044526936603798, 0.5044526936603798]; best LB 개선은 없다. Primary speed target35s 미충족으로 policy_canary=NOT_SUPPORTED이나 actual four-way resource gate는 PASS이다. Native optimize union 501.6940648998716초, 전체 build/audit 포함 elapsed 694.6445610999945초; 등록한 cycle-fit/final-C 종료 규칙으로 900초 한도 안에서 종료했다.

Adaptive dual smoothing은 Discovery pricing 가속에만 사용했다.

Smoothed dual에서 발견된 trajectory는 동일 iteration의 unstabilized true RMP dual로 reduced cost를 재계산한 뒤 true reduced cost가 음수인 경우에만 column으로 추가했다.

Scientific lower-bound, materiality, no-negative 및 CG convergence certificate는 모두 unstabilized true RMP dual과 global pricing BestBd를 사용했다.

따라서 dual smoothing은 exact feasible domain이나 scientific global certificate를 변경하지 않았다.

이번 task에서는 1 GiB available-RAM floor를 사용해 실제 4-way pricing optimize concurrency를 시험했으며, old 8 GiB gate를 이유로 pricing 시작 전에 실패 판정하지 않았다.

Discovery에서 여러 negative trajectory를 한 pricing solve에서 수집했지만, 모든 trajectory는 full original pricing domain에서 feasible하고 manual reduced-cost audit을 통과한 경우에만 D-W column으로 사용했다.

Scientific lower-bound/materiality certificate는 unstabilized true RMP dual과 global pricing BestBd를 사용하는 exact Certification layer에서만 생성했다.

May production과 Branch-and-Price는 실행하지 않았다.
