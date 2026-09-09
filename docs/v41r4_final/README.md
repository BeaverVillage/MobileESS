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

## Paper CSV projection and scientific limitations

Final integrated status: **PAPER_DATA_PROJECTION_PASS_WITH_COMPUTE_DEFERRAL_LIMITATION**.
The physical campaign is **PASS_124_OF_124**, May31 B2 is **RESOLVED**, and the
corrected paper projection is **PASS_AFTER_METADATA_CORRECTION**. The consolidated
[final authority report](evidence/final_reaudit/FINAL_PAPER_DATA_AUTHORITY.md) and
[machine-readable authority](evidence/final_reaudit/FINAL_PAPER_DATA_AUTHORITY.json)
bind these separate findings to the unchanged raw archive and all eleven CSVs.

The current paper-data selection is the existing V41R4 campaign's `MobileESS_V41R4_Paper_CSV_Export_corrected_20260909_112635` folder. This is a metadata correction of the same 31-day, 124-policy-day result; no campaign rerun produced it. The `00_experiment_authority.csv` method_SHA cell now uses the archived frozen Actual method. The other ten result CSVs are byte-identical. All eleven CSVs total 86,880,591 bytes and remain local.

The initial export's FAIL_CLOSED receipt remains in `evidence/paper_export/` as history. The subsequent independent archive audit classifies the corrected **CSV projection as valid, with a scientific terminal-service limitation**. This does not turn its 619 flagged records into passing terminal checks: the exporter retains the original additional-invariant gate, so running the exporter alone can still report FAIL_CLOSED. The independent audit classification is a separate finding.

The 619 job-policy-day records (B1=306, B3=313; 297 unique job UIDs) preserve total planned compute service but defer additional service beyond the D-day horizon. Extra post-horizon service totals 15,897 GPUh for B1 and 16,020.5 GPUh for B3 across independent daily experiments. These sums are not a continuously propagated monthly backlog. Grid improvements combine service deferral, location changes and MESS control; their causal shares are not identified. They must not be described as improvements under equal D-day service.

Job-level completion deadline authority could not be established for any of the 677 selected migrations. Requested-walltime reference completion is not an established migration deadline. Deadline compliance, violations and slack therefore remain NOT_AVAILABLE; neither zero violations nor universal deadline compliance is supported. See [the CSV audit](evidence/posthoc/CSV_REAUDIT_REPORT.md), [the deadline audit](evidence/posthoc/DEADLINE_AUDIT_REPORT.md) and [its authority evidence](evidence/posthoc/DEADLINE_AUTHORITY_EVIDENCE.md).

The workload trace does not provide an explicit job-level completion-deadline authority for the migratable jobs considered in this study. Accordingly, checkpoint-migratable jobs are modeled as best-effort, latency-tolerant batch workloads.

Checkpoint migration preserves total planned compute service, while checkpoint-to-transfer waiting, WAN transfer, and restart can defer part of that service beyond the D-day evaluation horizon.

The paper-facing term is **migration-induced post-horizon compute-service deferral**.
Report grid flexibility benefit versus compute-service deferral as a trade-off.
B1 and B3 extra service is respectively 3.17798% and 3.20267% of B0 scheduled
D-day GPUh over the 31 episodes; the maximum daily ratio is 17.4087%.
P1 percent-improvement correlations (Pearson/Spearman, N=31) are
0.372677/0.379829 for B1 and 0.109618/0.077024 for B3. These associations do not
identify a causal contribution. The historical `terminal_residual_violation_jobs`
field and RW diagnostic fields retain their original schema. They denote the
additional export invariant or RW comparisons, not established job-deadline
violations; physical voltage/current violation fields retain their physical meaning.

Each operating day is evaluated as an independent day-ahead episode; post-horizon compute service is therefore recorded as terminal carry-out and is not propagated as next-day backlog.

The May evaluation is not a continuous month-long workload simulation. No
service-neutral, deadline-compliant or SLA-preserving migration claim is made.

### ML metric availability

The [ML metric scope summary](evidence/final_reaudit/ML_METRIC_SCOPE_SUMMARY.json)
preserves all 22 stored rows and their original numeric strings and populations.
Runtime Q90 coverage, 15-minute reservation coverage, pinball loss, MAE, median
absolute error and underprediction rate use 40,335 matched pending job-day pairs.
The 6,209 unmatched/unavailable pairs are separately reported from 46,544 total
pairs. H4 raw/actionable coverage, raw-forecast MAE, mean/P90 actionable shortfall
and cap activations use 2,511 windows (31 x 81). Selected-route ETA MAE, SafeETA
coverage and margin use 72 deduplicated B2/B3 route observations. Full-link Q50
MAE/WAPE, Q90 coverage and quantile crossings remain NOT_AVAILABLE in the
preserved CSV export. The subsequent production provenance recovery below
establishes their PR19 held-out validation attribution separately. No CSV metric
was changed and no training or inference regeneration was performed.

Planning P1, Fresh line loading and Actual line loading remain separate metrics. Unbound feeder peak data remains NOT_AVAILABLE. Transformer loading is not merged into line rho.

### Traffic production provenance recovered

