# V27M SAFE-Flex R1 최종 과학 검토

RESULT CLASSIFICATION: `V27M_SAFE_R1_RESIDUAL_SIGNAL_FAIL`

## 핵심 결론

의무 Phase-1 residual 신호 게이트가 실패했으므로 SAFE-Flex R1 개발을 즉시 중단했다. R4 state+running residual 점수는 `19.462447`로 BL2 `15.243233`보다 나빴고, fold 승리는 `1/5`였다. 7일 block bootstrap 차이는 `4.219214`, CI95 `[0.231542, 10.236256]`이다.

## V26 실패 위치

- Pending prevalence: 양성 `78828`, 음성 `151`, 양성률 `99.808810%`.
- 높은 AUPRC와 음의 Brier skill은 극단적 양성 prevalence와 더 강한 climatology 기준선이 동시에 만든 현상이다.
- 기존 보정 참조의 `79.72%`가 0인데도 모든 2,880셀에 동일 shift를 적용해 전 집합이 붕괴했다.
- 2,880차원 보정 호출은 0이며, aggregate 96-slot 보정은 gate 실패로 실행하지 않았다.

## 집계 참조와 BL2 재현

- 225일 × 96-slot L/U가 비음수·단조·순서 조건을 모두 통과했다.
- BL2 V26 원 metric 점수 `15.243233180615933`를 오차 0으로 재현했다.
- residual training의 in-sample base 행은 0이다.
- Running IBS 개선 `17.415203%`도 정확히 재현했다.

## Residual audit

| model | score | relative improvement | fold wins | residual R2 | preprojection nonempty |
|---|---:|---:|---:|---:|---:|
| R0_ZERO_CORRECTION | 15.243233 | 0.000000 | 0 | -0.173290 | 1.000000 |
| R1_ELASTICNET_RESIDUAL | 14.993932 | 0.016355 | 3 | -14.017382 | 0.324503 |
| R2_BASE_ONLY_LGBM_RESIDUAL | 19.121146 | -0.254402 | 1 | -0.411964 | 0.390728 |
| R3_STATE_LGBM_RESIDUAL | 19.703961 | -0.292637 | 3 | -0.300310 | 0.496689 |
| R4_STATE_RUNNING_LGBM_RESIDUAL | 19.462447 | -0.276793 | 1 | -0.265710 | 0.417219 |
| R5_SMALL_MLP_RESIDUAL | 14.355195 | 0.058258 | 1 | -2.251424 | 0.470199 |

ElasticNet은 pooled 1.64% 개선이었지만 3/5 fold에 그쳤다. 작은 MLP는 pooled 점수만 강한 목표 아래였으나 1/5 fold 승리와 낮은 사전투영 nonempty율 때문에 secondary diagnostic일 뿐이다. Primary R4는 네 개 신호 게이트를 모두 실패했다.

## 중단된 후속 단계

HPO, functional basis, full R1, 물리 투영, BL2S, aggregate calibration, tier/latency allocation, IT power mapping, novelty 갱신, April open, bundle 생성은 실행하지 않았다. 결과 기반 architecture escalation도 0이다.

## 생산 권위

SAFE-R1은 제안 모델 또는 production 모델로 승인되지 않았다. Daily mean은 B2 LightGBM Tweedie, Q50/Q90은 B3 LightGBM Quantile을 유지하며 flexibility envelope는 BL2 conventional aggregate fallback을 유지한다.

## 방화벽

GPU-h facility MW multiplication, PUE, beta_AIDC, OpenDSS, B0–B3 최종 science, grid objective read는 모두 0이다. April 데이터도 열지 않았다. 새 grid science는 승인되지 않았다.

## Q1–Q18

- Q1: Pending labels were 78,828 positive versus 151 negative; AUPRC was prevalence-dominated while learned probabilities were worse than the near-perfect climatology Brier baseline.
- Q2: The scalar trajectory shift was broadcast to 2,880 cells despite 79.72% zero reference support, so two-sided tightening immediately made L_safe exceed U_safe.
- Q3: YES. The 2,880-dimensional calibration path was removed and called zero times.
- Q4: YES. BL2 reproduced exactly at 15.243233180615933 with error 0.
- Q5: NO under the preregistered R4 gate.
- Q6: 1/5 folds.
- Q7: 19.462447113445744.
- Q8: NO.
- Q9: NO.
- Q10: NOT EVALUATED; BL2S belongs to post-gate development, which was prohibited after failure.
- Q11: YES, zero residual is algebraically identical to BL2 to 1e-12.
- Q12: NOT EVALUATED; aggregate calibration was not authorized.
- Q13: NOT EVALUATED; calibrated sets were not constructed.
- Q14: NOT EVALUATED.
- Q15: NOT EVALUATED; downstream allocation was not run.
- Q16: NO.
- Q17: NO.
- Q18: NO.
