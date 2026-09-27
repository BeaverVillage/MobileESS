V41R4 standby eligibility was often conflated with executable temporal flexibility. This offline study reproduces the exact 47,009 job-day gate and all 31 restored candidate manifests, then compares preregistered TRAIN-only latency rules without modifying production.

| Rule | Flexible job-days | Jobs % | Flexible GPUh | GPUh % | Incremental PCC kWh | PCC % | Added job-days / GPUh |
|---|---:|---:|---:|---:|---:|---:|---:|
| R0 | 1,611 | 3.427003 | 17,273.50 | 3.453156 | 9,461.109778 | 2.496910 | 0 / 0.00 |
| R1 | 1,611 | 3.427003 | 17,273.50 | 3.453156 | 9,461.109778 | 2.496910 | 0 / 0.00 |
| R2 | 1,568 | 3.335531 | 17,217.00 | 3.441861 | 9,430.163377 | 2.488742 | 0 / 0.00 |

The primary table uses a conservative single-job capacity witness with all other jobs fixed. The original production temporal domain is 10.433886% GPUh; the literal gate is 28.760644%. These are reported separately, with exact frozen-C1 incremental PCC attribution. R1 adds nothing because all 456 otherwise eligible in-day normal records cross D24 and have zero terminal-preserving delay; R2 tightens standby budgets. No threshold was changed after evaluation. Retain R0.

Validation: 8 contract tests; independent reproduction of 141,027 membership records and 139,061 options; original terminal formulas; 228 source hashes; exact baseline GPU occupancy and PCC reproduction. All fixed/admitted populations, full service and spatial/migration rights remain present. No optimizer, runtime model, ML, CC4, traffic, grid, MESS, Actual or V42 coordinator was executed or changed.

Limitations: observed queue is not an SLA, historical request versions remain unverified, single-job alternatives are not a joint schedule, and May is previously exposed. Full raw-period eligibility is unavailable: ALL_AVAILABLE means all 31 frozen V41R4 May dates, not the entire raw trace. This draft explicitly records that unmet coverage requirement and does not recommend production latency-rule promotion.

Scope: only `docs/v42_aidc_workload_flexibility/`, based on the frozen V41R4 evidence branch. External raw/frozen archives are SHA-bound dependencies. Registration precedes evaluation in git history.
