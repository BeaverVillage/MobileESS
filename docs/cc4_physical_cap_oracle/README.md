# CC4 physical-cap oracle audit

The frozen May 2025 evaluation has 2,511 unique windows. Physical-cap oracle
coverage is **2,158 / 2,511 = 85.941856%**, so the 85% target is attainable under
the cap alone. Realized physical-cap exceedances number **353**, distinct from
the **517** windows where the prediction was clipped.

Read [REPORT.md](REPORT.md) for definitions, separate historical-cap results,
validation, and the limits of this conclusion. The historical-only ceiling is
2,418 / 2,511 = 96.296296%. No model changes are included.

## Evidence

- [SUMMARY.json](SUMMARY.json): exact counts, rates, gaps, and attainability.
- [CC4_PHYSICAL_CAP_EXCEEDANCE_WINDOWS.csv](CC4_PHYSICAL_CAP_EXCEEDANCE_WINDOWS.csv):
  all 353 exceeding windows, dates, starts, realized work, cap, and exceedance.
- [CC4_ALL_MAY_WINDOWS.csv](CC4_ALL_MAY_WINDOWS.csv): the complete population.
- [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) and [VALIDATION.json](VALIDATION.json):
  original September 23 source hashes and checks. Absolute paths are historical
  provenance from the original machine, not required checkout locations.

The report, JSON evidence, and CSVs are preserved byte-for-byte from the completed
audit. The accompanying script only adds explicit input/output paths and requires
every consumed source to have an extraction-manifest hash. Computation is unchanged.

## Reproduce from local authority

Requires Python with NumPy, pandas, and a Parquet reader such as pyarrow. The large
raw authority archive is not committed. Supply the original extracted
`CC4_FORENSIC_20260922` directory, including `*evidence_manifest.json` files and
`evidence/V41R4_May2025_raw`. Use a new output directory:

```powershell
python docs/cc4_physical_cap_oracle/audit.py --forensic-root "D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922" --output-dir "D:/ChatGPT/cc4-oracle-recheck"
```

The script reads the final result index, checks all 124 policy-day bindings,
reconstructs physical caps from eligible slot capacities, and deduplicates
policies only after exact equality checks. It never imports model code or runs
fitting, inference, optimization, or replay. Do not run Python with `-O`, which
disables its evidence assertions.

The May 21 contributor table is absent in the extracted evidence. Its 81 targets
remain included using the stored final H4 scores, identical across four policies.
The other 30 days also have exact contributor-level target reconstruction.
