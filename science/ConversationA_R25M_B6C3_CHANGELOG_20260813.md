# Conversation A — R25M B6-C3 Changelog

## Scope
Dual Stabilization for root and child exact column generation.

## Implemented
- Added lagged exponential dual centers for root and each branch-price child.
- Added convex smoothing of current duals for acceleration-only candidate pricing.
- Added up to 8 stabilized k-best candidates per MESS/iteration by default.
- Re-evaluate every stabilized candidate under the true current dual before insertion.
- Keep the exact true-current-dual minimum path as the sole pricing-closure oracle.
- Added per-iteration stabilization audit metadata and aggregate root statistics.

## Exactness guard
- Stabilized duals are never scientific lower-bound authority.
- Stabilized candidates cannot cause pricing closure.
- A stabilized candidate is inserted only when its true current reduced cost is negative.
- Root/child all-column closure still requires exact true-dual pricing.

## Scientific status
- Feasible set: unchanged.
- Objective: unchanged.
- H54 / 5-min / 3% / Threads=1: unchanged.
- Future actual / future D2 leakage: forbidden and unchanged.
- Same-issue post-hoc MIP start: still forbidden.
- B6-C1 and B6-C2 contracts preserved.

## Runtime
No long issue152 solve was performed in B6-C3.  Stabilization performance is deferred to the B6-C5 integrated runtime gate.