**V41R4_TRAFFIC_FULL_LINK_PROVENANCE_RECOVERY_PASS**. The expanded read-only
audit follows all 62 final B2/B3 M1 receipts to SHA-verified external execution
identities, 31 shared forecast and route-cache pairs, the transitive inventory,
and the exact PR19 frozen checkpoint. File and canonical hashes both verify.
All 95 final departures exactly match cached quantiles, Safe ETA and route links.
The loaded checkpoint's effective graph_smoothing_weight is **0.0**.

PR19 held-out Q50 MAE **28.778100967407227 s**, WAPE **4.140258207917213%**,
Q90 coverage **0.8831677945135705**, and **zero crossings** can now be attributed
to the exact production predictor. These are prior held-out 2024 validation
scores, not newly measured May full-link errors. The selected-route operational
metrics retain their separate N=72 scope. All eleven corrected CSVs are unchanged.
`VALIDATION_ONLY_RERUN_REQUIRED = NO`; every scientific reexecution count is zero.

See the [recovery report](evidence/traffic_provenance/TRAFFIC_PROVENANCE_RECOVERY_REPORT.md),
[machine-readable decision](evidence/traffic_provenance/TRAFFIC_PROVENANCE_RECOVERY.json),
and [62 policy-day bindings](evidence/traffic_provenance/TRAFFIC_PRODUCTION_DAY_BINDINGS.csv).
The earlier archive-only PARTIAL and final-re-audit availability records remain
historical evidence for their narrower source scope. External workspace evidence
is used only for Traffic provenance.

The later V41R5 experiment was stopped and removed from active local execution paths at the user's request. This PR retains V41R4 as the paper-result authority and includes no V41R5 code or result data. Local V41R5 files were isolated because deletion was blocked; they were not reported as deleted.

## Review and reproduction

- `SOURCE_SNAPSHOT.json`: exact copied-file SHA256, origin and repository destination.
- `evidence/restoration/`: frozen rule, final audit, May31 acceptance and execution evidence.
- `evidence/forensic_existence/`: diagnostic existence result, distinct from production.
- `PAPER_EXPORT_INDEX.json`: CSV names, counts, sizes and hashes; availability and failed-validation summary.
- `evidence/paper_export/`: delivered report, archive intake and independent failed-invariant confirmation.
- `evidence/final_reaudit/`: final integrated authority, raw-member bindings, terminal/deadline interpretation and ML metric scope; historical receipts remain intact.
- `tools/v41r4_final_snapshot/runtime/`: byte-preserved operational source for review, including historical coordinator helpers. These scripts depend on the original frozen environment and are **not clean-clone launchers**.
- `tools/v41r4_final_snapshot/packaging/`: exact archive builder used for local delivery.
- `tools/v41r4_final_snapshot/paper_export/`: archive-only exporter and intake helper. Requires Python, numpy, pandas and pyarrow. Pass `--archive` and `--output`; the caller supplies the local archive. Existing exported results are retained in new timestamped output directories on rerun.

Validation for this PR is static/source/hash and small projection-fixture checks only. No Gurobi, OpenDSS, SUMO, ML training, campaign restart or full archive re-export is required or performed for PR preparation.

Run `python tools/v41r4_final_snapshot/verify_snapshot.py` from the repository root (Python and numpy required). The check passed for all 77 copied-file hashes and 54 Python source parses, plus external-path rejection, unsafe-archive rejection, terminal-residual failure/passing controls, and CSV precision/Unicode/missing-value/boolean round trips. This engineering validation does not change the historical terminal-invariant failures or establish deadline compliance.

### Post-hoc audit provenance

`POSTHOC_SOURCE_SNAPSHOT.json` binds the additional report and script bytes. `evidence/posthoc/CORRECTED_EXPORT_INDEX.json` and `DEADLINE_AUDIT_INDEX.json` are compact catalogs linked by SHA256 to their full local manifests. `LOCAL_CSV_COMPARISON.json` records the ten identical result CSVs and the single metadata correction. The original `PAPER_EXPORT_INDEX.json` records the historical export and is retained unchanged.

The captured `tools/v41r4_final_snapshot/posthoc/` scripts use original local paths, audit caches and archived data. They are review snapshots, not a self-contained clean-clone audit pipeline. Their original completed-run manifests describe archive-wide checks. The earlier snapshot preparation verified copied hashes, syntax, the delivered CSV comparison and small fixtures. The subsequent final integration below adds direct archive reads without invoking those historical audit scripts or optimizers.

### Final integration audit

The subsequent `tools/v41r4_final_snapshot/audit_final_authority.py` performs a
read-only streaming hash of the final tar.gz and directly reads selected archived
JSON authorities without extraction. It cross-checks all 188,036 CSV job records
against final frozen compute segments, all 677 migration audit rows, 62 daily
boundary audits, May31 B2 acceptance, the 31-day paired denominator and retained
negative results. It verifies the existing deadline search through its local
manifest hash and frozen-source bindings; it does not repeat that broad search.
The resulting evidence distinguishes current static checks from the original
campaign's execution counts. All scientific reexecution counts for this final
integration are zero. The archive and both CSV deliveries remain read-only.
