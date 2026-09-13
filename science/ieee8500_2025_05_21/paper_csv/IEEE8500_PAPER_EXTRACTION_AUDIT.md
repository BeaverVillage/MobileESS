# IEEE8500 paper extraction audit

IEEE8500 PAPER EXTRACTION: **PASS**
Extraction timestamp (UTC): 2026-09-12T12:14:16.188175+00:00
SCIENTIFIC_EXECUTION_COUNT = 0 (this archive/extraction stage only).

Input archive: `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_ALL_RAW_RESULTS_20260912_205138.tar.gz`
SHA256: `9c5519cd182c803b75c305267ed44d617d696f8a8f7c91614897bd52e30ada6e`
Archive bytes: 26437106617
Archive members: 23711
Raw files: 23709
Raw source bytes: 27573635238
Evaluation date: 2025-05-21

## Scope and authority

All IEEE8500 workspace directories and matching root files are included, including planning, Day-Ahead, Actual, coefficient matrices, trajectories, logs, checkpoints, input manifests, source, historical failures and diagnostics. External IEEE123/V41R4 repositories and raw SUMO dependencies referenced by manifests are not duplicated wholesale. This archive is not a self-contained relocated execution environment.

The feeder is the canonical unbalanced IEEE8500 source with frozen 36 PCC transformers and declared compatibility adaptation: source1.0400pu, Vreg123.5V, alpha0.50, CAPBank3 OFF. This is not claimed as an unmodified canonical operating-point reproduction.

### Final scope-specific result authorities

- Day-Ahead B0: `IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json`
- Day-Ahead B1: `IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json`
- Day-Ahead B2: `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- Day-Ahead B3: `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- Actual B0: `IEEE8500_actual_20260912_r3/B0/COMPLETE.json`
- Actual B1: `IEEE8500_actual_20260912_r3/B1/COMPLETE.json`
- Actual B2: `IEEE8500_B2_actual_availability_gating_20260912_r3/FINAL_ACCEPTANCE.json`
- Actual B3: `IEEE8500_actual_20260912_r3/B3/COMPLETE.json`

All old stopped, pre-binding, failed-primary and excluded diagnostic candidates remain historical. A stale RUNNING status in the stopped r2 folder does not indicate a live run; see r3 STOPPED_PREVIOUS_RUN.json. No historical candidate is promoted by extraction.

## Metric and runtime definitions

- All source JSON read as data; no project modules imported. No optimization, OpenDSS, AC replay, inference or training performed by extraction. Ongoing B2 replay is a separate previously authorized stage.
- Attachment named a deleted older tar.gz. Latest user request requires new complete archive after B2; this new archive is the extraction authority.
- Line-loading denominator and critical terminal/conductor preserved. Voltage witness names absent in DA JSON remain NA; stored Actual witness names are retained.
- B3 MF trial RESULT has lower P1 but is not final accepted authority; only FINAL_AUTHORITY is used. B2 primary failure and diagnostic feasible candidate are historical, not final decisions.
- Legacy contract labels mentioning1800seconds/30min persist in raw code lineage; actual explicit frozen budget and accounting are14400seconds. No labels are rewritten in raw evidence.
- No global bounds or gaps inferred from neighborhood or fixed-route subproblem optima. Missing B0/B2 end-to-end runtime is NA.
- P/Q event counts use vehicle-slots, absolute>1e-9; no numerical power-flow calculation. Temporal/spatial counts compare exact job_UID paired assignments against final B0.
- Reduction=100*(B0-candidate)/B0 within identical metric scope. Runtime min=seconds/60. SoC fraction unchanged. Slots zero-based, clock=15min*slot.

