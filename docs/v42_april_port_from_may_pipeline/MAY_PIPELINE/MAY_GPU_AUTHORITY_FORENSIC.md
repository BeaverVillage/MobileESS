# May GPU authority construction audit

Base: PR #121 exact head `c0783fadbbca282f2ce580c45fe82feaed71584c`. This audit restores the May construction code and provenance as an April blueprint. It does not read May job payloads, copy May quantities to April, read May scientific outcomes, or run May/April science. All source and artifact SHA256 values are in [MAY_GPU_AUTHORITY_AUDIT.json](MAY_GPU_AUTHORITY_AUDIT.json).

The source rule is a direct request-field copy. It does not contain an additional GPU recovery formula. The current frozen Q50 stage changes service duration while inheriting the previously bound physical GPU gang. Historical missing-GPU exclusion is superseded by `RETAIN_FAIL_CLOSED` for April.

## Eight authority questions

### 1. Where did May GPU_gang / requested GPU originate?

Direct raw Kestrel gpus_requested, copied into the V37 job ledger and temporal schedule, then frozen requested_GPU, COMMON_B0_REFERENCE_JOBS requested_GPU, May native known_population GPU_gang, current-Q50 native inherited GPU_gang, and canonical Job.gpu. Current-Q50 inference replaces service duration without recomputing the physical GPU quantity.

Evidence: `dayahead/v37/aidc_materializer.py:461`, `dayahead/v40d_actual/inputs.py:74`, `dayahead/v41/common.py:59`, `dayahead/v41/common.py:84`, `v42_may01/prepare.py:87`, `v42_final/native_inputs.py:40`, `v42_final/native.py:13`, `v42_temporal/native.py:45`.

### 2. Was raw Kestrel gpus_requested used directly?

Yes at the upstream V37 construction boundary: float(raw[gpus_requested]) becomes requested_gpus. The final V42 bundle inherits the intermediate physical GPU quantity. Its snapshot gpus_requested also supplies the ML runtime feature num_gpus_req; that feature path is distinct from the inherited GPU_gang path.

Evidence: `dayahead/v37/aidc_materializer.py:69`, `dayahead/v37/aidc_materializer.py:463`, `v42_final/native_inputs.py:19`, `v42_final/native_inputs.py:40`.

### 3. Did it come through a canonical intermediate table?

Yes: V37_R4A_JOB_LEDGER.parquet requested_gpus/requested_GPUs and serialized temporal schedule requested_gpus precede frozen/common requested_GPU and native GPU_gang. The ledger and snapshot schemas were inspected from footers only; May per-job values were not compared in this audit.

Evidence: `dayahead/v37/aidc_materializer.py:390`, `dayahead/v37/aidc_materializer.py:559`, `dayahead/v40d_actual/inputs.py:50`, `dayahead/v41/common.py:39`.

### 4. Was GPU inherited from a job-state ledger?

Yes. May prepare.job_ledger copies common requested_GPU into its job-state record GPU_gang; the May native bundle receives these records as known_population. Current-Q50 native_inputs uses dict(j, ...) without overriding GPU_gang. EpisodeLedger.submit also preserves an already supplied, positive whole-gang GPU request; it does not discover missing request quantities.

Evidence: `v42_may01/prepare.py:108`, `v42_may01/prepare.py:186`, `v42_may01/prepare.py:243`, `v42_final/native_inputs.py:40`, `v42_final/state.py:40`.

### 5. Was there request-version reconciliation?

No reconstruction of original request versions was found in this executed-construction code path. V37 rejects duplicate full ids, which is not request-version reconciliation. Current V42 explicitly retains the Kestrel trace-proxy limitation: study authorization does not establish original request-version history.

Evidence: `dayahead/v37/aidc_materializer.py:180`, `v42_final/native_inputs.py:68`.

### 6. Was GPU maintained as an immutable physical attribute from the submission snapshot?

The code copies the snapshot request quantity into jobs and preserves requested_GPU through common rematerialization; V42 canonical/physical state uses inherited GPU_gang, with RUNNING occupancy independent of Q50 expiry. Identity uses the full source id, source-ledger submit_time and exact UID-set checks, with timestamp normalization to UTC. The May V42 membership gate checks full snapshot UIDs, cutoff and state; it does not recheck raw gpus_requested equality per UID. This audit therefore restores the construction rule, not independent numeric verification of every May row or original request version.

Evidence: `dayahead/v37/aidc_materializer.py:180`, `dayahead/v37/aidc_materializer.py:211`, `dayahead/v40d_actual/inputs.py:84`, `dayahead/v41/common.py:84`, `v42_may01/prepare.py:79`, `v42_temporal/native.py:57`, `v42_final/state.py:46`.

### 7. Was missing raw GPU exactly derived from another source-backed relation?

No additional GPU relation was found. Raw archive reprojection in current-Q50 native_inputs recovers array_pos only from exact ids. No GPU-from-node, GRES/ReqTRES parsing, job-id stem matching or other missing-GPU derivation exists in this May construction path. GPUS_PER_NODE*nodes is an upper-bound validation, not a replacement quantity.

