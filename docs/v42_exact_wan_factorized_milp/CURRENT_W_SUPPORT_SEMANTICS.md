# PR99 WAN support semantics
The frozen source is `v42_compact/graph.py` at 3309cd230cd8235201f5578d392241fa98e059bc. `w[j,k,d,tau]` indexes job, source, destination and transfer start. Start and checkpoint events remain separate, coupled by source/wait balances, compatibility and full-service conservation.

PR99 sweeps checkpoints c <= tau and finds maximum completed prefix c-s among compatible starts. It requires the inherited transfer template to be feasible, restart + shortest remaining duration <= latest completion, and immutable destination fit for ONE slot. The last check alone does not prove full remaining service. Checkpoints after the last available departure are removed. f1 and r1 span broad completion envelopes.

The inherited transfer uses nominal path bottleneck capacity, including zero-rate slots, then rejects incompatible immutable WAN/active occupancy. It never substitutes residual capacity as the transfer rate. Source prefixes, site/gang/rack authority, and physical 1800-second checkpoints remain frozen.
