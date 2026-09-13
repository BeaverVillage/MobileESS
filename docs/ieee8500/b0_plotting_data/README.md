# IEEE8500 B0 critical-time plotting data

This sealed snapshot supplies the geometry and stored loading needed to plot the
accepted IEEE8500 B0 case without rerunning optimization, OpenDSS, power flow or
ML. The nine CSVs, original audit and original manifest are byte-identical copies
of the accepted local extraction package. `SHA256SUMS` covers all eleven files,
including the manifest itself. Git attributes preserve their original bytes.

| Property | Value |
| --- | --- |
| Accepted B0 authority | `IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json` |
| Metric scope | `PLANNING` |
| Model buses | 4,912 |
| Topology LINE elements | 3,703 |
| Active scientific lines / matched lines | 3,698 / 3,698 (100%) |
| Inactive tie lines | 5 |
| Coordinate-mapped LINE elements | 3,703 (100%) |
| Critical interval | 31 zero-based / 32 one-based |
| Critical interval start | `2025-05-21T07:45:00+10:00` |
| Interval end | `2025-05-21T08:00:00+10:00` |
| Critical LINE | `Line.tpx21459660c0` |
| Native primary phase / terminal / conductor | C / 2 / `t2_node1` |
| Maximum loading | 0.8487691403696187 p.u. |
| Current / stored rating | 132.40798589766052 A / 156 A |

## Plotting contract

Use `05_B0_plotting_ready.csv` and the `plot_enabled` mask. Color enabled `LINE`
elements with `rho_line_max`. Draw transformers, regulators and the source
reactor in fixed gray. All five source-disabled tie lines remain in topology and
plotting CSVs with `loading_status=INACTIVE_TIE`, `rho_line_max=NA`, and
`plot_enabled=FALSE`. Their absence from the scientific metric is expected.
Both `ACTIVE_LINE_LOADING_COVERAGE` and `INACTIVE_TIE_PRESERVATION` pass.

The representative LINE value is the maximum over all valid stored
terminal/conductor axes. `conductor_label` preserves the original key;
`terminal_of_max_loading` separates the numeric terminal. The primary phase
column uses the frozen phase mapping. For split-phase secondaries, `node1` must
not be interpreted automatically as primary phase A. In the phase-detail CSV,
these columns describe each individual row. Its `phase` column retains the
original terminal/conductor key.

Geometry comes from the actual native `Master-unbal.dss` dependency set and the
frozen additive PCC overlay. Only horizontal reflection was applied to place the
substation on the left. Raw coordinates are retained exactly. Unstored terminal
P/Q and emergency-current properties remain NA. The optional PNG preview was
not generated.

## Files and authority scope

| File prefix | Content |
| --- | --- |
| 00 | Active-model bus coordinates and source hashes |
| 01 | Complete branch topology, types, raw endpoints and inactive status |
| 02 | One-row B0 critical interval and witness |
| 03 | One row per LINE, with maximum stored conductor loading |
| 04 | All 12,312 valid terminal/conductor rows at the B0 critical time |
| 05 | Joined geometry and B0 loading |
| 06 | Empty B3 same-time join schema |
| 07 | 34 extraction validation gates, all PASS |
| 08 | Separate stored `B0_REPLAY_AC` phase detail at the B0 reference time |

The auxiliary AC CSV is the saved preflight B0 replay anchor, not a newly run
production AC trajectory. Its arrays match the stored planning baseline; the
accepted final AC file supplies matching extrema for all 96 slots. The primary
planning scope remains separate. No B3 numerical loading is included.

Future B3 rows must reference B0 interval 31 and its start timestamp, use the same
topology and coordinates, and share one color scale with B0. B3's own critical
time must not replace the B0 reference time.

## Verification

From the repository root, with Python 3.9 or later:

```sh
python -B tools/validate_ieee8500_b0_plotting.py
python -B -m unittest discover -s tests -p test_ieee8500_b0_plotting_package.py
```

The validator uses only the standard library. It reads the packaged data, checks
all file hashes, coordinates, active/inactive joins, phase maxima, conductor
identity, interval-start semantics and the empty B3 schema. It writes no files
and invokes no scientific engine. The negative tests verify that a zero-filled
inactive tie, missing conductor, wrong representative maximum, interval-end
substitution or populated B3 template is rejected.

The original audit's `GIT MODIFICATION COUNT = 0` records the completed extraction
stage. The subsequent PR packaging was separately authorized. Scientific
execution remains zero across both stages. Original absolute paths are retained
as provenance references; the portable validator does not require those paths.
The raw 26-GB archive and `_work` authoring/runtime files are not included. Its
whole-archive hash is declared provenance, while the extraction independently
checked the 149 local source files against the recorded authorities. Rechecking
raw-source identities requires access to those external files.
