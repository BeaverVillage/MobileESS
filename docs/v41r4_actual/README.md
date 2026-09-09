# V41R4 Actual: eta95, robust Q-only control, and exact-state acceleration

Actual now freezes the Day-Ahead discrete decisions and active-power schedules while permitting causal, connected-MESS Q-only corrective AC-feasibility control. This PR archives the implementation used by the running campaign, its frozen scientific rules, the performance implementation, and the supporting evidence. It also updates the live monitor to distinguish DA stages, versioned Actual work, and the reduced acceleration audit.

This is a follow-up to PR #39. It does not alter or rerun Day-Ahead/Fresh optimization. The campaign checkout and original/partial Actual outputs remain untouched by the PR preparation. Large inputs, model files, trial logs, and full day arrays remain in the original local artifact namespaces.

## Scientific execution contract

- Shared charge/discharge efficiency: 0.95, checked against the DA electrical authority and used by the physical actuator and independent audit.
- Fixed AIDC schedule/placement/migration, MESS route/destination/departure/executed location, and executed active power. Only connected MESS Q can change.
- Test the physical frozen DA Q first. Intervene only on exact AC hard-limit failure; no preventive voltage margin.
- Preserve 0.95–1.05 pu, line loading, transformer phase-current and transformer kVA limits, with the frozen comparison tolerance. Preserve 300 kW, 400 kVA, the 16-face inner PCS polygon and exact norm audit.
- Deterministic full-domain screening, multistart, progressive/local refinement, candidate order, stopping rules and objective are frozen in `METHOD_FREEZE.json`. The objective is the squared deviation from the **raw frozen DA Q command**, not a newly chosen reference.
- Select the minimum-deviation feasible correction found by the prescribed deterministic search. No global-minimum claim. Failure remains `ROBUST_Q_ONLY_UNRESOLVED`; no P fallback.
- Every candidate starts from the same approved native slot-start state. Only the selected solution's final native state propagates.

The scientific method SHA is `710a50cd439a9bb42cc8e6ea77b47eb1a5536c37cef894456a0859aeae9db368`. The archived scientific sources retain their original bytes and binding hashes.

## Performance implementation

`cached_engine.py` restores seven regulator taps, fixed capacitor states, solver/control settings, empty native queue state, current realized inputs and fixed P/location, and the native voltage/current warm-start vectors. It reuses one compiled engine across Q trials and carries the approved state sequentially between slots. Unsupported restoration cannot silently start heavy production prefix replay: the performance entry point fails closed.

Tap restoration alone was insufficient: all 55 comparisons did **not** pass bit/numerical equality. The full visible state plus native warm-start vectors passed all 55 comparisons, as did reusable-engine and reversed-candidate-order trials. The completed May12 B3 slot30 robust search also matched all 4,558 evaluated candidates in order and exact result hashes, including selected Q. Its search time was 896.812 s with the old prefix engine and 44.215 s with reuse, a measured 20.28x improvement for that slot.

These measurements are not a full-day runtime claim. Most cost comes from thousands of Q candidates at intervention slots, not from visiting 96 timestamps once.

## Current acceptance scope

The user superseded the three-day audit and then explicitly approved a smaller gate:

1. Run the unchanged lightweight robust search once across May12 B3's 96 sequential slots.
2. Evaluate only its selected 96 Q vectors using the old clean-engine/full-prefix implementation.
3. Require exact selected-point voltage/current/transformer arrays, regulator start/final taps and final violation counts, with fixed P and unchanged SoC/energy.

This gate **does not prove that an independent old full-day search would choose the same Q at every slot**. The previous candidate/order comparisons are supporting evidence; they are not described as a complete all-day proof. The cancelled exhaustive May01/May02/May12 audit outputs and hashes remain historical local evidence.

