# V29 Grid-Responsive AIDC Final Development Review

RESULT CLASSIFICATION: **V29_DEV_MECHANISM_PASS**

Axes: TECHNICAL_STATUS=PASS; SOURCE_AUTHORITY=PASS; MECHANISM_STATUS=IMPROVED; GRID_EFFECT_STATUS=RESOLVED; AC_PHYSICAL_STATUS=PASS_WITH_PHYSICAL_RESULTS.

## 1. Starting Git state

V29 started from exact remote authority `c955e9e1bda7a6ca0906f80673da51531bf81e2a` on `codex/v29-grid-responsive-aidc-flexibility`. Campaign and forensic evidence remained read-only at their expected heads.

## 2. Stage-1 technical closure

The c955/6a681 comparison found no requested-scope scientific-formulation delta. DA/PI/Actual now share exactly one post-transit connection-delay slot; the namespace firewall recorded zero Actual opens before freeze. Manifest and stale-smoke corrections were metadata-only. Maintained V28R2 regression: 69/69 passed.

## 3. Stage-2 critical-time flexibility upper bound

The rho=.10 aggregate downshift bounds were 0.025683, 0.147754, 1.555834, and 0.972879 kW; rho=1.0 was exactly about 10×. Grid-effective utilization was essentially complete inside the old feasible set, supporting the mixed trust/topology diagnosis rather than hidden optimizer under-use.

## 4. Stage-3 cutoff-observable carry-in authority

Observable request fields were partition, requested nodes/GPUs, requested wallclock, and submit time. Final state, realized runtime, allocated nodes, nodelist, and sharing were prohibited. The causal D-1 18:00→D0 bridge yielded carry-in 0, 0, 216, and 1,020 node-h. April fit rows and post-cutoff actual scheduling features were both zero.

## 5. V29 formulation

The horizon remains one independent 24-hour/96-slot optimization. Initial backlog and Reference Compute Schedule V3 were added with terminal parity; the primary minimax objective, rho=.10, strict full-node eligibility, and PARTIAL/shared exclusion were unchanged.

## 6. V29 backend

B0/B1/B2 used monolithic solves; operational B3 used CL_MC_BD with monolithic and Standard BD comparison at 1e-4 equivalence. Actual made zero optimizer calls, PI remained ex-post B3, and the current-head smoke completed 10×96 fresh OpenDSS solves.

## 7. 2025-04-01–04 development results

| Day | B0 | B1 | B2 | B3 |
|---|---:|---:|---:|---:|
| 2025-04-01 | 0.567007122 | 0.567003659 | 0.508965474 | 0.508962011 |
| 2025-04-02 | 0.588608532 | 0.588588479 | 0.531388906 | 0.531368885 |
| 2025-04-03 | 0.578016116 | 0.577800638 | 0.515333777 | 0.515276141 |
| 2025-04-04 | 0.588737713 | 0.586362588 | 0.524944287 | 0.522573554 |

Mean relative reductions were B0→B1 0.111181%, B0→B2 10.409421%, B2→B3 0.116812%, and B0→B3 10.513587%.

## 8. Did critical-time AIDC action increase?

Yes. Pooled mean L1 increased from 1.179990 to 5.613059 kW. Days without carry-in were unchanged; Apr-3 and Apr-4 increased.

| Day | V29 critical row | L1 kW | signed weighted pu |
|---|---|---:|---:|
| 2025-04-01 | line.sw2 A @ 2025-04-01T18:30:00+10:00 | 0.025683 | 3.46319472e-06 |
| 2025-04-02 | line.sw2 A @ 2025-04-02T18:30:00+10:00 | 2.165565 | 2.00530097e-05 |
| 2025-04-03 | line.sw2 A @ 2025-04-03T06:45:00+10:00 | 3.384822 | 0.00021547766 |
| 2025-04-04 | line.sw2 A @ 2025-04-04T07:15:00+10:00 | 16.876164 | 0.00237512522 |

## 9. Did sensitivity-weighted grid-effective action increase?

Yes. Pooled signed sensitivity-weighted relief increased from 9.36235554e-05 to 0.000653529771 pu.

## 10. How much carry-in flexibility was actually used?

B3 carried 1,236 node-h across four days. Within-cohort FIFO attribution scheduled all of it, including 15.627680 node-h at each day's critical slot in aggregate; carry-in conservation error stayed below 1e-9 node-h.

## 11. Did compute-only B0→B1 become more grid-effective?

Yes on the mechanism gate: Apr-3 B0→B1 relief was 0.037279% and Apr-4 was 0.403427%, while Apr-1/2 reproduced the no-carry baseline behavior.

## 12. Did B2→B3 become numerically resolved?

Yes. All four days were STRONGLY_RESOLVED; every B3 relative solver range was below 1e-4 and each operational increment exceeded 10× its absolute solver spread.

## 13. Fresh OpenDSS physical result

All 40 trajectories and 3,840 slot solves converged with one clean engine per trajectory. This is PASS_WITH_PHYSICAL_RESULTS, not a claim of zero physical violations: 12 trajectories recorded a voltage/current violation flag and remain explicitly reported.

## 14. Actual result

Actual optimizer calls were zero. B3 executed/missed/backlog node-h are preserved per day in `V29_4DAY_ACTUAL_RESULTS.csv`; workload mass errors were below 1e-9 and MESS terminal target errors were zero for B0–B3.

## 15. PI regret

ACT−PI AC rho regret by day was 0.020305, 0.031529, 0.004653, 0.011879. PI used realized ex-post inputs without DA namespace reads.

## 16. Mechanism status

MECHANISM_STATUS=IMPROVED because both required pooled inequalities passed. This is a mechanism result on a development/regression set, not May final success.

## 17. What did NOT change

Scale, 12-site weights, C1, placement, ratings, PF, rho=.10, the primary objective, and PARTIAL/shared noncontrollability did not change.

## 18. What must not be retuned from the 4-day result

Do not change rho, inflate carry-in/queue mass, widen eligibility, weight or hard-code sites, alter the objective, invent deadlines/preemption, change MESS ratings/scale, include PARTIAL, or degrade the reference.

## 19. Tests

V28R2: 69 passed. V29 Stage 1–6: 21 passed. Final seal: 2 passed. Total: 92 passed, 0 failed, with no known unexplained failures.

## 20. Artifacts / SHA

All required Stage 1–6 and final artifacts are under `dayahead/artifacts/v29_grid_responsive_aidc/`. `V29_ARTIFACT_SHA256.json` hashes every artifact except itself and records byte counts.

## 21. Preservation audit

Status PASS. Campaign and forensic heads remained exact, their tracked worktrees were unchanged, V22/V24 authority tree objects matched the c955 base, raw source authority remained `3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f`, and existing V28R2 scientific results/certificates were not modified.

## 22. Final Git status

This report was generated from clean Stage-6 parent `69ee6361bfb4f76b4ee8c7cdc768d90d7edd5c63` for the final review commit. No push or merge was performed.

V29 did increase source-backed AIDC action at electrically decisive critical times while preserving the 24-hour one-shot Day-Ahead boundary.

These April 1–4 results are development/regression evidence, not final independent validation.
