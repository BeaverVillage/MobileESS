# V41R4 final-archive paper CSV export

V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_FAIL_CLOSED

This paper-data export is a projection of the supplied final raw archive.
It does not replace the full phase-resolved scientific authority.

All 124 archived completed policy-days are included. No workspace result was read and no optimizer, OpenDSS, SUMO or training was run.
The final result index selects restored May31 B2 and new May31 B3 from the selective Actual namespace, and the other 122 from the accepted robust V2 namespace.

## Files

- `00_experiment_authority.csv`: Case-study parameters and source archive authority.
- `01_policy_day_summary.csv`: Main B0/B1/B2/B3 Day-Ahead performance.
- `02_actual_summary.csv`: Realized-operation evaluation.
- `03_q_correction_summary.csv`: Q-only AC safety correction.
- `04_mess_timeseries.csv`: MESS P/Q/SoC/location/tap figures.
- `05_grid_timeseries.csv`: Line loading, voltage, transformer and regulator figures.
- `06_aidc_decisions.csv`: Temporal shifting / spatial relocation / migration.
- `07_ml_performance.csv`: ML performance.
- `08_policy_aggregate_statistics.csv`: Main results table.
- `09_paired_policy_comparisons.csv`: Paired B0/B1/B2/B3 analysis.
- `10_mess_utilization_statistics.csv`: MESS scale/utilization reviewer analysis.

## Definitions and use

UTF-8 BOM, comma separated, TRUE/FALSE booleans, full Python floating-point representation. NOT_AVAILABLE is unavailable/not applicable; NaN is mathematically undefined. Slots are zero-based. All parts repeat headers.
Planning P1, final Fresh line loading, and final Actual line loading are distinct. Line loading excludes transformers. Transformer total-kVA extrema have phase=TOTAL_ASSET.
Original Actual and pre-Q eta95 results in 05 are explicitly labeled historical/pre-control trajectories and do not replace final Actual in 02, 08 or 09.
B0/B1 pre/post Q rows share the verified control binding. Q-only MESS activity is preserved even when active-power dispatch is zero.
AIDC residual is actual remaining canonical compute-segment service after the D-day boundary, compared with same-day B0. Migration interruptions are included; no invariant failure is masked by using start+safe_duration alone.
Traffic route metrics cover selected executed routes, not the full traffic-link model validation. Runtime and H4 metrics are post-hoc comparisons of archived predictions and realized labels only.
MANIFEST.json supplies source hashes, per-unit paths, field availability, precise definitions, and all validation failures. A FAIL_CLOSED export must not be described as validated paper results.

## Re-run

Requires Python, numpy, pandas and a Parquet engine such as pyarrow. The scripts never import research project modules. Existing completed/failed export folders are preserved; a new timestamped directory is used.
```text
python _scripts/export_v41r4_final_archive_to_csv.py --archive "<source.tar.gz>" --output "<output folder>"
```

Temporary archive extraction is a read-only analysis source after intake. It is intentionally excluded from CSV export size. Full raw arrays remain in the unchanged source archive.
