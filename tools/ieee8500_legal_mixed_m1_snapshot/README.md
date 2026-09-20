# IEEE8500 legal_mixed_M1: conversation snapshot

This PR preserves the screening, production adapters, forensic evidence, and partial Actual results from the September 16–20 conversation. It does **not** claim that B2 Actual or B3 is complete. The campaign remains explicitly paused by the user.

## Verified result status

| Policy | Full 96-slot Fresh max line loading | Final Actual max line loading | Status |
|---|---:|---:|---|
| B0 | 0.9834285677838648 | 0.9815501233047021 | Fresh and Actual PASS |
| B1 | 0.9817357673991524 | 0.9800703763390655 | Fresh and Actual PASS |
| B2 | 0.9908030235623484 | **Not available** | Fresh PASS after 10 restoration rounds; Actual paused |
| B3 | **Not available** | **Not available** | M1 route search paused |

B2 Actual before QSAFE has rho=1.014294076389173. This is **not** its final Actual result. Slots 0–31 have accepted Q checkpoints; slots 29 and 30 each required 5,001 evaluations. The subsequent slot-32 search was interrupted, resumed using the accepted prefix, and explicitly stopped again. B3 must not be restarted by importing or reviewing this archive.

## What changed

- Native candidate generation, finite-difference sensitivity, placement/capability screening and restricted policy proxies selected `legal_mixed_M1`. Historical proxy results are kept separate from full-day results.
- Transport spatial-correlation P0 is `SUPERSEDED_NONBLOCKING_DIAGNOSTIC` by explicit user correction. Identity, traffic coordinates, travel matrices and mobility authority remain fixed. Native-service-compatible phase/voltage interfaces and inheritance of 18 existing MESS service PCCs were authorized.
- Full-day adapters preserve 1 worker / 4 Gurobi threads, native grid and workload rules, s_DC=s_MESS=1, background alpha=.574 and PV alpha=.50. ASCII runtime paths address Gurobi native I/O failures; hash-identical missing evidence files resolve historical paths without skipping gates.
- A concentrated 20-state seed collapsed after re-siting. It was generated from the current B0, rather than literally loaded from an old placement. First separation expanded to 1,175,712 line states. The current-layout diverse seed uses 438 states; unchanged full separation closes at roughly 500 **line** states (plus ~21,000 voltage states). Five diagnostic candidates preserved objective values; 14 production candidates had median 6.543 s versus ~401 s previously. No final active-set cap or hard-coded rho floor was added.
- B2 linear rho=.94014572 failed primary exact AC at rho=1.10865194. Existing fixed-discrete restoration achieved Fresh rho=.99080302. The old slot-75 peak fell to .89497347, but slot 32 on `tpx226308719b0` became the new maximum. A diagnostic-only Q removal at STA08 reduces that branch from .99080302 to .18258782, while the slot-wide maximum becomes .91633575. That counterfactual is not an accepted 96-slot schedule.
- Actual adapters freeze accepted DA inputs, preserve arrival gating, battery audits, causal QSAFE and final independent AC replay. A supplementary frozen wrapper returns nonconvergent trial measurements with `converged=False` so the existing feasibility predicate rejects them instead of aborting the entire search. API errors and nonfinite results still fail closed.
- Checkpoint resume reconstructs the accepted exact causal prefix and retains Q/events for completed slots. An interrupted slot has no persisted trial cache and therefore repeats the same deterministic search with its original per-slot cap. Trial counts after resume cover resumed work, not a complete historical trial ledger.
- The existing monitor gains Actual columns and uses the existing port. No new dashboard or infrastructure retuning is introduced.

## Reading the snapshot

`files/RESITING_SCREEN/IEEE8500_MAY01_20260916` contains screening code and evidence. `IEEE8500_TRANSPORT_COHERENCE_20260916` contains the superseded spatial diagnostic. `IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916` contains production adapters, seed proofs, physical closure, Actual audits and checkpoints. `files/monitoring` contains the existing dashboard updates.

`MANIFEST.json` records the source-relative path, byte count and SHA-256 for each unmodified copied file. Original status/history files can describe earlier runs or contain stale metadata; the final current Actual status is `Actual_B012/STATUS.json` (`PAUSED_USER`). Older notes prohibiting Actual were superseded by the user's later approval; the last stop request remains authoritative. Historical `SCREENING_RULE.json` contains inherited fields; the full-run electrical engine and AC reports explicitly use background .574.

## Reproduction limits and safety

These are **archival runtime adapters, not an installable standalone runner**. Their original absolute paths, imports, external authority hashes and fail-closed guards are preserved. The working copies depended on `C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance`, sibling IEEE8500 adapters, licensed Gurobi/OpenDSS, frozen traffic/workload inputs and WSL realized traffic. Related baseline material is in PRs #42, #45 and #48; this PR does not merge or replace those branches.

Large coefficients, candidate caches, solver checkpoints, native binary arrays, raw traffic datasets and complete trial logs are not published here. Their available dependency references/hashes remain in the evidence; this snapshot alone cannot reproduce full production. No solver license, credentials, or tokens are intentionally included. Source paths are provenance, not portable entry points.

Run `python -B tools/ieee8500_legal_mixed_m1_snapshot/verify_snapshot.py` from the repository root for content hashes, JSON and Python syntax, result-label consistency, and accepted-prefix checks. It never launches a solver or campaign. Production/Actual were not rerun for this PR.
