# Final report

V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_FAIL_CLOSED

- Source archive: C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz
- Archive SHA256: `1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`
- Archive size: 13,524,418,762 bytes
- Archive files: 69,297; uncompressed: 39,106,987,471 bytes
- Detected: 31 days, B0/B1/B2/B3 each 31, 124 policy-days, no missing or duplicate final-index units.
- Destination: C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\MobileESS_V41R4_Paper_CSV_Export
- CSV export: 86,880,540 bytes (86.881 MB); reduction versus source archive: 99.357602%.
- External workspace reads: 0. Raw archive unchanged (SHA256 and modification time checked).
- Validation: FAIL
- Failure counts: {'AIDC_TERMINAL_RESIDUAL_INCREASE': 619}

| CSV | Rows | MB | Parts | SHA256 |
|---|---:|---:|---:|---|
| 00_experiment_authority.csv | 1 | 0.001217 | 1 | cd2830a4f2f177780a6da00ecccae58c702b51990f1fdcb173daee21bd46c8ff |
| 01_policy_day_summary.csv | 124 | 0.053583 | 1 | 3f0255668ecc000fd29e705d8706106cb50cc0135aef16d4f3ea73b890f0f1a3 |
| 02_actual_summary.csv | 124 | 0.118644 | 1 | 838f6846da70d6834da16b533ae35f90c05357c5cba2f3b56895ca2275762615 |
| 03_q_correction_summary.csv | 124 | 0.069565 | 1 | 42acb4bf288b70d98a3bb6a9997e26ade1eaed64e20a1c3646e80d1bcc4c2196 |
| 04_mess_timeseries.csv | 47616 | 29.786368 | 1 | dce66e191330783cda1e0b6a7b3c4ca27c2ee2d149e2c0c82a2fa9c3e51cc621 |
| 05_grid_timeseries.csv | 43392 | 15.898027 | 1 | b8694c7293e1adfc1b16ede8316e68e1b7ecf81a85aa0a759019bf06fc59401a |
| 06_aidc_decisions.csv | 188036 | 40.896823 | 1 | bde2c3fc182622bcfbd8176492b3638dc92256cda99b8dbce7c6dcb899d43853 |
| 07_ml_performance.csv | 22 | 0.004514 | 1 | 30eae97ef4fd4374badb60efd81d209816d71351b5afc96c868e051647c2a557 |
| 08_policy_aggregate_statistics.csv | 4 | 0.002224 | 1 | 5f68e10c33e1f6f676a7a5884deb1beaf1d8d6155658c54405718c2902c1aaa5 |
| 09_paired_policy_comparisons.csv | 31 | 0.022824 | 1 | e72b541352bcdcdec668d255be7d9148d4a8e598b5367be9aa5c3b875094f8d7 |
| 10_mess_utilization_statistics.csv | 124 | 0.026751 | 1 | 7861d491a6ebf23e4a3e314e57585b4f0fa7de8b251f827a715306b55a8ca197 |

## Unavailable metrics

- grid_model, traffic_links, traffic_slots_per_day, traffic_interval_min, traffic_model_id: No complete final grid/traffic model identification or full traffic graph authority is established by the packaged final result index. External provenance targets intentionally not read.
- link_Q50_MAE_s, link_Q50_WAPE_pct, link_Q90_empirical_coverage, quantile_crossings: The archive lacks an identified full-link validation authority with frozen quantile predictions and matched realized labels. Selected-route metrics are separately scoped.
- B0_feeder_peak_kW, MESS_nameplate_to_B0_peak_ratio, MESS_actual_max_P_to_B0_peak_ratio: Historical FEEDER_SYSTEM_96 tables do not match the final Actual voltage/loading trajectory, or are absent. Final NPZ arrays do not provide source-terminal active power.
- Q_runtime_s: No separately identified end-to-end Q-only wall-clock authority; recorded search_runtime_seconds is exported separately without relabeling total replay time.
- mean_abs_delta_Q_changed_vehicle_slots_kvar: NaN when the changed-vehicle-slot denominator is zero; it is not replaced by zero.
- origin_service_id, destination_service_id, departure_slot, arrival_slot: NOT_AVAILABLE denotes no associated move in that slot; no arrival is inferred from another scenario.

## Validation failures

All adverse records are retained in the CSVs. Detailed records are in VALIDATION_FAILURES.json. The campaign completeness is independent of these additional paper-data checks.

Primary analysis files: 01, 02, 03, 08, 09 and 10. Use them with the validation status above; raw data were never altered.

## Independent confirmation of terminal-residual failure

An independent CSV/hash review confirmed all 11 CSVs, their row counts and the 500 MB limit. The 619 terminal-residual increases affect 60 policy-days: B1 has 306 records and B3 has 313 records. All 619 are checkpoint-migrated jobs. These are job-policy-day records, not 619 unique physical jobs.

Example: 2025-05-01 B1, job 8571256. The B0 reference compute segment is [0,188). The optimized segments are [0,26) and [28,190). At the issue-origin boundary 120, remaining compute service increases from 68 to 70 slots due to the migration interruption. This violates the requested export invariant even though the archived campaign's AC-feasibility checks completed successfully.

No source decision was repaired or reoptimized. See INDEPENDENT_EXPORT_REVIEW.json and VALIDATION_FAILURES.json. Total output folder size at final verification: 88.34 MB (CSV files: 86.88 MB).
