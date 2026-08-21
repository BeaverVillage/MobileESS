# R25M B6-C1 — Dual / Relaxation Correctness Repair

B6R4 reached exact root all-column pricing closure but the first branch-price child could not expose linear-row `Pi`. C1 reopens only the B6 solver-implementation layer.

The repair separates model lifecycles: after root exact pricing and deterministic primal column enrichment, a pristine **continuous** path-master copy is captured before any variable integrality is restored. The restricted primal MIP continues on the original model object. Every branch-price child is copied only from the pristine continuous authority. No `Model.relax()` call on a post-MIP model is used for the B&P base.

Each optimized child fails closed unless it is continuous and exposes all three runtime objects needed by the exact pricing contract: linear `Pi`, quadratic `QCPi` (`QCPDual=1`), and path-variable `RC`.

No H54, 5-minute cadence, MIPGap, physical constraint, objective, causal input, OpenDSS gate, or MIP-start policy is changed. This is not a Stage-1 authority release.
