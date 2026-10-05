# Actual pricing structure and Markov sufficiency

Classification: **HYBRID_DP_LP_POSSIBLE**. A finite SOC grid is not exact.
Source: original v42_native/mess.py (flow/terminal location 107–108; continuous
SOC 109–110; binary mode 112–113; continuous P/Q and connection/mode/PCS16
118–127; energy recurrence with departure-time travel debit 129–131).
Actual sparse block audit is saved separately, including variable families,
binary count, all original rows/coefficients, and full graph/domain identity.

Time and location identify the next outgoing route arc. Movement must retain
destination/connect time and travel debit; a time-only or current-site-only label
is insufficient. Future SOC feasibility depends on exact continuous energy and
terminal equality. Charge mode plus continuous P/Q polyhedron and PCS16 determine
each slot's attainable energy/cost. All coupling prices are local linear injection
costs at a fixed true dual. Retaining only an optimal prefix SOC loses attainable
future states and is not safe. Reactive power cannot be discarded as cost-neutral.

An exact hybrid exists by retaining the complete original continuous LP for each
binary prefix (route/mode decisions), including future rows and fixed prefix
bounds. The disjoint children x_j=0 and x_j=1 cover every integer continuation.
Every complete binary label is an original fixed-route/fixed-mode LP. This finite
cover is exponential; it does not prove a useful finite Markov-state compression.
The implementation is explicitly an LP-valued binary-label coverage prototype,
not a polynomial DP or a renamed shortest-path solver. SOC/P/Q are never rounded
onto a lattice. Cost pruning uses exact Fraction weak duality and finite original
coordinate bounds; infeasibility pruning needs an exact Farkas contradiction.
Incomplete labels retain inherited bounds and remain unresolved. Discovery-only
prototype diagnostics do not change the original true-dual certificate path.

Toy route/mode/SOC/travel/PCS-like continuous fixtures compare native integer
pricing with the complete hybrid to 1e-8, including original coefficients and
feasibility. Full-scale comparison uses MESS01, one same true checkpoint dual,
original 60s MIP versus one 60s hybrid attempt; shared wall <=600. Incomplete
optimization is reported as such, never as an exact optimum or no-column proof.
