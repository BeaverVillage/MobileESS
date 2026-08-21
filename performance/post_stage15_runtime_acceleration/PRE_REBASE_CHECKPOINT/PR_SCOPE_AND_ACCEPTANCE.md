# PR #5 Pre-Rebase Checkpoint — Scope and Acceptance

## Goal

Create a clean, reproducible Git checkpoint of meaningful G8T→G12E work **before** starting the new professor-feedback redesign.

## In scope

- clean reusable repository-level materializer fix from G12C, if not already present;
- targeted tests for solve-optional continuation materialization;
- compact native-K3/no-z-route audit;
- compact M3 bounded ablation audit;
- compact G10F/G11A/G12A/B/C/E status evidence;
- HANDOFF update preventing accidental continuation of the old experiment;
- PR #5 body update with honest latest status;
- checksums and compact provenance.

## Out of scope

- PFR/v13 scientific redesign;
- new B0–B7 baseline implementation;
- AI-training checkpoint/gang/power-throughput model;
- new joint conformal risk monitor;
- new AC safety projection controller;
- fixing old M3/M4 full-day wrappers for appearance;
- full W02 / 12-week rerun;
- committing datasets or raw runtime outputs.

## Acceptance criteria

1. No force-push or history loss.
2. Existing PR #5 scientific invariants preserved.
3. Materializer optional-solve semantics cleanly implemented/tested or proven already equivalent.
4. G12E result preserved honestly: M1/M2 full-day pass, M3/M4 fail at issue3493.
5. No large generated artifacts staged.
6. `git diff --check` clean except explicitly justified byte-frozen legacy assets already present.
7. Modified Python compiles; modified shell scripts pass `bash -n`.
8. Targeted tests pass or are explicitly NOT_RUN with reason.
9. PR remains draft and unmerged.
10. Final local result bundle created with SHAs/test summary/PR metadata.
