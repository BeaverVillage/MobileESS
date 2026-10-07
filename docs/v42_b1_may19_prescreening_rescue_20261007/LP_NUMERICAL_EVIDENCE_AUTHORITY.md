# LP evidence acceptance

Each raw LP point is saved before acceptance and independently expanded into the original full matrix coordinates. The original full rows and bounds are replayed without rounding or clipping, using the unchanged original checker authority (1e-5). A raw TIME_LIMIT point is accepted for the conditional MIP only if this replay passes.

The native LP objective / bound fields in RESULT.json are diagnostic solver attributes. They are not a validated dual/Farkas certificate, certified lower bound, integer upper bound or production acceptance. No native numeric value is promoted to those authorities merely because the solver reported it.

S_A, S_B and S_C timed out and failed full-coordinate primal replay. No integer feasibility call followed those three LPs. The surviving exact signed support rows remain a ranking/continuation guide; their expanded-domain margins are unresolved, not a new infeasibility proof.

The prespecified LP Method=2, Threads=1, Crossover=0 and TimeLimit=600 remain unchanged. Actual native Runtime can exceed the configured limit by termination granularity; both values are reported, without an automatic extension or a repeated solve.
