# V40R5 BODY gate feasibility proof

PRIMARY RESULT: NO REGISTERED COMBINATION PASSED THE FROZEN SAFETY GATES

IMPORTANT METHODOLOGICAL FINDING: BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION

BODY_GATE_STRUCTURAL_INCOMPATIBILITY = YES (actual CAL BODY population).

For a nonnegative target y and nonnegative Q90 prediction, y=0 is always covered under y<=Q90. Partitioning the oracle BODY population gives

`C_overall = p_zero + (1-p_zero) C_positive`.

Thus `C_positive >= .90` implies `C_overall >= .90 + .10 p_zero`. This exceeds .95 exactly when `p_zero > .50`. No alternative nonnegative predictions can satisfy both bounds for such a population. This argument is independent of model quality, calibration, or tuning.

The whole mature TRAIN target reference and the actual BODY denominators must be distinguished:

| Population | N | Zero N | p_zero | Min overall at positive 90% | Incompatible |
|---|---:|---:|---:|---:|---|
| Whole mature TRAIN reference | 16032 | 8168 | 50.94810379% | 95.09481038% | YES |
| TRAIN | 15638 | 8168 | 52.23174319% | 95.22317432% | YES |
| DEVELOPMENT | 5317 | 3158 | 59.39439534% | 95.93943953% | YES |
| CALIBRATION | 2345 | 1195 | 50.95948827% | 95.09594883% | YES |
| EXPOSED_EVALUATION | 8030 | 3856 | 48.01992528% | 94.80199253% | NO |

On the same mature TRAIN days, whole-target zero fraction rises from 40.86826347% at reconstructed 30min to 50.94810379% at 15min. The 30min diagnostic is a consecutive sum of original-event 15min labels, not a newly fitted target.

On the CAL empirical grid, positive covered intervals must be at least 1035, but the overall upper bound permits at most 1032. This is also an exact integer contradiction.

The EXPOSED aggregate BODY zero fraction is below 50%, so its aggregate bounds are feasible in principle. An observed EXPOSED overall upper-bound failure is not, by itself, proof of structural incompatibility in that split. The mandatory CAL gate already prevents selection under the frozen contract.

All existing BODY options and both registered raw tuning trials are reported below. BC1 existed only for the DEV-selected trial 0. No BC1 score is created for trial 1. PB2 was optional and not implemented. Results are diagnostics of saved predictions, never a new ranking.

| Role / candidate | Overall | Zero-only | Positive BODY | Frozen BODY failure reasons |
|---|---:|---:|---:|---|
| CALIBRATION / PB1_TRIAL_0_BC0 | 86.652452% | 100.00% | 72.782609% | OVERALL_COVERAGE_BELOW_90, POSITIVE_BODY_COVERAGE_BELOW_90, MONTHLY_OVERALL_BELOW_88:2024-11 |
| CALIBRATION / PB1_TRIAL_1_BC0 | 85.628998% | 100.00% | 70.695652% | OVERALL_COVERAGE_BELOW_90, POSITIVE_BODY_COVERAGE_BELOW_90, MONTHLY_OVERALL_BELOW_88:2024-11 |
| CALIBRATION / PB1_TRIAL_0_BC1 | 95.138593% | 100.00% | 90.086957% | OVERALL_COVERAGE_ABOVE_95 |
| EXPOSED_EVALUATION / PB1_TRIAL_0_BC0 | 86.799502% | 100.00% | 74.604696% | OVERALL_COVERAGE_BELOW_90, POSITIVE_BODY_COVERAGE_BELOW_90, MONTHLY_OVERALL_BELOW_88:2025-01, MONTHLY_OVERALL_BELOW_88:2025-02 |
| EXPOSED_EVALUATION / PB1_TRIAL_1_BC0 | 86.052304% | 100.00% | 73.167226% | OVERALL_COVERAGE_BELOW_90, POSITIVE_BODY_COVERAGE_BELOW_90, MONTHLY_OVERALL_BELOW_88:2025-01, MONTHLY_OVERALL_BELOW_88:2025-02 |
| EXPOSED_EVALUATION / PB1_TRIAL_0_BC1 | 96.948941% | 100.00% | 94.130331% | OVERALL_COVERAGE_ABOVE_95 |