- Final accepted B3 P1 comes from FINAL_AUTHORITY, not the lower-P1 MF trial RESULT. Raw original V41R4 algorithm source/semantics are intentionally reused; final IEEE8500 results are identified by the independent IEEE8500 numerical preflight, common coefficient SHA list, parsed counts and frozen electrical settings. No IEEE123 numerical results are substituted.
- Branch count is4911 distinct bus-to-bus graph corridors. There are3703 line elements and1226 transformer elements (4929 in total); parallel/single-phase bank elements do not equal graph corridors.
- `max_voltage_pu`, `min_voltage_pu`, and feasibility fields in policy summary refer to DAY_AHEAD_AC. Additional Actual fields are explicitly labelled. AC feasibility rows retain both scopes.
- DA violation counts count violating slots; Actual counts are recorded node/line-phase/transformer-row occurrences summed over slots. The units are labelled and not treated as identical counts.
- DA min/max bus-phase witnesses are absent from saved final AC JSON. Their time slots are extractable; bus/phase fields remain NA. Endpoint voltages are not recomputed.
- B3 total algorithm runtime includes reused final B1 runtime once; incremental runtime excludes it. AIDC search budgets are14400s each for B1 and B3 A1, not a14400s total cap on M1/A1/MF. B3 paper A1=raw A0/B1 reuse, paper A2=raw A1, paper M2=raw MF.
- Search time-limit termination and no global certificate are preserved. A local LP/MILP optimum or bound is not a global optimum/bound for the whole policy.
- OBJECTIVE_TIME_TRACE_AVAILABLE = true. Each record labels its clock origin; absent per-neighborhood elapsed times are NA rather than cumulative solver-time approximations.

## Unresolved fields

- F: B1/B3 recorded DA algorithm totals include AC; no aggregate B2 restoration total recorded
- L: 4 policy rows; DA voltage bus/phase witnesses, endpoint voltage, B0/B2 total runtime, global bounds/gaps unavailable

## CSV outputs and aggregation provenance

| File | Rows | SHA256 |
|---|---:|---|
| 00_CASE_AUTHORITY.csv | 1 | `7a08fa17de6a0fb3e5f54d258c29b5e6f058c506651d65c99f3aa93a7f610e02` |
| 01_POLICY_PERFORMANCE_SUMMARY.csv | 4 | `d482b4c0210de10bb9b4c2c127011285926d18ba3eff12a7619eeb823011ee9b` |
| 02_RUNTIME_AND_TERMINATION.csv | 4 | `fd4d28419c28e311158b838ebc1ef5bac9ca3b365c199f0534dd3fcd815232ac` |
| 03_AC_FEASIBILITY_SUMMARY.csv | 8 | `d1223706a1dc7c61b40e7583cef2fdb0747f836344fc437f015c91d91dda06ae` |
| 04_DECISION_SUMMARY.csv | 4 | `2a5b6f7629f11abc7c68806dad50adda6bf35adb5ca7f6b6c071813339bde6dd` |
| 05_NETWORK_SCALE_COMPARISON_READY.csv | 1 | `bb09aae9996e75f578e5a04291d375b66f9a5dff82f5b3724f6689bd1658125e` |
| 06_OBJECTIVE_TIME_TRACE.csv | 2287 | `015c3d05044d5709bac8aef12afe3d3b44ffbaa42307ac1c44671305aa0cf27a` |
| 07_CRITICAL_LOADING_DETAIL.csv | 12 | `0d87d3e1a34675e86dd638acdf4be0e0f21587043c5eff26b5cedaaecd63b241` |
| 08_POLICY_PAIRED_COMPARISON.csv | 6 | `794c1504541449f5f1f3ed1867ef77d7bdfeddbc6417ef518064706b594893fe` |
| 09_PAPER_KEY_RESULTS.csv | 36 | `81a5478fc2663573dd5b4684f27e9cff49cb3a415983034f56807a514410f8c4` |
| 10_VALIDATION_CHECKS.csv | 15 | `87e6ca991570105a155406f85cfd29a6f9fb8c6c8bece6d19ece987a4ca32cc7` |

### 00_CASE_AUTHORITY.csv
Parsed feeder and experiment scale, with nominal name separated from actual counts

