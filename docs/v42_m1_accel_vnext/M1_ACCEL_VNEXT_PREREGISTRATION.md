# Exact M1 acceleration screening

Scientific authority is PR152, exact head 63e81dc3b6d236549f566e65e07dcd05ac0a160c:
1,604 columns, certified LB 0.5687115725336208, audited UB 0.5741861223241257.
PR153 is unselected experimental evidence only. All scientific authorities and
the authoritative pool are immutable. New benchmark columns stay in this worktree.

Develop and decide stages 1–5 sequentially. Each full-scale experiment has one
continuous 600-second wall deadline, no retries or extensions. Source/checkpoint
audits and identical input preparation finish before timing. The performance
denominator starts before model build and includes update, native solve, column
admission, postsolve audit, and model disposal. No repository hashing inside a
variant's timed interval. Shared watchdog/process sampling runs throughout.
If a confirmed foreign PID is in an actual native optimize/OpenDSS phase before
admission: WAIT_RESOURCE. Imports/reservations are not conflicts. On overlap,
cancel only our owned solve and label NONCOMPARABLE; never control foreign tasks.
RAM floor 1 GiB; commit <95%; no catastrophic sustained paging. Threads=1.

1. Compare cold rebuilt RMP versus persistent RMP with an optimal simplex basis
   extended by nonbasic new columns at zero. Initial solve uses original PR152
   barrier/crossover settings; appended warm solves use dual simplex, LPWarmStart=2.
   Fixed two additions of independently audited PR153 baseline fixture columns.
   Both variants solve 1,604 and the same two appended pools. Native cap 90 seconds
   per LP, subject to remaining wall. Objective tolerance 1e-8, matrix identity
   exact. Retain only if equal audited objectives and practical total time improves.
2. One dual box-step design, Discovery only. Radius derived once from checkpoint
   dual oscillation; deterministic serious/null updates; no radius/alpha sweep.
   Baseline alpha=0.1; one four-way 20s Discovery and one true RMP each. Retain for
   at least 20% improvement in audited UB decrease per complete pipeline second.
3. Audit exact Markov sufficiency of continuous resources before implementation.
   No SOC/P/Q discretization. Implement a specialized exact or LP-valued hybrid
   only if its full domain coverage and bound semantics can be proved. Toy
   enumeration against native pricing precedes any bounded pricing comparison.
4. Elimination requires universal continuation inclusion, not a favorable SOC or
   a negative incumbent. Exact duplicate arc elimination requires identical
   original local/coupling columns and a proved at-most-one aggregate. Reject
   families without such evidence; no domain pruning by assumption.
5. All cuts must hold for every original integer trajectory and have explicit
   pricing coefficients. Local valid linear cuts are implied by exact block
   convexification and cannot strengthen the full D-W optimum. No invented fleet
   resource constraints. Root-only experiments; no branch nodes.

Only individually retained stages enter ONE final combined benchmark, <=600s,
versus PR152. Select for >=20% end-to-end efficiency/work benefit, or independently
proved material matched-time bound improvement. Raw column count is insufficient.
An empty retained set means the final candidate is the unchanged identity
algorithm; its single paired benchmark still runs, with selection false.
No continuation or B&P.

Solver FeasibilityTol/IntFeasTol/OptimalityTol=1e-8; affine audit=1e-6;
Discovery admission requires exact Fraction true-dual RC <=-1e-7; no-negative
certificate requires a valid global BestBd >=-1e-8. Incumbents are never lower
bounds. Stabilization never replaces true-dual certification. Full local physics,
coupling, route domain, all 96 slots, four MESS, and material threshold unchanged.
