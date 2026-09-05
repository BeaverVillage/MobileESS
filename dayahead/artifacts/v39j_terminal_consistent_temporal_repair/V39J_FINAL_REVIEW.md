# V39J final review

All three target days are certified terminal-safe temporal-repair infeasible.
Their original base-RSP migration fallback witnesses pass independent planning
verification. The certified candidate count is **101**, a reduction
of **4** from the original 105. Live authorities remain unchanged.

| Day | Old primary lower bound | Terminal upper bound | Repair | Fallback migrations | Vmax | Upper headroom |
|---|---:|---:|---|---:|---:|---:|
| 2025-05-24 | 108 | 2,516 | INFEASIBLE | 2 | 1.046348088348 | 0.003651911652 |
| 2025-05-25 | 29,568 | 8,384 | INFEASIBLE | 8 | 1.046649468702 | 0.003350531298 |
| 2025-05-26 | 13,086 | 3,376 | INFEASIBLE | 15 | 1.046509465466 | 0.003490534534 |

## Proofs and scope

The source baseline is the sealed accepted production snapshot, including
the 12 V39E module SHAs in the refreeze fingerprint and the unchanged V39H
decision-function seals referenced by production close. All 1099
accepted source files match. Unrelated copied monitor/runtime changes were
removed from the V39J worktree; the live tree was never edited.

J is the sum of per-job symmetric occupancy deviations over complete
reservation intervals: `sum_j 2*g_j*min(delay_j,d_j)`. It has no site cost,
no omitted constant, and uses integer GPU-slots. The audit independently
reconstructs all three old certified objective values from explicit occupancy.

May25/May26 use the required analytic U<L fast path: zero Gurobi models,
zero feasibility solves, zero primary reoptimizations. May24's U=2,516 is
inconclusive. Its full model with J=108 was assembled, then an exact integer
mandatory-capacity certificate resolved feasibility. Removing J=108 leaves
the same contradiction. This is a complete infeasibility proof without a
numerical Gurobi optimize call; no Gurobi infeasibility status is fabricated.
The two later dates also have independently checked capacity contradictions,
which corroborate but do not replace their required objective-bound proofs.

Case C UNASSIGNED state is retained in both model keys and outputs. Case B
PENDING boundary sites come solely from SHA-verified pre-refreeze same-day
RSP witnesses; RUNNING remains pinned to its original migration-OFF initial
site. Cross-boundary and post-H-only jobs are excluded from temporal eligibility.

The terminal audit CSVs describe **restored original RSP plus original
migration witnesses**, not successful temporal-repair schedules. All 917
reservations retain baseline timing and their existing site/unassigned state
relative to that fallback. Added post-H GPU-h and changed post-H profiles are
zero. Existing baseline migration counts are 2/8/15. Grid/Rack/capacity/C1/
inner-polygon, frozen runtime, GPU requests and RW checks pass. Grid evidence
covers issue slots [24,120) only. No Actual/Fresh/future observations were read.

The hierarchy remains base RSP → grid check → terminal-consistent standby
repair → original exact-minimum RUNNING migration if repair is infeasible.
This result does not invalidate temporal repair; May17/May23 remain intact.

## Validation and preservation

25 tests passed, including exhaustive compact/profile equivalence,
exhaustive toy upper bounds, cancellation rejection, UNASSIGNED and cohort
tests, a forbidden-Gurobi analytic-path test, and source/live preservation.
Actual V39J solver threads used = 0; parallel numerical day solves = 0.
The numerical-model setting is 1 thread if a future free-slot solve is needed.

Live orchestrator PID before/after: [30196] / [30196].
816 live source hashes and
170 sealed DA/May17/May23 authority
hashes matched. No live restart, source/DA update, HOLD release, push, or PR.
Integration remains a separate controlled task.

## Explicit answers

**Q1.** Yes. The per-job invariant is implemented with exact interval/site equivalence and exhaustive tests.

**Q2.** Yes. Baseline cross-boundary reservations and wholly post-H unassigned reservations retain their timing and state.

**Q3.** No. May24 cannot retain 108: even without the primary equality, mandatory terminal/initial jobs require 83 GPUs at AIDC05 (capacity 80) at issue slots 112–119.

**Q4.** No. May25 has the same-objective upper bound 8,384 < certified old lower bound 29,568; no terminal-safe repair exists.

**Q5.** No. May26 has the same-objective upper bound 3,376 < certified old lower bound 13,086; no terminal-safe repair exists.

