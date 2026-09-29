# V42_CONTINUOUS_SERVICE_INDEPENDENT_SNAPSHOT_V1

D24/H=96 is an electrical evaluation boundary, never a job completion deadline. This normative contract implements the current user instruction; it does not promote a new runtime predictor or an unselected temporal eligibility rule.

An admitted job has exact authorized compute seconds W, integer gang G and complete compute segments. Allocation reserves ceil(W/900) full gang slots. Exact compute W and unused final reservation seconds remain separate; rounding resource reservation upward is not additional compute. Sum of segment lengths equals allocated slots, segments cannot overlap, and prefix compute + post-H compute equals W. Transfer/restart gaps are not compute. All tail GPU/resource constraints are retained. No GPU clipping, splitting, service dropping or artificial midnight completion.

Electrical support is [start,min(end,H)); no post-H electrical-security claim. Full-service feasibility, electrical support and post-H carry-out are distinct quantities. `NativeServiceBoundary` requires source hashes for exact duration and finite authorized start window. Its completion bound is a representation ceiling covering all retained tails, not D24. It cannot authorize delay from QoS/requested walltime by itself. PR90 option construction still enforces a checkpoint, complete WAN transfer/restart and useful destination compute before the control boundary for migration.

Reconciliation keeps previous counterfactual plan history. A same-site causal RUNNING observation replaces the old plan in an independent day's current view; this does not delete previously executed service. An expired PENDING counterfactual start remains unresolved, without requeue or start reset. Completion release requires an observed COMPLETED state plus a matching causal episode/source receipt. Current RUNNING cannot be released by an old completion receipt.

Use the next day's authoritative snapshot independently when causal sequential execution cannot be demonstrated. No fabricated D+1 state, no stacking old RUNNING reservation on top of current remaining service, and no claim of sequential policy validation. PR79 already used this RUNNING replacement structure; semantic closure alone does not eliminate its resource conflicts.

Structural service/tail semantics are ready and tested. End-to-end native reference placement, selected temporal windows and production duration providers remain gated separately.
