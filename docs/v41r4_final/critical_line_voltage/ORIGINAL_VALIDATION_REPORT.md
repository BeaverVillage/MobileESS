# V41R4 critical-line voltage validation

Overall status: **PASS**. Scientific result reruns: **0**.

Primary: realized pre-Q. Secondary: final accepted post-Q. Reference points for both are the B0 pre-Q argmax.

## Authority and validation
- Voltage is read directly from archived `voltage_pu[slot,node_index]`; no inference, interpolation, or power-flow replay.
- Line current is archived `phase_current_a` and `phase_current_loading_pu`. Ratings and oriented endpoints are archived per-day, per-policy `BRANCH_PHASE_CURRENTS.parquet` topology fields. DA current observations are not used as realized currents.
- Sending/receiving means the archived from_bus/to_bus orientation (upstream/downstream topology), not the instantaneous direction of power flow. The literal DSS Bus1/Bus2 order was not inferred.
- All 96 slots and non-transformer line phases are searched. Switch elements recorded as lines are retained to match the paper authority. Exact ties select the first slot then first branch-phase in archived array ordering.
- Full node/branch axes, unique endpoint phase mapping, 96-slot convergence, finite voltages/currents, recorded current/rating ratios, final candidate and native output hashes, and paper maxima are checked.
- SD is sample SD (ddof=1). Improved/worsened requires a change outside +/-1e-12 pu; unchanged includes this floating-point tolerance. Raw differences are not rounded or zeroed.
- B0/B1 primary and secondary read CONTROL_COMMON_BINDING, with no Q correction. B2/B3 primary reads ETA95_ACTUAL; secondary reads ETA95_QSAFE_ACTUAL.
- No source rows are silently dropped. An authority failure suppresses scientific CSV data rows and aggregates, with errors below. Transformer-only NaNs in the unused total-kVA array are structural and are not endpoint-voltage missingness.

## Missing per-policy topology file, resolved by shared authority
The 2025-05-31 B2 DA BRANCH_PHASE_CURRENTS.parquet is absent. Its topology is read from same-day B0 only after verifying identical archived electrical certificate SHA256 (95c21f1edaa3e0409bec07e9b4e256e35e4865a181b766bc80763065428bbe9a) and electrical base-data SHA256 (c0204b833d301f72b35468866d581d4475e4e6e4525f486a210fe301be8279ce). The full final B2 branch-phase axis and all 96-slot line-current/rating ratios are independently checked against that map. B2 voltages and currents are still read exclusively from its own final raw NPZ. This is shared immutable topology, not voltage or current reconstruction.

## Errors
[]

## CSV row counts
- 01_B0_reference_critical_points.csv: 31
- 02_policy_comparison_at_B0_critical_points_preQ.csv: 124
- 03_policy_aggregate_at_B0_critical_points_preQ.csv: 4
- 04_daily_paired_changes_preQ.csv: 31
- 05_policy_comparison_at_B0_critical_points_postQ.csv: 124

