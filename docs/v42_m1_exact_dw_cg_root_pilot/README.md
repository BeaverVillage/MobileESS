This root-only pilot starts from PR139 exact head
`c8e518f97cbe1748f3e8773128ff8152bd394ee8`. All inherited source,
scientific artifacts and campaign semantics remain byte-identical.

Run order is `prepare`, bounded `fixtures`, `run`, then post-terminal
semantic/full `testing`, read-only `finalize`, commit/push/Draft PR.
The scientific optimize marker is outside Git in `DW_ROOT_LOCAL`.
The current entry-point package is `v42_dw_root`. The scientific run used
the initial `v42_dw` namespace; after the pilot terminated, the package was
moved because two immutable legacy production tests reject all imports
under that historical name. The migration receipt maps every executed
scientific source SHA to its byte-identical current path. Original test
failure logs are retained; no legacy test or production source changed.
For the final full regression run, `--basetemp` selects the fresh actual
ASCII path `C:/Users/Public/CodexDWRootTests/full_20261004_02`, outside Git,
after creating its parent directory and running the path-probe tests.
The system ESTsoft/CreatorTemp path caused an atomic `os.replace` WinError 5
in one campaign fixture. A subsequent D: local path resolved through a
junction to a Unicode OneDrive path, causing native Gurobi file-write errors.
The initial actual-ASCII attempt omitted its parent directory, causing
missing-temp-base setup errors. All failed runs and receipts are retained.
Campaign atomic-publication
behavior and all legacy tests remain unchanged.
One Python worker and one Gurobi thread are used, with four numerical
environment thread limits set before imports. Pricing and RMP solves
are sequential. Tests cannot start before the pilot result exists.

The partition uses the immutable original sparse dependency graph.
Native free/shared and objective coordinates are global anchors.
Remaining matrix row/column connected components are assigned only when
all original route/mode integer provenance anchors identify one MESS.
Continuous ownership follows actual dependencies, rather than variable
name guesses. Ambiguous/unanchored components and every row that touches
a shared or multiple-unit coordinate stay global. Original row/column
axes, RHS, senses, bounds, types, objectives and native names are retained.
The selected model has 206,062 local rows and 679,955 global rows.

A trajectory column is a complete feasible native local solution:
route/stay/travel, modes, Pch/Pdis/Q and SOC over all 96 slots, including
initial/terminal SOC and departure travel-energy debit. It is not merely
a route. Every candidate is audited on original local rows, exact integer
patterns and independent route/SOC/PCS/mode/connection semantics. No
clipping, rounding repair or slack is introduced. The initial four columns
come from PR139's raw polished point.

The continuous RMP keeps original shared variables and every global row,
adds nonnegative lambda columns and one convexity equality per unit, and
minimizes original rho. Column coefficients are actual original B_m*v
products. Exact rational dyadic coupling products are archived alongside
binary64 solver transport, with an explicit transport audit. Column hashes
include raw local-vector bits, raw master-vector bits and objective bits;
signed zero is preserved. Only exact duplicates may be skipped. No column
aging, deletion or tolerance merging is permitted.

Pricing is the full original local MILP. There is no Top-K, route pool,
Hamming neighborhood, site/time pruning, beam/greedy/approximate-path
pricing or historical-only termination. Gurobi searches the original full
domain with MIPGap=MIPGapAbs=0 and at most 600 seconds per call. A validated
negative incumbent may be added and the call may stop before global
optimality, as explicitly allowed by the request. Such a call is never
called most-negative or pricing-optimal. No custom heuristic pricer exists.
MIP Starts seed native full-domain searches and do not impose restrictions.

The bounded sign fixture compares manual c-Pi*a-alpha with solver RC and
then releases an improving column. The deterministic equivalence fixture
enumerates every physical pattern-polytope vertex for all 2 legal paths x
4 binary mode patterns, including feasible and infeasible cases. For the
integer comparison lambda remains continuous and reconstructed original
binaries force a single pattern, allowing convex mixtures within that
pattern. A binary single-vertex master would generally fail to represent
continuous trajectory interior points and is not used. Full enumeration
therefore represents the original bounded union exactly; its convex-hull
LP cannot weaken the original arc LP.

No-negative certificates require a native full-domain global BestBd >=
-1e-8 at the same last RMP dual for all four units. A timeout or incomplete
search is never a no-column certificate. Frozen-dual pricing may resume
within the 3600-second overall budget without changing domains or policy.
Restricted objectives are never promoted to original-M1 lower bounds.
The observed pilot stopped at RMP iteration 210: the native barrier reported
numerical trouble and crossover returned OPTIMAL, but the independent raw
original master-row residual was 6.371490002266e-8, above the unchanged
1e-8 gate. That dual was never used for pricing. The pilot records
INCONCLUSIVE, with no certified D-W LB or material-effect conclusion,
after 836 pricing calls and 836 validated additions (840 retained columns).
The preceding audited RMP objective and the failed RMP diagnostic objective
are explicitly distinguished in the numerical-stop receipt. No scientific
retry or tolerance relaxation was performed.
If all pricing certificates are obtained, original-global-row exact dual
arithmetic plus pricing BestBd and proven shared-coordinate enclosures
produce a conservative lower bound, including residual box terms.

The pilot never branches the D-W master, performs node-level pricing,
implements Branch-and-Price, executes an integer D-W production master,
or runs P2/A2/M2/Actual/Fresh AC. Native local MILP pricing and explicitly
authorized small integer equivalence fixtures are distinct from a
production or Branch-and-Price solve. The May/B3 1,458-stage dry plan and
Actual feedback firewall stay unchanged; campaign optimizer/Actual/Fresh
AC calls are all zero. Inconclusive results leave D-W strength unknown.

Raw native logs and inherited handled OpenDSS exception traces in regression
logs are preserved. Test exit codes/final summaries, original-file byte
preservation, model/authority SHA checks, ledgers and the SHA manifest give
provenance. `FINAL_REVIEW_KO.md` contains the requested ordered report.
