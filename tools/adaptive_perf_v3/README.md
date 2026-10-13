# Adaptive 4-MESS joint performance version

This additive version evaluates IEEE123/B2/2025-05-01 only. It keeps Source18r physical/Grid/PCS16/ETA/travel-energy/SOC/AIDC constraints and all 384 charge modes. Four independent one-hot route pools are solved jointly with P/Q/SOC. STAY, single MOVE, and multiple MOVE remain available to each vehicle.

The version was developed in `D:/v42_b2_adaptive_perf_v3_20261013`, while its frozen predecessor continued in `D:/v42_b2_adaptive_compact_joint_20261013`. `bootstrap.py` intentionally reads the predecessor from its recorded path. Copies of all additive predecessor artifacts are included byte for byte for provenance; recorded runtime paths and raw evidence are not rewritten.

The SHA-bound integer alias cache replaces repeated static expansion. Every new pool still checks named DAG incidence, original aliases, dynamic links, source bounds, and the exact warm start. Direct coefficients are checked as exact dyadic sums; sparse EF retains original route/helper coordinates and removes only implied node integrality. Native CSR/Bounds/Types/Objective/Start readback and original FULL replay are mandatory.

Grid scoring covers all 96 slots. Backward terminal-SOC recovery and signed P/Q service/charging lookahead rank routes heuristically. Neither scores nor restricted solver bounds are certified global bounds. The K48 certificate remains the global LB.

The same 1,800-second authorization includes the 63.642-second pilot, V2 calls, and V3 calls. Handoff records preserve the old model/Raw/ledger/source SHA and carry actual Runtime forward. No budget reset, parallel heavy solver, forced movement, LB Optimize, B1/B3/campaign, or Actual AC run is permitted.

Recorded executions must not be restarted. `RUN_STARTED.json` blocks duplicate dispatch. Reproducing preparation or tests requires a fresh output directory and preserved source authority; do not change a sealed version in place. Native0 mode creates and reads back a model without Optimize or presolve. Cache tests reject changed Source/version identities and corrupted content.

Final evidence is in `docs/v42_b2_adaptive_perf_v3`: the Korean report, exact Native ledger, timing CSVs, matched-formulation results, candidate/selection diagnostics, 96-slot P/Q/Mode and 97-boundary SOC plans, independent FULL replays, source seals, and artifact index.
