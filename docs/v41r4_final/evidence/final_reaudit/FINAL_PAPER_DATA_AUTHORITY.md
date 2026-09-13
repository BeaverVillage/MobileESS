# V41R4 final paper-data authority

**V41R4_FINAL_PAPER_DATA_AUTHORITY_PASS**

The final May 2025 campaign remains 31 days x B0/B1/B2/B3 = **124/124 physically
accepted**, pending=0. Final Fresh and Actual results retain 96-slot convergence
and zero voltage, line, transformer-current and transformer-kVA violations.
Existing scientific results were not recomputed or rolled back.

## Projection authority and history

The final paper-data projection is
`MobileESS_V41R4_Paper_CSV_Export_corrected_20260909_112635`, status
**PAPER_DATA_PROJECTION_PASS_WITH_COMPUTE_DEFERRAL_LIMITATION**.
Its eleven CSVs total **86,880,591 bytes**. The sole changed cell is
`00_experiment_authority.csv: method_SHA`, from `NOT_AVAILABLE` to
`710a50cd439a9bb42cc8e6ea77b47eb1a5536c37cef894456a0859aeae9db368`.
The other ten CSVs are byte-identical to the original archive-only delivery.

The original archive-only export historically triggered FAIL_CLOSED under an
additional terminal-service invariant. Its report, index and independent review
remain unchanged in `../paper_export/` and `../../PAPER_EXPORT_INDEX.json`.
The independent audit established correct exporter projection, real deferral in
frozen decisions, and an additional invariant outside the frozen migration
method. Projection PASS does not remove those historical invariant outcomes or
change the exporter's gate.

The raw archive is `V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz`,
13,524,418,762 bytes, SHA256
`1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`.
It was read without extraction, mutation, moving or recompression.

## Computing-flexibility interpretation

The workload trace does not provide an explicit job-level completion-deadline authority for the migratable jobs considered in this study. Accordingly, checkpoint-migratable jobs are modeled as best-effort, latency-tolerant batch workloads.

Checkpoint migration preserves total planned compute service, while checkpoint-to-transfer waiting, WAN transfer, and restart can defer part of that service beyond the D-day evaluation horizon.

The 619 retained job-policy-day records are **migration-induced post-horizon
compute-service deferral**: B1=306, B3=313, 297 unique UIDs, 60 affected
policy-days. They are not failed jobs, exporter bugs or established deadline
violations. The amounts below are planned/reserved service, not realized GPU use.

| Quantity | B1 | B3 |
|---|---:|---:|
| Extra post-horizon planned service, GPUh | 15,897.0 | 16,020.5 |
| Extra / all B0 scheduled D-day GPUh | 3.17798% | 3.20267% |
| Maximum daily ratio | 17.4087% | 17.4087% |
| P1 percent-improvement Pearson, N=31 | 0.372677 | 0.109618 |
| P1 percent-improvement Spearman, N=31 | 0.379829 | 0.077024 |

Report **grid flexibility benefit versus compute-service deferral**.
Correlation does not identify causal contribution: migration location changes,
service deferral and MESS control coexist. No equal D-day service, service-neutral,
deadline-compliant or SLA-preserving migration claim is made.

Each operating day is evaluated as an independent day-ahead episode; post-horizon compute service is therefore recorded as terminal carry-out and is not propagated as next-day backlog.

These 31 independent daily episodes do not constitute continuous month-long
backlog propagation. The same UID can occur in more than one daily episode.

## Deadline authority

**DEADLINE_AUTHORITY_NOT_ESTABLISHED**. Explicit job-level completion deadline
authority is available for **0/677** migrations (B1=333, B3=344). Candidate
generation does not directly check a job-specific completion deadline.
`RW_completion_slot` is a requested-walltime based reference schedule completion
quantity and is not reinterpreted as an authoritative migration deadline.

Final completion exceeds RW in 388 flagged rows (B1=192, B3=196), and 412 rows
across all migrations. These are diagnostics, not deadline violations.
Within-deadline counts, deadline violations, slack and maximum deadline violation
remain **NOT_AVAILABLE**, which does not mean zero violations. Legacy diagnostic
column names are preserved without promoting them to deadline authority.

## May31 B2 restored acceptance

| Field | Final value |
|---|---:|
| status / full_PQ_fallback | PASS / TRUE |
| rho_max | 0.6319676083483373 |
| Vmin / Vmax | 0.9528912500659789 / 1.049570015262741 |
| transformer phase-current max | 0.9870033465393178 |
| transformer total-kVA max | 0.9999903138843736 |
| voltage / line / transformer-current / transformer-kVA violations | 0 / 0 / 0 / 0 |
| converged slots | 96 |

AIDC and route identities remain unchanged; restoration DA optimization and
route-search rerun counts are both zero. The failed pre-restoration trajectory
remains history and is not selected as the final result.

## Static CSV and ML review

Rows in files 00 through 10 are respectively
**1, 124, 124, 124, 47,616, 43,392, 188,036, 22, 4, 31, 124**.
All eleven pass SHA256, expected schema/header, UTF-8 byte round trip, full
binary64 value round trip, TRUE/FALSE spelling, NOT_AVAILABLE and NaN preservation,
and the per-file 500 MB bound. Paired statistics retain 31 days and negative
improvements. Undefined changed-slot Q means remain NaN, not zero.

All 22 ML rows retain their original numeric strings. Runtime metrics use 40,335
matched pending job-day pairs; the 6,209 unmatched/unavailable pairs are reported
separately out of 46,544. Available metrics include Q90 empirical and reservation
coverage, pinball loss, MAE, median AE and underprediction rate. H4 uses 2,511
windows for raw/actionable coverage, raw MAE, mean/P90 actionable shortfall and
historical/physical cap activations. Traffic operational metrics use 72 selected
route observations. Full-link Q50 MAE/WAPE, Q90 coverage and quantile crossings
remain NOT_AVAILABLE. Selected-route performance is not full traffic-model
validation. No model training, rerun or inference regeneration occurred.

## Evidence and verification scope

- [FINAL_PAPER_DATA_AUTHORITY.json](FINAL_PAPER_DATA_AUTHORITY.json): per-file
  schema/count/size/hash, current checks, final status and source paths/hashes.
- [RAW_AUTHORITY_BINDINGS.json](RAW_AUTHORITY_BINDINGS.json): selected JSON
  members read directly from the hash-verified archive.
- [TERMINAL_INTERPRETATION_SUMMARY.json](TERMINAL_INTERPRETATION_SUMMARY.json):
  fresh segment/CSV comparison and diagnostic aggregates.
- [DEADLINE_AUTHORITY_SUMMARY.json](DEADLINE_AUTHORITY_SUMMARY.json): all 677
  migration rows cross-checked against raw decisions; prior authority-search
  manifest and active method bindings verified, broad search not repeated.
- [ML_METRIC_SCOPE_SUMMARY.json](ML_METRIC_SCOPE_SUMMARY.json): exact 22 stored
  rows and availability/population boundaries.

Static verification traversed the original archive and compared all 188,036
exported job records with final frozen segments, retaining the 619 flagged rows.
Stored physical acceptance was inspected, not re-simulated. Historical search
and execution receipts are distinct from checks performed in this integration.
Only small text/JSON/code evidence is versioned; raw archives, extracted data,
large CSVs, NPZ/parquet and logs stay outside Git.

Reexecutions in this integration: **Gurobi=0, DA optimization=0, B1/B3
reoptimization=0, OpenDSS=0, Actual=0, Q search=0, SUMO=0, ML training=0,
ML inference regeneration=0, route search=0, checkpoint-domain regeneration=0**.
