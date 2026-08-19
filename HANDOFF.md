# Mobile ESS K9-H7 Engineering Handoff

Snapshot time: **2026-08-18T00:00:46+09:00 (Asia/Seoul)**  
Snapshot type: **live-run handoff; progress and PIDs are volatile**  
Authoritative Linux environment: **WSL distribution `Ubuntu-MobileESS-D`**

This document is intentionally self-contained. A new Codex conversation must assume it cannot access the prior conversation. Facts labelled `CONVERSATION-DERIVED` came from explicit user decisions and are not necessarily reconstructible from Git. Facts labelled `NEEDS_VERIFICATION` must not be treated as accepted.

## 1. Project / Task Overview

### Final goal

Build and scientifically validate the Mobile ESS K9-H7 event-triggered hierarchical controller and its comparison matrix, then execute the frozen representative-period experiment with realistic runtime while preserving causal operation, Fresh Exact AC network safety, reproducibility, and fail-closed evidence.

### Current workstream

The 15-stage controller work is reported complete (`CONVERSATION-DERIVED`). The active workstream is post-Stage15 runtime acceleration and the W02 production gate for four policies:

| ID | Frozen method |
|---|---|
| M1 | Proposed Event30 + Local Repair, mobile ESS |
| M2 | Fixed30, mobile ESS |
| M3 | Event30 without Local Repair, mobile ESS |
| M4 | Fixed-location ESS mobility ablation |

P4 Fixed15 exists only as a supplementary configuration and is not one of the primary M1–M4 W02 comparison methods.

### Experiment workflow

1. Earlier Stage-1 exact optimization and 54/54 acceptance were frozen in commit lineage `358a269` and related artifacts.
2. Stage 7 was superseded to deterministic zero-burn-in canonical PRE initialization; commit lineage `06a94bc`.
3. Representative-period selection fixed 12 independent 2025 representative weeks. Do not revert to 12 calendar-month episodes or a continuous 365-day trajectory.
4. Post-Stage15 performance work prepared one shared exogenous source, four-policy 4-process × 4-Gurobi-thread execution, observability, restart/evidence, and W02 preflight.
5. W02 (`2025-01-13` through `2025-01-19`, 2016 five-minute issues per method) is the current production gate.
6. Only after W02 is scientifically accepted may the remaining representative weeks / first-six launcher be considered.

### Completed stage boundary

- Stage 1: 54/54 completion is in Git history.
- Stage 7: zero-burn-in canonical initialization is in Git history.
- Stage 15: user states it is complete; detailed acceptance should be verified from the existing authority bundles if needed.
- Post-Stage15 preflight/tooling: implemented and previously passed bounded validations.
- W02 production acceptance: **NOT COMPLETE**. The current R3 actual run has three policy failures and therefore supersedes the optimistic preflight confidence.

## 2. Current Status

### Live R3 state at snapshot

Command was launched from `RUN_W02_4POLICY_ACTUAL.sh` with run ID `B_W02_4POLICY_ACTUAL_FINAL_R3`.

```text
W02(01/13~19) | M1 95/2016 4.7% OK | M2 60/2016 3.0% FAIL | M3 60/2016 3.0% FAIL | M4 6/2016 0.3% FAIL
```

Processes observed at the snapshot:

```text
102641 bash RUN_W02_4POLICY_ACTUAL.sh
102699 .../W02_POLICY_EPISODE_RUNNER.py ... M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE
```

M2, M3, and M4 workers had exited. M1 was still running. **Do not assume this is still current; refresh with the monitor command before any action. Do not edit the runner while a worker is active. Do not stop the live process without the user's direction.**

### Completed work

- W02 shared exogenous source can be reused without regenerating heavy mobility/power/price inputs.
- W02 production launcher uses topology-aware 4×4 CPU/Gurobi execution.
- Compact one-line progress monitor exists.
- Source binding, preflight, Fresh OpenDSS observability, duplicate-candidate gate, bounded AC recovery, numerical residual refinement, and result/evidence writers are implemented.
- `--preflight-only` passed immediately before R3 began.
- The release authorization JSON reported `AUTHORIZED_FOR_W02` before R3.
- Targeted regression artifacts R4/R5/R6 and validators reported PASS before R3.
- Git `diff --check` passed before this handoff.

### Partially complete / invalidated by actual evidence

- Targeted regressions are useful forensic evidence but are **not sufficient acceptance evidence**: the clean actual R3 run failed.
- `authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json` remains mechanically `AUTHORIZED_FOR_W02`, but it predates the new R3 actual failures. Treat it as **stale for a new production run until the blocker is fixed and authorization is regenerated**.
- M1 has partial R3 results; its eventual state is `UNKNOWN` at this snapshot.

