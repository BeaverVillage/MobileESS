# R25Q B6-C5R4R3 — numerical envelope and verified resume

- R25P completed and committed issues 113–115 with global gaps 1.98496%, 1.84513%, and 0.86461%; all three passed numerical and Fresh Exact OpenDSS gates.
- R25P stopped before committing issue 116 because root-CG RC accounting remained 1.16976e-4 after retries, slightly above the fixed 1e-4 audit tolerance.
- R25Q extends strictly tighter fresh-KKT recovery through `BarQCPConvTol=1e-12`, adds homogeneous barrier and quad precision escalation, and applies the same policy to B&P children.
- The fixed 1e-4 audit tolerance is not loosened. If all strict retries remain outside it but below the bounded 5e-4 hard cap, the measured error becomes the pricing guard and is conservatively subtracted once per MESS from the minimization lower bound.
- R25Q cryptographically binds the R25P archive and issue-115 POST state, re-verifies the complete issue 113–115 prefix, and continues from issue 116. Non-binding issue-115 route/MESS plans are used only as VarHints.
- No scientific feasible-set, objective, causal-information, or gap-semantics change is made.
