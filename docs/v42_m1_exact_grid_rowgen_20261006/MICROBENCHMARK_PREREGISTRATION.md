# One sequential comparison within one continuous 600s development window

Base is untouched PR157 head611af1ba474e8f457d79e79590ed30aa529262a3.
Hard case: current frozen 96-slot May01 M1 with PR134 original full/reduced
matrix and integrated A1 freeze, exactly the scientific model used in PR157.
Immutable input SHA and all original matrix signatures are audited before solve.

Fresh baseline A is the current original exact monolithic M1, all886017 reduced
rows. Challenger B is the SAME formulation, same variables/bounds/objective,
with287552 initial rows and598465 deferred original security rows. PR157 D-W /
Early B&P remains preserved as historical evidence, not a paired new native arm.

One shared continuous wall window <=600s, sequential A then B, each at most
280s including native model build and original-row transport checks. The remainder
is reserved for final separation/publication. Native deadline termination is
requested early; a600s watchdog may terminate ONLY this benchmark's child by
its verified process identity. It is a time budget, never a RAM/resource guard.
No optimization after the window, no production canary or7200s solve.

Both arms share unchanged original solver policy: Threads1, Method2,
NodeMethod1, Crossover2, MIPFocus3, DegenMoves0, Seed20260929,
MIPGap.005, FeasibilityTol/IntFeasTol/OptimalityTol1e-8, native defaults otherwise.
The same independently validated original feasible PR157 integer point is only
a Start hint and starting UB. No route fixing, previous tree, partial clock,
incumbent checkpoint or pricing domain restriction is imported. Both arms retain
the same independently certified full-domain rational floor0.5687115725336208;
native subset bounds may strengthen it with existing1e-8 outward safety.

Report starting/end valid UB/LB/gap, every native call, row-generation iteration,
all inserted original axes, final full exhaustive separation, time to new valid
integer point, native/wall time, passive RSS/free RAM/system/process commit,
and valid gap reduction/wall-second. Pre-existing valid incumbent is time0;
new native incumbent time is reported separately to avoid misleading speed claims.

Selection requires all scientific/exhaustive checks and >=20% improvement in
valid gap reduction/wall-second, or comparably strong valid-bound/earlier-new-UB
evidence at matched wall. Native build/solver-memory reductions alone without
end-to-end progress do not establish selection. If ambiguous, selected=false.
No compact PR124 challenger unless the primary experiment is promising.

Fixture/native calls outside this frozen full-scale comparison are explicitly
bounded and separately counted. All historical evidence stays byte-preserved.
