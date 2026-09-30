# V42 MESS graph/SOC acceleration

Base: Draft PR #99, `3309cd230cd8235201f5578d392241fa98e059bc`. Independent branch `codex/v42-mess-graph-soc-acceleration`; no concurrent AIDC D-W changes.

The common M1/M2 engine retains the inherited joint network-flow/P/Q/SOC MILP. The new immutable domain prunes only structurally or physically impossible arcs, conservatively propagates forward/backward SOC hulls, screens individual arc mappings, and iterates to a deterministic fixed point. Electrical variables and PCS16 rows exist only for surviving stay tails. Route indices retain PR99 ordering, including the deterministic tie. Exact duplicate matching includes **all** RouteArc fields, including route ID and authority; different energy routes are never deleted by dominance.

## Evidence and measured limits

- All 77 audited bounded cases (original canary, 12 adversarial and 64 seeded random cases) preserve every feasible fixed-path continuous SOC interval and all five optimal objectives. The full test suite is recorded in `TEST_RESULTS.xml`.
- Native source-backed **mobility-only construction**, 96 slots/24 sites/4 MESS: route binaries 207,928 → 207,928; Pch/Pdis/Q 8,942 each → unchanged; PCS16 rows 143,072 → unchanged; columns 235,526 → unchanged; rows 206,336 → 206,062; nonzeros 1,259,442 → unchanged. Removed rows are 274 identically zero flow rows. Existing forward screening already removed impossible columns.
- Exact timings are in `MESS_BASELINE_MODEL_SIZE.json`. The first SOC/domain construction adds cost. The separately measured Gurobi construction reduction does **not** establish total cold-build acceleration or native solve speed. Reusing a domain avoids a second prescreen.
- The transit-only adversarial fixture reduces route binaries 7 → 2, each P/Q family 6 → 1, charge modes 5 → 1 and PCS16 rows 96 → 16. These are bounded correctness examples, not native performance estimates.
- One M2 cold/warm diagnostic uses the **identical M2 problem** with a dynamic grid different from M1. The full MESS physical start is accepted; scientific objectives match. Timings/nodes/gaps are recorded without claiming a speedup from one small case.
- Native M1 and M2: `NOT_RUN_AWAITING_ACCEPTED_A_BLOCK`. PR99 has no accepted A1; no accepted A2 or artificial anchor is supplied.

## Safety argument

Every feasible prefix energy is contained in the forward envelope by induction over the DAG. Every feasible suffix energy is contained in the backward envelope initialized to terminal SOC **equality** at every authorized terminal site. Merging predecessors/successors by interval hull only enlarges those sets. A physically feasible arc must map at least one energy in the source intersection into the destination intersection. Empty node intersections or arc images therefore cannot contain a feasible trajectory. Repeating the same necessary-condition screens on surviving arcs is safe by induction on iterations. Outward arithmetic/slack retains uncertain boundary cases.

Stay envelopes use `[-dt*p_limit/eta_discharge, dt*eta_charge*p_limit]`. These are safe **outer** limits: PCS16 or grid coupling can further restrict them. SOC hull membership is never a full feasibility certificate. All connected survivors contribute to global E[t] bounds; a travel arc also contributes its **post-deduction** interval at every skipped time. Full energy is deducted in the departure slot's balance, and Pch/Pdis/Q remain zero until the surviving stay at `connect`. No intermediate location or gradual energy deduction is fabricated.

The independent bounded oracle enumerates every route, propagates exact fixed-path continuous energy intervals using the PCS-admissible real power limit at Q=0, and checks the complete interval against every screening iteration and global SOC bound. Identical P/Q, connection, direction and PCS rows on retained paths preserve their full electrical feasible sets. Optimal Gurobi comparisons additionally exercise both P1 and nonzero P2, movement energy/count and the deterministic tie. Both comparison models use MIPGap=0 and the same fixed 1e-9 numerical tolerances; production MIPGap remains .005. No parameter/gap sweep was performed.

## Integration interface

```python
from v42_native.mess_domain import build_domain
from v42_native.mess_optimizer import OptimizeBudget
from v42_native.mess import solve

domain = build_domain(sites, initial_sites, source_routes, battery, 96)
# Call only after the corresponding genuine accepted A block is available.
m1, stats1 = solve('M1', OptimizeBudget('M1'), sites, initial_sites,
                  source_routes, battery, 96, accepted_a1_grid, domain=domain)
m2, stats2 = solve('M2', OptimizeBudget('M2'), sites, initial_sites,
                  source_routes, battery, 96, accepted_a2_grid, m1, domain=domain)
```

The domain is frozen, hashable and contains no grid/AIDC data. A bounded LRU also reuses identical authority inputs in a single process. Callers crossing process boundaries must retain/pass the immutable domain through their trusted integration layer; the existing JSON-only coordinator/supervisor is unchanged in this branch. No claim of native backend integration or 1800-second outer-supervisor support is made. Future integration must align that outer supervision with this **MESS-only** optimize budget rather than apply its inherited 600-second total wall cap to a native run.

Before any Start assignment, the engine verifies domain authority, full x/charge_mode/Pch/Pdis/Q/SOC values, selected-path consistency, numerical bounds, SOC balances, terminal equality, PCS16 and circle safety. Invalid starts raise a reason and are never clipped. Dynamic grid variable starts are recomputed by M2. The physical M1 solution must come from the caller's accepted M1 handoff; `physical_audit` is revalidated, never trusted as a flag.

`OptimizeBudget` is armed immediately before the first `model.optimize()`, gives M1 and M2 1800 seconds each cumulatively across lex levels, and includes presolve. Legacy `Deadline` callers retain their requested solve duration with build time excluded. Diagnostic runs use 20 seconds and exact gap 0. Receipts separate preparation/prescreen/build, per-pass Gurobi Runtime, reported presolve/root times and callback milestones. Unobservable isolated B&B durations remain null; they are not invented by subtracting approximate callbacks.

## Reproduce

```powershell
python docs/v42_mess_graph_soc_acceleration/audit.py --route-table 'PATH_TO_IDENTICAL_ROUTE_TABLE.json.gz'
python -m pytest -q --junitxml=docs/v42_mess_graph_soc_acceleration/TEST_RESULTS.xml
python docs/v42_mess_graph_soc_acceleration/verify.py
git diff --check
```

The optional route-table argument must match the inherited SHA exactly. The adapter reads supplied travel/connect slots and `energy_safe_kwh`; it performs no road search or route generation. Same-site records are stays; records outside PR99's `depart < arrive <= connect < H` contract are accounted for separately, not newly screened or silently repaired.

Keep the network-flow MILP. Neither MESS D-W nor CL-MC-BD is triggered by available evidence: static route column share is large, but native branching/grid/root behavior is unmeasured. The next task is genuine A1/A2 integration and the preregistered native profile, followed by a measured choice of route decomposition, grid/security decomposition, continuous coupling improvements, or the existing solver.
