# Day-Ahead Planning contract

`v42_native.coordinator.run(backend, output, seconds=600)` retains supervised,
bounded A1 → M1 → A2 → M2, same-state warm starts and fixed-A2 M2 no-regret.
After validated stage candidates it calls `backend.combine(a, m)` exactly once.
The composition must supply every field in `DAYAHEAD_FREEZE_SCHEMA.json`;
incomplete compositions fail closed rather than manufacturing schedules or hashes.

`freeze_day_ahead_plan(final_plan, output, grid_sha=backend.grid_sha)` writes:

- `DAYAHEAD_PLANNING_FREEZE.json`
- `DAYAHEAD_PLAN_SHA`
- `POLICY_SHA`
- `GRID_SHA`

Publication uses exclusive creation; an existing freeze is never overwritten.
The frozen object stores immutable JSON bytes and returns detached mappings.
Reload validates field coverage, existing causal interface, authority hash format,
finite JSON, full plan digest, policy digest, and grid identity. The backend
grid SHA must equal the supplied grid anchor. Logical immutability is enforced by
hashes and write-once publication; this is not an OS filesystem permission seal.
Partial I/O publication fails closed and is never an accepted completed freeze.

`DAYAHEAD_PLAN_SHA` hashes the entire plan, including all schedules, policy,
electrical footprint, grid anchor and input authority hashes. Canonical hashing
uses the existing `v42_native.contracts.digest`: sorted JSON keys, compact
separators, default ASCII escapes, finite values, UTF-8 and SHA256. `POLICY_SHA`
hashes the entire unknown-arrival policy/interface; `GRID_SHA` is the existing
explicit physical grid authority hash, not a newly invented topology authority.

Return: `status=DAYAHEAD_PLANNING_FROZEN`, `final` (detached schedule),
`frozen_plan` (verified immutable object), stage receipts, and all three SHAs.
No `fresh_ac` receipt or PASS requirement occurs in this function. Completion
does not assert scientific M1 acceptance, Actual PASS, or kernel readiness.
Production adapters must retain independent native stage acceptance checks.

M1/A2/M2 retain 0.955–1.045 pu (squared 0.912025–1.092025).
A1 retains its existing 0.95–1.05 pu bootstrap authority. No voltage constants,
margin policy, model formulation or optimizer behavior are changed.
