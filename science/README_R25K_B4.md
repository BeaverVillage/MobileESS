# R25K / B4 — Root/Branch Exact Strengthening

B3 showed that all three MIQCP kernels spent the complete 300 s diagnostic budget at node 0. B4 therefore targets the root-cut-to-branch handoff rather than adding another long solve.

Frozen changes:
- MIQCPMethod=-1 (B3 winner).
- CutPasses=3 to cap diminishing-return root cut loops.
- BranchPriority: STAY 30, node occupancy 20, job/defer 10, charge/discharge mode 5.
- Exact auxiliary symmetry break `mode <= active_STAY`.
- R25G resource-cover cuts densified from 6-step checkpoints to all steps.
- Pure mobility/SOC prefix cover at every prefix.

No physical constraint, objective, H54, 5-min cadence, 3% MIPGap, causality, or Fresh Exact OpenDSS contract is relaxed. No long issue152 solve is run in B4.
