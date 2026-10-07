# Exact STAY projection study

The unrestricted proposal to replace every native STAY component with
`y[class,site,start]` is **not adopted**. It is integer-exact for identical
fixed-duration scientific classes, but it does not preserve the inherited
singleton mixed-event-flow LP projection. An exact rational counterexample
passes every row and bound of a tiny actual `v42_root.factor.add_job` model
without any optimization. Existing histogram classes retain their proven
compact representation and activate complete physical STAY support. Singleton
mixed migration graphs retain their existing representation, activate S0 plus
every valid no-action anchor, and retain the other physical STAY choices in
deterministic lazy support.

Scientific class membership and `class_exact_cardinality` are preserved.
Complete hard-valid STAY support is a domain authority: neither failure of a
new projection proof nor a tractability choice makes an omitted option
scientifically forbidden. The complete physical domain includes both active
and lazy support. Failed singleton LP equivalence therefore triggers the
explicit lazy fallback in the request, rather than unconditional expansion
of that native graph. Migration remains lazy in all scopes.

## Reference and proof scope

The accepted PR134 A1 builds `F2-CRA` via `v42_root.native.local_units`.
Non-singleton, nonfixed scientific classes already use
`factor.stay(..., eliminate_f0=True, eliminate_state=True)` plus optional
individual migration lanes and the exact cardinality row. STAY-only singleton
graphs also use the histogram when auxiliaries are eliminated. Fixed graphs
retain their immutable history. Singleton graphs containing migration use
`factor.add_job`, whose event-flow relaxation is different.

The study proves elimination from the **fixed-duration histogram extended
formulation**, for any finite physically authorized support. It does not claim
that the old restricted support and the new physical support have the same
feasible set. Changing support is the intended new scientific domain authority.
It also does not replace an unrelated relaxed event-flow representation merely
because the integer trajectories coincide.

The API in `v42_a_stage_domain_v2/stay_projection.py` is independent of native
model building and solving. `incidence(job, starts, N, class_id)` takes keys in
`(site,start)` order. `scientific_column` accepts inherited Runtime and signed
grid coefficients from its caller. `representation_gate` and `add_stay_unit`
fail closed for fixed histories, unproved references, and singleton mixed
migration graphs. Existing native histogram construction needs no replacement:
it is already the projected model. The exact cardinality row remains the
caller's obligation because it also includes the unchanged migration lanes.

## Integer projection proof

For one scientific class with exactly `N` identical members and fixed service
duration `D`, let `S` be the complete authorized finite STAY support. For each
`(k,s)` in `S`, define an integer count `0 <= y[k,s] <= N`. Preserve

```
sum_(k,s in S) y[k,s] + sum_selected_migration_lanes = N.
finish[k,s+D] = y[k,s].
occupancy[k,t] = sum_(s: (k,s) in S, s <= t < s+D) y[k,s].
```

For an integer feasible point, assign exactly `y[k,s]` class members to the
complete one-segment option `(k,s,s+D)`. The migration lanes already describe
one complete job each. The cardinality equality assigns every member exactly
once. Every member has the same frozen scientific signature and whole-gang
compatibility, so a deterministic assignment of sorted members to sorted
complete options preserves all row and objective effects. No fractional GPU
gang or averaging of individual service is introduced.

Conversely, every allocation of the members over these STAY options has the
histogram `y[k,s]` equal to its number of members at `(k,s)`. Its occupancy and
finish counts equal the displayed expressions. These two constructions prove
the equality of integer schedules modulo interchangeable member labels, while
retaining the exact cardinality and every scientific row effect.

## LP projection proof for existing histograms

Consider the extended histogram with explicit finish and occupancy variables,
the displayed equalities, and all inherited global variables and rows. For
every real nonnegative `y` satisfying cardinality with nonnegative migration
amount, the displayed equalities provide a unique lift. Each finish is bounded
by `N`. Each occupancy sum is at most `sum(y) <= N`, so the eliminated
auxiliary bounds are redundant. This argument uses real values and therefore
proves LP projection equality, not just integer equivalence.

Every eliminated variable has an explicit linear expression. Substitute those
expressions in all global rows and all objectives. Projection and lifting then
preserve each row's activity, sense, right-hand side, and objective value.
Unchanged migration variables and shared grid/CC4 variables can be arbitrary
feasible values; the argument holds for every such value. It does not infer
global feasibility or optimality from local support.

