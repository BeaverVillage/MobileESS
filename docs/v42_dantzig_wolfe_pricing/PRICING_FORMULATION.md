# Exact DAG pricing

The PR99 GraphFactory supplies finite starts, checkpoint compatibility and
deterministic WAN templates; its domain enumerator is never called by production.
The DP retains a best checkpoint prefix for each (source k, completed work u,
time tau). A prefix starts at s, checkpoints at c, and has u=c-s. Costs include
the entire source GPU interval, shift/preplacement, migration and selected y/q
event-rank terms. Checkpoint physical seconds remain a backpointer attribute.

At time tau, insert all authorized checkpoint prefixes c=tau, merging by minimum
cost for the same (k,u); propagate the label from the preceding time through
zero-cost WAIT. For every inherited (k,d,tau) WAN event and every label u, check
the full destination interval [restart, restart + Q50_service - u) against
immutable capacity and the original latest completion. Add exact WAN bytes,
active interval, full destination GPU, terminal Runtime risk and w/f1 event-rank
costs. Normal STAY paths are evaluated independently with full service. Include
the job's convexity dual once. Reconstruct only the minimum complete path and
validate it against inherited physical authority and deterministic transfer.

Correctness: for fixed (k,u,tau), all feasible checkpoint prefixes have identical
future transitions and remaining work. Their future GPU, WAN, Runtime terminal
and event-rank costs are identical. Keeping the lowest-cost prefix cannot remove
an optimal complete path. Time advances through WAIT and transfer/restart; an
initial carry-in checkpoint can have zero source length exactly when inherited
RUNNING phase permits it. There is no free site switch or compute during wait,
transfer or restart. All source prefixes and all feasible WAN times/destinations
are considered; no Top-K, sample, beam, shortened horizon or tail is used.

The graph is implicit: WAIT labels are propagated and WAN arcs traversed on
demand. Reported nodes count START/source-prefix plus time-layered labels;
reported arcs count STAY/checkpoint/WAIT and consumed-work/WAN transitions.
These are DP work counts, not the count of complete trajectory objects. No
checkpoint x destination x WAN-start Option table is built.

Within one immutable-dual sweep, identical physical jobs/graphs and frozen
completion-risk offsets can reuse the same exact minimum path. The full Job
metadata except uid is in the cache key; graph hash alone would miss gang size
in graphs without transfers. Convexity differs only by a constant and does not
change the argmin. Nonzero tie duals require the job's event-rank offset in the
key. Kernel/resources belong to one immutable factory. A new cache is created
for every dual snapshot. Cached and uncached minima/path sets are explicitly
tested with different convexity duals, gang sizes and tie duals. Every job still
receives its own column, RC and pricing receipt. Worker count remains one.

Bounded exhaustive scans compare minimum RC and exact old physical membership
under seeded vectors covering every coupling and objective metric. Full-column
LP and small binary comparisons are separate gates. One-job MILP fallback was
unnecessary: the inherited single-migration physics fits this DAG exactly.
