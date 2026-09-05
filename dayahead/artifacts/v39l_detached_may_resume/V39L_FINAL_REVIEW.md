# V39L final review

V39L fixes the Codex session-lifetime coupling and stale-monitor defects without changing production science. A Task Scheduler self-test completed after its initiating PowerShell shell exited, and the production resume uses the same detached mechanism.

May01–12 remain exact reusable PASS results. Their 24 result/certificate files are protected by SHA-256, size, and nanosecond mtime. May13–16 remain incomplete and are not promoted to PASS; only case checkpoints that pass the existing exact runner fingerprint and file-hash validator are reused.

| Day | Resume classification | Last valid unit | Reusable checkpoints |
|---|---|---:|---|
| 2025-05-13 | INCOMPLETE_NONAUTHORITATIVE | 4 | B0, B1 |
| 2025-05-14 | INCOMPLETE_NONAUTHORITATIVE | 4 | B0, B1 |
| 2025-05-15 | INCOMPLETE_NONAUTHORITATIVE | 4 | B0, B1 |
| 2025-05-16 | INCOMPLETE_NONAUTHORITATIVE | 4 | B0, B1 |

The resume is bound to V39K: May23/24/25/26 use migration counts 4/2/8/15, May17 retains its accepted authority, and total migration accounting remains 105 across 12 days. Runtime remains four date workers with four Gurobi threads per model.

Post-launch acceptance: **PASS** with 7 advancing heartbeat observations. The Task Scheduler registration remains while the campaign runs.

No commit, push, or PR was created.

```text
ROOT_CAUSE = CODEX_SESSION_LIFETIME_COUPLING_DEFECT
SCIENCE_FAILURE = NO
GUROBI_FAILURE = NO
OOM_FAILURE = NO
DETACHED_LAUNCHER_IMPLEMENTED = YES
DETACHED_CHILD_SURVIVES_PARENT_EXIT = YES
MONITOR_PID_LIVENESS_CHECK = PASS
MONITOR_HEARTBEAT_STALE_CHECK = PASS
STALE_JSON_CAN_SHOW_RUNNING = NO
MAY01_12_REUSED = YES
MAY01_12_RERUN = 0
MAY13_STATUS = INCOMPLETE_NONAUTHORITATIVE
MAY14_STATUS = INCOMPLETE_NONAUTHORITATIVE
MAY15_STATUS = INCOMPLETE_NONAUTHORITATIVE
MAY16_STATUS = INCOMPLETE_NONAUTHORITATIVE
ORCHESTRATOR_RESTART_COUNT_FOR_RESUME = 1
GLOBAL_MONTH_RERUN = NO
MAX_PARALLEL_DAY_WORKERS = 4
GUROBI_THREADS_PER_MODEL = 4
CURRENT_PRODUCTION_AUTHORITY = V39K
MAY_CAMPAIGN_RESUMED = YES
FAILED_DATES = 0
PRODUCTION_SCIENCE_CHANGED = NO
DA_AUTHORITY_CHANGED = NO
push = NO
PR = NO
```
