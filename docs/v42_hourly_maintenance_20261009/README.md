# V42 May B1/B2 hourly maintenance

The Windows Coordinator owns the live campaign. Codex diagnoses it once per hour and prepares evidence-backed repairs when needed. Healthy Workers, the frozen algorithm, their budgets, results and ledgers are preserved.

Campaign: `D:\MobileESS_v42\runtime\v42_may_campaign\candidate_20261009_implementation01`.
Maintenance storage: `D:\MobileESS_v42\runtime\v42_may_campaign\hourly_maintenance`.
Branch: `v42`; existing PR: #189. Read the preserved full user request in `USER_REQUEST.txt` before every scheduled run.

## First action and whole-turn lock

Use Python 3.11 from the existing campaign manifest. Run all commands with working directory `D:\MobileESS_v42`, `-B`, and UTF-8. Verify the repository path and branch before any mutation.

```powershell
python -B -X utf8 -m v42_may_maintenance.session begin --storage D:\MobileESS_v42\runtime\v42_may_campaign\hourly_maintenance
```

Save the returned token. The Windows byte lock is held by a windowless guardian process for the entire Codex turn, including diagnosis and isolated code repair. Save and verify its PID, creation time, command and owner thread. Do not impose a time expiry on a still-running maintenance turn.

`SKIP_PREVIOUS_MAINTENANCE_ACTIVE` means skip the overlapping run. An abandoned owner may be released only after `mcp__codex_app__read_thread` proves that exact owner thread is idle, completed or archived. Save the real tool response and its status in an evidence JSON with `owner_thread_id`, `owner_status`, `source: mcp__codex_app__read_thread`, and `response`, then pass `--owner-end-evidence` to `session end` for the old token. Unknown or running status prohibits release. Never substitute a guessed status. Dead guardians release the OS lock naturally; every mutation still requires a valid current session token.

```powershell
python -B -X utf8 -m v42_may_maintenance.check --campaign D:\MobileESS_v42\runtime\v42_may_campaign\candidate_20261009_implementation01 --storage D:\MobileESS_v42\runtime\v42_may_campaign\hourly_maintenance --session-token TOKEN --recover-dead-hosts
```

Check reads the original checkpoint, exact process identities, changing heartbeats, source/input/gate SHA, native ledger, original task state, Scheduler ancestry and HTTP monitor. Dispatch `request.started_UTC` is the Wall origin, including model construction and certification; old progress samples are not the elapsed clock. Completed Native Runtime is explicitly distinguished from an in-flight solve. Low CPU, unchanged Gap or a long model build alone never trigger restart.

The checker starts only a dead Coordinator or monitor with the already verified registration and manifest. It reuses original checkpoint recovery validation and never starts a Worker directly. Additional identity/integrity failures block this narrow recovery until diagnosed. New heartbeat evidence is required before reporting a successful restart. Healthy hosts receive no task action. A terminal date is never retried or given a reset budget.

## Diagnosis, repair and version promotion

Read `MAINTENANCE_STATE.json`, prior evidence and new log deltas before further analysis. Infrastructure failures, algorithm bottlenecks and scientific defects are different categories. Preserve the earliest failure and raw logs. TIME_LIMIT is an outcome: validate incumbent integer/physics evidence and independent Global LB/Gap, retain the receipt, let the Coordinator continue, and investigate repeated bottlenecks when justified.

Terminal failure triage remains OPEN across checks until independently classified. Save a JSON with `root_cause`, `original_results_preserved: true`, and `source_evidence` containing actual file paths and SHA256 values, then resolve that issue with:

```powershell
python -B -X utf8 -m v42_may_maintenance.resolution --storage D:\MobileESS_v42\runtime\v42_may_campaign\hourly_maintenance --session-token TOKEN --issue-id ISSUE --evidence D:\ABSOLUTE_EVIDENCE.json
```

Validate the session before any repair, commit, recovery or promotion. Prepare minimal fixes in an isolated D drive worktree, reuse existing implementations, and run Native=0 regression and original model/matrix/physics/certificate equivalence before any finite separate Native validation. Record frozen-versus-candidate performance, versions, attempt identity and budgets. Commit only verified changes; update v42 and PR189 without force push. Unrelated shared workspace changes remain untouched.

