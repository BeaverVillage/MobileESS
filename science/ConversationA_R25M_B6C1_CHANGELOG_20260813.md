# R25M B6-C1 changelog — Dual / Relaxation Correctness Repair

Parent B6R4 reached exact root all-column pricing closure (`43` CG iterations, guarded LB about `-2017.405959`) but the first branch-price child returned `linear_dual_unavailable_AttributeError` before any certified child lower bound was produced.

C1 reopens only the B6 solver-implementation freeze. It does not change the scientific optimization problem.

Changes:

- capture a pristine continuous path-master authority **before** restoring non-mobility and path integrality for the separate primal restricted MIP;
- remove the branch-price use of `Model.relax()` on the post-MIP model;
- branch-price children clone only the pristine continuous authority;
- fail closed unless child `NumIntVars=0`, `NumBinVars=0`, and `IsMIP=0`;
- set `QCPDual=1` on the continuous authority and every child;
- require runtime availability of linear `Pi`, quadratic `QCPi`, and path-variable `RC` before a child can be used for exact pricing;
- preserve root exact-LB reuse and exact child all-column pricing;
- add a dependency-free static lifecycle proof and a tiny Gurobi user-runtime dual-lifecycle smoke test that touches no Stage-1 data/state.

B6R4 solver implementation is superseded by B6-C1 for the dual/model-lifecycle layer. H54, 5-minute cadence, objective, physical feasible set, 3% target, causality, Threads=1, and no same-issue post-hoc MIP-start policy are unchanged.
