# V41R2 AIDC GPU capacity sizing authority audit

**RECOMMENDED CAPACITY AUTHORITY: generalized allocation rule B; no tested installed capacity is approved. Full May remains HOLD.** This PR contains only audit evidence and reproducibility code. No production capacity, schedule, model, electrical coefficients, B1/B2/B3 or WAN semantics are changed.

All-D-day offered mean: **2,202.516 GPU slots**. Mean-occupancy totals: **75%=2,936; 80%=2,752; 85%=2,592**. A and B are compared at each identical total. All six still leave material D-day service unstarted. The requested 80% mean is an arithmetic design point, not proof of a healthy operating region.

## Current authority and historical lineage

Current total **624**; vector **[64, 32, 64, 32, 80, 64, 32, 64, 32, 64, 32, 64]**. Four-GPU equivalent H100 node granularity; four nonadditive logical rack pools per site. Physical rack count and GPU-per-physical-rack are unavailable, so 48 logical pools must not be presented as 48 installed physical racks.

| AIDC | GPU | 4-GPU nodes | Logical pools | Each pool envelope | IT idle kW | IT full kW |
|---|---|---|---|---|---|---|
| AIDC01 | 64 | 16 | 4 | 64 | 6.666 | 41.721 |
| AIDC02 | 32 | 8 | 4 | 32 | 3.333 | 20.860 |
| AIDC03 | 64 | 16 | 4 | 64 | 6.666 | 41.721 |
| AIDC04 | 32 | 8 | 4 | 32 | 3.333 | 20.860 |
| AIDC05 | 80 | 20 | 4 | 80 | 8.333 | 52.151 |
| AIDC06 | 64 | 16 | 4 | 64 | 6.666 | 41.721 |
| AIDC07 | 32 | 8 | 4 | 32 | 3.333 | 20.860 |
| AIDC08 | 64 | 16 | 4 | 64 | 6.666 | 41.721 |
| AIDC09 | 32 | 8 | 4 | 32 | 3.333 | 20.860 |
| AIDC10 | 64 | 16 | 4 | 64 | 6.666 | 41.721 |
| AIDC11 | 32 | 8 | 4 | 32 | 3.333 | 20.860 |
| AIDC12 | 64 | 16 | 4 | 64 | 6.666 | 41.721 |

GPU source SHA-256: `bef9175ce8bcbbfcbdde6d66d41f7f10da18998859dec5000ec9fbed44fe0c9e`; creating commit `7741844618c7661301be6ecc84b98f003ffb844b`. Rule commit `3cd14441fba0d574678339fc7d206e05496a4887`. Rack authority commit `9ff503ae643a7bed756b03d1a005f3f398438145`. Complete fields, line locations, hashes and per-site ceilings are in CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json. Current coefficient-bound PCC interfaces are **500 kVA per phase** and **208.179184 A per phase**, identical across all 31 days; shared network/voltage constraints also apply. The historical V22SR1 0.3-MVA interface is not the current runtime limit.

The exact V39C construction gives eight nodes to every site, then one eight-node/32-GPU block to each of the seven highest facility-weight sites, then four residual nodes/16 GPUs to AIDC05. The pre-May gang audit documents recurrent 32-GPU jobs; this is a defensible frozen synthetic engineering allocation (CASE A), not a GPU census. V22SR1 is a soft facility-size prior, not a MW-to-GPU conversion.

The original fixed-total allocator is not forced onto larger totals. Rule A scales its frozen shape; rule B is the user-authorized generalization: 32 GPU/site plus residual 4-GPU nodes apportioned by authoritative V22SR1 weights. B is explicitly **not historically identical** to the original allocator.

