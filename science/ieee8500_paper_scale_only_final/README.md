# IEEE8500 final paper-PCC scale-only campaign

This is a reviewable snapshot of the completed 2025-05-01 research campaign,
its implementation repairs, verified paper exports, and external raw archive.
It does not promote the earlier `legal_mixed_M1` or subsequent re-siting cases.

## Final authority

- BG scale **0.552**; AIDC absolute scale **2.40**, applied as `2.40 / 2.00`
  to arrays already stored at absolute scale 2.00.
- Six MESS vehicles, each **600 kW / 800 kVA / 2400 kWh**.
- Original paper feeder, PCC/overlay, ratings, traffic, jobs/WAN and controller.
- Production order: B0, B2, B1, B3; each policy followed by Actual.
- B3 independently completed A1 → M1 → A2 → M2. B1/B2 results are not B3 results.
- One worker, four threads; each AIDC search received 14,400 seconds.
- The user's later **paper termination restoration** supersedes earlier requests
  for unlimited MESS solves: 600 seconds per optimize, WorkLimit tiers 60/180/300,
  MIPGap target 0.001, and original feasible-incumbent/quality-bound acceptance.
  A target gap is not a claim of a global 0.1% proof on every restricted solve.
- Full separation and final 96-slot exact AC validation remain mandatory.

| Policy | Planning rho | DA exact | Fresh | Actual |
|---|---:|---:|---:|---:|
| B0 | 0.946912268 | 0.946912268 | 0.946912268 | 0.944061254 |
| B1 | 0.945892078 | 0.945894690 | 0.945894690 | 0.943463580 |
| B2 | 0.928071819 | 0.930048418 | 0.930048418 | 0.933177577 |
| B3 | 0.924155151 | 0.926287579 | 0.926287579 | 0.930493346 |

All final DA/Fresh/Actual hard AC checks pass. Actual B0–B3 reduction is
**0.013567908 pu = 1.3567908 percentage points**. The larger 5–10 percentage-point
screening aspiration was not achieved. No policy ordering constraint was added.
The original-scale regression independently reproduces DA 0.8543958835735742 and
Actual 0.8537462147791017; those are different evaluation scopes.

Use [the verified report](evidence/FINAL_VERIFIED_REPORT_20260923.md) and
[scoped review](evidence/FINAL_REVIEW_20260923.json) for reporting. The preserved
original report's B2 `runtime_seconds=308.252...` covers only the last restoration
attempt, not total B2 execution. Its recorded start-to-DA-complete calendar interval
is 51,450.218 seconds, including interruptions, repairs and waiting.

## Implementation and evidence

`campaign_source/` preserves the campaign's Python implementation and monitor.
`screening_source/` preserves the earlier forensics, scale screening and regression
tools. These are **historical source snapshots**, not installed entry points.
They retain original absolute paths and imports from the frozen research runtime.
Do not execute launch/recovery scripts in a new checkout without restoring their
dependencies, paths, solver license and archived data.

The adopted fixes include compact active electrical rows with full separation,
coefficient/state reuse, original parent-candidate quality guards, fixed-route DA
physical feasibility restoration, SHA-verified missing evidence bindings, scaled
SOC audit bounds, and exact-equivalent Actual metadata/native-input acceleration.
The original Actual controller keeps executed actuator P and uses Q correction
only for hard AC violations. No Actual P optimization was introduced.

**Rejected and superseded code is retained for provenance.** In particular,
`actual_batch_inputs.py` and its debug/benchmark variants failed numerical parity
and are not adopted. Earlier no-cutoff launch/audit scripts do not supersede
`evidence/PAPER_SOLVER_TERMINATION_AUTHORITY.json`. Native-input parity evidence is
under `evidence/actual_native_preflight/`. Source snapshots must not be interpreted
as a list of commands to rerun.

44 original sparse separation certificates are included. Each records checking
31,945,536 logical rows against its recorded tolerance, without a hard active-row
cap or route pruning. Additional raw diagnostics remain in the external archive.

## Paper CSV and archive

`paper_csv/` contains the compact final policy table, reductions, 96-slot system
rho, export validation and full CSV manifest. The large line-by-time heatmap CSVs
remain in the separately delivered CSV folder/ZIP identified by the manifest.
All heatmaps use **Actual** arrays: 3,698 lines × 96 slots, with 12,312 underlying
phase/terminal axes. B0/B1/B2 reach their Actual maxima at slot 73 (18:15), and B3
at slot 78 (19:30). Common-time comparisons use B0's critical time. Timestamps are
simulation local clock; no UTC offset is invented.

`export_tools/` preserves the CSV extraction and raw archive creation scripts.
They write new output namespaces and do not run scientific optimization.

Raw archive (not committed):

`IEEE8500_FINAL_MAY01_BG0552_AIDC240_MESS200_RAW_20260923_144908.tar.gz`

- 18,532,150,287 bytes; 32,243 source files plus an embedded manifest.
- SHA-256: `872e1b68a8e873f0eae415da0be3bc6dd689e8257b6c9af696f0a97a291fc776`.
- Contains the full final campaign, diagnostic attempts, native feeder source and
  top-level paper authority. All archived file contents matched source hashes.
- `archive/` records its local location, checksum, verification, and external
  full-index hash. It is not a self-contained installed execution environment.

`SOURCE_INVENTORY.json` hashes every copied source/evidence file; 262 files were
also checked against the raw archive's original member hashes when assembling this
PR. Historical path/SHA references inside evidence remain unchanged, even where
they refer to an earlier repair-stage snapshot.

## Offline review

From the repository root:

```console
python -m unittest discover -s tests -p "test_ieee8500_paper_scale_final.py" -v
git diff --check
```

These checks validate snapshot integrity, scientific scope consistency, final
AC/completion evidence, separation certificates and archive/CSV provenance. They
do not rerun OpenDSS or Gurobi and do not establish new optimization results.
