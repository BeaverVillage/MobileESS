# V42 architecture supersession

Base: Draft PR #117, exact head `e2d4779685fff6d0cf022c649733b2ca41fdfc08`.

Before: `v42_native.coordinator.run()` performed A1 → M1 → A2 → M2,
combined the schedule, immediately called `backend.fresh_ac(final)`, and
required matching Fresh AC before returning. Planning therefore contained an
AC execution stage. The existing final-kernel predicate required a PASS and
plan hash but did not identify a D-Day execution layer.

After:

```text
D-1 information / forecast freeze
    → A1 → M1 → A2 → M2 (all Day-Ahead Planning)
    → FINAL DAY-AHEAD PLANNING FREEZE
    → D-Day Actual execution with realized load/PV/AIDC state
    → physical arrays reconstruction using unchanged frozen decisions
    → one Fresh OpenDSS AC validation (0.95–1.05 pu + line/transformer)
    → final response/event kernel eligibility only on this Actual PASS
```

`run()` returns at the immutable planning freeze. It neither calls Fresh AC nor
requires AC PASS. `run_dday_actual()` is a separate entrypoint. Failure remains
FAIL with the original receipt; there is no repair, retry, schedule rescue, or
global optimization. Actual physical adapter and OpenDSS producer remain trusted
backend capabilities, independently bound by hashes and mutation checks.

V41_DAYAHEAD_AC_VALIDATION = HISTORICAL

V42_DAYAHEAD_AC_VALIDATION = REMOVED_FROM_OPERATIONAL_CHAIN

V41 source/evidence and all inherited documentation are preserved byte-for-byte.
V41 is not reinterpreted as wrong. Earlier V42 reports describing coordinator
AC or kernel timing remain historical evidence and are operationally superseded
by this contract. The change to planning preflight replaces `final_kernel_anchor`
with `frozen_policy_interface`: an existing frozen causal interface is an input;
a final response/event kernel produced after Actual is not a planning prerequisite.
This replacement does not promote a missing runtime/policy authority.

Existing regression tests retain their assertions and fixtures. Historical
preservation tests now recognize this explicit source supersession through an
exact current/base SHA allowlist without changing old manifests. Read-only
snapshot checks reconcile inherited Windows CRLF receipt hashes against the
original Git blobs. The inherited Benders production `verify_inherited` and
`require_scope` guards are unchanged and intentionally remain closed on this
successor branch. Only their small synthetic unit tests use the read-only
snapshot audit as a test-specific scope fixture.

M1 remains unaccepted. Architecture/contract tests use explicit fake physical
adapters and small existing synthetic fixtures. No B0/B1, new M1 Benders research,
A2/M2 production, Actual production, OpenDSS production, retraining, margin
redesign, or Problem 13 scientific validation was run.
