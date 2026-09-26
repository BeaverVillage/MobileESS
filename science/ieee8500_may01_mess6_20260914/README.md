# IEEE8500 May01, six-MESS result snapshot

This package preserves the **2025-05-01** operating day from the September 13–14
six-MESS campaign. B0/B1 reuse its four-hour **MESS-OFF** baseline. B2/B3 use six
vehicles. It is not the older May21/four-MESS case, and does not promote or replace
the subsequent September 18–20 experiments.

The original September 14 CSV/code directory was unavailable when preparing this
PR. The 13 CSVs were rebuilt from the same saved authorities, and their source
hashes were compared with the preserved raw archive. This is a new serialization,
not a claim of byte-identical recovery of the deleted CSV ZIP.

## Recorded results

| Policy | Planning rho | Day-ahead AC rho | Realized AC rho |
|---|---:|---:|---:|
| B0 | 0.854395883574 | 0.854395883574 | 0.853746214779 |
| B1 | 0.851962458825 | 0.851537852426 | 0.852598358653 |
| B2 | 0.836269122533 | 0.839062484363 | 0.844523989510 |
| B3 | 0.831435696166 | 0.841025750732 | 0.842070841018 |

Lower is better. B0 > B1 > B2 > B3 holds for planning and realized AC, **not**
day-ahead AC. The planning B3 reduction relative to B0 is **2.687300799%**.
Planning, day-ahead AC and realized AC are separate quantities, not interchangeable.

All eight stored policy/scope AC validations pass. B3 is accepted as
`PASS_WITH_USER_ACCEPTED_E_MIN_EXCEPTION`: MESS06 is at **439.9986868076838 kWh**
in slots 32–40, **0.0013131923162177372 kWh** below the 440 kWh operating floor.
Its AC pass does not imply compliance with that original operating floor.
`B3_OPERATING_ENERGY_EXCEPTION.csv` retains all nine rows, and check C15 is FAIL.

## Files and definitions

The `paper_csv` directory contains case authority, policy summary, runtime,
AC feasibility, six-MESS B2 stage timings, realized and day-ahead time series,
same-time B0/B3 heatmap and summary, flexibility actions, the B3 energy exception,
paper key values, validation checks, and a source/output SHA256 manifest.

The `timeseries_heatmap` directory contains a separate archive-direct extraction
of B0 and B3 realized-operation line loading for all 96 May-1 slots. It includes
the long policy/slot/physical-line table, daily maxima, B0-ranked common stress
windows, loading-duration summaries, source-member audit, manifest, and the exact
read-only extraction script. Values below 0.40 and signed B0-minus-B3 differences
are retained without clipping. The extraction is marked `PARTIAL` because the raw
archive contains only the 36-bus PCC coordinate overlay, not the base-feeder
coordinate or disabled-line inventory authorities; unavailable fields remain
blank and the disabled count remains unknown.

* `rho` is maximum recorded line terminal-phase current divided by original
  line NormAmps. Transformer current and winding-kVA gates remain separate.
* The heatmap uses **realized AC at B0's peak, 2025-05-01 18:15**, held fixed for
  B3. B0 is 0.8537462147791017; B3 at that same time is 0.838356609744188;
  the relative reduction is **1.8025971616%**. B3's own daily peak is not used.
* Heatmap data have 16,089 recorded terminal-phase rows plus five explicit NA
  rows for disabled switches: all 4,929 line/transformer elements. Native
  schematic and remapped PCC coordinates are copied from saved inputs.
  Terminal/node labels are preserved; secondary node1 is not assumed phase A.
* Case `branch_count=4915` means unique undirected line/transformer bus pairs,
  including disabled lines and excluding reactors. It is not a full energized
  graph edge count. There are 4,912 named buses and 8,639 non-ground nodes.
* B0 planning comes from the recorded no-optional-move reference seed audit
  inside B1. B2 uses **restored final** P1, not the lower failed-primary value.
* B1 runtime is measured search-process duration only. B0/B2/B3 end-to-end
  runtimes are **NA** because no single authoritative total is recorded.
  B3's component sum includes B1 reuse, M1, final A1 search and MF; it is not a
  total across setup, interruptions, prior attempts or final postprocessing.
* The final AIDC search deadline is **14,400 seconds**, not a whole-B3 cap.
  Feasible incumbents are not global optima. Global gaps/bounds remain NA.
* B2 MESS stage times sum recorded screening, restricted optimization and full
  MILP wall times; restoration/final AC are excluded.
* Flexibility job deltas and relocations are day-ahead decisions. Power/energy
  use realized actuators; positive P discharges, energy integrates 0.25-hour
  intervals. Max P/Q is per vehicle. `final_soc_*_kwh` are battery energy, not
  fractions; MESS-OFF baseline battery outcomes are NA.
* Missing data remain NA. AC tolerance is 1e-9 pu; B2's approximately 6.4e-12 pu
  numerical voltage overshoot retains the stored pass. DA violation counts
  count slots; realized counts use saved category occurrences.

See [EXTRACTION_AUDIT.md](EXTRACTION_AUDIT.md) for verification and archive scope.

## Verify without raw data

From the repository root (Python 3.11+; standard library only):

```sh
python tools/ieee8500_may01/verify_results.py science/ieee8500_may01_mess6_20260914/paper_csv
python -m unittest discover -s tests -p test_ieee8500_may01_package.py -v
```

## Rebuild from local original files

The exporter needs Python 3.11+ and numpy. It imports no project models and runs
no optimization, OpenDSS, AC replay or ML inference. Output must be a new/empty
directory. Either use the original workspace, or safely unpack the trusted raw
archive to a separate directory retaining its member paths.

```sh
python tools/ieee8500_may01/export_results.py --source-root /path/to/raw-root --archive-index /path/to/archive_INDEX.json --output-dir /path/to/new-csv
python tools/ieee8500_may01/verify_results.py /path/to/new-csv
python tools/ieee8500_may01/verify_archive.py --archive /path/to/raw.tar.gz --package /path/to/new-csv --output /path/to/archive-verification.json
```

The **12.67 GB raw archive stays local**. Git contains CSVs, code, source hashes,
small final evidence and verification receipts. The archive is a results snapshot,
not a self-contained execution environment; externally referenced coefficient
binaries and runtime dependencies are not duplicated wholesale.

**SCIENTIFIC_EXECUTION_COUNT = 0** for this extraction and PR preparation.
