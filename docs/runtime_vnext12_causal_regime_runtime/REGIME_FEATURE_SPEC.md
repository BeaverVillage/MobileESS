# V12 causal regime specification

TOTAL predicts at submit_time. Each explicit index window contains only completed
episodes with `prediction_time - window <= end_time < prediction_time` and
`submit_time <= start_time <= end_time`. The job cannot contribute to its own
submission features. Simultaneous completions are excluded, regardless of input order.

Global7/14/30d: runtime quantiles25/50/75/90/95; >1/4/8/12/24h prevalence;
completed count, sum(runtime*requested_GPU)/3600, mean requested GPUs, fraction GPUs>=16;
runtime/requested-walltime quantiles50/75/90. Invalid/nonpositive walltimes are
excluded from ratio samples. Runtime quantiles use linear interpolation.

Six cohort families: partition, QoS, walltime buckets <=1h/4h/12h/24h/>24h,
GPU buckets <=1/4/8/16/>16; partition x QoS; partition x walltime.
Missing categories have an explicit sentinel, never an outcome-derived category.
14/30d cohort features: N, runtime Q50/Q90, >4h/>12h rates, ratio Q50.
No other crosses or7d cohorts. Exact raw N and selected support N, tail N, ratio N,
fallback depth and newest/oldest observation ages are retained per family.

Support and fallback are frozen in REGIME_SUPPORT_CONTRACT.json. A prior is
available only after its own newest observation; earlier TRAIN rows remain NaN.
Absolute dates, hour and weekday are excluded. Metadata ages describe observation
freshness. Current unfinished jobs are excluded, so completion-selection lag is a
limitation of the hypothesis, not a label reconstructed from the future.

R0=29 V9 static features; R1 adds global; R2 adds cohorts; R3 adds four trends:
global Q90(7d)-Q90(30d), >4h(7d)- >4h(30d), Q50(7d)/Q50(30d),
ratio Q50(14d)-ratio Q50(30d). Zero-denominator trends remain NaN.
Static descriptors remain archived trace proxies, not verified initial-submit values.

Only C0 raw hazard is preregistered. Positive piecewise rates and last-rate
continuation retain the exact V9 grid; stable log-space interval scores use V10 math.
No additive-seconds or static global probability calibration is used.
