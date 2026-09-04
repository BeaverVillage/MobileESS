# R25N B6-C5R2 — Thread Topology + Gap-Source Forensic

Purpose: reopen only the Stage-1 B6 numerical/runtime policy after C5R1 showed that
Gurobi failed to compute QCP duals at root CG iteration 22. The user-runtime log
explicitly warned that the barrier solution was inaccurate and recommended decreasing
`BarQCPConvTol`; the previous code had tightened `BarConvTol`, which is not the QCP
barrier convergence tolerance.

Changes:
- use explicit `BarQCPConvTol` for every continuous QCP root/child certificate solve;
- require Pi/QCPi/RC before accepting a pricing iteration;
- retry dual recovery only with tighter `BarQCPConvTol` values;
- diagnostic sequential 1-process thread screen for Threads = 1,2,4,8;
- exact root-pricing forensic with the selected thread count;
- measure fractional mobility/path and non-mobility integer blocks;
- run restricted-path-pool partial-integrality diagnostics, explicitly non-authoritative.

Not changed: H54, 5-min cadence, frozen 3% full-scalar gap definition, objective,
physical feasible set, causal information set, Rack/WAN/OpenDSS gates, h0-only commit.
C5R2 is diagnostic-only and performs no physical commit.
