# Independent delivery audit

Run `audit.py` with the registered CC4 Python environment **after** `EVALUATION_COMPLETE.json` exists. The auditor runs the primary validation, then independently checks probability validity, exact causal training and residual membership, corrections, C0/C1/C2 output values, Q50 preservation, sparse back-off, and evaluation receipt hashes. It does not fit models, select a candidate, or calculate comparison metrics.

The original PR64 and CC4-v2.2 training receipts stored `weights` as abbreviated `pandas.Index` strings through JSON `default=str`. Those strings are preserved. They do not constitute complete numeric weight records and are never parsed to recover omitted values.

`RECONSTRUCTED_NUMERIC_TEMPORAL_MEMBERSHIP.npz` appends complete numeric vectors **deterministically reconstructed** from the immutable ledger, issue times, and frozen source functions. These were **not originally logged numeric vectors**. For every target day, the auditor separately executes the original PR64 membership/weight functions and compares their complete outputs with the current functions. The NPZ contains the target-day list and, for each day, matching `train_day_indices_<day>` and `weights_<day>` arrays. The unchanged training code repeats each day weight 24 times. `TEMPORAL_WEIGHT_RECONSTRUCTION.json` records provenance and hashes; `INDEPENDENT_AUDIT.json` records the complete audit result.

All added artifacts are write-once. Repeated audits validate existing artifact contents without replacing them. The primary `study.verify()` writes its normal validation receipt. The auditor does not rewrite historical evidence, predictions, model checkpoints, selection, or protocol.

The C2 replay checks the application of its sealed raw tail bounds, gate and support rule. It does not retrain models or claim an independent refit of every tail model. Finite-rank residual calibration does not establish distribution-free coverage for dependent hourly observations. The paired bootstrap describes uncertainty conditional on the fitted historical forecasts.