### Not started / not accepted

- No accepted full W02 four-policy result exists.
- No accepted W02 B→D handoff exists for R3.
- Do not run `RUN_FIRST6_REP_WEEKS_ACTUAL.sh` or the other 11 representative weeks.
- Do not create a PR/commit unless the user explicitly requests it after the fix.

### Highest-priority next work

Resolve the clean-run recovery failure where Fresh Exact AC reports voltage violations, the AC correction does not close the violation, and the same-PRE H54 Full Replan returns an identical decision fingerprint. The duplicate gate correctly avoids a redundant second/third OpenDSS solve, but the method then fails closed.

### Current blocking issue

All three completed failures are `DUPLICATE_RECOVERY_CANDIDATE_NO_SECOND_OPENDSS`:

- M4: issue `3462`, after 6 committed issues.
- M2: issue `3516`, after 60 committed issues.
- M3: issue `3516`, after 60 committed issues.

M4 duplicate decision SHA:

```text
69c428e965097b48f75f2d7ade6107fffa96f0d247f94d6d2d43f02348409c30
```

M2 duplicate decision SHA:

```text
e16b06c4e31f578f5f010501e6035974181a50d2cadc4127e0347be93eea8b39
```

M3 duplicate decision SHA:

```text
d943e99bd01d2ac5d1e6bcb33444055d1689618e425b5251f4a5f78f8b33bc1b
```

The duplicate gate itself behaved as designed:

- same PRE state: true
- hard limits relaxed: false
- future actual used: false
- second OpenDSS call for the duplicate: false

The unverified part is why the AC correction / Full Replan did not generate a distinct safe physical action in the clean R3 execution, despite earlier targeted regression PASS results. This discrepancy is the root engineering task for the next conversation.

## 3. Decisions and Constraints

### Frozen decisions

- Keep AC physics. Fresh Exact OpenDSS is the authoritative physical gate before every committed transition. Do not replace the experiment with sensitivity-only linear OPF.
- Use 12 fixed independent representative weeks, not 12 full calendar months and not a continuous 365-day simulation.
- Use deterministic canonical zero-burn-in PRE state. The former `12 × 576` controller burn-in contract is superseded.
- Prepare/cache common exogenous source once and slice/reuse it. Do not regenerate expensive source data per method/week unless authority drift proves it necessary.
- W02 has 2016 five-minute issues per method (7 days × 288).
- Run M1–M4 concurrently as 4 processes, each with Gurobi `Threads=4`, on the 16 logical CPUs.
- Common initial service sites are frozen and outcome-blind:
  - `MESS01=STA09`
  - `MESS02=IDC12`
  - `MESS03=STA07`
  - `MESS04=STA11`
- M4 is fixed at those same sites; M1–M3 start at the same sites for comparison fairness.
- Preserve no-future-actual and causal state contracts. Never inject future D2 state or future actual jobs.
- Preserve fail-closed behavior, exact scientific limits, and frozen numerical residual gates. Do not loosen tolerances merely to obtain PASS.
- Preserve same-PRE retry semantics and candidate fingerprints.
- The user will run long/full experiments in local Bash. Codex may run only bounded reproductions and validations with reasonable wall time.
- Do not edit the user's Word/PDF methodology document. The user owns document edits.
- Do not create or update a PR until explicitly instructed.

### Current recovery contract in code

- Initial Fresh Exact AC candidate.
- At most one bounded phase-aware finite-difference P/Q AC correction.
- If still unsafe, at most one same-PRE H54 `GRID_HARD_RISK` Full Replan.
- No AC cut after the Full Replan.
- Duplicate electrical/decision candidate gate prevents redundant OpenDSS invocation.
- Constants currently include:
  - `AC_RECOVERY_MAX_CUT_ROUNDS=1`
  - `GRID_HARD_RISK_FULL_REPLAN_MAX=1`
  - `FRESH_AC_PRODUCTION_CANDIDATE_MAX=3`
  - `AC_RECOVERY_FD_STEP_KW=10.0`, with smaller feasible probes in code.

This recovery contract was explicitly chosen after the user approved a bounded multi-opportunity safety recovery. Do not silently revert to “Full-Replan-only” or expand retries without discussing the scientific contract.

### Approaches superseded or forbidden

