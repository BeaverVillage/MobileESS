# Fresh current-matrix PR160/161 security reduction

The reduction is run after the unchanged native MILP is captured and the exact
Compact node-flow extension is constructed, before C2 static presolve. Historical
row numbers, solutions, bounds and certificates are never read. The representative
run must supply the actual row counts and native performance; this proof does not
claim a Root LP time.

## Continuous and integer route domain

The independent transport verifier checks every original flow row, the original
terminal mass equation, all existing original arc bounds, the strictly forward
time graph and every Compact node-activity link. Nonnegative flow in this DAG
decomposes into source-to-terminal paths of total mass one. At each time the sum
of connected stay masses is at most one, including fractional mixtures and paths
currently in transit. All generated original physical states are included in the
support mask. No route or possible terminal site is removed.

## Physical support and grid row implication

For each original connected state, the independent verifier reads the actual 16
stored PCS planes and both connected charging/discharging limits. Stored binary64
values are interpreted as exact binary rationals. With stay mass `m`, the net
power and reactive power belong to `m K`, where `K` is that exact polygon
intersected with `-Pmax <= P <= Pmax`. Pair intersections and membership checks
enumerate its rational vertices. Every original block must have the same planes.

The production direct-source path also checks each original injection binding:
`injection_P = sum(Pdis - Pch)` and `injection_Q = sum(Q)` at the stated site and
time. Each response binding has unit pivot and distinct direct injection axes at
one time. Negating its stored coefficients constructs its exact affine direction;
the stored RHS is its exact constant. No small coefficient is discarded. A
structurally different dependency graph uses the generic exact-rational expansion.

After normalizing an inequality to `a x <= b`, substitution gives a constant plus
an affine form in the aggregate site controls, plus any `rho_max` term. Its support
is bounded by the sum, over units, of the maximum of zero and the polygon support
over that unit's generated connected states. This follows from the homogeneous
PCS perspective and total connected mass at most one. It is valid for the entire
fractional LP domain, including simultaneous fractional charging/discharging.
The `rho_max` term uses the original finite box endpoint of the appropriate sign.
No aggregate SOC bound is applied as a per-site perspective bound.

The direct producer reuses PR160's sparse dot-product enclosure. For a row with
`n` stored terms, `k = 2n + 4`, machine roundoff `u`, computed absolute magnitude
`mag`, and smallest positive subnormal `delta`, its radius is rounded upward from
`4 * gamma_k * mag + (k + 4) * delta`, where
`gamma_k = k u / (1 - k u)`. The contract requires `k u <= 1/8`. This covers product
and addition rounding, the rounding of the computed magnitude, and subnormal
underflow. All subsequent sums, vertex products and maxima are enclosed outward.
An independent program reconstructs the raw bindings and encloses each elementary
multiply and add instead of importing this producer or its sparse gamma routine.
If the independent interval is wider than the recorded enclosure, exact rational
support is used as a fallback. A row is deleted only when its recorded upper
bound is independently shown valid and is `<=` the exact original RHS. There is
no slack tolerance.

## PR161 bounds before C2

The exact polygon's Q extrema bound every state's Q because its stay mass lies
in `[0,1]`. Bounds are converted outward to binary64. Original energy-balance
rows, not recomputed efficiencies, give coefficients `c` and `d` with
`0 < c <= d`. Each slot has total charge/discharge at most `Pmax`; nonnegative
departing travel energy is at most the maximum original travel coefficient in
that unit/slot. Thus the SOC change lies in
`[-d * Pmax - travel_max, c * Pmax]`. Exact rational interval propagation from
both original endpoint equalities gives each intermediate SOC envelope.
The independent verifier derives the same interval consequences directly from
the original energy rows. Source node activity at time zero is fixed to the
original source indicator by the original flow row and the node-activity link.

## Newly unconsumed auxiliaries

After certified security rows are removed, a continuous, unbounded, objective-zero
injection or response auxiliary whose sole remaining consumer is its defining
unit-pivot equality may be removed. Every retained-variable assignment has one
unique extension through that equality. There is no auxiliary bound or objective
term to preserve, no changed binary domain, and no consumer in which fill is
created. The exact C2 verifier checks its defining equation, the complete weighted
recursive inverse, every retained coefficient/RHS, original bound transport and
objective transport. Nonrepresentable substitutions are still rejected.

## Validation and audit

The small tests cover direct and generic source paths, LP optimal-value equality
under multiple transported objectives, nested weighted auxiliary reconstruction,
and rejection of coefficient, injection, PCS, source, SOC, metadata, certificate,
and inward-bound mutations. These tests use SciPy LP only; no Gurobi optimize or
assignment sweep is called.

Each fresh case writes `CURRENT_SECURITY_PRE_C2_SUMMARY.json`,
`CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json`, and
`CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json`. The independent proof is embedded
in `ORIGINAL_DOMAIN_EQUIVALENCE.json`. Source, matrix, domain, retained axes,
certificates and pre-bound arrays participate in the frozen transport SHA.

The qualification run replays the proof independently. Later explicitly released
campaign runs regenerate the same mathematical construction on each day's inputs;
the existing no-daily-replay receipt identifies the qualified unchanged algorithm
and records that an independent daily replay was not performed.
