# Universal continuation and exact parallel-arc quotient

Higher SOC at equal time/site/cost is NOT universal dominance. With terminal SOC
equality and a travel/no-exchange suffix, energy 1 can finish at terminal1 while
energy2 cannot. With upper SOC and mandatory future recharge, extra energy may
also prevent a continuation. Different prior coupling injection/cost histories
are not interchangeable simply because routes meet at one node. These families
are rejected unless complete continuation inclusion is proved.

The implemented sufficient condition is exact parallel-arc equivalence:
binary coordinates j,k have identical complete ORIGINAL local and coupling
matrix columns, bounds [0,1], objective coefficient, and identical native
source/depart/destination/connect provenance. The original nonnegative unit flow
on a strictly time-increasing DAG proves x_j+x_k<=1 (and sum over a group <=1):
at each node incoming/outgoing mass cannot exceed the single source unit; no
cycles or disconnected circulations exist. Thus y=sum(group x) is binary for
all integer trajectories. Replace the group by one representative y. Every
original feasible trajectory maps to it with identical rows/objective/coupling.
Conversely lift y to the canonical original arc and zero the others; every
original row, bound, type, and coefficient projection is unchanged. For an
arbitrary pricing dual, reduced cost is identical in both directions.

No favorable-resource, Top-K, route-score, incumbent-based, or approximate
dominance is applied. Hashes only propose groups; exact CSR/CSC coefficient
equality and route provenance prove eligibility. Original route files/models
and P2 are unchanged. Toy exhaustive integer projections and costs agree in
both directions. The full-scale audit records groups/counts before build; if
none exist, the reduction is rejected as an identity transformation.
