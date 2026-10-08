# May11 numerical replay diagnosis and staged V3 adapter

Run: `native90_build_reuse_20261009_01`. Original source HEAD:
`2791ca66702e1ff1e952e4590bf10ae53a902c39`.

B1 May11 terminated as `IMPLEMENTATION_FAILURE` after the first Phase I
optimize returned status 2. Its saved original primal has an equality residual
of **1/524288 = 1.9073486328125e-6** at row 6622, above the unchanged **1e-6**
scientific tolerance. Independent rational replay confirms that this is an
actual residual, not sparse summation error. Bounds and reduced-cost sign
replay pass. Scientific infeasibility is not proven. Native Runtime **0.417s**
is already recorded in the immutable date ledger; no date retry is authorized.

The reporting defect is that the original Phase I guard raises one generic
exception without retaining either primal or dual replay details, and the
A-stage classifies it as an implementation failure. The isolated
`v42_may_replay_v3` candidate delegates the existing solve exactly once,
persists row/bound and dual replay evidence before rejection, and classifies
an evidenced numerical rejection as `NUMERICAL_FAILURE`. It delegates the
original A-stage builder, phase algorithm, original physical checks and Native
budget. It changes no matrix, objective, RHS, sense, bound, type, checkpoint,
STAY/migration candidate, cache, tolerance or solver parameter. It neither
repairs nor accepts the invalid May11 solution. There is no performance claim.

Validation: `VALIDATION.json` replays all 12 saved B1 Phase I S0 matrix/attribute/
raw receipts from May01-May12, verifies their original hashes, and matches the
original primal and dual verifier outputs exactly. Only May11 is rejected.
Seven focused tests cover primal/dual distinctions, tolerance boundaries,
single-solve delegation, unchanged Runtime/raw arrays, classification isolation,
and rejecting requests that have no explicit version admission. All validation
uses **Native=0/P2=0**; no campaign result, ledger or input is modified.

The candidate is **staged, not activated**. Current Worker imports, frozen
scientific and implementation hashes, and the campaign manifest remain intact.
A production source-boundary admission must include this candidate in the
new source freeze and request version before an unstarted date can use it.
Merely adding `replay_diagnostics_version` is not a scientific admission.
The current Coordinator has no such version handoff contract; changing the
frozen manifest ad hoc would violate identity checks. May11 remains terminal
and the existing campaign continues to later dates under its pinned V2 code.

May01 full preparation remains 1098.7472762s against the same-scope reference
755.9328127s (1.4535x, below the 1.5x warning). Later dates have different inputs
and are not compared against that May01 benchmark. This inspection found no
new model-generation stall; May12 CPU and actual pricing progress advanced over
more than two minutes. The live Worker was preserved.
