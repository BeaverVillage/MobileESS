# Canonical rows and simultaneous-deletion proof

Each original scientific row has a unique zero-based reduced-model row ID and
its unreduced-model row ID. Native names repeat, so names alone are never IDs.
M1_CANONICAL_ROWS.npz records every original sparse index, exact stored IEEE
coefficient, canonical RHS/sense, original sense/name and constant zero.
The original fixed backgrounds remain in original binding/security RHS values.
Canonicalization changes `>=` to `<=` by exact multiplication by -1, only in
the proof. Equality signs remain unchanged. Native reduced model transports
original coefficients, senses and RHS without canonical transformations.
Signed zero alone is normalized for hashes; no nonzero value is rounded.
Certificate CSV RHS and outward IEEE upper bounds use Python round-trip
decimal float spellings, interpreted as the exact recovered IEEE binary
rational (not as a different decimal rational). Exact box/implication upper
bounds and all certified slacks are written as explicit rational strings.

IEEE finite values are binary rational numbers. SHA256 lookup is followed by
complete exact sparse payload comparison. Proportional vectors are converted
to primitive integer vectors with the common power-of-two denominator and
integer gcd; normalized RHS is rational. Inequality scale must be positive.
Equality removal requires exact equality (or exact signed/scaled equality).
Different polygon normals are never merged by angle/cosine tolerance.

## Proved outer domain

All 9,216 original flow equations are matched exactly to the native time DAG.
The terminal equation allows every original sink at slot96; it does not demand
a named terminal site. The four initial sites are unchanged. Forward and
backward sweeps therefore exclude only arcs outside a source-to-admitted-sink
path. Nonnegative unit flow on a DAG is a convex combination of such paths.
The total mass crossing any time cut is one; connected stay mass is at most
one. This proof holds before integrality, so continuous M1 points are covered.

For each connected site/time the original Pch/Pdis connection bounds give
|Pdis-Pch|<=300*stay. Q connection rows give |Q|<=400*stay. Original PCS16
gives n_f P+n_f Q<=c_f*stay. All 143,072 stored PCS rows are checked exactly,
including tiny nonzero trigonometric coefficients. Rational pairwise face
intersections plus the P/Q bounds yield twelve exact polygon vertices. The
support of a linear functional on this bounded polygon is its largest vertex
value. Homogeneity implies each connected site's contribution is its stay
mass times a polygon value; the sum is bounded by the maximum support across
reachable sites, including zero transit contribution. Fractional simultaneous
site mass is explicitly covered, without assuming a single integer site.

Forward/backward SOC envelopes use exact original energy-equation factors,
initial/terminal equalities and finite original energy bounds. Travel deductions
are bounded above by the maximum feasible departure cost and below by zero.
Aggregate P bounds follow from those envelopes for both modes and fractional
relaxations. They are reported but are NOT applied separately to each site
perspective: that would require a further proof and could exclude fractional
SOC mixtures. The deletion domain deliberately retains the looser PCS outer
domain. SOC/PQ additional-removal count is therefore zero.

All 81,216 original affine definitions have unique +1 pivots and retain their
unbounded auxiliary variables. Injection rows are exact sums of the same four
MESS controls. Response variables are exact affine functions of injections,
with their stored constants and coefficients. The proof substitutes these
definitions; the reduced formulation retains them and every original column.
Security rows involve those affine responses/injections and, where present,
the original rho epigraph. Its original bounds are included. A fixed physical
response with a free rho is not misclassified as a violated constant equality.
Truly fixed violated security would stop the audit; no such inconsistency was
found. All security families, senses and physical faces are evaluated.

For a canonical row, U=constant+sum_m max(0, max_reachable_site PCS_support)
plus the original finite rho endpoint is an upper bound on the full original
integer and continuous feasible domain. Stored factors are exact. Production
sparse arithmetic encloses every dot product with a conservative gamma bound
and subnormal payment. Every later elementary multiplication and addition
rounds outward; exact rational vertices are rounded outward. Removal needs
U<=RHS-1e-8*max(1,abs(RHS),abs(U)); uncertain rows stay. This is an extra KEEP
margin, not a relaxed physical authority. All finite-bound box candidates are
also examined with exact rational arithmetic; a nonzero unbounded term cannot
certify a row. This audit found no additional box deletion.

## Closure and independent replay

Nonempty flow, connection, PCS, SOC and affine-domain proof anchors remain.
Only exact duplicate empty flow equalities may disappear; they imply 0=0.
A duplicate can point directly to an original retained representative or to
a representative with an independent absolute domain certificate. Every
absolute certificate is independent of all candidate security deletions.
The final graph has no circular chain. Therefore the FINAL retained system
still implies every removed row simultaneously. The feasible sets are equal,
not just the sampled fixtures. Keeping all column attributes and the P1
objective then preserves the optimum and valid global MIP-gap interpretation.

Independent replay does not call screen, exact_audits, exact_box or the
deletion decision. It reloads immutable original data, checks row hashes,
reconstructs injection/response definitions, recomputes reachability with an
independent transitive-closure algorithm, checks every PCS plane and enumerates
the exact rational vertices again. It substitutes affine terms with individual
outward operations, checks every support certificate, and validates exact
row implications, dependency endpoints and the final original-row subset.
Mutated row hashes, RHS, upper bounds and cyclic self-dependencies must fail.

Physical fixture optimum comparisons use the inherited 1e-7 postsolve check;
those native tests support implementation validation, not the mathematical
deletion proof. Both returned optima pass every original P/Q/SOC/grid row;
arbitrary degenerate continuous optima need not have identical coordinates.
All exhaustive integer optimum pattern sets agree, with selected patterns
checked when unique. No per-security-row LP or full-scale optimizer is used.