**Q6.** None of May24/25/26. May17/May23 remain previously certified unchanged repair dates; they were not re-solved.

**Q7.** There are no passing target repair days. Each restored baseline fallback has zero repair-induced incremental post-midnight GPU-h.

**Q8.** The model preserves each job's baseline terminal timing and site state. All restored fallbacks match their original frozen fallback authority per job; no future physical AIDC is invented for UNASSIGNED reservations.

**Q9.** Yes for all three restored fallback candidates: independent planning-grid verification passes on [24,120). No target temporal-repair witness is claimed feasible and no post-H grid certification is claimed.

**Q10.** Yes for the original V39H-eligible population; all baseline completion times are retained and newly introduced violations across all jobs equal zero. Pre-existing noneligible lateness is separately recorded.

**Q11.** The certified candidate is 101 migrations = 105 − 4 from May23. May17 is not counted in the original 105.

**Q12.** May24, May25 and May26 use their original base RSP plus existing exact minimum migration witnesses: 2, 8 and 15. No migration MILP was re-run.

**Q13.** Yes. Live source and DA SHA seals match, the original orchestrator remains running, and all three HOLD gates remain closed. Worker rotations are natural campaign progress.

## Required final status

```text
V39J_DIAGNOSTIC_COMPLETE = YES
V39J_SOURCE_MATCHES_PRODUCTION_REFREEZE = YES
TERMINAL_INVARIANT_IMPLEMENTED = YES
TERMINAL_INVARIANT_PER_JOB = YES
FULL_POST_H_SITE_AUTHORITY_FOUND = NO
POST_H_UNASSIGNED_STATE_PRESERVED = YES
CROSS_BOUNDARY_BASE_SITE_PRESERVED = YES
PRIMARY_OBJECTIVE_IDENTITY_PASS = YES
MAY24_TERMINAL_INTERVENTION_UPPER_BOUND = 2516
MAY24_OLD_PRIMARY_LOWER_BOUND = 108
MAY24_TERMINAL_SAFE_REPAIR = FAIL
MAY24_PRIMARY_OPTIMUM = INFEASIBLE
MAY24_INCREMENTAL_POST_MIDNIGHT_GPU_H = 0
MAY24_SOLVER_CALLS = 0
MAY25_TERMINAL_INTERVENTION_UPPER_BOUND = 8384
MAY25_OLD_PRIMARY_LOWER_BOUND = 29568
MAY25_TERMINAL_SAFE_REPAIR = FAIL
MAY25_PRIMARY_OPTIMUM = INFEASIBLE
MAY25_INCREMENTAL_POST_MIDNIGHT_GPU_H = 0
MAY25_SOLVER_CALLS = 0
MAY25_ANALYTIC_INFEASIBILITY_PROVEN = YES
MAY26_TERMINAL_INTERVENTION_UPPER_BOUND = 3376
MAY26_OLD_PRIMARY_LOWER_BOUND = 13086
MAY26_TERMINAL_SAFE_REPAIR = FAIL
MAY26_PRIMARY_OPTIMUM = INFEASIBLE
MAY26_INCREMENTAL_POST_MIDNIGHT_GPU_H = 0
MAY26_SOLVER_CALLS = 0
MAY26_ANALYTIC_INFEASIBILITY_PROVEN = YES
POST_H_RESERVATION_PROFILE_CHANGED_JOBS = 0
POST_H_SITE_STATE_CHANGED_JOBS = 0
RW_COMPLETION_NONINFERIORITY_PASS = YES
NEW_RW_COMPLETION_VIOLATIONS = 0
FROZEN_SAFE_RUNTIME_PRESERVED = YES
GRID_HARD_CONSTRAINTS_PASS = YES
BASELINE_MIN_MIGRATIONS = 105
POST_V39J_MIN_MIGRATIONS = 101
MIGRATION_REDUCTION = 4
PRIMARY_OPTIMIZATION_RERUN_DAYS = []
MIGRATION_MILP_RERUN = 0
FULL_13DAY_RERUN = NO
FULL_31DAY_RERUN = NO
V39J_THREADS_PER_MODEL = 0
V39J_PARALLEL_DAY_SOLVES = 0
LIVE_CAMPAIGN_RESTARTED_BY_V39J = NO
LIVE_PRODUCTION_SOURCE_MODIFIED = NO
MAY24_26_HOLD_RELEASED = NO
push = NO
PR = NO
```