The running manifest freezes 974 source files. Do not edit those files or add modules to `v42_may_campaign` while the campaign uses that manifest. The current Coordinator has no live version selector. An algorithm/policy candidate must stay in `pending_releases` until a separately tested handoff/version selection mechanism can adopt it at a proven safe dispatch boundary. Never repin a manifest or modify active callbacks/parameters to work around that boundary. Every Worker retains its original selected version through termination. Scientific changes require separate versioning and user review; they cannot be promoted as equivalent experiments.

No MemLimit, SoftMemLimit, Python/OS RAM caps, CPU caps, priority reduction, Solver sleep, new Greedy/Random/Search heuristic, arbitrary rescue incumbent, SOC discretization, Top-k routes, fractional rounding, unsupported constraint removal, bound upgrading, data manipulation, objective/QoS/physical relaxation or future leakage. Resource measurements are informational. Existing M-stage Adaptive Role-Exchange LNS is reused, but a restricted-neighborhood ObjBound is never an original Global LB.

## Heuristics audit

Frozen A-stage `Heuristics=0.05` enables Gurobi built-in MIP heuristics. It conflicts with a policy requiring zero built-in heuristics. This maintenance adds no new search heuristic and does not silently describe the frozen policy as heuristic-free. `HEURISTICS_POLICY_COMPATIBILITY_AUDIT.json` preserves the configured policy SHA, this conflict, and separate candidate validation status. Any future policy change requires its own version, regression/equivalence and finite performance validation, then a safe dispatch boundary. The current B1 May01 Worker is explicitly protected from interruption and parameter changes. M-stage actual parameter evidence must be audited when B2 Native begins; it is not inferred as already observed.

## Campaign and monitor

B1 runs 31 days sequentially with one Worker, AIDC ON/MESS OFF, P1 Gap 0.5%. After all 31 B1 dates are terminal, including TIME_LIMIT/FAIL, the OS Coordinator automatically dispatches B2 May01/02/03 and keeps at most three distinct B2 dates active. B2 is AIDC OFF/MESS ON with original-input independent fixed AIDC and P1 Gap 3%. Threads=1, Wall=5400 and cumulative Native=5400 per date, P2=0. A finished slot automatically receives the next pending date. Input/output/log/cache/OpenDSS/ledger identity stays date-specific. Never wait for Codex to perform this transition. Observe the original transition receipt; keep Native=0 PASS distinct from actual transition NOT_YET_OBSERVED.

Original monitor: `http://127.0.0.1:8793/`. The separate read-only maintenance extension at `http://127.0.0.1:8794/` forwards the campaign view, retains three B2 cards, derives live Wall from dispatch, and displays the last Codex check and recovery state. It runs in its own ordinary-user Scheduler task; no existing task or frozen monitor source is overwritten. HTTP/API verification is recorded separately from visual browser verification.

The required ten maintenance artifacts persist after every check, plus heuristic/session/automation evidence. `SOURCE_SHA_AUDIT.json` checks frozen bytes independently of current Git HEAD; `ALGORITHM_VERSION_LEDGER.csv` reports the frozen algorithm HEAD and dated input/manifest identity. Guard communication and monitoring intervals do not delay the Solver.

## Completion and actual scheduling

The local Codex desktop app must remain running, the machine awake and the D drive repository accessible for scheduled maintenance. Windows Coordinator runs independently of Codex. InteractiveToken execution does not prove logoff persistence: `LOGOFF_PERSISTENCE_NOT_PROVEN` remains explicit.

Create or update only the matching Codex automation named `V42 May B1-B2 Hourly Recovery`, every hour, as a standalone local recurring task. Inspect existing automation TOML and tool view to avoid duplicates, preserve settings on update, and record actual ACTIVE status and authoritative next-run UTC/KST. Distinguish an end-to-end manual first test from a scheduled execution: never claim the latter before a real run receipt. Saved project metadata and the absolute D repository execution scope are reported separately if D is unavailable as a saved Codex project.

Pause that automation only when all 62 dates are terminal and there are no unresolved triage/repair/promotion items. Preserve full automation fields on the update. Release the guardian in a finally step after all work and before ending the Codex turn:

```powershell
python -B -X utf8 -m v42_may_maintenance.session end --storage D:\MobileESS_v42\runtime\v42_may_campaign\hourly_maintenance --token TOKEN
```

Verify `ACTIVE_SESSION.json` reached RELEASED. No campaign process is terminated by this action.
