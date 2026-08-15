# R25H / B1 — Certificate-Focused Solver Search

B1 is a solver-search-only patch on the frozen R25G exact formulation. It does not change variables, constraints, objective, H54, 5-min cadence, causality, or the 3% economic MIPGap acceptance rule.

When `MOBILEESS_R25H_B1_CERTIFICATE_FOCUS=1` and `issue>113`:

- `MIPFocus = 3` is frozen for the economic certificate search.
- `ImproveStartGap = 0.0` disables the pre-target solution-improvement switch.
- The previous rolling `MIPFocus = 1` primal-recovery override is bypassed.
- Rolling `Heuristics = 0.10` is unchanged in B1.
- Previous plan remains VarHint-only; no rolling MIP Start is introduced.
- MIPGap remains 0.03 and Threads remain controlled by the existing frozen runner contract (Stage-1 authority: 1 thread).

No long issue152 solve is performed in B1. Runtime comparison is deferred to B3/B5 according to the fixed B1–B7 roadmap.
