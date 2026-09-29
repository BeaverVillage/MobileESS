# PR79 reconciliation attempt

Read-only join of all 242,842 source job-days, not a chosen favorable date. `EPISODE_RESOURCE_RECONCILIATION.json` hashes the local 26,586-row conflict/source join. State-pair keys in that JSON are **(current state, prior state)**.

- Duplicate (day,episode) rows: 0.
- Conflicting site/time segments: 321; contribution rows: 26586.
- PENDING→PENDING: 18,838; PENDING→RUNNING: 7,512; RUNNING→RUNNING: 236 contribution rows.
- New-placement overlap rows: 0. Continuing invalid state is detected before new admission.
- Expired PENDING reservation job-days: 28,025.
- PENDING→RUNNING transitions: 16,266; 4,670 have comparable old assigned start. Observed start is later in 3,234 and earlier in 1,436; none matches exactly. 4,711 conflict contribution rows have a later observed start than the prior counterfactual start.

Source inspection rejects A (stale RUNNING reservation stacked with current execution) and B (duplicate logical episode) as an implemented double-count bug. PR79 rebuilds current intervals and replaces RUNNING remaining service at the preserved site. The demonstrated cause is mismatch between counterfactual planned start/reservation and later causal execution inside synthetic site mapping. This is an inconsistency under the current native representation, not evidence that raw Kestrel scheduling violated its physical cluster.

C: no causal requeue/restart receipt resolves expired PENDING starts. D: requested-duration reservations may be conservative, but future realized runtime cannot authorize shortening them; no approved unknown runtime provider is available. E/F: continuing occupancy still exceeds current assigned-site capacity. No supported completion/requeue/mapping transaction was found that removes those conflicts legally. Diagnosis is not a claim that every segment has a unique physical causal explanation.

Reconciliation code closes independent-day ledger semantics and refuses unsupported releases. Actual physical conflicts resolved: **0**. No site/GPU/service changes, drops, invented completion or requeue. Apr01 has 664 rows, 582 capacity-feasible rows and 82 other/nonphysical rows; its stored day-ready flag is true, but that alone does not establish final native service/kernel/security/provider authority. No alternative easier date was substituted.

Required next evidence: causal execution/requeue/completion mapping or a separately validated reference allocation authority preserving all obligations, plus approved duration/start-window authorities. Oversize jobs remain out of domain; no legacy >100-GPU virtual capacity, clipping or gang splitting is promoted.
