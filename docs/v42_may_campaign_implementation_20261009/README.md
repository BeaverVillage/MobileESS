# May B1 → B2 P1 campaign

The approved entry point is `v42_may_campaign`. It binds the existing May12 A-stage and M-stage Adaptive Primal–Dual Hybrid to fresh dated inputs. The previous blocked preflight at commit `e43bab57aac210546ebd7012be426f00b7f97311` and `docs/v42_may_b1_b2_p1_campaign_20261009` remain historical failures.

## Execution contract

| Arm | Original algorithm | AIDC | MESS | Certified Global Gap |
| --- | --- | --- | --- | --- |
| B1 | May12 complete pricing, integer recovery, full-domain bound | Optimized | P/Q zero | ≤0.5% |
| B2 | Adaptive role-exchange LNS and exact LP dual certificate | Independently regenerated FCFS/Q50, fixed | Optimized | ≤3% |

All 31 B1 dates run sequentially through one Worker and must have terminal receipts before B2 can start. B1 PASS is not required for transition. B2 uses three independent Worker slots, initially assigned May01, May02 and May03. A completed or failed slot automatically receives the next unstarted date while the other slots continue. Every terminal date has one attempt. An interrupted Worker without a valid terminal result is preserved and classified. Surviving Workers are adopted by exact PID, creation time and command identity. OS locks exclude a second Coordinator, duplicate dates, B1/B2 overlap and more than three B2 Workers. There is no automatic single-worker fallback.

Each arm/date has a 5,400-second inclusive optimization/certification wall clock, starting at Coordinator dispatch, and 5,400 seconds of measured cumulative Native runtime. All Native calls use Threads=1 and the remaining wall/native budget with validation reserve. Worker processes have separate dated inputs, outputs, caches, TEMP/TMP, Gurobi NodefileDir, logs and Native ledgers. Original OpenDSS NewContext engines use each date's private D output directory. P2 and B2 AIDC optimization are forbidden. Fresh D-day AC is separately measured after P1 acceptance and never extends its optimization budget.

## Original implementation reuse

- A: original PR134 dated input producer and native binder; original May12 canary preparation, Phase I, complete pricing, integer recovery, independent bound certificate and original physical replay. Thin routing changes dates, isolated paths and shared budget. Aggregated running classes with a migration domain retain the original nonconstant tag, even when the initial pool contains one STAY option. Class cardinalities and all original options remain intact.
- M: original `v42_native.mess.MESS`, compact/Presolve transport and same-day original grid model; original `v42_m1_anytime` schedule/UB/LP/master functions; original integer and exact dual checkers. Current case/context and column dimensions replace historical fixed case identities. Each case proves the original-to-C3A matrix and integer/LP domains before Native. Exact rational proofs handle extended infinite bounds and duplicate auxiliary defining-row subtraction.
- Operations: original Planning Freeze, Actual realization and 96-slot Fresh OpenDSS code, current autonomous controls and original MESS P/Q/SOC mapping. No Actual MILP or P/Q repair. AC convergence and authority checks govern execution acceptance; actual voltage/current/loading outcomes remain reported values under the existing evaluator.
- Orchestration: original PR134 atomic writes, checkpoint persistence, process identity and HTTP monitoring helpers, with a separate approved campaign entry point. Historical execution guards still apply outside its explicit frozen permit.

## Native=0 evidence scope

Runtime evidence resides at `D:\MobileESS_v42\runtime\v42_may_campaign\candidate_20261009_implementation01`.

`MAY31_ACTUAL_INPUT_LOADER_BINDING_AUDIT.json` checks each date through the actual original loader: causal jobs, windows/resources, 96-slot original electrical coefficients and constraints, original route arcs, mobility/SOC and independent fixed AIDC authority. It explicitly does **not** claim 31 full MILPs have been materialized upfront. The May01 A and M full-case receipts are separate. Every actual Worker freshly constructs and validates its own date's full model/domain before its first Native call; failed proof produces a terminal failure and no Native call for that date.

`TRAFFIC_AXIS_COMPATIBILITY_AUDIT.json` checks all 31 original days and both arms' byte-preserving input copies. The format error was confusing logical forecast-bundle SHA with NPZ file-container SHA. Original 288 five-minute forecast samples map to the 96 route departure slots using the existing `departure * 3` rule. SafeETA, 600-second connection delay, ceiling-to-slots and traction energy are unchanged. No interpolation, missing-route creation, travel-time change or constraint relaxation is used.

`B1_TO_B2_TRANSITION_VERIFICATION.json` separates Native=0 transition tests from the actual transition. The Coordinator automatically appends B2 Worker identity, input SHA, start time and first heartbeat when B2 May01 starts. `B2_THREE_WORKER_PARALLEL_VERIFICATION.json` records three-slot allocation, failure isolation, restart adoption, date/output/ledger isolation and actual parallel observations separately. Actual status remains `NOT_YET_OBSERVED` until those events occur. A separate three-process Native=0 audit verifies simultaneous Gurobi environment/full-model admission and resource observations; it does not claim three Native optimization calls have already occurred.

## Windows ownership and monitoring

The ordinary current-user tasks use `InteractiveToken`, `LeastPrivilege`, no credentials or security-policy changes, no execution timeout, and no healthy-process hard termination. The Native=0 process-lifetime probe records a Task Scheduler service-owned launcher exiting while its child continues emitting heartbeats. Process ancestry and job kill flags are evidence; `Start-Process` alone is not used as proof. Logoff persistence is `LOGOFF_PERSISTENCE_NOT_PROVEN`. Coordinator/Monitor logon triggers support checkpoint resume after login; a one-minute Watchdog checks process identity without interrupting a healthy Worker.

Own task prefix: `MobileESS_V42_B1B2_P1_20261009_Implementation01_`. Existing study tasks, results, ledgers and monitor port 8791 are preserved.

New monitor: <http://127.0.0.1:8793/>. The HTML and status API are tested for current arm/date, both 31-day tables, certified UB/LB/gap, wall/native budgets, CPU/RAM/PID, heartbeat, Planning/Fresh AC and automatic transition state. Browser visual verification is separately `NOT_TESTED`: the browser tool's permission verification failed; its restriction was not bypassed.

## Startup and resume

Only a frozen manifest with all ten new preflight gates, including `PARALLEL_B2`, complete source SHA coverage and all 62 dated input trees can authorize Native. Live checkpoint/results are written under the runtime folder and are not committed as changing Git artifacts.

The registered tasks launch `pythonw.exe -B -X utf8 -m v42_may_campaign.host <coordinator|monitor|watchdog> <runtime-root>`. Running the owned Coordinator task resumes the checkpoint. It never reruns a terminal arm/date. The monitor is read-only and the browser can close without affecting calculation. The Coordinator performs the B1→B2 transition itself and requires neither Codex nor an AI automation.

Final startup evidence, manifest, Windows task status and Korean handoff remain in the runtime root. Repeated S4U registration and system power-policy changes are not part of this implementation.
