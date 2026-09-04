# V39B RW/RSP baseline semantics audit

Diagnostic label: `NON_PRODUCTION_DIAGNOSTIC_ONLY`
Source HEAD: `b78fa725e8f98ef43091dd67a8a642275de7f963`
Input manifest SHA-256: `41c4fc0db7ff056a0a6b1cfaa8f6806ed90742caed591da75f4e16393e6f7df6`
Solver seed/threads: `20260904` / `1`
Production mutations/future reads: `0` / `0`

## RW

Trace-derived D-1-visible workload arrivals and requested/remaining runtime, dispatched by protected-tier/FIFO first-fit against the modeled aggregate 624-GPU testbed capacity; it is not raw Kestrel execution replay.

## RSP

The same modeled aggregate-capacity tier/FIFO first-fit dispatch; RUNNING uses requested remaining runtime and PENDING uses frozen causal-safe runtime with requested-walltime fallback.

Both share the same modeled aggregate 624-GPU capacity and tier/FIFO first-fit
dispatch. The exact authority is `dayahead/v37/aidc_materializer.py`, together
with `V37_R4A_SCHEDULER_CONTRACT_RECOVERY.json`.

`REFERENCE_BASELINE_REDEFINITION_REQUIRED=NO`: RW already is a modeled
capacity-queued reference dispatch rather than immutable raw execution replay.
This does not authorize an arbitrary V39B reschedule. A separate scientific
decision must define latest-start/deadline/terminal-service windows first.