- Calendar-month Stage7 continuity / 11 month-boundary E7A / old 132-lane E7B.
- Repeating 48-hour/576-step controller burn-in for each representative week.
- Heavy per-week/per-method source regeneration.
- Replacing Fresh Exact AC with linearized OPF as final authority.
- Fixed-root-dual multiway prepass; it consumed time without materially improving bounds.
- Arbitrary tolerance relaxation, pilot splice, fabricated zero derivatives, or unsafe commit.
- Resuming R1 or R2 as production truth.
- Treating a Gurobi-native MIP gap alone as the project’s global scientific certificate.
- The former secondary artificial h0 P/Q-norm full-model QCP. Current code directly commits the accepted primary economic action and retains Fresh OpenDSS as the safety authority.

## 4. Repository / Git State

### Repository identity

```text
repository: BeaverVillage/MobileESS
remote: https://github.com/BeaverVillage/MobileESS.git
WSL path: /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration
branch: agent/post-stage15-runtime-acceleration
HEAD: 8db768c938d62dd61edccc06a1cb8f8faab1b2bc
HEAD subject: Fix W02 launcher authority and source reuse
origin branch: origin/agent/post-stage15-runtime-acceleration at the same committed HEAD
```

PR at snapshot:

```text
PR #5
title: Accelerate and harden post-Stage15 representative-week execution
URL: https://github.com/BeaverVillage/MobileESS/pull/5
state: OPEN, draft=true, mergeStateStatus=CLEAN
base: main
head: agent/post-stage15-runtime-acceleration
GitHub head OID: 8db768c938d62dd61edccc06a1cb8f8faab1b2bc
```

The R3 recovery work is uncommitted and therefore not present in the GitHub PR head.

### Modified tracked files before adding this handoff

```text
M performance/post_stage15_runtime_acceleration/package/RUN_W02_4POLICY_ACTUAL.sh
M performance/post_stage15_runtime_acceleration/package/SHA256SUMS.txt
M performance/post_stage15_runtime_acceleration/package/STATIC_VALIDATION.json
M performance/post_stage15_runtime_acceleration/package/authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json
M performance/post_stage15_runtime_acceleration/package/runtime/W02_POLICY_EPISODE_RUNNER.py
M performance/post_stage15_runtime_acceleration/package/tools/BUILD_PRE_W02_FINAL_RELEASE_AUTHORIZATION.py
M performance/post_stage15_runtime_acceleration/package/tools/PREFLIGHT_W02_4POLICY.py
M performance/post_stage15_runtime_acceleration/package/tools/SHOW_W02_PROGRESS.py
```

### Untracked implementation files before adding this handoff

```text
?? performance/post_stage15_runtime_acceleration/package/authority/POST_STAGE15_PRIMARY_ACTION_DIRECT_COMMIT_SUPERSESSION.json
?? performance/post_stage15_runtime_acceleration/package/authority/POST_STAGE15_W02_ACTUAL_FAILURE_CORRECTION.json
?? performance/post_stage15_runtime_acceleration/package/authority/POST_STAGE15_W02_SAFETY_RECOVERY_REFREEZE.json
?? performance/post_stage15_runtime_acceleration/package/authority/POST_STAGE15_W02_SENSITIVITY_KEYERROR_CORRECTION.json
?? performance/post_stage15_runtime_acceleration/package/tools/BIND_W02_RUN_SOURCE.py
?? performance/post_stage15_runtime_acceleration/package/tools/VALIDATE_W02_SAFETY_RECOVERY_CONTRACT.py
?? performance/post_stage15_runtime_acceleration/package/tools/VALIDATE_W02_SENSITIVITY_KEYERROR_CORRECTION.py
```

After this package is installed, `HANDOFF.md`, `HANDOFF_STATE.json`, and `HANDOFF_GIT_STATUS.txt` will also be untracked at repository root.

### Preservation rule

All modified/untracked files above are intentional ongoing work or generated evidence. **Do not reset, checkout, overwrite, clean, or delete them.** Never use `git reset --hard`, `git checkout --`, or `git clean`. Inspect diffs and patch narrowly.

## 5. Important Files and Artifacts

### Primary package

Base directory:

```text
/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package
```

