# G8T → G12E Compact Status — Pre-Feedback Legacy Checkpoint

This file records the meaningful bounded/full-day evidence accumulated after the earlier PR #5 authority. It is a **checkpoint, not the final post-feedback scientific design**.

## G8T — Native mobility architecture freeze — PASS

- Native K=3 route architecture confirmed.
- `separate_z_route_binary_layer = REJECTED_AS_REDUNDANT`.
- `MOVE_arc_binary_count = 0` is valid.
- `MOVE_arc_continuous_count = 100704`.
- `node_occupancy_binary_count = 4596`.
- `candidate_move_count = 100704`.
- Production `E_MESS` unit is MWh.
- `E_FLOOR_model = 0.44` corresponds to 440 kWh.
- The earlier G8R route/SOC attempt failed partly because it subtracted `440` from an MWh-domain variable; that design must not be revived.

## G9A/B/C — M3 no-dual-debt/rebound ablation

- G9A: config-level knob search did not find explicit decision knobs.
- G9B: decision-use constraint anchors found.
- G9C: one-issue bounded ablation PASS.
- Removed linear constraints total = 256:
  - support_debt_terminal = 4
  - r24_debt_suffix = 36
  - r25g_debt_stay_cover = 36
  - r25k_debt_stay_cover_dense = 180
  - workload_debt_terminal = 0
- Event Trigger, mobility, observability and Fresh AC remained active in bounded evidence.
- Later G12E showed the package-local deletion hook was not robust for every issue; do not promote the monkeypatch as production architecture.

## G10A — Materializer smoke — PASS

Materialized sidecars included:

- debt_rebound_step.csv
- workload_debt_step.csv
- dc_facility_power_step.csv
- mess_step_enhanced.csv
- exact_grid_step.csv
- constraint_event_step.csv
- controller_event_path_step.csv
- solver_runtime_step.csv
- wan_state_step.csv
- objective_cost_step.csv

Key semantic requirement: `NULL != 0 != NA != OBSERVED_ZERO`.

## G10B–E — Wrapper failures

Several wrapper/name-resolution failures occurred. These are diagnostic only and must not be represented as scientific failures.

## G10F — Four-method one-issue smoke — PASS

- M1/M2/M3/M4 runner return code 0.
- commit marker = 1 each.
- materializer PASS each.
- M3 ablation removed 256 decision-use constraints.
- no full-day / month / 12-week campaign.

## G11A — Event/replan freeze — PASS

- Frozen then-current M1–M4 comparison authority.
- Event classes frozen for legacy design: HARD / INITIALIZATION / PERIODIC / SOFT.
- One-issue evidence observed initialization full replan; it was not sufficient to establish event effectiveness.

## G12A — 24 issues/method day-readiness smoke — runner PASS, materializer strictness FAIL

Each method:

- runner return code 0
- commit markers = 24

But strict materializer passed only 4/24 because it incorrectly required `A_B10_FULL_PLANNER_SOLVE.json` on committed continuation steps.

## G12B — Observability gap audit — PASS

For each M1–M4:

- committed issues = 24
- strict-ready = 4
- gap = 20
- the only systematically missing source was `A_B10_FULL_PLANNER_SOLVE.json`.
- all other key observability sources existed.

Conclusion: materializer strictness bug, not missing physical observability.

## G12C — Solve-optional materializer fix — PASS

Across M1–M4:

- total materialized issues = 96
- PASS = 96/96
- optional solve missing accepted = 80
- solve present = 16

Correct semantic status for a continuation step with no full planner solve:

`OPTIONAL_MISSING_NO_FULL_PLANNER_SOLVE_FOR_COMMITTED_CONTINUATION_STEP`

This is the main clean reusable change to port into repository-level materialization logic if not already equivalent in PR #5.

## G12D — Packaging failure — NOT SCIENTIFIC

- Failed before runner start.
- Cause: missing `materializer_lib` Python dependency in generated package.
- Do not preserve as a scientific failure or production design.

## G12E — Full-day 288 issues/method — PARTIAL / LEGACY DIAGNOSTIC

M1:

- runner return code 0
- commit 288/288
- materializer 288/288 PASS
- optional-solve-missing accepted 232
- solve present 56

M2:

- runner return code 0
- commit 288/288
- materializer 288/288 PASS
- optional-solve-missing accepted 229
- solve present 59

M3:

- runner return code 1
- commit 37/288
- materializer 37/37 PASS for committed issues
- fails at issue 3493
- error: `G10F/G9C found zero explicit debt/rebound decision-use constraints to remove`
- bounded ablation audit still reports 256 removed constraints in earlier applicable issues

M4:

- runner return code 1
- commit 37/288
- materializer 37/37 PASS for committed issues
- fails at issue 3493
- error: `R62_FIXED77_DEFERRED_FREE_FEASIBILITY_FAILED:SKIP_NOT_M4_ISSUE5299_FIXED_LOCATION`

G12E global:

- `full_day_started = true`
- `full_month_started = false`
- `final_12week_started = false`
- `future_actual_jobs_used_for_optimizer = false` in failure evidence
- `future_D2_state_reinjected = false` in failure evidence

## Post-feedback interpretation

Do not continue the old G12F repair lane solely to make M3/M4 full-day green. Professor feedback will cause a new scientific design rebase. Preserve this work as reusable implementation/evidence and a legacy pre-rebase checkpoint.
