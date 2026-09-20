# IEEE8500 May01 B0 fine-scale feasibility evidence

This snapshot records the completed **2025-05-01 Day-Ahead B0** search with the frozen reference AIDC workload/PCC injections ON, MESS OFF and fixed PV alpha 0.50. Only the uniform native background P/Q scale varied. It does not replace any production authority or the separate May21 plotting dataset.

| Result | Value |
|---|---:|
| Maximum tested feasible scale | 0.5775 |
| First tested infeasible scale | 0.578 |
| Final bracket width | 0.0005 |
| Recommended production scale | 0.574 |
| Recommended peak line loading | 0.9834260616754051 pu |
| Recommended Vmin | 0.9510182205993569 pu |
| Recommended Vmin margin over 0.95 | 0.001018220599356967 pu |

The maximum tested feasible point has Vmin 0.9500830383575262 pu. It is not automatically selected for production. The recommendation is the most stressed **tested** candidate satisfying Vmin >= 0.9505, a recommendation criterion separate from the unchanged hard lower bound of 0.95. Scale 0.576 remains hard-feasible at Vmin 0.950481192638906. No continuous mathematical optimum is claimed.

## Results

- [Full report](REPORT.md) and [nine-candidate table](csv/FINE_SCREEN_TABLE.csv).
- [All candidate daily-max maps](ALL_CANDIDATE_DAILY_MAX_HEATMAPS.png).
- Recommended 0.574: [daily-max map](scale_0.574/B0_DAILY_MAX_HEATMAP.png), [same critical-time map](scale_0.574/B0_CRITICAL_TIME_HEATMAP.png).
- Recommended CSVs: [daily maximum](csv/B0_0.574_DAILY_MAX_HEATMAP.csv), [critical time](csv/B0_0.574_CRITICAL_TIME_HEATMAP.csv), [summary](csv/B0_0.574_HEATMAP_SUMMARY.csv).

Every candidate has 96-slot extrema, control states, summary, input freeze and static/spatial audit. Eight candidates used independent fresh OpenDSS contexts (768 snapshots); the existing 0.580 control contributes 96 reused snapshots. All converged and settled. FAIL candidates have undervoltage only. No B1/B2/B3 optimization was run. PR packaging performs no scientific execution.

## Plotting contract

Original coordinates, whole-feeder/detail extents, YlOrRd and the 0–1 pu colorbar match the preceding actual-B0 0.58 figures. There is **no reflection or rotation**. Daily colors maximize over slots, terminals and local nodes; critical-time colors maximize over terminals/local nodes at a single system-wide critical slot.

Daily CSV: 3,703 physical-line rows, including five `DISABLED` lines with empty loading. Critical CSV: 12,312 monitored terminal/local-node rows plus five disabled placeholders. Group by `element_id` and take the maximum to plot one value per physical line. Loading is pu, not percent. Phase fields are raw OpenDSS **local node numbers**, not inferred primary A/B/C phases. Slot 75 starts at **18:45 AEST (+10:00)**; the corresponding forecast interval ends at 19:00.

## Portable validation

From the repository root, using Python 3.10+ and NumPy:

```sh
python -B tools/validate_ieee8500_b0_fine_scale.py
```

The validator checks all packaged SHA256 values, candidate slot metrics/control completion, input invariants, the search bracket/recommendation, unchanged CSV schemas, disabled-line semantics, original coordinates, every recommended CSV loading/witness against the included raw arrays, and recommendation summary metrics. It does not import OpenDSS, invoke an optimizer, or alter files.

## Reproduction scope and provenance

All 94 copied evidence files are byte-identical to their local originals. `PACKAGE_MANIFEST.json` uses portable relative paths; historical manifests retain original machine paths as provenance.

The **0.574 raw arrays are included**. Other candidates' approximately 19 MB raw arrays remain external; their hashes are in `SCREEN_TABLE.json`. Their 96-slot extrema/control evidence is included. Independent full-array revalidation for those eight candidates requires those external raw files. The validator explicitly reports this distinction.

`frozen_code/` preserves the original search, runner, rendering and verification sources. These are a historical snapshot, not a standalone simulator: rerunning scientific calculations requires the original frozen source workspace and its OpenDSS/input dependencies. Use the portable validator above to audit this PR without replay. Runtime dependencies, temporary caches, symlinks and unrelated campaigns are excluded.
