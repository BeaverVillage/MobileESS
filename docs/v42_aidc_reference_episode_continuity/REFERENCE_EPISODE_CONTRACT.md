# Canonical synthetic execution-episode reference, V1

This contract implements a precomputed reference boundary. It does not activate a policy or certify a complete native V42 plan. Current readiness: **False**. All regression days are before May 2025. The numerical contract was registered in DESIGN_REGISTRATION.json before metrics were produced; no April electrical outcome was evaluated or used to tune it.

## Inputs and identity

Only the typed `Observation` fields, frozen GPU/rack capacity, prior weights and causally established reference obligations enter `ReferenceBuilder`. Source hash is a consistency/provenance check, **not a placement seed**: archive bytes may contain later records. The episode key hashes contract + normalized source UID + observed submission seconds + explicit attempt ID (when authorized). Source UID/submission continuity is checked across adjacent snapshots. Explicit causal attempt evidence may establish a new episode. Gap/reappearance, changed record/submit without attempt evidence, RUNNING→PENDING, changed RUNNING execution start or a contradicted PENDING→RUNNING start is EPISODE_BOUNDARY_UNRESOLVED. Such rows remain in the ledger and block executable use.

## Construction order and intervals

The builder runs once in chronological order **before policy workers**. Continuing assigned episodes keep site and logical rack without hashing or site first-fit. Reserve their full inherited service representations first. RUNNING uses the inherited causal remaining duration and issue-origin start 0. Continuing PENDING retains its absolute previously reserved start and current inherited requested duration. A planned start that is already past while the authoritative snapshot still says PENDING is an unresolved reference/service-state obligation. The contract does not pretend the job ran or silently choose a new start; it records REFERENCE_START_STATE_CONFLICT and blocks that state.

The current snapshot duration authority is retained exactly (including requested-walltime fallback). Slots are ceil(seconds/900), as in the inherited adapter. No realized future runtime/end is read. Negative/invalid resource observations remain outside the inherited controlled cohort with explicit status; oversize gangs remain indivisible and unassigned or preserve an inherited conflict. They are not scaled.

After continuing reservations, newly entering RUNNING episodes use deterministic weighted rendezvous preference, now keyed by episode, with descending gang/UID order and full-interval feasibility. New PENDING uses inherited service-tier/FIFO ordering and earliest resource-release event with numeric site/rack first-fit. An as-yet-unassigned continuing episode can receive its **first** assignment if all preceding obligations are resolved; an existing site can never be reassigned by repair. Failed carry obligations block new assignments rather than let new work consume uncertain capacity.

Site capacities remain (80,40,80,40,100,80,40,80,40,80,40,80), total 780. Each logical rack is a NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE. Pools add zero capacity and are not a measured physical-rack census. Validation sweeps all half-open execution endpoints, including post-H carry-out. Every conflicting interval includes site, GPU total, authorized cap and exact episode IDs. A row's capacity_feasible is not a full day's ready flag.

## Optimization boundary

Reference site, optimized initial placement and migration are distinct. An eligible PENDING job may select another compatible initial site in its daily policy; that never modifies the frozen reference ledger. RUNNING initial placement remains immutable. A valid policy checkpoint migration may change execution site in that independent counterfactual, but does not edit the reference or seed another policy day. Reference migration_selected is always false in this task.

Spatial eligibility is represented independently from nullable temporal eligibility. No missing RSP/RW authority is filled. `validate_initial_placement` supplies a conservative reference-boundary guard and does not replace/expand the existing A1/A2 implementation. Native deployment is not wired while gates fail.

## Frozen consumers

`frozen_day(directory, day)` reads REFERENCE_LEDGER_FREEZE.json and only that day's compressed JSON slice, checks the canonical hash and rejects unready freezes/states. `audit_only=True` permits diagnostic readback of blocked evidence, not policy execution. No worker output path or optimizer result is an argument. Chronological, reverse, seeded randomized and four-process invocations produce identical day hashes. The builder's chronological pass is policy-independent preprocessing, not interday policy carry-over.

## Unknown reference rule

`reference_action(gpu, duration, release, intervals, capacity)` implements numeric first-feasible baseline placement from current physical resource state. There is no policy-label, grid or outcome parameter. Same rule can choose different sites after prior physical actions produce different availability. The rule is provided and audited; the unfinished unknown-control policy is not activated. Historical selected actions are read only by the isolated physical-state forensic audit, after the canonical ledger is frozen.

## Blocking semantics

No change to runtime, CC4, MESS, kernel, trust, epsilon, temporal domains or migration permission resolves these conflicts. The default consumer fails closed. A future source-backed service-state reconciliation is required; this task does not invent it. A zero teleportation count alone is insufficient for closure. See FINAL_VERDICT.json and REFERENCE_CAPACITY_RACK_AUDIT.csv.
