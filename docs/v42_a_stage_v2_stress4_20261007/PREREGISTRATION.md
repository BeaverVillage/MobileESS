# A-stage Domain Authority V2 four-date stress qualification

Continuation authorization was received after the formulation-only task. The
current work was preserved by checkpoint commit
`08cdba2f5988c4f5334e24548257bcd505a949cd` on
`codex/v42-a-stage-domain-authority-v2`. Historical PR134/163/165/166 evidence
is read-only. The executed source and all independent gate receipts must be
frozen by SHA256 before any native stress solve.

## Authorization gate

The stress guard remains closed outside an explicit `StressRunPermit` scope.
A permit requires distinct PASS receipts for domain authority verification,
all pre-run tests, complete STAY equivalence, migration equivalence audit,
lex-stage rebuild, migration-zero projection, shift integrality, safe shift
strengthening, common no-flex nesting, May17 rescue membership, May19 PR165/166
membership, and scientific input identity. Gate and execution-source hashes
are rechecked before every native optimize call. Receipt/code drift fails
closed. There is no environment-variable or CLI bypass. Execution-authorization
tests use Python sentinels/control-flow mocks and make no real native solve.
Other short tests may solve tiny synthetic fixtures; no stress-date production
optimization is permitted before all gates PASS.

## Four isolated dates and one policy

Run order is May17, May19, May12, May10. This is an operational order; no
scientific equation, candidate membership rule, strengthening inequality or
solver setting depends on the date. One child process handles one date,
preventing B1's source/date-routed global namespaces from leaking across dates.
The other 27 May dates remain unauthorized. No 31-day campaign is launched.

The frozen Gurobi version is 13.0.2. Local parameter metadata supports
`NodeMethod=1` and `MIPFocus=3`. The single algorithmic policy uses `Threads=1`,
`Method=2`, `NodeMethod=1`, `MIPFocus=3`, and automatic `Crossover=-1` inherited
from the frozen native default. The existing `Seed=20260929`, `MIPGap=0.005`,
`FeasibilityTol=1e-6`, `OptimalityTol=1e-6`, `IntFeasTol=1e-5`, and other frozen
parameters remain as recorded in `A_STAGE_SOLVER_POLICY_V2.json`. Diagnostic
LP `Crossover=0` is rejected for the production MILP. No parameter sweep,
alternate-method retry, artificial slowdown, or memory admission guard is
authorized. Resource observations do not control execution.

## Scientific stages and budget

Preserve rho, migration count, shift magnitude, prestart relocation in that
order. Each date has one cumulative 3600-second native A1 budget measured by
current-run Gurobi Runtime. Build/static verification lies outside that budget.
Each pass receives only the remaining native budget. No historical bounds,
locks, partial native clock, or fabricated May12/19 start is imported.
Historical feasible schedules may become starts only after independent replay
under the new authority.

Continuous rho uses the inherited tolerance/gap authority. Integer objectives
require independent integer optimality certificates over the active model.
Completed integer objectives use exact equality locks; rho uses the inherited
1e-7 lock tolerance. Fresh stage models/projections must independently preserve
the original model plus these new-run locks. Migration-zero projection is used
only when the newly proved migration optimum is exactly zero. Nonzero migration
counts are never forced to zero. Projection lifting must pass original-row and
independent physical verification before an incumbent is retained.

## Domain closure and downstream production

Complete physical STAY support must be active and independently exact. Lazy
migration options retain their original scientific authority. Feasible or
lexicographically solved active models are explicitly classified as active
domain results. Root LP pricing closure is never integer-domain closure.
An unresolved omitted integer universe cannot produce `A1_FULL_DOMAIN_ACCEPTED`.

Planning freeze, fixed Actual, Fresh OpenDSS and independent physical validation
require a verified integer-domain closure certificate, all scientific objective
certificates and independent physical PASS. These actions additionally require
an accepted-pipeline scope for the corresponding stress date. Actual-stage
reoptimization and P/Q repair remain zero. No downstream pipeline runs for
restricted-domain optima with unresolved closure.

## Observations and stop conditions

Capture stage model counts/build time, inherited/effective parameters, presolve
and presolved sizes, root/barrier/crossover observations, first incumbent and
incumbent/bound histories, numerical warnings, Work, nodes, gap, RSS/peak RSS
and available RAM. Unsupported or missing quantities remain null. Kappa is
recorded only when available; KappaExact is not silently computed. Native
callback observations are labelled separately from explicit solver-log timing.

Date timeouts/unresolved solves continue to the next date without budget
extension. Scientific identity mismatch, corrupted input, failed exact
equivalence or invalid physical/original-row replay stops the experiment.
Final reporting retains active/full-domain acceptance separately, identifies
every unresolved closure, and never turns TIME_LIMIT into infeasibility.

## CLI protocol verification

The command-line entrypoint delegates to the canonical package module so the
backend and runner use the same `StageBuild` class. A real subprocess regression
executes four fresh stages with current-run locks through a pure Python mock
adapter. A native-optimizer sentinel remains uncalled. The subprocess also
rejects an unauthorized May date before importing the adapter. These fixtures
exercise execution protocol only and provide no scientific production result.

