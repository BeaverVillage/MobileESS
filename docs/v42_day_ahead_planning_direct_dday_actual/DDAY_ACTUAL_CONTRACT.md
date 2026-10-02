# D-Day Actual execution contract

```python
run_dday_actual(frozen_day_ahead_plan, realized_inputs, backend, output,
                local_p_repair=False, local_q_repair=False,
                full_reoptimization=False)
```

Input is a verified `FrozenDayAheadPlan` (reload with `.load(path)`), plus
JSON realized `load`, `pv`, `aidc_state` and any causally observed arrivals.
An unverified mapping is rejected. The same full plan SHA crosses the boundary.
Output reserves `DDAY_ACTUAL_INPUT.json` before execution. Reusing its output
directory is rejected before another AC execution.

The narrow trusted `ActualBackend` has only `reconstruct_physical(schedule,
realized_inputs)` and `fresh_ac(physical_arrays)` capabilities. Reconstruction
returns `schedule`, physical `load`, `pv`, `aidc_state`, and
`execution_controls={local_p_repair:false, local_q_repair:false,
full_reoptimization:false, global_MILP_calls:0}`. Frozen known-job schedule,
actions, route, movement, charge mode, P, Q, SOC, policy, grid and input
authorities must remain identical in both the supplied and returned schedule.
Realized input arguments must also remain unchanged. The original inputs are
detached before callbacks and the reconstructed payload is detached before AC.
Only these five reconstruction keys are accepted; extra top-level P/Q/route or
other control overrides are rejected, keeping the frozen schedule authoritative.

The adapter maps the realized inputs to physical arrays using the existing
electrical footprint/grid authority; this PR does not fabricate a native
reconstruction model or an OpenDSS producer. Physical adapters must apply only
the frozen `v42_native.actual.unknown_arrival` interface and its supplied existing
authority. That function retains causal observation validation, the unpromoted
runtime fail-closed branch, exact kernel-anchor identity, site-only reservation,
no temporal shift or migration, and full-service/capacity checks. New ML,
unknown-job authority or kernel promotion is not permitted. A frozen interface
hash is an identity, not proof that an unpromoted provider is ready.

Actual stamps full plan/grid/policy SHA, realized input SHA, DDAY_ACTUAL layer,
and 0.95–1.05 pu bounds on the reconstructed physical payload and writes
`ACTUAL_PHYSICAL_ARRAYS.json`. Fresh OpenDSS is called once with these arrays.
Its receipt must bind schedule/grid/policy SHA, realized input SHA, physical
array SHA and execution layer; explicitly report voltage bounds, a real fresh
OpenDSS engine, convergence, and zero voltage/line-current/transformer-current/
transformer-kVA violations. Raw receipts are retained in
`DDAY_ACTUAL_RESULT.json`. Physics, identity, array mutation, or OpenDSS
execution failures produce persistent FAIL; there is no rescue or retry.

Local P/Q repair and global reoptimization options reject before any callback.
Backend correction/global-call declarations reject before AC. The Actual module
imports no optimizer and never calls planning stages or repair functions.
Mutation checks and receipt checks enforce the trusted adapter contract; injected
Python code is not sandboxed against arbitrary hidden side effects. Production
adapters remain responsible for trustworthy physical readback and causal-policy
implementation. No production adapter was activated in this PR.

Final kernel audit: this checkout has no final kernel producer. The existing
`v42_final.gates.require_kernel` predicate now requires DDAY_ACTUAL as well as
accepted M2, AC PASS, plan identity and upstream hashes. The stronger public
`v42_native.actual.require_dday_kernel(frozen, actual_result, upstream)` verifies
the real receipt and physical/realized identities, exact frozen upstream
authorities, and existing M2 acceptance; it never mints acceptance. Future final
response/event kernel producers must call this boundary after Actual PASS.
`KernelAnchor` remains an existing causal-policy identity check, not final
kernel generation. Planning never generates/freezes a final kernel.
