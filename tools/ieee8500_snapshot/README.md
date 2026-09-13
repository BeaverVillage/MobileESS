# IEEE8500 conversation work: complete provenance coverage

This PR extends the final May21 package in `science/ieee8500_2025_05_21` (PR #45). Together they preserve the work performed in this conversation without changing the original V41R4 or IEEE8500 runtime, decisions, frozen artifacts, or acceptance rules.

## Coverage

`SOURCE_COPY_MANIFEST.json` accounts for all 193 authored code/document files found in the original 26 IEEE8500 workspaces, excluding unmodified canonical source, third-party plot libraries, runtime scratch files, and bytecode. Each is either SHA-identical to a file already in PR #45 or included here. This includes source/topology selection, PCC construction, failed and accepted compatibility stages, binding reconstruction, coefficient generation, policy orchestration, physical restoration, monitoring, Actual replay, and historical failed implementations. The complete raw archive's 23,709-file manifest preserves the remaining raw evidence.

Additional snapshots cover the May06 independent screening, IEEE123 read-only mobility regression, and the export orchestration/probes omitted from the base package. All copies retain source bytes; historical `AGENTS.md` files use the suffix `.source` so that archival instructions cannot govern unrelated future work.

These are **provenance snapshots, not a portable execution release**. They retain absolute paths and external dependencies. Do not import or execute the historical source tree as a test suite: it includes superseded, stopped, diagnostic-only and explicitly rejected implementations. In particular, the temporary B2 selection-order experiment remains development-only; it was not applied to production. Accepted B2 uses the frozen physical-restoration sequence. Original B1/A1 P1–P5 and acceptance semantics are unchanged.

## Final May21 results

| Policy | Planning P1 | Day-Ahead exact AC max line | Actual exact AC max line |
|---|---:|---:|---:|
| B0 | 0.8487691403696187 | 0.8487691403696187 | 0.9187894369215509 |
| B1 | 0.8473104038318897 | 0.8488178297477951 | 0.9249467613822655 |
| B2 | 0.8284125998911473 | 0.8355810352862253 | 0.9076065509538066 |
| B3 | 0.82573859707742 | 0.8366269795479181 | 0.9029293071261447 |

All final policies pass their stored exact AC acceptance. B2 Actual completed with one QSAFE intervention, zero necessary departure shifts, zero missed nonzero commands, and unchanged executed P. The base package contains the 96-slot independent replay and battery/identity evidence.

B1's lower planning P1 does not establish lower exact AC loading. Its Actual maximum is at the same line and slot as B0, with a different VREG2_C tap and lower local voltage. This is consistent with a regulator-response contribution; no counterfactual isolation of that contribution was performed. The existing AC validator checks physical feasibility, not exact-AC dominance over B0. This PR does not add such a gate or alter selection order.

## May06 screening: stopped at the B0 gate

The independent May06 run used source1.0400pu, all Vreg123.5V, CAPBank3 OFF, unchanged topology/PCC/ratings and AIDC scale1.00. PV was fixed at the May06 alpha0.50 reference capacity while native load P/Q varied. The comparison scope was provisionally Day-Ahead exact AC; the original optional scope/PV questions and assumptions were documented before execution.

| alpha_BG | B0 max line(pu) | Vmin | Vmax | Feasible |
|---|---:|---:|---:|---|
| 0.60 | 1.0280968500480012 | 0.9500111710989994 | 1.0413685919570337 | no |
| 0.65 | 1.117175003494293 | 0.9477941600932298 | 1.041288348866128 | no |
| 0.70 | 1.2028435921372138 | 0.9349333380382778 | 1.041364486196248 | no |

All 288 slots converged and controls settled. No feasible alpha was selected; AIDC scale enlargement and B1/B2/B3 were not run. The requested ordering was not achieved or claimed. No further parameter tuning occurred. This is outcome-conditioned exploratory screening, not confirmatory evidence of general policy superiority.

## Raw archives and verification

- `MAY21_FULL_RAW_INDEX.json` and `MAY21_FULL_RAW_FILE_MANIFEST.json` identify the complete original archive (SHA256 `9c5519cd182c803b75c305267ed44d617d696f8a8f7c91614897bd52e30ada6e`). The 26.4GB archive is external, not stored in Git.
- `MAY06_EXTERNAL_ARCHIVE.json` binds the separately created full May06 raw archive, its complete source manifest, decompressed readback verification and unchanged source SHA/size/mtime.
- The 11 CSVs, compact upload ZIP, extraction audit and completed export verification are in the base PR. Their extraction scientific execution count is zero; this is distinct from the previously executed simulations.
- `verify_snapshot.py` checks every copied byte, base-PR coverage, and the saved May06 stop gate without invoking OpenDSS, SUMO, optimization, or ML.

Run from the repository root:

```console
python -B tools/ieee8500_snapshot/verify_snapshot.py
python -B science/ieee8500_2025_05_21/verify_evidence.py
```

No existing production source or result is modified. No new scientific run is performed by this PR preparation or its verification commands.
