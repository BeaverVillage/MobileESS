# Conversation A — R25I B2/7 Exact Numerical Re-scaling

## Scope

B2 changes only the **internal R25D LinDistFlow branch-flow auxiliary units** from kW/kvar to MW/Mvar. No scientific constraint, objective, MIPGap target, H54 horizon, 5-minute cadence, Rack/WAN gate, or Fresh Exact OpenDSS interface is relaxed or removed.

## Exact transformation

- `FP_model = FP_kW / 1000`
- `FQ_model = FQ_kvar / 1000`
- Every branch balance is divided by the same positive factor 1000.
- Voltage recursion uses `2.0*r*FP_MW` and `2.0*x*FQ_Mvar`, which is algebraically identical to `0.002*r*FP_kW` and `0.002*x*FQ_kvar`.
- Line thermal limits are changed internally from kVA to MVA by the same factor, so the quadratic circle is exactly equivalent.
- Reference branch flows are divided by the same factor.

## Numerical motivation

The frozen R25F issue152 log reported `Matrix range [2e-09, 7e+02]`. The frozen BUILD7AR2 coefficient artifact contains a minimum nonzero line `r/x = 1e-6`, giving the exact `0.002 * 1e-6 = 2e-9` voltage-flow coefficient. B2 makes that coefficient `2e-6`, a 1000x improvement. Relative to the prior 700 maximum, the grid-driven static coefficient ratio becomes about `3.5e8`, below `1e9`.

This is a **static prediction for the identified grid-driven lower edge**, not a claim about the final full-model coefficient range. B3 will record Gurobi's actual coefficient statistics on the built model.

## Proof / validation

- 10,000 randomized balance/voltage/thermal algebraic-equivalence trials: PASS.
- Actual BUILD7AR2 topology/coefficients loaded: 168 nodes, 167 edges.
- B1 regression and full release self-test: PASS.
- Model API call counts unchanged.
- Existing function modified: `build_full` only.
- Long issue152 solver run: **NOT RUN**.
