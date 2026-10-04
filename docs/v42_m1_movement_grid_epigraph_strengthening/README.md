This standalone diagnostic starts from PR138 exact head
`4ea94878a40327a11e57c7a9b69030da9e158993`. The accepted scientific
model and all inherited source/report files remain byte-identical.

The execution order is `prepare`, `polish`, `oracle`, `separate`, `root`,
then `canary` only after the material gate passes, followed by semantic and
full `testing` and read-only `finalize`. Modules live in `v42_movement`.
The full scientific MPS, original matrix/data and route cache are immutable
external inputs identified by SHA in `M1_MOVEMENT_GRID_BASE_IDENTITY.json`.
Exclusive optimize markers live outside Git in `MOVEMENT_GRID_LOCAL`; no
scientific optimizer retry or parameter sweep is allowed. Four numerical
environment thread limits are set before imports. Run exactly one worker.

The exact epigraph representation is a factored DAG of native dyadic
coefficients. `GRID_EPIGRAPH_ROW_COEFFICIENTS.npz` retains original face
terms, binding-row identifiers and certified outward dense coefficient
enclosures. Each binding has output coefficient +/-1, so its local exact
inverse uses only sign changes. The archive's dense lower/upper arrays
enclose the exact rational expanded expression; they are not asserted to
be a rounded exact coefficient identity. Tests verify all factored face
terms against the immutable matrix and check exact rational dense
reconstruction across all slots.

PCS vertices are computed with exact rational intersections of the actual
native 16-face coefficients and original bounds for both integer modes.
Support minima use outward coefficient and vertex enclosures. Site minima
include transit zero. SOC, travel-energy and cross-time coupling are
ignored only to enlarge the support relaxation. A selected movement arc
forces its unit's P/Q to zero on `[depart,connect)`; arrival slot `connect`
is excluded. Other units keep optimistic supports. Max across all original
epigraph rows and the inherited certified L0 gives the conditional bound.

All 131,350 saved fractional movement arcs are evaluated. Their individual
two-case inequalities are included in the separation CSV even when delta
is zero; zero-delta inequalities are reported separately from nontrivial
cuts. Clique construction allows only positive coefficients from the same
original outgoing flow node for the same unit. Exact duplicate removal and
clique dominance affect added-cut efficiency only. No route, site, time,
SOC or P/Q domain changes occur. No conditional full LP is executed.

The separate zero-action polishing diagnostic fixes only the previously
validated discrete pattern. Original continuous variables are free and no
slack or point repair is introduced. An OPTIMAL raw point must pass strict
1e-8 original-row/bound audits, exact fixed-integer matching and independent
physical checks to be available as a Start. Availability does not certify
a global UB or actual MIP Start acceptance.

The result is material FAIL: support-derived conditional bounds do not
exceed L0, no cuts are added, and the fresh root reproduces the baseline.
The independent upper enclosure audit proves this result is not a rounding
accident in the optimistic support construction. It does not upper-bound
true physical conditional M1 optima. The gated canary is NOT_RUN; no canary
log or Start acceptance receipt is fabricated. The sole next direction is
trajectory-level exact Dantzig-Wolfe / column generation / branch-and-price,
reported without implementation.

The 1,458-stage May/B3 dry plan, A1 authority and Actual feedback firewall
remain unchanged. Campaign optimizer/Actual/Fresh AC calls are all zero.
Native handled OpenDSS exception traces from unchanged legacy regression
tests are retained verbatim; pytest exit codes and final summaries are
recorded independently. `FINAL_REVIEW_KO.md` gives the requested 30-item
report; `VERIFICATION.json` and `SHA256_MANIFEST.json` provide provenance.
