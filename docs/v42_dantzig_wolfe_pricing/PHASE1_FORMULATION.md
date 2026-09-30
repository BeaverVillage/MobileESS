# Formal Phase I

Before adding artificials, for each original global row i freeze
scale_i = max(1, abs(RHS_i), max_j abs(A_ij)). These are deterministic physical
row scales, not penalties tuned on May outcomes. Convexity remains exact.
For equality rows add +scale_i a_i^+ - scale_i a_i^-; for <= rows add
-scale_i a_i; for >= rows add +scale_i a_i. All artificials are nonnegative.
The normalized Phase-I objective is the sum of all artificial variables.
Variable bounds and initial one-path convexity remain intact.

Pricing uses the optimal Phase-I master duals and the same physical oracle as
scientific levels. No artificial belongs to a physical column. Nonzero artificial
use is never accepted as a physical solution. Phase I must reach <=1e-9 and
complete exact pricing for every movable job before every artificial UB is fixed
to zero. Scientific optimization then has precisely the inherited hard rows.

If complete exact pricing has no negative RC but normalized artificial objective
exceeds 1e-9, report DANTZIG_WOLFE_LP_INFEASIBLE for the full represented physical
column space. If the external budget ends before that certificate, feasibility
is unresolved; no infeasibility claim follows from a positive restricted-master
artificial value. The initial feasible local trajectories need not be globally
feasible, so this initialization is necessary.

The generic all-row elastic model adds many continuous variables, including
native grid rows. Its cost is measured separately from physical RMP size. No row
generation, dual stabilization or changed capacity is introduced in this task.
