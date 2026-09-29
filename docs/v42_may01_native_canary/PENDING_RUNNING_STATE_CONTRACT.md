# Current physical state and future planning reservations

For both known and unknown jobs, causally observed PENDING has current physical GPU occupancy zero. RUNNING has its full GPU gang at its causal native site. A previous counterfactual PENDING schedule is metadata, never evidence of an execution transition. `v42_may01.state.observe` separates these views and rejects an unsupported RUNNING site rewrite.

A known PENDING job remains in the current planning population. Its full gang is reserved on every selected future execution slot, including post-H carry-out. Neither PENDING status nor an old plan reserves physical GPU *now*. Conversely, zero current physical occupancy never deletes the selected future reservation. RUNNING elapsed/requested-remaining values come from the issue-time causal snapshot and frozen native service authority; no future completion is used.

Issue is 2025-04-30 08:00 UTC (18:00 AEST). Issue-origin slot 24 is May-01 D00 and slot 120 is D24. D24 is only the electrical boundary. The ledger keeps full exact seconds, padded 900-second reservations, and post-H reservations separately. PENDING duration is frozen ROLLING_Q90_TRACK_P_L2; RUNNING uses REQUESTED_REMAINING, not an estimate of realized completion. No runtime model is trained or invoked.

All 1,649 source records are retained: 1,395 PENDING, 254 RUNNING. The native source admits 1,605 records (210 assigned RUNNING). The 44 UNASSIGNED RUNNING records retain full physical gang and their source-authorized pre-D00 remaining-service representation in an unresolved external ledger. They are not FIX, are not assigned a fictitious site, and are not claimed to have actually completed. This follows the existing native reference contract; complete issue-time site mapping is not claimed.

The 321 PR79 intervals have two distinct audit views. Their RUNNING physical occupancy is within capacity, so none establishes a true physical conflict after separating PENDING plans. The original table was already a *future-reservation audit*: its 321 future-plan collisions remain recorded and are not claimed repaired. The historical counterfactual reference is not merged into the independent-day May-01 frozen reference.

Unknown arrivals have no D-1 job reservation. C0 is a same-hour nominal aggregate plus uncertainty envelope, without invented jobs, deadlines, or backlog. Unknown temporal/migration actions remain disabled. Checkpoint physics and full-service rules from PR90/91 are unchanged.
