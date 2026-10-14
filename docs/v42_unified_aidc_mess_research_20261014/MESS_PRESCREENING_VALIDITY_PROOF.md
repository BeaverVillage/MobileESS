# MESS prescreening validity

All routes retain original service IDs, road link chains, traffic SHA, ETA, connection delay and safe travel energy. The 96-slot DAG retains the original complete STAY/MOVE grammar. Forward-unreachable and backward-dead-end arcs are zero for every feasible nonnegative unit flow and can be removed in both LP and integer domains.

A path SOC upper bound grants optimistic maximum charging in every connected slot and no discharge. A path whose maximum reachable SOC is below the original minimum or terminal SOC cannot be physically feasible. These path checks never establish a fractional-arc zero. Grid sensitivity and beam-width/depth discards are heuristic search limits and never redefine the exact reduced MILP or provide a global bound.

Inactive vehicles are current-source independently replayed with all four original physical vehicles. Their exact location, P, nonzero Q, Mode and SOC persist as fixed full-grid injections. An old full grid certificate is not copied; the current original grid rows must independently pass.

A bound from a joint finite route pool is RESTRICTED_ROUTE_POOL. Only the unrestricted reduced original physical MILP can provide REDUCED_CASE_GLOBAL. Neither proves the original 4x24 global lower bound.
