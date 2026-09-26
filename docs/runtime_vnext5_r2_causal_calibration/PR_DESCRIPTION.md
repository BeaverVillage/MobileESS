## Result

This study tests whether causal residual calibration can improve the frozen PR71 R2 Running Q90 without another model, feature, temporal-policy, or quantile search. New R1 is the exact PR71 R2 raw bound; new R2/R3 add global/GPU-weighted one-sided empirical residual corrections. Pending is exact frozen production R0 in every arm.

DEV/CAL froze **raw R1**: neither calibrator met the safety gates, and GPU-weighted calibration also exceeded the predeclared 2% DEVELOPMENT pinball limit. May is already-exposed historical diagnostic, not untouched confirmation.

| May Running | Coverage | GPU coverage | Total-runtime>4h under | Missed GPU-slots | Overreserve / requested-reference overreserve | Q90 pinball (s) |
|---|---:|---:|---:|---:|---:|---:|
| R0 frozen production | 54.06% | 56.35% | 48.77% | 136,902 | 0.68454 | 32,197.51 |
| R1 raw PR71 R2 | 86.53% | 84.65% | 14.36% | 41,286 | 1.35484 | 13,058.72 |
| R2 global calibration | 87.04% | 85.13% | 13.81% | 41,058 | 1.36027 | 13,064.18 |
| R3 GPU-weighted calibration | 86.85% | 85.02% | 14.01% | 41,209 | 1.35630 | 13,056.75 |

May missed-slot reduction versus raw is R2 0.552% (paired 7-issue block 95% CI 0–7.326%) and R3 0.187% (0–2.431%). Both include zero. Pinball deltas are +5.462 seconds [−9.926,+18.859] and −1.968 [−7.722,+1.224]. Neither candidate reaches 90% coverage/GPU coverage. Reserve remains the user's **preferred** condition, not an added hard calibration-support gate; its failure is reported separately.

`RUNTIME_CALIBRATION_SUPPORTED=FALSE`, `PRODUCTION_REPLACEMENT_SUPPORTED=FALSE`, `OPTIMIZER_INTEGRATION_READY=FALSE`, `PRODUCTION_PROMOTED=FALSE`.

## Causal protocol and evidence

- Only strictly prior OOS predictions with `source_issue < issue` and `job_end < issue` enter calibration. Filter before latest-per-Job deduplication; residual uses the **source** issue and source raw Q90.
- Expanding available residual history; inverse empirical CDF at 90%, positive additive correction, no interpolation/scaling/capping. Fewer than 100 distinct mature Jobs means raw fallback with all queries retained.
- No finite-sample/distribution-free coverage guarantee. `D1_SCHEDULER_REQUEST_STATE_PROXY_V1` remains UNVERIFIED/UNOBSERVED; historical request versions and actual census completeness are not claimed.
- Pre-DEV registration, DEV/CAL freeze, exact source/model-maturity audit, 59 residual memberships, elapsed/GPU strata, paired day/block uncertainty, Korean review, source/parent hashes and reproducible scripts.
- Six contract tests, 198,269 prediction rows, all 330 CI rows, Pending equality, exact raw preservation, independent replay, scoped staged/committed blob verification.

New scope only: `docs/runtime_vnext5_r2_causal_calibration`, stacked on PR71. Start with `FINAL_REVIEW_KO.md`, `FINAL_VERDICT.json`, `COMPARISON.png`, and `README.md`.

No model fits, optimizer/MESS/IEEE123/8500/Actual/OpenDSS runs or edits, or production promotion. All parent frozen evidence is preserved.