| Role / candidate | Positive Q90 pinball mean GPUh | Positive normalized pinball | Positive Q50 WAPE | Positive Q50 MAE GPUh | Positive Q90 WAPE | Positive Q90 MAE GPUh | Under GPUh | Over GPUh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION / PB1_TRIAL_0_BC0 | 17.156805 | 0.592989760 | 97.155226% | 28.109647 | 141.394865% | 40.909376 | 18782.184317 | 51946.216093 |
| CALIBRATION / PB1_TRIAL_1_BC0 | 17.980542 | 0.621460547 | 96.978707% | 28.058575 | 134.947313% | 39.043924 | 20234.465301 | 45463.525463 |
| CALIBRATION / PB1_TRIAL_0_BC1 | 15.591471 | 0.538887212 | 101.301343% | 29.309231 | 418.330331% | 121.034331 | 5014.054829 | 229082.596289 |
| EXPOSED_EVALUATION / PB1_TRIAL_0_BC0 | 16.070564 | 0.505446565 | 96.689123% | 30.742098 | 136.360384% | 43.355490 | 61227.443172 | 213142.708677 |
| EXPOSED_EVALUATION / PB1_TRIAL_1_BC0 | 16.307839 | 0.512909240 | 96.435423% | 30.661434 | 136.918610% | 43.532977 | 62372.817148 | 214262.197604 |
| EXPOSED_EVALUATION / PB1_TRIAL_0_BC1 | 16.305292 | 0.512829162 | 100.408081% | 31.924533 | 441.503741% | 140.375161 | 11832.123124 | 946228.651092 |

A. Yes: PB1 trial 0 / BC1 has positive BODY coverage inside 90–95% in both CAL and EXPOSED.

B. Yes within the BODY gate: that option fails only the overall upper 95% in each split; sample support and monthly BODY lower bounds pass. CAL is structurally incompatible. EXPOSED is feasible in principle but this saved prediction exceeds its overall upper bound. This does not establish whole-pipeline safety.

C. PB1 trial 0 / BC0 and trial 1 / BC0 fail positive BODY coverage in CAL and EXPOSED. These observed undercoverage failures remain distinct from the mathematical evaluation-contract conflict.

Burst detector recall, GPUh-weighted recall, captured GPUh, ECE, FPR, envelope coverage, and overreservation retain their frozen evaluations. No automatic detector PASS follows from this BODY finding. The rejected PB1_BC0_C3_R0 diagnostic pipeline remains rejected; selected_model=NONE.

The 15-min target increased zero inflation sufficiently that the preregistered simultaneous overall and positive BODY Q90 coverage bounds became structurally incompatible. Therefore, failure of the registered BODY gate cannot be interpreted solely as evidence of poor forecast quality.

V40R5 remains failed under its frozen preregistration; the evaluation contract will be corrected only in a separate prospective revision.

NEXT_RECOMMENDED_REVISION=V40R5R1_ZERO_INFLATION_AWARE_GATE_CORRECTION. Recommendation only; no revision created or executed. Future scope is evaluation-contract correction: separate occurrence from positive BODY magnitude, treat overall coverage as diagnostic, retain burst and hybrid overreservation/safety gates. Preserve the target, cohort, splits, features, threshold, model registry/hyperparameters, May firewall and optimizer firewall.

No model fits, new calibrations, threshold/eta changes, reselection, or winner promotion were performed for this audit. Protected input, prediction, result and frozen-contract SHA256 values were checked before and after. All operational HOLDs remain unchanged.

[Full audit, monthly gates, exact metrics and unchanged hashes](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_ZERO_INFLATION_GATE_AUDIT.json>)
