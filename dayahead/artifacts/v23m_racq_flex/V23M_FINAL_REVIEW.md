# V23M RACQ-Flex 최종 과학 검토

RESULT CLASSIFICATION: `V23M_RACQ_RECURRENCE_GATE_FAIL_ACQ_ONLY`

## READY FLAGS

- NOVELTY_GATE_PASS = `true`
- RECURRENCE_SIGNAL_READY = `false`
- RACQ_MODEL_DEVELOPMENT_READY = `false`
- RACQ_PROPOSED_MODEL_ACCEPTED = `false`
- CONDITIONAL_MEAN_AUTHORITY_READY = `true`
- QUANTILE_AUTHORITY_READY = `true`
- FORECAST_BUNDLE_V2_READY = `true`
- QUEUE_CONSISTENCY_READY = `true`
- POWER_FORECAST_READY = `true`
- SCALE_DEPENDENT_DIAGNOSTIC_READY = `false`
- NEW_LOCKED_TEST_READY = `false`
- PUBLISHABLE_LOCKED_GENERALIZATION_READY = `false`
- NEW_GRID_SCIENCE_RUN_READY = `false`
- FINAL_GRID_SCIENCE_AUTHORIZED = `false`

## 1. Novelty audit

각 구성요소에는 선행연구가 있고 GPU 반복 job을 활용한 연구도 확인됐다. 다만 조사 범위에서 RACQ의 전체 결합과 사실상 동일한 구조는 없었다. Gate는 `PARTIAL_OVERLAP_BUT_DISTINCT_COMBINATION`, WORLD_FIRST는 `NOT_YET`이다.

## 2. Recurrence audit

계정 hash 안정성은 PASS, strict/family/innovation GPU-h 비중은 84.243183%/0.370391%/15.386427%이다. fold 중앙 전체 recurring 비중은 89.877820%지만 R2 Brier 개선 중앙값은 -141.484636%로 실패했다.

## 3. Dataset

source-valid H100 이벤트 323,354개, flexible target 85,866개, 총 614322.9725 GPU-h, 225일과 900개 cutoff sample이다.

## 4. Architecture

Compact hourly DeepSets/decay-GRU, hurdle-ZTNB, LogNormal+GPD, low-rank cohort, exact 15분 질량, fluid/exact EDF, frozen IT-side power bridge를 구현했다. Recurrence branch는 gate에 의해 비활성화됐다.

## 5–8. Baselines, blocked CV, acceptance, ablation

실제 CUDA ACQ 5-fold×3-seed 결과는 mean WAPE 1.091156, Q50 WAPE 1.060961, burst WAPE 0.889745, mass ratio 0.596757, Q50/Q90 coverage 0.370861/0.854305, power WAPE 1.562361이다. RACQ는 gate 규칙상 실행하지 않았고 관련 ablation은 허위 생성하지 않았다.

## 9. April post-freeze diagnostic

freeze SHA `c5dc6ea772e7d2dcf63e6ded45a2a1b04a01d3ee406b96a1cbe85378151be686` 이후에만 읽었다. Mean/Q50 WAPE는 0.571119/0.579127, mass ratio는 0.428881, IT-power WAPE는 1.091231이다. locked test가 아니다.

## 10. Production forecast authority

Mean은 B2 LightGBM Tweedie, Q50/Q90은 B3 LightGBM Quantile을 유지한다. RACQ와 ACQ 모두 새 권위로 승격되지 않았다.

## 11–13. Queue, power, frozen scale

Queue 보존과 hidden shedding=0은 통과했다. PUE 없이 IT-side power만 계산했다. GPU-h에 0.528808792 MW를 곱하지 않았고, flexible peak의 0.406775994 MW IT envelope 초과 0.000 kW는 clipping 없이 진단 실패로 남겼다.

## 14. Limitations

- NO_UNTOUCHED_LOCKED_TEST
- FORECAST_NEW_ONLY_SCOPE
- RETROSPECTIVE_FLEXIBLE_TARGET
- PARTIAL_NODE_HOST_POWER_LOWER_BOUND_GAP
- SITE_SPECIFIC_GPU_ALLOCATION_UNAVAILABLE
- RACQ_ABLATIONS_NOT_RUN_AFTER_GATE_FAILURE

## 15–16. Artifacts and Git

Artifact SHA는 `V23M_ARTIFACT_SHA256.json`에 기록한다. Branch는 `codex/v23m-racq-flex`, 시작 SHA는 `499d5793...`이며 최종 SHA는 self-reference를 피하기 위해 외부 최종 응답에서 보고한다.

## 17. Q1–Q15

- Q1: 사실상 동일한 prior architecture는 찾지 못했으나 각 구성요소와 GPU recurrence 활용에는 강한 부분 중복이 있었다.
- Q2: 반복 GPU-h 비중은 컸지만 preregistered predictive recurrence gate를 만족하는 신호는 입증되지 않았다.
- Q3: fold 중앙 recurring GPU-h 비중은 89.877820%였다.
- Q4: 아니다. R2-vs-R1 GPU-h weighted Brier 중앙 상대 개선은 -141.484636%, bootstrap CI는 [-12.711906292494943, -1.6136339835402735]였다.
- Q5: B2_LIGHTGBM_TWEEDIE가 유지된 mean baseline이다.
- Q6: B3_LIGHTGBM_QUANTILE이 유지된 Q50/Q90 baseline이다.
- Q7: RACQ는 gate 실패로 학습하지 않았다. ACQ fallback daily WAPE는 1.091156165344였다.
- Q8: RACQ 값은 없다. ACQ fallback Q50 WAPE는 1.060961291793였다.
- Q9: 아니다. ACQ burst WAPE 0.889744708853는 C-MASS 0.847146966831보다 나빴다.
- Q10: 입증하지 못했다. RACQ가 gate에서 중단되어 GPD 독립 ablation은 실행하지 않았고 개선 주장을 하지 않는다.
- Q11: 입증하지 못했다. queue/power 구조 보존은 통과했지만 성능 개선 및 mass 비열화 조건을 만족하지 못했다.
- Q12: 아니다. recurrence gate 실패로 RACQ를 paper proposed model로 채택할 수 없다.
- Q13: production mean은 B2 LightGBM Tweedie, Q50/Q90은 B3 LightGBM Quantile이다.
- Q14: NO. GPU-h에 0.528808792 MW scale을 곱한 호출은 0이다.
- Q15: NO. 새 grid science run은 승인되지 않았다.
