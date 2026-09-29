# Audit and observation scope

The event stream covers the already-separated pre-April GPU-job source through
2025-04-01T00:00Z (exclusive). The original final label-information cutoff remains
2025-03-31T08:00Z. Materializing later pre-April submission rows does not add them
to a TRAIN/CAL/VALID role or reveal their events to an earlier query. All fifteen
original role memberships and censored labels are unchanged and hash-verified.
No April or May payload is used by this task.

The offline adapter sees timestamps only to schedule SUBMIT/START/END events.
It emits no end/start timestamp in a SUBMIT request and no outcome in a START.
The time dispatcher may compare scheduled timestamps to a query boundary to
withhold delivery. This necessary event scheduling operation is not a feature
read of a future start/end. The state engine has no access to that schedule or
the archive. Its public apply method independently rejects every event at or
after the prediction boundary.

The causality audit changes the entire future suffix, including simultaneous
events and the current job's future events, at 1,024 random prediction points.
Suffix payloads are represented by a universal poison accessor rather than
copied hundreds of millions of times. A separate audit concretely changes every
future scheduling timestamp at another 1,024 points and verifies that exactly
the same prefix is delivered. Past SUBMIT GPU changes are positive controls.
An independent lifecycle reducer verifies pending/running counts, resource sums,
ages, arrival-window counts and GPU sums without using the state implementation.

The full replay compares every feature value, including NaNs, and a canonical
row hash for all621,583 rows. Four sequential fresh processes restore the prior
trusted checkpoint and dispatcher cursor. This tests both chunking and process
restart; it is not parallel off-policy state construction. The checkpoint bundle
includes the state pickle and cursor.json schema/version/next-query metadata.

Hourly intermediate queries are used only for the long-gap forensic snapshots
to expire rolling buffers efficiently. They consume the same chronological
events and do not change the requested boundary's membership or features.
These boundary snapshots use a descriptor-free dummy query. Job-specific
same-account/QoS/partition counters and interaction columns in the full snapshot
therefore describe that missing-descriptor query, not a global cluster measure.
The forensic conclusions use only global arrival pressure, pending/running
resource counts and composition. Undefined numerical interactions remain NaN.

These checks establish event-time consistency for this trace-derived stream.
They do not establish original-submit immutability, full cluster observability,
real scheduler delivery latency, causal effects of queue pressure on runtime,
or deployability of an unvalidated model. Fold boosters are research components.
