# Post-Professor-Feedback Boundary

This checkpoint PR is intentionally **pre-rebase**.

After this PR is cleanly checkpointed, a separate scientific implementation branch/PR will redesign the main experiment around:

- `Move Energy vs. Move Computation` as the primary scientific question;
- AI-training-aware job semantics;
- slow discrete orchestration + 5-minute fast continuous recourse;
- risk-calibrated plan-validity monitoring;
- formal three-phase AC safety filter;
- dual-debt recovery only if ablation demonstrates value;
- broader baseline/regime characterization rather than the old M1–M4 final matrix.

Therefore, in this PR:

1. Do not label M1–M4 as the permanent final paper comparison.
2. Do not spend time repairing G12E M3/M4 solely to continue the old campaign.
3. Do not delete the old design; preserve it as provenance and reusable implementation evidence.
4. Keep frozen traffic/grid/MESS/OpenDSS/observability/atomic-commit infrastructure available for the new branch.
5. Do not modify the large research specification/docx in this task.

Suggested repository status label:

```text
PRE_FEEDBACK_IMPLEMENTATION_CHECKPOINT / LEGACY_MAIN_EXPERIMENT_SUPERSEDED_FOR_NEXT_BRANCH
```
