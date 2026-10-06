# Exact original-grid constraint generation

Let the frozen current original M1 be min c'x+c0, with unchanged variable
bounds/types, non-grid rows N, affine definitions D and grid security rows G.
The initial relaxation contains N and D and an empty controlled subset of G.
Every original arc/mode/Pch/Pdis/Q/SOC/rho variable remains in the master.
An auxiliary definition has native +1 pivot and triangular dependencies:
injection depends only on individual P/Q, and grid response only on injection.
All 81,216 grid auxiliaries are free continuous, objective-free and unique.
Thus candidate security values require affine evaluation, not recourse LP.

At iteration k, S_k is a subset of original row indices G. The original
feasible set is contained in every master N ∩ D ∩ S_k. A valid native master
lower bound is consequently a lower bound for the original M1, even if its
candidate violates omitted rows. Only a fully independently validated original
integer point supplies an upper bound. Restricted-column bounds are not used.

Exhaustively evaluate G\S_k and add ALL violated original rows. Row insertion
uses the same CSR indices/data/RHS/sense, with no coefficient transformation.
S_k grows monotonically. No trajectory/domain is removed; no generated row
can exclude an original-feasible point. With terminal master optima and no
violations the solution is an original optimum. With unfinished native solves,
only the original global UB/LB and unchanged .005 gap authority can accept P1.
Infeasible/time-limited/suboptimal states are distinguished explicitly.

Termination or P1 acceptance additionally requires an exhaustive pass of ALL
original grid rows, including active, constant and duplicate rows in the full
unreduced matrix. Every original non-grid row, bound, exact integer decision,
route, temporal SOC, connection/mode and PCS validator must also pass.
The final separation is not replaced by a critical subset or native status.

Stored IEEE coefficients are the current scientific matrix authority. Sparse
dot-products are screened only through outward roundoff enclosures covering
product, accumulation, RHS subtraction and subnormal operations. Ambiguous
threshold rows are evaluated with exact binary-rational Fraction arithmetic.
No approximate sensitivity, row deletion, sign clamping or tolerance relaxation
is introduced. Separation uses the unchanged 1e-8 numerical authority; existing
affine physical postsolve authority is 1e-6 and bounds/route equality remain1e-8.

Policy for this experiment: ALL currently violated rows, sorted original index.
No gamma=.98 inheritance and no near-critical threshold are used. Multi-row
addition is already mandatory. Optional critical-line additions are not tested
or selected in this bounded experiment. Every security family is eligible.

We retain exact sparse factor auxiliaries rather than expand their affine
expressions into each face. Mathematical elimination is possible and unique,
but expansion recreates dense repeated coefficients; current row deferral alone
reduces initial native row/nnz size materially without floating transport changes.

This algorithm has no ML/Top-K/trajectory-pool restriction, grid recourse optimization,
or the historical giant P/Q/SOC recourse. No production runtime is inferred.
