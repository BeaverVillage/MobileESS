# CC4-v2 hourly future arrival workload

At modeled local time D−1 18:00, predict Q50 and Q90 for each of the 24
non-overlapping local-clock hours of day D. The frozen modeled clock is fixed
UTC+10 (`Etc/GMT-10`), not the host's Asia/Seoul clock and not a DST clock.
Hour h has lead time 6+h hours, including 29 hours for the 23:00 bin.

For `[D+h hours, D+(h+1) hours)`, sum
`gpus_requested * (end_time-start_time).total_seconds()/3600`
over jobs whose original submit timestamp is in that interval. Boundaries are
left-closed, right-open. Unit: GPU·h. All target jobs are unsubmitted at issue.

This is **arrival workload**, not the compute service executed or required to
finish within that hour. A job submitted at 14:20 using 4 GPUs for 2.5 hours adds
10 GPU·h to the 14:00 bin; its processing can continue beyond 15:00. It is not
fractionally spread over its execution hours. Labels are never capped.

The exact frozen eligibility predicate is: finite strictly positive GPU count;
nonmissing start/end; end strictly after start; start at or after submit. No
imputation of missing GPU counts, CPU-only expansion, replicated sites, or job
filter based on target magnitude is introduced. The entire raw archive is read;
filename months are not used to choose submit-day populations. IDs and GPU·h
are checked against PR #59's frozen `raw_work.parquet`, whose production code
lineage is PR #42. Daily and original 15-minute targets are independently rebuilt.

The model has no physical/historical capacity input or upper-output clipping.
Log1p target fitting is inherited from PR #59 and monotonically inverted with
expm1; all evaluation and residual calibration use original GPU·h. Raw and
calibrated values are both preserved. Quantile-order repair and nonnegative
support are lower constraints, not physical limits.

History is observable by issue. Arrival counts use closed past bins. Historical
workload/count/maturity/age summaries use the inherited conservative all-job
completion mask. Seasonal 15-minute features describe historical sub-bins at
the hour start; cumulative lag features cover the entire historical hour.
Unknown work is encoded as zero with an explicit maturity mask, not as an
observed empty workload. A past job with an unobserved future end is censored.
`FEATURE_MATURITY_PROOF.parquet` records every day/feature availability; each
record applies to all 24 target rows. Counterfactual removal of future jobs and
hidden runtimes must leave the features exactly unchanged.

TRAIN and DEVELOPMENT label maturity is checked before the first issue of the
next stage. CALIBRATION labels must mature strictly before 2024-11-30 18:00
UTC+10 (the first December issue). No TRAIN label is required to be known at
its own historic issue: that would make supervised forecasting impossible.
It must instead be known before the fitted model is used. Every feature must
be known at its own issue. This distinction also applies to neural scalers.

Final calibration uses one score per calibration day for each target hour:
`actual - raw Q90`. The signed correction is order statistic
`ceil(.9*(n_days+1))`; for n=26, rank 25. Q90 is then constrained to be at least
Q50 and zero. No scale is searched. This empirical finite-sample correction
does not establish exchangeability of chronological days or simultaneous
coverage of a 24-hour profile. All inference uncertainty is grouped by day.

The earlier H4 result remains: 2,511 overlapping four-hour May windows;
actionable coverage 81.4416567%; physical-cap oracle ceiling 85.9418558%.
Unlike that capped lifetime-work interface, this target does not impose an
upper limit of one hour's processing capacity on arrivals.

## Later optimizer interface (documentation only)

**ML predicts future workload. Optimizer determines headroom.**

The future optimizer can define `H_h(x)=C_h-L_h_known(x)` and service
`0 <= S_h_future <= H_h(x)*Δt`. Cumulative arrivals, service, deadlines and
carry-out must be modeled explicitly; marginal hourly quantiles cannot simply
be summed and called a joint daily Q90. P2 coupling, dependence/scenario
validation and explicit replay of newly arriving jobs belong to a later task.
No operational reserve adequacy, same-hour completion guarantee, or deadline
compliance is claimed here.
