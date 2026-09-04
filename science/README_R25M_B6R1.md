# R25M B6R1 — Gurobi solution-attribute lifecycle fix

The first B6 runtime reached an **optimal convex continuous RMP** in well under one second, obtained QCP duals, priced new mobility paths, and then failed before the first CG record was written. The cause was orchestration-only: `addVar()` followed by `m.update()` invalidated the just-solved model's `ObjVal`, but the code read `m.ObjVal` afterward.

B6R1 caches the solved RMP objective before any column is added, uses that cached value as the exact all-column lower bound when pricing closes, and updates the model only after all dual/reduced-cost/audit data from the current solution have been consumed. No scientific constraint, objective, mobility path set, 3% certificate rule, or causal contract is changed.
