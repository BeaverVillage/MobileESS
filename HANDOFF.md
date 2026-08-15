# Mobile ESS current handoff

## Stage-1 status

R25T remains the authoritative offline continuation. It keeps the five-minute
H54 model, h0-only causal commit, four-thread policy, unchanged AC-aware QCP,
Fresh OpenDSS gate, and globally certified 3% modeled-objective rule.

Stage-1 is complete. Issues 113 through 166 form one verified causal chain and
the final runtime reports `PASS_STAGE1_FINAL_FREEZE`, authoritative 54/54,
all global gaps at or below 3%, all first-step transitions closed, and all Fresh
Exact OpenDSS gates passed. No R25T driver or solver process was running at the
time of this handoff.

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

R25W repairs a post-solve thread audit exposed at issue 157. The issue itself
passed the global certificate at `2.999394%`, but Gurobi used one worker after
the root start closed the solve and the wrapper incorrectly required the last
message to equal four. `Threads=4` is now audited as a cap: the parameter must
remain four and every observed count must lie in `[1,4]`. KKT calls matched CG
iterations plus only zero/one numerical retry. A measured batch-64 trial was
rejected because issue 157 regressed from 17 iterations/187.5 seconds to 24
iterations/324.5 seconds; the production exact batch remains 32.

R25X responds to the issue-164 near-final failure and the measured CG/KKT tail.
Issue 164 reached a native global gap of `2.9963%`, then the strict fixed-integer
continuous QCP corrected the objective from `-866.7846857454` to
`-866.7845933850`. The old wrapper incorrectly failed because the stricter,
more feasible result was about `9.24e-5` worse. The polish now accepts either
objective direction only when its strict feasibility/bound gates pass and the
polished incumbent still has the unchanged global 3% certificate.

The same archive showed that issue 163 used 23 CG iterations but 45 KKT dual
solves, while issue 164 used 27 CG iterations but 69 KKT dual solves. The extra
22/42 solves were strict numerical retries after an OPTIMAL snapshot was already
inside the conservative RC envelope. Production now accepts that bounded
snapshot immediately and subtracts its measured error from the certified lower
bound exactly as before. The base pricing batch remains 32. A batch of 64 is
used only for saturated blocks when at most two MESS blocks remain active in the
late CG tail; every added path must have negative reduced cost under the true
current dual, and exact pricing closure is unchanged.

The R25X rerun produced direct wall-time evidence. Issue 164 fell from 27 CG
rounds / 1,153.0 CG seconds to 23 rounds / 366.6 seconds and committed at
2.9431%. Issue 165 committed at 2.9961%; its sparse tail added 96 targeted
columns. Both runs needed only one strict dual retry. The continuation is now
53/54 at that checkpoint; R25Y completed the final issue below.

Issue 166 then exposed a separate numerical-state carryover: root CG iteration
17 inherited an extreme prior recovery profile (`BarQCPConvTol=1e-11`,
`BarHomogeneous=1`, `NumericFocus=3`) and Gurobi returned SUBOPTIMAL even though
the preceding convex RMPs were optimal. R25Y restores the reviewed primary
barrier profile at the start of every newly enlarged RMP. Only NUMERIC or
SUBOPTIMAL statuses enter a cleared-state numerical recovery portfolio, and no
RMP is used unless the final status is OPTIMAL. Scientific rows, objective,
pricing closure, AC QCP, and certificate authority are unchanged.

The final R25Y issue-166 run passed without an RMP optimality recovery retry:
23 exact CG iterations in 240.8 seconds, 32 sparse-tail columns, priced-root
closure, strict polish PASS, and global certified gap 2.98751%. Compact exact
B&B remained the dominant phase at 1,657.0 seconds; total decomposition time was
1,997.0 seconds. The final incumbent/lower bound were `-816.8581803795` and
`-841.2618981842`. This supplies positive runtime evidence for the per-iteration
primary-profile reset while preserving every scientific authority.

The final external result archive is
`ConversationA_R25T_STAGE1_RUNTIME_RESULT_20260815T021614.tar.gz`, SHA-256
`4bedaab45a4270b4c4bdc5d6f744c0a4060a7f6b05cfac82db037c44453964fb`.

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

- Windows unit/integration suite: 37 passed, one WSL-only lock test skipped.
- WSL unit/integration suite: 48 passed (including current period-selection tests).
- WSL R25T global-bound proof: PASS.
- WSL Gurobi compact-authority smoke: PASS.
- WSL full `science/release_self_test.py`: PASS.
- WSL native two-start Gurobi smoke: PASS.
- Actual runtime: `PASS_STAGE1_FINAL_FREEZE`, authoritative `54/54`.
- Every issue: globally certified gap <= 3%.
- Final issue 166: transition PASS and Fresh Exact OpenDSS hard-constraint PASS.

## Run command

From the repository in WSL:

```bash
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25t_stage1_resume_latest.py
```

The 54/54 Stage-1 run is a completed offline one-time validation sequence, not a
solve that the eventual R26 controller performs 54 times every operating day.

## Annual evaluation sampling

The production evaluation now scores one deterministic contiguous seven-day
block per calendar month: 2,016 five-minute issues/month and 24,192 scored
issues/year. Every monthly episode has 48 hours of unscored causal burn-in.
Four monthly processes with four threads each execute the 12 months in three
waves. R26 and operational baselines run all seven scored days; R25T exact is a
54-issue oracle window inside each selected week and is never imputed over the
remaining issues. The completed Stage-1 54/54 validates the exact
causal/certificate pipeline required before those oracle windows are used.
