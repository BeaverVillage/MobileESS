# M-stage trajectory CG adapter contract

Scientific base: PR #202 `a5ce8685eb694f750dca7a539d010eece38ece37`.
This research adapter imports software mechanics, never historical M1 scientific
inputs, dual authority, resource policy, columns, matrix, or certified bounds.

## Actual source reuse

`LEGACY_SOURCE_PROVENANCE.json` records the inspected Git objects, file SHA256 and
method SHA256. `legacy_mechanics.py` preserves these function bodies (only class
indentation was removed):

| Source | Function | Current binding |
|---|---|---|
| PR142 `v42_dw_throughput/common.py` | `next_smoothing_weight` | Discovery center update only |
| PR147 `v42_arc_floor/cg.py` | `Experiment.smooth_snapshot` | True/source-row Pi and convexity vectors; current output paths |
| PR152 `v42_dw_continuation/cg_reuse.py` | `Mechanics.add` | Current full-horizon block validation, exact RC, coupling products, pool |

PR142 run/worker, PR147 CG loop and both PR152 CG sources were inspected. Their
ordering (pricing, admission, master, new true pricing, certificate, checkpoint)
and durability policies are adapted in `integrated.py`, not wholesale imported.
Historical process workers, M1 authority, iteration count and time caps are not
used. PR153 multi-column acceleration and PR157 early B&P remain OFF. At most one
distinct eligible trajectory per vehicle is admitted per round.

## Axis and stage contract

Each invocation admits the current Case SHA, original CSR Matrix SHA, Domain SHA,
Stage, fixed-input SHA and fixed-decision SHA using `case.load`. Each local vector
must match the original column **indices and order**, not merely variable names.
Master source rows equal the sorted union of original coupling and NONUNIT rows.
The entire immutable local original matrix contains mobility, all 96 SOC slots,
travel energy, mode, PCS P/Q, and original initial/terminal conditions. Coupling
is retained in the Master, not imposed separately on each trajectory.

The master uses original NONUNIT variables and source rows, four convexity
equalities, original objective/ObjCon, and the existing trajectory factory.
Power-of-two transport is `A_solver = R A_master`, `b_solver = R b_master`,
`S = I`, original primal = solver primal, original dual = `R Pi_solver`.
Readback requires exact binary64 CSR equality; bounds and objective are unchanged.
No tiny coefficient deletion, epsilon, tolerance changes or sign clipping occur.

Local admission checks every original local row/bound numerically at the existing
1e-8 criterion and requires literal original integer/binary values. It is explicitly
**NUMERICAL_ONLY**, not an exact mathematical hull-membership certificate.
Exact rational coupling products and exact true price/RC are recorded separately.
Near-equal grid projections are recorded and never automatically pruned.

## True-price authority and conservative coverage

Historical M1's +/-1 objective shortcut is replaced by original-coefficient exact
arithmetic: `q_m = c_m - B_m^T y`, `RC = q_m^T x - eta_m`. Stabilization affects
only discovery. Admission, native certification pricing and exact Global LB all
use the current TRUE original-coordinate dual. Convexity eta is excluded from
the integer pricing objective and from the final global accounting.

Only same-MESS original-axis saved duals are candidates for reuse; their old
numerical bound is never reused. Each is recomputed against current q and current
branch bounds, with exact RHS, finite-box correction and native-objective rounding
correction. Wrong-sign Pi is rejected; raw Pi, current bounds, objective and rejection
reason remain saved. Every binary split covers both children; unresolved descendants
inherit valid ancestor lower bounds. Unit bound = minimum over all covering leaves.
This proves a conservative full-domain bound without claiming integer optimality.

The independent original-matrix checker evaluates exactly:

`c0 + b_coupling^T y + certified_NONUNIT_minimum + sum(certified_unit_minima)`.

Neither RMP objective nor Native BestBound is certificate authority. Published LB
is the maximum of the frozen existing certificate and the new independent result.
Full reduced-cost closure requires all four certified missing-trajectory minima
minus current eta to be nonnegative. Native OPTIMAL is insufficient.

## Checkpoint and budget authority

Checkpoint validates all six identities, row/variable axes, column bytes, true
dual bytes, discovery-center bytes and the measured Native sum. Resume restores
pool, columns, smoothing and round state. It never resets prior Native usage;
unresolved IN_FLIGHT calls and terminal checkpoints prohibit automatic replay.
The original ledger is read-only and carried unchanged as the new ledger prefix.
After the stopped integrated trial, the gate anchors the latest 141.40300178527832
second ledger by SHA and retains the original 436.16500186920166 second campaign
ceiling. The pilot stop latch forbids automatic restart, including in a new folder.
Optional cached `point_sha` metadata is derived from the verified saved vector
when absent; an explicitly supplied mismatching point SHA is rejected.

One sequential worker, Threads=1, at most three rounds. Per round each vehicle
requests 6 seconds discovery + LP certificate nodes 8/3/3 seconds (20 total),
and Master 15 seconds: at most 95 seconds requested per round. Additional measured
Native cap is 300 seconds and cumulative cap 600 seconds, including prior
136.16500186920166 seconds. Requests are clipped to remaining budget; overshoot is
recorded and prohibits further calls. No external worker or production hooks.

No negative true-RC column, source/audit/certificate failure, budget reserve,
exact closure, or an unresolved large pricing gap without >=0.001 improvement in
the **independently certified candidate** stops the loop. Candidate progress below
the published LB is diagnostic and never reported as published LB improvement.
An exact full-DW upper witness below the 3% target would also stop; numerical
Master feasibility alone cannot authorize that ceiling conclusion.

B2/B3 share the adapter, but Stage/fixed inputs stay independent. B3 M1/M2 are
NOT_RUN until their actual current A1/A2 fixed inputs exist.
