# V40A final review

Implementation and the predeclared 2025-04-01 development smoke are complete. Python tests: 54 passed; inherited monitor liveness: 9 assertions passed. Fresh: PASS; post-freeze AC restoration rounds: 0; Actual frozen-decision replay identity gate: PASS.

## Q1. Was the old running May campaign fully stopped?

YES. Final process inventory has zero authoritative May orchestrators and zero active May workers. The monitor is no longer RUNNING.

## Q2. Were all old completed results preserved?

YES. Fifteen completed dates and their thirty result/certificate files retain their pre-stop hashes. The in-place preservation manifest covers 64,845 files / 4,086,616,346 bytes, including incomplete checkpoints and logs.

## Q3. Can the old detached launcher auto-restart the old science?

NO. The old Task Scheduler entry is disabled; its XML and launch configuration are preserved.

## Q4. Is B3 now bidirectionally coupled?

YES. M1 responds to A0; A1 optimizes AIDC against frozen M1 P/Q in the full inherited Planning model; MF adapts electrical control to accepted A1.

## Q5. How many full MESS mobility-route searches occur per B3 day?

1 fleet search stage. Four vehicles, beam parents, K fallbacks and full MILP children remain internal to that one inherited search; they are not four separate co-optimization rounds.

## Q6. Does A1 directly see the grid state created by M1?

YES. Its fixed control vector includes M1 injections in every modeled voltage, line-current, transformer-current and transformer-kVA row.

## Q7. Can A1 change MESS route/destination/departure?

NO. A1 receives a frozen trajectory; both full trajectory identity and route hash are checked.

## Q8. Can MF change route/destination/departure?

NO. MF has no route table, candidate enumeration or beam input. It retains all mobility, transit, ready-time, ETA and travel-energy fields.

## Q9. Does Fresh participate inside the A0→M1→A1→MF loop?

NO. Fresh runs after joint freeze. A Planning file firewall and Fresh-entrypoint guard enforce the separation in the final entrypoint.

## Q10. Are terminal-state invariants preserved?

YES. Per-job profile changes = 0; post-H site changes = 0; positive incremental post-midnight GPU-h = 0.0.

## Q11. Can V40A honestly be described as bounded iterative co-optimization?

YES. Exactly one bidirectional feedback round is predeclared. This describes the coordination architecture, not an optimality or convergence guarantee.

## Q12. Is global joint optimality claimed?

NO. Individual solver status/incumbent/bound data are reported without promoting them to a global joint certificate.

## Q13. What is the measured runtime overhead of the feedback pass?

A1: 24.582385 s; MF: 14.215591 s; combined: 38.797976 s. Paired Planning runtime ratio = 1.017304157. Fresh/restoration are separate.

## Q14. What is the measured J improvement of the feedback pass?

A1 improvement = 0; MF improvement = 0.0096417106409567; old→new improvement = 0.0096417106409567 (1.956603581%).

## Q15. Did the expensive MESS route-search count increase?

NO. OLD = 1, NEW = 1. Both comparisons share the identical measured A0/M1 prefix.

## Q16. Is the full May V40A campaign launched?

NO. The development entrypoint accepts April 1 only. May reuse/evaluation remains a separate later task.

## Scope, provenance and interpretation

The accepted production working overlay, rather than plain Git HEAD alone, is the base. All 1,123 inherited source files and 903 authority files match the pre-stop snapshot. B0/B1/B2 source/authority equivalence is PASS; numerical regression is NOT_RUN and reuse is not approved by this task. Old B3 is superseded for V40A science. V39H/V39J diagnostics and the historical V39K fallback count of 105 remain history.

On this smoke day A1 accepted an unchanged AIDC decision: its measured J contribution is zero. The observed OLD→NEW improvement comes from the MF electrical recourse. The smoke validates bidirectional model wiring, but it does not establish an empirical benefit from changing AIDC decisions.

The April V40A A0 migration count is 0; A1 adds 0. The user explicitly retained the temporal-infeasibility prerequisite, so feasible A0/M1 never authorizes additional RUNNING migration for objective improvement.

The April A0 materializer reuses causal RSP and accepted placement; it fails closed if an uncertified escalation would be needed. The accepted-A0 adapter preserves existing terminal-repair and WAN decisions and validates their PCC reconstruction. No May numeric adapter run or 31-day validation has been performed.

The Actual result is the inherited fixed-decision replay identity gate. It is not a new physical realized-demand/traffic replay. Planning transformer current/kVA loading fields are normalized to inherited ratings, as their saved units explicitly state. Fresh phase arrays retain the inherited physical measurement outputs.

The console-stop helper could not attach (Windows error 5) and sent no signal. Processes were already absent at the subsequent identity recheck; the old log ends in ^C. The exact exit origin is not established. No unrelated process or forced termination was used.

