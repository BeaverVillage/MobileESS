# Conversation A — R25C A3/6 Changelog

## Stage
A3/6 — Compactness Decision Gate + Exact Decomposition Architecture.

## Decision
The permanent monolithic BUILD7C mobility formulation is rejected for production continuation. Historical issue152 evidence has 99,283 MOVE binaries after exact pruning. After R24's exact STAY projection, approximately 99,499 integer variables remain, so MOVE accounts for about 99.783% of the integer combinatorics. Existing exact MOVE pruning removed only 2,636 / 101,919 = 2.586%, and the 8-hour issue152 run still ended at 3.0982539% versus the frozen 3% certificate.

All four fixed A3 decision gates fail, therefore `EXACT_DECOMPOSITION_REQUIRED` is frozen.

## Implemented in A3
- Added an evidence-bound compactness decision gate.
- Added an exact full-column MESS path-reformulation contract.
- Added an acyclic shortest-path dynamic-programming pricing kernel.
- Added column signatures for STAY occupancy, MOVE departure, Safe route-energy and route tie-break couplings.
- Added a small-DAG proof test: 200 random pricing trials matched exhaustive full-column enumeration exactly.
- Preserved the A2 scientific `main.py` byte-for-byte; A3 does not silently change the optimizer feasible set.

## Exactness boundary
The full-column formulation is mathematically equivalent to the integer unit-flow mobility path model when all feasible paths are represented. A restricted set of heuristic columns is **not** authoritative. A5 must implement certified branch-and-price or an equivalent all-column completeness certificate before decomposition can replace the monolithic solver in A6.

## Long-run policy
No issue152 long solve was executed in A3. No bash runner is required now.

## Next
A4/6 performs radial-grid exact projection / node-QCP reduction on the compact operational master. A5 integrates the frozen A3 decomposition contract with persistent rolling execution and the exact column-completeness mechanism.