Source archive members:
- `IEEE8500_B3_production_20260912/PRODUCTION_RULES.json`
- `IEEE8500_pcc_overlay_20260911/PCC_OVERLAY_STRUCTURAL_VALIDATION.json`
- `IEEE8500_scalability_20260910/audit/lines.json`

### 01_POLICY_PERFORMANCE_SUMMARY.csv
P1, DA AC, and realized AC: separate metrics and same-scope reductions

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B2_physical_closure_20260912_r2/accepted_clean_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3_A1/ACCEPTED_AIDC.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_numerical_preflight_20260911/P1_EXACT_B0_WITNESS_BINDING.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/ACCEPTED_AIDC.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/final_exact/AC_VALIDATION.json`

### 02_RUNTIME_AND_TERMINATION.csv
Recorded DA runtime and component budgets; no global optimality claim

Source archive members:
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3_A1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_B3_production_20260912/B3_A1/F_AND_O_LIVE.json`
- `IEEE8500_B3_production_20260912/B3_A1/MODEL_BUILD_MEMORY.json`
- `IEEE8500_B3_production_20260912/B3_A1/SCALABILITY_METRICS.json`
- `IEEE8500_B3_production_20260912/B3_A1/SOLVER.log`
- `IEEE8500_B3_production_20260912/campaign.py`
- `IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/F_AND_O_LIVE.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/MODEL_BUILD_MEMORY.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/SCALABILITY_METRICS.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/SOLVER.log`
- `IEEE8500_v41r4_production_20260911_r2/aidc_runtime.py`

### 03_AC_FEASIBILITY_SUMMARY.csv
Saved exact AC validations; DA and Actual remain separate

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_B2_physical_closure_20260912_r2/accepted_clean_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/final_exact/AC_VALIDATION.json`

### 04_DECISION_SUMMARY.csv
Final accepted DA decision counts, with separately labelled Actual terminal SoC

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/ACTUATOR.json`
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3_A1/ACCEPTED_AIDC.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/ACTUATOR.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/ACTUATOR.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/ACTUATOR.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/ACCEPTED_AIDC.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json`

### 05_NETWORK_SCALE_COMPARISON_READY.csv
IEEE8500 only; no IEEE123 results appended

Source archive members:
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_numerical_preflight_20260911/P1_EXACT_B0_WITNESS_BINDING.json`
- `IEEE8500_pcc_overlay_20260911/PCC_OVERLAY_STRUCTURAL_VALIDATION.json`
- `IEEE8500_scalability_20260910/audit/lines.json`

### 06_OBJECTIVE_TIME_TRACE.csv
Saved checkpoints, accepted updates and every neighborhood incumbent record; missing clocks remain NA

Source archive members:
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3_A1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_B3_production_20260912/B3_A1/IMPROVEMENT_TRACE.json`
- `IEEE8500_B3_production_20260912/B3_A1/timed_checkpoints/1h.json`
- `IEEE8500_B3_production_20260912/B3_A1/timed_checkpoints/2h.json`
- `IEEE8500_B3_production_20260912/B3_A1/timed_checkpoints/30min.json`
- `IEEE8500_B3_production_20260912/B3_A1/timed_checkpoints/4h.json`
- `IEEE8500_B3_production_20260912/B3_M1/FINAL_AUTHORITY.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/IMPROVEMENT_TRACE.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/timed_checkpoints/1h.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/timed_checkpoints/2h.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/timed_checkpoints/30min.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/timed_checkpoints/4h.json`

### 07_CRITICAL_LOADING_DETAIL.csv
Saved loading witnesses; unrecorded endpoint voltages remain NA

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B2_physical_closure_20260912_r2/accepted_clean_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3_A1/ACCEPTED_AIDC.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_numerical_preflight_20260911/P1_EXACT_B0_WITNESS_BINDING.json`
- `IEEE8500_scalability_20260910/audit/lines.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/ACCEPTED_AIDC.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/final_exact/AC_VALIDATION.json`

