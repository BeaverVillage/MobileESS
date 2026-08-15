# Representative-period selection for the Mobile ESS experiments

## Experimental boundary

The representative-period selector is calibrated only with 2024 exogenous
data. The frozen rule is then applied once to the 2025 exogenous data, before
any controller, routing, OpenDSS, or realized-outcome result is available.
Thus 2024 is the validation/calibration year and 2025 remains the held-out
application year. The manifest produced by this workflow is an input freeze;
it does not authorize an annual controller run.

## Inputs and repair policy

The ten selection features are VIC1 regional demand, rooftop-PV production,
VIC1 spot price, three SCATS traffic statistics, three Kestrel job-arrival
statistics, and nominal arriving WAN volume. Regional demand is used only as a
regional temporal-pattern feature. WAN volume is derived from arriving GPU
hours as `GPUh x 3 GB/GPUh` and is not a separately observed WAN trace.

The AEMO rooftop-PV source is exact-deduplicated before repair. Five blank
measurement values are replaced by the same-timestamp `SATELLITE` observation.
Only the two 2024 timestamps for which neither measurement nor satellite data
exists are linearly interpolated between adjacent valid observations. Raw
archives are not modified. This same-timestamp satellite rule is the same rule
used by the proposal-model input pipeline.

## Selection rule

Candidate periods are complete observed Monday-to-Sunday weeks with a
48-hour burn-in. Distances use 2024 median/IQR normalization, with robust
fallback scales, and combine time-aligned profiles with weekly distribution
summaries. Domain weights are balanced across power, price, traffic, and
job/WAN inputs. Exact Southern Hemisphere seasonal quotas are imposed for
`K in {4, 8, 12}`.

Before minimum-distance tie breaking, every feature must satisfy a maximum
20% seasonal-mean relative error. A candidate K is accepted only when all of
the following hold:

- maximum annual-mean relative error: 15%;
- maximum seasonal-mean relative error: 20%;
- maximum continuous-feature p95 relative error: 10%;
- maximum continuous-feature ramp-p95 relative error: 10%;
- correlation-matrix mean absolute error: 0.10;
- exact seasonal quotas and the selection constraint both pass.

Job/WAN observations are sparse at five-minute resolution, so pointwise p95
and ramp-p95 are structurally zero-dominated. Their annual and seasonal means
remain in the representative-period gate, while their tail behaviour is
covered by a separate, zero-weight workload/WAN stress episode. Separating
typical and extreme periods follows the representative-period literature
[1-3], while the retained distribution, ramp, and correlation checks follow
the k-MILP validation rationale in [2].

## Frozen result

Exhaustive seasonal-quota feasibility analysis rejected K=4 and K=8. K=12
was the smallest feasible and accepted configuration in 2024. Applying that
rule once to 2025 selected three weeks per season:

`W02, W07, W10, W17, W18, W25, W26, W32, W38, W41, W44, W51`.

The 2025 audit passed every preregistered criterion. The maximum annual-mean
relative error was 0.0850, maximum seasonal-mean relative error 0.1822,
maximum continuous-feature p95 relative error 0.0741, maximum continuous
ramp-p95 relative error 0.0475, and correlation-matrix mean absolute error
0.0185. Cluster weights sum to one. Four 48-hour, zero-weight stress episodes
cover maximum regional demand, price/demand ramps, traffic congestion, and
compound workload/WAN arrivals.

Machine-readable selected-week tables are stored under
`period_selection/output/`; a compact result record suitable for paper and
artifact review is stored in
`science/REPRESENTATIVE_PERIOD_RESULT_20260815.json`.

## Reproduction

Install `requirements-period-selection.txt`, then provide local data paths
through these environment variables or the corresponding command-line
arguments:

- `MOBILE_ESS_RAW_ROOT`
- `MOBILE_ESS_F30_SOURCE`
- `MOBILE_ESS_KESTREL_RAW_ZIP`
- `MOBILE_ESS_TRAFFIC_FREEZE`
- `MOBILE_ESS_CANONICAL_2025_JOBS` (optional parity check)

The raw audit, adapters, repaired parquet tables, full feature matrices, and
checksum manifests are generated locally and intentionally excluded from Git
because they contain machine-specific paths or large derived data. Selection
tables and the path-free scientific summary are versioned.

## References

1. Fazlollahi et al., representative periods with epsilon constraints,
   *Computers & Chemical Engineering* (2014),
   https://doi.org/10.1016/j.compchemeng.2014.03.005.
2. Teichgraeber and Brandt, k-MILP representative periods with load,
   ramp-duration, and correlation constraints, *Energy* (2019),
   https://doi.org/10.1016/j.energy.2019.05.044.
3. Teichgraeber et al., systematic inclusion of extreme periods,
   *Applied Energy* (2020), https://doi.org/10.1016/j.apenergy.2020.115223.
