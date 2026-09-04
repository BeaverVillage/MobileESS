# R25G A6R3 Hybrid STAY-Binary Exact Acceleration

Purpose: recover an explicit economically meaningful STAY-vs-DEPART branching variable after R25E reduced MOVE integrality from ~99k binaries to node occupancy. MOVE arcs remain continuous; node occupancy and STAY arcs are binary. This is an exact extended formulation because R25E already proves every integer-feasible path has STAY in {0,1}.

Additional exact valid inequalities at 6-step suffix checkpoints:
- support-debt repayment <= physical charging capacity of future STAY steps;
- terminal-SOC survivability under maximum future STAY charging and zero discharge.

No change to H54, 5-min cadence, 3% MIPGap, objective, K=3 traffic authority, D2, causality, or Fresh Exact OpenDSS gate.
