## Problem and result

Running bounds still miss GPU occupancy despite the fixed elapsed-conditioned MULTI_QUANTILE model. This study holds the 180-day/14-day temporal policy and Pending frozen R0 constant, compares one predeclared GPU/observed-long-job weighting change (R2) and one fixed archive-conditional censored AFT challenger (R3), and ends selector/threshold/quantile search. Q90 remains Q90; Q50/Q95 are separate diagnostics.

May historical diagnostics (already exposed):

| Running arm | Coverage | GPU coverage | Total-runtime>4h under | Missed GPU-slots | Overreserve / walltime-reference overreserve | Q90 pinball (s) |
|---|---:|---:|---:|---:|---:|---:|
| R0 frozen production | 54.06% | 56.35% | 48.77% | 136,902 | 0.685 | 32,197.51 |
| R1 frozen MQ | 81.95% | 81.53% | 19.28% | 42,242 | 1.400 | 15,114.68 |
| R2 GPU/long weighted MQ | 86.53% | 84.65% | 14.36% | 41,286 | 1.355 | 13,058.72 |
| R3 censored AFT | 96.93% | 93.33% | 3.17% | 31,579 | 26.531 | 225,310.20 |

R2 improves May Q90 pinball by 13.6% versus R1 (paired 7-issue block delta 95% CI −4,703.71 to −216.14 seconds), but fails coverage gates. R3 was the only safety-passing DEV/CAL research candidate; its excessive reserve and loss reject operational superiority. Its missed-slot reduction versus R0 is 76.93% (95% block CI 50.98–92.72%), while the May comparison against R1 is not robust. No adoption is made.

`NEW_MODEL_SUPERIOR=FALSE`, `PRODUCTION_REPLACEMENT_SUPPORTED=FALSE`, `OPTIMIZER_INTEGRATION_READY=FALSE`, `PRODUCTION_PROMOTED=FALSE`. Pending remains exactly R0 in every arm.

## Evidence and scope

- New files only under `docs/runtime_vnext4_gpu_censored_running`; stacked on PR68. Prior frozen evidence is byte-preserved.
- User-authorized `D1_SCHEDULER_REQUEST_STATE_PROXY_V1` and archive-conditional censor risk set; request versions and actual historical census remain UNVERIFIED/UNOBSERVED. No immutable request, complete census, or outcome-independent archive-inclusion claim.
- Censored future completion values are masked before model-facing labels/features/weights. The raw GPU extract has no null-end rows; absent never-completed jobs are not fabricated.
- Pre-DEV model/weight registration, DEV/CAL selection freeze, exact memberships with lossless compact reconstruction, elapsed/GPU strata, full paired 1/7-issue bootstrap CIs, Korean review and executable reproduction.
- R2−R1 isolates the weight change; R3−R2 combines model and censored-population effects. May is historical diagnostic, never untouched confirmation.
- Six contract tests, all 118 fits, portable membership reconstruction, raw input byte reconstruction, independent metrics/360 CI-row recomputation, Pending R0 equality, source hashes and scoped Git blob checks.

Start with `FINAL_REVIEW_KO.md`, `FINAL_VERDICT.json`, `COMPARISON.png`, and `REVIEWER_GUIDE.md`. Full model weights/full membership Parquets remain unchanged locally with manifests; compact exact membership and portable preprocessing are committed.

No optimizer, MESS, IEEE123/8500, Actual/OpenDSS, or production code execution/modification/promotion.