| Path | Role |
|---|---|
| `00_READ_FIRST.md` | Short package intent and frozen four-policy topology. Some statements predate the R3 failures; do not treat its ETA/authorization as final acceptance. |
| `RUN_W02_4POLICY_ACTUAL.sh` | Primary W02 launcher; current run ID is R3. |
| `runtime/W02_POLICY_EPISODE_RUNNER.py` | Main per-policy rolling runner and active recovery implementation. Current SHA-256: `d14dd492c2e4f7e4a29861e77c0ef95be3ed389c9fa11d413fd559c0afcafd47`. |
| `runtime/production_adapter.py` | Adapter into the frozen scientific engine. |
| `runtime/MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2.py` | Stage 2/3 runtime helper used by the production runner. |
| `configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json` | M1 configuration. |
| `configs/P2_FIXED30.json` | M2 configuration. |
| `configs/P3_EVENT30_NO_LOCAL_REPAIR.json` | M3 configuration. |
| `configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json` | M4 configuration. |
| `configs/P4_FIXED15.json` | Supplementary only. |
| `scripts/PREPARE_W02_SHARED_SOURCES.sh` | Reuse/build one W02 exogenous authority. |
| `tools/PREFLIGHT_W02_4POLICY.py` | Static/source/license/config preflight. |
| `tools/BIND_W02_RUN_SOURCE.py` | Immutable run-source identity binder. |
| `tools/CPU_AFFINITY_4X4.py` | Generates four CPU affinity groups. |
| `tools/SHOW_W02_PROGRESS.py` | Package progress monitor. |
| `/home/jaewon/mobile_ess_work/SHOW_W02_PROGRESS_COMPACT.py` | User-facing one-line progress monitor. |
| `tools/VALIDATE_W02_SAFETY_RECOVERY_CONTRACT.py` | Static/dynamic recovery contract validator. |
| `tools/VALIDATE_W02_SENSITIVITY_KEYERROR_CORRECTION.py` | Targeted prior failure validator; current PASS is insufficient after R3. |
| `tools/BUILD_PRE_W02_FINAL_RELEASE_AUTHORIZATION.py` | Builds release authorization after evidence gates. Must be rerun only after a genuine new fix. |
| `authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json` | Pre-R3 release token. Now stale relative to actual R3 failures. |
| `SHA256SUMS.txt` | Package file checksum inventory; regenerate after intentional source/evidence changes. |

### Scientific engine and period authority

| Path | Role |
|---|---|
| `/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/science/main.py` | Frozen scientific engine. Do not casually modify; package preflight binds its SHA. |
| `period_selection/output/REP_WEEK_SELECTION_2025_K12.csv` | Frozen 12 representative-week selection (path is from prior authority/PR3 context; verify exact location in this worktree before use). |
| `episode_bindings/*.json` | 12 weeks × 4 methods execution bindings. |

### Shared data authority

```text
/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT
```

It passed shared-source preflight and should be reused. Do not regenerate it merely because a controller recovery failed.

### Current and forensic run roots

```text
R1: /home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R1
R2: /home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R2
R3: /home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R3
R3 logs: /home/jaewon/mobile_ess_work/logs/B_W02_4POLICY_ACTUAL_FINAL_R3
```

- R1 and R2 are forensic only; do not resume or promote them.
- R3 is the current failed/partial actual run. Preserve it exactly for diagnosis.
- Do not overwrite R3 with another run ID or delete its `interrupted_attempts`, issue directories, failure JSON, fingerprints, or logs.

### R3 blocker evidence

M4:

```text
.../R3/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION/FAILURE.json
.../R3/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION/engine/issue_003462/A_B10_DUPLICATE_RECOVERY_CANDIDATE_GATE.json
.../logs/R3/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.log
```

M2:

```text
.../R3/M2_FIXED30_MOBILE/FAILURE.json
.../R3/M2_FIXED30_MOBILE/engine/issue_003516/A_B10_DUPLICATE_RECOVERY_CANDIDATE_GATE.json
.../R3/M2_FIXED30_MOBILE/interrupted_attempts/20260817T145420Z/issue_003516_grid_hard_pre_replan/issue_003516/exact_grid/
```

M3:

```text
.../R3/M3_EVENT30_NO_LOCAL_REPAIR_MOBILE/FAILURE.json
.../R3/M3_EVENT30_NO_LOCAL_REPAIR_MOBILE/engine/issue_003516/A_B10_DUPLICATE_RECOVERY_CANDIDATE_GATE.json
.../R3/M3_EVENT30_NO_LOCAL_REPAIR_MOBILE/interrupted_attempts/20260817T145803Z/issue_003516_grid_hard_pre_replan/issue_003516/exact_grid/
```

### Earlier regression evidence

