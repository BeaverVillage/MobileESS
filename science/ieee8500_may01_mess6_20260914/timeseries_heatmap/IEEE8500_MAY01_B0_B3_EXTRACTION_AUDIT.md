# IEEE8500 May 1 B0/B3 extraction audit

Status: **PARTIAL**. Electrical line loading and all 96-slot aggregates were materialized from the specified raw archive. Base feeder coordinates and disabled-line inventory are absent from that archive. Blank coordinates and an unknown disabled count are preserved. No inferred coordinates or disabled loading zeros were added.

## Source authority

- B0: `independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913/actual/B0/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz`; summary and slot extrema in the same folder; `independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913/AXES.json`.
- B3: `independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/actual_B3_energy_exception_20260914/B3/FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz`; summary and slot extrema in the same folder; `independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/AXES.json`.
- Both COMPLETE and AC_SUMMARY files state `REALIZED_OPERATION_AC`, 2025-05-01 and 96 converged/settled slots. B3 is the archived accepted energy-floor-exception Actual branch.
- The NPZ `line_current_loading_pu` values are absolute normalized conductor loading. `AXES.json` supplies exact axis ordering and `line_rating_A` for each conductor/terminal axis. The original engine code stores complex current divided by `line_rating`; the NPZ stores its magnitude. For every line-slot, the maximum across its valid terminal/phase axes is retained without clipping.
- `current_A` is reconstructed as selected normalized loading × selected axis rating. There is no independent current-ampere array in the selected NPZ, so current/rating is an algebraic check, not an independent raw-current check.
- `critical_phase` is OpenDSS node number 1, 2 or 3; `critical_terminal` is `t1` or `t2`. From/to buses are the archived t1/t2 axis bus names with numeric node suffixes stripped. Physical-line order follows first occurrence in AXES.
- The only archived coordinate files are the two identical 36-bus `PCC_BusCoordinates.dss` overlays. Their source x/y values are used unchanged, with no reflection. The `PCC_Master.dss` files reference an external `Master-unbal.dss` which is absent from the raw tar.gz. Neither external source nor prior derived CSV was used.
- Timestamp text is generated as May 1 local 00:00 plus 15 minutes per slot from the task's 96-slot resolution and archived date/slot indices. The selected archive files do not encode a timestamp or timezone series.

## Counts and checks

- Archive members scanned: 14117; active line elements represented in AXES: 3698; conductor/terminal axes: 12312.
- Disabled line elements: unknown; their inventory is unavailable in this archive. `is_switch` is also unavailable.
- B0/B3 long rows: 355008 each. Slots are exactly 0–95 with no duplicates; both policies use identical line labels and per-axis ampere ratings.
- Lines with both endpoint coordinates: 0/3698; endpoint coordinate fields present: 0/7396. Missing coordinates remain blank.
- Lines with phase/terminal rating variation: 0; topology `rating_A` is blank for such lines while long CSV retains the selected axis rating.
- Source-summary absolute difference: B0 0; B3 0. Gate: ≤1e-8.
- Per-slot extrema maximum absolute difference: B0 0; B3 0. Witness label mismatches from tie/ordering: B0 0; B3 0.
- Active loading is finite and nonnegative. Ratings are positive. All observed line axes have valid t1/t2 and node 1–3 labels; all observed lines have from/to buses. Duplicate policy-slot-line rows: 0 by unique line-axis grouping and complete slot loops.
- Top-K means use the same B0-ranked slots for both policies. Duration thresholds use inclusive ≥ comparisons and 0.25 hour per slot. Daily maxima are selected independently per line and policy. Signed B0 minus B3 values are retained.

Scientific execution count: **0**. Git modification count: **0** (script and outputs are outside repositories).
