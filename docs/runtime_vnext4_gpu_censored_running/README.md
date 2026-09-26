# Runtime-vNext4 — GPU-weighted / censored Running study

Read `FINAL_REVIEW_KO.md` after completion. Pending is exact frozen production R0 in every arm. Running compares R0, inherited PR65 MULTI_QUANTILE R1, GPU/long-job weighted MULTI_QUANTILE R2, and fixed log-normal remaining-lifetime AFT R3. Q90 remains the operational bound; Q50/Q95 are diagnostics only. Selector and quantile-level search has ended.

R2 preserves R1's completed landmark membership, learned input representation, model hyperparameters, and 180-day/14-day policy. Its only change is recency×GPU×observed-long-job weighting, normalized to preserve total recency weight. R3 adds as-of right-censored archive rows and changes the model family; this jointly changes censor handling and architecture, so R3−R2 is not a pure architecture ablation.

## Authorized proxy scope

The user explicitly authorized V40S4 `D1_SCHEDULER_REQUEST_STATE_PROXY_V1`. Request fields are assumed scheduler-visible proxies; provenance is **UNVERIFIED/UNOBSERVED**. We do not claim immutable requests, zero changes, historical exactness, a complete actual as-of census, or outcome-independent archive inclusion. R3 is conditional on the released archive. The original stricter authority assessment is preserved and linked by the later `PROXY_AUTHORIZATION.json`. [Sources](SOURCES.md) explains this boundary.

R3 uses stable Job-hash landmarks inherited from PR65. At an issue, a completed Job with end<issue has exact remaining duration. Otherwise its remaining duration at an already-observed landmark has lower bound issue−start−landmark and upper bound infinity. Future end values, final state and final label_valid do not enter censored features/labels/weights. Censored long-job weight is based on already-observed elapsed duration only. Rows whose assigned landmark has not yet been reached have no positive remaining follow-up and are omitted using only as-of elapsed information.

## Reproduction

The repository parents `runtime_vnext_causal_tail`, `runtime_vnext2_q95_operational_bound`, and `runtime_vnext3_adaptive_running_bound` must remain at their sealed versions in PR68 base `d078bdc3d849f62ccd12db8baee6f95e67c0d2be`. Scientific dependencies are pinned by `ENVIRONMENT.json`/`REQUIREMENTS.txt`. The raw archive SHA is recorded in `PREPARATION.json`.

The delivered directory is immutable. To reproduce, create a fresh sibling directory, copy `study.py`, `prepare.py`, `censor_proxy.py`, `test_contract.py`, the `preprocessing` folder and read-only input records `PREPARATION.json`, `PREPROCESSING_BRIDGE.json`, `CENSORING_AUTHORITY.json`, `PROXY_AUTHORIZATION.json`. Copy `delivery_tools/rebuild_jobs.py` and recreate the exact normalized input:

```text
python delivery_tools/rebuild_jobs.py
```

Set `RUNTIME_JOBS_PARQUET` to the new `cache/JOBS.parquet` path, and `KESTREL_RAW_ZIP` if needed. The rebuilt Parquet must match the exact parent SHA. Portable preprocessing objects contain only the existing sklearn encoder/SVD and metadata, with 59 original query matrices verified bit-exact at export; original external MoE checkpoints are not needed to refit this study.

```text
python -m unittest -v test_contract
python study.py register
python study.py development
python study.py select
python study.py evaluation
python study.py audit
```

`prepare.py` and `censor_proxy.py` retain the original preparation/audit/export steps for provenance, but re-running the export requires the original PR65 local checkpoints and model code; the committed portable objects avoid that dependency for reproduction. New model checkpoints and full fit-time membership Parquets remain unchanged locally and are recorded by hashes. The compact delivered membership representation is each fit's ordered `ROW_IDS.npz` plus `PORTABLE_MEMBERSHIP.json`, the immutable parent job catalog, and frozen `censor_proxy.py`. This losslessly reproduces every original safe label, timestamp, censor flag and float64 weight. `delivery_tools/package_membership.py` verifies all canonical column digests; use `--package` only in a new reproduction after fitting, and no argument to audit an existing delivery without the full local Parquets. No parent file is modified.

Selection uses only DEV/CAL and fixed Q90. May is exposed historical diagnostic. Paired 1/7-observed-issue-day circular block 95% CIs use 2,000 draws, recomputing nonlinear ratios within each sample. Remaining long-job error uses total actual runtime>4h to define the stratum. Requested reference is max(requested−elapsed,0). GPU-slots are the inherited 15-minute/24-hour runtime-origin occupancy proxy, not optimizer dispatch.

No optimizer/MESS/IEEE123/8500/Actual/OpenDSS edits or runs, and no production promotion.
