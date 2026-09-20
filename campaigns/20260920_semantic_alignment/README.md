# IEEE123 / IEEE8500 campaign repair and semantic alignment

## Scope and status

This is a reviewable snapshot of campaign source and existing verification evidence, not a completed production release. Live campaign directories are untouched. The main branch contains only repository metadata, so these adapters are added as a self-contained review archive rather than replacing an existing implementation. External historical source modules, frozen inputs, coefficient arrays and solver installations are required to execute these scripts; this is not a standalone installation.

- IEEE123: all 31 May dates; three concurrent days, four solver threads each; both first- and second-round B3 Actual.
- IEEE8500: May 1; BG 0.45, AIDC 2.10, MESS 2.00, PV 0.50; original feeder, mappings and hard limits retained.
- Identical Actual controller copies: Q-first, minimal P correction when Q is insufficient, causal energy recovery. B0/B1 keep MESS off.
- Runtime directories, caches, solvers, state and outputs remain independent.

## Changes

- Retry transient Windows JSON replacement locks; unique temporary names and exclusive supervisor lock.
- B1-first IEEE8500 scheduling, then B2 and full coordination; preserve the authorized 14,400-second AIDC search.
- Short, identity-checked candidate cache paths avoid Windows MAX_PATH failures.
- Single-pass coefficient loading and cached immutable anchored polygon constants preserve numerical results.
- Actual native evaluations use accepted-prefix replay for alternative P/Q trials. The experimental snapshot evaluator remains unused because its control-state equivalence failed.
- Monitors distinguish preparation from timed search and display accepted Actual maximum line loading, with partial and final results distinguished.

## Verification and limits

SOURCE_MANIFEST.json records byte sizes, SHA256 and local provenance for every captured file. Evidence files are historical verification snapshots, not continuously updated status.

- Both Actual controller copies are byte-identical.
- Python source syntax parsed successfully during PR preparation.
- Lightweight controller regression checks minimal charging curtailment, causal recovery and disconnected MESS behavior.
- Recorded 96-slot coefficient evaluation: exact dictionary equality, 192 to 96 loads, 59.07 to 46.93 seconds.
- Recorded anchored-constant benchmark: bitwise equality and writable-copy isolation, 7.56x speedup for this computation only; no claim of full B2 speedup.
- Recorded independent native 96-slot forecast replay with rejected P/Q trials: zero recorded numerical error.
- Recorded B0 physical-scale audit: PASS. Old Actual results are not promoted to the new controller result set.

Full new B2/M2 integration, final Fresh validation and IEEE8500 Actual completion remain production gates. This draft does not certify their completion or policy ordering. Do not run copied launchers without restoring their frozen dependencies and independent writable namespaces. Absolute local paths in source/evidence are provenance and existing deployment bindings, not portable defaults.
