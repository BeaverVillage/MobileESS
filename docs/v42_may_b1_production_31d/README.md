# Current V42 May B1 detached production

This branch ports the accepted historical implementation, generates new current V42 input bindings for every May date, and executes one complete B1 day at a time: A1 → Planning freeze → fixed Actual materialization → Fresh OpenDSS → physical validation freeze. B0 is a verified completion barrier only. No historical optimized freeze, V39K witness, B0 result, or synthetic diagnostic is a current B1 result.

## Implementation authority

PR24 (`56f0c08c1239ad6dca25c4fb0ffec590a1c97a68`) establishes V37 causal per-day execution. PR25 (`87e531bb4dd6198ec16e20589f2a307af4ef52b6`) supplies V39E `campaign_adapter.build_day`, 31-day orchestration, production entrypoint, and V39L Task Scheduler/monitor infrastructure. PR26 (`79a4d44baa5fae016d152b85f0488f777784e3b7`) supplies terminal-safe authority. `HISTORICAL_LINEAGE_AUDIT.json` records Git blob hashes and preserved imported source hashes, plus V39K's 124 frozen-decision hash entries. Its historical fallback solutions/parameters are not imported. Full old V39E freeze JSONs are absent from the current source stores and PR25's tracked tree; their forensic hashes do not authorize a new result.

`v42_b1_production.replay.build_day` ports V39E's verified frozen PCC/IT/GPU axis materialization. The audited V37 B1 path calls V36 without the B2/B3 restoration loop. V36 constructs the solver-free `FrozenTrajectory` and calls the original `dayahead.v28r2.opendss_backend.run_fresh_opendss`. This port calls that unchanged 96-slot backend body with explicit current V42 source bindings. No new ActualBackend policy is invented. Historical B1 Actual semantics are fixed Planning power/service replay, without reconstructing or rescheduling decisions from retrospective job outcomes. Current source-backed realized background load and PV are applied in Fresh.

## Current authority overrides

B1 has AIDC flexibility ON, MESS OFF, current 780-GPU whole-gang/rack/WAN/Runtime/CC4/C1 authority, one day worker, Gurobi Threads=1 and a total A1 solver budget of 1800 seconds across the existing two objective groups/four sequential lock components. The accepted PR133 F2-CRA equations and independent certificate remain unchanged. The May01 date literal is routed to the current bundle date; each electrical cache and C0/C1 binding is specific to its date. All 120 transformer phase-current rows are explicitly bounded with current source NormalAmps. Voltage bounds are 0.95–1.05 with zero margin.

Fresh starts from the exact source initial controls, runs autonomous regulators, retains four fixed ON capacitors and zero CapControls, and never copies Planning taps. Actual reoptimization and local/global P/Q repair are zero. MESS P/Q and B2/B3/M1/M2 calls are zero. All four physical violation counts must be zero; convergence alone cannot make a day PASS.

Every current physical known job remains in the native raw ledger, including Q50-expired RUNNING records with issue-boundary physical occupancy and future Runtime risk. Positive nominal service enters the native scheduling model. Common references are newly generated using the accepted current grid-blind FCFS Q50 policy. Historical TS boundaries are admitted only for an identical snapshot and reference start; incompatible boundaries fail closed. In these current references, eligible operating-day standby TS domains are absent. Prestart placement and authorized checkpoint migration remain enabled where allowed. No latency budget, future endpoint, or alternate TS window is invented.

## Durable execution

`tools/v42/start_b1_may_detached.ps1 -Root C:/v42_b1_runs/<id8>` creates a dedicated Windows Task Scheduler registration using the accepted V39L registration/terminating-shell implementation. The command sets the exact worktree and Python, appends separate stdout/stderr logs, allows battery transitions, has no execution-time limit, ignores concurrent task starts, and adds current-user logon recovery plus infrastructure restart. Machine recovery occurs on the user's next logon under that interactive account.

Atomic checkpoints and stage receipts require matching run/arm/date/stage version/Git/scientific/input/checker identities and every output hash. Completed valid stages are reused. Exact surviving worker identities are adopted after coordinator death; a command-specific scan closes the spawn/PID-publication gap. Resource interruption discards the partial attempt and retries the same full contract when admissible. License/OOM/crash retries are bounded and terminal infrastructure failure stops the campaign. Scientific failure is terminal for that date, blocks its dependent stages, remains visible, and other independent dates continue. No foreign process is stopped.

Before each new A1, the independent coordinator admits only sufficient RAM/commit and no active foreign full-scale native heavy process. Tests, static verification, normal Codex activity, and idle imported native modules are exempt. One-second telemetry and heartbeats continue in WAIT_RESOURCE, and the task resumes automatically. Hard memory/commit/sustained-paging guards first request termination, then can stop only the exact registered owned worker tree if it does not respond.

The separate visible PowerShell monitor is a port of V39E's readonly PID/creation/command/heartbeat liveness and failure-latch display. Its exact title is `Mobile ESS V42 May B1 Production Monitor`. Atomic read errors retain its previous snapshot. PASS dates disappear; failures remain; missing solver metrics and unobserved Fresh progress show N/A. Closing the monitor has no effect on the campaign.

## Validation and launch

`VALIDATION.json`, `B1_INPUT_BINDING_AUDIT.json`, `NATIVE_MODEL_BINDING_SMOKE.json`, `NATIVE_PORT_DIAGNOSTIC.json`, and `DETACHMENT_SELF_TEST.json` record prelaunch checks. The native fixture/model smoke are explicitly synthetic diagnostics with zero optimization calls and zero production day PASS claims. `tools/v42/preflight_b1_may.py` supersedes the earlier audit-only failure once the historical port checks pass.

After committing and pushing this implementation, `python -m v42_b1_production prepare --audited-input-root C:/v42_b1_audit` verifies source hashes and freezes the new run. Task/monitor launch receipts and live status are in its short run root. The detached campaign itself creates the final scientific result; launch does not assert 31-day completion and never advances to B2/B3.
