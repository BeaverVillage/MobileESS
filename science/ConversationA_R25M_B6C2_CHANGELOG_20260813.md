# Conversation A — R25M B6-C2 Changelog

## Scope
Global Path Cache + Parent/Child Column Inheritance + Child k-best Batch Pricing.

## Implemented
- Added exact `k_shortest_paths_with_node_restrictions` DP.
- Added global trajectory metadata cache shared by branch-price nodes.
- Cached visited-node sets, sparse master-column coefficients, and objective values.
- Branch nodes import all globally known branch-compatible trajectories before the first RMP solve.
- Child pricing inserts the exact minimum-RC path plus up to 8 exact k-best negative-RC paths per MESS per iteration.
- Exact minimum restricted path remains the only pricing-closure oracle.
- Added runtime cache/inheritance/batch counters to B6 result metadata.

## Scientific status
- Feasible set: unchanged.
- Objective: unchanged.
- H54 / 5-min / 3% / Threads=1: unchanged.
- Future actual / future D2 leakage: unchanged and forbidden.
- Same-issue post-hoc MIP start: still forbidden.
- B6-C1 continuous dual lifecycle: preserved.

## Runtime
No long issue152 solve was performed in B6-C2.
