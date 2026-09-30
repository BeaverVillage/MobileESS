# Aggregate CC4 service timing

This interface consumes the unchanged B0/C0 lifetime GPUh forecasts. It does not predict job identities or train a model. Individual TS applies only to already submitted eligible PENDING jobs; aggregate service timing applies to remaining anonymous forecast mass.

For cohort `h`, `x[h,t]` is nonnegative GPUh, with no variable before hour-start slot `4h`. `sum(x[h,*]) + carryout[h] = remaining_W50[h]`. An electrical slot receives `4 * sum_h x[h,t]` GPU. Carry-out is nonnegative, retained beyond 24:00, and is not presented as a scheduled or electrically validated post-horizon trajectory. No service variables are invented beyond supported empirical lags.

At each supported active lag `l=t-4h`, the cumulative GPUh obeys `F_L(l)*W50 <= sum_{tau<=t} x[h,tau] <= F_U(l)*W50`. Completed TRAIN submission-hour cohorts from the PR96 kernel's exact parquet provide pointwise linear-interpolation Q10/Q90; the median is reported, not selected as another envelope. Cohorts with any censored/unobserved member are excluded as a whole. At a lag boundary, only cohorts whose observation cutoff reaches that boundary contribute. A completed cohort's observed completion plateau may extend to its cutoff, never beyond it. Every lag reports its cohort count. No May outcome or VALID sample participates.

`CC4_SERVICE_COHORT_CDF.csv` is a sparse exact representation: per-cohort change points, lag zero, and the last observed-support lag. Fill forward between listed points within `supported_through_lag`; do not interpolate linearly or extend past that support. A cohort with zero total observed work has no defined served fraction and is excluded. The envelope ends at the last observed nonzero-service lag, after which any unserved mass is carry-out.

The original 6,729-slot kernel stays byte-identical. It was constructed relative to individual submission timestamps and then anchored at each forecast hour's beginning. The new empirical cohort CDF uses actual submission-hour origins, as preregistered. This alignment difference is explicit; the reference kernel is neither silently re-estimated nor required to lie inside every envelope bound.

For every active `x`, nonnegative `dplus >= x - W50*kappa` and `dminus >= W50*kappa - x` create an L1 reference-deviation objective. There is no fixed reference-profile equality. Normalization is by total remaining nominal GPUh (and separately total reserve GPUh), with zero mass contributing zero. Only the active optimization horizon contributes to this deviation; carry-out is conserved without inventing its future schedule.

The A-stage lexicographic order is:

1. P1 grid-security `rho`.
2. P2 runtime plus CC4 reserve shortfall.
3. Normalized CC4 nominal and reserve reference deviation.
4. Migration count.
5. Shift slots.
6. Prestart placement changes.
7. Existing deterministic tie objective.

Higher-priority objectives are locked before the next objective. Deviation is never a security constraint. In an M stage the selected A-stage workload and deviation are fixed constants; the existing P1/P2, movement energy/count and tie objectives remain unchanged.

The remaining `max(W90-W50,0)` has separate timing variables under the same envelope and deviation rules. Their slot values are headroom targets, not realized IT load. The runtime reserve continues to use the unchanged survival kernel and gamma90 `2.423057443558147`, associated with the selected option's completion time and site. The diagnostic necessary LP relaxes achieved reserve to zero; full A1 is configured to bind real targets and their P2 shortfalls.

`ForecastBook` remains unchanged: each submission creates an explicit frozen-Q50 job and depletes Q50/Q90 exactly once; a closed cohort cannot retain anonymous physical occupancy. This arrival de-forecasting operation is distinct from conserving the remaining anonymous mass within a single planning solve. Mid-cohort planning issues require explicit already-served GPUh history for a positive-mass cohort that predates the active horizon. Known jobs and anonymous mass are never counted twice.

The new native adapter uses the original complete-option domain, exact service identity, WAN paths/payload/restart, and site/rack authorities. Only the permitted starts and the CC4 timing binding change. Native acceptance, Fresh AC and response-kernel freezing remain separate gates. A diagnostic LP witness is not an executable placement.