[GitHub PR #12](https://github.com/BeaverVillage/MobileESS/pull/12), head `499d5793ed4b725fa5d0b38691b07752c4f88482`, contains the exact same weight-file bytes (SHA `1fb7931dcc86b190af7e9cc0e18b3466897ea66a35a79e53e452b36524a6e63b`). Retrieved PR metadata says open/unmerged; its artifact is verified in current Git history, rather than assumed merged. Repository field `primary_IT_equivalent_capacity_MW` is the primary site-scale authority. Total **202.750769230769 MW**.

| Site | Facility | Primary IT-equivalent MW | Weight | Classification / source |
|---|---|---|---|---|
| AIDC01 | Equinix ME4 | 12.000 | 0.059185965338 | SOURCE_BACKED_IT_CAPACITY / S_ME4_ITNEWS |
| AIDC02 | Micron21 | 2.000 | 0.009864327556 | SECONDARY_CRITICAL_POWER_EQUIVALENT / S_MICRON_DCM |
| AIDC03 | Fujitsu Noble Park | 28.000 | 0.138100585789 | SOURCE_BACKED_IT_CAPACITY / S_FUJITSU_OFFICIAL |
| AIDC04 | AAPT / TPG Richmond | 1.885 | 0.009295231736 | ENGINEERING_IT_EQUIVALENT_FROM_MVA / S_AAPT_INFLECT |
| AIDC05 | NEXTDC M2 | 42.000 | 0.207150878684 | SOURCE_BACKED_DATA_HALL_DESIGN_POWER_CAPACITY / S_NEXTDC_1H25 |
| AIDC06 | NEXTDC M3 | 13.500 | 0.066584211006 | SOURCE_BACKED_DATA_HALL_DESIGN_POWER_CAPACITY / S_NEXTDC_1H25 |
| AIDC07 | Vocus Mitcham | 9.000 | 0.044389474004 | SECONDARY_CRITICAL_POWER_EQUIVALENT / S_VOCUS_DCM |
| AIDC08 | NEXTDC M1 | 15.000 | 0.073982456673 | SOURCE_BACKED_IT_CAPACITY / S_NEXTDC_GUIDE |
| AIDC09 | Equinix ME5 | 2.346 | 0.011571615018 | ENGINEERING_EQUIVALENT_IT_CAPACITY_PROXY_FROM_N_PLUS_1_BACKUP / S_ME5_EQX |
| AIDC10 | CDC Brooklyn BK1 | 34.000 | 0.167693568458 | SOURCE_BACKED_OPERATING_BUILD_CAPACITY_EQUIVALENT / S_CDC_INFRATIL_2025 |
| AIDC11 | IBM MEL01 / Digital Realty MEL11 | 7.020 | 0.034623789723 | HISTORICAL_DIGITAL_REALTY_FACILITY_CAPACITY_PRIMARY / S_MEL11_DLR_HISTORICAL_2020 |
| AIDC12 | STACK MEL01A | 36.000 | 0.177557896015 | SOURCE_BACKED_BUILT_CRITICAL_CAPACITY / S_STACK_OPEN |

All twelve historical GPU weights are `UNAVAILABLE_NOT_INFERRED`; V22S records zero MW-equals-GPU-weight calls. Primary classifications include engineering MVA and generator conversions as well as source-backed facility capacities. Values are not uniformly measured IT capacities.

## Offered demand and UNASSIGNED causes

Daily forecasts are independent D-1 18:00 fixed-AEST snapshots. Slot 24 is D00; slot 120 is D24. Preserve reference work already complete before D00 and exact D00 RUNNING residuals. Causally known PENDING jobs are ready before D00: V37 `_first_fit` starts at issue slot 0 and accepts no independent future not-before/release field. In a D00-anchored capacity-free counterfactual their earliest nominal Day-D start is 24. This removes capacity waiting, not an exogenous release or a policy time-shift. The trace is conditional on the fixed D00 state; an issue-time release sensitivity is also saved and must not be substituted silently.

There are 25,597 UNASSIGNED pending job-day observations with old starts >=120. `production_activity` dropped intervals outside [24,120) before placement; their timestamps were produced by the 624-GPU queue. **None has an independent nominal future release >=120**, so they are D-day offered demand, not true future-service exclusions. 1,464 UNASSIGNED jobs are already pre-D00 complete. Another 14 have Q90-expanded preday intervals overlapping D00 but no physical source site; their 11 GPU-hours are included conservatively in system demand and remain explicitly ambiguous for site replay. Their offered share is 0.001%. No site was fabricated.

| Cohort | Job-day observations |
|---|---|
| D_DAY_RUNNING_RESIDUAL | 8588 |
| PRE_D00_COMPLETE | 1523 |
| D_DAY_PENDING_OFFERED | 36884 |
| AMBIGUOUS_UNASSIGNED | 14 |

Authoritative POST_H_BACKLOG / FUTURE_SERVICE_DEMAND in this issue-visible, capacity-free cohort: **0 jobs / 0 GPU-hours**. This does not assert that no jobs arrive in the future; future arrivals are outside the frozen visible cohort. Historical post-H queue backlog is reported separately and remains in the D-day demand until service is delivered.

| Mean | P50 | P90 | P95 | P99 | Max | GPU-hours |
|---|---|---|---|---|---|---|
| 2,202.516 | 1,238.000 | 5,442.000 | 8,379.000 | 10,148.000 | 13,275.000 | 1,638,672.250 |

| Site component | Mean GPU | P50 | P90 | P95 | P99 | Max | GPU-hours | Total share |
|---|---|---|---|---|---|---|---|---|
| AIDC01 | 64.041 | 64.000 | 118.000 | 134.000 | 189.000 | 415.000 | 47,646.500 | 2.908% |
| AIDC02 | 32.419 | 32.000 | 64.000 | 69.000 | 95.000 | 164.000 | 24,119.500 | 1.472% |
| AIDC03 | 64.846 | 64.000 | 98.000 | 128.000 | 192.000 | 636.000 | 48,245.500 | 2.944% |
| AIDC04 | 32.324 | 32.000 | 64.000 | 68.000 | 87.000 | 230.000 | 24,049.000 | 1.468% |
| AIDC05 | 83.011 | 80.000 | 144.000 | 164.000 | 224.000 | 566.000 | 61,760.500 | 3.769% |
| AIDC06 | 63.462 | 64.000 | 98.000 | 115.000 | 172.000 | 260.000 | 47,216.000 | 2.881% |
| AIDC07 | 31.281 | 32.000 | 58.000 | 66.000 | 96.000 | 187.000 | 23,273.250 | 1.420% |
| AIDC08 | 61.052 | 64.000 | 80.000 | 96.000 | 120.000 | 359.000 | 45,422.750 | 2.772% |
| AIDC09 | 30.450 | 32.000 | 52.000 | 66.000 | 96.000 | 180.000 | 22,655.000 | 1.383% |
| AIDC10 | 63.822 | 64.000 | 108.000 | 128.000 | 188.000 | 381.000 | 47,483.750 | 2.898% |
| AIDC11 | 33.842 | 32.000 | 64.000 | 73.000 | 96.000 | 164.000 | 25,178.500 | 1.537% |
| AIDC12 | 69.111 | 64.000 | 128.000 | 158.000 | 190.000 | 282.000 | 51,418.500 | 3.138% |
| UNKNOWN_SITE | 1,572.854 | 375.000 | 4,764.000 | 7,736.000 | 9,501.000 | 12,441.000 | 1,170,203.500 | 71.412% |

The known-site statistics are a partial decomposition, not the complete spatial workload. `D_GPU_offered_total == sum(D_GPU_offered_known_site, axis=2) + D_GPU_offered_UNASSIGNED` exactly. The NPZ alias `D_GPU_offered` holds the known-site component only; the aggregate sizing array is `D_GPU_offered_total`.

| Day | Mean | P95 | Max | GPU-hours | Unknown-site mean |
|---|---|---|---|---|---|
| 2025-05-01 | 1,085.885 | 1,769.000 | 1,804.000 | 26,061.250 | 432.667 |
| 2025-05-02 | 1,160.625 | 1,813.000 | 1,813.000 | 27,855.000 | 443.448 |
| 2025-05-03 | 1,021.240 | 1,697.500 | 1,810.000 | 24,509.750 | 333.135 |
| 2025-05-04 | 687.625 | 1,223.000 | 1,235.000 | 16,503.000 | 0.000 |
| 2025-05-05 | 439.177 | 838.250 | 860.000 | 10,540.250 | 0.000 |
| 2025-05-06 | 809.354 | 1,030.500 | 1,045.000 | 19,424.500 | 0.000 |
| 2025-05-07 | 3,602.802 | 3,502.000 | 13,275.000 | 86,467.250 | 2,845.906 |
| 2025-05-08 | 3,064.740 | 3,028.750 | 10,492.000 | 73,553.750 | 2,385.385 |
| 2025-05-09 | 1,032.406 | 1,066.000 | 6,182.000 | 24,777.750 | 357.823 |
| 2025-05-10 | 1,039.083 | 1,374.000 | 6,517.000 | 24,938.000 | 491.635 |
| 2025-05-11 | 1,768.583 | 2,803.000 | 4,745.000 | 42,446.000 | 919.208 |
| 2025-05-12 | 1,272.844 | 2,133.000 | 2,137.000 | 30,548.250 | 612.240 |
| 2025-05-13 | 790.510 | 1,698.000 | 1,698.000 | 18,972.250 | 117.500 |
| 2025-05-14 | 1,028.594 | 2,162.000 | 2,177.000 | 24,686.250 | 286.865 |
| 2025-05-15 | 876.833 | 1,814.000 | 1,887.000 | 21,044.000 | 159.760 |
| 2025-05-16 | 704.354 | 1,491.000 | 1,495.000 | 16,904.500 | 11.958 |
| 2025-05-17 | 317.583 | 569.000 | 2,895.000 | 7,622.000 | 0.000 |
| 2025-05-18 | 1,416.771 | 2,066.000 | 2,067.000 | 34,002.500 | 798.000 |
| 2025-05-19 | 1,060.385 | 1,931.000 | 1,941.000 | 25,449.250 | 367.875 |
| 2025-05-20 | 970.531 | 1,367.250 | 1,630.000 | 23,292.750 | 374.354 |
| 2025-05-21 | 10,058.990 | 10,179.000 | 10,179.000 | 241,415.750 | 9,419.240 |
| 2025-05-22 | 8,446.833 | 8,584.000 | 8,595.000 | 202,724.000 | 7,792.229 |
| 2025-05-23 | 6,808.604 | 6,895.000 | 7,258.000 | 163,406.500 | 6,129.250 |
| 2025-05-24 | 5,406.604 | 5,442.000 | 5,442.000 | 129,758.500 | 4,764.000 |
| 2025-05-25 | 4,350.448 | 4,431.000 | 4,431.000 | 104,410.750 | 3,714.000 |
| 2025-05-26 | 3,408.062 | 3,493.000 | 3,511.000 | 81,793.500 | 2,754.000 |
| 2025-05-27 | 2,533.823 | 2,618.000 | 2,618.000 | 60,811.750 | 1,856.000 |
| 2025-05-28 | 1,761.917 | 1,830.000 | 1,830.000 | 42,286.000 | 1,120.000 |
| 2025-05-29 | 918.740 | 962.000 | 966.000 | 22,049.750 | 272.000 |
| 2025-05-30 | 223.469 | 261.000 | 266.000 | 5,363.250 | 0.000 |
| 2025-05-31 | 210.594 | 329.000 | 329.000 | 5,054.250 | 0.000 |

Time-of-day statistics for every 15-minute slot are in OFFERED_DEMAND_TIME_OF_DAY.csv and the JSON report. Quantiles use linear percentile interpolation and equal slot weights. Counts/GPU-hours sum independent job-day forecast observations; repeated job IDs on different days are not unique real executions.

May-04 offered mean/P95/max: **687.625/1,223.000/1,235.000 GPU**. Offered at 18:00: **308 GPU**, vector [60, 8, 51, 32, 39, 26, 0, 40, 0, 36, 0, 16]; old materialized demand is 624 at that slot. The old May-04 mean is 611.021 (97.920%). Thus relieving queueing can lower late-day demand by completing work earlier.

Across May, old materialized mean is 561.873 GPU. Net offered-minus-old Day-D demand is 1,220,639.000 GPU-hours. The final Q90 queue layer added delays to 705 job-day observations; most waiting was inherited from RW. May-04 has zero added final-layer delays, so merely undoing that layer would leave its 624-GPU queue intact.

## Two allocation rules at each target

A — **LEGACY_SHAPE_SCALE**: common-alpha scaling of the frozen current vector, Hamilton apportionment in 4-GPU nodes.

B — **GENERALIZED_MINIMUM_PLUS_WEIGHTED_RESIDUAL**: reserve 32 GPU at every site (384 total); distribute the remaining `(C_total-384)/4` nodes with Hamilton largest remainders using repository V22SR1 weights. Numeric AIDC order breaks ties. The floor and residual weights are independent of May workload geography. No MW-to-GPU census claim is made.

| Option | Total | Continuous total | AIDC01–12 vector |
|---|---|---|---|
| A75 | 2936 | 2,936.689 | [300, 152, 300, 152, 376, 300, 152, 300, 152, 300, 152, 300] |
| A80 | 2752 | 2,753.146 | [284, 140, 284, 140, 352, 284, 140, 284, 140, 284, 140, 280] |
| A85 | 2592 | 2,591.196 | [268, 132, 268, 132, 332, 268, 132, 268, 132, 264, 132, 264] |
| B75 | 2936 | 2,936.689 | [184, 56, 384, 56, 560, 204, 144, 220, 64, 460, 120, 484] |
| B80 | 2752 | 2,753.146 | [172, 56, 360, 56, 524, 188, 136, 208, 60, 428, 112, 452] |
| B85 | 2592 | 2,591.196 | [164, 52, 336, 52, 488, 180, 132, 196, 56, 404, 108, 424] |

The rounded total is the nearest physically valid multiple of four; allocation conserves this total exactly. Every candidate has minimum >=32 GPU and only complete 4-GPU nodes. Per-site quota errors are in CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json; all 72 site/option rows are in V41R2_AIDC_GPU_CAPACITY_CANDIDATES.csv.

## Aggregate offered-demand occupancy

These ratios include unknown-site D-day offered work; they are not feasible materialized occupancy. A/B share identical aggregate ratios at a given total.

| Target | Mean | P50 | P90 | P95 | P99 | Max | >=90% | >=95% | >=100% |
|---|---|---|---|---|---|---|---|---|---|
| 75% | 75.018% | 42.166% | 185.354% | 285.388% | 345.640% | 452.146% | 27.016% | 26.142% | 24.160% |
| 80% | 80.033% | 44.985% | 197.747% | 304.469% | 368.750% | 482.376% | 30.376% | 27.386% | 26.243% |
| 85% | 84.974% | 47.762% | 209.954% | 323.264% | 391.512% | 512.153% | 30.645% | 30.376% | 27.823% |

No P95 hard threshold is claimed as an industry law. Severe burstiness is visible directly: the 80% point has offered P95/P99 of 304.469%/368.750%.

## A/B resource-only comparison

Fixed D00 RUNNING sources and residuals are preserved. D-day ready PENDING uses service-tier/FIFO, earliest feasible event, whole-gang site/rack capacity, numeric AIDC preference and first logical rack. Current V39D supplies the eligible-site domain/numeric preference; V41R1 supplies event first fit. **This is an explicit resource-only adaptation**, because the production baseline fixes old sites and skips UNASSIGNED; it is not that unchanged routine nor a global-placement-optimality certificate. Newly assigned PENDING sites are generated only after candidate capacity is specified. No policy/grid/temporal-flexibility/migration optimization is run.

| Option | Materialized mean | P95 | P99 | 12/12 FULL | >=10 FULL | Unstarted jobs | Unserved offered GPUh | Weight L1 |
|---|---|---|---|---|---|---|---|---|
| A75 | 50.186% | 99.966% | 100.000% | 4.570% | 5.880% | 708 | 523,296.000 | 0.512 |
| A80 | 51.955% | 100.000% | 100.000% | 5.410% | 8.098% | 766 | 554,592.000 | 0.509 |
| A85 | 54.020% | 100.000% | 100.000% | 12.063% | 13.206% | 840 | 572,806.000 | 0.511 |
| B75 | 50.505% | 100.000% | 100.000% | 7.224% | 9.241% | 702 | 515,712.000 | 0.095 |
| B80 | 52.043% | 100.000% | 100.000% | 6.485% | 8.468% | 762 | 551,520.000 | 0.099 |
| B85 | 53.638% | 100.000% | 100.000% | 10.383% | 12.030% | 836 | 580,206.000 | 0.106 |

All six have valid gang/rack envelopes and fit immutable running reservations. The largest pending gang is 256 GPU and has compatible sites under each candidate. An additional 14 ambiguous D00 source observations / 11 GPU-hours remain separate, with no fabricated physical source. Remaining D-day pending counts mean resource starts at/after120; they are capacity-induced unserved demand, not true nominal future arrivals.

## Whole-job destination headroom

Empirical P50/P90 GPU request sizes are **1/2 GPU**, counted over frozen job-day observations. Additional 4/8/16/32/60/128/256-GPU representative gangs are retained. Instantaneous GPU/rack acceptance only; source exclusion, full-duration reservation, WAN and electrical safety are not claimed.

| Option | GPU | >=1 destination | >=2 | >=3 |
|---|---|---|---|---|
| A75 | 1 | 95.430% | 94.489% | 94.120% |
| A75 | 2 | 94.456% | 94.321% | 94.086% |
| A75 | 4 | 94.456% | 94.288% | 94.019% |
| A75 | 8 | 92.977% | 92.742% | 91.667% |
| A75 | 16 | 92.406% | 89.785% | 88.609% |
| A75 | 32 | 76.647% | 74.294% | 71.337% |
| A75 | 60 | 75.470% | 69.153% | 69.153% |
| A75 | 128 | 73.723% | 69.153% | 67.003% |
| A75 | 256 | 58.737% | 46.371% | 32.392% |
| A80 | 1 | 94.590% | 93.481% | 91.902% |
| A80 | 2 | 94.288% | 93.011% | 91.667% |
| A80 | 4 | 92.742% | 91.599% | 90.759% |
| A80 | 8 | 91.163% | 88.945% | 88.642% |
| A80 | 16 | 88.911% | 88.239% | 87.265% |
| A80 | 32 | 69.960% | 69.657% | 69.321% |
| A80 | 60 | 69.422% | 69.153% | 69.052% |
| A80 | 128 | 69.153% | 69.019% | 62.030% |
| A80 | 256 | 55.141% | 36.559% | 26.512% |
| A85 | 1 | 87.937% | 87.063% | 86.794% |
| A85 | 2 | 87.130% | 86.962% | 86.660% |
| A85 | 4 | 87.030% | 86.828% | 85.786% |
| A85 | 8 | 84.341% | 82.829% | 81.922% |
| A85 | 16 | 83.501% | 78.293% | 72.245% |
| A85 | 32 | 69.288% | 69.019% | 69.019% |
| A85 | 60 | 69.019% | 69.019% | 69.019% |
| A85 | 128 | 69.019% | 68.179% | 61.458% |
| A85 | 256 | 48.185% | 28.293% | 18.044% |
| B75 | 1 | 92.776% | 91.465% | 90.759% |
| B75 | 2 | 91.801% | 91.364% | 90.625% |
| B75 | 4 | 91.767% | 90.894% | 90.524% |
| B75 | 8 | 90.222% | 89.113% | 88.239% |
| B75 | 16 | 89.953% | 87.433% | 85.618% |
| B75 | 32 | 74.160% | 73.320% | 73.017% |
| B75 | 60 | 73.723% | 69.153% | 69.153% |
| B75 | 128 | 72.379% | 69.153% | 60.618% |
| B75 | 256 | 69.153% | 68.313% | 51.075% |
| B80 | 1 | 93.515% | 91.566% | 91.532% |
| B80 | 2 | 92.574% | 91.532% | 91.499% |
| B80 | 4 | 92.574% | 91.532% | 91.431% |
| B80 | 8 | 91.163% | 88.844% | 88.474% |
| B80 | 16 | 89.281% | 87.634% | 85.652% |
| B80 | 32 | 70.867% | 69.792% | 69.556% |
| B80 | 60 | 69.153% | 69.019% | 69.019% |
| B80 | 128 | 69.153% | 68.179% | 56.082% |
| B80 | 256 | 69.153% | 65.222% | 50.235% |
| B85 | 1 | 89.617% | 88.474% | 87.970% |
| B85 | 2 | 88.710% | 88.374% | 87.870% |
| B85 | 4 | 88.609% | 88.172% | 87.802% |
| B85 | 8 | 86.996% | 86.626% | 85.887% |
| B85 | 16 | 85.820% | 85.484% | 82.258% |
| B85 | 32 | 69.019% | 69.019% | 66.667% |
| B85 | 60 | 69.019% | 68.179% | 66.667% |
| B85 | 128 | 69.019% | 65.222% | 53.259% |
| B85 | 256 | 69.019% | 60.719% | 46.102% |

## Per-site occupancy and headroom

### A75: LEGACY_SHAPE_SCALE

| AIDC | Mean | P90 | P95 | P99 | Max | FULL | Spare mean | Spare P10/P50 | Headroom GPUh |
|---|---|---|---|---|---|---|---|---|---|
| AIDC01 | 68.809% | 100.000% | 100.000% | 100.000% | 100.000% | 18.347% | 93.574 | 0.000/25.000 | 69,619.000 |
| AIDC02 | 59.582% | 100.000% | 100.000% | 100.000% | 100.000% | 21.270% | 61.435 | 0.000/24.000 | 45,708.000 |
| AIDC03 | 58.279% | 100.000% | 100.000% | 100.000% | 100.000% | 21.237% | 125.162 | 0.000/51.000 | 93,120.250 |
| AIDC04 | 51.836% | 100.000% | 100.000% | 100.000% | 100.000% | 23.555% | 73.210 | 0.000/58.000 | 54,468.250 |
| AIDC05 | 55.618% | 100.000% | 100.000% | 100.000% | 100.000% | 15.961% | 166.876 | 0.000/136.000 | 124,155.750 |
| AIDC06 | 56.039% | 100.000% | 100.000% | 100.000% | 100.000% | 14.113% | 131.882 | 0.000/99.000 | 98,120.000 |
| AIDC07 | 42.513% | 100.000% | 100.000% | 100.000% | 100.000% | 17.272% | 87.381 | 0.000/120.000 | 65,011.250 |
| AIDC08 | 44.435% | 99.667% | 100.000% | 100.000% | 100.000% | 9.577% | 166.694 | 1.000/236.000 | 124,020.250 |
| AIDC09 | 37.724% | 100.000% | 100.000% | 100.000% | 100.000% | 11.794% | 94.660 | 0.000/120.000 | 70,426.750 |
| AIDC10 | 37.942% | 100.000% | 100.000% | 100.000% | 100.000% | 11.962% | 186.173 | 0.000/236.500 | 138,513.000 |
| AIDC11 | 38.682% | 100.000% | 100.000% | 100.000% | 100.000% | 13.206% | 93.203 | 0.000/120.000 | 69,342.750 |
| AIDC12 | 39.237% | 100.000% | 100.000% | 100.000% | 100.000% | 10.988% | 182.290 | 0.000/238.000 | 135,624.000 |

Sites with positive headroom at every slot: 0. Destination-count distribution (count: slots): `{"0": 136, "1": 28, "2": 11, "3": 18, "4": 56, "5": 51, "6": 87, "7": 118, "8": 166, "9": 99, "10": 129, "11": 285, "12": 1792}`.

### A80: LEGACY_SHAPE_SCALE

| AIDC | Mean | P90 | P95 | P99 | Max | FULL | Spare mean | Spare P10/P50 | Headroom GPUh |
|---|---|---|---|---|---|---|---|---|---|
| AIDC01 | 69.702% | 100.000% | 100.000% | 100.000% | 100.000% | 17.137% | 86.046 | 0.000/27.000 | 64,018.500 |
| AIDC02 | 62.793% | 100.000% | 100.000% | 100.000% | 100.000% | 23.253% | 52.090 | 0.000/13.000 | 38,755.250 |
| AIDC03 | 58.827% | 100.000% | 100.000% | 100.000% | 100.000% | 24.597% | 116.932 | 0.000/30.000 | 86,997.500 |
| AIDC04 | 54.164% | 100.000% | 100.000% | 100.000% | 100.000% | 24.261% | 64.171 | 0.000/44.000 | 47,743.000 |
| AIDC05 | 55.756% | 100.000% | 100.000% | 100.000% | 100.000% | 19.590% | 155.738 | 0.000/93.000 | 115,869.250 |
| AIDC06 | 56.395% | 100.000% | 100.000% | 100.000% | 100.000% | 19.288% | 123.839 | 0.000/140.000 | 92,136.000 |
| AIDC07 | 48.138% | 100.000% | 100.000% | 100.000% | 100.000% | 14.516% | 72.607 | 0.000/96.000 | 54,019.500 |
| AIDC08 | 46.779% | 100.000% | 100.000% | 100.000% | 100.000% | 11.122% | 151.148 | 0.000/220.000 | 112,454.250 |
| AIDC09 | 42.855% | 100.000% | 100.000% | 100.000% | 100.000% | 11.492% | 80.003 | 0.000/108.000 | 59,522.250 |
| AIDC10 | 40.460% | 99.296% | 100.000% | 100.000% | 100.000% | 8.804% | 169.094 | 2.000/220.000 | 125,805.750 |
| AIDC11 | 39.651% | 100.000% | 100.000% | 100.000% | 100.000% | 13.844% | 84.488 | 0.000/108.000 | 62,859.250 |
| AIDC12 | 40.696% | 100.000% | 100.000% | 100.000% | 100.000% | 12.970% | 166.052 | 0.000/217.500 | 123,542.750 |

Sites with positive headroom at every slot: 0. Destination-count distribution (count: slots): `{"0": 161, "1": 33, "2": 47, "3": 23, "4": 22, "5": 46, "6": 73, "7": 123, "8": 159, "9": 109, "10": 92, "11": 308, "12": 1780}`.

### A85: LEGACY_SHAPE_SCALE

| AIDC | Mean | P90 | P95 | P99 | Max | FULL | Spare mean | Spare P10/P50 | Headroom GPUh |
|---|---|---|---|---|---|---|---|---|---|
| AIDC01 | 70.743% | 100.000% | 100.000% | 100.000% | 100.000% | 28.931% | 78.408 | 0.000/20.000 | 58,335.500 |
| AIDC02 | 66.783% | 100.000% | 100.000% | 100.000% | 100.000% | 32.392% | 43.847 | 0.000/8.000 | 32,622.000 |
| AIDC03 | 62.777% | 100.000% | 100.000% | 100.000% | 100.000% | 27.722% | 99.757 | 0.000/20.000 | 74,219.500 |
| AIDC04 | 56.552% | 100.000% | 100.000% | 100.000% | 100.000% | 29.469% | 57.351 | 0.000/31.000 | 42,669.250 |
| AIDC05 | 56.896% | 100.000% | 100.000% | 100.000% | 100.000% | 25.941% | 143.107 | 0.000/96.000 | 106,471.250 |
| AIDC06 | 56.585% | 100.000% | 100.000% | 100.000% | 100.000% | 24.261% | 116.351 | 0.000/171.000 | 86,565.500 |
| AIDC07 | 52.770% | 100.000% | 100.000% | 100.000% | 100.000% | 24.395% | 62.343 | 0.000/88.000 | 46,383.500 |
| AIDC08 | 50.198% | 100.000% | 100.000% | 100.000% | 100.000% | 17.910% | 133.469 | 0.000/204.000 | 99,300.750 |
| AIDC09 | 43.450% | 100.000% | 100.000% | 100.000% | 100.000% | 15.289% | 74.646 | 0.000/100.000 | 55,536.500 |
| AIDC10 | 41.319% | 100.000% | 100.000% | 100.000% | 100.000% | 16.398% | 154.917 | 0.000/200.000 | 115,258.250 |
| AIDC11 | 42.790% | 100.000% | 100.000% | 100.000% | 100.000% | 16.431% | 75.517 | 0.000/100.000 | 56,184.500 |
| AIDC12 | 42.390% | 100.000% | 100.000% | 100.000% | 100.000% | 18.112% | 152.091 | 0.000/200.000 | 113,156.000 |

Sites with positive headroom at every slot: 0. Destination-count distribution (count: slots): `{"0": 359, "1": 26, "2": 8, "3": 19, "4": 77, "5": 80, "6": 103, "7": 55, "8": 117, "9": 89, "10": 168, "11": 266, "12": 1609}`.

### B75: GENERALIZED_MINIMUM_PLUS_WEIGHTED_RESIDUAL

| AIDC | Mean | P90 | P95 | P99 | Max | FULL | Spare mean | Spare P10/P50 | Headroom GPUh |
|---|---|---|---|---|---|---|---|---|---|
| AIDC01 | 69.463% | 100.000% | 100.000% | 100.000% | 100.000% | 18.481% | 56.189 | 0.000/23.000 | 41,804.500 |
| AIDC02 | 62.458% | 100.000% | 100.000% | 100.000% | 100.000% | 31.015% | 21.024 | 0.000/24.000 | 15,641.500 |
| AIDC03 | 62.429% | 100.000% | 100.000% | 100.000% | 100.000% | 34.879% | 144.273 | 0.000/40.000 | 107,338.750 |
| AIDC04 | 52.418% | 100.000% | 100.000% | 100.000% | 100.000% | 24.496% | 26.646 | 0.000/24.000 | 19,824.750 |
| AIDC05 | 55.817% | 100.000% | 100.000% | 100.000% | 100.000% | 25.840% | 247.426 | 0.000/165.000 | 184,085.000 |
| AIDC06 | 61.212% | 100.000% | 100.000% | 100.000% | 100.000% | 20.262% | 79.127 | 0.000/51.500 | 58,870.500 |
| AIDC07 | 51.553% | 100.000% | 100.000% | 100.000% | 100.000% | 20.665% | 69.764 | 0.000/78.000 | 51,904.500 |
| AIDC08 | 49.950% | 100.000% | 100.000% | 100.000% | 100.000% | 14.180% | 110.111 | 0.000/156.000 | 81,922.250 |
| AIDC09 | 55.302% | 100.000% | 100.000% | 100.000% | 100.000% | 33.300% | 28.607 | 0.000/32.000 | 21,283.500 |
| AIDC10 | 37.042% | 100.000% | 100.000% | 100.000% | 100.000% | 10.786% | 289.605 | 0.000/396.000 | 215,466.000 |
| AIDC11 | 37.808% | 100.000% | 100.000% | 100.000% | 100.000% | 11.895% | 74.631 | 0.000/88.000 | 55,525.250 |
| AIDC12 | 36.825% | 100.000% | 100.000% | 100.000% | 100.000% | 12.534% | 305.768 | 0.000/421.500 | 227,491.250 |

Sites with positive headroom at every slot: 0. Destination-count distribution (count: slots): `{"0": 215, "1": 39, "2": 21, "3": 28, "4": 36, "5": 69, "6": 81, "7": 189, "8": 101, "9": 217, "10": 247, "11": 466, "12": 1267}`.

### B80: GENERALIZED_MINIMUM_PLUS_WEIGHTED_RESIDUAL

| AIDC | Mean | P90 | P95 | P99 | Max | FULL | Spare mean | Spare P10/P50 | Headroom GPUh |
|---|---|---|---|---|---|---|---|---|---|
| AIDC01 | 70.917% | 100.000% | 100.000% | 100.000% | 100.000% | 24.395% | 50.022 | 0.000/16.000 | 37,216.500 |
| AIDC02 | 63.436% | 100.000% | 100.000% | 100.000% | 100.000% | 32.460% | 20.476 | 0.000/20.000 | 15,234.000 |
| AIDC03 | 64.278% | 100.000% | 100.000% | 100.000% | 100.000% | 23.824% | 128.600 | 0.000/27.000 | 95,678.750 |
| AIDC04 | 54.353% | 100.000% | 100.000% | 100.000% | 100.000% | 28.259% | 25.562 | 0.000/24.000 | 19,018.250 |
| AIDC05 | 55.009% | 100.000% | 100.000% | 100.000% | 100.000% | 21.707% | 235.755 | 0.000/96.000 | 175,402.000 |
| AIDC06 | 61.078% | 100.000% | 100.000% | 100.000% | 100.000% | 21.001% | 73.173 | 0.000/28.000 | 54,441.000 |
| AIDC07 | 53.239% | 100.000% | 100.000% | 100.000% | 100.000% | 20.531% | 63.595 | 0.000/48.000 | 47,315.000 |
| AIDC08 | 54.661% | 100.000% | 100.000% | 100.000% | 100.000% | 15.591% | 94.306 | 0.000/144.000 | 70,163.500 |
| AIDC09 | 49.302% | 100.000% | 100.000% | 100.000% | 100.000% | 14.550% | 30.419 | 0.000/28.000 | 22,631.500 |
| AIDC10 | 40.719% | 99.299% | 100.000% | 100.000% | 100.000% | 9.442% | 253.721 | 3.000/364.000 | 188,768.250 |
| AIDC11 | 41.525% | 100.000% | 100.000% | 100.000% | 100.000% | 12.601% | 65.492 | 0.000/80.000 | 48,726.000 |
| AIDC12 | 38.353% | 100.000% | 100.000% | 100.000% | 100.000% | 12.500% | 278.644 | 0.000/388.000 | 207,311.250 |

Sites with positive headroom at every slot: 0. Destination-count distribution (count: slots): `{"0": 193, "1": 58, "2": 1, "3": 21, "4": 46, "5": 122, "6": 75, "7": 71, "8": 179, "9": 102, "10": 156, "11": 535, "12": 1417}`.

### B85: GENERALIZED_MINIMUM_PLUS_WEIGHTED_RESIDUAL

| AIDC | Mean | P90 | P95 | P99 | Max | FULL | Spare mean | Spare P10/P50 | Headroom GPUh |
|---|---|---|---|---|---|---|---|---|---|
| AIDC01 | 70.853% | 100.000% | 100.000% | 100.000% | 100.000% | 28.461% | 47.801 | 0.000/15.000 | 35,563.750 |
| AIDC02 | 64.798% | 100.000% | 100.000% | 100.000% | 100.000% | 30.914% | 18.305 | 0.000/14.000 | 13,619.000 |
| AIDC03 | 67.472% | 100.000% | 100.000% | 100.000% | 100.000% | 25.638% | 109.295 | 0.000/16.000 | 81,315.750 |
| AIDC04 | 57.923% | 100.000% | 100.000% | 100.000% | 100.000% | 25.773% | 21.880 | 0.000/20.000 | 16,278.750 |
| AIDC05 | 55.533% | 100.000% | 100.000% | 100.000% | 100.000% | 24.294% | 216.998 | 0.000/92.000 | 161,446.500 |
| AIDC06 | 61.642% | 100.000% | 100.000% | 100.000% | 100.000% | 22.614% | 69.045 | 0.000/26.000 | 51,369.500 |
| AIDC07 | 55.595% | 100.000% | 100.000% | 100.000% | 100.000% | 22.312% | 58.615 | 0.000/32.000 | 43,609.500 |
| AIDC08 | 59.467% | 100.000% | 100.000% | 100.000% | 100.000% | 21.707% | 79.444 | 0.000/103.000 | 59,106.500 |
| AIDC09 | 57.292% | 100.000% | 100.000% | 100.000% | 100.000% | 23.925% | 23.916 | 0.000/24.000 | 17,793.750 |
| AIDC10 | 41.604% | 100.000% | 100.000% | 100.000% | 100.000% | 12.836% | 235.918 | 0.000/340.000 | 175,523.000 |
| AIDC11 | 41.807% | 100.000% | 100.000% | 100.000% | 100.000% | 16.163% | 62.848 | 0.000/76.000 | 46,759.000 |
| AIDC12 | 39.236% | 100.000% | 100.000% | 100.000% | 100.000% | 17.843% | 257.638 | 0.000/360.000 | 191,683.000 |

Sites with positive headroom at every slot: 0. Destination-count distribution (count: slots): `{"0": 309, "1": 34, "2": 15, "3": 22, "4": 55, "5": 108, "6": 46, "7": 56, "8": 176, "9": 166, "10": 152, "11": 421, "12": 1416}`.

## May-04 18:00 and reference queue changes

| AIDC | Before spare | A75 | A80 | A85 | B75 | B80 | B85 |
|---|---|---|---|---|---|---|---|
| AIDC01 | 0 | 240 | 224 | 208 | 124 | 112 | 104 |
| AIDC02 | 0 | 144 | 132 | 124 | 48 | 48 | 44 |
| AIDC03 | 0 | 249 | 233 | 217 | 333 | 309 | 285 |
| AIDC04 | 0 | 120 | 108 | 100 | 24 | 24 | 20 |
| AIDC05 | 0 | 337 | 313 | 293 | 521 | 485 | 449 |
| AIDC06 | 0 | 274 | 258 | 242 | 178 | 162 | 154 |
| AIDC07 | 0 | 152 | 140 | 132 | 144 | 136 | 132 |
| AIDC08 | 0 | 260 | 244 | 228 | 180 | 168 | 156 |
| AIDC09 | 0 | 152 | 140 | 132 | 64 | 60 | 56 |
| AIDC10 | 0 | 264 | 248 | 228 | 424 | 392 | 368 |
| AIDC11 | 0 | 152 | 140 | 132 | 120 | 112 | 108 |
| AIDC12 | 0 | 284 | 264 | 248 | 468 | 436 | 408 |

Old May-04 critical-slot demand is624; offered demand is308. Extra capacity permits earlier completion. Critical-slot headroom is useful but does not negate monthly bursts.

| Metric | A75 | A80 | A85 | B75 | B80 | B85 |
|---|---|---|---|---|---|---|
| reference_jobs_no_longer_delayed | 22,734.000 | 22,059.000 | 21,262.000 | 22,669.000 | 21,984.000 | 21,372.000 |
| start_change_jobs | 36,576.000 | 36,576.000 | 36,575.000 | 36,576.000 | 36,576.000 | 36,576.000 |
| newly_admitted_former_UNASSIGNED | 24,889.000 | 24,831.000 | 24,757.000 | 24,895.000 | 24,835.000 | 24,761.000 |
| queue_reduction_job_hours | 2,152,135.750 | 2,144,976.750 | 2,134,613.000 | 2,151,769.500 | 2,145,006.500 | 2,136,521.250 |
| queue_reduction_GPU_hours | 12,031,339.750 | 11,876,021.000 | 11,792,689.250 | 12,053,569.750 | 11,897,560.750 | 11,762,660.500 |
| same_day_completions_old | 11,235.000 | 11,235.000 | 11,235.000 | 11,235.000 | 11,235.000 | 11,235.000 |
| same_day_completions_new | 36,263.000 | 36,262.000 | 36,252.000 | 36,263.000 | 36,262.000 | 36,253.000 |
| D24_running_old | 8,631.000 | 8,631.000 | 8,631.000 | 8,631.000 | 8,631.000 | 8,631.000 |
| D24_running_new | 8,501.000 | 8,444.000 | 8,380.000 | 8,507.000 | 8,448.000 | 8,383.000 |
| old_carryout_GPU_hours | 2,179,798.500 | 2,179,798.500 | 2,179,798.500 | 2,179,798.500 | 2,179,798.500 | 2,179,798.500 |
| new_carryout_GPU_hours | 1,501,577.000 | 1,534,067.000 | 1,556,086.250 | 1,494,605.500 | 1,532,249.750 | 1,563,451.750 |

Full per-job evidence is compressed in A_B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv.gz and B_B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv.gz. The combined NPZ identifies A75/A80/A85/B75/B80/B85 explicitly. Independent days do not propagate synthetic carry to the next day.

## Allocation recommendation and capacity HOLD

Recommend **B as the generalized relative-capacity allocation rule**. At75%, total-share L1 distortion from V22SR1 falls from0.511796 (A) to0.094902 (B), while the32-GPU minimum remains. B also leaves slightly fewer unstarted jobs at each total. This does not mean B dominates: at75%, A has lower simultaneous saturation and more32-GPU destination availability. B is selected for physical relative-scale fidelity with an explicit service floor, not for favorable policy or realized-site outcomes.

**No tested total/vector is recommended for application.** Even B75, the largest and least-backlogged B comparison, leaves702 pending observations and515,712 offered GPU-hours without a Day-D start. Its offered saturation remains24.160% of slots. B80 leaves762; B85 leaves836. The mean-size/peak-service tradeoff must be resolved before a new installed authority is frozen. No untested larger capacity or changed terminal/WAN contract is silently substituted.

## Power, electrical coefficients, H4 and WAN dependencies

Power CASE2: installed capacity contributes104.1606964512843 W idle/GPU; active swing547.7239090195797 W/GPU. Both A/B totals add idle IT power of240.820/221.654/204.988 kW for75/80/85%. Site allocation changes its geographic distribution. GPU-to-PCC tables use the unchanged C1/weather model and PF0.95; no extra historical PUE1.30 multiplication. No physical rack census is available; four nonadditive logical pools/site stay, but their capacity envelopes must be refrozen.

GPU/rack authority,624-specific aggregate power bounds/conservation, all31-day power tables, H4 physical/actionable capacity fields, B0 materialization and descendant manifests require propagation. Current dedicated PCC ratings are500 kVA/phase and208.179184 A/phase; shared feeder constraints still apply.

Electrical class **A conditional exact numerical equivalence**: existing AC coefficients use an immutable exogenous anchor, not rematerialized B0 or GPU count. No numerical regeneration is required if that anchor and all generation inputs stay identical; capacity-dependent power tables are built afterward. Context provenance/reuse must be recertified. If the anchor is recentered, **full31-day regeneration** is required. No coefficients were regenerated and no expanded-load Fresh safety is claimed here. See GPU_CAPACITY_DEPENDENCY_GRAPH.md and dependency JSONs.

GPU headroom cannot repair UID-serialized WAN waits or D24 service-shift semantics. The resource study already exhibits material backlog with migration/WAN optimization absent. That contract audit remains separate.

## Validation, provenance and scope

31/31 current B0 tables reproduced exactly with the unmodified baseline. Offered total reconciles exactly to known-site plus UNASSIGNED components and independently counted job-interval GPU-hours. All six candidate interval sweeps conserve resources and satisfy gang/rack limits. Critical May04 and heavy May21 repeat exactly for each vector. Source/forecast causality and Q90 duration identities are checked. PR_PACKAGE_VERIFICATION.json provides a portable read-only check of saved results; raw-authority replay still requires the external frozen source/forecast files referenced by manifests.

The initial A-only audit is superseded by this six-candidate report. The pre-existing Git worktree was separately committed as a6ba216 after audit interruption; source/evidence byte preservation is verified separately from this expected Git metadata change. No claim of unchanged Git HEAD across that external PR work is made.
