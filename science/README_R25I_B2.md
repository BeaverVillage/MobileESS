# R25I / B2 Exact Numerical Re-scaling

B2/7 changes only the internal units of R25D dynamic-skeleton LinDistFlow branch-flow auxiliaries from kW/kvar to MW/Mvar. The transformation is exact and invertible with scale 1000. All physical inputs/outputs, SOC, dispatch, objective dollars, hard limits, and Fresh Exact OpenDSS interfaces remain in the frozen units.

No long issue152 solve is run in B2. The full-model coefficient statistics are intentionally measured in B3.
