# V41R4 voltage at fixed B0 critical-line operating points

At the 31 B0 pre-corrective-control critical operating points, B3 reduces
line loading on every date and reduces the absolute local endpoint-voltage
difference on every date. Receiving-end deviation from 1 pu increases on
average, with 12 dates improved and 19 worsened. These are different voltage
metrics and must not be described as one general voltage improvement.

This is read-only post-processing of the final V41R4 May 2025 archive from
PR #42. Existing scientific results and the original local analysis are
unchanged. Scientific reruns in both this analysis and its PR packaging: **0**.

## Primary: realized pre-Q

Each date selects the B0 maximum archived normalized line phase-current loading
over all 96 slots and `branch_kinds == line`. Transformers are excluded;
switch elements recorded as lines remain included, matching the paper metric.
Exact ties retain slot-major, archived branch-phase ordering. All policies are
then read at that same line, phase and slot. Reference lines are `line.l10`
and `line.sw2`, both on phase A. Time is fixed AEST (+10:00), slots 0..95.

| Policy | Mean same-point rho | Mean daily rho reduction vs B0 (%) | Mean absolute endpoint-voltage difference (pu) | Mean receiving-end absolute deviation from 1 pu |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.7012018741 | 0 | 0.0033468187 | 0.0022088745 |
| B1 | 0.6993020118 | 0.2754376 | 0.0033386548 | 0.0022036567 |
| B2 | 0.6084295326 | 13.3260091 | 0.0030037371 | 0.0027251520 |
| B3 | 0.5751503857 | 18.1329632 | 0.0029327053 | 0.0031576177 |

B3's paired mean change in absolute endpoint-voltage difference is
**-0.0004141134 pu** (improved/unchanged/worsened: **31/0/0**).
Its paired mean change in receiving-end absolute deviation is
**+0.0009487432 pu** (**12/0/19**). Raw values are unrounded in the local CSVs.
Sample SD uses ddof=1. Classification uses +/-1e-12 pu as the unchanged
floating-point tolerance, not an engineering significance threshold. Some
switch-segment differences are very small; segments are not length-normalized.

Appropriate descriptive wording:

> At the fixed B0 pre-Q critical operating points, B3 exhibited lower
> line-current loading and smaller absolute endpoint-voltage differences
> on all 31 dates, while receiving-end deviation from 1 pu increased on average.

This does not identify a causal effect or establish feeder-wide voltage
improvement. The service-deferral and independent-daily-episode limitations
in the [final results documentation](../README.md) continue to apply.

## Separate source states and metrics

Primary B0/B1 values come from `CONTROL_COMMON_BINDING` (no Q control).
Primary B2/B3 values come from `ETA95_ACTUAL` (realized before Q correction).
Secondary B2/B3 values come from final accepted `ETA95_QSAFE_ACTUAL`;
B0/B1 retain `CONTROL_COMMON_BINDING`. Both comparisons use B0 **pre-Q**
reference coordinates. Same-state B0 is the denominator for paired changes.

Secondary post-Q B3 mean same-point rho is 0.5748347217 (18.1743123% mean
daily reduction). Mean absolute endpoint-voltage difference is 0.0029303695 pu
(31/0/0 days), and mean receiving-end deviation is 0.0032874124 pu
(11/0/20 days). These values are not mixed into the primary table.

The existing headline realized daily-maximum means are approximately
B0=0.70120, B1=0.69960, B2=0.64800, B3=0.63767. Each policy selects its own
maximum for that metric. It is not the same-point metric in this analysis.
B0 daily maxima match the raw and paper authorities exactly, with mean
0.7012018740531762.

## Endpoint and rating authority

Voltage is directly indexed from each policy's archived `voltage_pu` array.
Current and loading come from its archived `phase_current_a` and
`phase_current_loading_pu` arrays. No power flow is recomputed.

Endpoint orientation and ratings are recorded `from_bus`, `to_bus` and
`current_limit_A` fields in archived topology tables. Sending/receiving denotes
that topology orientation, not instantaneous power direction. Both phase-node
indices are checked explicitly. All line phases and 96-slot current/rating
ratios are checked against final AC arrays. No line-name inference or voltage
reconstruction is used.

The May31 B2 DA topology table is absent. The same-day B0 table is used only
after checking identical archived electrical-certificate and electrical
base-data SHA256 values, the complete final B2 branch-phase axis and all
recorded current/rating ratios. B2 voltages and currents remain its own
final archived observations. Exact identities are retained in the original
report and catalog; this resolution is explicit, not a silently omitted row.

## Delivery and verification

Following the repository's local-data policy, all five CSVs stay outside Git,
LFS, PR attachments and release assets. Their names, columns, hashes and sizes
are in [LOCAL_DATA_CATALOG.json](LOCAL_DATA_CATALOG.json):

| Local CSV | Rows |
| --- | ---: |
| 01_B0_reference_critical_points.csv | 31 |
| 02_policy_comparison_at_B0_critical_points_preQ.csv | 124 |
| 03_policy_aggregate_at_B0_critical_points_preQ.csv | 4 |
| 04_daily_paired_changes_preQ.csv | 31 |
| 05_policy_comparison_at_B0_critical_points_postQ.csv | 124 |

- [RESULTS_SUMMARY.json](RESULTS_SUMMARY.json): unrounded primary/secondary aggregates.
- [Original validation report](ORIGINAL_VALIDATION_REPORT.md): source interpretation and all requested findings.
- [Original independent verification](ORIGINAL_INDEPENDENT_VERIFICATION.json): 2,976 saved raw-value/formula checks, alongside the original 33,001 primary checks.
- [PR readback receipt](PR_READBACK_VALIDATION.json): current local file hashes, saved CSV formulas and aggregates rechecked during packaging. This does not claim another raw archive analysis.
- [Source snapshots](../../../tools/v41r4_final_snapshot/critical_line_voltage/README.md): original Python scripts, byte-identical to the completed analysis.

The 13,524,418,762-byte raw archive has SHA256
`1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`.
Raw arrays, dependency packages, the full member inventory and detailed check
logs remain local. Original local evidence hashes are recorded in the catalog.
