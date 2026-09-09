# V41R4 May campaign implementation

This change continues PR #35 with the 780-GPU capacity rebase, native Actual
RegControl replay, compound-candidate ranking completion, and the final May
search-budget contract. Full May is still running; this is not a completed
31-day scientific result. The captured status is 20/124 completed policy-days.

## Final authority

- `alpha_BG = 1.15`; no additional alpha selection or tuning.
- AIDC capacity 780 GPU; existing per-GPU power, temporal shifting, spatial
  relocation, checkpoint migration, and existing 2/3-way compounds retained.
- Compound ranking consumes the full net site/time electrical effect, using
  the same hierarchical score as direct candidates; no new candidate products.
- Four MESS vehicles, each 300 kW / 400 kVA / 1200 kWh.
- B1 starts from the same day's B0. B3 is new B1 reuse (A0), M1, A1, then MF.
  A1 uses the B1 algorithm with all M1 route/location/P/Q decisions fixed.
- B1 A0 and B3 A1 each get a continuous 1800-second F&O loop clock, including
  candidate evaluation, ranking, electrical calculations, solver calls,
  in-loop validation/checkpointing, and overhead. One-time preparation is outside
  the timer. The original P1–P5 allocations are 900/480/180/120/120 seconds.
  No stagnation or objective-floor early stop; return the best validated feasible
  incumbent. A candidate validated after the deadline cannot replace it.
  Noninterruptible work beyond the deadline is reported separately.
- Existing M1/MF budget and lexicographic objective/constraint rules remain.
- DA uses nominal D-1 information. The later [Actual authority](../v41r4_actual/README.md)
  freezes DA discrete decisions and active-power schedules, and permits causal
  connected-MESS Q-only corrective AC-feasibility control with sequential native
  RegControl. Scheduling optimization, robust S0/S1/S2, quantile grid margins,
  and forecast-error correction are not introduced.

## Code and operation

`v41r4_loop_budget.py` implements the final timer and scoped engine adapters.
`v41r4_loop_runtime.py`, `v41r4_loop_worker.py`, and `v41r4_loop_campaign.py`
bind the final release, independent dates, retained B0/B2, and four day workers.
Earlier search-budget modules remain dependencies of the frozen adapters;
their solver-seconds and stagnation contracts are superseded, not launch targets.

The current operational launcher is `mission_loop_resume.py`, whose workers use
`mission_loop_archive.py`. This adapter fixes the unit archive's rejection of
approved retained B0/B2 Day-Ahead junctions. It permits only the declared exact
retained root while preserving traversal rejection and all artifact hash checks.
`mission_loop_archive_recover.py` records the specific May-02 archival repair;
it is not a general retry command. No numerical replay was needed for that repair.

The WMI launcher and owned log handles let the campaign survive the Codex
process. Windows/session availability is still required. Do not start another
campaign against the live output directory.

`v41r4_reuse_visibility.py` creates verified physical reporting copies under
`frozen_artifacts/v41r4_may/loop_wall_v4/reused_results/`. Old Actual copies remain
outside optimizer input paths until all four new DA decisions are frozen.
The existing PowerShell monitor retains its compact layout, shows B2 in the
policy table, and refreshes every five seconds without blocking keyboard reads.

## Validation

- Fresh PR checkout: 18 F&O/loop-clock tests passed, including real Gurobi solves,
  preservation of rows/incumbents, late-proposal rejection, and five-stage timing.
- Four selected capacity/power/reference tests passed; ten external-artifact
  capacity tests were not run in this checkout.
- Existing monitor's four A1/MF/MF-complete/Fresh render cases passed.
- Captured production regression verifies exact cached sensitivities and top-20
  ordering; separate A1 structural and coordinator evidence is included.

Run the focused tests from the checkout root with Python, NumPy, pytest,
gurobipy and a working Gurobi license:

```text
python -m pytest -q v41r4_loop_tests.py tests/dayahead/test_v41r1_first_improvement.py
python v41r4_loop_monitor_test.py
```

The old small-model F&O tests now provide an explicit identity ranking fixture:
they have no feeder and test acceptance/locking, while feeder ranking is covered
separately. The production requirement for prepared ranking remains fail-closed.

## Evidence and limits

`evidence/` contains focused test outputs, prior integration audits, and a dated
campaign snapshot. Full datasets, model binaries, logs, and daily archives remain
under the existing local `frozen_artifacts/` and `logs/` trees. Those external
inputs and sealed release files are required to launch/reproduce the campaign;
a clean clone alone is not a portable full experiment package.

Snapshot evidence deliberately preserves its original paths and hashes. Source
bytes are retained through `.gitattributes`; some diff noise is inherited line
ending variation. The running checkout was not edited or committed for this PR.
Negative Actual results remain in the campaign and are not implementation failures.