## Primary pre-Q aggregate
[
  {
    "policy": "B0",
    "N_days": 31,
    "mean_rho": 0.7012018740531762,
    "SD_rho": 0.07381277428650859,
    "mean_rho_reduction_pct_vs_B0": 0.0,
    "median_rho_reduction_pct_vs_B0": 0.0,
    "mean_abs_line_voltage_difference_pu": 0.0033468186880936113,
    "SD_abs_line_voltage_difference_pu": 0.0038112140344148788,
    "mean_abs_line_voltage_difference_change_vs_B0": 0.0,
    "median_abs_line_voltage_difference_change_vs_B0": 0.0,
    "abs_line_voltage_difference_improved_days": 0,
    "abs_line_voltage_difference_unchanged_days": 31,
    "abs_line_voltage_difference_worsened_days": 0,
    "mean_receiving_voltage_deviation_abs_pu": 0.0022088744800234034,
    "SD_receiving_voltage_deviation_abs_pu": 0.0018034427630373073,
    "mean_receiving_voltage_deviation_change_vs_B0": 0.0,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0,
    "receiving_voltage_deviation_improved_days": 0,
    "receiving_voltage_deviation_unchanged_days": 31,
    "receiving_voltage_deviation_worsened_days": 0
  },
  {
    "policy": "B1",
    "N_days": 31,
    "mean_rho": 0.6993020118470517,
    "SD_rho": 0.07408014783070431,
    "mean_rho_reduction_pct_vs_B0": 0.2754375574247917,
    "median_rho_reduction_pct_vs_B0": 0.11730970973520988,
    "mean_abs_line_voltage_difference_pu": 0.0033386547788208857,
    "SD_abs_line_voltage_difference_pu": 0.0038031629946596967,
    "mean_abs_line_voltage_difference_change_vs_B0": -8.163909272725313e-06,
    "median_abs_line_voltage_difference_change_vs_B0": -5.266003189063895e-10,
    "abs_line_voltage_difference_improved_days": 21,
    "abs_line_voltage_difference_unchanged_days": 6,
    "abs_line_voltage_difference_worsened_days": 4,
    "mean_receiving_voltage_deviation_abs_pu": 0.0022036566994230893,
    "SD_receiving_voltage_deviation_abs_pu": 0.0018007713872367798,
    "mean_receiving_voltage_deviation_change_vs_B0": -5.217780600313791e-06,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0,
    "receiving_voltage_deviation_improved_days": 15,
    "receiving_voltage_deviation_unchanged_days": 4,
    "receiving_voltage_deviation_worsened_days": 12
  },
  {
    "policy": "B2",
    "N_days": 31,
    "mean_rho": 0.608429532623754,
    "SD_rho": 0.07626420802508094,
    "mean_rho_reduction_pct_vs_B0": 13.326009052114081,
    "median_rho_reduction_pct_vs_B0": 12.39051964267383,
    "mean_abs_line_voltage_difference_pu": 0.0030037370671607924,
    "SD_abs_line_voltage_difference_pu": 0.0034307597785179387,
    "mean_abs_line_voltage_difference_change_vs_B0": -0.00034308162093281907,
    "median_abs_line_voltage_difference_change_vs_B0": -2.637488605294891e-08,
    "abs_line_voltage_difference_improved_days": 31,
    "abs_line_voltage_difference_unchanged_days": 0,
    "abs_line_voltage_difference_worsened_days": 0,
    "mean_receiving_voltage_deviation_abs_pu": 0.002725151968249195,
    "SD_receiving_voltage_deviation_abs_pu": 0.0017754078466388106,
    "mean_receiving_voltage_deviation_change_vs_B0": 0.0005162774882257918,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0011586523879540955,
    "receiving_voltage_deviation_improved_days": 14,
    "receiving_voltage_deviation_unchanged_days": 0,
    "receiving_voltage_deviation_worsened_days": 17
  },
  {
    "policy": "B3",
    "N_days": 31,
    "mean_rho": 0.5751503856544795,
    "SD_rho": 0.07823808442557205,
    "mean_rho_reduction_pct_vs_B0": 18.13296319250392,
    "median_rho_reduction_pct_vs_B0": 17.062098364059604,
    "mean_abs_line_voltage_difference_pu": 0.002932705265622536,
    "SD_abs_line_voltage_difference_pu": 0.003363090674423033,
    "mean_abs_line_voltage_difference_change_vs_B0": -0.00041411342247107513,
    "median_abs_line_voltage_difference_change_vs_B0": -3.118398228529884e-08,
    "abs_line_voltage_difference_improved_days": 31,
    "abs_line_voltage_difference_unchanged_days": 0,
    "abs_line_voltage_difference_worsened_days": 0,
    "mean_receiving_voltage_deviation_abs_pu": 0.003157617686866735,
    "SD_receiving_voltage_deviation_abs_pu": 0.0023430869403714117,
    "mean_receiving_voltage_deviation_change_vs_B0": 0.000948743206843332,
    "median_receiving_voltage_deviation_change_vs_B0": 0.001027662679221164,
    "receiving_voltage_deviation_improved_days": 12,
    "receiving_voltage_deviation_unchanged_days": 0,
    "receiving_voltage_deviation_worsened_days": 19
  }
]

