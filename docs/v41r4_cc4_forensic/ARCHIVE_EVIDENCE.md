# Accessing original evidence

The report's raw-artifact links lead here because multi-gigabyte extracted
execution records are intentionally not committed. The original archive member
path remains visible in each link label and in
[CC4_EVIDENCE_SOURCE_MAP.json](CC4_EVIDENCE_SOURCE_MAP.json). Window and job CSVs
also carry source-member paths.

- Archive: `V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz`
- Bytes: `13524418762`
- SHA-256: `1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`
- Member prefix: `V41R4_May2025_raw/`
- Final authority: `FINAL_RESULT_INDEX.json` under that prefix.

Use the archive's `FILE_MANIFEST.json` to validate extracted member hashes.
The extraction manifests, full inventory and extracted evidence are retained
with the original local `CC4_FORENSIC_20260922` audit. The published extraction
receipts describe that September 22 audit; they do not claim a new archive scan
on the PR publication date.

Important member paths relative to the prefix:

| Evidence | Path |
| --- | --- |
| Final Job replay | `frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/{day}/{policy}/ACTUAL_JOB_REPLAY.json` |
| Delay records | The same directory's `aidc/PHYSICAL_EXECUTION_DISPATCH.parquet` and `aidc/DELAYED_JOBS.parquet` |
| H4 labels | The same directory's `H4_SCORE.json` |
| Final May 31 B2/B3 | Use `v41r4_selective_actual_revision_v1` instead of the above namespace |
| Prediction and cap | `frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{policy}/dayahead/ml/H4_WINDOW_PREDICTIONS.parquet` |
| Planned headroom | Final accepted joint's sibling `PLANNING_RESULT.json` |

The small [source snapshots](source/) are byte-identical reference copies for
review, not runnable replacements for the experiment. Their hashes and recorded
authority are in [source_bindings.json](source_bindings.json).
`dayahead/v40d_actual/job_replay.py` was not directly hash-bound by that receipt;
its limitation is explicitly retained in the report. All other copied core
source bindings in that file were checked during the original audit.
