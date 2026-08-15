# Conversation A — R25J / B3 MIQCP Kernel Batch Screen

## Purpose
Compare `MIQCPMethod=-1,0,1` on the same authoritative issue152 PRE state after B1 certificate-focused search policy and B2 exact MW/Mvar branch-flow rescaling.

## Scientific invariants
No model variable, constraint, objective, H54 horizon, 5-minute cadence, 3% MIPGap target, causal state contract, Rack/WAN/OpenDSS contract, or rolling VarHint policy is changed by B3. B3 is diagnostic-only and cannot become Stage-1 authority.

## Code changes from B2
- `MIQCPMethod` is selectable only through `MOBILEESS_GUROBI_MIQCPMETHOD` with accepted values `-1,0,1`.
- Effective method is written to runtime audits instead of the previous hard-coded audit value `1`.
- Diagnostic-only screen audit added.
- When a method certifies issue152 before its screen budget, B3 stops immediately after the optimizer returns and before rolling warm-start/state transition/Rack/WAN/OpenDSS/h0 commit. This prevents the screen from altering the authoritative trajectory.

## Batch contract
- issue: 152 only
- methods: -1, 0, 1
- per-method TimeLimit: 300 s
- Threads: 1
- MIPGap: 0.03
- MIPFocus: 3
- ImproveStartGap: 0
- B2 scaling: active
- output: one screening bundle with parsed matrix statistics and per-method optimization metrics

## Parent runtime evidence
R25G/A6R3 ended fail-closed at issue152 after 1800.03 s with gap 3.43710069%, 2,959 nodes. This improved over R25F/A5's 3.54066810% and 1,499 nodes but remained above 3%. R25G still used the pre-B2 matrix range `[2e-09, 7e+02]`; B3 is the first runtime screen of B1+B2 together.
