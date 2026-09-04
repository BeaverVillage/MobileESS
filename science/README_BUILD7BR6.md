BUILD7BR6 — EXACT ROUTE-DOMAIN REDUCTION + 14-THREAD + WARM START

BUILD7BR5 actually used 8 Gurobi threads and reached the 1.5% economic target in about
665 s, but its post-solve wrapper incorrectly failed because it reread Gurobi LogFile
before the buffered tail containing `Thread count was 8` had become visible. BR6 uses
the official MESSAGE callback (`MSG_STRING`) as synchronous thread evidence.

BR6 exact speed improvements:
1. Default Threads=14, runtime-overridable from 1 through 16. This is a benchmark on the
   16 logical processors; more threads are not assumed to be faster.
2. Method=2 forces the parallel barrier root algorithm because BR5's concurrent root
   repeatedly selected barrier as the winner.
3. Exact route pruning removes:
   - arcs from structurally unreachable service/time states,
   - move arcs that arrive exactly at terminal H (strictly dominated),
   - move arcs infeasible even under an optimistic maximum-SOC dynamic program.
4. Exact lexicographic zero certificate: if every known queued job can start immediately
   at its origin, Defer/Wait/Remote/WAN attain proven global lower bounds. The model then
   fixes the decision domain to those exact minima and solves only the economic MIQCP.
   Otherwise it falls back to the original five-pass hierarchical solve.
5. Partial MIP warm start from the prior causal issue113 PASS solution. No future actual
   values are introduced. BUILD7C will use the shifted previous rolling issue instead.

All grid, WAN, Rack, SOC, P/Q, debt, mobility-energy, Fresh Exact OpenDSS, 1e-9 solver
feasibility/integrality/optimality tolerances, and no-look-ahead contracts are unchanged.
