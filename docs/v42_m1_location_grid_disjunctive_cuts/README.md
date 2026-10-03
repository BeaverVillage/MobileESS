Standalone location/grid disjunctive-cut diagnostics from PR137 exact head
`94f8a38b7ef7b60cf5d7ffd91c86b109589fcaef`.

The existing `v42_native`, scientific cache, A1 freeze, thermal authority and
campaign implementation are read only. This package adds no production adapter.
No May campaign, Actual or Fresh AC runner is invoked.

Execution is sequential:

1. `python -m v42_disjunctive.prepare`: verify identity and acquire one optimal
   continuous baseline simplex basis with Method=2, Crossover=2, Threads=1.
2. `python -m v42_disjunctive.separate`: rank all positive fractional stays in
   split unit/slots, then reuse one LP model and the baseline basis with
   Method=1. The 1,800-second loop budget includes fixing, optimization,
   certificates and restoration; a fixed 60-second audit reserve is declared
   before the first conditional solve. Analysis/model preparation precedes it.
3. `python -m v42_disjunctive.root`: prove and separate partial cuts, copy the
   original model, add only certified violated cuts/proven infeasible-state
   fixings, and perform one fresh root LP. One 600-second MIP canary is allowed
   only after the requested material gate passes.
4. Run semantic and full tests through `v42_disjunctive.testing` after all heavy
   optimization ends. `v42_disjunctive.finalize` verifies preserved files,
   rereads the cold model without optimizing, reconstructs rational bounds and
   publishes the Korean report, flags and SHA manifest.

Each full-model solve has an exclusive-create local marker. Reexecution does
not silently retry a scientific solve. Original native logs are preserved byte
for byte, including warnings, trailing whitespace and Windows exception traces.

The conditional numerical policy is declared before conditional results.
Approximate row multipliers are projected to valid inequality signs. Original
affine equalities prove finite coordinate enclosures for otherwise free grid
auxiliaries. Those enclosures are never installed as solver bounds. Exact
`Fraction` arithmetic computes

`b'pi + min_box (c-A'pi)'x + objective_constant`.

This is a weak-duality lower bound even when stationarity residuals are nonzero;
their complete box contribution is included. Each bound is rounded down and
receives the fixed additional `1e-8` safety allowance. The inherited global L0
also applies to every conditional problem. Missing basis, failed original-row
audit, residual/duality-gap failures or a basis condition estimate above the
preregistered limit leave the state UNRESOLVED, with no usable cut coefficient.
An infeasible state requires an independently reconstructed exact rational
Farkas contradiction before a fixing can be added.

The partial cut uses original stay binaries. For an integer unit path exactly
one stay or transit is selected at each slot. Computed sites use certified
conditional lower bounds; uncomputed sites and transit use L0. Coefficients
are rounded downward from the exact difference `L_safe-L0`. Sensitivity scores
only determine separation priority.

The diagnostic feasible reference `0.6715884801665905` is used only to calculate
gap closure. It is never imported as a new incumbent or UB certificate. Material
selection requires exact validity, LB nondecrease within `1e-8`, and either
absolute LB improvement of `0.005` or relative diagnostic gap closure of 5%.
Unattempted states remain unknown; they are not counted as solved UNRESOLVED
states. A failed material gate ends this task without further experiments.

Native API references: [Gurobi warm starts](https://doc.gurobi.com/projects/optimizer/en/current/features/warmstart.html),
[VBasis](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#vbasis),
[FarkasDual](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#farkasdual).
The native solve log, rather than the presence of set attributes alone, confirms
that each conditional optimization actually accepted the basis.
