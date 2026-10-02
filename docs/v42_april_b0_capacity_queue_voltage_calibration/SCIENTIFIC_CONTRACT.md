# Scientific contract

CC4 is not a four-hour model. It supplies 24 hourly Q50/Q90 future-arrival
lifetime GPUh values. Its frozen execution-lag kernel and ML predictions stay
unchanged. Only capacity-caused forward admission backlog is added, with full
GPUh and original kernel-tail conservation. No workload advance or drop.

Planning RUNNING nominal remaining is max(Q50_total - elapsed, 0). Expired Q50
retains observed physical placement at the issue instant, but no infinite nominal
future reservation. Statistical overrun exposure uses the existing signed Q50
completion origin, gamma and frozen survival kernel. Reserve is a headroom KPI,
not realized IT/PCC load and not a new scientific objective.

Actual retains physical RUNNING until causal completion/release. Submitted jobs
wait under deterministic strict FCFS and first capacity-feasible ascending AIDC
placement, without backfill. Queue waiting is physical admission, not optimized
timeshift, migration, grid-aware relocation or P/Q/schedule voltage repair.
Realized service duration is private environment truth; controller/job views
cannot receive future end/runtime. Pending completion is simulated admission
plus uniquely source-backed realized duration, following the audited current
May-lineage counterfactual execution primitive. Missing actual duration stops the
campaign; requested walltime, Q50 and invented zero cannot replace it.

Primary voltage evidence is Planning surrogate magnitude pu versus D-Day Fresh
OpenDSS magnitude pu. Compare exactly aligned day/node/phase/slot axes after
sqrt conversion where the surrogate stores voltage squared. Primary band is
0.95–1.05 pu. No operational Day-Ahead AC stage or required DA diagnostic.
Empirical quantiles use the fixed higher method. Violating days remain present.
FINAL_MARGIN_ACCEPTED=false and PROBLEM13_FINAL_VALIDATED=false. B1/B2/B3,
May scientific runs, M1/A2/M2 and PR124 imports remain off.
