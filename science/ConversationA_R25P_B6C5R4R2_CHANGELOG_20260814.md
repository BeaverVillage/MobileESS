# R25P B6-C5R4R2 — Stage-1 54/54 unlimited completion

- Runs the authoritative rolling chain from issue 113 through 166; resume starts at the frozen issue-113 PRE state.
- Removes root CG, restricted integer master, continuous polish, global B&P, child CG, CG-iteration, and B&P-node budgets in completion mode.
- Retains deterministic early termination only when the frozen global 3% certificate is achieved.
- Fixes projected decision-independent voltage extraction (`float` versus Gurobi expression).
- Adds an explicit certificate fail-closed gate before solution extraction and physical h0 commit; the optimal status of the fixed-integer continuous polish is not accepted as a global integer certificate.
- Retains 4 Gurobi threads, exact child QCP repricing, RC accounting audits, complete MW/MWh normalization, numerical gates, causal h0-only state transition, and Fresh Exact OpenDSS verification.
- Does not change the scientific feasible set, objective, causal information set, or gap definition.
