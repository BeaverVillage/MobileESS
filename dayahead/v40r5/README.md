# V40R5 15-minute selective burst forecast

Scientific result: **V40R5_BODY_FORECAST_INSUFFICIENT**, selected model **NONE**.

The event-based 15-minute target reconstructs the frozen parent 30-minute target within 2.91e-11 GPUh. The primary target is exogenous arriving GPU-service demand, not historical execution occupancy. The failed frozen diagnostic pipeline is PB1_BC0_C3_R0; all interface rows are proposals with optimizer use disabled.

Base: `ff1fec3a7d8f80b3c2af496758747fafc04bad7b`.
Preregistration: `9e77df9e3d607c2b1ef3ee9a6f18fe21b653634e`.
Development baseline: `5e7ac5ef4e395b54e7fd5e07825e6be864af7f65`.
CAL selection freeze: `2917efa8a3b56b2bc0b897574009eb96df3cd526`.

The registered model source, event inputs, feature data, split and thresholds are hash-checked by `common.authority()`. No R4 model object was imported or refitted. R3 and R4 files are hashed separately at start and completion. R2 remains superseded and untouched.

Completed workflow, using `C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe` from this worktree:

1. `python -m dayahead.v40r5.initialize`
2. Commit Phase-0 identity/rules, then `python -m dayahead.v40r5.phase0`.
3. `python -m dayahead.v40r5.preregister`; run prefit tests; commit registration and write its receipt.
4. `python -m dayahead.v40r5.train fit`; commit development baseline and fits.
5. `python -m dayahead.v40r5.train calibrate`; commit rejected CAL selection, eta and envelopes.
6. `python -m dayahead.v40r5.train reproduce`; one independent same-seed rebuild, with no replicate selection.
7. `python -m dayahead.v40r5.evaluate`; frozen exposed evaluation only.
8. `python -m dayahead.v40r5.zero_inflation_audit` reads saved predictions for the user's post-result interpretation amendment; no fitting, calibration or reselection. Then `finalize audit`, postfit tests, `finalize review`, research commit, `finalize receipt`, receipt commit.
9. Final closure tests, report/receipt/hash manifest update and closure commit; read-only closure verification.

These commands document completed research; repeating mutation stages overwrites local R5 artifacts. No automatic refit or favorable-result retry is part of the frozen experiment.

Read-only final test command:

```powershell
& 'C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe' tests/dayahead/test_v40r5_contracts.py --final --closure --read-only
```

There are 59 required artifacts: 57 original requirements plus the two formal zero-inflation audit/proof artifacts requested after CAL exposure. The Korean final review covers requested items 1–50. The forecast safety result is distinct from implementation-test success.

The BODY gate feasibility audit identifies an additional mathematical limitation: nonnegative Q90 covers every exact zero, so overall coverage is `z + (1-z) * positive coverage`. With CAL BODY zero fraction above 50%, the requested positive lower bound 90% and overall upper bound 95% cannot both hold. The experiment retains those gates unchanged.

PRIMARY RESULT: NO REGISTERED COMBINATION PASSED THE FROZEN SAFETY GATES.
IMPORTANT METHODOLOGICAL FINDING: BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION.
PB1 trial 0 / BC1 has positive BODY coverage within 90–95% in CAL and EXPOSED; within the BODY gate it fails only overall upper 95%. The raw trials also under-cover positive BODY outcomes. CAL is structurally incompatible; EXPOSED aggregate bounds are feasible in principle. Detector and hybrid failures remain separate. Do not interpret the failure taxonomy as evidence that all models are poor.

NEXT_RECOMMENDED_REVISION=V40R5R1_ZERO_INFLATION_AWARE_GATE_CORRECTION is a recommendation in the final review only. No R5R1 worktree, code or experiment was created or executed. Any future correction is prospective and limited to the evaluation contract; the current frozen gates remain in force.

Hybrid cumulative and 30/60-minute outputs are sums of reserve envelopes, not true Q90 values. Only the Tweedie diagnostic uses full compound Poisson-Gamma scenarios; its cumulative quantiles are computed after summing within each scenario.

No optimizer, Gurobi or OpenDSS calls; no migration, WAN, terminal, event-trigger or local-repair changes. May 2025 scientific reads remain zero, with metadata access disclosed separately. All fitted models ran on CPU; GPU hardware/framework availability and exact timing are recorded in the compute ledger.
