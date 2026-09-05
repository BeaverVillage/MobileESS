# Cross-midnight / terminal-state consistency audit

## Decision

**TERMINAL_STATE_INCONSISTENCY_FOUND. May24, May25, and May26 are HOLD; none is released for Actual.** The current campaign orchestrator was not restarted and unaffected workers were not stopped. This is an audit finding, not a future-information-leakage finding.

The saved passing temporal-repair witnesses for May24, May25, and May26 increase post-midnight reservation occupancy. The next independent day's frozen state/DA does not carry that workload consistently. May17 and May23 have no incremental horizon escape from their repairs. There is no out-of-domain physical grid certificate.

May24 is an additional affected date: it has 4.5 GPU-h of incremental post-midnight work despite zero newly post-midnight starts or completions. The user explicitly approved extending the May25/26 HOLD gate to May24. All three dates are now blocked before Actual; none is terminal-consistency-cleared. This admission-only update reuses all completed audit arithmetic and evidence.

## Exact measurement convention

The accepted physical/grid horizon is issue slots **[24,120)**: 96 fifteen-minute slots, midnight to midnight, fixed AEST (UTC+10). The issue origin is D-1 18:00 AEST. A start at slot 120 is post-midnight; a completion at exactly 120 is not beyond the boundary.

For a job with GPU request g and reserved interval [s,e):

`post-midnight GPU-slots = g * max(0, e - max(s,120))`

GPU-hours are GPU-slots / 4. These are safe-reservation occupancy units, not measured runtime or electricity consumption. Every changed job retains the same GPU request and safe duration. Total reservation work is preserved, but this does not establish daily-boundary or next-day consistency.

The audit covers **95 changed standby jobs**: 62 / 1 / 9 / 15 / 8 on May17 / 23 / 24 / 25 / 26. B1 and B3 share the same AIDC schedule and are not counted twice. Job-level before/after starts, completions, boundary flags, and GPU-slot differences are in `CHANGED_STANDBY_JOB_BOUNDARY_AUDIT.csv`.

## Aggregate boundary metrics

Post-midnight before/after values below include **all jobs** in each day's reservation schedule, including existing baseline tails. The increment is caused only by the changed standby jobs.

| Day | New post-midnight starts | New post-midnight completions | Post GPU-h before | Post GPU-h after | Incremental post GPU-h |
| --- | ---: | ---: | ---: | ---: | ---: |
| May17 | 0 | 0 | 8,233.75 | 8,233.75 | 0 |
| May23 | 0 | 0 | 111,913.75 | 111,913.75 | 0 |
| May24 | 0 | 0 | 96,246.50 | 96,251.00 | **4.5** |
| May25 | 3 | 2 | 86,917.50 | 88,309.50 | **1,392** |
| May26 | 1 | 0 | 67,655.75 | 68,047.75 | **392** |

Changed-job-only post GPU-h before/after are: May17 0/0; May23 0/0; May24 30/34.5; May25 7,824/9,216; May26 3,728/4,120. The new post-midnight completion count is **2**, both on May25.

### Physical horizon versus full reservation domain

Out-of-domain below includes both the six-hour pre-operating interval and all post-midnight reservation time.

| Day | In-domain GPU-h before | IN_DOMAIN_GRID_GPU_H after | OUT_OF_DOMAIN_RESERVATION_GPU_H after | Incremental out-of-domain GPU-h |
| --- | ---: | ---: | ---: | ---: |
| May17 | 10,131.00 | 10,133.50 | 11,973.25 | -2.5 |
| May23 | 14,932.00 | 14,932.00 | 115,641.00 | 0 |
| May24 | 14,903.50 | 14,899.00 | 99,869.00 | +4.5 |
| May25 | 14,449.00 | 13,057.00 | 92,045.25 | +1,392 |
| May26 | 14,686.75 | 14,297.75 | 71,758.25 | +389 |

May26's post-midnight increase is 392 GPU-h while total out-of-domain increases by 389 GPU-h because 3 GPU-h also moves from the pre-operating interval into the operating day. May17 instead brings a net 2.5 GPU-h into the physical horizon.

Therefore the passing May24/25/26 witnesses **do remove in-day load and place additional reservation work after the certified horizon**. This describes the saved witnesses; it does not prove that horizon escape is necessary for feasibility or primary optimality. No counterfactual optimization was performed.

