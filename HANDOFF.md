# Mobile ESS current handoff

## Stage-1 status

R25T remains the authoritative offline continuation. It keeps the five-minute
H54 model, h0-only causal commit, four-thread policy, unchanged AC-aware QCP,
Fresh OpenDSS gate, and globally certified 3% modeled-objective rule.

Issue 153 has now completed and committed. The expected WSL preflight after the
R25V science refresh is:

```text
PASS_R25T_PREFLIGHT verified=41/54 resume_issue=154 remaining=13
```

Issues 113 through 153 are preserved. No
R25T driver or solver process was running at the time of this handoff.

## Issue 151 and 152 diagnosis

Both are hard-tail cases, not a single anomaly:

| Issue | Root CG | Restricted primal | Compact exact | Compact nodes | Final global gap |
|---|---:|---:|---:|---:|---:|
| 151 | 126.6 s | 121.7 s | 3,281.8 s | 14,708 | 2.9947% |
| 152 | 84.0 s | 119.7 s | 3,253.8 s | 12,494 | 2.9994% |
| 153 | 241.6 s | 116.5 s | 1,612.0 s | 3,957 | 2.9031% |

Fixed-integer AC-QCP polish took under two seconds. The dominant cost is the
original compact mixed-integer tree raising a valid global bound, not AC power
flow. Replacing AC with sensitivity OPF would therefore not solve this Stage-1
bottleneck.

## Exact-safe acceleration in the current source

The R25T working master now starts with multiple exact feasible paths ranked by
the previous-plan hint and raw route objective. A feasible restricted-master
solution is transferred to the untouched compact authority as integer VarHints
as well as a MIP start. These changes affect search guidance only:

- no feasible path is removed;
- no physical row, objective, AC QCP, or causal rule is changed;
- restricted-master `ObjBound` remains diagnostic only;
- the global lower bound remains
  `max(exact priced-root LB, original compact MIQCP ObjBound)`.

New audits report the final compact/polished gap at the top level. Early R25T
files for issues 151/152 contain the correct final value in the nested compact
phase but a stale pre-compact top-level convenience value; resume validation
now reads that immutable nested authority rather than recomputing the issues.

R25V adds three exact-safe runtime reductions for issue 154 onward:

- the prior causal plan is shifted into a solver-checked partial native MIP
  start, while the same-issue restricted-master solution remains a second start;
- exact root pricing batch is 32 instead of 16, reducing expensive QCP/dual
  synchronization rounds without changing pricing closure;
- restricted primal waits 30/60/300 seconds (minimum/stall/maximum) instead of
  60/120/600, and primal path enrichment is capped at 64 instead of 96.

These changes have passed unit/static and licensed-Gurobi multi-start smoke
tests, but their issue-154 wall-time improvement is not yet runtime evidence.

## R26 operational design

R26 avoids running the full H54 discrete solve at every five-minute boundary:

1. Every five minutes: shift the valid route/work plan, solve conditioned
   P/Q/SOC AC-aware dispatch, run Fresh OpenDSS, then commit h0.
2. Local event: free only affected MESS/jobs over the near horizon; keep all
   unrelated decisions fixed.
3. Full asynchronous replan: only for configured global hard events, economic
   opportunity, local-repair escalation, or maximum refresh.
4. Full online horizon: 12 five-minute stages plus 14 fifteen-minute stages,
   reducing 54 route/work integer stages to 26.
5. Generalized-Benders cuts may be reused only with a matching structural
   signature and authoritative QCP provenance.

The local/full orchestration, opportunity-gap authority gate, multiresolution
grid, and Benders cut cache are implemented. Production Gurobi
master/subproblem integration is still a separate future implementation gate;
the code does not claim that the cache alone accelerates the current R25T run.
AC remains in the fast layer. Sensitivity OPF is deferred unless the conditioned
fast dispatch itself later violates the 300-second maximum deadline.

## Validation completed

- Windows unit/integration suite: 33 tests passed, one WSL-only lock test skipped.
- WSL R25T global-bound proof: PASS.
- WSL Gurobi compact-authority smoke: PASS.
- WSL full `science/release_self_test.py`: PASS.
- WSL native two-start Gurobi smoke: PASS.

## Run command

From the repository in WSL:

```bash
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25t_stage1_resume_latest.py
```

The 54/54 Stage-1 run is an offline one-time validation sequence, not a solve
that the eventual R26 controller performs 54 times every operating day.

Do not create a PR until the user explicitly requests it.
