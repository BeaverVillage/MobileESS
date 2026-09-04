# R25M B6-C2 — Global Path Cache + Child Batch Pricing

B6-C2 preserves the B6-C1 pristine continuous certificate lifecycle and changes
only branch-and-price orchestration efficiency.

## Changes

1. A global path cache stores each discovered original-DAG trajectory once,
   including its visited-node set, sparse projected master column, and objective.
2. Every later branch node inherits all cached paths compatible with its required
   and forbidden occupancy branches before its first RMP solve.
3. Child pricing still computes the exact minimum reduced-cost restricted path as
   the closure oracle, but additionally inserts up to 8 exact k-best negative-RC
   paths per MESS from the same true dual in one iteration.
4. A path discovered under one branch may be shared elsewhere only because the
   path itself is a valid trajectory of the original frozen mobility DAG; child
   branch restrictions are rechecked before inheritance.

No restricted-master bound or k-best candidate is promoted to scientific lower-
bound authority. Exact all-column closure remains mandatory.
