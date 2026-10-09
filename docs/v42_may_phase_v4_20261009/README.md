# May19 Phase I normalization defect and staged V4

In `native90_build_reuse_20261009_01`, B1 May19 terminated as
`IMPLEMENTATION_FAILURE` after 57 Native calls totaling 46.33699941635132
seconds. The original inclusion check raised
`PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT` after selecting 64
verified physical candidates. Its result and budget remain terminal and intact.

The original Phase I constructor recomputes dyadic normalization from the
largest currently active coefficient. Adding native support changes that
scale even though the coupling row identity, RHS and sense are unchanged.
The next inclusion witness requires the previous artificial weights to stay
fixed. Reconstructing the saved May19 initial state and selected batch, without
optimizing, reproduces this contradiction. Initial reference and compact
weights agree; the activation changes weights while signs remain unchanged.
The full details are in `DIAGNOSIS.json`.

`v42_may_phase_v4` stores the original first compact Phase I weights by global
row identity. It calls the existing elastic constructor with these weights for
restricted, compact and reference models, including subsequent activations.
Restricted row indices map back to their full row identity. Changed global
RHS/sense or unrecognized rows fail closed. The original Phase I code object,
row promotion, pricing, candidate selection, stagnation rule, P1, integer
restoration and physical validation are reused. Legacy module globals and
current Worker source files are unchanged.

On the reconstructed May19 activation, the original prior-point inclusion
and compact inverse replay pass at the unchanged 1e-6 tolerance. The exact
previous Phi is preserved. Original and expanded reference fingerprints,
expanded compact fingerprint, raw arrays, class membership and complete
physical domain SHAs remain unchanged. This verifies the specific inclusion
defect; it does not certify a completed May19 solution. `VALIDATION.json`
contains the independent results. No production point, ledger, budget or
completion is transferred. Saved raw values are used only for offline diagnosis.

The real May19 reconstruction/replay uses Native=0/P2=0. The seven focused V4 tests plus the existing replay,
Phase I, compact row generation, maintenance-lock and Native budget regressions
pass: 72 tests. The broader Phase I/compact suites include tiny synthetic
Gurobi solves outside the campaign. Separately, 24 V4/replay/lock/budget tests
pass with actual Gurobi optimize blocked by `native_zero_scope`; these are
the Native=0 regressions. No campaign optimize call is made by maintenance.
Initial test-harness attempts used a C-drive temporary path or
a missing D-drive parent; the final run uses an existing, isolated D-drive
temporary parent and passes. There is no model-preparation speed claim.

The candidate is staged only. The current frozen Coordinator has no admitted
source-version handoff contract. Merely inserting `phase_weights_version` into
a request is insufficient admission. A future unstarted Worker requires a
validated source boundary including V4 and the frozen scientific authority;
editing the live manifest or restarting completed dates would violate the
current identity and no-retry contracts. May19 remains terminal, and the
existing campaign continues under its pinned V2 source.
