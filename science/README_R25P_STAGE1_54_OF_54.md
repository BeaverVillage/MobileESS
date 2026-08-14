# R25P Stage-1 54/54

This release is the non-diagnostic Stage-1 completion run. It executes all 54 causally chained issues 113–166 with one process and four Gurobi threads. Solver time and node budgets are disabled. Each issue must obtain the frozen global 3% certificate, pass numerical gates, pass the Fresh Exact OpenDSS first-step check, and only then commit h0.

The run is intentionally fail-closed. If any mathematical, numerical, memory, or physical gate fails, it writes a result archive without claiming Stage-1 completion.

After a full pass, annual production remains a separate monthly-episode runner using four independent monthly processes with four Gurobi threads each and the frozen 48-hour causal burn-in contract.
