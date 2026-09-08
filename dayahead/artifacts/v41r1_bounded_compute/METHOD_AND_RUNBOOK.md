# V41R1 bounded-compute fix-and-optimize revision

The monthly algorithm is a **bounded-compute fix-and-optimize matheuristic**. The scientific formulation remains the original MILP. Every neighborhood retains its original physical constraints. An unchanged, independently verified incumbent is an accepted bounded-compute outcome; improvement and global optimality are not promised.

## Preserved scientific authority

- B0/B1/B2/B3, Q90, H4 R85_B2, fixed planned starts, one first-checkpoint RUNNING migration, GPU/rack/WAN, MESS, and the independent 24-hour horizon are unchanged.
- `domain.py`, migration eligibility, sparse interval recurrence, electrical methods and inputs, and Actual execution methods are unchanged. `STRATEGY_SOURCE_EQUIVALENCE.json` records the source comparison and B0 execution equivalence.
- Complete job segments and cross-midnight service remain materialized. Independent GPU/rack verification uses exactly the existing D00–D24 capacity horizon; it does not introduce an extra post-horizon capacity model.
- No AIDC top-K, sensitivity, job, destination, or random pruning is introduced. `FULL_CANDIDATES.jsonl.gz` stores every original option. A candidate ID is its job ID and full option index. Candidate SHA is computed over the uncompressed canonical rows.
- Counts of removals in the new candidate manifest refer to this computational revision: zero. Existing structural eligibility reasons remain in `authority/migration_before_solve/MIGRATION_ELIGIBILITY_SUMMARY.json` and its per-job tables.

## Search and accounting

A complete seed supplies every original model variable. Independent checks substitute every linear, bound, integrality, PWL, MAX and indicator row. Job materialization independently checks the GPU/rack interval occupancy, WAN and migration/state semantics, Planning grid and H4 values. Unsupported model constraint types fail the gate.

F&O reuses one model. All independent job decisions outside the current neighborhood are fixed to the accepted incumbent. An opened job keeps its entire original placement/STAY/migration domain. Auxiliary state variables remain governed by the original equations. Neighborhood sizes count independent job decision variables; derived GPU/WAN/source-state integer auxiliaries are not separate job choices.

Families rotate deterministically through critical time windows, pairs of IDC sites, RUNNING migrations, PENDING relocations and low-visit coverage. Only the lowest visit-count layer can open, so no second complete cycle starts before the first completes. Full option ranges share their job block's exact visit count. Unvisited candidates remain available and are reported explicitly.

The initial independent decision target is 5,000, adapting within 2,000–10,000 from the recorded previous solve time. Complete-job packing can leave a smaller final neighborhood. The per-neighborhood solve cap is 60 seconds. The ranking and adaptation rules are deterministic given their recorded inputs; wall-clock limits and machine load can change the number of completed iterations.

The 1,800-second policy-day budget is shared across A0/M1/A1/MF and their objectives. A0/A1 model building, seed substitution, solving and iteration verification/persistence are charged. Existing input/coefficient preparation and final scientific archive/Fresh/Actual processing are separately visible in phase wall time. Small shutdown/verification overhead is checked by the final budget gate. Budget expiration retains the verified incumbent.

P1/P2 are locked to accepted values using the existing numerical tolerances. The 3% neighborhood solve target does not allow a 3% deterioration of a higher priority. P3/P4 remain ordered, and P5 stays inside the remaining budget: equal P1–P4 does not prove identical physical trajectories. No weighted objective is introduced.

Exact aggregation only refines original coefficient-equivalent groups. UID-serial migratable jobs remain singleton groups, and the original P5 group rank is preserved.

B2 retains its existing MESS search and fixed B0 AIDC input. B3 reuses the exact accepted B1 AIDC result, then runs the inherited MESS search, A1 F&O and fixed-route P/Q recourse. MESS search retains a verified complete fleet checkpoint, including neutral trajectories for unprocessed vehicles. Its subprocess shares the policy-day deadline. It does not receive another 30-minute allowance.

## Evidence and classifications

- `POLICY_FEASIBLE_SEED_AUDIT.json`: complete seed and independent physical/model checks.
- `V41R1_FULL_CANDIDATE_MANIFEST.json`: original candidate counts, SHA and stage authority.
- `CANDIDATE_COVERAGE_REPORT.json`: exact option-range visit counts, distribution and unreached candidates.
- `bounded_checkpoints/ITERATION_*.json`: neighborhood, model size, time, memory, objectives, locks, materialization and checkpoint SHA/readback.
- `IMPROVEMENT_TRACE.json`, `BOUNDED_SOLVER_REPORT.json`, `POLICY_DAY_COMPUTE_REPORT.json`: compact progression and shared budget.
- `F_AND_O_LIVE.json`: current stage, iteration, budget and coverage for the monitor.
- `aggregation/F_AND_O_MONTHLY_SOLUTION_QUALITY.json`: all 124 units, including incomplete units and missing global certificates. Missing bounds are never converted to zero gap.
- `aggregation/V41R1_FULL_CANDIDATE_MANIFEST.json`: per-policy stage lineage, including B3's complete B1 A0 universe and its separately authorized A1 domain.

Neighborhood bounds are explicitly labeled as neighborhood-only. The production configuration does not run an optional global pass, so F&O output is `F_AND_O_NO_GLOBAL_CERTIFICATE`. The historical monolithic logs and bounds remain preserved separately. No neighborhood optimum is reported as a global optimum.

A solver proposal that exceeds the unchanged row tolerance is rejected. Its complete variable vector, residual audit and solver status remain in the rejection receipt. The retained incumbent is independently rechecked before continuing; the invalid proposal is never materialized or accepted. This behavior was verified by replaying the full-size May-04 P2 neighborhood that produced a GPU-to-PCC PWL residual above `1e-9`.

## Validation and operation

The difficult-instance acceptance is May-04 B1 with the full 1,800-second contract, complete iteration history, Fresh verification and Actual replay. No Full-May launch is authorized by a development-only test. The exact uncompressed acceptance MPS must match the full-size model used in the successful four-model/four-thread stress test.

The completed B0 phases retain their original bytes and producer commits. The accepted May-04 B1 phase bytes can be adopted after final freeze, with their working-tree validation provenance retained. Old attempts are labeled `SUPERSEDED_BY_FIX_AND_OPTIMIZE_COMPUTE_STRATEGY` by an additional receipt; original evidence is not erased.

New policy-unit output is provisioned on `D:/MobileESS_v41r1_FO_results` before generation, through the existing logical runtime paths. Accepted historical units keep their original paths. MESS temporary/search evidence and nodefiles use short, separately recorded D: directories. New attempts use separate logs so the watchdog does not mistake a historical traceback for a current failure.

Release order is `fo_release prepare`, final git commit, `fo_release freeze`, `fo_transition transition`, then detached `campaign_run launch` and `watchdog launch`. Release verification checks source and evidence hashes before dispatch. Production remains four day workers and four solver threads per day. The watchdog checks health every ten minutes; ten minutes is not a scientific solve timeout.

The predeclared stronger global B1 validation dates are May 3, 4, 13 and 22, selected from low/median/high B0 loading plus the predeclared difficult instance. Their source characteristics are in `REPRESENTATIVE_GLOBAL_VALIDATION_PLAN.json`. After Full May, a separate detached, single-worker run targets 0.5% global gaps with a finite two-hour search budget per selected day. P2 bounds are conditional on the monthly accepted P1 lock. This does not certify global B2/B3 optimality. Representative validation remains pending until its actual solver receipts exist.
