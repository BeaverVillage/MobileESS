BUILD7BR8 — FAST EXACT HOT PATH

This release only accelerates preprocessing/Python hot paths. It deliberately avoids batch variable creation or reordered Gurobi matrix construction because, under the currently retained 1.5% economic stopping criterion, changing variable/row ordering could alter the search path and therefore the selected near-optimal incumbent even when the mathematical model is equivalent.

Exact changes:
- Replace 29,808 repeated Pandas OD filters in pareto_moves with one stable OD/rank grouping.
- Preserve exact legacy iteration order h -> OD -> rank and identical dominance/tie logic.
- For issue113, fail closed unless the 54-element route-count vector and total exactly match the frozen BR7 PASS authority (31,975 candidate arcs).
- Remove repeated incoming/outgoing dictionary scans when building flow rows; by construction every endpoint belongs to reachable[h], so the row domain is unchanged.
- Cache rack->IDC/racks-by-IDC mappings and static grid topological node order.
- Add finer runtime markers for route completion, mobility-domain completion, and full model-constraint completion.

Unchanged: Obj1-4 exact/certificate policy, Obj5 1.5% MIP gap, Threads=14, all physical constraints, causal/no-look-ahead authority, route K=3 semantics, variable/constraint creation order.
