# Conversation A — R25O B6-C5R4R1 RC dual recovery

- Treats analytical-versus-native path reduced-cost mismatch as a QCP dual
  lifecycle failure and retries the same RMP at `BarQCPConvTol` 3e-10 and 1e-10.
- Resets the Gurobi solution state before every root/child dual retry so changed
  scaling and barrier settings force a fresh KKT solve instead of a 0-iteration
  reuse of the previous inaccurate dual point.
- Applies `ScaleFlag=2` and at least `NumericFocus=2` on RC-mismatch recovery.
- Applies `ScaleFlag=2`, `NumericFocus=2`, full path-RC accounting, and model
  coefficient-range auditing to every exact branch-and-price child QCP.
- Applies `ScaleFlag=2` to the fixed-integer continuous-QCP incumbent polish.
- Adds a licensed native-kW/kWh versus normalized-MW/MWh MIQCP equivalence
  smoke and changes the polish smoke to exercise Gurobi `Model.fixed()`.
- Does not loosen the 1e-4 RC audit envelope or the frozen 3% gap contract.
- Preserves H54, five-minute cadence, objective, physical feasible set,
  causality, external units, and Fresh Exact OpenDSS boundaries.
