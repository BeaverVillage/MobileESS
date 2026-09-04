# Conversation A — R25N B6-C5R3 changelog

## Basis from actual C5R2 runtime
- Threads=1 mean root RMP: 1.543568 s
- Threads=4 mean root RMP: 0.994895 s
- Threads=8 mean root RMP: 0.965463 s
- Threads=2: invalid because Pi remained unavailable after BarQCPConvTol retries
- Winner: Threads=4 under the frozen 'within 5% choose smaller thread count' rule
- Exact root pricing with Threads=4: 24 CG iterations, 96.199817 s
- Root gap-source diagnostic: path-lambda lift 13.334246, mode lift 0.573677, job/defer lift 0
- Remaining 3% lower-bound shortfall against the known C5 incumbent: 21.191267

## C5R3 corrections
1. Freeze runtime topology candidate at one process x four Gurobi threads.
2. Preserve explicit BarQCPConvTol QCP-dual policy and fail-closed Pi/QCPi/RC checks.
3. Preserve batch pricing=16; stabilization OFF; strong QCP probes OFF.
4. Prioritize mobility branching while mobility fractionality remains.
5. Add exact fixed-dual multiway time-layer mobility partitioning.
6. Increase deterministic primal path enrichment and restricted-master heuristic effort.
7. Keep restricted-master ObjBound diagnostic-only; exact root/fixed-dual/B&P lower bounds remain the only certificate authority.
8. Scientific feasible set, objective, 3% semantics, causality and physical gates are unchanged.