## Actual implementation and authority trace

1. `dayahead/v37/aidc_materializer.py:211` reconstructs each operating day's snapshot from source trace submission/start/end state at that day's own issue time. It does not read the previous simulated day's terminal state. `materialize_day` at line 554 builds fresh RW/RSP schedules from that snapshot.
2. `dayahead/v39e/initial_state.py:29` constructs a daily RW-anchored synthetic initial site state. Its saved authority explicitly records `previous_simulated_day_reads = 0`. `dayahead/v39e/evaluate.py:195` and `V39E_COMMON_INITIAL_STATE_AUDIT.json` record `inter_day_state_carry_count = 0` and zero cross-day AIDC-state reads.
3. `dayahead/v39e/full_preflight.py:81` loads those date-keyed initial states. It does not substitute the previous day's repaired terminal workload or site map.
4. `dayahead/v39a/spatial.py:72` clips reservation intervals to [24,120) before making production activity. `dayahead/v39e/temporal_refreeze.py` emits only those accepted-day assignments and the 96-slot GPU/PCC arrays. Its selective certificates explicitly set `outside_domain_site_grid_physical_claim = false`.
5. `dayahead/v39e/campaign_adapter.py:34` loads the current day's frozen 96 x 12 PCC arrays and current-date ledger. `configure_v37_runner` at line 116 binds this loader into Actual. There is no terminal-state carry input. The audit called only this read-only loader for May18, May24, May25, May26, and May27; every loaded PCC array exactly matched its frozen DA authority. **No Actual, MESS, Fresh, or physical-grid solve was executed by the audit.**

Thus the next day's own planning certificate verifies its independently reconstructed load, not the additional tail of the preceding repaired schedule. Coincidental reappearance of the same job UID is not a carry contract or proof of compatible remaining work, time, or site.

## Direct D-to-D+1 artifact comparison

These values cover the changed jobs' expected repaired occupancy during D+1. They include baseline tails and are not the same metric as net additional post-midnight GPU-hours above.

| Source day | Expected D+1 carry GPU-h | Same-time GPU-h matched in D+1 DA | Expected carry GPU-h not represented at that time | Matched job/site mismatches |
| --- | ---: | ---: | ---: | ---: |
| May17 | 0 | 0 | 0 | 0 |
| May23 | 0 | 0 | 0 | 0 |
| May24 | 34.5 | 0 | **34.5** | 0 |
| May25 | 1,144 | 88 | **1,056** | **1** |
| May26 | 1,536 | 0 | **1,536** | 0 |

Concrete examples, all in fixed AEST:

- **May24, job 9047207, 1 GPU:** start 22:00 -> 23:30; completion May25 04:00 -> 05:30. Both completions already exceed midnight, so the new-start/new-completion flags are zero, but post-midnight reservation grows by **1.5 GPU-h**. Jobs 9047208 and 9047209 show the same increment. D+1 reconstructs these as PENDING, not as the repaired running carry, and has no in-day assignment for them.
- **May25, job 9062345, 32 GPUs:** completion moves from May25 21:45 to May26 11:30, adding **368 GPU-h** after midnight. The next day's snapshot, initial state, and DA assignment omit this job UID entirely.
- **May25, job 9062346, 32 GPUs:** completion moves from May25 23:00 to May26 00:15, adding **8 GPU-h** after midnight. It is also absent from the next day's snapshot/DA.
- **May25, job 9062370, 32 GPUs:** the repaired future reservation uses **AIDC01**, while the next independent day reconstructs the same UID as RUNNING at **AIDC10**. Although 88 GPU-h overlaps in time, site and execution-duration histories are inconsistent. That overlap is not valid physical carry certification.
- **May26:** four of the five changed jobs requiring D+1 occupancy are absent from the next snapshot. The fifth, 9062397, reappears as PENDING at a different time/site rather than as the repaired reservation.

The future-day comparison also checks available May authorities beyond D+1. Some changed-job post-midnight reservations extend past May31: **888 GPU-h from May25 and 24 GPU-h from May26** lie beyond the available May physical authorities. No certification or eventual execution is claimed for those tails.

