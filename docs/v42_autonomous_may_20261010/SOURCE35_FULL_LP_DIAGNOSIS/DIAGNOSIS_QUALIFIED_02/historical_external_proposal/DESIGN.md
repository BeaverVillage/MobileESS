# Read-only Source35 full-LP finding and future diagnostic seam

Actual May01 Source35 full-LP entry used Method6/LPWarmStart2 on Gurobi13.0.2,
PDHGAbsTol1e-9/RelTol0/ConvTol1e-9/GPU0, original Crossover-1, Threads1 and
TimeLimit300. The original ledger records Native300.88899993896484, status11,
SolCount0 and errornull. Its matrix has779129 rows/306040 columns/8384557nnz;
same-day LP model build2.109605s. The original budget terminates when callback
Runtime reaches its cap, so status11 is expected cap interruption, not an adapter
exception or a proved infeasible model.

Original native_diagnostics.observe handles PRESOLVE/SIMPLEX/BARRIER but has no
PDHG branch. If PDHG callbacks occur, they cannot replace a prior SIMPLEX
label/iteration0 with new scalar diagnostics. Their actual occurrence is not
proved by the saved label. finished() does not query PDHGIterCount.
The actual Native log contains only the Gurobi header, so the saved evidence
cannot distinguish PDHG convergence, presolve/start processing or crossover.
The model builder suppresses output; no residual/iteration trace is available.
This is a proved observability gap, not a proved numerical root cause.

Historical same-day full-LP cap observations are Source27 Method1/P-D start/warm2
(300.004s/101916 simplex iterations/Sol0), Source30 Method0/basis/warm1
(300.011s/12718/Sol0), and Source32 Method0/basis/warm2
(300.063s/70278/Sol0). These were different attempts and valid different start
contexts; comparing iteration counts is not a performance experiment. Simply
repeating those settings has no success evidence.

Future owned Scope seam: keep the exact original incoming callback=None and all
admission/source/math/parameters guarded in f1_basis.Scope._budget.Proxy. After
its approved original call validation and actual parameter readback, construct
an observer for that exact model/request/source/current call. Supply it only to
the existing budget.native_optimize delegate. The original DateBudget.observe
continues doing Runtime/cap/ledger/progress and invokes this delegated observer
afterward. Original code and its callback must not be replaced or bypassed.

The observer authority callback should be a cheap current scope/model/captured
callable identity check. Retain the original full declared source verification
at its existing admission and completion boundaries; do not introduce whole-map
rehashing on every solver callback. Callback/publication overhead remains part
of measured Native Runtime, so any future integration needs actual overhead
observation rather than a claim that diagnostics are free.

Official Gurobi13 PDHG callbacks expose PDHG_ITRCNT, PRIMOBJ, DUALOBJ, PRIMINF,
DUALINF and COMPL. Observe those values plus RUNTIME, with isolated SIMPLEX and
PRESOLVE counters; preserve UNKNOWN for unavailable/nonfinite data. Scalar
objective/dual values are iterate diagnostics, never certified bounds or Native
Pi. Save an owned supplemental F1_FULL_LP_SOLVER_DIAGNOSTICS.json, not a modified
historical ledger or overwritten scientific receipt. Completion may additionally
query PDHGIterCount/IterCount/BarIterCount only after an actual original known
Native row; no reset/update/solution/start mutation or extra Native call.

This prototype imports no Gurobi and has not executed tests, a model or solver.
Production admission/source/callable guards remain a required future port step.
Current immutable Source35 and normal workers were not changed. All precision,
physical/integer checks, original full signed certification and 300/5400 budgets
must stay unchanged. Diagnostic-first collection adds no solver-performance claim.

Official sources:
- https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html
- https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#attr:PDHGIterCount
- https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter:LPWarmStart

Method2+LPWarmStart2 with an accepted complete current-F1 basis is not evidence
of barrier iterations. Official warm-start semantics derive vectors from the
basis, crush them, and run crossover without barrier iterations for that start
combination. Its effect/performance is untested; it must be described as a
warm crossover alternative. Cold barrier would be a different computational
candidate with sparse-factorization memory risk; no such model/probe was run.
