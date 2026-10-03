1. **PR / SHA / clean / tests**

Exact base PR126 `573517629a0445472da2f755460032ee9322e968`; child branch `codex/v42-m1-root-pathology-diagnostics`. Draft PR URL and final evidence commit are recorded in the delivery message; the evidence manifest avoids a self-referential commit hash. Full pytest: 912 passed, 1 warning in 94.18s (0:01:34). Final Git byte/index and manifest checks in VERIFICATION.json / STAGED_BYTE_AUDIT.json.

2. **Method 0/1/2 root LP 시간과 status**

original: M0 600.039s TIME_LIMIT, M1 600.004s TIME_LIMIT, M2 74.080s OPTIMAL; compact: M0 600.047s TIME_LIMIT, M1 600.025s TIME_LIMIT, M2 128.812s OPTIMAL. Fresh LP, no Start, Threads4, max600s; terminal optimal objective gate <=1e-8.

3. **Method=2 MIP root가 300초 안에 완료됐는가**

original: root relaxation True, barrier True, exact root processing completion=null; compact: root relaxation False, barrier True, exact root processing completion=null

4. **first branch가 관찰됐는가**

original: False, nonroot callback=None, exact first-branch time=null; compact: False, nonroot callback=None, exact first-branch time=null

5. **coefficient 실제 range**

Both: 1.0006451962467139e-13 to 400; dynamic range 3997420879052299.5.

6. **extreme coefficient가 집중된 top 5 row families**

PCS16=143072, connected_Pch=8942, connected_Pdis=8942, connected_Qmax=8942, connected_Qmin=8942 (Original, |a|<1e-12 or |a|>100; strict census thresholds. Source representative <=/>= thresholds and exact replay are separately preserved in EXTREME_COEFFICIENT_SOURCE_TRACE_COMPLETE.csv).

7. **Kappa/KappaExact**

Kappa=null; KappaExact=null. Terminal optimal simplex basis unavailable; KappaExact also omitted for factorization cost on a 954k+ row system.

8. **primal degeneracy ratio**

INCONCLUSIVE: terminal optimal basis 없음. 1e-9/1e-8/1e-7 기준 모두 미측정.

9. **near-zero RC ratio**

INCONCLUSIVE: terminal optimal basis 없음; pivot count를 추측하지 않음.

10. **exact duplicate/proportional row 수**

original: {'exact_duplicate': 75736, 'positive_proportional': 64503}, nonzero={'exact_duplicate': 75455}, constant-only={'exact_duplicate': 281, 'positive_proportional': 64503}; compact: {'exact_duplicate': 75736, 'positive_proportional': 64503}, nonzero={'exact_duplicate': 75455}, constant-only={'exact_duplicate': 281, 'positive_proportional': 64503}. Every hash hit exact-rational verified; counts relative to representative, not all pairs.

11. **grid-response block의 rows/nnz 비율**

original: rows 748224/954560 (78.384%), nnz 7022908/8282350 (84.794%), extreme share 0.5560%; compact: rows 748224/972540 (76.935%), nnz 7022908/12678118 (55.394%), extreme share 0.0263%

12. **exact row scaling 효과**

NOT_RUN (USER_STOP); H2=INCONCLUSIVE. No runtime comparison is available. Registered initial scaling would delete 342 coefficients; never optimized. Original cache/proof preserved; approved positive-power-of-two guard verified all 8,282,350 coefficients and original-unit point audit separately.

13. **exact auxiliary elimination 효과**

Exact injection-only subset: 4,608 helpers/equalities removed; physical rows/primary variables removed=0. 8,282,350 -> 34,229,409 nnz. Full 81,216-helper flattened transport has an exact-rational counterexample and is not executed. Terminal objective solve gate: NOT_EVALUATED_USER_STOP; performance NOT_RUN. Existing-point mappings and algebraic proof are separately measured in AUX_ELIMINATION_DIAGNOSTIC.json.

14. **각 root-cause 판정**

Method=1 pathology=CONFIRMED; coefficient scaling=INCONCLUSIVE; poor numerical conditioning=INCONCLUSIVE; degeneracy=INCONCLUSIVE; redundant rows=WEAKLY_SUPPORTED; response auxiliary burden=STRONGLY_SUPPORTED; voltage rows=INCONCLUSIVE; line thermal polygon rows=INCONCLUSIVE; compact continuous expansion=WEAKLY_SUPPORTED; binary combinatorics=NOT_SUPPORTED; MIP Start=NOT_SUPPORTED. Numerical evidence and causal limits attached for each.

15. **가장 큰 원인 1위**

Method1 root-LP method sensitivity / CONFIRMED

16. **두 번째 원인**

Grid matrix/factorization burden / STRONGLY_SUPPORTED; structural share is measured; exclusive causality unresolved.

17. **세 번째 원인**

Degeneracy / conditioning mechanism / INCONCLUSIVE

18. **다음 exact fix 1순위**

Root method와 basis acquisition/crossover 경로 재설계. Root barrier convergence만으로 MIP root 완료를 주장하지 않음. 행·bounds·objective·tolerance·Start 그대로 유지하고 literal root completion을 검증해야 함.

19. **기존 UB/LB/gap 유지 확인**

UB=0.5912812634331275, LB=0.5722125039436496, gap=3.22498964%. Unstrengthened F3 LP objective and raw diagnostic MIP bounds never adopted.

20. **M1_ACCEPTED=false / production NOT_RUN**

M1_ACCEPTED=false, COMPACT_M1_PRODUCTION_AUTHORIZED=false, PRODUCTION_1800S/P2/A2/M2/Actual/Fresh_AC=NOT_RUN, PROBLEM13_FINAL_VALIDATED=false. M1_ROOT_CAUSE_DIAGNOSED=true.

현재 M1이 느린 가장 직접적인 원인은 동일 LP에서 재현된 Method=1 root 풀이 지연이며, 이를 만드는 구조적 원인은 INCONCLUSIVE이다.
