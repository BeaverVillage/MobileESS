# Exact permanent-row audit preregistration

Base PR159 exact head 07c9ae892335b34a32faf82cff6266ab5cf80aac.
Isolated branch codex/v42-m1-exact-redundancy-audit and worktree
C:/v42_m1_exact_redundancy_audit_20261006. No fleet experiment outputs read.
All immutable PR159 scientific inputs are read-only; mutable audit outputs and
caches belong only to this worktree. Four existing MESS units, all columns,
objective, route/SOC/PCS/grid/numerical authority remain identical.

Before seeing screening results: deterministic exact sparse hashes plus full
payload comparison; exact binary-rational proportionality; exact finite-bound
box certificates; exact affine auxiliary elimination solely in the proof;
forward/backward route reachability and SOC outer propagation. Security upper
bounds use homogeneous per-site PCS16 and route flow mass <=1, hence convex
combinations of reachable states, covering continuous route/mode relaxations
as well as integer paths. A site union maximum is valid for both. SOC bounds
may stay loose; never assume integer mode to tighten continuous bounds.

Stored IEEE coefficients denote exact binary rationals. Interval operations
round each elementary operation outward with nextafter, rejecting nonfinite
enclosures. Rational checks and independent rational replay are used for
removal certificates where applicable; independent per-operation outward
interval replay covers every affine support removal. Strict positive slack
must exceed 1e-8 times max(1, absolute RHS, absolute certified upper); this
additional keep margin never weakens a physical limit. No approximate
duplicate/proportional tests, no historical
inactivity, no sampling-based deletion, no face/quadrant omission. Equalities
can only be removed as exact duplicates. A constant-violated security row stops
the audit. Keep all ambiguous rows. Certificates depend on final retained
rows; closure is checked after all proposed deletions. Binding/flow/PCS rows
used as domain proof anchors are retained unless replaced by an exactly
equivalent retained original anchor. No variable elimination or route changes.

Validate the existing twelve physical fixture families and all 1536 bounded
binary assignments, with small original/reduced native models only. Add
adversarial voltage directions, line/transformer faces, reverse P/Q, terminal
SOC, unreachable site, transit, exact duplicate, near non-proportional and
near-boundary cases, plus dependency/certificate corruption checks. Independent
full-scale replay reconstructs every removed row from original data and does
not call the deletion decision function.

Heavy monolithic comparison requires all proof/fixture/replay gates, reduction
>=20% rows OR >=15% nnz, and no active foreign scientific optimizer. Inspect
processes immediately before any heavy optimize. Never interrupt others. On
conflict finish static audit and stop BENCHMARK_DEFERRED_RESOURCE_CONFLICT.
Otherwise low-value gate stops without heavy solves. If eligible, sequential
original then reduced, <=300 native seconds per arm, identical PR159 POLICY
and defaults (MIPGap=.005), all auxiliary variables retained, no callbacks,
no row generation. Selection additionally requires meaningful compute gain;
memory alone or reduction size alone cannot select. No mass LP certificates.

## Bounded comparison freeze after user resource-release instruction

The user reported stopping the competing experiment and explicitly instructed
continuing eligible execution. Recheck live native processes before each build
and again immediately before each optimize. Existing conflict evidence stays
in the namespace. One original then one reduced monolith; TimeLimit=270s in
both, with a 300s wall cap per arm including construction/audits. The identical
270s limit leaves room for build/final verification. All 208 native parameter
values are captured and compared except the necessarily different LogFile.
Use PR159 original-monolithic POLICY, PreCrush=1 and LazyConstraints=0, the
same independently full-original validated seed and inherited certified
full-domain LB in both arms. Callbacks only observe/audit and enforce wall;
they add no constraints or cuts. Store verbatim native BestBd separately from
the inherited downward-safe global LB contribution.

Selection requires >=15% root completion time improvement if both complete,
or reduced valid LB improving >=.001 and gap >=.001 at matched native budget,
or clear beyond-root transition when original remains incomplete at root.
No selection from lower Work on unmatched unfinished roots. These explicit
engineering tests are frozen before either benchmark arm. No second comparison.
