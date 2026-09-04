# R25M B6-C4 — Reliability Strong Branching

B6-C4 preserves C1 continuous certificate authority, C2 global path cache/batch pricing, and C3 true-dual-certified stabilization.

## Change
The previous branch rule selected the most fractional occupancy, which allowed very late-horizon states (e.g. h=53 of H54) to win solely because they were near 0.5. B6-C4 replaces this with a small reliability-strong-branching shortlist. Mobility states receive only a mild early/mid-horizon shortlist bias; the final branch is chosen by cheap child-RMP probe scores or reliable pseudocosts.

## Exactness boundary
Strong-branch probe objectives and pseudocosts are **selection-only**. They are never used as scientific lower bounds, never prune a node, and never certify the 3% gap. After a branch is selected, each child must still reach true-current-dual all-column exact pricing closure before its lower bound is admitted to the branch-and-price tree.

## Runtime policy
C4 performs no long issue152 solve. Integrated speed and branch quality are measured once in C5.
