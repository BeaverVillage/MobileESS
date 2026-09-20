# IEEE8500 May01 six-MESS Actual and monitoring snapshot

This package preserves the September 13–14 May01 campaign discussed in this task.
The original B3 Actual replay stopped when MESS06 reached 439.9986868076838 kWh
after travel. The user explicitly authorized continuing below the 440 kWh
operating floor. The separate replay completed with AC feasibility and independent
96-slot replay verification, while retaining the failed original and recording
`PASS_WITH_USER_ACCEPTED_E_MIN_EXCEPTION` rather than claiming 440 kWh compliance.

This is a source/evidence snapshot with original absolute paths and external
dependencies, not a portable production launcher. Nothing here activates the
exception globally. Historical campaign launchers and superseded diagnostics are
provenance; do not run them from this package. The accepted continuation entry
point was `b3_actual_energy_continue.py`, launched by its separate supervisor.
Later September 15–20 resiting/scaling campaigns are outside this package.

## Preserved results

Maximum phase-line loading, pu:

| Policy | DA exact AC | Actual exact AC | Actual QSAFE slots |
| --- | ---: | ---: | ---: |
| B0 | 0.854395883574 | 0.853746214779 | 0 |
| B1 | 0.851537852426 | 0.852598358653 | 0 |
| B2 (6 MESS) | 0.839062484363 | 0.844523989510 | 4 |
| B3 (6 MESS, energy exception) | 0.841025750732 | 0.842070841018 | 0 |

All four stored Actual authorities report 96 converged/control-settled slots,
AC feasibility, independent replay PASS and zero unresolved QSAFE slots. B3's
Actual AC replay took 1211.981 s; the separate supervisor interval was 1250.956 s.
These are recorded historical results, not simulations rerun for this PR.

B3 MESS06 has nine below-floor slots (32–40, zero-based), shortfall
0.0013131923162177372 kWh. The exception leaves actual energy unclipped, keeps
the 0–1080 kWh physical check and the existing 440 kWh discharge saturation
floor, and retains DA P/Q command clocks, mobility availability and QSAFE Q-only
semantics. It does not establish feasibility against the original 440 kWh lower
bound. The preserved preflight records 18 above-floor equivalence cases and all
576 vehicle-slot replay rows.

## Implementation and authority

- Six vehicles share the original per-vehicle ratings. Initial locations are
  MESS01–06 = STA01, STA12, STA08, STA06, STA03, STA10; initial energy totals
  4560 kWh. `PRODUCTION_AUTHORIZATION.json` follows the earlier preflight-only
  `FLEET_AUTHORITY.json`; its earlier `production_optimization_authorized=false`
  field is preserved as historical evidence.
- QSAFE groups the unchanged discrete Q-deviation metric into shells, evaluates
  the complete first feasible shell using legacy chronological exact AC, then
  applies the existing deterministic tie-break. The 5000-candidate cap is absent;
  local refinement is separate and final correction is independently replayed.
  The same core SHA serves IEEE123 (4 vehicles) and IEEE8500 (6 vehicles).
  IEEE123 material is the port/preflight, not an IEEE123 production rerun.
- `evidence/rejected_checkpoint` records the failed numerical-equivalence gate.
  That checkpoint evaluator is excluded from production; the accepted path uses
  full chronological OpenDSS replay and native automatic tap/cap controls.
- A1's clock is continuous 14400 s, cumulative deadlines 7200/11040/12480/13440/
  14400 s, no pause. Its final planning P1 is 0.831435696166192 with zero incumbent
  updates. This is distinct from DA/Actual exact-AC maxima and is not a global
  optimality claim.
- The read-only monitor distinguishes completed A1/MF from Actual progress,
  prioritizes the authorized new namespace over historical failures, and labels
  the operating-floor exception. Its live files were subsequently repurposed
  for another campaign. This package uses the preserved pre-repurpose copy;
  both hashes exactly match the September 14 `MONITOR_VERIFICATION.json`.

## Contents and validation

`SOURCE_COPY_MANIFEST.json` gives original source/backup paths, roles, byte counts
and SHA256 for every copied file. `.gitattributes` preserves archival bytes.
`evidence/campaign/RESULT_WITH_ENERGY_EXCEPTION.json` is the final comparison;
`evidence/actual_B3/USER_ACCEPTED_COMPLETE.json` is the explicit B3 acceptance.
Earlier failures remain historical, not current result authorities. Large raw
trial directories, traffic caches, coefficients and replay arrays remain in the
original external workspaces; this package does not claim to contain them all.

From repository root (Python with numpy, scipy and psutil):

```powershell
python -B science/ieee8500_may01_mess6_20260914/verify_snapshot.py
python -B science/ieee8500_may01_mess6_20260914/frozen_code/qsafe/test_shell.py
```

The archive verifier checks copied hashes/syntax, four final Actual authorities,
source-certificate linkage, energy exception, fleet/clock, shared core and monitor
completion with an old failure present. Six QSAFE tests check full 4/6-vehicle
domains (625/15625), complete-shell selection, deterministic parallel ordering,
disconnected axes, separate refinement and no 5000-candidate truncation. Neither
command invokes scheduling, OpenDSS, SUMO or ML. Stored physical preflight and
AC certificates are inspected, not recomputed.

Stacked on PR #48, retaining #45/#42 provenance. Existing frozen files and the
currently running/visible campaigns were not modified during packaging.