## Runtime, grid, CC4, and objective identity

Known GPU at `(k,t)` is exactly `GPU * occupancy[k,t]`. Completion at `(k,e)`
is exactly `finish[k,e]`; the inherited `completion_risk`/`coefficient_vector`
provider is evaluated at that same site and completion, with the same provider
semantics, completion offset, survival kernel, and gamma. Its coefficients are
not recalibrated. The Runtime finish-count auxiliaries used by the native
binder retain their original linear equality and upper bound.

The native grid sees the same site/time known-GPU and Runtime interfaces, and
retains its same anonymous CC4 workload, reserve variables, power conversion,
signed sensitivities, voltage bounds, line ratings, and transformer rows. A
known STAY column adds no direct anonymous CC4 forecast coefficient. The known
GPU and Runtime interfaces consumed by the original CC4/headroom equations are
identical, so substitution preserves those equations too.

P1 `rho` is preserved through the identical grid interface. P2 has unchanged
STAY coefficients: migration count zero, shift magnitude `abs(s-reference)`,
and prestart relocation `int(k != reference_site)`. These coefficients apply
to both the histogram and its lift. The historical signed shift expression
is recorded separately as metadata, not used as the new earlier-start P2
magnitude. On the old domain `s >= reference`, signed shift and magnitude were
equal. The common no-action option retains zero shift and relocation costs.

## Why the unrestricted LP proof fails

Take one PENDING job with `D=3`, source site A, starts `{0,1,2}`, and source
finishes `{3,4,5}`. The complete graph has physically authorized migration
events; set every migration event, state, and WAN auxiliary to zero. Select

```
y[A,1] = 1,             all other y = 0.
f0[A,3] = 1/2, f0[A,5] = 1/2, f0[A,4] = 0.
r0[A,1] = 1, r0[A,2] = 1,
r0[A,3] = 1/2, r0[A,4] = 1/2, r0[A,0] = 0.
```

The source balances, terminal balance, one-start row, source-exit row,
`full_service=3`, and every relaxed bound pass exactly. Zero migration also
passes the full transfer, deterministic WAN, optional routing, and destination
constraints in the actual native fixture. The histogram at `y[A,1]=1` instead
forces `f0[A,4]=1` and occupancy one at slots 1, 2, 3, zero at slot 4. Thus the
LP projections differ in both completion and known-GPU coordinates. Runtime
and grid LP effects can differ as a consequence. Integer STAY equivalence is
insufficient to adopt this as an exact replacement of the inherited LP.

The counterexample is an explicit tiny synthetic fixture. It is not a stress
date input, a production model, or a solver result. Its all-row replay uses
exact rational arithmetic over the actual generated matrix coefficients.

## Model size and validation

For `S` support keys and `U` occupied site/time states, projected histogram
locals contain `S` count variables and no finish/occupancy variables or local
equality rows. Its unprojected histogram contains another `S` finish variables,
`U` continuous occupancy variables, and `S+U` equalities with
`2*S + U + D*S` nonzeros. The one external cardinality row has `S` STAY terms;
its migration terms remain unchanged. `N=1` count variables are binary and
`N>1` count variables are integer. These are exact local structural counts,
not an extrapolation of full grid/Runtime matrix size.

The existing accepted projected histogram already has that compact structure,
so its representation-only size delta is zero. Enlarging support adds required
count keys and global bindings. No claim is made that a complete new domain is
smaller than S0; the static census separately quantifies the support increase.
The complete-STAY physical forecast is distinct from the active initial domain
forecast: the latter leaves unproved singleton mixed-flow new STAY choices
lazy. The rejected singleton replacement has no advertised size saving.

Focused tests cover all integer histograms of a tiny support, real LP lifts,
optional migration/cardinality conservation, exact objective projection,
inherited Runtime values and signed grid coefficient identity, deterministic
incidence, exact structural counts, native histogram expression identity, and
the all-native-row event-flow counterexample. Ten tests passed. Three tiny
native models were built for static matrix/expression audits; no optimization,
relaxation solve, or presolve was called. No stress date was optimized, no
historical PASS date was rerun, and no production optimality is asserted.