### 08_POLICY_PAIRED_COMPARISON.csv
Scope-preserving B0 paired comparisons

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B2_physical_closure_20260912_r2/accepted_clean_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3_A1/ACCEPTED_AIDC.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_numerical_preflight_20260911/P1_EXACT_B0_WITNESS_BINDING.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/ACCEPTED_AIDC.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/final_exact/AC_VALIDATION.json`

### 09_PAPER_KEY_RESULTS.csv
Compact key values without metadata overload or optimality overclaim

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B2_physical_closure_20260912_r2/accepted_clean_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3_A1/ACCEPTED_AIDC.json`
- `IEEE8500_B3_production_20260912/B3_A1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_B3_production_20260912/B3_A1/F_AND_O_LIVE.json`
- `IEEE8500_B3_production_20260912/B3_A1/MODEL_BUILD_MEMORY.json`
- `IEEE8500_B3_production_20260912/B3_A1/SCALABILITY_METRICS.json`
- `IEEE8500_B3_production_20260912/B3_A1/SOLVER.log`
- `IEEE8500_B3_production_20260912/PRODUCTION_RULES.json`
- `IEEE8500_B3_production_20260912/campaign.py`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_numerical_preflight_20260911/P1_EXACT_B0_WITNESS_BINDING.json`
- `IEEE8500_pcc_overlay_20260911/PCC_OVERLAY_STRUCTURAL_VALIDATION.json`
- `IEEE8500_scalability_20260910/audit/lines.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/ACCEPTED_AIDC.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/final_exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/aidc_runtime.py`

### 10_VALIDATION_CHECKS.csv
PASS/FAIL/UNRESOLVED evidence checks with missing values explicitly retained

Source archive members:
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/CAUSAL_MOBILITY_PRE_AUDIT.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/B2/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_B2_actual_availability_gating_20260912_r3/FINAL_ACCEPTANCE.json`
- `IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json`
- `IEEE8500_B2_physical_closure_20260912_r2/accepted_clean_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json`
- `IEEE8500_B3_production_20260912/B3/final_exact/AC_VALIDATION.json`
- `IEEE8500_B3_production_20260912/B3_A1/ACCEPTED_AIDC.json`
- `IEEE8500_B3_production_20260912/B3_A1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_B3_production_20260912/PRODUCTION_RULES.json`
- `IEEE8500_actual_20260912_r3/B0/ACTUAL_MOBILITY_PRE_REPLAY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B0/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B1/ACTUAL_MOBILITY_PRE_REPLAY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B1/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_actual_20260912_r3/B3/ACTUAL_MOBILITY_PRE_REPLAY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/AC_SUMMARY.json`
- `IEEE8500_actual_20260912_r3/B3/FINAL_ACTUAL/SLOT_EXTREMA.json`
- `IEEE8500_numerical_preflight_20260911/IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json`
- `IEEE8500_numerical_preflight_20260911/P1_EXACT_B0_WITNESS_BINDING.json`
- `IEEE8500_v41r4_binding_reconstruction_20260911/IEEE8500_V41R4_AIDC_BINDING_PASS.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json`
- `IEEE8500_v41r4_production_20260911_r2/B0/exact/AC_VALIDATION.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/ACCEPTED_AIDC.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/BOUNDED_SOLVER_REPORT.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json`
- `IEEE8500_v41r4_production_20260911_r2/B1/final_exact/AC_VALIDATION.json`

## Read-only preservation and package verification

Every archived source file was verified by SHA256, size and original mtime after archive construction. Every tar member was decompressed and checked against its original SHA256. Every CSV cell was compared against extraction tables; every extraction source SHA was matched to the full archive manifest.
CSV authoring used Artifact Tool worksheet ranges and exact public-range readback, then UTF-8 BOM/RFC4180 CSV serialization. No scientific engine was invoked by these scripts.
