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

Classification: `POSTHOC_ENGINEERING_CAPACITY_REFREEZE`.
