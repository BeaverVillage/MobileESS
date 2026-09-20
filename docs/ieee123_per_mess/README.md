# IEEE123 per-MESS soft budgets and campaign recovery

This package preserves the IEEE123 work performed in the September 14, 2026 conversation: independent 15-minute MESS search budgets, four-day orchestration, a date-selectable PowerShell monitor, and recovery of restricted-candidate retention failures. It is stacked on the V41R4 final-results/provenance branch (#42).

The original `IEEE123_RESITED_PRODUCTION_20260913` directory was unavailable during PR preparation on September 20. The 17 authored Python/PowerShell files were recovered from 41 literal patch operations and one recorded string transformation. No recorded shell command was executed to reconstruct them. The complete private conversation is not included.

The recovered budget module SHA256 is `acd4009e12a104f42981fc8dfca900a3fd9cf05507df421c44e232ba168b2bb4`, exactly matching the digest in the September 14 runtime observations. Per-file reconstruction hashes, operation ordinals and timestamps appear in [SOURCE_RECOVERY.json](SOURCE_RECOVERY.json). This independent historical digest comparison applies to the budget module; the other files have reconstruction hashes, not a newly recovered production receipt attesting their bytes.

## Runtime behavior

- B2 and B3-M1 use separate 900-second soft budgets for MESS01 through MESS04. Enumeration, ranking, model building, solving and certification count toward the current depth. Parent and K transitions do not reset it. An already admitted atomic solver/certification operation can finish after expiry; no subsequent operation is admitted. Early search completion advances without waiting for 900 seconds.
- Frozen K200 → K400 → K800 → FULL fallback, beam width two, deterministic ordering, physical constraints, full-MILP TimeLimit 600, WorkLimit tiers 60/180/300 and rho agreement tolerance `1e-7` remain in force. At expiry, only independently validated children can enter retention; the existing certified neutral STAY remains the fallback.
- The separate namespace preserves B0 planning/Fresh and B1 May01–08 results. Missing B1 May09–31 and Actual phases are scheduled; B2/B3 decisions are new. B3 A1 and MF retain their separate existing budgets; the per-MESS limit is not a whole-policy deadline.
- The supervisor runs four day workers with four solver threads each. It can adopt existing final workers during a supervisor handover. The Windows entry point checks that it is outside a Windows job before starting the campaign. These host-specific startup scripts require their original environment and data.
- The PowerShell monitor reads live MESS status directly, shows subsequent A1/MF stages and restoration preparation, and supports date arrows, policy details, four worker selections, logs and the selected result folder. Closing the display does not stop computation.

## Failure and recovery semantics

May05 B3 MESS02 and May08 B2 MESS04 encountered restricted candidates whose original certificate passed battery, voltage, current and transformer kVA checks but did not certify the full-model transformer polygon. The additional retained-child validation rejected them. Initially that rejection aborted the whole search.

`RestrictedPolygonRejection` now prevents such a restricted result from entering the retained-child pool and records the rejected candidate. It does not relax a constraint or certify the candidate as feasible. The original full MILP may still use it as a seed and must enforce its own constraints. Other physical/grid validation errors still propagate. Neutral fallback and final full-fleet validation remain mandatory.

Technical recovery uses an explicit `TECHNICAL_RECOVERY.json` in the same search namespace. Completed depth envelopes must match their recorded file hashes, execution identity, parent states, retained states and budget contract. The interrupted depth debits time already consumed. This does not enable arbitrary old-campaign stage reuse or additional quality runs.

Recorded recovery points:

| Work item | Completed depths restored | Time already consumed in resumed depth |
|---|---|---:|
| May05 B3 | MESS01 | 50.701492 seconds in MESS02 |
| May08 B2 | MESS01–03 | 435.406398 seconds in MESS04 |
| May06 B3, last pre-fix worker | MESS01–03 | 163.641098 seconds in MESS04 |

May08 failed after the first fix because its existing process still held the old code in memory. The remaining May06 old worker was then paused between submissions; its in-flight candidate completed and committed before the process was replaced. May05/May07 continued. Updating source on disk alone must not be interpreted as updating a running process. The legacy live digest reads the file on disk, so it alone cannot attest loaded process code.

## Validation and limits

Run from the repository root:

```powershell
python -B tools/ieee123_per_mess_snapshot/verify_snapshot.py
```

This verifies the file inventory and hashes, parses all recovered Python files, compares the budget module with its historical digest, and exercises seven solver-free control/rejection scenarios. PowerShell syntax is checked separately with the PowerShell parser during PR preparation. [VALIDATION.json](VALIDATION.json) records these current checks.

[HISTORICAL_OBSERVATIONS.json](HISTORICAL_OBSERVATIONS.json) contains selected terminal observations from September 14, including the 11-test run, four-depth mocked integration, saved-candidate rejection checks, preserved budget evidence, and progression beyond both failure points. They are historical observations, not newly generated production receipts. Original large datasets, SQLite caches, electrical authorities, full manifests, solver outputs, and some runtime adapters are not available here. The archived production integration tests and diagnostic scripts therefore have not been rerun against the original environment for this PR.

The snapshot is review/provenance material, not a self-contained portable campaign release. Do not launch its historical preparation/recovery scripts against unrelated current production directories. No optimization, AC replay, ML training, or new scientific result was produced during PR preparation, and this package does not claim full-May completion.

## May07 results reported in the conversation

These are the saved September 14 comparison, not a replacement for later Actual studies.

| Policy | Planning P1 (%) | Fresh maximum line loading (%) | Actual maximum line loading (%) |
|---|---:|---:|---:|
| B0 | 69.133358 | 69.132364 | 65.869118 |
| B1 | 69.114254 | 69.112630 | 65.887967 |
| B2 | 60.045593 | 63.312290 | 58.954492 |
| B3 | 58.770244 | 61.676155 | 59.233396 |

All four Actual cases reported 96 converged slots and zero line-current overload counts. The raw B2/B3 summaries also recorded 4/10 voltage boundary counts, respectively, with extrema differing from 0.95/1.05 by less than `1e-10`; execution receipt PASS must not be conflated with a zero raw voltage-violation count. Actual B2 was lower than B3 by 0.278905 percentage points on this day.
