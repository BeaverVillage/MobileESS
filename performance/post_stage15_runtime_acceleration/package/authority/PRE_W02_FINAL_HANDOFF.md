# Mobile ESS K9-H7 — Pre-W02 Final Handoff

Status: `AUTHORIZED_FOR_W02`

This release authorizes only the frozen `W02_2025-01-13` four-policy scientific episode. It does not claim that W02, the first six representative weeks, or all twelve representative weeks have been executed. Remaining weeks remain gated by the outcome-blind W02 acceptance token.

## Frozen production path

Each 5-minute issue executes only:

`PRE → policy/event decision → planner when required → conditioned dispatch → Fresh Exact OpenDSS → bounded safety recovery when required → POST → atomic commit`

Independent result recalculation, dense Parquet materialization, statistics, and paper figures are post-run jobs. They do not run inside the controller loop and perform zero Gurobi or OpenDSS validation solves.

Fresh-AC limits remain exactly `0.95 ≤ V ≤ 1.05 pu`. One phase-aware finite-difference cut/re-solve is permitted. If correction is exhausted, the unsafe candidate is not committed; the same PRE is restored, `GRID_HARD_RISK` requests at most one H54 Full Replan, and unresolved failure remains fail-closed.

## Pre-W02 evidence closed

- Fresh-AC recovery: 4/4 methods.
- Deterministic same-PRE repeatability: PASS.
- Four-process × four-thread isolation, injected child termination, quarantine, and restart: PASS.
- M1–M4 immutable exogenous-source identity and sampled content SHA: PASS.
- M2/M3 no Local Repair; M4 no movement; mobile path/state closure: PASS.
- Same-solve observability, required cardinality, finite values, units, and compressed Parquet materialization: PASS.
- Offline independent recalculation: PASS for all four bounded method samples, with zero scientific reruns.
- Statistical and paper-output synthetic/bounded dry-run: PASS.
- Twelve representative weeks × four methods = 48 outcome-blind episode bindings: frozen.

Measured observability serialization overhead on bounded v2 issues was 1.89% median and 5.27% p95 by paired phase subtraction; absolute serialization was about 0.024 seconds per ordinary no-recovery issue. The 48-episode compressed analytical storage projection is approximately 11.5 GB. Post-run materialization time is never reported as controller runtime.

## Local execution

From the package directory:

```bash
cd /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package
bash RUN_W02_4POLICY_ACTUAL.sh --preflight-only
```

The preflight-only command performs no scientific Gurobi/OpenDSS episode run. A completed 2,304-issue shared source is validated and reused without GPU rematerialization. After it prints `W02_4POLICY_PREFLIGHT_ONLY_STATUS=PASS`, start the actual W02 run:

```bash
bash RUN_W02_4POLICY_ACTUAL.sh
```

Equivalent one-shot form:

```bash
cd /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package
bash RUN_W02_4POLICY_ACTUAL.sh
```

Progress in a second terminal:

```bash
cd /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package
/home/jaewon/miniconda3/envs/power_v61/bin/python tools/SHOW_W02_PROGRESS.py
```

After W02 finishes, run the offline recalculator/materializer and apply the frozen technical-integrity acceptance protocol. An unfavorable scientific result is not a rerun reason; only the machine-readable `RERUN_ELIGIBILITY_CONTRACT.json` may authorize a same-configuration rerun.
