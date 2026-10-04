# Discovery quota controller

`DiscoveryController` is an opt-in per-MESS adapter. The same immutable DiscoverySnapshot
must be created from the completed RMP before all worker jobs are dispatched.
It includes true/smoothed coupling duals, both convexity dual vectors, alpha, RMP objective,
iteration and exact PR143-compatible dual SHAs. Tuples detach the snapshot from source arrays.

Inside MIPSOL, the adapter performs the existing PR143 block physical validator,
the complete original-local corrected-row/integrality audit, and exact_rc under the true
same-iteration dual. Search RC and the native objective must also agree within 1e-8.
Only distinct PR143 column SHA values that are legal, true RC <= -1e-7, and absent from
the retained MESS set fill the quota. Hash identity uses the original x/a/c hash function.
MESS ownership is carried separately; axis identity prevents cross-MESS cache reuse.

After four accepted columns, terminate() is requested once and acceptance is frozen.
The reason is DISCOVERY_QUOTA_FILLED. Any callback exception aborts and clears addable
results. Errors, duplicates, nonintegral points and smoothed-only negatives never fill quota.
Discovery receipts always set optimality, convergence, valid_bound and no-negative claims false.
INTERRUPTED (11) is expected; it is never promoted to OPTIMAL (2).
Caller cancellation must still be combined with this callback by the integrating worker.

DW_EARLY_STOP_FIXTURE.json uses a synthetic 586-variable, 2-row model with ten selector
profiles and the real PR143 96-slot idle-route/SOC/PCS validators. Nine profiles are valid
true-negative trajectories; one is negative only under the smoothed dual. Ten feasible
MIP starts expose native MIPSOL observations without fixing or restricting the domain.
Early/continued models have identical matrix, bounds and objective identities.
Quota run status=11, accepted=4;
continued status=2. All added columns passed original audits.

The quota request occurred at callback 5.
Gurobi issued 5 further callbacks while completing
start processing; the controller added no more columns. Termination is cooperative.
Measured wall times: early 0.038957 s, continued 0.025133 s.
This toy does not establish a runtime benefit or production speedup. It proves safe acceptance
and terminal semantics. Production callback latency and solver-thread interaction remain
integration measurements for an authorized later lane; full-size pricing was not executed.
Certification controllers are disabled even when all four runtime flags are enabled.
