# CODEX TASK — Consolidate G8T→G12E Work into PR #5 as a Pre-Feedback Checkpoint

You are the repository/PR integration owner for `BeaverVillage/MobileESS`.

Your job is to **inspect, cleanly integrate, test, commit, push, and update the existing draft PR #5 with all meaningful work completed after the existing PR #5 checkpoint through G12E**, while explicitly freezing this as a **pre-professor-feedback legacy checkpoint**.

Do **not** start the new scientific redesign in this task.

---

## 0. Non-negotiable safety rules

1. Do not force-push.
2. Do not rewrite existing published commit history.
3. Do not merge PR #5.
4. Keep PR #5 in draft state.
5. Do not delete or overwrite frozen runtime evidence.
6. Do not commit external datasets or large generated outputs.
7. Do not silently “fix” unfavorable scientific outcomes.
8. Do not claim full W02 / 12-week completion.
9. Do not introduce a separate `z_route` binary layer; it was rejected as redundant.
10. Do not treat package-local `sitecustomize.py` monkeypatches as production architecture.
11. Do not continue G12F-style repair of old M3/M4 just to make the legacy 4-method full-day run pass. The next scientific design will supersede that comparison.
12. Preserve all causality/Fresh-AC/no-future-actual invariants already present in PR #5.

---

## 1. Repository reconnaissance — do this before changing anything

Start from `/home/jaewon/mobile_ess_work` and locate the actual Git worktree containing PR #5 lineage. The likely repository root is `/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration`, but verify by finding `.git` rather than assuming.

