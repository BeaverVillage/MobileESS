# Adaptive four-MESS joint route optimization

IEEE123 B2 May01 only. Original Source18r physics, all96 slots, fixed AIDC,
PCS16, travel ETA/energy, terminal SOC and every Grid security row are kept.

The earlier running local joint canary is preserved in
`docs/v42_b2_global_local_multistart_dual1800`. Its actual runtime is reconciled
without rewriting its partially persisted ledgers. The first redesign pilot
is in `docs/v42_b2_adaptive_compact_joint`. The user's subsequent fresh1800s
authorization is recorded separately in
`docs/v42_b2_adaptive_compact_joint_fresh1800`.

The actual new four-vehicle MILP has32 route-selection binaries plus384 charge
modes. Exact route incidence simultaneously controls all four vehicles.
No vehicle is forced to move or forced to retain the old MESS03 route.
Original FULL replay is the only UB admission rule.

Two compact formulations were independently audited:

* `compact.py`: retain original route coordinates and rows; replace redundant
  node integrality with exact one-hot lambda links.
* `direct.py`: remove216674 route/node/flow coordinates through `x=T z`.
  Preserve every original row as `A T z sense rhs`, with independent exact
  dyadic coefficient closure, unchanged RHS, and an exact inverse lift of Raw.

Direct substitution shrinks input variables but worsened observed same-pool
Native runtime18.729→29.366s. It is explicitly rejected as the default backend.
The retained Source Exact Joint Extended Formulation is the fallback. No
speedup is claimed for the extended formulation18.747s observation either.

`beam.py` reuses PR219 Label/Minimax and PR220 original-DAG closure/retiming.
`scoring.py` replaces a guessed unchanged-vehicle schedule by measured FULL
incumbent P/Q. `fresh_feedback.py` reuses the verified PR21964-label Beam body
with that scorer, adds existing depth4 reservoir paths, and selects a fixed
eight-path pool per vehicle using joint complementarity and diversity.
It uses no fabricated LP duals, exact pricing or column-generation claims.
Every pool retains STAY, one-MOVE, multiple-MOVE and the certified winner.
Beam depth and ranking are heuristics; original physical limits are separate.

The new run starts at Native0 under a distinct1800s maximum, with historical
1738.949s kept separately. The initial pilot spent63.642s with no UB or compute
gain. The policy therefore stopped further Native dispatch. Post-pilot feedback
and the new candidate-pool inclusion proof run at Native0; their UB performance
is not claimed. Existing run-start markers prevent repeating or resetting runs.

Replays and audits do not call Optimize. Source/Policy seals must remain intact.
The fresh worker supports a scoped `CANCEL_REQUEST.json` cancellation path;
the controller blocks dispatch and the active worker uses `model.terminate()`
in its callback, preserving Raw and actual Runtime.

The Korean final report, all38 actual call receipts, cost phases, two plan CSVs,
six scientific plots, source hashes and the independent PASS review are in the
fresh1800 output directory. B1/B3/IEEE8500/campaign/Actual are not executed.
