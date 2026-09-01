# V26M SAFE-Flex 최종 검토

## RESULT CLASSIFICATION

`V26M_SAFE_CALIBRATION_FAIL`

## READY FLAGS

`SAFE_FLEX_PROPOSED_MODEL_ACCEPTED=false`, `SAFE_FLEX_PRODUCTION_READY=false`, `SAFE_FLEX_BUNDLE_V5_READY=false`, `NEW_GRID_SCIENCE_RUN_READY=false`, `FINAL_GRID_SCIENCE_AUTHORIZED=false`

## 1. V25 forensic

- canonical field: `SUMMARY_MAPPING_DEFECT_ONLY` — 0.890250은 quantile 행을 포함한 잘못된 전체 최소화였다.
- April Q50: `BASE_RECONCILIATION_DEFECT_FOUND` — OOF 15일에서 BR-A가 양의 raw Q50을 0으로 붕괴시켰다.
- V25 historical artifact 수정: 0.

## 2. Causal state reconstruction

- label: `EVENT_CENSORED_RECONSTRUCTED_STATE`; exact historical squeue: NO.
- 225일, 지원 비율 99.99986194%; unsupported=0, 누적 ambiguous=45.
- running/pending/done은 cutoff 이전 SUBMIT/START/END event 발생 여부로만 복원했다. 미래 timestamp 숫자 feature read=0.

## 3. Historical capacity

- 2024-08=520 GPU, 2024-09=520 GPU, 2024-10=528 GPU, 2024-11=520 GPU, 2024-12=616 GPU, 2025-01=616 GPU, 2025-02=616 GPU, 2025-03=620 GPU
- boundary는 `OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY`; source-infeasible workload는 clip하지 않았다.
- 528 GPU는 training에 사용하지 않았고, rejected SAFE에 equivalent mapping도 실행하지 않았다.

## 4. Observable-state share

- rho_K_total: aggregate=0.65714225, mean=0.58554189, P50=0.70767317, P95=0.99923073
- rho_K_schedulable: aggregate=0.46892327, mean=0.30399504, P50=0.17477484, P95=0.92535108
- rho_G aggregate=0.01950018; rho_N aggregate=0.32335757.

## 5. Oracle ceiling

- O0 LEGACY_INNOVATION_ONLY: score=0.820735, coverage=0.774834, shortfall=46370.169 GPU-h
- O1 ORACLE_PRE_CUTOFF_PENDING_SERVICE: score=0.395070, coverage=0.900662, shortfall=57762.891 GPU-h
- O2 ORACLE_PRE_CUTOFF_ALL_FUTURE_SERVICE: score=0.317570, coverage=0.953642, shortfall=87162.715 GPU-h
- O3 ORACLE_INNOVATION: score=0.666868, coverage=0.125828, shortfall=0.000 GPU-h
- O4 FULL_ORACLE: score=0.000000, coverage=1.000000, shortfall=0.000 GPU-h

O1은 primary score를 51.86383934% 개선했고 state/share 조건도 통과해 `COMMITTED_STATE_VALUE_READY=true`다. shortfall은 개선되지 않았다.

## 6. Novelty

`PARTIAL_OVERLAP_DISTINCT_COMBINATION`; near duplicate=NO; WORLD_FIRST=`NOT_YET`. 가장 가까운 queue-aware data-center regulation 연구에도 동일한 residual-survival/K-G-N/conformal-inner-set 결합은 없었다.

## 7. Running residual-service prediction

- SAFE discrete hazard: IBS=0.138384, NLL=4.004496, Q50 MAE=5.587799 h, Q90 coverage=0.892530.
- SR1 대비 IBS 개선 17.41520319%; SR3 escalation은 하지 않았다.

## 8. Pending-job prediction

- pooled AUPRC=0.996935, Brier=0.00194100, Brier skill=-5.747346 (FAIL).
- conditional service mean WAPE=0.947773; future exact start time은 예측하지 않았다.

## 9. Innovation

- N authority는 B2 Tweedie mean + raw B3 Q50/Q90을 유지했다. weekday-factorized pooled WAPE 우위만으로 authority를 바꾸지 않았다.
- G share=1.950018%로 1%를 넘어 small LightGBM Tweedie/quantile을 사용했다.

## 10. Scenario model

- D2 day-level bootstrap tuple coupling; development 512/final 4096, seeds 20260901–20260903.
- scrambled Sobol 재현성 PASS, negative workload=0, mass identity PASS.

## 11. Service-set projector

- 96×6×5 EDF projector가 release/deadline/capacity/backlog를 명시한다.
- random 100 cases PASS; overload는 `DEADLINE_INFEASIBLE`; hidden shedding=0; mass conservation PASS.

## 12. Flexibility envelope

