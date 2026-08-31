RESULT CLASSIFICATION: C. V19_C_MASS_TPP_NOVELTY_PASS_PERFORMANCE_FAIL

# V19 C-MASS-TPP final review

## READY FLAGS

- NOVELTY_GATE_PASS = true
- MODEL_DEVELOPMENT_READY = true
- PROPOSED_MODEL_ACCEPTED = false
- FACILITY_FORECAST_INTEGRATION_READY = false
- NEW_LOCKED_TEST_READY = false
- NEW_GRID_SCIENCE_RUN_READY = false

## 1. Novelty audit

World-first claim allowed? `NOT YET`

| Model | Similar component | C-MASS-TPP addition | Near duplicate? |
|---|---|---|---|
| DualTPP / Long Horizon Forecasting With Temporal Point Processes | micro event model plus macro aggregate constraint | continuous GPU-h aggregate-to-event hard reconciliation and frozen tier bridge | NO |
| DEF / Detecting the Future | parallel query event detection plus horizon matching | continuous GPU-h aggregate-to-event hard reconciliation and frozen tier bridge | NO |
| EventFlow | non-autoregressive joint future event-time generation | continuous GPU-h aggregate-to-event hard reconciliation and frozen tier bridge | NO |
| Add and Thin | whole-window point-process generation | continuous GPU-h aggregate-to-event hard reconciliation and frozen tier bridge | NO |
| S2P2 / Deep Continuous-Time State-Space Models | continuous-time state-space event encoder | continuous GPU-h aggregate-to-event hard reconciliation and frozen tier bridge | NO |

## 2. Dataset

- all H100 input events: 323354
- flexible target events: 85866
- training days: 225
- K_max: 10012
- master mass identity max error: 0.0 GPU-h

## 3. Architecture

Decay/jump continuous-time encoder, daily mass head, burst auxiliary, chunked all-at-once service-set decoder, and float64 hard reconciliation.

## 4–7. Baselines, blocked CV, acceptance, ablation

- selected variant: V19-A
- best baseline: B3_LIGHTGBM_QUANTILE
- Daily WAPE relative improvement: -13.182309%
- Burst WAPE relative improvement: 7.981121%
- proposed accepted: False

## 8. April post-freeze diagnostic

- seven-day conditional mean: 16235.362528 GPU-h
- observed diagnostic: 34047.871389 GPU-h
- April was read only after the selection-freeze SHA was written.

## 9–10. Electrical and facility diagnostic

All IT/PCC/site/facility values are `PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC`. They were not used for model selection.

- provisional legacy facility energy share: 6.464113%
- FINAL_FACILITY_FLEXIBILITY_SHARE = null
- literature target calibration: NO

## 11. Scheduler preflight

- feasible: False
- served mass: 16235.362528 GPU-h
- terminal backlog: 0.000000 GPU-h
- shedding: 0.000000 GPU-h

## 12. Limitations

- 225-day supervised horizon
- semantic-flexible label is a retrospective proxy
- exact D-1 queue snapshot absent
- capacity timeline partial and C_MODEL is only an equivalent case-study normalization
- no untouched locked future test
- B5/B6 are resource-feasible long-horizon adaptations rather than canonical likelihood reproductions
- B7/B8 not reproduced for documented compute/dependency reasons
- facility/site electrical magnitudes are provisional legacy-scale diagnostics, not final Melbourne authority

## 13–14. Artifacts and Git

Artifact SHA256 values are reported by the final verification pass. Git commits are recorded after generation.

## 15. Final Q1–Q15

See `V19_FINAL_REVIEW.json` and the final Codex response for explicit answers.
