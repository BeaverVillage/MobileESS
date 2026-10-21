# V2_add PR236 correction and S0/S1 evidence

This directory supersedes the interpretation of the preserved earlier V2_add
reports. It does not replace their input files, runtime archives or receipts.
The experiment remains **V2_add** on the same Draft PR236.

Read `FINAL_V2_ADD_CORRECTION_REVIEW_KO.md`,
`FINAL_V2_ADD_GO_NO_GO.json` and `SELECTED_SCENARIO_FREEZE.json` first.

## Measurement scopes

- `RECALCULATED_*`: independent parent-terminal arithmetic over the56 original
  STATIC B0/pilot/Fresh archives, without a new operating solve.
- `canonical/`: current r043-compatible TIME objective. Select the **last native
  solved state per slot**, then take the evaluation96 parent-terminal maximum.
  NormalAmps and all original MV/LV/Triplex lines are retained.
- Root TIME result CSVs produced before this projection are preserved
  **intermediate all-event security envelopes**. They are not the current V44
  objective. `CURRENT_MEASUREMENT_CONTRACT.json` is authoritative.
- `svr/`: S0 original12 controls and S1 additional3/6/12 three-phase banks,
  with the same settled96 objective plus explicit evaluation-event and
  Prefix24/all120 safety. `physics_PASS` in the canonical/SVR summaries means
  settled evaluation96; the other safety columns must also be read.
- A Fresh PASS certifies reproducibility, not physical feasibility. Failed
  physical cases and their independent Fresh are intentionally retained.

`correction_current.CanonicalTimePhysical` is the current measurement API.
`correction.CorrectedPhysical` remains the SHA-bound archival event producer;
its aggregate row is an event envelope. The projection and current API correct
that timing distinction without rewriting historical evidence.

## Additional hardware

`svr/S0_DIAGNOSIS_SEAL.json` was written before S1 operating AC. Candidate
contracts and numeric/physical assumptions were frozen there. The IEEE8500
identifier/implicit-phase syntax amendments retain their initial rejected
installer receipts and do not change any electrical parameter.

The original line terminal1 is split through three finite single-phase
transformers. All other line properties, enabled states and ratings remain
identical. The independent model snapshot includes both complete property
sets, every original/new connection, transformer ratings, PV roster, and live
scalar-versus-bulk current comparison after PDE reindexing.

Legacy source field labels containing `original_seven` are provenance labels.
Their values cover all12 IEEE8500 originals; see
`svr/INHERITED_COUNT_LABEL_SCOPE.json`. No IEEE1237/43 count is forced here.

Full event tap readbacks are in `svr/ALL_EVENT_TAP_NUMBER_READBACK.csv.gz`
(lossless CSV gzip). Native queue entries, action ordering, complete properties,
all node/line/transformer arrays and dispatch/physical-input identities remain
in the per-case Raw archives referenced by receipts.

The original12 RegControls and9 CapControls had EventLog=No. Full within-native-
timestamp action ordering is supplemented by logging-only beta2 S0/S1_03
anchors, not claimed for all40 original cases. The accepted anchors are
bit-identical in physical arrays/states to their logged-off originals. The
first S1 attempt edited logging after initialization and failed strict bitwise
equivalence by a maximum line-rho1.68234e-9; it is retained as a failure. The
accepted S1 trace enabled logging before installation/initialization. Queue
time/handle sorting is not substituted for the native execution order.

## Finite control witnesses

The original temporal and slow-charge schedules retain their preregistrations.
`PEAK31_DIAGNOSTIC_PREREGISTRATION.json` explicitly follows the observed B0
peak31; it is not backdated into the original registration. The S1_03 beta2
pilot has its own post-B0 preregistration. Neither is an optimizer or a scenario
selection rule. Every dispatch preserves the original8 initial sites, original
STAY routes, SOC/PCS/P/Q limits, initial/terminal760 and complete rebound.

Source QoS, relaxed research-policy compliance, causal Actual AIDC commands,
instantaneous electrical sensitivity, finite SOC-feasible operation and B3
optimization are separate claims. See the AIDC report and per-UID audits.

## Reproduction

Use the existing isolated `../V2_add_runtime/.venv/Scripts/python.exe` and the
preserved `V2_add_runtime` evidence. No production worker or optimizer is
imported or invoked. The supported stage entry validates all148 frozen prior
tracked inputs/configuration/evidence files before and after reuse:

```powershell
& '..\V2_add_runtime\.venv\Scripts\python.exe' -m v2_add_preflight.correction_entry audit
& '..\V2_add_runtime\.venv\Scripts\python.exe' -m v2_add_preflight.correction_projection
& '..\V2_add_runtime\.venv\Scripts\python.exe' -m v2_add_preflight.correction_verify
& '..\V2_add_runtime\.venv\Scripts\python.exe' -m v2_add_preflight.correction_svr_results
& '..\V2_add_runtime\.venv\Scripts\python.exe' -m v2_add_preflight.correction_svr_verify
& '..\V2_add_runtime\.venv\Scripts\python.exe' -m v2_add_preflight.correction_report
```

Full operating replay stages are `anchors`, `legacy_remaining`, `extension`,
`legacy_pilots`, `temporal`, `charge_spread`, `peak31`, and
`svr S0|S1_03|S1_06|S1_12` through `correction_entry`.
The additional S1 finite pilot, model snapshot, fixed loss probes and local
sensitivities have correspondingly named modules. Completed matching receipts
are reused only after scientific-input and artifact SHA checks. Do not change
frozen preregistrations or source code and reuse the old receipts as current.

All campaign AC processes run below normal priority on reserved logical CPUs.
At most two long screening AC processes were run concurrently; the last beta2.1
S1_12 pair used an independent reserved CPU and was reused by the ordered driver.
Short verification/probe solves are recorded separately. Existing production
workers, held locks and Native optimization resources were preserved.

Native **optimization** calls are zero. OpenDSS operating solves, preparation
solves and the short independent validation probes are distinct and are not
described as zero. This work does not authorize G4 long Native execution.
