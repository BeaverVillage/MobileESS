# PFR0-PFR2 Scientific-Rebase Foundation

This foundation inherits PR #5 at
`f728d4635922c02f08c1f146ced7c932a866d5df` without changing its historical
evidence.  It separates the post-feedback AI-training design from the legacy
M1-M4, Event30, and Local Repair scientific line.

## Scope

- PFR0 records the inherited checkpoint, retained infrastructure, superseded
  scientific methods, and explicit long-run prohibition.
- PFR1 records portable dataset identities, hashes, schemas, measured/modelled
  boundaries, and roles.  Local paths are supplied through environment
  variables and are not committed.
- PFR2 supplies typed checkpoint-aware training state, lifecycle, gang
  feasibility, work/resource accounting, migration payload, measured
  power-utilization, and fixed-inference primitives.

No full-day, representative-week, 12-week, or annual campaign is authorized or
started by this branch.

## Data findings

Kestrel F30 remains the 59,901-row operational timing/resource backbone.  Its
SHA-256 matches the inherited historical value.  It does not identify neural
network architectures and does not measure training progress, checkpoints, or
restart overhead.

The downloaded H100/B200 Figshare archive contains 95 CSV members.  The audited
node schema measures timestamped CPU/GPU utilization, power, memory, and
temperature.  It does not expose a defensible throughput target or checkpoint
and restart fields.  Therefore PFR2 provides a measured power-utilization
envelope contract but deliberately does not fabricate a power-throughput curve.
H100 is the primary compatibility path and B200 is sensitivity-only.

MIT Supercloud and Alibaba GPU data were not found in the bounded local search.
They remain optional and no replacement data was downloaded.

## Scientific boundaries

- Resource occupancy is accounted in GPUh.
- Work progress is separate normalized effective compute, not FLOPs or tokens.
- A required GPU gang must be allocated simultaneously at one eligible site.
- Site and gang are immutable between checkpoints.
- Spatial migration is permitted only from `CHECKPOINT_READY`.
- Migration payload is missing destination dataset bytes plus one checkpoint
  state representation.
- Online inference remains fixed background load.
- Independent traces cannot be row-wise merged into a purported real joint
  deployment record.

PFR3+ must resolve training-throughput authority before fast compute recourse
can consume a power-throughput curve.
