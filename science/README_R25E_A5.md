# R25E / A5 — Exact node-arc integrality compression + causal-safe persistent rolling freeze

A5 replaces the 99k MOVE-binary mobility formulation with an exact simple-DAG formulation:

- binary state/node occupancy `occ[m,h,service]`
- continuous `[0,1]` MOVE and STAY arc flows
- exact node inflow/outflow equalities
- fail-closed rejection of any parallel tail/head transition after A2

All A1/A2 feasible arcs remain present, so there is no restricted-column completeness problem. The A3 Dantzig-Wolfe/DP pricing kernel is retained as an exact fallback but is not the A5 primary production formulation.

A5 also reuses immutable/static rolling context across issues after per-issue topology identity checks. It intentionally does **not** reuse the entire mutated Gurobi model across issues because queue/running/WAN state and issue-specific causal mobility coefficients are authoritative dynamic inputs; stale constraints or future-state leakage are not acceptable.

No long issue152 solver run is performed in A5. Long closure is deferred to A6.
