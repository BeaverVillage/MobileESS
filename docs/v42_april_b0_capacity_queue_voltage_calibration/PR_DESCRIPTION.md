PR123's B0 construction blocked nominal overflow instead of queueing it, and Q50-expired RUNNING jobs reserved future capacity indefinitely. This sibling adds the current V42 nominal-release producer, deterministic capacity queues and all 30 April Planning-to-Actual voltage measurements.

Base: Draft PR #123 exact `81118271a837648da13146fb6ffdc8e3de8d95ab`. PR #124/M1 remains a separate sibling, with no imports, merges, cherry-picks, cache donation or scientific execution. All 3,189 base files are byte-identical.

- CC4 is **24 hourly Q50/Q90 future-arrival lifetime GPUh**, not a four-hour model. Predictions and TRAIN execution-lag kernel are unchanged; no retraining, scaling or clipping.
- RUNNING Planning remaining is `max(Q50_total - elapsed, 0)`. Current issue physical placement remains, while expired nominal future occupancy becomes zero. Runtime overrun gamma **2.423057443558147** and survival kernel are unchanged; reserve achievement/shortfall is a headroom KPI, not electrical load or a new P1/P2 objective.
- Of the former 15 overflow days, nominal release resolves 12 and forward CC4 backlog handles the remaining three. All 30 Planning days respect per-site and 780-GPU capacity; full GPUh plus original post96-tail conservation passes.
- Actual uses submission/UID strict FCFS, no head-of-line backfill, first compatible ascending AIDC spare capacity and causal release/re-admission. Realized end−start duration is uniquely source-backed for all **54,492** frozen J_phys jobs and stays private in the environment. Delayed completion is simulated admission + observed source duration. Future durations/end/receipts never enter the controller.
- B0 has AIDC/workload/Runtime/CC4 ON; grid-aware flexibility, MESS P/Q/movement, Actual P/Q/local repair/global reoptimization and voltage schedule repair **0**. Actual IT and PCC P/Q are recomputed from physical occupancy and each day's NOAA weather; no Planning power copying or CC4 double counting.
- Each day runs new April affine Planning voltage response → freeze → causal Actual queue replay → independent Fresh OpenDSS. Primary residual is **V_ACTUAL_AC − V_PLAN** with sqrt conversion of stored Planning v² and exact 386-node-phase ×96-slot axes. B0 is its new reference anchor, so this does not estimate off-anchor flexible-control linearization error. No operational or primary DA_AC comparison.

Measured April: **B0 30/30; Fresh OpenDSS 30/30 ×96 converged slots; 1,111,680 residual points**. Planning and Actual GPU capacity violations are **0/0**. Actual voltage violations: **22 cells across April 15, 16, 30**, retained without repair. Line current / transformer current / transformer kVA violations: **0/0/0**. Actual IT energy **299,455.783312 kWh**, PCC energy **342,502.768473 kWh**, physical GPUh **439,928.095556**.

Mean signed error **−0.002652077376 pu**, MAE **0.002726309883**, RMSE **0.003252295678**, max absolute **0.012229724342** at **April 25 / idc_idc10_pcc / A / slot 55**. ±0.005 upper/lower/joint point coverage **99.993074% / 89.164868% / 89.157941%**; joint day coverage **0/30**, exceedance days **30/30**.

| q | Point up / down (pu) | Day-worst up / down (pu) | Point candidate band | Day candidate band |
|---|---|---|---|---|
| Q90 | 0.000000000 / 0.005104494 | 0.003687776 / 0.011275945 | 0.955104494–1.050000000 | 0.961275945–1.046312224 |
| Q95 | 0.000000000 / 0.005927587 | 0.004559693 / 0.012125419 | 0.955927587–1.050000000 | 0.962125419–1.045440307 |
| Q97.5 | 0.000437244 / 0.006700580 | 0.005460484 / 0.012229724 | 0.956700580–1.049562756 | 0.962229724–1.044539516 |
| Q99 | 0.001325061 / 0.007588593 | 0.005460484 / 0.012229724 | 0.957588593–1.048674939 | 0.962229724–1.044539516 |


**FINAL_MARGIN_ACCEPTED=false; PROBLEM13_FINAL_VALIDATED=false.** Candidates are calibration evidence awaiting May holdout. B1/B2/B3/May/M1/A2/M2 **NOT_RUN**. No remaining April execution authority blocker.

Validation: **1,200 full pytest PASS**; independent CSV/NPZ identity, residual formulas, capacity, source-backed Actual power and frozen native-state audit PASS. Existing Runtime inference warning remains and finite-output checks pass. Full-precision 145 MB residual CSV is local; its lossless 39 MB gzip, decompressed SHA/size receipt and all generated April response/Actual NPZ files are versioned to respect GitHub's blob limit. Raw external data stays read-only and outside Git.

Evidence: `docs/v42_april_b0_capacity_queue_voltage_calibration/FINAL_REVIEW_KO.md`.
