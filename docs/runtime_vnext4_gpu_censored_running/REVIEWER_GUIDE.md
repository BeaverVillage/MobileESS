# Review order and evidence map

1. `FINAL_REVIEW_KO.md`, `FINAL_VERDICT.json`, and `COMPARISON.png`: conclusions, operational trade-off, and strict production boundary.
2. `REGISTRATION.json`, `VERDICT_RULE_FREEZE.json`, `FINAL_SELECTION_FREEZE.json`, and `FREEZE_BUNDLE.json`: fixed model/weight/quantile/selection decisions and chronology before new evaluation.
3. `MODEL_METRICS.csv`, `QUANTILE_DIAGNOSTICS.csv`, `RUNNING_ELAPSED_METRICS.csv`, `RUNNING_GPU_METRICS.csv`, and `PAIRED_UNCERTAINTY.csv`: exact points and paired uncertainty. Q90 is the operational bound. Q50/Q95 retain their names.
4. `PROXY_AUTHORIZATION.json`, `CENSORING_AUTHORITY.json`, `SOURCES.md`, and `FEATURE_AVAILABILITY_AUDIT.json`: explicit user-authorized request/state proxy and archive-conditional population; certification is not claimed.
5. `EXACT_SPLITS.csv`, `TRAINING_MEMBERSHIP_LEDGER.csv`, each fit's `ROW_IDS.npz`/`PORTABLE_MEMBERSHIP.json`/`RECEIPT.json`, and `PORTABLE_MEMBERSHIP_AUDIT.json`: exact training observations, safe labels, weights, censored rows, and source digests.
6. `PREDICTIONS.parquet` and raw `predictions/R2`, `predictions/R3`: final common-cohort outputs and unfused model quantiles. R1 and R0 source predictions remain in the immutable parent evidence. Pending is exact R0 in all four arms.
7. `VALIDATION.json`, `TEST_RESULTS.json`, `INDEPENDENT_REVIEW.json`, `RAW_REBUILD_VALIDATION.json`, `PREPROCESSING_BRIDGE.json`, and parent preservation receipts: scientific checks and byte preservation.
8. `README.md`, scientific source, `delivery_tools`, pinned requirements and `DELIVERY_MANIFEST.json`: reproduction and delivery verification.

New model checkpoints and large full fit-time membership Parquets are preserved unchanged locally, not committed. The checkpoint manifest records their exact bytes. Compact membership NPZ plus immutable parent job catalog and frozen censoring recipe reproduces every full membership column, including masked completion timestamps, infinity upper bounds and float64 weights. Its audit can run without the large local Parquets or model checkpoints.

`NEW_MODEL_SUPERIOR` follows the pre-evaluation rule, not a post-hoc choice of a favorable metric. `selected=R3` identifies the DEV/CAL safety-first research candidate; the reserve preference was not a hard selection gate. Production suitability is assessed separately and remains fail-closed under unverified request versions, unverified archive census, and already-exposed evaluation history.

No optimizer, MESS, grid, Actual/OpenDSS, or production execution is part of this study.
