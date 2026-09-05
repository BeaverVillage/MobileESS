# V39H production refreeze and May campaign resume

Immediate close-out: **PASS**. This is a campaign-resume certificate, not a claim that the entire May campaign has completed.

```text
PRODUCTION_REFREEZE_COMPLETE = YES
SELECTIVE_PREFLIGHT_COMPLETE = YES
READINESS = 31/31
NOT_READY = 0
MISSING = 0
MAY01_05_REUSE = YES
MAY01_05_RESULTS_TOUCHED = NO
MAY_CAMPAIGN_RESUMED = YES
MAX_PARALLEL_DAY_WORKERS = 4
GUROBI_THREADS_PER_MODEL = 4
push = NO
PR = NO
```

## V39I disposition

```text
V39I_DIAGNOSTIC_COMPLETE = NO
V39I_STOP_REASON = DEFERRED_NONBLOCKING_SERVICE_DELAY_DIAGNOSTIC
V39I_PRODUCTION_BLOCKER = NO
PRODUCTION_SCIENCE_CHANGED = NO
```

The last flag describes the preserved V39I stop-time audit, before the separately authorized production refreeze. Both threshold workers were safely interrupted. May25 T=196 and May26 T=144 remain **UNKNOWN**, not feasible, infeasible, or optimal. Logs, bounds, partial certificates, and saved witnesses were preserved.

May25's V39H witness has maximum added delay **5745 min**; May26's has **3840 min**. Neither is certified as the minimum possible maximum delay. No service-acceptability threshold or new SLA/deadline was introduced.

## Production authority and minimum recomputation

The accepted hierarchy is base causal RSP, planning-grid check, then V39H standby-only primary-minimum-intervention repair when needed. A passing temporal repair has zero RUNNING migration. An infeasible repair retains the original base RSP and its existing exact minimum-migration witness; no partially repaired infeasible schedule enters migration.

Only May17, May23, May24, May25, and May26 changed, and only their B1/B3 DA authorities: **10 changed day-cases; 114 byte-identical authorities reused**. All B0/B2 authorities were reused. Primary temporal optimality is the only required temporal optimization claim; secondary/tertiary global optimality is not asserted.

| Changed date | Saved primary optimum, GPU-slots | Selective physical/contract preflight | RUNNING migrations |
| --- | ---: | --- | ---: |
| May17 | 2,216 | PASS | 0 |
| May23 | 8 | PASS | 0 |
| May24 | 108 | PASS | 0 |
| May25 | 29,568 | PASS | 0 |
| May26 | 13,086 | PASS | 0 |

The other eight affected dates retain exact migration counts: May06=12, May08=2, May10=10, May11=7, May18=6, May19=22, May21=2, May22=15. This is **8 migration days / 76 migrations**, versus the earlier 12 / 105 baseline. Reduction: 29 migrations. These are frozen DA counts, not completed Actual campaign measurements.

No primary optimization or migration MILP was rerun. There was no expensive 31-day preflight/optimization rerun. The five changed dates used independent temporal materialization and physical/contract verification; final 31-day readiness used SHA, authority, loader, certificate, and provenance assembly only.

The voltage, capacity, safe-runtime, eligibility, gang, Rack, WAN/checkpoint/restart, and migration semantics remain frozen. RW-completion noninferiority and the accepted planning-grid checks pass. The grid claim is scoped to the accepted operating-day horizon; it does not invent off-day physical certification. Actual/Fresh result content was not used to construct the changed DA decisions. Reading completed May01–05 results occurred afterward only to verify reuse.

## Preservation and runtime confirmation

May01–05's 20 case checkpoints passed exact execution/DA/Actual/Fresh/certificate equivalence. After campaign resume, **470 protected files** retained their SHA, size, and modification time, and **138 required V39H artifacts** retained their SHA. Old diagnostic-era result labels were not rewritten; a separate sealed equivalence authority authorizes their reuse.

Production regression tests: **11/11 PASS**, with no optimization calls.

At the recorded resume snapshot, the campaign was AUTHORITATIVE, May01–05 were reused, May06–09 were running, and no failed dates were reported. The orchestrator PID was 30196. A visible progress-monitor window was started (PID 38000). Each active day logged four threads per model and at most one concurrent solver per day, giving a maximum of sixteen concurrent solver threads across four day workers. Historical Threads=1 caches remain reusable under the approved runtime-only equivalence rule.

Actual uses fixed replay of the frozen DA authority: temporal, AIDC, migration, and WAN reoptimization calls are all zero. MESS execution and Fresh validation continue through the accepted campaign workflow. Subsequent campaign progress is live; this report records resume, not month completion.

## Evidence

- `PRODUCTION_CLOSE_FINAL_STATUS.json`: timestamped resume snapshot, runtime/process checks, and evidence SHAs.
- `PRODUCTION_CHANGE_IMPACT_AUDIT.json`: all 124 day-case reuse/change decisions.
- `PRODUCTION_REFREEZE_AUTHORITY.json`: sealed production DA authority.
- `SELECTIVE_PREFLIGHT_SUMMARY.json` and `days/*/SELECTIVE_PREFLIGHT_CERTIFICATE.json`: five changed-date checks.
- `CHEAP_31_DAY_READINESS.json`: 31 READY, zero NOT_READY/MISSING, zero optimization calls.
- `MAY01_05_REUSE_EQUIVALENCE.json`: immutable result and checkpoint reuse proof.
- `MIGRATION_REUSE_EQUIVALENCE.json`: eight original-RSP exact migration witnesses, with preserved source provenance.
- `PRODUCTION_CLOSE_TEST_REPORT.json`: eleven passing regression tests.
- `before_refreeze/`: preserved prior DA and aggregate authorities.
- Live progress: repository `progress/V39E_OVERNIGHT_PROGRESS.json`; day logs: `logs/v39e_may_2025/`.

If a later implementation defect is found, use diagnosis, scoped repair, change-impact audit, and minimum safe selective rerun. Do not restart V39I, re-solve completed primary/migration proofs, or invalidate the full month absent a genuine common frozen-semantics change.
