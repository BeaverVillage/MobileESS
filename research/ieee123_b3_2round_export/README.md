# IEEE123 May 2025 B3 second-round paper export

This snapshot preserves the completed corrected 31-day campaign's raw-result
packaging scripts, eight paper CSVs, and verification receipts. It does not run
or change the optimization campaign. The original campaign remains read-only.

## Contents and authority

- `scripts/`: byte-preserved export scripts used in the local research workspace.
- `paper_csv/`: published CSVs and per-table source paths, SHA256, and extraction rules.
- `evidence/`: completed export checks and external archive manifest.

The raw archive is external: `IEEE123_B3_2ROUND_MAY2025_RAW_RESULTS.tar.gz`
in `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터`.
It contains 41,762 files, occupies 13,539,656,407 bytes, and has SHA256
`93f233b2e507479df3bf2ac973a8d3db078b26d3b90f6e2b464ce39334254808`.
Recorded verification reopened the gzip/tar, checked every member's SHA, and
verified the published copy. Large raw outputs and invalidated runs are not
included in this Git snapshot.

Numeric authority uses original final coefficients. The two missing historical
sensitivity parquet originals remain explicitly missing; regenerated sensitivity
files are diagnostic only. The corrected campaign retains Round-1 MESS support
in A1(2), with the final accepted computing schedule as incumbent. The earlier
MESS-inactive attempt is not the source of these CSVs.

## Interpretation

| CSV | Data rows | Columns |
|---|---:|---:|
| 01 daily comparison | 31 | 23 |
| 02 second-round stages | 31 | 25 |
| 03 Actual line loading | 2,976 | 12 |
| 04 Actual voltage | 2,976 | 7 |
| 05 MESS trajectory | 11,904 | 15 |
| 06 AIDC trajectory | 35,712 | 9 |
| 07 changed decisions | 44 | 8 |
| 08 aggregates | 19 | 5 |

Electrical time series have 96 native 15-minute slots per day, with AEST
timestamps. No 5-minute values were interpolated. AIDC trajectories represent
stored DA decisions. Unsupported values remain empty. Equality uses absolute
rho tolerance 1e-10 and zero relative tolerance. Daily deltas are 1R minus 2R;
aggregate changes are 2R minus 1R. May25 stage runtime includes completed
M1/A2 work before resume, without adding that work twice to total runtime.
May31 uses the verified selective Actual revision where required.

## Reproduction and validation limits

These are archival scripts, not a standalone installed package. Their original
working directory is
`D:\ChatGPT\Mobile ESS 2\B3_2ROUND_EXTENSION\paper_export_20260917`,
with `production_v4_corrected` in its parent and the original authority trees
at the paths recorded in the manifests. Run only in a separate prepared export
namespace with those inputs available; do not run scripts directly from this
snapshot against absent inputs. Python requires NumPy, pandas and a parquet
engine; CSV authoring requires the bundled JavaScript artifact-tool runtime.
Order: `extract.py`, `build_csv.mjs`, `verify_csv.py`, `archive.py`, `publish.py`.
Publishing refuses an existing destination.

The recorded export validation checks every CSV cell, raw-array extrema,
source hashes (2,172 sources), and archive integrity. Snapshot validation
separately checks copied CSV dimensions and hashes, published manifest hashes,
and Python syntax without executing the export or any solver. Existing receipts
describe the completed export; they are not a claim that production was rerun
for this PR.
