# CODEX Day-Ahead AIDC Joint Implementation Report

## Outcome

Implementation stopped at the mandatory C2 scientific gate. The source audit is complete enough to establish that the only observed NLR ESIF IT-power series ends at `2025-08-29 04:35:08.461000`, before the frozen September-October validation and November-December locked evaluation windows. Its supplied README also does not state the timezone semantics of `ts`. P/G/W do not share one proven source-system/time-axis identity. Creating a synthetic P target, row-wise joining independent traces, or silently reducing the model is prohibited.

## Authority and source

- Branch: `codex/dayahead-aidc-joint-v1`
- Parent / PR #9 HEAD: `94b6d320d524ea6ef76ba324f91cb820e8e48004`
- Scientific framework: `V15_DA_AIDC_ICPS`
- Raw root: `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터` (read-only)
- Full inventory: 385 files, 56157210220 bytes, SHA-256 complete
- Kestrel: 10559977 rows in 29 Parquet members
- ESIF PUE/IT power: 4569543 rows, observed span `2015-11-10 03:00:01` to `2025-08-29 04:35:08.461000`

## Implemented scope

- Frozen authority IDs and mapping digest contracts
- Fixed-AEST D-1 18:00 cutoff and exact 96-slot axis
- Energy-preserving AEMO 30-to-15 hold, realized 5-to-15 mean, and mobility-energy 5-to-15 sum
- Complete-product latest-vintage selection without per-slot mixing
- Read-only full raw inventory/hash and key Parquet/ZIP metadata audit
- P/G/W label-origin, dependency, source-system, time-axis, and coverage firewall
- Split/seed/calibration contract definition without activating training

## Changed files

- `dayahead/__init__.py`
- `dayahead/authority.py`
- `dayahead/input_contract.py`
- `dayahead/aidc_preflight.py`
- `dayahead/aidc_labels.py`
- `dayahead/cli.py`
- `dayahead/materialize_precode_gate.py`
- `dayahead/finalize_precode_artifacts.py`
- `tests/dayahead/test_authority.py`
- `tests/dayahead/test_input_contract.py`
- `tests/dayahead/test_label_gate.py`
- `tests/dayahead/test_preflight.py`
- `dayahead/artifacts/precode/*` (C0-C2 evidence and blocked downstream reports)

## Scientific invariants preserved

- No historical result bytes were relabelled.
- No synthetic label or future job ID was created.
- No row-wise cross-dataset temporal fabrication was performed.
- No November/December training, tuning, optimization, or evaluation was started.
- No reduced-target model was selected by Codex.
- Solver calls: 0; OpenDSS calls: 0.

## Blocking evidence

- `FAIL_AIDC_P_LABEL`: observed IT-power coverage ends before the frozen validation/evaluation windows, and the supplied PUE README does not resolve the `ts` timezone.
- `FAIL_AIDC_JOINT_LABEL_ALIGNMENT`: P uses NLR ESIF PUE while G/W use NLR Kestrel Slurm, with no source-backed identity proving one synchronized operational target axis.
- Required action: create a prospective scientific re-freeze with a source-backed aligned P/G/W authority, or explicitly approve a reduced-target contract under a new authority ID.

## Known limitations

C4-C12 were intentionally not executed because the frozen handoff requires C2 PASS before the proposed model and downstream optimization evidence. The existing historical rolling-control implementation remains unchanged.
