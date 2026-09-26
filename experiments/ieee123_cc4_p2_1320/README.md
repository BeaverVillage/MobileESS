# IEEE123 CC4/P2 removal: 1,320-second campaign snapshot

This PR preserves the implementation and audit evidence of a **stopped, incomplete**
May 2025 ablation. It does not publish final ablation results or resume computation.
The user stopped the campaign and its monitor on September 23, 2026; the hourly
recovery automation was paused. Zero of 31 paired dates are complete. The first
computing pass completed for May 1–4; the subsequent B3 stages were interrupted.

## Experimental contract

| AIDC priority | Frozen WITH_CC4 | New NO_CC4 |
| --- | ---: | ---: |
| P1 | 900 s | 900 s |
| P2 | 480 s | absent |
| Original P3 | 180 s | 180 s |
| Original P4 | 120 s | 120 s |
| Original P5 | 120 s | 120 s |
| Total per computing pass | 1,800 s | 1,320 s |

P2 time is not redistributed. Both computing passes in A1→M1→A2→M2 use this
contract. The original MESS budget/termination remains unchanged. The campaign
uses four date workers and four solver threads. Original model construction
remains outside the continuous search clock, so elapsed wall time can exceed
22 minutes per computing pass.

CC4 reserve variables, input interface and constraints are removed from
optimization, together with P2 solves and locks. The five-slot stored objective
vector retains an inert zero for compatibility; reserve shortfall is evaluated
separately as a diagnostic. Other priorities, tolerance, job/GPU/rack constraints,
migration, forecasts, electrical coefficients and MESS authority are retained.
The frozen WITH_CC4 baseline is reused without optimization. The recorded audit
checks 31 dates and 1,280 SHA leaves; historical missing April lineage exceptions
are explicitly recorded in AUTHORITY_VERIFIED.json and the recovery evidence.

The prior 1,800-second NO_CC4 run redistributed P2 time. It is superseded and its
results/checkpoints are excluded from this snapshot's paired comparison.

## Review map

- `snapshot/patches/` and `PATCH_MANIFEST.json`: changes against sealed source.
- `snapshot/original_source/`: source overrides actually used by this campaign.
- `snapshot/*.py`: orchestration, authority checks, reporting and runtime adapters.
- `snapshot/preflight_wiring/`: recorded A1/A2 budget wiring checks without solves.
- `snapshot/EXPERIMENT_MANIFEST.json`: final configuration and scientific caveats.
- `snapshot/USER_STOP.json`, `CAMPAIGN_STATUS.json`, `monitoring/`, and
  `days/*/status/`: stop evidence and stage receipts.
- `SNAPSHOT_INDEX.json`: relative paths, sizes and hashes of every exported file.

Historical RUNNING receipts, RUNNING_HANDOFF, launch PIDs and monitor timestamps
are preserved verbatim. They do not override the later USER_STOP and campaign
STOPPED_BY_USER state. In particular, stale M1_WORKER receipts are not evidence
of currently running processes. Never control a process using an archived PID.

## Numerical exception and interpretation

The previously authorized Actual repair projects initial Q onto the unchanged
exact bounds only for deviations within the original outer 1e-7 kvar acceptance.
Q_DA reference, P, physical limits and solver tolerances are unchanged. This is
an explicit exception to bit-identical frozen execution, declared by
ACTUAL_FROZEN_BITWISE_EXECUTION_UNCHANGED=false; it must not be hidden behind
OTHER_MODEL_CHANGES=false. `actual_numerical_recovery.py` contains the wrapper.

No completed new paired Actual result exists here. Do not infer whether CC4
raises or lowers Actual loading. Later complete results may describe reserve
shortfall benefits and paired ablation differences, but cannot establish CC4
electrical-safety, SLA or future-job-delay causal effects. Post-issue future jobs
are not explicitly enqueued in the realized replay queue.

## Validation and dependencies

Run `python experiments/ieee123_cc4_p2_1320/verify_snapshot.py` from the repository
root. This validates export hashes, pinned source/authority hashes, configuration,
budget evidence, stage receipts and Python syntax without importing the runtime
or invoking any optimizer. It does not repeat the original 1,280-leaf audit against
external data, nor certify end-to-end results of this unfinished campaign.

This is a reviewable archival snapshot, **not a portable standalone runner**.
The archived runtime retains absolute Windows paths, original source dependencies
from `codex/v41r4-may-final-restoration-paper-export` (recorded checkout
`04f9c73`), Gurobi/OpenDSS dependencies, local frozen inputs and D:/c5 cache routing.
Main does not yet contain those dependent PRs. Raw day outputs, solver caches,
full checkpoints and input datasets remain in the source namespace listed in the
index, rather than being duplicated in Git. Do not run the archived launch script
from this checkout; an explicit resume request and authority/path review are
required before starting any process. The source experiment and IEEE8500 are
unchanged by this export.
