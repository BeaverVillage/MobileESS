BUILD7BR4 — FINAL ECONOMIC 1.5% GAP + 8-THREAD SPEED TRIAL

This stage changes solver termination/runtime policy only.

Objectives 1–4 remain exact at the model-level MIPGap=0 and Threads=1:
  1) defer
  2) wait
  3) remote migration
  4) WAN transfer

Only multi-objective optimization pass 4, the final economic objective, uses:
  MIPGap    = 0.015
  MIPGapAbs = 0
  Threads   = 8
  MIPFocus  = 2

The objective-specific setting uses Gurobi's multi-objective environment API, so the
1.5% gap does not leak into the higher-priority service objectives.

BR3 sparse branch-flow, exact reachable-route pruning, 24 service-transformer kVA
constraints, MIQCPMethod=1, PreSparsify=2, NodefileStart=0.5 GB, dynamic SoftMemLimit,
1e-9 feasibility/integrality/optimality tolerances, and all causal/no-look-ahead
contracts remain unchanged.

This is explicitly an 8-thread speed trial. Parallel MIP can consume more memory, so
the BR3 SoftMemLimit and node-file safeguards remain active. If this run reaches
MEM_LIMIT or causes unacceptable memory pressure, the next benchmark should use 4
threads rather than relaxing any physical constraint.

The run also fixes final-pass gap reporting for a multi-objective model. It prefers
Gurobi pass-specific ObjPassN* attributes when available and falls back to callback
incumbent/bound telemetry.
