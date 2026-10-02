# Full root LP numerical diagnostics

All attempts use the identical sealed F3 on both arms. Formal exactness and exact-rational matrix substitution are independent of numerical termination. Failed or interrupted attempts are retained; no SUBOPTIMAL objective is a certificate.

| Artifact | Raw status | OPTIMAL | Objective (raw; certified only if OPTIMAL) | Optimize wall seconds | Selected |
|---|---|---|---|---|---|
| ROOT_LP_ORIGINAL.json | 9 | False | NOT_RUN/NA | 1800.010593199986 | False |
| ROOT_LP_COMPACT.json | 9 | False | NOT_RUN/NA | 1800.0452153000224 | False |
| ROOT_LP_BARRIER_ORIGINAL.json | INTERRUPTED_BY_AGENT_NUMERICAL_FAILURE | False | NOT_RUN/NA | NOT_RUN/NA | False |
| ROOT_LP_BARRIER_COMPACT.json | NOT_RUN | False | NOT_RUN/NA | NOT_RUN/NA | False |
| ROOT_LP_INTERIOR_ORIGINAL.json | 13 | False | 0.5813075313147773 | 533.5722218000155 | False |
| ROOT_LP_INTERIOR_COMPACT.json | INTERRUPTED_BY_AGENT_UNCERTIFIABLE_PAIR | False | NOT_RUN/NA | NOT_RUN/NA | False |
| ROOT_LP_PRIMAL_ORIGINAL.json | 2 | True | 0.5718494620559795 | 56.675548900006106 | True |
| ROOT_LP_PRIMAL_COMPACT.json | 2 | True | 0.5718494622717606 | 74.84949670001515 | True |

Primary dual simplex timed out. Crossover pilot was explicitly terminated after a dropped basis and repeated large infeasibilities; its compact arm was not run. The automatic-dual no-crossover Original ended SUBOPTIMAL, and its compact arm was explicitly discontinued because that pair could no longer satisfy the OPTIMAL gate. Neither interruption is represented as a Gurobi terminal numerical status.

Fresh paired barrier LPs with PreDual=0 and Crossover=0 retain primal presolve. [Gurobi documents PreDual=0 as forbidding presolve dualization](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-predual). This is LP numerical certification only: the preregistered 600-second MILP Method=1 policy remains unchanged. It does not select MIP settings using canary outcomes.

Selected root objective difference: 2.1578105968700356e-10; equivalence gate: True. The F3 objective is compared with F3, while the historical stronger S2 valid LB 0.5722125039436496 remains an external original-M1 certificate. Kappa is unavailable without a basis and is reported as null. Floating dual stationarity diagnostics are not exact rational dual certificates.