```text
/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_INCOMPLETE_SENSITIVITY_LOCK_REGRESSION_R4_20260817
/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_FRESH_R2_M4_RECOVERY_REGRESSION_R5_20260817
/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_R3_THREE_FAILURE_REGRESSION_R6_20260817
/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_SAFETY_RECOVERY_CONTRACT_CURRENT.json
/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_SENSITIVITY_KEYERROR_CORRECTION_CURRENT.json
```

These are not obsolete as forensic evidence, but they must not be cited as proof that clean R3 passes. In particular, R5 contains `interrupted_attempts` / resume lineage and did not predict the clean R3 failure reliably.

## 6. Implementation Details

### High-level data flow

```text
canonical PRE + frozen config + shared exogenous window
    -> event-trigger decision (NONE / LOCAL_REPAIR / FULL_REPLAN)
    -> slow planner only when triggered
    -> conditioned fast physical dispatch (3% operational Gurobi gap gate)
    -> numerical residual check/refinement when needed
    -> Fresh Exact OpenDSS
       -> PASS: commit h0 transition and evidence
       -> voltage FAIL: one P/Q sensitivity correction
          -> PASS: commit
          -> FAIL: restore same PRE, set GRID_HARD_RISK, one H54 Full Replan
             -> distinct candidate: Fresh Exact OpenDSS
             -> duplicate candidate: no redundant OpenDSS; FAIL_CLOSED
    -> checkpoint/progress/observability/result artifacts
```

### Important runner components

- `SourceBlocks`: cached shared exogenous source access.
- `PerformanceBook`: per-phase runtime accounting.
- `solve_fast(...)`:
  - `Threads=4`
  - `MIPGap=0.03`
  - infinite production time limit
  - residual gates `ConstrVio<=1e-6`, `BoundVio<=1e-6`, `IntVio<=1e-5`
  - conditional same-objective numerical refinement with `NumericFocus=3`, `FeasibilityTol=1e-9`, `OptimalityTol=1e-9`, `BarQCPConvTol=1e-10`, `ScaleFlag=2`
  - direct primary economic action commit; no secondary artificial P/Q-norm selector
- `exact_ac_cut_recovery(...)`: one bounded P/Q correction before (never after) Full Replan.
- `_recovery_candidate_fingerprints(...)` and `_record_recovery_candidate(...)`: preserve electrical/decision identity.
- `planner_solve(...)`: slow planner, currently `MIPGap=0.10`, `TimeLimit=300`, `Threads=4`.
- `planner_feasibility_rescue(...)`: bounded hard-event feasibility rescue.
- `prebuild_event_conditioning(...)` / inner `hook(...)`: event mode, local/full planning, dispatch, duplicate gate.
- `reset_failed_attempt_for_same_pre(...)`: restores controller boundary for technical retry.
- `execute_one_issue(...)`: binds causal source and invokes one scientific issue.
- `build_results(...)`: materializes comparison/observability result tables after successful episode.

### Inputs / outputs

Runner inputs:

```text
--repo      frozen scientific worktree
--config    one method JSON
--output    method-specific delivery root
--candidate-id (default W02_2025-01-13)
--shared-root (optional override; production normally uses frozen shared root)
--benchmark-issues N (bounded tests only; 0 means full episode)
```

Production flags beginning with `--benchmark-*` are test-only and must not silently enter scientific results.

Key environment:

```text
PYTHONHASHSEED=0
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
GUROBI_NUM_THREADS=4
```

The launcher uses `taskset` CPU groups from `CPU_AFFINITY_4X4.py`.

Per-policy outputs include:

- `progress/W02_PROGRESS.json`
- `control/POLICY_RUNTIME_CHECKPOINT.json`
- `engine/BUILD7C_ROLLING54_ISSUE_SUMMARY.csv`
- `engine/issue_XXXXXX/BUILD7C_PRECOMMIT_STATE.json`
- `engine/issue_XXXXXX/BUILD7C_POSTCOMMIT_STATE.json`
- `engine/issue_XXXXXX/BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json`
- `engine/issue_XXXXXX/exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_XXXX.json`
- Fresh AC observability, candidate identity, recovery, and duplicate-gate JSON
- `FAILURE.json` and `engine/_FAILURE.json` on fail-closed

## 7. Execution / Reproduction

### Environment

```text
WSL distro: Ubuntu-MobileESS-D
Python: /home/jaewon/miniconda3/envs/power_v61/bin/python
Gurobi: 13.0.2, academic license present at last preflight
CPU: 16 logical processors
```

No install/build step was needed at the last successful preflight. Do not update dependencies during a live/forensic reproduction.

### First command in a new conversation: read-only live status

