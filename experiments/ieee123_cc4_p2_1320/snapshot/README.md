# IEEE123 CC4/P2 ablation: original remaining-priority budgets

Fresh 31-date run for 2025-05-01 through 2025-05-31, sole new policy B3_NO_CC4_P2. Prior redistributed-budget run is superseded and preserved separately. No old NO_CC4 date outputs, checkpoints, jobs, MESS decisions or Actual results are reused here. WITH_CC4 remains the verified frozen main-paper 1-Round authority; it is never reoptimized.

WITH_CC4 AIDC priorities: P1=900, P2=480, P3=180, P4=120, P5=120 seconds; total1800. NO_CC4 priorities: P1=900, original P3=180, original P4=120, original P5=120 seconds; total1320 (22 minutes). P2 time is omitted, not redistributed. Each computing pass (paper A1 and A2) uses1320s. Stage order, objectives, tolerances and original per-family timing scale are retained. Legacy MESS outer budget stays1800s; core shared budget constants that serve MESS are deliberately unchanged. Physical model preparation is outside the original continuous search clock, just as in the frozen authority.

CC4 reserve variables/constraints and P2 solve/locks are absent. A five-slot storage vector has inert zero at index1 for compatibility; independently evaluated reserve shortfall remains a diagnostic. A1→M1→A2→M2 1-Round is retained. Internal B1/A0 is the first computing pass within B3, not an additional policy.

Concurrency is4 date workers ×4 solver threads for the entire new run. Work directories, native OpenDSS paths, logs, checkpoints and outputs belong to each date. New MESS short cache is D:/c5 with a namespace ownership marker. IEEE8500 is untouched. launch.ps1 uses WMI detached supervisor and a separate visible PowerShell monitor; both survive Codex exit. Shutting down or sleeping Windows interrupts execution. Existing supervisor supports identity-checked adoption of this namespace's live workers when recovering.

Audits: AUTHORITY_VERIFIED.json verifies frozen baseline dates and input SHA leaves; PATCH_MANIFEST.json and patches/ record source differences; RUN_CODE_SHA.json pins runtime. Do not use superseded prepare.py or copy old NO_CC4 outputs. Recovery resumes verified completed stages unless the user explicitly requests another fresh campaign.

Outputs: days/YYYY-MM-DD/paired.json and paired.csv, detailed job/migration/MESS comparisons; reports/PAIRED_DAILY.csv, PAIRED_SUMMARY.json and INTERPRETATION.md. Missing results are not zero or PASS. Deltas are WITH minus WITHOUT. Reserve shortfall reduction is a decision-facing benefit; feeder differences are ablation differences only. Future post-issue jobs are not enqueued, so no causal SLA/delay claim is supported.

Previously authorized Actual numerical recovery is retained: initial Q within the original outer1e-7 kvar bound acceptance is projected onto unchanged exact bounds. This is an explicitly recorded numerical execution exception, not bit-identical frozen execution; limits, tolerances, Q_DA reference and P are unchanged. Corrections are audited per date. Numerical source originals stay SHA-sealed.

Monitor: D detail, left/right date, O date logs, R reports, Q closes only monitor. Hourly Codex review continues this namespace. Final flags include TOTAL_AIDC_BUDGET_MATCHED=FALSE, REMAINING_PRIORITY_BUDGETS_UNCHANGED=TRUE, P2_BUDGET_REDISTRIBUTED=FALSE, P1_BUDGET_UNCHANGED=TRUE, WORKERS=4, THREADS_PER_WORKER=4.
