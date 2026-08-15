# Conversation A — R25N B6-C5R4

- Completed internal MESS power normalization to MW/Mvar and SOC, debt, and
  route-energy normalization to MWh.
- Preserved all external data, result, economic-objective, and Fresh Exact
  OpenDSS boundaries in kW/kvar/kWh.
- Added a fixed-integer continuous convex-QCP incumbent polish with explicit
  numerical and fixed-value acceptance gates.
- Removed the C5R3 fixed-dual multiway prepass from the runtime path.
- Retained exact child QCP re-optimization, exact child pricing closure, and the
  frozen full-modeled-cost global-gap definition.
- Added randomized coordinate-equivalence proofs, static source guards, a
  licensed Gurobi lifecycle smoke test, and runtime coefficient auditing.
