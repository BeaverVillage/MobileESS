# Conversation A — R25N B6-C5R1 Gap Authority / Target Certificate

## Actual C5 diagnosis
- exact root pricing closed: PASS
- U = -1937.9964663366604
- L = -2017.405996772834
- frozen Stage-1 gap = 4.097506%
- 3% target lower bound at current U = -1996.1363603267603
- required additional global bound lift = 21.26963644607372
- B&P produced no lift because its first exact child hit `rmp_status_9`

## Gap fixes
1. Explicit 0.03 B6 target; no silent historical 0.015 default.
2. `certificate_lower_bound` is the single acceptance/audit bound authority.
3. Restricted integer-master `MIPGap` is non-authoritative diagnostic.
4. Absolute gap and origin-sensitive translated gap are reported separately.
5. Negative/near-zero/sign-crossing warnings are explicit.
6. Route-energy tie-break semantics are explicit; procurement-only gap is not invented.
7. Non-finite partition bounds cannot produce a PASS.

## Exact B&P corrections
- Restricted RMP infeasibility without Phase-I/Farkas pricing is no longer pruned as full-node infeasibility.
- One incomplete child no longer aborts the tree.
- Unresolved subtrees retain a conservative valid ancestor lower bound.
- Partial globally valid bound lift is promoted even before reaching 3%.
- Child bounds are monotone with inherited parent bounds.

## New acceleration
A fixed-root-dual mobility-partition prepass computes exact restricted DAG minimum reduced costs and converts them into conservative child lower bounds without child QCP re-solves. This directly targets the frozen 3% threshold.

## Runtime rollback based on actual C5
- C3 stabilization: disabled in C5R1 runtime (code retained optional).
- C4 QCP strong probes: disabled in C5R1 runtime (code retained optional).
- scientific model/objective: unchanged.