## Secondary post-Q aggregate
[
  {
    "policy": "B0",
    "N_days": 31,
    "mean_rho": 0.7012018740531762,
    "SD_rho": 0.07381277428650859,
    "mean_rho_reduction_pct_vs_B0": 0.0,
    "median_rho_reduction_pct_vs_B0": 0.0,
    "mean_abs_line_voltage_difference_pu": 0.0033468186880936113,
    "SD_abs_line_voltage_difference_pu": 0.0038112140344148788,
    "mean_abs_line_voltage_difference_change_vs_B0": 0.0,
    "median_abs_line_voltage_difference_change_vs_B0": 0.0,
    "abs_line_voltage_difference_improved_days": 0,
    "abs_line_voltage_difference_unchanged_days": 31,
    "abs_line_voltage_difference_worsened_days": 0,
    "mean_receiving_voltage_deviation_abs_pu": 0.0022088744800234034,
    "SD_receiving_voltage_deviation_abs_pu": 0.0018034427630373073,
    "mean_receiving_voltage_deviation_change_vs_B0": 0.0,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0,
    "receiving_voltage_deviation_improved_days": 0,
    "receiving_voltage_deviation_unchanged_days": 31,
    "receiving_voltage_deviation_worsened_days": 0
  },
  {
    "policy": "B1",
    "N_days": 31,
    "mean_rho": 0.6993020118470517,
    "SD_rho": 0.07408014783070431,
    "mean_rho_reduction_pct_vs_B0": 0.2754375574247917,
    "median_rho_reduction_pct_vs_B0": 0.11730970973520988,
    "mean_abs_line_voltage_difference_pu": 0.0033386547788208857,
    "SD_abs_line_voltage_difference_pu": 0.0038031629946596967,
    "mean_abs_line_voltage_difference_change_vs_B0": -8.163909272725313e-06,
    "median_abs_line_voltage_difference_change_vs_B0": -5.266003189063895e-10,
    "abs_line_voltage_difference_improved_days": 21,
    "abs_line_voltage_difference_unchanged_days": 6,
    "abs_line_voltage_difference_worsened_days": 4,
    "mean_receiving_voltage_deviation_abs_pu": 0.0022036566994230893,
    "SD_receiving_voltage_deviation_abs_pu": 0.0018007713872367798,
    "mean_receiving_voltage_deviation_change_vs_B0": -5.217780600313791e-06,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0,
    "receiving_voltage_deviation_improved_days": 15,
    "receiving_voltage_deviation_unchanged_days": 4,
    "receiving_voltage_deviation_worsened_days": 12
  },
  {
    "policy": "B2",
    "N_days": 31,
    "mean_rho": 0.6084278914060575,
    "SD_rho": 0.07626406682002931,
    "mean_rho_reduction_pct_vs_B0": 13.326227143571378,
    "median_rho_reduction_pct_vs_B0": 12.39051964267383,
    "mean_abs_line_voltage_difference_pu": 0.003003600859828673,
    "SD_abs_line_voltage_difference_pu": 0.0034306254639574403,
    "mean_abs_line_voltage_difference_change_vs_B0": -0.00034321782826493834,
    "median_abs_line_voltage_difference_change_vs_B0": -2.637488605294891e-08,
    "abs_line_voltage_difference_improved_days": 31,
    "abs_line_voltage_difference_unchanged_days": 0,
    "abs_line_voltage_difference_worsened_days": 0,
    "mean_receiving_voltage_deviation_abs_pu": 0.0027257255386728746,
    "SD_receiving_voltage_deviation_abs_pu": 0.0017755894630061123,
    "mean_receiving_voltage_deviation_change_vs_B0": 0.0005168510586494716,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0011586523879540955,
    "receiving_voltage_deviation_improved_days": 14,
    "receiving_voltage_deviation_unchanged_days": 0,
    "receiving_voltage_deviation_worsened_days": 17
  },
  {
    "policy": "B3",
    "N_days": 31,
    "mean_rho": 0.574834721680028,
    "SD_rho": 0.0780471647550178,
    "mean_rho_reduction_pct_vs_B0": 18.174312274812724,
    "median_rho_reduction_pct_vs_B0": 17.182772916587812,
    "mean_abs_line_voltage_difference_pu": 0.002930369455836776,
    "SD_abs_line_voltage_difference_pu": 0.0033572555054581523,
    "mean_abs_line_voltage_difference_change_vs_B0": -0.00041644923225683534,
    "median_abs_line_voltage_difference_change_vs_B0": -3.118398272938805e-08,
    "abs_line_voltage_difference_improved_days": 31,
    "abs_line_voltage_difference_unchanged_days": 0,
    "abs_line_voltage_difference_worsened_days": 0,
    "mean_receiving_voltage_deviation_abs_pu": 0.0032874124026187074,
    "SD_receiving_voltage_deviation_abs_pu": 0.002292827196478285,
    "mean_receiving_voltage_deviation_change_vs_B0": 0.0010785379225953043,
    "median_receiving_voltage_deviation_change_vs_B0": 0.0010838222018959565,
    "receiving_voltage_deviation_improved_days": 11,
    "receiving_voltage_deviation_unchanged_days": 0,
    "receiving_voltage_deviation_worsened_days": 20
  }
]

## Interpretation
B0 daily maximum mean: 0.7012018740531762. B3 mean same-point rho reduction: 18.1329631925%. Mean change in absolute line-voltage difference: -0.0004141134224710751 pu. Mean change in receiving-end absolute deviation from 1 pu: 0.000948743206843332 pu.
The proposed sentence is supported as a descriptive mean association across these 31 fixed B0 reference points.
This comparison does not establish causality, universal daily improvement, or a feeder-wide voltage improvement. Separate receiving-end deviation results must be reported. These reference points mix line.l10 and line.sw2; absolute voltage differences are not normalized by segment length.

Full check records and distinct policy-own daily maxima: VALIDATION_DETAILS.json.