# V39D independent daily temporal-first AIDC migration

V39D is an orchestration-only successor to V39C.  Each May operating day is
an independent scientific sample.  A policy-blind synthetic RUNNING AIDC state
is frozen from the D-1 18:00 visible cohort before RW or RSP is evaluated.

The initial state may read only job UID, requested GPU, the frozen V39C site
capacities, and the frozen V22SR1 site prior.  It cannot read RW/RSP future
occupancy, grid/Fresh output, Actual output, migration results, or another
day's simulated state.  If the frozen RW reference is infeasible, V39D reports
`RW_REFERENCE_INFEASIBLE_UNDER_FROZEN_SYNTHETIC_INITIAL_STATE`; it does not
reshape initialization or rescue RW with time shifting or migration.

For RSP, the byte-preserved V37 temporal schedule is evaluated first with
RUNNING migration disabled.  Migration is opened only after that candidate
fails a hard site/Rack/planning gate.  Its primary objective is the number of
RUNNING migrations; PENDING initial placement is excluded.  Fixed V38 WAN,
checkpoint, READY, and restart semantics are reused unchanged.

Actual execution verifies the DA freeze SHA and may assign only a compatible
logical Rack inside the already selected AIDC using stable Rack-ID first-fit.
It cannot reoptimize time, AIDC, migration, or WAN routing.  Fresh and fixed
discrete restoration remain post-freeze validators and never feed workload
decisions.

V39D re-freezes the legacy 48 logical Rack IDs as non-additive, synthetic
single-gang compatibility envelopes.  The unchanged V39C AIDC capacity vector
is still the only aggregate GPU-capacity authority.  Thus logical Rack
compatibility cannot introduce the legacy 609-GPU ceiling, cannot add capacity
above the 624-GPU site total, and does not claim a measured physical Rack
census.  The rule is frozen and committed before any May preflight evaluation.

The AIDC sites are modeled sites in a trace-driven cyber-physical testbed, not
measured real-world AI facilities.
