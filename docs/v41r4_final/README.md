# V41R4 May completion, restoration and local paper-data export

May31 B2 was physically feasible with its frozen AIDC plan and MESS mobility decisions, but its restricted local restoration model was infeasible. The versioned post-DA closure now tries the original local correction first and invokes a deterministic full-physical P/Q fallback only on local-model infeasibility. The completed May campaign contains 31 days × B0/B1/B2/B3 = 124 accepted policy-days.

This is a review snapshot stacked on PR #41 (Actual acceleration), which in turn uses PR #39 (May loop budgets). PR #40 separately records the alpha_BG=1.15 background screen. Earlier work is referenced through those PRs; this PR records the subsequent restoration, campaign completion, monitoring handoff, local archive creation and paper CSV projection.

## Restoration and execution

- Primary Fresh PASS remains a no-op. A failed Primary Fresh first uses the existing fixed-discrete local restoration. Only an infeasible local model opens the full physical P/Q fallback.
- AIDC decisions and MESS routes, locations, destinations and departures remain fixed. Authority remains 300 kW / 400 kVA per MESS, eta=0.95, terminal energy 760 kWh and the existing battery/mobility constraints. No background, rating, source-voltage or scientific-objective change is introduced.
- The production fallback finds its own candidates and selects the minimum deviation among exact-AC-validated candidates. The earlier Q=0 forensic witness is existence evidence only. Neither the production search nor Actual Q-only correction claims global optimality.
- All accepted results require 96-slot clean sequential OpenDSS validation of voltage, line phase-current, transformer phase-current and transformer total-kVA limits.
- Existing 123 DA decisions were reused. May31 B3 was a first required execution, using existing final B1 as A0 followed by M1, A1, MF, Fresh and Actual.
- The final execution/hash audit records 122 reused Actual results and two new Actual results (May31 B2 and B3), zero existing DA reoptimizations, and 50,490 verified hashes.

The monitor displays the revised acceptance/Actual namespaces. The first detached B3 Actual attempt failed before execution because Git was absent from the detached process PATH. The environment-only resume preserved the failed log and restarted Actual without DA reoptimization. The final completion receipt confirms that the subsequent Actual and audit finished.

## Local data delivery

`LOCAL_DATA_CATALOG.json` records the requested destination and exact hash of the locally created archive:

- File: `V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz`
- Compressed bytes: 13,524,418,762.
- SHA256: `1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`.
- Archive tree: 69,297 regular files, including four package metadata files; 69,293 source-file hashes verified.
- Extracted bytes: 39,106,987,471 including package metadata.

The operation created a new archive at the requested destination. Original scientific files were not moved, deleted or rewritten. The archive, extracted raw files, CSV data and large logs are **not in Git, Git LFS, PR attachments or release assets**. Only small catalogs, audit summaries and source code are included.

## Paper export remains FAIL_CLOSED

The archive-only exporter produced all eleven requested CSV tables: 86,880,540 bytes, a 99.357602% reduction versus the archive. Main result tables each contain all 124 completed units; MESS time series has 47,616 rows, grid projections 43,392 rows, AIDC decisions 188,036 rows, and paired comparisons 31 rows. Each CSV is below 500 MB and was read back and hash-checked. External workspace result reads were zero, and the archive hash and modification time were unchanged.

The campaign's completed AC acceptance is distinct from the additional paper-export invariant. The requested rule that optimized remaining compute service must not exceed the same-day B0 reference fails for **619 job-policy-day records across 60 policy-days**: B1=306 and B3=313. All are checkpoint-migrated jobs. No adverse records were removed to obtain a passing export.

For example, May01 B1 job 8571256 has reference segment [0,188), and optimized segments [0,26) and [28,190). At the archived issue-time boundary 120 (D-day midnight end), remaining compute service changes from 68 to 70 slots. The exporter therefore reports `V41R4_FINAL_ARCHIVE_PAPER_CSV_EXPORT_FAIL_CLOSED`. This PR does not repair or reoptimize those scientific results.

Missing full-link traffic validation and unbound feeder peak data are marked NOT_AVAILABLE. Historical feeder tables are not used where their voltage/loading trajectory differs from final Actual. Runtime/H4 metrics and selected-route metrics are scoped to archived matched predictions/labels. Planning P1, final Fresh line loading and final Actual line loading remain separate; transformer loading is never merged into line rho.

## Review and reproduction

- `SOURCE_SNAPSHOT.json`: exact copied-file SHA256, origin and repository destination.
- `evidence/restoration/`: frozen rule, final audit, May31 acceptance and execution evidence.
- `evidence/forensic_existence/`: diagnostic existence result, distinct from production.
- `PAPER_EXPORT_INDEX.json`: CSV names, counts, sizes and hashes; availability and failed-validation summary.
- `evidence/paper_export/`: delivered report, archive intake and independent failed-invariant confirmation.
- `tools/v41r4_final_snapshot/runtime/`: byte-preserved operational source for review, including historical coordinator helpers. These scripts depend on the original frozen environment and are **not clean-clone launchers**.
- `tools/v41r4_final_snapshot/packaging/`: exact archive builder used for local delivery.
- `tools/v41r4_final_snapshot/paper_export/`: archive-only exporter and intake helper. Requires Python, numpy, pandas and pyarrow. Pass `--archive` and `--output`; the caller supplies the local archive. Existing exported results are retained in new timestamped output directories on rerun.

Validation for this PR is static/source/hash and small projection-fixture checks only. No Gurobi, OpenDSS, SUMO, ML training, campaign restart or full archive re-export is required or performed for PR preparation.

Run `python tools/v41r4_final_snapshot/verify_snapshot.py` from the repository root (Python and numpy required). The check passed for all 62 copied-file hashes and 42 Python source parses, plus external-path rejection, unsafe-archive rejection, terminal-residual failure/passing controls, and CSV precision/Unicode/missing-value/boolean round trips. This engineering validation does not change the paper export's FAIL_CLOSED status.
