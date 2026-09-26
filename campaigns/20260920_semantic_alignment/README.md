# IEEE123 / IEEE8500 campaign repair and semantic alignment

## Scope and status

This is a reviewable snapshot of campaign source and existing verification evidence, not a completed production release. Live campaign directories are untouched. The main branch contains only repository metadata, so these adapters are added as a self-contained review archive rather than replacing an existing implementation. External historical source modules, frozen inputs, coefficient arrays and solver installations are required to execute these scripts; this is not a standalone installation.

- IEEE123: all 31 May dates; three concurrent days, four solver threads each; both first- and second-round B3 Actual.
- IEEE8500: May 1; BG 0.45, AIDC 2.10, MESS 2.00, PV 0.50; original feeder, mappings and hard limits retained.
- Identical Actual controller copies: frozen physical P/SOC execution and event-triggered Q-only repair. Q search is skipped when the frozen DA P/Q realized state is feasible and remains within the pre-frozen DA-exact deviation thresholds.
- Runtime directories, caches, solvers, state and outputs remain independent.

## Changes

- Retry transient Windows JSON replacement locks; unique temporary names and exclusive supervisor lock.
- B1-first IEEE8500 scheduling, then B2 and full coordination; preserve the authorized 14,400-second AIDC search.
- Short, identity-checked candidate cache paths avoid Windows MAX_PATH failures.
- Single-pass coefficient loading and cached immutable anchored polygon constants preserve numerical results.
- Actual native evaluations use accepted-prefix replay for Q-only trials. P correction and P rescheduling are forbidden.
- Event B thresholds are frozen before result inspection: line loading 0.02 pu, Vmin 0.005 pu and Vmax 0.005 pu. Event A is any exact AC hard-limit failure.
- Performance events accept only exact-feasible candidates that reduce both exact line loading and normalized DA-state deviation, choosing the smallest tested Q change. AC failures prioritize feasibility and electrical-deviation recovery.
- Monitors distinguish preparation from timed search and display accepted Actual maximum line loading, with partial and final results distinguished.

## Verification and limits

SOURCE_MANIFEST.json records byte sizes, SHA256 and local provenance for every captured file. Evidence files are historical verification snapshots, not continuously updated status.

- Both Actual controller copies are byte-identical.
- Python source syntax parsed successfully during PR preparation.
- Lightweight controller regression checks no-event DA-Q preservation, Event B minimal-Q repair, Event A feasibility repair, frozen P and zero future-Actual exposure.
- Recorded 96-slot coefficient evaluation: exact dictionary equality, 192 to 96 loads, 59.07 to 46.93 seconds.
- Recorded anchored-constant benchmark: bitwise equality and writable-copy isolation, 7.56x speedup for this computation only; no claim of full B2 speedup.
- Recorded independent native 96-slot forecast replay with rejected P/Q trials: zero recorded numerical error.
- Recorded B0 physical-scale audit: PASS. Old Actual results are not promoted to the new controller result set.

The IEEE8500 May-1 B2 preflight was stopped by user instruction after 9/96 slots. Its stopped progress is evidence only: all completed slots passed AC, one material-deviation event caused one Q intervention, and no controller SHA was promoted to a final production freeze. IEEE123 was not resumed. Full B2 preflight, independent 96-slot verification, controller freeze, IEEE123 single-case preflights and the monthly campaign remain production gates. Do not run copied launchers without restoring their frozen dependencies and independent writable namespaces. Absolute local paths in source/evidence are provenance and existing deployment bindings, not portable defaults.

## PowerShell monitor follow-up

The upper summary now displays only overall completion percentage/count and FAIL presence. Per-policy Actual line-loading results remain in the lower date-detail table. The monitor upgrade runs after template generation so regeneration preserves this layout. This update changes display code only. Python and PowerShell syntax checks passed; source hashes were refreshed.