```bash
wsl -d Ubuntu-MobileESS-D -- bash -lc '
  date --iso-8601=seconds
  /usr/bin/python3 -u /home/jaewon/mobile_ess_work/SHOW_W02_PROGRESS_COMPACT.py
  pgrep -af "[W]02_POLICY_EPISODE_RUNNER.py|[R]UN_W02_4POLICY_ACTUAL" || true
'
```

Do not run another launcher while the current launcher/worker exists.

### Working directory

```bash
cd /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package
```

### Read-only progress monitor

```bash
watch -t -n 30 /usr/bin/python3 -u /home/jaewon/mobile_ess_work/SHOW_W02_PROGRESS_COMPACT.py
```

### Preflight-only

Run only after no production worker is using code that will be modified:

```bash
bash RUN_W02_4POLICY_ACTUAL.sh --preflight-only
```

### Full W02 launcher

```bash
bash RUN_W02_4POLICY_ACTUAL.sh
```

**Do not execute this now. R3 already exists and is failed/partial. A corrected launcher must use a new run ID (for example R4) only after validated correction and regenerated authority. Never overwrite R3.**

### Static and evidence validation commands

```bash
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  tools/PREFLIGHT_W02_4POLICY.py \
  --repo /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration \
  --require-shared-source

/home/jaewon/miniconda3/envs/power_v61/bin/python \
  tools/VALIDATE_W02_SAFETY_RECOVERY_CONTRACT.py

/home/jaewon/miniconda3/envs/power_v61/bin/python \
  tools/VALIDATE_W02_SENSITIVITY_KEYERROR_CORRECTION.py

cd /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration
git diff --check
```

The validators' exact CLI defaults/output paths should be checked with `--help` or source before rerunning. They passed before R3 but must be extended/regenerated to include the clean-run failures.

### Checksums

After an intentional fix and regenerated authority, from the package root:

```bash
find . -type f ! -name SHA256SUMS.txt ! -path '*/__pycache__/*' -print0 \
  | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
```

Do not regenerate checksums while an active worker may be using a changing source tree.

## 8. Validation Status

### PASS before R3

- Package checksum verification: PASS before R3.
- `RUN_W02_4POLICY_ACTUAL.sh --preflight-only`: PASS.
- Shared W02 exogenous authority: `PASS_REUSED`.
- Gurobi license and runtime dependencies: PASS.
- Source binding smoke: `PASS_NEW_SOURCE_BINDING`.
- Safety recovery validator: PASS.
- Sensitivity/KeyError validator: 11 checks PASS.
- Targeted R4/R5/R6 regressions: reported PASS.
- `git diff --check`: PASS.

### Actual R3 FAIL

- M4 issue3462: `DUPLICATE_RECOVERY_CANDIDATE_NO_SECOND_OPENDSS`.
- M2 issue3516: same failure class.
- M3 issue3516: same failure class.
- M1: still active at the snapshot; final state unknown.

### Why prior PASS is insufficient

The targeted regression evidence did not reproduce/predict the clean R3 run behavior. At least R5 includes resume/interrupted-attempt lineage. The next validation must start from the same canonical clean PRE/source/config semantics as production and exercise the failing issue history, not splice directly into a later issue with a mismatched state.

### Acceptance criteria for the next correction

1. No production worker active while patching.
2. Preserve exact Fresh OpenDSS limits, no-future-actual, same-PRE, and fail-closed contracts.
3. Reproduce at least M4 issue3462 and M2/M3 issue3516 from scientifically identical causal history.
4. Demonstrate that the correction produces a distinct safe candidate or a scientifically justified deterministic safe fallback; do not merely bypass the duplicate gate.
5. Fresh Exact OpenDSS must pass before commit.
6. No duplicate candidate gets another redundant OpenDSS call.
7. No residual/tolerance gates are relaxed.
8. New bounded clean-start regression passes for M1–M4 and captures candidate SHA and source/state lineage.
9. Regenerate validators, release authorization, source hashes, and use a new run ID.
10. Only the user starts the full run.

## 9. Known Issues / Risks

