# V44 r043 release and dated campaign continuation

This snapshot updates PR #233 from r032 through r043, preserves the earlier immutable recovery overlays, and records the May 01–07 completion plus the authorized May 08–14 dispatch sequence. The live production checkout and scientific source files were read only while preparing this PR.

## Verified result

All **28 date/arm cases for 2025-05-01 through 2025-05-07** have one official completed result with `Actual96_execution_PASS` and `Fresh96_physical_PASS`. Exact result bytes are in `completed_results/`; their original paths and SHA-256 receipts are in [COMPLETED_RESULTS_MANIFEST.json](COMPLETED_RESULTS_MANIFEST.json).

This is an Actual execution and Fresh physical result. It does **not** assert that every M stage met its independent Global Gap target. Of the 14 B2/B3 final records, four explicitly report `M_gap_certified=false` and ten do not report that field. Missing flags are not promoted to certification. Existing FULL-plan revalidation and historical acceptance policies remain attached to the original results.

The compact Fresh table in [week2/COMPLETED_WEEK_LOADING_TABLE.json](week2/COMPLETED_WEEK_LOADING_TABLE.json) was generated from all 28 official results. B1/B3 values additionally replay the SHA-verified corrective Fresh files over exactly slots 24–119; prefix measurements are excluded. Original raw files remain external and unchanged.

## Changes since the previous PR head

| Revision | Resulting behavior |
| --- | --- |
| r033 | Reuse exact immutable JSON encodings; preserve original output bytes, native solves, measurements and physical checks. Component timings are not an end-to-end Actual speed claim. |
| r034 | Reduce redundant audit/cache-key work while retaining live control and source guards. |
| r035–r037 | Store exact audit content and shared historical rows with lossless reconstruction; retain separate Fresh measurements. Storage maintenance and cleanup keep their explicit ownership and natural-boundary guards. |
| r038 | Prepare cases serially, seal pre-Actual handoffs, then launch independent P-core Actual/Fresh workers. CPU topology, reservations and SMT sharing remain explicit. |
| r039 | Remove the 900-second wall-latency rejection only. The simulation slot remains 900 seconds; physical gates and independent Fresh remain required. |
| r040 | Exclude a failed preparation or bad handoff locally; isolate worker launch and Actual failures without stopping healthy peers. Unresolved preparations still block release. |
| r041 | Fence Actual entry during preparation, preserve completed A1 reuse, and create the state-dump parent before the original exclusive write. |
| r042 | Automatically release verified healthy Actual cases after the preparation barrier. Strip preparation-only routing flags before entering the dedicated Actual runner. |
| r043 | Restore the accepted May07 B1 A1 cache producer's `root` and `case_root`; reject cross-case/tampered caches. Reuse completed May07 B3 M1 with its original Native ledgers, then complete A2, M2, Actual and Fresh. Preserve the six already completed batch cases. |

The original V43 seven-RegControl Planning / SVR12, 43-RegControl Actual architecture remains. Q250, PCS400, P300, the existing Native budgets and physical tolerances remain governed by their sealed policies. Historical authorization and prelaunch validation receipts in `receipts/` are preserved as historical records; [R043_FINAL_RESULT.json](receipts/R043_FINAL_RESULT.json) records the later completed outcome.

## May 08–14 dispatch

The new `v44_week2` adapter binds seven dated input bundles and independently initializes each date with the existing issue-only algorithm. It does not import the previous day's optimized state.

The latest user-authorized sequence in `v44_week2_sequence.py` is:

1. Prepare the **14 B1/B3 cases with one worker**. Keep an already running worker until its natural exit; adopt its verified result without restarting it.
2. Resolve every B1/B3 preparation as ready or excluded, then run healthy Actual/Fresh cases with **at most seven independent workers**. A failure remains local.
3. After every B1/B3 case is terminal, automatically process **B0/B2 by date, one worker at a time**: May08 B0, May08 B2, May09 B0, May09 B2, …, May14 B2. Each worker runs the original complete Planning → Actual → Fresh chain before the next case starts. Existing failed cases stay excluded.

May08 B0 failed the unchanged R0 roster equality check: the source R0 roster contains one UID absent from the native input. [DATED_R0_ROSTER_DIAGNOSTIC.json](week2/DATED_R0_ROSTER_DIAGNOSTIC.json) records this discrepancy. No UID was silently dropped and no physical PASS is claimed for that case.

May08–14 remains in progress. [CURRENT_CAMPAIGN_SNAPSHOT.json](CURRENT_CAMPAIGN_SNAPSHOT.json) is a timestamped snapshot, not a full-week completion certificate. Keep the PR draft while the new campaign is unfinished.

## Existing monitor

`v44_monitor_live_ui/` contains the exact existing monitor binding and helpers copied from the running monitor directory. The existing address remains `http://127.0.0.1:8795/`; the PR does not create another monitor service.

The primary table uses date rows and B0/B1/B2/B3 columns. Completed May01–07 cells show three-decimal Fresh maximum line/phase loading and Fresh PASS; current May08–14 cells show progress, waiting or exclusion without invented measurements. The verified historical summary avoids re-reading large raw Fresh graphs on every refresh. The long 28-case detail table is folded by default. Planning bounds, physical results, controller callback counts and physical slot positions remain separate.

## Validation and environment

- **280 focused regressions passed**: immutable audit encoding/storage, source checks, barriers, failure isolation, preparation fences, automatic release, accepted-cache ownership, second-week ordering, and monitor matrix validation.
- [validation/REGRESSION.xml](validation/REGRESSION.xml) and [validation/RUN.json](validation/RUN.json) record the run. Earlier revision receipts report their own original validation scope and counts.
- Every copied Python snapshot parsed successfully. No credential-pattern findings were found in the copied source snapshot.
- Source copies were compared byte for byte; `.gitattributes` preserves newly added sealed Windows source bytes. Tracked EOL-only differences from the live checkout were excluded.
- Campaign permits and active worker identities remained unchanged during monitor publication and PR preparation.

The production adapters intentionally require the existing Windows/D-drive runtime, raw datasets, solver/native libraries and sealed receipts. This is not a standalone portable replay bundle. The regression entry point loads that pinned environment explicitly and does not dispatch a campaign:

```powershell
python -X utf8 validation_tools/actual_performance/validate_r043_pr_snapshot.py --source-root D:/v44_r022_rowgen_20261017
```

To inspect the existing UI from the snapshot with that same environment:

```powershell
$env:PYTHONPATH='D:/v44_may01_07_prepare_20261016'
python -X utf8 v44_monitor_live_ui/monitor_binding.py 8795
```

The existing live monitor already owns that port; this command is documentation, not a request to launch a second instance. Production permits continue to pin the original live source paths. Reviewing or checking out this PR does not authorize rebinding or restarting a live case.
