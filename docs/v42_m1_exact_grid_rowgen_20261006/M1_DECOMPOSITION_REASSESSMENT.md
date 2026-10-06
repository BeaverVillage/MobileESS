# Historical lesson and current structure

V16.3 May02 bounded reference evidence is preserved byte-for-byte in history/.
Standard BD:29 iterations,29 cuts,71.488491s. CL-MC-BD:7 iterations,57 cuts,
38.376431s. Both equal monolithic objective0.7683165991452516 to relative2.89e-16.
Monolithic itself takes4.82s on this historical case. Multi-row/critical-line
reduced decomposition iterations; these data do not demonstrate universal
decomposition speedup or transfer V16.3 tolerances/gamma=.98 to current V42.
V16.3 was a different continuous B3 formulation, not the current full M1 domain.

Preserved GitHub authority snapshots of PR115/116/117/120 document route/mode
master with P/Q/SOC/grid in giant recourse. PR115 first recourse1433.581s and
Kappa5.11554e15 rejects its ray. PR117 native1085.591s plus701.267s Phase-I
does not certify a cut. PR120 exact rational equality repair finally certifies
two cuts, but native recourse still1367.159s and1031.127s, Kappa7.81611e15 /
3.81613e15. Validity is necessary and eventually possible; practical full M1
acceleration was not established. This giant recourse architecture is rejected.

PR124 exact node-activity representation cuts binary count95.477% but increases
rows/nnz. Fresh LP compact74.85s versus original56.68s;600s canaries do not show
post-root/global-gap benefit. It is not adopted or tested inside this candidate
unless primary row generation first produces promising measured progress.

PR157 D-W/Early B&P evidence and code stay untouched. Its conservative dual
certificate is valid, but the600s experiment keeps UB.6694159238756877,
LB.5687115725336208 and15.04361455% global gap. All new evidence is separate.

CURRENT structural conclusion: DIRECT_EXACT_ROW_GENERATION_POSSIBLE.
Every current grid auxiliary has a unique native affine definition in P/Q;
the definitions are acyclic, continuous, free, and objective-free. They do not
appear in temporal MESS rows. Direct security evaluation is a certified original
matrix dot product. No native grid LP or giant P/Q/SOC recourse is needed.

All208312 route/mode binaries and individual Pch/Pdis/Q/SOC/rho remain in master.
No Top-K routes, restricted column pools, compact route replacement, ML pruning
or scientific threshold change. Maintain sparse injection/response factoring.
Auxiliary columns removed=0; removal is not required to obtain substantial size
reduction and would expand repeated all-face coefficients.

Current M1:886017 rows,316743 cols,208312 binaries,108431 continuous,8447855nnz.
Security rows:598465. Affine grid definitions/auxiliary columns:81216.
Initial master:287552 rows,316743 cols,208312 binaries,2784047nnz.
Estimated CSR bytes104918332→34558776, before native solver copies/factorization.
This is a structural memory estimate, not a native-RSS performance assertion.

Bounded exactness:12 physical fixtures and1536 exhaustive discrete assignments.
49 feasible/1487 infeasible, original and row-generated status/optima agree.
Scalar exact rational residual replay, coefficient/sign identity, deliberate
omitted-row violation, constant rows, and mandatory final separation tests pass.
The proof retains the entire continuous fiber and all discrete trajectories.

The benchmark preregistration gives one shared continuous600s development window
with sequential original-monolithic and row-generated arms. No production solve
or publication runtime is authorized by the resulting comparison.
