# IEEE123 May certification, restart and monitoring handoff

Status: **DRAFT — historical conversation record; implementation sources missing**.

This records the IEEE123 work discussed on September 14, 2026, for the May 2025
campaign in `IEEE123_RESITED_PRODUCTION_20260913`. It is not the earlier campaign
export in PR #42 and does not incorporate September 20 QFIRST MINP work.

The original campaign directory was absent when packaging this PR on September
20. Targeted searches of the current workspace, the ChatGPT workspace tree,
the C/D runtime workspace trees, and available local Git history did not recover
the named operational sources. These searches do not establish permanent loss
or rule out unsearched backups. No historical implementation is reconstructed
or asserted to be present in this PR.

The evidence here is the retained task conversation and its displayed tool
results. Historical PASS statements below are **reported results**, not tests
rerun against recovered source. This PR adds documentation only. It cannot
serve as an executable release, a source-SHA attestation, or a full forensic
audit of every candidate. Recover and verify the files listed in
[SOURCE_RECOVERY.md](SOURCE_RECOVERY.md) before an implementation review.

## Contract and authorization sequence

- Keep the K200 -> K400 -> K800 -> FULL search, objective, candidate universe,
  electrical limits, and MESS initial stations STA01/STA12/STA08/STA06.
- Rho certificate agreement tolerance was changed to 1e-7 by a later explicit
  request; this is separate from physical acceptance tolerances.
- Original forensic work required reporting before restarting. A later user
  instruction explicitly authorized the May campaign and error recovery.
- Preserve incumbent identity and completed work across restart. Do not invent
  historical solution vectors or share candidate-specific electrical rows.
- Fresh restoration stops on PASS and has a maximum of 10 rounds. Genuine
  infeasibility or exhausted recovery is not grounds to relax scientific gates.
- User authorized checks every two hours and fixes/restart on implementation
  failure. No polling between scheduled checks except explicit user requests.

## Historical changes recorded in the conversation

| Area | Recorded behavior | Packaging limitation |
| --- | --- | --- |
| Numerical certification | Rho agreement tolerance 1e-7; historical gate reports no physical violation leakage. | Source and gate receipt not recovered. |
| Same-candidate reuse | Immutable certified-candidate cache and completion receipts; partial separation-state resume remained disabled. | Do not claim partial-state persistence was implemented. |
| Full MILP incumbent | Future full solution-vector snapshots and identities were reported retained. | Complete schema and no-solver reboot restoration cannot be reverified here. |
| B3 provenance | Bind source identity around runtime-cloned functions whose virtual filenames broke inspection. | No original bytecode/source comparison available in this PR. |
| Fresh restart | Preserve failure evidence, enter the original restoration handler, handle contained Windows paths and remaining domain-store consumption. | Reported successful one-round recoveries are historical, not a new solver run. |
| Archive finalization | Flush/fsync and close only output-owned event streams before sealing; recover already-completed B1 archive sealing without optimization. | Saved bytes and SHA identities require original receipts. |
| K-stage archives | Permit archive moves inside the exact bound candidate-search root, retain same-parent and naming checks, reject overwrite. | No cross-candidate row sharing is authorized. |
| Process restart | Supervisor launched independently; live workers adopted by PID, creation time and command identity. | Historical supervisor 30908 reported outside a Windows Job; not a current liveness claim. |
| Day transition | B0/B1/B2/B3 DA followed by B0/B1/B2/B3 Actual, then the next day on each date worker. | A 31-day/310-phase simulated transition check was reported; scientific execution was not simulated by that check. |
| Monitor | Read current Actual phase receipts and summary schema; show maximum line loading as percent; simplify details. | Old legacy receipt paths must not be assumed equivalent to the current summary schema. |

The historical forensic label was `FULL_RUNTIME_ROOT_CAUSE = MIXED`, with
`CERTIFICATION_STALL` and `RESTART_STATE_LOSS` reported as components. This is
not evidence that every candidate was feasible, nor a new exhaustive
candidate/retry classification. The original candidate census, row-by-row
separation history, and roughly 67-minute depth-2 decomposition are not
reproduced here because their underlying records are unavailable.

## Actual monitor numerical interpretation

The recorded May01–03 Actual voltage excursions were about 1e-11 to 1e-10 pu;
the corresponding line-current and transformer overload counts were zero.
The original summary used strict voltage comparisons and retained
`WITH_VIOLATIONS`. The monitor-only assessment was changed to the existing
squared-voltage condition:

```
0.95^2 - 1e-8 <= V^2 <= 1.05^2 + 1e-8
```

This is a tolerance on squared voltage, not a blanket +/-1e-8 pu band.
Recorded display checks required 96 converged slots, finite extrema/loadings,
available violation counts, and ordered nonnegative voltage extrema. Thermal
counts and loading >= 1 remained display failures. Original Actual summaries,
arrays and scientific decisions were not rewritten to make the display PASS.
Display PASS must not be used to overwrite the raw physical-outcome field.

The conversation reports 12 completed summaries passing the display check,
with real voltage/thermal violations, incomplete convergence and NaN inputs
rejected. A live frame showed May03 B2 at 57.54% and B3 at 57.96% maximum line
loading. These are historical observations, not current campaign results.

## Time reporting and known gaps

The requested final comparison is B0/B1/B2/B3 time by day and across 31 days,
excluding error wait/recovery and wasted duplicate execution, while including
successful pre-error work actually reused after restart. Fresh restoration and
Actual replay are separate from DA optimization. No final 31-day timing report
was produced in the retained conversation.

- Configured budgets such as 1,800 seconds are not measured execution times.
- Completed `OPTIMIZE` events record call duration and solver runtime; ongoing
  or uninstrumented calls are not represented by those completed-event sums.
- Certification timers may include optimize calls. Do not add overlapping
  nested timers as disjoint wall time.
- Depth elapsed time includes candidate enumeration, model construction,
  certification, solver work and other overhead. It is not pure solver time.
- A restored depth's tiny duration measures cache restoration, not its original
  optimization. May01/02/03/05 receipts showed this issue during the discussion.
- Only timestamp-supported I/O is measured I/O. Keep unmeasured residual wall
  time unresolved; do not estimate it into an apparently exact decomposition.
- Parallel date-worker elapsed intervals and summed solver work are different
  quantities. Any future aggregation must define its denominator and overlap
  handling and preserve the failed/reused-attempt attribution.

At the recorded September 14 11:58 snapshot, B2 depth elapsed totals were about
76m17s for May07 and 16m53s for May08. Completed instrumented solver calls summed
to 10m10s and 2m09s respectively. The discrepancy was explicitly unresolved;
these values must not become final optimization totals.

## Review boundary

This PR does not modify or restart a campaign, refresh an automation, rerun
Gurobi/OpenDSS, change search or physical gates, or publish raw simulation data.
It preserves the handoff and its limitations pending source recovery. Original
test counts, source hashes, candidate outcomes and final runtime totals must
be re-established from recovered artifacts before deployment or scientific use.