- BL0_STATIC_FLEXIBILITY_RATIO: score=11.968801, coverage=0.000000, nonempty=1.000000, width=18630.419
- BL1_LEGACY_B2_B3: score=31.953840, coverage=0.218543, nonempty=0.006623, width=760.232
- BL2_DIRECT_LIGHTGBM_ENVELOPE: score=15.243233, coverage=0.000000, nonempty=1.000000, width=41627.250
- BL3_DIRECT_QUANTILE_LIGHTGBM: score=19.346139, coverage=0.033113, nonempty=0.000000, width=9121.706
- BL4_OBSERVABLE_STATE_POINT_RUNTIME: score=20.921439, coverage=0.000000, nonempty=1.000000, width=47286.065
- BL5_SURVIVAL_ONLY_NO_INNOVATION_UPDATE: score=20.395356, coverage=0.125828, nonempty=0.000000, width=4165.004
- FULL_SAFE_FLEX_RAW: score=43.400202, coverage=0.145695, nonempty=0.000000, width=4859.451

Runtime은 개별 모델 단위로 계측하지 않아 `NOT_INSTRUMENTED_LIMITATION`이다.

## 13. SAFE calibration

- raw SAFE score=43.400202, raw nonempty=0.000000.
- calibrated simultaneous coverage=1.0이나 nonempty=0.0, width=0.0이다. 모든 set이 empty이므로 coverage 성공으로 인정하지 않았다.

## 14. Ablation

A0–A12는 `V26M_ABLATION_RESULTS.csv`에 동일 평가 universe로 기록했다. running locked 단계는 flexible descriptor가 같음을 명시했고 A9는 diagnostic only다.

## 15. Statistical significance

SAFE-direct raw score 차이=28.156968; 7일 block bootstrap 10,000회 CI95=[15.448737, 42.852163]. SAFE가 유의하게 나쁘다.

## 16. April post-freeze

7개 지정일을 `APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST`로만 열었다. fit/calibration/selection/architecture change=0. April 관측 lower-bound는 154 nodes/616 GPUs다.

## 17. Equivalent 528-GPU diagnostic

`NOT_RUN_SAFE_NOT_SELECTED`. IT-side only 정책을 유지했으며 PUE/PCC/0.5288 MW multiplication은 0이다.

## 18. Limitations

- exact squeue 없음; event-censored state만 존재.
- running preemption/checkpointability를 가정하지 않음.
- envelope는 engineering feasibility label이며 measured Kestrel flexibility가 아님.
- untouched locked test 없음; site GPU allocation authority 없음.
- partial-node power는 GPU-board-only lower bound.
- pending 식별 실패와 tier/latency support mismatch 때문에 calibrated set이 비었다.

## 19. Production authority

SAFE는 거절됐다. V25 B2/B3 fallback authority를 그대로 유지한다.

## 20. Artifacts + SHA

56개 artifact의 SHA256은 `V26M_ARTIFACT_SHA256.json`에 기록했다.

## 21. Git

- branch: `codex/v26m-safe-flex`
- starting HEAD: `377f147f007151c53ebbe8ca3fb2cdd616bc3e5b`
- pre-final HEAD: `91230f74be3c1a4e1dc09e83a6f1a7cb6ce39369`
- final commit title: `Complete V26M SAFE-Flex scientific evaluation`
- auto merge: NO

## 22. Q1–Q20 핵심 답변

- Q1 YES summary mapping defect. Q2 BR-A collapse mechanism confirmed. Q3 exact squeue NO.
- Q4 observable K=65.71422500%. Q5 schedulable K=46.89232711%.
- Q6 gap material YES. Q7 oracle value YES. Q8 information-value gate PASS. Q9 near duplicate NO.
- Q10 running survival YES. Q11 pending positive Brier skill NO. Q12 B2/B3 + G LightGBM.
- Q13 nominal coverage 100% but invalid empty set. Q14 capture=0. Q15 meaningful shortfall reduction=0.
- Q16 direct LightGBM 승리, Q17 direct quantile 승리. Q18 SAFE accepted=NO.
- Q19 facility MW×GPU-h=NO. Q20 new grid science=NO.

## 핵심 수치 요약

- event-state 지원 비율: 99.99986194%
- schedulable-known 질량 비율: 46.89232711%
- O1 oracle primary score 개선: 51.86383934%
- running hazard IBS 개선: 17.41520319%
- pending Brier skill: -5.747346
- SAFE raw boundary score: 43.400202
- direct LightGBM score: 15.243233
- 7일 block-bootstrap SAFE-direct CI95: [15.448737, 42.852163]
- calibrated coverage: 100%, nonempty rate: 0%

정보가치와 running survival 개선은 확인됐지만 pending 확률이 base-rate를 이기지 못했고, trajectory calibration은 모든 set을 비워서만 containment를 달성했습니다. 따라서 SAFE-Flex는 제안 모델이나 production authority로 승인되지 않았으며 V25 B2/B3 fallback이 유지됩니다.

April 7일은 freeze 이후 진단으로만 열었고 fit/calibration/selection 호출은 모두 0입니다. 528 GPU equivalent mapping, PUE/PCC/facility scale, OpenDSS, B0–B3 grid science는 실행하지 않았습니다.

## 보존 및 권한

- V17–V25 protected files unchanged: True
- raw source unchanged: True
- SAFE_FLEX_PRODUCTION_READY: false
- NEW_GRID_SCIENCE_RUN_READY: false
- FINAL_GRID_SCIENCE_AUTHORIZED: false
