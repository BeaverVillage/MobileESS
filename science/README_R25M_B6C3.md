# R25M B6-C3 — True-Dual-Certified Dual Stabilization

B6-C3 preserves the B6-C1 continuous-certificate lifecycle and B6-C2 global
path cache / child batch pricing.  It changes only candidate-column generation.

## Stabilized candidate generation

For root and child RMPs, a lagged dual center is maintained.  Candidate pricing
uses a convex blend of the current true dual and the lagged center.  This is an
acceleration heuristic only.

Every candidate produced by the stabilized dual is re-evaluated under the
**true current RMP dual** and is inserted only if its true reduced cost is
strictly negative beyond the frozen pricing tolerance.

## Exact closure remains unchanged

The exact minimum-reduced-cost path computed under the **true current dual** is
still the only pricing-closure oracle.  Stabilized duals, stabilized candidate
paths, restricted-master bounds, and k-best ranks never become lower-bound or
certificate authority.

Therefore B6-C3 can change column-generation order and iteration count but cannot
change the original feasible set, objective, or the validity of the global 3%
certificate.
