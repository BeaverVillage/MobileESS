# R25F A6 — Final Stage-1 Closure Carrier

This is the A6 runtime carrier derived from frozen R25E/A5.

Runtime-only metadata corrections made at A6 release:
- R25E continuation policy is explicitly named `R25E_A5_EXACT_NODE_ARC_H10_ISG32`.
- R24 legacy audit fields no longer falsely state that MOVE arcs remain binary when A5 is active.
- pre-opt/runtime metrics distinguish continuous MOVE arcs from binary node occupancy.
- final continuation metadata states that shifted h>=1 plans are non-binding VarHints, not physical/MIP-start state.

No scientific equation, feasible physical trajectory, objective, frozen K=3 traffic authority, D2 contract, Rack/WAN gate, SOC/debt semantics, or Fresh Exact OpenDSS gate is relaxed.

A6 is the first long solve after A1-A5. It resumes at exact issue152 PRE state and uses a 1800 s per-issue engineering fail-fast ceiling. The 3% scientific MIPGap criterion is unchanged.
