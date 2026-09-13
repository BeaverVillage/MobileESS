# Critical-line voltage source snapshots

These two files are byte-identical snapshots of the completed 2026-09-11
read-only analysis. Their original SHA256 values are in
`docs/v41r4_final/critical_line_voltage/LOCAL_DATA_CATALOG.json`.
They are not imported by production or registered as tests.

The extractor streams the raw tar archive, selectively copies AC/topology
evidence, and creates the five CSVs plus validation/provenance files. Its
independent verifier compares saved CSVs with archived arrays and formulas.
Neither script imports scientific project modules or calls any solver,
OpenDSS, routing, SUMO or ML execution.

These snapshots retain the original Windows paths and environment. They are
not portable CLI entry points. The extractor writes beside `__file__`; copy
both scripts into a new local output directory outside Git before executing.
The original README, source paths, local dependencies, manifests and selected
raw-index requirements are documented in that original output directory,
whose location and evidence hashes are recorded in the catalog. On a migrated
machine, adapt source/output/repository paths in the local working copies and
record their new script hashes. Do not overwrite the original analysis.

Dependencies are Python, numpy, pandas and pyarrow; the original dependency
versions are in the catalog. No dependency packages are committed.

With those local prerequisites satisfied, the historical stage sequence is:

```text
python extract_critical_line_voltage_analysis.py --stage intake
python extract_critical_line_voltage_analysis.py --stage supplement
python extract_critical_line_voltage_analysis.py --stage analyze
python verify_critical_line_voltage_outputs.py
```

The analysis enforces archive/output hashes, final-result state identity,
phase axes, endpoint availability, rating consistency and paper controls.
An unresolved per-date authority error suppresses scientific output rows.
Read the generated validation status; the historical scripts do not provide
a uniform nonzero exit code for every reported scientific validation failure.

PR packaging did not execute either snapshot or repeat the scientific work.