The reduced gate passed all 96 selected points. Lightweight search took **922.187 s (15 min 22 s)** for 104,352 candidate evaluations; the old selected-point validation took **14.077 s**. There were 48 intervention slots, zero unresolved slots, and peak lightweight working set was 0.357 GB. The implementation was sealed as `PERFORMANCE_ONLY_EXACT_EQUIVALENT_ACCELERATION_PASS` with the reduced scope recorded and handed off to `v41r4_actual_eta95_qsafe_robust_v2_perf1`. The existing two DA/Fresh workers were adopted and two Actual workers started from May01/May02. `CAPTURE_STATUS.json` records this running state. No complete-May physical-feasibility result is claimed.

## Resource and output preservation

The current allocation is **four total day workers**, following chronological date/policy DA/Fresh then its Actual. There is no global Actual-first priority. The earlier 2+2 allocation and subsequent temporary Actual8 + DA2 burst are historical resource configurations. `CAPTURE_STATUS.json` is the initial deployment snapshot, not the current resource setting.

The burst exit condition originally counted pending Actual policies on dates occupied by DA workers. Date-exclusive scheduling prevented these units from being dispatched, leaving burst reservations idle. The operational adapter now distinguishes dispatchable backlog from pending units on occupied dates. It returns to normal4 when dispatchable backlog and active Actual both drain, and normal4 remains sticky when later DA results generate new Actual work. The missed transition was applied without preempting any day worker; four retained workers completed normally and four subsequent live workers were verified.

`evidence/resource_restore/` records the deployed adapter authority, restoration receipt, regression checks and process verification. The adapter has a separate operational SHA; scientific and performance seals are unchanged. The monitor displays the active common cap and normal pipeline mode. Synchronous report publication and date scanning can still delay backfill; this correction does not claim to remove those delays.

B0/B1 use the common Actual binding and require exact historical regression verification when an original Actual result exists. B2/B3 preserve original Actual, eta95 baseline and Q-corrected trajectories separately. Versioned reports distinguish the 17 development dates (May01–16, May18), 14 holdout dates, and 31-day total with explicit completed-pair denominators. P/SoC identity, interventions, unresolved slots, PCS use, violations and runtime are included.

## Source layout and review boundary

`tools/v41r4_actual_snapshot/robust_v2/` is a **byte-preserved review archive**, not an importable installation or a clean-clone campaign launcher. Relative namespace assumptions and absolute authority paths intentionally retain their live meanings. Do not execute the archived operational entry points from this directory. They require the retained DA/Fresh artifacts, frozen electrical inputs, native OpenDSS environment and active campaign coordinator that exist in the original workspace. The snapshot does not package those large external dependencies or claim to reproduce the whole experiment from a clean clone.

- `binding.py`, `actual_worker.py`, `input_adapter.py`, `robust_search.py`, and `frozen_code/`: scientific/physical execution and audit authority.
- `acceleration_audit/cached_engine.py`: exact-state/reusable-engine implementation.
- `selected_q_gate.py`, `close_selected_q_gate.py`: the currently authorized reduced acceptance gate.
- `adopt_lightweight.py`, `performance_worker_template.py`: conditional new-namespace sealing and coordinator-only handoff.
- `state_regression.py` and `full_equivalence.py`: historical regression source corresponding to completed evidence; they are not scheduled again.
- `dispatcher.py`, `report_candidate.py`: shared resource allocation and separated cohort reporting.
- `../perf1_overlay/` within the snapshot: deployed performance worker, dispatcher/report overlays and final implementation seals. The remaining code is byte-identical to the base snapshot.
- `SOURCE_SNAPSHOT.json`: original paths, copied paths, sizes and SHA256 values.

Run the data-free snapshot and resource-policy checks in a PR checkout:

```powershell
python tools/v41r4_actual_snapshot/verify_snapshot.py
python tools/v41r4_actual_snapshot/test_resource_policy.py
```

It checks copied bytes, scientific bindings, evidence scope, syntax and the frozen PCS Q-interval endpoints/maximality/disconnection/active-rating contract. It invokes neither OpenDSS nor campaign workers. Live physics evidence is preserved separately under `evidence/`; monitoring render verification is recorded in `VALIDATION.json`.
