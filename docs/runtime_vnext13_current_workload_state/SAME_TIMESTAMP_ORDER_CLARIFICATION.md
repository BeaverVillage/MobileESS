# Exact tie-break keys in the preregistered implementation

The unchanged, preregistered stream13.py uses the total ordering
`(event_timestamp, event_kind_rank, canonical_source_row_index)`.
Kind ranks are SUBMIT=0, START=1, END=2. Source rows are canonically sorted by
`(submit_time, job_id)` before their indices are assigned.

Thus the short wording “stable job_id order after source canonical sorting” in
the original JSON contract means the stable canonical source-row order. For
simultaneous START/END events from jobs with different submit times, this is
**submit_time then job_id**, not a new global job-ID sort within the event batch.
This document clarifies that wording; the frozen dispatcher code, event schedule,
feature values, model inputs, and same-timestamp exclusion rule are unchanged.

Every event at timestamp t is withheld from every prediction at t. All events in
an earlier timestamp batch are applied before the next query. Distinct identities'
within-kind ordering does not change the resulting resource sums, sorted
quantiles, category counters, or model features. A delivery regression test
explicitly permutes simultaneous START identities and verifies feature equality.
The type ordering still matters for a single zero-wait/zero-runtime identity.