Record:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
git log --oneline --decorate -30
```

Then fetch without modifying local work:

```bash
git fetch origin --prune
```

Compare local HEAD and working tree with:

```text
origin/agent/post-stage15-runtime-acceleration
remote PR #5 snapshot head expected at handoff time:
e73d1509d2f9bed230b3fc34c0f603eaea925c10
```

If remote has moved, use the **actual fetched remote head** as authority and document the drift. Do not reset local work.

Also inspect open PR #5 if `gh` is available:

```bash
gh pr view 5 --repo BeaverVillage/MobileESS --json number,title,state,isDraft,headRefName,headRefOid,baseRefName,url,body
```

---

## 2. Determine what is already in PR #5 versus what only exists in local task packages

PR #5 already contains substantial post-Stage15 runtime, zero-burn-in, M1–M4, observability, atomic commit, safety-recovery and materializer infrastructure. Do not duplicate those files.

Inspect the local task/evidence lineage G8T→G12E and map every meaningful delta to one of:

- `ALREADY_IN_PR5`
- `PORT_CLEANLY_TO_PR5`
- `EVIDENCE_ONLY_COMPACT_SUMMARY`
- `DO_NOT_COMMIT_PACKAGE_HACK`
- `SUPERSEDED_BY_POST_FEEDBACK_REBASE`

Create a machine-readable audit file in the repository, e.g.:

```text
performance/post_stage15_runtime_acceleration/PRE_REBASE_CHECKPOINT/G8T_G12E_PORT_AUDIT.json
```

Do not copy entire task directories.

---

## 3. Scientific/engineering facts that must be preserved

Use `CURRENT_WORK_G8T_G12E.md` and `.json` in this handoff as the status authority for this checkpoint.

### Native mobility formulation

- Production has native K=3 candidate-route architecture.
- Node occupancy binary count = 4,596.
- Move arcs are continuous: 100,704.
- `MOVE_arc_binary_count = 0` is valid and must not be treated as missing/false.
- Separate `z_route` binary layer is `REJECTED_AS_REDUNDANT`.
- Internal `E_MESS` unit is MWh; 0.44 model units = 440 kWh protected floor.

If there is no clean existing repo artifact that captures this, add a compact audit/contract under `PRE_REBASE_CHECKPOINT/`; do not change the scientific route formulation merely to create evidence.

### M3 ablation development evidence

- Decision-use constraint anchors were found.
- One-issue M3 ablation removed 256 linear constraints:
  - `support_debt_terminal`: 4
  - `r24_debt_suffix`: 36
  - `r25g_debt_stay_cover`: 36
  - `r25k_debt_stay_cover_dense`: 180
- Event Trigger, mobility, observability, Fresh AC were preserved in that bounded evidence.
- The later G12E failure shows the package-local ablation hook is fragile when an issue exposes zero removable constraints.

Do **not** promote the `sitecustomize.py` monkeypatch into production. Store only compact evidence and, if already cleanly implemented in source, keep the implementation; otherwise classify it as legacy bounded ablation evidence.

### Materializer/observability correction

This is the main clean reusable change that should be integrated if not already present:

`A_B10_FULL_PLANNER_SOLVE.json` is **optional for a committed continuation / fast-dispatch step** where no full planner solve occurred.

The materializer must:

- still materialize one solver/runtime row for every committed issue;
- distinguish `solve present` from `optional missing because no full planner solve occurred`;
- not treat numeric zero as missing;
- preserve `NULL != 0 != NA != OBSERVED_ZERO` semantics;
- fail closed on genuinely required missing sources.

G12C evidence: 96/96 issues materialized PASS across M1–M4; 80 optional-solve-missing continuation cases accepted, 16 solve-present cases.

Port this as a clean repository-level implementation and test if the PR #5 current materializer does not already contain equivalent logic.

### G12E full-day checkpoint

Do not hide or repair the outcome in this PR.

- M1: 288/288 commits, 288/288 materializer PASS.
- M2: 288/288 commits, 288/288 materializer PASS.
- M3: 37/288 commits then fail at issue 3493.
- M4: 37/288 commits then fail at issue 3493.
- M3 failure: `G10F/G9C found zero explicit debt/rebound decision-use constraints to remove`.
- M4 failure: `R62_FIXED77_DEFERRED_FREE_FEASIBILITY_FAILED:SKIP_NOT_M4_ISSUE5299_FIXED_LOCATION`.
- `future_actual_jobs_used_for_optimizer=false`.
- `future_D2_state_reinjected=false`.
- Full 12-week campaign not started.

Store a compact checkpoint summary, not raw issue outputs.

---

## 4. Files/code that SHOULD be ported if missing from PR #5

After inspecting current PR #5, cleanly integrate only missing reusable pieces.

Priority A — production-quality reusable fixes:

1. Solve-optional materializer logic from G12C.
2. Tests covering:
   - full-planner issue: solve file exists → pass;
   - continuation issue: solve file absent → pass with explicit optional-missing status;
   - truly required source absent → fail;
   - zero-valued fields remain observed zero, not missing.
3. Source-coverage audit utility if it is generic and repository-quality.
4. Compact pre-rebase status/audit artifact for G8T→G12E.

Priority B — compact evidence/docs only:

1. Native K=3 / no-z-route audit.
2. M3 bounded 256-constraint ablation evidence.
3. G10F 4-method one-issue pass summary.
4. G11A event/replan freeze summary.
5. G12A/B/C progression summary.
6. G12E full-day method matrix and failure classification.
7. A supersession boundary stating that the old M1–M4 main comparison will not be extended after professor feedback.

---

## 5. Files/code that MUST NOT be ported as production architecture

Do not commit:

- task-package tarballs;
- `frozen_artifacts/TASK_G12*` output trees;
- materialized per-issue CSV/Parquet outputs;
- package-local `__pycache__`;
- `sitecustomize.py` monkeypatch used to delete M3 constraints;
- G12D broken packaging package;
- G12E raw engine output/log directories;
- large external datasets;
- any new scientific redesign (B0–B7, checkpoint-aware AI training, new risk monitor, new AC safety projection) in this PR.

Do not repair M3/M4 legacy full-day failures merely to make the matrix green.

---

## 6. Recommended repository location for compact checkpoint evidence

Prefer a clearly scoped directory such as:

```text
performance/post_stage15_runtime_acceleration/PRE_REBASE_CHECKPOINT/
```

Recommended compact files:

```text
00_READ_FIRST.md
G8T_G12E_PORT_AUDIT.json
G8T_G12E_STATUS.json
G12E_FULL_DAY_MATRIX.csv
G12E_FAILURE_CLASSIFICATION.json
POST_FEEDBACK_SUPERSESSION_BOUNDARY.json
SHA256SUMS.txt
```

Do not add large evidence bytes already present outside Git.

---

## 7. HANDOFF / README update

Update the repository handoff minimally so the next agent does not resume the wrong experiment.

It must say:

- PR #5 is the pre-feedback implementation checkpoint.
- G12E old 4-method full-day lane ended with M1/M2 PASS and M3/M4 legacy-wrapper failures at issue 3493.
- Do not launch G12F or old W02/12-week campaign.
- The next scientific work is a separate post-feedback rebase branch/PR.
- Existing frozen traffic/grid/MESS/OpenDSS/observability infrastructure remains reusable.

Do not rewrite the 198-page research specification in this task.

---

## 8. Validation required before commit

At minimum:

1. `python -m py_compile` on every modified Python file.
2. `bash -n` on every modified shell file.
3. Targeted unit/regression tests for the materializer optional-solve behavior.
4. Existing relevant PR #5 lightweight/self tests that can run without the large external data campaign.
5. `git diff --check`.
6. Secret/path scan: do not commit machine-only absolute paths except inside clearly labeled compact provenance/evidence fields where necessary.
7. Confirm no large generated output was staged accidentally:

```bash
git status --short
git diff --cached --stat
git diff --cached --name-only
```

If a relevant test cannot run because external data/runtime is unavailable, document `NOT_RUN` with exact reason. Do not invent PASS.

---

## 9. Commit strategy

Use a small number of logically separated commits. Suggested structure, adapt after inspection:

```text
fix(observability): accept solve-optional committed continuation steps
chore(evidence): checkpoint G8T-G12E pre-rebase results
docs(handoff): freeze post-feedback supersession boundary
```

Do not commit unrelated dirty files.

---

## 10. Push and PR #5 update

Preferred behavior: update existing draft PR #5 on branch `agent/post-stage15-runtime-acceleration`.

Before pushing, ensure the local branch is safely based on the fetched remote branch. If local history diverged, reconcile without destructive reset/force-push.

Push normally.

If `gh` is authenticated, update PR #5 body to include a concise “Latest pre-rebase checkpoint” section based on `PROPOSED_PR_BODY_UPDATE.md`.

Keep PR draft. Do not merge.

If PR #5 branch cannot safely accept the local changes because the work is based on a distinct unpublished branch, create a **new checkpoint branch from the fetched PR #5 head** and open a **draft PR targeting `agent/post-stage15-runtime-acceleration`**, but do this only if necessary and explain why. Do not silently create an unrelated main-target PR.

---

## 11. Required final Codex report

Return all of the following:

```text
repository root
remote PR #5 head before work
local starting HEAD
final branch
final HEAD SHA
commits created
files changed
files intentionally not committed
tests run + exact PASS/FAIL/NOT_RUN
G12E compact status
PR URL and draft state
whether PR #5 was updated or a stacked checkpoint PR was created
working tree status after push
```

Also create a local handoff archive under:

```text
/home/jaewon/mobile_ess_work/frozen_artifacts/
```

named like:

```text
CODEX_PR5_PRE_REBASE_CHECKPOINT_RESULT_<timestamp>.tar.gz
```

containing the final report, new commit SHAs, changed-file list, test logs/summaries, compact evidence manifest, PR metadata snapshot, and SHA256SUMS. Do not include datasets or full runtime outputs.
