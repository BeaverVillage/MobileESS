# V29 pre-April carry-in population and service-mass calibration review

Status: **PASS — read-only census; pre-April grid-value potential is not identifiable from frozen electrical authority.**

No production formulation, parameter, eligibility rule, objective, site mapping, or campaign result was changed. No full 10×96 OpenDSS campaign was run.

## Direct answers

1. **How often does source-backed carry-in actually exist?** Nonzero predicted carry-in occurs on 9.21% of the 456 study days; 90.79% are zero. Fractions strictly above 100/250/500/1000 node-h are 8.55% / 7.89% / 6.36% / 4.61%.

2. **Are Apr-3 216 node-h and Apr-4 1020 node-h typical?** Apr-3 is at the inclusive empirical 92.11th percentile (midrank 92.11); Apr-4 is at the 95.39th percentile (midrank 95.39).

3. **What is wallclock_req as a service-mass proxy?** It is a conservative upper-bound-like proxy at population level, not a calibrated point estimate.

4. **What fraction is typically realized?** Median job-level R is 0.0400; aggregate realized/requested service is 0.1980.

5. **Does R depend on request-time groups?** Yes, strongly for requested wallclock and QoS in descriptive terms; less strongly for node class and cutoff-observable queue age. Median-R ranges (groups with at least 20 rows) are: node class 0.03703703703703705, requested wallclock 0.13538194444444443, QoS 0.4014351851851852, and first-cutoff queue age 0.04677662037037037. These are associations, not causal effects.

6. **Is a lower-bound calibrated executable-service mass justified?** Yes as a separately validated lower-bound/uncertainty estimator, but not as an immediately selectable production replacement. The fixed historical P25 candidate has 76.36% empirical lower-bound coverage while its median fold prediction/realized ratio is only 0.1011; it is conservative enough to underpredict aggregate mass materially. This census selects no production quantile.

7. **How often is grid-value material under rho=.10?** Not identifiable. Frozen D1 feeder critical-line/phase/time authority begins in April 2025, outside the study population.

8. **Why is AIDC contribution low at population level?** Rare workload is the demonstrable population-level gate because carry-in is zero on 90.79% of days. Conditional on nonzero carry-in, historical topology and trust contributions are not jointly identifiable, so the residual may be mixed but cannot be apportioned.

9. **What remains unchanged?** rho; production `nodes_req × wallclock_req`; strict full-node eligibility and PARTIAL/shared exclusion; PRE_DAY_QUEUE_BRIDGE_V1; clipping policy; objective; site mapping; and all production quantiles, multipliers, and formulation parameters until the active post-development forensic finishes.

## Causal and scientific boundaries

- `FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF = 0`
- `APRIL_LABEL_ROWS_IN_PREAPRIL_FIT = 0`
- Future archive members were opened only to reconstruct historical queue state; their post-cutoff completion labels were excluded from every fit.
- Daily D0 realized queued service is an ex-post diagnostic only.
- The grid-value CSV is deliberately fail-closed with null electrical fields rather than extrapolating April topology into pre-April dates.
