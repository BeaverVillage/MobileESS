# May 2025 B1 launch preflight — NOT LAUNCHED

Base: PR148 exact head `c6c2f733d8196e90c0cda5f849f3e894c872697f`.
Branch: `codex/v42-may-b1-production-31d`.

The requested detached production launch did not pass scientific integration
preflight. No scheduled task or monitor was launched. This receipt is not a B1
run, resource wait, complete production adapter, or scientific failure of B1.
No optimizer, B0 rerun, B1/B2/B3, M1/M2, or Branch-and-Price was executed.

## Verified authority

The authoritative B0 run `B0_202505_20261004T203131_71a9bf18` has 31/31 PASS,
155/155 PASS stages, and scientific/campaign completion flags. The read-only
preflight verifies all 155 receipt hashes and 1,519 referenced output hashes.
Four existing independent completed-campaign audits also pass. B0 outputs are
barrier evidence only; no B0 outputs have been relabeled as B1.

The frozen May authority has exactly 31 unique sorted dates, May 1–31, 2025.
The existing B1 contract is **one complete day at a time**:
`A1 -> PLANNING_FREEZE -> ACTUAL -> FRESH_AC -> VALIDATION_FREEZE`.
Each day's Actual requires that day's Planning Freeze, not all 31 freezes.
All 31 B0 Validation receipts are the preceding arm barrier. This is the
original `v42_campaign.plan` / PR146 DAG contract; the B0-specific month-wide
Planning barrier must not silently be applied to B1.

B1 semantics remain AIDC present, AIDC grid flexibility on, MESS off, ML not
off. Required execution policy remains one day worker and Gurobi Threads=1.

## Missing integration

1. `v42_single_thread/a1.py:37` asserts 1,499 jobs and May 1. Its input path is
   `MAY01_FINAL_NATIVE_INPUT_BUNDLE.json`, and its model census is compared with
   the May 1 reference. Native per-day Runtime/CC4, TS boundary, WAN, and grid
   producers have not been routed and certified for the 31-day B1 campaign.
   The 31 shared May input bundles exist and pass their input gates; that does
   not certify the missing B1 native input transformation.
2. Existing accepted A1 freeze is `selected_jobs` plus electrical `anchor`.
   It fails the current `v42_native.planning.validate_plan` API: all twelve
   required FrozenDayAheadPlan fields are absent. There is no demonstrated
   production serializer binding that A1 result to the frozen causal
   unknown-arrival policy, realized service replay, and physical job identity.
3. Current `v42_native.actual.ActualBackend.reconstruct_physical` is a Protocol
   declaration. AST inspection of current `v42_*` source finds no concrete
   implementation; implementations in `tests/test_v42_dayahead_actual.py` are
   explicitly fake architecture adapters, never production evidence.
4. PR148's B0 Actual is a fixed source-site FCFS producer. It does not execute
   optimized A1 time shifts or migrations. Reusing it would silently change
   B1 into the B0 replay policy.
5. The historical V41R3 native-control wrapper initializes from Planning
   `regulator_taps[0]`. Direct reuse violates this request's no Planning tap
   replay condition. Historical frozen-policy job replay exists in
   `dayahead/v41/actual.py`, but its direct connection to current V42 job,
   queue, policy, and physical-control authority is unverified.

These are implementation/authority gaps, not a resource shortage. Publishing
an idle task as `WAIT_RESOURCE` would conceal them and would not automatically
run a scientifically valid B1 pipeline when Lane A finishes.

## Historical infrastructure located

Actual historical files, hashes, and relevant current scientific source lines
are recorded in `B1_LAUNCH_PREFLIGHT.json`:

- `C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/tools/v37/run_may_locked_final.ps1`
- Same worktree: `tools/v37/monitor_may.ps1` (atomic JSON reads, active-only view,
  completed PASS omitted, FAIL retained, `-Once` mode; legacy monitor also writes
  its own lock, which a strictly read-only adaptation would remove).
- `C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v39l/infrastructure.py`
  contains the proven `schtasks /Create /SC ONCE` registration plus battery,
  unlimited execution time, and IgnoreNew instance settings.

Git history confirms the actual V37 launcher/monitor in commit
`71a581460e32abbcda69d54da8e8d73ab7f03b5b`; the launcher explicitly selects
`monitor_may.ps1` and launches a separate visible PowerShell process with
`Start-Process -WindowStyle Normal`. Historical code was inspected, not guessed
or imported into the B1 scientific branch.

## Checks and limits

Run the preflight from this worktree:

```powershell
python tools/v42/preflight_b1_may.py
```

It writes atomic audit JSON and returns a nonzero code for missing integration.
It does not start a task or run native science.

Fourteen B1 gate tests and four completed-B0 audit tests pass. They check
prohibited arm/worker/thread/MESS/ML settings, incomplete/tampered B0 authority,
bad date axes, mock production rejection, and rejection of a historical A1
freeze as a complete Actual policy.

Detached launch, survival, Task Scheduler command identity, adapted monitor
atomic reads/liveness, WAIT_RESOURCE/resume, and restart behavior have **not**
been implemented or passed for B1. Their absence is reported; these gate tests
must not be represented as the requested full prelaunch suite.

Complete the source-backed B1 integration above, validate the unchanged native
equations and causal policy on the 31-day input authority, then adapt the
located historical monitor and scheduler, test detachment, commit the reviewed
adapter, freeze a new run ID/SHA, and launch. No B2/B3 auto-advance is permitted.
# Superseded initial scope audit

The initial PR148-only integration blocker was resolved by the explicit historical V39E → V37 → V36 port. See [current production implementation](../v42_may_b1_production_31d/README.md) and the updated `B1_LAUNCH_PREFLIGHT.json`. The retained initial validation/description files describe the earlier investigation, not current launch readiness.
