# Exact physical-column decomposition

BASE: PR99, `3309cd230cd8235201f5578d392241fa98e059bc`.

Let X_j be the finite set of complete locally valid PR99 physical trajectories.
Each path preserves the authorized start/site, full Q50 work, physical 1800 s
checkpoint phase, 900 s control rounding, optional single migration, deterministic
fixed-path maximal-rate WAN transfer including zero-rate waiting, restart, whole
gang, rack/residency and the complete authorized completion tail. Immutable
resource usage is checked locally; interactions between movable jobs stay global.

The full master replaces each x_j by a convex combination of X_j. Each column
contains one valid trajectory's GPU, WAN, active-transfer, frozen Runtime risk and
intervention coefficients. Fixed PR99 true singletons contribute constants.
Convexity, capacity, CC4, reserve and native grid remain in the master. Pricing
minimizes a linear functional over X_j for fixed duals; jobs are independent at
that point. No grid equations are replicated in pricing.

The mathematical full-column LP represents the product of conv(X_j) intersected
with the original global constraints. The RMP is an inner restriction of that
LP. Missing columns remain implicit; they are not declared impossible. This is
column generation, not prescreening. A finite full-column optimum is certified
only after an optimal RMP and a complete exact sweep return minimum RC >= -1e-7
for every movable job. No unpriced, timed-out or failed job permits convergence.

An exhaustive full-column LP is the authoritative bounded benchmark. Equality
with the naive continuous relaxation of the PR99 event MILP is not assumed:
conv(X_j) can strengthen that relaxation. For integer schedules, a binary full
column master chooses one element of X_j and has the same physical trajectory
space as PR99. That equivalence is tested only on bounded cases.

Even a converged full May LP is not an integer A1 plan. Fractional lambda is
allowed. This task does not implement branching, Branch-and-Price, a restricted
master MIP canary, M1/A2/M2, Fresh AC or a response kernel.

All historical evidence is preserved byte for byte. New files describe a
decomposition and its measured limitations. Runtime ML, gamma90
2.423057443558147, TS 1024/1605, PR97 CC4, 780 GPU capacity, grid coefficients,
WAN and MESS authority are inherited unchanged.