Evidence: `v42_final/native_inputs.py:23`, `dayahead/v37/aidc_materializer.py:113`, `dayahead/v37/aidc_materializer.py:431`.

### 8. Was there fallback or imputation?

No physical GPU imputation is implemented. The historical V37 producer excludes incomplete resource rows and records UNKNOWN_GPU_REQUEST; historical Actual contributor construction similarly retains only positive finite requested-GPU contributors. Historical coverage_fallback_status is a duration fallback, not GPU recovery. Those exclusions and requested-walltime duration rules are superseded for this April task: retain every population row, leave unresolved GPU null, fail the known/Actual completeness gates, and use current frozen V42 Runtime service authority.

Evidence: `dayahead/v37/aidc_materializer.py:431`, `dayahead/v37/aidc_materializer.py:486`, `dayahead/v41/actual.py:148`, `v42_final/native_inputs.py:45`.

## Verified construction provenance

The actual `COMMON_INPUT_RECEIPT.json` generator is `dayahead/v41/common.py`, SHA256 `e21bde3188d1a246dbebfb50262c7722782ff2fa69b7e9b331ff2fba8a9d8a75`. Its declared generator/baseline/migration/admission code and source artifact hashes/sizes match local bytes. The common-reference job payload was hashed without parsing its jobs: SHA256 `60a75be104f8df41a93ac14f50a9ddd8ce330e3bd0c12cce2aa4e23e4b202ddb`.

The Kestrel ZIP SHA256 is `3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f`. The May-01 D1 snapshot is `8d74fcf0bc305bff983bff9607fe7d5120c8a61618631cfc6d6fdda81c71423a`; its `id`, `job_id`, UTC `submit_time`, `gpus_requested`, `source_member`, state and known-running-start schema were verified from the Parquet footer only. The job-ledger footer supplies `job_id`, `submit_time`, `requested_gpus` and `requested_GPUs`. Old and current-Q50 native bundle hashes are `6bd1eb8c5d01d902a2a03fe5924440b82e26b0e78bc5094eb2ecab30ed437582` and `f18b9dea2686b49de73b6d5d6ec7cc9e409c82e47b7f3bf7d29bdf5b1ba31170`; no job payload was parsed.

## Caller, snapshot and identity boundary

`materialize_all` calls `load_state_source`, `snapshot_at_issue`, then `materialize_day`, whose line 559 calls `_jobs_and_ledger`. The snapshot is saved in full at line 581 and the filtered ledger/exclusion table separately at lines 582–583. `refresh_causal_snapshots` verifies full snapshot UIDs equal ledger UIDs union exclusion UIDs at lines 756–757. The source helper `dayahead/v37/sources.py:165` reuses the same snapshot constructor. A historical ledger exclusion therefore does not prove the saved D1 snapshot excluded the job.

The full source `id` is preserved as a string; duplicate full IDs fail. Submission timestamps are normalized to UTC. The D1 cutoff is fixed AEST D-1 18:00. Pending future starts/ends are removed at the snapshot firewall; only a RUNNING job’s observed start survives. `frozen_jobs` joins submit_time from the source ledger using the full UID and requires equal selected/ledger UID populations. May V42 additionally requires the full D1 snapshot UID set equal the common-reference set, source SHA match, submission at/before cutoff, and state match. It does not independently compare every raw request quantity in its projected snapshot. No May row payload was inspected here, so this audit makes no claim that this full-set assertion passed through historical missing-row exclusion.

## Frozen April port rule

Use the same month-independent rule for all retained April known rows and Actual arrivals: exact full UID plus exact UTC submission identity, and source-backed positive whole GPU request. Preserve source path/member/SHA/field/raw value and parser rule. Do not collapse array IDs, infer a gang from nodes, truncate a fractional value, replace requested with allocated resources, use a fixed default, or borrow a May value. A uniquely parsed independent scheduler request field is permissible only with its own exact source provenance; this May path did not reveal one.

Conflicting source quantities remain ambiguous. Missing/invalid quantities remain in the population with null GPU and fail the corresponding known or Actual authority gate. The replacements are `EXCLUDE_MISSING_GPU → RETAIN_FAIL_CLOSED` and historical positive-only Actual contributors → all retained Actual rows with explicit unresolved authority. Original request-version history remains unverified.

Current frozen V42 Q50 provides service duration. Requested walltime remains only a predictor feature. Current V42 compatibility/capacity and the user-defined causal deterministic common reference scheduler provide placement; historical requested-service geometry, population masking and queue rules are not ported as scientific authority. Q50 expiry must not release an observed RUNNING gang.

## Evidence limits

Construction-rule restoration and matching provenance hashes are complete. Independent numeric reproduction of May per-job quantities was not performed. April GPU recovery/completeness is the separate builder’s responsibility; this audit creates no recovered rows, schedules, voltages, residuals, or margin estimates. All scientific values remain null and science is NOT_RUN in this audit.