Development debugging evidence is retained separately. An initial serialization failure occurred before M1. The full M1 search was performed once, and its checkpoint was continued only after exact PCC/coefficient/source/settings checks. Integration and reporting changes did not use May objective values or alter K, beam, seed, WorkLimit, eligibility, tolerance or coordination depth. The paired runtime includes the once-measured M1 prefix; continuation wallclock and development attempt totals are recorded separately.

## Measured stages

| Stage | J | Wallclock seconds |
|---|---:|---:|
| A0 | 0.584039297257942 | 2.884409 |
| M1 | 0.492777930863882 | 2210.169239 |
| A1 | 0.492777930863882 | 24.582385 |
| MF | 0.483136220222925 | 14.215591 |

Planning verification: 1.469391 s (overlaps enclosing stage timing). Fresh: 0.685288 s. AC restoration: 0.000000 s. Total represented pipeline: 2285.295937 s.

Route candidate/state evaluations: 1407; Gurobi optimize calls: 6; internal full MILP child solves: 14. Candidate counts and solver invocations have different units.

A1 solver records:

```json
[
  {
    "bound": 0.49277793086382704,
    "global_optimality_certified": true,
    "incumbent": 0.49277793086382704,
    "objective": "rho_max",
    "solver_runtime_seconds": 2.8470001220703125,
    "status": 2,
    "work": 4.6043457077515
  },
  {
    "bound": 0.0,
    "global_optimality_certified": true,
    "incumbent": 0.0,
    "objective": "complete_interval_site_symmetric_GPU_slots",
    "solver_runtime_seconds": 3.3610000610351562,
    "status": 2,
    "work": 5.722147236834835
  },
  {
    "bound": 14080766.0,
    "global_optimality_certified": true,
    "incumbent": 14080766.0,
    "objective": "deterministic_tie",
    "solver_runtime_seconds": 2.6080000400543213,
    "status": 2,
    "work": 4.483721127742276
  }
]
```

MF solver record:

```json
{
  "Gurobi_optimize_calls": 1,
  "bound": 0.48313622022292135,
  "global_optimality_certified": true,
  "incumbent": 0.48313622022292135,
  "solver_runtime_seconds": 4.888000011444092,
  "status_code": 2,
  "work": 7.331360415411398
}
```

## Required final status

```text
OLD_MAY_CAMPAIGN_STOPPED = YES
OLD_MAY_AUTO_RELAUNCH_DISABLED = YES

OLD_COMPLETED_RESULTS_PRESERVED = YES
OLD_B3_CLASSIFICATION =
HISTORICAL_SEQUENTIAL_AIDC_THEN_MESS_RESULT

V40A_IMPLEMENTED = YES

METHOD =
BOUNDED_ITERATIVE_AIDC_MESS_CO_OPTIMIZATION

B3_SEQUENCE =
A0 -> M1_ROUTE_PQ -> A1_FEEDBACK -> MF_FIXED_ROUTE_PQ

BIDIRECTIONAL_AIDC_MESS_COUPLING = YES

MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS = 1
SECOND_MESS_FULL_ROUTE_SEARCH_CALLS = 0

AIDC_FEEDBACK_PASSES = 1
FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS = 1

FRESH_CALLS_INSIDE_COOPT_LOOP = 0

TERMINAL_INVARIANT = PASS
POST_H_RESERVATION_PROFILE_CHANGED_JOBS = 0
POST_H_SITE_STATE_CHANGED_JOBS = 0

J_A0 = 0.584039297257942
J_M1 = 0.492777930863882
J_A1 = 0.492777930863882
J_FINAL = 0.483136220222925

DELTA_J_MESS = 0.0912613663940604
DELTA_J_AIDC_FEEDBACK = 0
DELTA_J_FINAL_PQ = 0.0096417106409567
DELTA_J_TOTAL = 0.100903077035017

RUNTIME_A0_SECONDS = 2.884409
RUNTIME_M1_SECONDS = 2210.169239
RUNTIME_A1_SECONDS = 24.582385
RUNTIME_MF_SECONDS = 14.215591
RUNTIME_TOTAL_SECONDS = 2285.295937

FINAL_JOINT_DECISION_SHA = 33fa59373e71d55b16ffa02c82b12acc19807eb05ea23dfdf5392dc3d0252520

B0_REGRESSION = NOT_RUN
B1_REGRESSION = NOT_RUN
B2_REGRESSION = NOT_RUN

GLOBAL_JOINT_OPTIMALITY_CLAIM = NO
FULL_MAY_V40A_CAMPAIGN_STARTED = NO

SCIENCE_CHANGED = YES
MAY_RESULT_BASED_TUNING = 0

push = NO
PR = NO
```
