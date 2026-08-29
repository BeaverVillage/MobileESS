# CODEX Day-Ahead AIDC Joint V16 Implementation Report

## Status

V16 authority reconciliation and contract implementation passed its engineering tests, raw-source reproduction, and controlled solver-equivalence fixture. The scientific May/June campaign remains **LOCKED** because April-only HPO/final model refit, full scientific Monolithic/BD solve, G13 OpenDSS, and G14 result audit are not complete. No scientific result was fabricated.

## A. Reused from prior work

- `input_contract.py`, `traffic_da.py`, `mobility_energy_da.py`, `mess_physics.py`, `grid_lp.py`, `benders.py`, `opendss_qsts.py`, and the result writer were retained.
- Existing 96-slot, MESS, phase-mask, Pi/Farkas, cut-selection, LB/UB/gap, and immutable-QSTS tests were rerun successfully.

## B. Patched for V16

- Replaced V15 `P_NF/G_NF` authority with source-backed `P_IT_REF/G_REF/W_F`, the ESIF-Kestrel hierarchy, the Apr/May/Jun split, and V16 IDs.
- Replaced the unresolved AIDC HOLD path with frozen V16 authority while preserving locked-evaluation fail-closed gates.
- Updated `REFERENCE_COMPUTE_SCHEDULE_V2`, result matrices, replay status policy, and reference-delta terminology.

## C. Newly implemented

- Historical-vs-D1 eligibility isolation, package-only Dataset312 kappa reproduction, Direct96/coupling contracts, positive target scaling, H100-node-hour service conservation, reference delta, realized remove-then-add replay, fidelity firewall, fixed compute/MESS replay, controlled solver equivalence, and independent recalculation.

## D. Superseded / disabled

- `P_NF/G_NF`, Sep-Oct/Nov/Dec split, artificial deadline/slack, individual queued-job D-1 injection, and physical-background quantile interpretation are absent from the V16 production path. Historical precode/today artifacts remain untouched as provenance only.

## E. Test results

- Day-Ahead: 72 passed.
- Focused prior-work regression: 112 passed plus 71 subtests.
- Full repository: 424 passed, 4 skipped, 84 subtests passed, 3 pre-existing Windows/environment failures (one Gurobi 13.0.3 behavior; two missing POSIX `fcntl`).
- Full raw inventory: 389 files / 57329540933 bytes, PASS.
- Kestrel sharing/volume and Dataset312 kappa raw reproduction: PASS.
- Controlled Monolithic/Standard/CL-MC-BD equivalence: PASS.

## F. Remaining blockers

- April-only HPO and one Aug19-Apr30 production refit with a real Transformer backend.
- Materialized AIDC forecasts/reference schedule and the identical full scientific B3 Monolithic/BD comparison.
- Scientific 96/96 Fresh OpenDSS forecast/realized QSTS (G13).
- Complete scientific result matrices and independent audit (G14).
- Frozen mapping source files are referenced by SHA authority but were not found inside this checkout for direct re-hash.

## G. May/June access status

LOCKED. May primary and Jun1-25 replication were not opened by model training, tuning, smoke, optimization, or fidelity code during this run.
