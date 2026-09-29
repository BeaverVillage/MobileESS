# Frozen current state features

S0 uses the same29 static V9 columns. S1 adds arrival pressure: counts5m,
15m/1h/6h/24h counts and request GPU/node/core/memory/GPU-time sums, GPU and
walltime means/medians, walltime Q75/Q90, highGPU>=16/longwall>4h/array counts
and fractions. Same-account1h/6h and sameQoS/partition1h counts, time since
strictly prior submission. Observed same-timestamp count is always0 under the
conservative contract; retrospective cohort size is deliberately unavailable.

S2 adds pending count and resource sums, GPU/wall Q50/Q90, observed submit age
Q50/Q90/max, longwall fraction, same-account count. S3 adds running count,
GPU/node/core/memory sums, elapsed Q50/Q90/max from observed START, same-account
count. S4 adds pending/running controlled QoS/partition shares plus OTHER,
GPU-size/walltime bucket shares, entropy and HHI, and four explicit interactions
listed in the JSON contract. No actual runtime enters any state feature.

TRAIN-prefix vocabulary is unavailable before its own observation cutoff; early
category shares map to OTHER. Raw matching account/partition/QoS counts use only
observed identities and never a job-ID predictive lookup. Job IDs solely maintain
event lifecycle. Empty sums/counts/shares are0; empty quantiles/ages/means NaN.
Resource sums use fixed micro-unit integers for deterministic insert/delete.
Age quantiles use t minus the reverse quantile of observed submit/start times.
The rolling lower endpoint is inclusive, upper endpoint strict. There are no
runtime-completion aggregates, absolute calendar features or capacity divisors.
