# V24M FASER-Flex 최종 과학 검토

RESULT CLASSIFICATION: `V24M_FASER_NOVELTY_PASS_PERFORMANCE_FAIL`

## READY FLAGS

- NOVELTY_GATE_PASS = `true`
- FACTOR_IDENTITY_READY = `true`
- FACTOR_PREDICTABILITY_READY = `true`
- SIGNATURE_SIGNAL_READY = `true`
- RETRIEVAL_SIGNAL_READY = `true`
- FASER_MODEL_DEVELOPMENT_READY = `true`
- FASER_PROPOSED_MODEL_ACCEPTED = `false`
- CONDITIONAL_MEAN_AUTHORITY_READY = `true`
- QUANTILE_AUTHORITY_READY = `true`
- FORECAST_BUNDLE_V3_READY = `true`
- QUEUE_DIAGNOSTIC_READY = `true`
- POWER_DIAGNOSTIC_READY = `true`
- SCALE_DEPENDENT_DIAGNOSTIC_READY = `true`
- NEW_LOCKED_TEST_READY = `false`
- PUBLISHABLE_LOCKED_GENERALIZATION_READY = `false`
- NEW_GRID_SCIENCE_RUN_READY = `false`
- FINAL_GRID_SCIENCE_AUTHORIZED = `false`

## 1. Prior-result integrity

V23M recurrence gate에서 class-weighted probability를 확률로 해석한 calibration 결함을 확인했다. Corrected diagnostic은 비권위 자료이며 V23M 역사 결과와 RACQ gate 결론은 변경하지 않았다.

## 2. Novelty audit

분류는 `PARTIAL_OVERLAP_DISTINCT_COMBINATION`, WORLD_FIRST는 `NOT_YET`이다. Signature GP, retrieval-augmented forecasting, analog ensemble, factor forecasting과 각각 중복되지만 전체 결합의 near duplicate는 찾지 못했다.

## 3–4. Factorization and predictability

H=R×PI×KAPPA 최대 오차는 7.276e-12 GPU-h다. Factorized/direct LightGBM WAPE는 0.975339/0.992099, 주 병목은 `BURST_OCCURRENCE`다. Oracle burst WAPE는 0.700793다.

## 5–7. Path, retrieval, architecture

168시간×8개 causal event channel의 time-augmented path, 검증된 depth-2/3 tensor log-signature, past-only signature analog, J2 OOF residual copula, monotonic reliability gate, mass-preserving shape transfer를 구현했다. iisignature는 NumPy 2 비호환으로 본 실행에는 사용하지 않았고 별도 NumPy 1.26 환경으로 수치 교차검증했다.

## 8. Probe

Signature/retrieval 신호는 각각 4/5, 4/5 fold에서 확인됐다.

## 9–10. Full blocked CV and acceptance

FASER mean WAPE 1.187748, Q50 WAPE 0.941433, CRPS 2454.959353, burst WAPE 0.763990, mass ratio 1.120052, Q50/Q90 coverage 0.499201/0.808843, 15분 WAPE 2.077554, IT-power WAPE 1.888134다. 평균·Q50·분포·Q90 calibration·bootstrap gate 실패로 proposed model 채택은 false다.

## 11. Ablation

Factorization과 signature/retrieval에는 부분 신호가 있었지만 reliability mixture가 단일 retrieval/GP를 일관되게 능가하지 못했다. 따라서 gate의 empirical novelty 기여를 주장하지 않는다.

## 12–15. April, production, queue/power, scale

April은 freeze SHA `471c8f16c9632775fe150dc9bef6b990bfb573c1de523aea1e36bb1a5f03eb51` 생성 후 한 번만 진단용으로 읽었다. Production은 B2 mean/B3 Q50·Q90 fallback을 유지한다. April production mean WAPE는 0.571119, IT-power WAPE는 1.091231이다. GPU-h에 0.528808792 MW를 곱한 호출은 0이며 0.406775994 MW IT envelope 비교만 수행했다.

## 16. Limitations

- NO_UNTOUCHED_LOCKED_TEST
- FORECAST_NEW_ONLY_SCOPE
- RETROSPECTIVE_FLEXIBLE_TARGET
- SITE_GPU_ALLOCATION_UNAVAILABLE
- PARTIAL_NODE_LOWER_BOUND_GAP
- J1_INTRINSIC_COREGIONALIZATION_NOT_COMPLETED
- POSTFREEZE_DIAGNOSTIC_ESTIMATORS_INSTANTIATED_AFTER_APRIL_CONTAINER_OPEN_BUT_FIT_MARCH_ONLY

## 17–18. Artifacts and Git

모든 artifact SHA는 `V24M_ARTIFACT_SHA256.json`에 기록한다. Branch는 `codex/v24m-faser-flex`이며 자동 merge하지 않았다.

## 19. Q1–Q16

- Q1: 아니다. 부분 중복은 있으나 조사 범위에서 사실상 동일한 전체 architecture는 없었다.
- Q2: 그렇다. 최대 identity 오차는 7.276e-12 GPU-h였다.
- Q3: BURST_OCCURRENCE
- Q4: 그렇다. factorized/direct LightGBM WAPE는 0.975339/0.992099였다.
- Q5: probe 기준 5개 fold 중 4개에서 개선 신호가 있었다.
- Q6: 그렇다. signature retrieval은 5개 fold 중 4개에서 CRPS 개선 신호를 보였다.
- Q7: 아니다. gate는 많은 fold에서 단일 analog 또는 GP로 fallback했고 full FASER가 retrieval-only보다 우월하지 않았다.
- Q8: B2_LIGHTGBM_TWEEDIE
- Q9: B3_LIGHTGBM_QUANTILE
- Q10: 1.187747829462
- Q11: Q50 WAPE 0.941433451846, CRPS 2454.959352888569
- Q12: 그렇다. burst WAPE 0.763990358555는 비열등 한계 0.864089906167401 이하였지만 이것만으로 acceptance를 통과하지는 못했다.
- Q13: 아니다. preregistered performance gates를 통과하지 못했다.
- Q14: Mean=B2 LightGBM Tweedie, Q50/Q90=B3 LightGBM Quantile이다.
- Q15: NO. GPU-h facility-scale multiplication 호출은 0이다.
- Q16: NO. 이번 task는 새 grid science run을 승인하지 않는다.