- **Primary bug/blocker:** Full Replan can return exactly the same failed decision candidate after AC correction exhaustion. Current code correctly blocks a redundant OpenDSS call but has no accepted way to produce a safe distinct action.
- **Regression representativeness debt:** Prior R5/R6 PASS evidence was not production-clean-start equivalent enough to catch R3 failures.
- **Stale authorization risk:** `PRE_W02_FINAL_RELEASE_AUTHORIZATION.json` says authorized although actual R3 evidence now fails. Do not trust status alone.
- **Live-run mutation risk:** M1 may still be running. Editing runner/science/config or regenerating authority while active can corrupt provenance.
- **Dirty-tree risk:** Important uncommitted changes exist. Do not reset or overwrite.
- **Artifact collision risk:** Reusing R3 output paths can archive/mix stale failures and destroy a clean forensic boundary. Use a new run ID only after a fix.
- **Apparent monitor semantics:** One completed issue is one five-minute interval, not one day. Each policy needs 2016 issues.
- **Scientific vs engineering retry:** Adding more retries can change methodology and runtime. Any change beyond the frozen bounded recovery requires explicit authority update, not an ad hoc loop.
- **Numerical nondeterminism/concurrency:** Isolated regressions may differ from 4×4 contention. The next bounded test should include both isolated deterministic reproduction and a short 4×4 clean-start check.
- **Exact maximum/minimum voltage fields:** Some Fresh OpenDSS summary JSON uses detailed `bus_phase_voltage` rows rather than top-level max/min fields. Do not infer missing top-level values as missing physical data.
- **UNKNOWN:** Whether M1 later completed or failed after the snapshot. Refresh first.

## 10. Exact Next Actions

### Priority 0 — protect the live run

1. Run the read-only status command.
2. If M1/launcher is still active, do not modify code. Ask the user whether to let M1 finish or interrupt it. Do not assume permission to kill it.
3. Preserve R3 artifacts/logs and record the final M1 state.

Completion condition: no uncertainty about active workers and no code mutation during a live worker.

### Priority 1 — freeze the new failure evidence

1. Snapshot R3 M2/M3/M4 `FAILURE.json`, `engine/_FAILURE.json`, duplicate gates, interrupted attempts, Fresh AC observability, precommit state, config/source identity, and logs.
2. Add these exact paths and SHA-256 values to a new failure authority file; do not edit/delete older authorities.
3. Compare clean R3 state/source fingerprints with R5/R6 regression fingerprints to explain why the prior regression passed.

Likely files to add/update only after M1 is inactive:

- new authority JSON under `package/authority/`
- `tools/VALIDATE_W02_SENSITIVITY_KEYERROR_CORRECTION.py` or a new clean-run validator
- no document edits

Completion condition: deterministic explanation of the R3-versus-regression discrepancy with source/PRE/controller hashes.

### Priority 2 — correct the recovery design narrowly

Inspect and patch only the relevant paths in:

```text
package/runtime/W02_POLICY_EPISODE_RUNNER.py
```

Focus on:

- `exact_ac_cut_recovery(...)`
- `reset_failed_attempt_for_same_pre(...)`
- the `GRID_HARD_RISK` branch in `hook(...)`
- `_recovery_candidate_fingerprints(...)`
- the duplicate-candidate gate

Do not bypass the duplicate gate and do not call OpenDSS again for an identical electrical candidate. The fix must cause the planner/dispatch to produce a scientifically distinct controllable action or define an explicitly approved safe fallback. Preserve exact constraints and causal semantics.

Completion condition: bounded causal reproductions of M4 issue3462 and M2/M3 issue3516 pass Fresh Exact OpenDSS with no unsafe commit and no contract relaxation.

### Priority 3 — rebuild validation and authorization

1. Add a clean-start bounded regression covering sufficient history to reach the failure issues.
2. Run isolated tests, then a short 4×4 contention-equivalent test.
3. Run validators and `git diff --check`.
4. Regenerate source hashes and `PRE_W02_FINAL_RELEASE_AUTHORIZATION.json` only after all new gates pass.
5. Change launcher to a new run ID such as R4; never reuse R3.

Completion condition: preflight PASS, new actual-failure regression PASS, authorization bound to the new runner SHA, and clean R4 roots absent before user execution.

### Priority 4 — hand execution back to user

Provide the exact Bash run and one-line monitor commands. Do not launch the full W02 from Codex. Do not run first six weeks until W02 four-policy acceptance passes.

## 11. Conversation-Derived Context

The following items are essential and cannot be recovered reliably from the repository alone:

