# Restricted master

For each movable job j: lambda_jp >= 0 and sum_p lambda_jp = 1.
True PR99 singletons have no lambda. All production master variables are
continuous. No global y/q/w/f0/f1/r0/h/r1 families are created.

The implemented row orientation is:

```
known_GPU[k,t] - sum(GPU_jp[k,t] lambda_jp) = immutable_GPU + singleton_GPU
runtime_target[k,t] - sum(RISK_jp[k,t] lambda_jp) = expired_RUNNING_risk + singleton_risk
sum(WAN_jp[l,t] lambda_jp) <= WAN_capacity - immutable_WAN - singleton_WAN
sum(ACTIVE_jp[t] lambda_jp) <= max_active - immutable_active - singleton_active
metric[n] - sum(metric_jp[n] lambda_jp) = singleton_metric[n]
```

Known GPU bounds preserve capacities through the entire authorized tail. Runtime
risk is computed by the PR99 completion adjustment and frozen risk_exposure()
on slots 24..119. Native planning_grid() is called unchanged: PR97 CC4 nominal
and Q90 reserve service timing, depletion/work conservation/carryout/reference
deviation, anonymous site partition, headroom and Runtime/CC4 shortfalls; C1 power
and the original voltage, line thermal faces, transformer and rho rows. Reserve
occupancy is not electrical load. A1 keeps inherited zero MESS P/Q anchors.

Scientific levels are rho, reserve shortfall, CC4 reference deviation, migration
count, shift slots and prestart changes. After each complete pricing certificate,
an upper lock is added with tolerance 1e-7 for rho, 1e-8 otherwise. Final
deterministic tie uses the sum of inherited PR99 selected event ranks, computed
as metadata with no event variables. It runs only after all six scientific levels.

All column objectives are zero: objective expressions use global or balanced
metric variables. A new column therefore has zero direct coefficients in every
objective lock. The metric-balance dual propagates the effect of intervention
and tie locks. GPU/risk balance duals propagate reserve, grid and rho values.
`PhysicalColumn.master_coefficients()` is the sole registry for insertion, manual
RC, factorized arc costs and audit. There are no omitted nonzero lock terms.

For Gurobi minimization convention, RC = c_p - sum_i Pi_i A_ip. Here c_p=0:
GPU/risk contribute +Pi times profile; WAN/active contribute -Pi times usage;
convexity contributes -alpha_j; metric balances contribute +Pi times metric.
Arc costs obtain these signs by probing the same coefficient registry. The RC
test clones the optimal RMP, preserves its basis, inserts a new column fixed at
zero and uses dual simplex without presolve. It compares both the original-dual
manual RC and cloned reported RC, and records any dual drift.
