# Conversation A — R25B / Acceleration A2 of 6

A2 formalizes and audits K=3 exact route dominance and equivalent planning-state merging after A1.
No hours-long MIP solve is authorized in A2.

The frozen upstream `pareto_moves()` already removes a K<=3 route when another route for the same OD and departure step reaches the ready state no later and uses no more Safe route energy. A2 therefore does not pretend that this already-adopted pruning is new. Instead it checks the post-A1 graph for any escaped dominated/equivalent route and measures the irreducible destination/time state floor that route-rank pruning alone cannot remove.

If A2 passes with no escaped dominance, more K-rank tuning is not the main acceleration lever; A3 must decide whether the remaining destination/time/MESS combinatorics require exact decomposition.