- The user considers the 15-stage work complete and is now focused on runtime acceleration plus representative-week production execution.
- The user chose representative weeks rather than full months/annual continuous simulation because runtime must be realistic.
- The user accepted zero burn-in canonical cold start, superseding the 48-hour controller burn-in validation workload.
- The user explicitly retained AC physics/Fresh OpenDSS rather than switching the final model to a sensitivity-linearized OPF.
- The user wants more realistic/accurate changes considered even if numerical outcomes change; outcome equality alone is not a rejection criterion. Scientific contracts and fairness still require explicit re-freeze.
- The user prioritizes both reducing computation amount and accelerating remaining computation.
- Long/full runs are executed by the user in Bash. Codex must use bounded tests and avoid long unattended runs.
- The user wants compact horizontal progress only: week/date, completed/required issues, percent, and FAIL/OK. No worker IDs in the normal monitor.
- One issue equals one five-minute simulation interval. `2016` issues equal one seven-day policy episode.
- The user asked that FAILs be genuinely fixed, not hidden, but in this handoff turn explicitly instructed this conversation **not** to fix the new FAIL; the new conversation owns it.
- The user owns and will modify the Word/PDF formal specification. Codex must not edit the document.
- PR work must happen only when the user explicitly directs it. PR #5 exists but current changes are uncommitted.
- R1/R2 are forensic and must not be resumed. R3 is now also failed/partial forensic evidence unless a future authority explicitly permits a safe resume; default is preserve and use a new run ID.

## 12. Handoff Prompt for the New Conversation

Copy the following as the first message in the new Codex conversation:

```text
You are taking over BeaverVillage/MobileESS K9-H7 post-Stage15 runtime/W02 production work in WSL `Ubuntu-MobileESS-D`.

First read these files completely:
1. `/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/HANDOFF.md`
2. `/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/HANDOFF_STATE.json`
3. `/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/HANDOFF_GIT_STATUS.txt`
4. `performance/post_stage15_runtime_acceleration/package/00_READ_FIRST.md`
5. `performance/post_stage15_runtime_acceleration/package/runtime/W02_POLICY_EPISODE_RUNNER.py`
6. the R3 M2/M3/M4 failure and duplicate-candidate artifacts listed in HANDOFF.md.

Project goal: complete the scientifically frozen four-policy W02 representative-week gate with realistic runtime, causal/no-future execution, exact constraints, and Fresh Exact OpenDSS before every commit, then proceed to the remaining fixed representative weeks only after W02 acceptance.

Current repository: `/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration`, branch `agent/post-stage15-runtime-acceleration`, committed HEAD `8db768c938d62dd61edccc06a1cb8f8faab1b2bc`, PR #5 draft/open. The working tree contains important uncommitted modified and untracked recovery files. Preserve all of them; do not reset/checkout/clean or overwrite user work.

Current actual R3 run is failed/partial. At the 2026-08-18T00:00:46+09:00 snapshot: M1 95/2016 and still running, M2 60/2016 FAIL, M3 60/2016 FAIL, M4 6/2016 FAIL. All three failures are `DUPLICATE_RECOVERY_CANDIDATE_NO_SECOND_OPENDSS` after a true Fresh AC voltage failure and an identical same-PRE Full-Replan candidate. The duplicate gate correctly avoided redundant OpenDSS; do not bypass it. The previous R4/R5/R6 targeted regressions and release authorization are no longer sufficient because clean R3 contradicted them.

Before doing anything, run the read-only monitor and process check from HANDOFF.md. If any runner is active, do not edit source or stop it without user direction. Preserve R1/R2/R3 artifacts and logs.

Your first engineering task after the live process is settled is to freeze the clean R3 failure evidence and explain why prior targeted regressions passed. Then reproduce M4 issue3462 and M2/M3 issue3516 with scientifically identical causal history. Patch the recovery narrowly so it creates a distinct safe candidate or an explicitly approved deterministic safe fallback; never relax tolerances, use future actuals, commit before Fresh OpenDSS, call OpenDSS again for an identical candidate, or fabricate sensitivities. AC physics remains authoritative.

Maintain: 12 fixed independent representative weeks, zero-burn-in canonical PRE, one shared exogenous source, four methods M1–M4, 4 processes × 4 Gurobi threads, common initial sites MESS01=STA09/MESS02=IDC12/MESS03=STA07/MESS04=STA11, one issue=5 minutes, 2016 issues/policy/week. Do not revert to calendar-month/365-day execution, 12×576 burn-in, or per-method source regeneration.

Use bounded tests only. Do not launch full W02 or first-six weeks; the user runs long Bash jobs. After a genuine fix, run clean-start causal regressions, a short 4×4 check, validators, `git diff --check`, regenerate authority/checksums, and allocate a new run ID (not R3). Provide the user run/monitor commands. Do not edit the Word/PDF specification. Do not create a commit or PR unless the user explicitly asks. Do not rerun already completed source generation or old validations unless the new fix actually invalidates them.
```

