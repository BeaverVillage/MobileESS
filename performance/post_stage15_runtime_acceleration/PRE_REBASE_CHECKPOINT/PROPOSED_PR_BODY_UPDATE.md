# Suggested PR #5 Body Addition — Latest Pre-Rebase Checkpoint

Codex should adapt this to the actual final commits/tests rather than pasting blindly.

## Latest pre-rebase checkpoint (G8T–G12E)

After the original PR #5 bounded release work, additional local scientific/observability smoke tests were performed before a planned professor-feedback scientific redesign.

### Native mobility / formulation audit

- Confirmed the production model already uses the native K=3 candidate-route architecture.
- Time-expanded move arcs remain continuous and node occupancy carries the binary routing state.
- A separate `z_route` binary layer was rejected as redundant.
- Confirmed the production `E_MESS` model unit is MWh and the protected floor is 0.44 MWh = 440 kWh.

### Observability materialization correction

A committed continuation/fast-dispatch issue does not necessarily produce `A_B10_FULL_PLANNER_SOLVE.json` because no full planner solve occurred. The offline materializer now treats that source as optional only for the correctly identified continuation case while preserving a solver/runtime row and explicit source status. Zero-valued observations remain distinct from missing values.

Bounded validation materialized 96/96 M1–M4 issues, including 80 valid continuation cases without a full-planner-solve file and 16 solve-present cases.

### Full-day legacy smoke

A 288-issue/method full-day smoke was then attempted on the pre-feedback M1–M4 matrix:

- M1: 288/288 committed; 288/288 materializer PASS.
- M2: 288/288 committed; 288/288 materializer PASS.
- M3: 37/288 committed; stopped at issue 3493 because the package-local no-debt/rebound ablation hook found zero removable decision-use constraints for that issue.
- M4: 37/288 committed; stopped at issue 3493 in a legacy fixed-location feasibility hook.

The M3/M4 failures are retained as implementation diagnostics; they are not hidden or rerun for favorable results. No full W02 or 12-representative-week campaign was completed.

### Scientific-design boundary

This PR is being frozen as the pre-professor-feedback implementation checkpoint. The next branch will redesign the scientific comparison/controller around the revised research question and will reuse the validated traffic/grid/MESS/OpenDSS/observability infrastructure. The old M1–M4 long-run campaign is therefore not continued from this checkpoint.
