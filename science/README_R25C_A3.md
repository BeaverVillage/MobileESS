# R25C — A3/6 Compactness Decision Gate and Exact Decomposition Architecture

A3 uses the already-observed issue152 authority rather than running another expensive solve.

## Decision

The monolithic mobility block is rejected for permanent production use when any fixed A3 gate fails. Historical issue152 has 99,283 MOVE binaries after exact pruning; R24 removes 4,299 STAY integrality variables but leaves approximately 99,499 integer variables, so MOVE remains ~99.8% of integer combinatorics. The 8-hour run still stopped at 3.0982539% versus the frozen 3% certificate.

A3 therefore selects an exact full-column path reformulation for each of the four MESS units.

## Exactness boundary

For each MESS, the integer unit-flow mobility DAG is equivalent to selecting exactly one complete source-to-H path when the full feasible path set is represented. All K=3 route, travel-duration, D2 delay and Safe-energy semantics remain unchanged. Master coupling uses column signatures for STAY occupancy, MOVE departures and route Safe-energy terms.

The included pricing kernel is an exact DAG shortest-path oracle for additive reduced costs. It is **not** permission to solve a heuristic restricted-column MILP. A5 must implement certified branch-and-price or an equivalent all-column completeness certificate before decomposition becomes production authority.

## A3 validation scope

- historical structural evidence only; no new issue152 solve;
- fixed compactness gate;
- exact full-column reformulation contract;
- exact small-DAG pricing/equivalence proof test;
- no scientific constraint, objective, K=3 authority or causal state change.