`DOUBLE_COUNT = NO` is narrowly an observed result: no duplicate assignment rows, or completed-prior-job replay, were found within the inspected changed-job/day comparisons. It is **not** proof of an inter-day deduplication mechanism; none exists in this route. Adding a carry overlay without reconciling independent same-UID jobs and remaining work could introduce double counting. Actual for the inspected future dates has not been run by this audit.

## Classification and minimum correction proposal — NOT implemented

- May17 / May23: **NO_INCREMENTAL_HORIZON_ESCAPE** for the repair increment. This does not certify all pre-existing baseline tails as a continuous multi-day simulation.
- May24 / May25 / May26: **TERMINAL_STATE_INCONSISTENCY_FOUND**. No day qualifies for fully carried, physically consistent cross-day occupancy.

The smallest correction consistent with keeping independent-day evaluation is an explicitly approved **baseline-relative terminal workload/reservation invariant**, not a same-day completion rule or arbitrary maximum-delay SLA. Prevent repair from outsourcing extra work beyond the baseline's accepted boundary obligation; reconcile the per-job queued/running status, remaining work, and future reservation timing rather than constraining only a net aggregate that could cancel between jobs. Existing baseline overnight jobs must remain legal.

After scientific approval, limit any changed formulation/refreeze and selective checks to the affected dates. Saved primary bounds/certificates can inform that work, but the previous primary optimum must not be claimed feasible under a new boundary contract without checking it. No such optimization or constraint change was made here.

A minimum-computation fallback to consider separately is the original base-RSP schedule plus the already solver-proven migration witnesses for May24/25/26 (2 / 8 / 15). This would remove the new repair-induced escape without re-solving migration, but it restores the accepted independent-day baseline; it does not magically create a continuous inter-day carry model. This fallback was **not** applied.

A genuine continuous multi-day alternative would require explicit per-job carry/remaining-work/site state and physical certification on the receiving horizons. That is a broader scientific change and is not authorized by this audit.

## Operational protection and preservation

- May24, May25, and May26 are `HOLD_TERMINAL_STATE_INCONSISTENCY_FOUND` in `TERMINAL_AUDIT_LAUNCH_GATE.json`.
- The day entrypoint checks this gate **before** runtime initialization and Actual. Missing/malformed gate evidence is fail-closed for all three dates. `--check-launch-gate` validates HOLD/HOLD/HOLD/UNAFFECTED for May24/25/26/27 without running a day.
- The existing parent process (PID 30196, original start time) has no hot-reload launch-filter hook. Without restarting it, the safe guard waits at day-worker admission and never enters Actual. When all three held entries reach the queue, they can occupy three of its four process slots; the remaining slot can continue unaffected dates. No replacement orchestrator or duplicate date work was created.
- The 4-day maximum and four Gurobi threads per active model remain unchanged. Audit arithmetic itself creates no solver.
- All **124 DA freeze files**, **470 May01–05 protected files**, and **138 required V39H artifacts** retain their SHA; protected May01–05 size/mtime checks also pass. The sealed production implementation fingerprint is unchanged. No previously completed unrelated date was invalidated.
- **9/9 audit/gate regression tests PASS.** Primary, migration, physical-grid, and Actual calls by this audit: **0**. No same-day completion constraint, SLA, voltage-limit change, full-month restart, or full-May rerun was made.

## Evidence files

- `TERMINAL_AUDIT_FINAL_STATUS.json`: required flags, aggregate metrics, classifications, loader checks, and preservation.
- `CHANGED_STANDBY_JOB_BOUNDARY_AUDIT.csv`: all 95 changed jobs and the requested before/after boundary quantities.
- `NEXT_DAY_JOB_STATE_AUDIT.csv`: D+1 snapshot, initial site, DA occupancy, and fixed-replay implications for every changed job.
- `FUTURE_MAY_JOB_OCCUPANCY_AUDIT.csv`: additional future-May occupancy comparisons.
- `PER_DAY_BOUNDARY_METRICS.csv`: complete in-domain/out-of-domain and carry metrics.
- `TERMINAL_AUDIT_SOURCE_SHA_MANIFEST.json`: exact inspected source and artifact fingerprints.
- `TERMINAL_AUDIT_LAUNCH_GATE.json`: the separate runtime HOLD authority; production DA files were not rewritten.
