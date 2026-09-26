# Runtime-vNext5 — fixed R2 causal residual calibration

Only calibration changes. R1 in this study is the exact raw PR71 **R2** elapsed-conditioned Running Q90. R2 adds a global one-sided empirical residual quantile; R3 uses requested-GPU-weighted residuals. R0 is the frozen production reference, available only for May. Every Pending arm is exactly R0. No model refit, new features, temporal-policy search, Q95 selection, AFT fitting, optimizer/grid operation or production promotion occurs.

At current issue `t`, retain source OOS forecasts only when `source_issue < t` and `job_end < t`. Filter first, then keep the latest eligible forecast per Job. Its residual is `job_end - source_issue - source_raw_Q90`, in seconds. It is not the remaining duration at the current issue. Each Job contributes once to that issue's pool.

With at least 100 distinct mature Jobs, the correction is `max(0, inverse_empirical_CDF_0.90(residual))`. R2 gives each Job weight 1; R3 uses the strictly positive requested GPU count at its source forecast. The quantile is the first sorted residual with cumulative weight at least 90% of total, with no interpolation. With fewer than 100 Jobs, correction is exactly zero and all queries remain in all metrics. There are no PR71 R2 TRAIN forecasts to backfill this warmup.

This is empirical causal calibration, not a finite-sample or distribution-free coverage guarantee. The expanding calibration history is distinct from the unchanged 180-day/14-day base-model training policy. Latest-per-Job sampling changes the elapsed distribution, and maturity requirements favor already-finished Jobs; neither temporal dependence nor archive inclusion bias is removed. GPU weights remain the user-authorized scheduler request proxy. Their concentration/ESS is reported, never used as a tuned gate.

The DEV/CAL eligibility gates are coverage≥90%, GPU coverage≥90%, total-runtime>4h underprediction≤15%, and Q90 pinball≤1.02×raw in **both** roles. Among eligible arms, prefer requested-walltime overreserve compliance, then lowest mean role reserved/requested ratio, then arm ID. Otherwise retain raw R1. Reserve is a preference, as specified by the user, and is not silently turned into a mandatory calibration-support gate. Nonnegative additive correction mathematically cannot decrease raw reserve/overreserve on a fixed cohort. Production/integration readiness remains fail-closed separately.

The original proposal briefly considered a mandatory reserve support gate. Before registration or DEV metrics, the instruction hierarchy was clarified to preserve the user's explicit **preferred** reserve condition. The final frozen protocol records this correction; no model result or May outcome was used to tune the quantile, support, pinball margin or reserve rule.

## Reproduce

Parents are immutable PR71 base `1702abdd14db3ad6e5a63211459b9b99d6a8a054`. No raw archive, local model checkpoints or training environment is needed: all source predictions and original exact membership are committed in the parents.

Create a fresh sibling folder under `docs`, copy `study.py`, `test_contract.py` and `REQUIREMENTS.txt`, install the pinned packages, then run:

```text
python -m unittest -v test_contract
python study.py prepare
python study.py register
python study.py development
python study.py evaluation
python study.py audit
```

`development` freezes the selection before evaluation. Write outputs to the new sibling only; existing evidence is immutable. `SOURCE_FORECASTS.parquet` is the exact frozen raw source catalog, joined to parent event-time labels for maturity filtering. Each issue's `calibration/<issue>/MEMBERSHIP.parquet` records every included source forecast, mature end, raw bound, GPU weight and residual. No source future outcome may enter an earlier pool.

`FINAL_REVIEW_KO.md`, `FINAL_VERDICT.json`, point/stratified metrics, 1/7-observed-issue paired bootstrap 95% CIs, contract tests, independent audit and the delivery manifest document the result. May remains an already-exposed historical diagnostic. Request/state authority remains **D1_SCHEDULER_REQUEST_STATE_PROXY_V1, UNVERIFIED/UNOBSERVED**; immutable requests or an actual historical census are not asserted.
