# V39C gang-aware synthetic AIDC capacity re-freeze

V39C replaces neither measured facility data nor the V37 temporal scheduler.
It explicitly classifies the legacy site vector as a synthetic allocation and
constructs a new synthetic H100-equivalent site compute capacity from a fixed
engineering rule: eight 4-GPU nodes per modeled AIDC, seven additional
32-GPU blocks assigned by the V22SR1 facility-size ordering, and the remaining
four nodes assigned to AIDC05.

The capacity is materialized and hash-frozen before any V39C May feasibility
evaluation. May results cannot feed back into the numeric vector. Evaluation
then retains the V37 RW/RSP schedules byte-for-byte and tests slot-local,
contiguous-interval, and causal stateful AIDC placement in sequence.

Stage C preserves the zero-migration result as a non-authoritative C0
STAY-only diagnostic.  The readiness gate is C1: RUNNING jobs carry their
source `current_AIDC` but may stay or complete a frozen-path V38 checkpoint,
serialized inter-AIDC WAN transfer, READY transition, and restart.  C1 uses a
literal zero feasibility objective.  Only after C1 passes, a separate causal
witness solve minimizes RUNNING migrations; PENDING initial placement is not a
migration.  A deterministic numeric-AIDC feasibility-preserving pass resolves
placement ties without peak-utilization, grid, Fresh, or May-result objectives.

Stage C execution classification:
`SCIENCE_NEUTRAL_FEASIBILITY_EXECUTION_SIMPLIFICATION`.

Classification: `POSTHOC_ENGINEERING_CAPACITY_REFREEZE`.
