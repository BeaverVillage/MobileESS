# Conversation A — R25N B6-C5R2 changelog

## Trigger
C5R1 user runtime failed at exact root CG iteration 22 with `Pi` unavailable. The
captured Gurobi log showed: QCP dual solution could not be computed because the barrier
solution was inaccurate and recommended decreasing `BarQCPConvTol`.

## Correction
1. Replace B6 QCP numerical-authority use of `BarConvTol` with `BarQCPConvTol`.
2. Add root and child QCP-dual recovery: no pricing/certificate bound is accepted until
   Pi, QCPi, convexity Pi, and path reduced costs are available. Retry uses only tighter
   BarQCPConvTol values.
3. Reopen Threads=1 runtime-policy freeze for diagnostic screening only.
4. Screen 1x1, 1x2, 1x4, 1x8 sequentially on the same issue152 PRE state.
5. On the selected thread count, close exact root pricing and audit integrality-gap
   sources by mobility/path and non-mobility integer blocks.
6. Partial-integrality MIP diagnostics use the generated path pool and are diagnostic
   only; they never become a scientific global lower bound.

## Scientific contract
No feasible-set, objective, H54, 5-min cadence, 3% target, causal-data, or physical-gate
change. C5R2 performs no h0 commit and does not authorize B7.
