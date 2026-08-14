# R26 Event-Triggered Mobility Replanning with Five-Minute AC-Aware Dispatch

R26 is a separate online-control architecture. It does not alter or replace the
frozen R25R Stage-1 exact benchmark.

## Authority boundary

R25R retains the five-minute H54 model, exact all-column lower-bound authority,
global modeled-total-objective gap at or below 3%, causal PRE-to-POST state
chain, h0-only commit, four Gurobi threads, and Fresh Exact OpenDSS gate. A
restricted-master `ObjBound` or its native MIP gap is never a global scientific
certificate.

R26 does not claim an online 3% exact certificate. Its slower worker seeks the
best feasible route/work candidate within a configured runtime budget. The
five-minute loop retains a valid old plan while that worker runs and never waits
for it.

## Five-minute sequence

1. Load only information available at the current cutoff.
2. Restore the authoritative PRE state and verify its hash.
3. Poll the single route worker without blocking.
4. Validate and atomically swap a candidate only at its issue boundary.
5. Shift the active immutable route plan by exactly its committed first step.
6. Evaluate configured HARD and hysteretic/dwell-qualified SOFT events.
7. Start or coalesce an asynchronous planner request; retain the old plan.
8. Fix route/work decisions and solve the existing AC-aware radial dispatch QCP.
9. Report the actual remaining `NumIntVars`; call it continuous only when zero.
10. Run a Fresh nonlinear OpenDSS AC power flow.
11. Commit h0 and POST only if feasibility, numerical, transition, and OpenDSS
    gates all pass. Otherwise fail closed.

## Plan safety

`RoutePlan` is immutable, canonical-JSON hash addressed, and includes creation
and cutoff timestamps, source-state hash, valid issue, cadence, horizon,
per-MESS states/actions, committed prefix, causal terminal extension, planner
status/objective/runtime, parent checksum, and plan checksum. Transit state is
explicit. A shift rejects a committed first step that differs from the plan,
preventing silent rewrite or teleportation.

## Event and planner rules

Tier-1 HARD feasibility events bypass dwell. SOFT rules are categorized as
Tier-2 security margin, Tier-3 prediction deviation, or Tier-4 economic events,
and use separate trigger and release thresholds for hysteresis. Maximum refresh
is configured in steps. One audit record contains every reason. At most one
worker runs; newer requests replace the pending request while their reason sets
are coalesced. Invalid, infeasible, hash-mismatched, or stale candidates are
rejected. An invalidated active plan may be replaced only by a prevalidated
boundary-compatible fallback; otherwise the controller fails closed.

## AC physics decision

The fast layer initially keeps the current AC-aware radial QCP, followed by
Fresh nonlinear OpenDSS. Sensitivity OPF is not implemented at this stage. It
may be evaluated only if mobility-conditioned fast dispatch still misses the
300-second maximum runtime gate; any such later design requires a trust region,
refreshed sensitivities, OpenDSS verification, and corrective fallback.

## Validation order

The R25R exact reference plus fixed and event-triggered 15/30/60-minute matrix
and threshold-sensitivity grid must be completed before selecting a policy. A real-time claim requires every measured
five-minute fast-loop runtime to be below 300 seconds, with p95/p99/max reported.
Annual execution is authorized only after that validation and uses four
independent monthly processes, four solver threads per process, and a causal
48-hour monthly burn-in.

See `R26_METHOD_REVIEW_DEFENSE.md` for the novelty boundary, conditional
recursive-feasibility statement, sensitivity design, and reviewer-facing
metrics.
