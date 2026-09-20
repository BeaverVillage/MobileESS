# Extraction audit

Prepared on 2026-09-20 for the preserved September 13–14 campaign, operating
day **2025-05-01**, six MESS vehicles. No optimization or electrical simulation
was run: **SCIENTIFIC_EXECUTION_COUNT = 0**.

## Provenance

The exporter read 55 saved source files. Their relative paths, sizes and SHA256
hashes are recorded in `paper_csv/MANIFEST.json`, alongside output hashes and
table provenance. The small `evidence/RESULT_WITH_ENERGY_EXCEPTION.json` file
is an unmodified copy of the campaign's final authority.

The original raw archive remains in the user's local results directory:
`IEEE8500_MAY01_MESS6_RAW_RESULTS_20260914_151641.tar.gz`.
Its size is 12,665,757,241 bytes and its SHA256 is
`ed1d8316ce12725f5456f0f1a76440ced7f5257baf2f334f965df5775c45173e`.

`ARCHIVE_VERIFICATION.json` records a successful full compressed-file checksum
and comparison of all 55 extraction sources with the frozen raw-file manifest
inside the archive, which inventories 14,115 original files. This comparison
uses archived manifest hashes; it is not a fresh hash of every archived payload.

## Validation

The standalone verifier passed for all 13 CSVs, including output checksums,
policy coverage, May01 timestamps, scope-specific ordering, same-time heatmap
coverage, AC results, runtime semantics and the explicit B3 energy exception.
Five unit tests passed: the valid package and rejection of an altered cell,
a mixed heatmap timestamp, a hidden energy-floor failure, and a component sum
misrepresented as end-to-end runtime. These checks run locally without requiring
raw data, numpy, a solver or OpenDSS. A GitHub Actions workflow was omitted because
the current OAuth credential lacks workflow scope.

The original CSV directory was unavailable. These files are a newly generated
serialization of the preserved raw results, not recovered original CSV bytes.
The final-authority energy exception remains visible; extraction success does
not convert the original 440 kWh operating-floor failure into a pass.

## Scope limits

The package excludes the old May21/four-MESS case and later September experiments.
The archive is a raw-results snapshot, not a complete runtime distribution.
Missing end-to-end timings and global optimality bounds remain NA. Recorded
component timings must not be described as total optimization runtimes.
