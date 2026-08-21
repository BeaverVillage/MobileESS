# Mobile ESS — Codex PR #5 Pre-Rebase Checkpoint Handoff

Purpose: **freeze and PR the meaningful work completed through G12E before the professor-feedback scientific redesign begins.**

This is **not** the prompt to implement the new post-feedback PFR/v13 scientific redesign. First checkpoint the current engineering/scientific lineage cleanly in Git/PR, then start the redesign on a separate follow-up branch/PR.

## Preferred target

- Repository: `BeaverVillage/MobileESS`
- Existing PR: **#5**
- Existing PR branch: `agent/post-stage15-runtime-acceleration`
- Remote PR snapshot checked 2026-08-21 KST:
  - state: OPEN
  - draft: true
  - mergeable: true
  - head SHA: `e73d1509d2f9bed230b3fc34c0f603eaea925c10`
  - base: `main`

**Do not assume the local checkout equals this remote SHA. Inspect local Git state first. Do not reset, force-push, or discard local work.**

## Primary Codex instruction

Read `CODEX_PR5_CHECKPOINT_PROMPT.md` first and execute it end-to-end.

Supporting files:

- `CURRENT_WORK_G8T_G12E.md` — compact scientific/engineering status through G12E
- `CURRENT_WORK_G8T_G12E.json` — machine-readable status
- `PR_SCOPE_AND_ACCEPTANCE.md` — what belongs / does not belong in this PR
- `LOCAL_PATHS_AND_ARTIFACTS.md` — local evidence locations Codex should inspect
- `POST_FEEDBACK_BOUNDARY.md` — explicit boundary between this checkpoint and the next redesign
- `PR5_REMOTE_SNAPSHOT.json` — current remote PR metadata snapshot
- `PROPOSED_PR_BODY_UPDATE.md` — content direction for PR #5 body update
- `evidence/G12E_FULL_DAY_MATRIX.csv` — compact authoritative G12E method matrix
- `evidence/G12E_FAILURE_SUMMARY.json` — compact G12E failure evidence
- `SHA256SUMS.txt` — handoff integrity

## Critical rule

Do **not** commit large runtime outputs, frozen-artifact directories, external datasets, generated materialized issue tables, or package tarballs to Git. Commit only source, tests, compact contracts/audits, and compact evidence needed to reproduce/understand the checkpoint.
