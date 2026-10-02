# Current V42 common reference and B0

Primary base is PR118 exact head `86d77673a5f1cc04729cc742090bba1fb72a09fa`.
The user's current comparison and subsequent common-reference instruction are
the policy authority. Historical B0 producers and stored reference mappings
are not prerequisites. No historical requested-service schedule is promoted.

The new reference belongs to all four arms. B0 and B2 retain it with AIDC
flexibility disabled; B1 and B3 may optimize authorized deviations from exactly
the same population, GPU demand, runtime/service, arrivals, capacity, IT/PCC
mapping and reference. This task executes none of B1/B2/B3, May or M1 Benders.

The D-1 population is the entire current snapshot, including invalid/missing
GPU-request rows. No B0-specific eligibility filter is applied. Every row is
preserved in the output; incomplete rows are BLOCKED, never silently removed.
GPU gangs are not inferred from requested nodes, actual occupied nodes,
partition labels or an assumed full-node reservation. The current source
contains missing GPU requests; defining their workload requires a separate
source-backed authority. Missing workload is not treated as zero workload.

Runtime inference uses `v42_final.runtime.FrozenQ50` with the exact bundled
V10 T3 ISOTONIC ROLLING14 provider available at 2025-03-31 00:00 UTC.
Projected March/April request fields are joined by exact known job ID, with
submission and requested GPU identity verified against each D-1 snapshot.
Only submissions observed by issue time enter inference. Requested walltime
is an existing predictor feature. Service is current Q50 remaining seconds
and `ceil(seconds/900)`, not requested walltime. No fit or recalibration occurs.
Request-version history remains the source's UNVERIFIED proxy limitation.

The exact queue rule is frozen in
`V42_COMMON_REFERENCE_SCHEDULE_AUTHORITY.json` before any voltage execution.
Time origin is D-1 18:00 fixed AEST; D-day occupies issue slots 24 through 119.
Authoritative RUNNING source sites are reserved first. Missing-site RUNNING
jobs are ordered by decreasing gang then UID and placed at the first compatible
site with capacity, start 0. This is an explicitly modeled common reference
placement, not a measured Kestrel physical site. A supplied source site is
never moved. All observed running gangs remain hard at the observation boundary.
If Q50 is already expired, its physical occupancy is retained indefinitely
until a source-authorized release exists; no completion is invented.

PENDING jobs use strict FCFS by submit time then UID, earliest feasible start,
then ascending site ID. Source/home site, when supplied, stays fixed. Site
compatibility uses current V42's 780-GPU capacities and non-additive single-gang
rack envelopes. Queueing uses capacity only and has no grid objective. A later
pending job does not bypass an unresolved FCFS predecessor. No arbitrary large
sentinel start, gang splitting, reservation truncation or capacity repair is
introduced. Incomplete initial placement remains explicit BLOCKED evidence.

The generator has no voltage, line, price, D-Day result or May input and no
optimizer dependency. It rejects explicitly supplied future/grid fields.
Mapping audit records fallback counts, known nominal GPUh and its share. When
GPU requests are missing, total population GPUh remains unknown; the measurable
subset is not presented as the complete denominator.

B0 requires AIDC present and workload present. Timeshift, migration, pre-start
relocation, site-allocation optimization, MESS optimization and every Actual
repair/reoptimization count are zero. MESS P/Q/movement are zero. Scientific
acceptance requires strictly positive AIDC IT energy, PCC energy, active slots
and served workload with the common population unchanged. A contract flag is
not evidence that these physical checks passed.

Primary calibration uses S0 0.95–1.05. Production voltage constants remain
unchanged. Offline DA-AC is an external diagnostic, never an operational gate;
its failure cannot rescue, modify or reoptimize the frozen plan. Both replays
must share the same reference SHA, common input hashes and topology. Actual
must recompute IT from realized occupancy and independently reconstructed
physical arrays. These recomputation flags are null until a real replay exists.

Voltage CSV timestamps denote 15-minute interval ends in fixed AEST. April 30
slot 95 ends at May 1 00:00; this labels the April interval, not a May run.
Identical node/phase/slot/timestamp keys are required across all three curves.
Residual identity uses eight ULPs of voltage scale. Quantiles use linear
interpolation at `(n-1)q`, q=0.90/0.95/0.975/0.99, separately by direction and
pointwise/day-worst aggregation. Exceedance means strictly greater than 0.005.
Candidate bands may be asymmetric or empty and are never automatically adopted.

Current status: 30 days audited; zero approved executable common references,
zero complete realized workload authorities and zero scientific executions. Five
known-only mappings are initial diagnostics. The raw per-day
realized files do not supply complete carry-in coverage. All days also contain
missing realized H100 GPU requests. Header-only voltage/residual CSVs and null
summary fields record non-execution, not zero residual or physical feasibility.
The new package supplies validators, reference construction and statistics;
it does not yet supply a complete April physical producer. Integration of
source-complete realized episodes, current CC4 where required, current C1/PCC
and April grid coefficient/replay authority remains pending after workload
authority resolution. No older requested-service producer is substituted.

The five known-only mappings are initial diagnostics. Under the user's later
input-bundle-first contract, the approved REFERENCE namespace is NOT_GENERATED
until the full Planning/Actual input gate passes. The full raw-root inventory,
47 LFS payload SHA matches and expanded 30-day bundle/recovery evidence are in
APRIL_V42_SOURCE_RECOVERY and APRIL_V42_INPUT_BUNDLE. Historical mapping search
is not a prerequisite. Request-version causality remains explicitly unverified.

Scientific statistics must call complete_calibration_residuals with the physical
feeder's authoritative node/phase set. Matching partial curves cannot silently
become full-day calibration evidence. The lower-level residuals helper only
checks supplied-row alignment and arithmetic.
