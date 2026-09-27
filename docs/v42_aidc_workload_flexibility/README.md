# V42 AIDC workload flexibility eligibility study

R1 adds **no temporal-flexible jobs or GPUh** under the registered rule and frozen service boundaries. R2 removes 43 standby job-days / 56.5 GPUh. Retain R0; this study does not support a new production latency rule.

| Rule | Flexible job-days | Jobs % | Flexible GPUh | GPUh % | Incremental PCC kWh | PCC % | Added job-days / GPUh |
|---|---:|---:|---:|---:|---:|---:|---:|
| R0 | 1,611 | 3.427003 | 17,273.50 | 3.453156 | 9,461.109778 | 2.496910 | 0 / 0.00 |
| R1 | 1,611 | 3.427003 | 17,273.50 | 3.453156 | 9,461.109778 | 2.496910 | 0 / 0.00 |
| R2 | 1,568 | 3.335531 | 17,217.00 | 3.441861 | 9,430.163377 | 2.488742 | 0 / 0.00 |

The primary metric above is the pre-registered standalone capacity-witness screen: one job moves while every other job remains at B0. It is a conservative sufficient feasibility test, **not the production optimizer's jointly coupled temporal domain**. R0 production gate and candidate-domain reproduction are reported separately:

| R0 definition | Job-days | Day GPUh | GPUh % | Incremental PCC % |
|---|---:|---:|---:|---:|
| stored standby eligibility gate | 18,588 | 143,867.50 | 28.760644 | 20.796256 |
| exact restored production temporal domain | 4,767 | 52,192.75 | 10.433886 | 7.544538 |
| registered standalone capacity-witness screen | 1,611 | 17,273.50 | 3.453156 | 2.496910 |

Denominators: 47,009 independent job-day records, 500,223.50 admitted reference Day-D GPUh, 378,912.796624 frozen unscaled B0 PCC kWh. Full safe-duration service totals 2,707,618.00 GPUh, with pre-day/tail/backlog included; it is a separate metric. May snapshots repeatedly contain the same physical job, so these are not monthly unique-job execution totals.

`ALL_AVAILABLE` and `MAY` both cover May 01–31, 2025. Whole-raw-trace eligibility is **NOT_AVAILABLE** because other dates lack this exact V41R4 frozen reference/domain authority. No runtime model, admission schedule, or workload scale was invented to fill that gap. Raw-request bridge covers 10,559,977 raw accounting rows and 18,955 unique evaluation jobs; TRAIN has 439,534 distinct jobs completed before 2025-01-01.

## Reproduce

Python 3.11, numpy, pandas, pyarrow; versions are in `ENVIRONMENT.json`. Original local input paths and exact SHA-256s are in `SOURCE_MANIFEST.json`. Constants at the top of `study.py` locate external archives; path relocation is permissible only with identical hashes. Large original trace/frozen input archives are external dependencies, not bundled here.

From this directory:
```
python -m unittest test_contract -v
python study.py evaluate
python raw_request_bridge.py
python validate_independently.py
python report.py
```
`evaluate` restores ignored TRAIN CSV from the checked-in deterministic gzip and verifies its registered hash. It regenerates this study's evidence only. To independently rebuild TRAIN, use a fresh copy/output directory without registration artifacts, then `python study.py prepare`; never overwrite this frozen registration. `prepare` refuses an existing registration. The threshold/rule registration was committed at `f937659f` (exact-byte preservation `fcc28fd0`) before evaluation.

The only post-freeze evaluation-code repair resolves a missing legacy source path to an identical SHA-256 copy in the retained repository. `IMPLEMENTATION_AMENDMENT.json` records it. No rule/threshold changes followed evaluation.

## Evidence

- `FLEXIBLE_MEMBERSHIP_R*.csv` deliberately retain **all** reference jobs and flags, including fixed/unadmitted jobs; filter `temporal_flexible` for primary membership. `temporal_domain` is the production-style geometric domain, `eligible_standby` the exact original stored gate, and `spatial_flexible` the unchanged frozen spatial/migration membership.
- `FEASIBLE_OPTIONS.csv` lists every safe standalone alternative as exact site/start sets. Options are alternatives, not independently selectable simultaneous moves; a future scheduler must retain aggregate capacity constraints.
- `COHORT_LATENCY_STATISTICS.csv`, `TRAIN_MEMBERSHIP.csv.gz`, `ELIGIBILITY_FUNNEL.csv`, `INCLUSION_BY_COHORT.csv`, and `SHIFT_WINDOW_DISTRIBUTION.csv` expose cohort support, selection, reason and windows.
- `GPUH_SHARE_BY_DAY.csv` and `RULE_COMPARISON.csv` contain exact numerators/denominators, category totals, and non-targeted 20/30/40 reporting.
- `SERVICE_FEASIBILITY_AUDIT.json`, `LEAKAGE_AUDIT.json`, `RAW_REQUEST_BRIDGE.json`, and `INDEPENDENT_VALIDATION.json` distinguish observed checks from provenance limitations.
- Read `FINAL_REVIEW_KO.md` for the verdict and `PROVENANCE_LIMITATIONS.md` before interpreting these as operational workload flexibility.

No ML/CC4/runtime fitting or prediction, traffic, optimizer, MESS, grid simulation, Actual replay, or V42 A1-M1-A2-M2 execution occurred. Existing evidence was read only. No production integration was made.
