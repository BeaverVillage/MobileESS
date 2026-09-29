# V13 event contract

The offline adapter splits the existing pre-April GPU-job trace into a request
table and a chronological event schedule. The state module cannot access archive
rows, actual runtimes, or endpoint columns. SUBMIT carries only the nine request
proxies. START/END carry identity and their own observed timestamp only.

At query t the dispatcher delivers strictly earlier events. Every simultaneous
event is excluded; for later predictions a timestamp batch is applied in
SUBMIT, START, END order, then stable identity order. A zero-duration job can
therefore become terminal without remaining spuriously active. END can terminate
a pending cancelled episode; late START on a terminal identity is ignored.
Missing END never creates a completion. Pre-submit malformed events are excluded
individually, recorded in the adapter audit, not repaired using future endpoints.

The engine rejects future events, chronological reversals, outcome/unknown keys,
and orphan START/END. Phase transitions make duplicate events idempotent.
The checkpoint serializes version, latest event/query, identity phases, pending
and running descriptors, observed start times, rolling arrival buffers, counters,
sorted order-statistic lists, and feature cache. The dispatcher cursor is separate.
Trusted local pickle is the research checkpoint encoding.

This is event-time causality, not proof of original-submit request immutability
or scheduler delivery latency. Kestrel_trace_proxy remains research-only. The
input covers GPU-requested jobs, not every Kestrel workload. No 780-GPU divisor.
