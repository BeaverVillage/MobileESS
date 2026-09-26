# CC4-v2 시간별 미래 도착 GPU-work 예측: 최종 검토

독립 offline experiment v1. 과거 평가를 본 뒤 재학습·보정·대상 변경을 하지 않았다. 모든 수치는 GPU·h 원단위이며 seed별 점수를 동일 가중 평균했다.

## 1–3. 기존 H4의 의미와 90% 한계

기존 H4는 4시간 안에 원래 submit 시각이 들어오는 Job의 **전체 lifetime GPU-work** 합이다. 실행이 그 4시간 안에 끝난다는 뜻이 아니다. 따라서 장시간 Job들의 도착량은 그 창에서 처리 가능한 780 GPU × 4 h = 3120 GPU·h보다 클 수 있다.
PR #57의 2,511개 May 창 중 353개가 physical cap을 넘는다. 기존 actionable coverage는 2045/2511 = 81.4416567%, physical-cap oracle ceiling은 2158/2511 = 85.9418558%다. 기존 target과 cap을 함께 유지하면 어떤 예측기로도 90% actionable coverage를 달성할 수 없다. PR #59의 교체 근거 부족 판정은 변경하지 않는다.

## 4–5. 새 target과 인과 경계

고정 UTC+10 modeled local time의 D−1 18:00에 다음날 D 00:00–24:00의 24개 정시 bin을 예측한다. Lead는 6–29시간이다. 각 bin은 submit이 그 시간에 들어가는 frozen-eligible Job의 GPU 수 × 실제 runtime 전체 합이다. 모든 대상 Job은 발행 시점 이후 submit된다. 14:20 도착, 4 GPU, 2.5 h Job은 14시 bin에 10 GPU·h를 더하며 15시 이후에도 처리될 수 있다.
원시 Job archive의 전체 partition을 다시 읽어 frozen IDs와 GPU·h를 대조했다. 미래 runtime은 label에만 사용한다. 과거 workload는 완료되어 성숙한 경우만 feature에 들어가고 미성숙은 mask와 0으로 표시한다. 71개 lineage 중 불필요한 child15_position만 target_hour로 바꿨다. 실제 telemetry ingestion latency와 request 수정 이력은 원 authority에서 인증되지 않았으므로 event-time 기준의 인과 검증이다.

모델 파라미터·정규화·burst threshold는 TRAIN에서만 추정한다. DEVELOPMENT에서 설정과 모델을 고정하고, CALIBRATION의 시간별 잔차를 유한표본 순위로 보정했다. 26개 일별 residual이면 ceil(0.9×27)=25번째 값을 쓴다. 시간별 보정은 24시간 동시 보장이나 시계열 분포 무관 보장을 뜻하지 않는다. 보정은 signed additive이며 Q50 이하를 막는 순서 제약만 적용한다. 용량 상한이나 임의 배율은 없다.

## 정확한 분할

```text
TRAIN_DAYS = 167
DEVELOPMENT_DAYS = 58
CALIBRATION_DAYS = 26
EXPOSED_EVALUATION_DAYS = 88
MAY_HISTORICAL_DAYS = 31
NO_UNTOUCHED_CONFIRMATION = TRUE
```

PR #59와 day membership은 정확히 대조하며 모든 24시간은 같은 split에 속한다. PURGE와 기존 제외일을 보존했다. 전체 날짜와 성숙 시각은 각 MEMBERSHIP.csv, 변경 여부는 SPLIT_MEMBERSHIP_DIFF.csv에 있다. May는 untouched holdout이 아니다.

## 6. Q50/Q90와 sharpness

| 기간 | 모델 | Q50 coverage | Q90 coverage | 보정오차 | Q90 pinball | Q50 pinball | Q50 MAE | Q50 RMSE | 요구량 비율 | 초과량 비율 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EXPOSED_EVALUATION | DEEPAR | 41.9665% | 92.1875% | 0.02187 | 228.192 | 152.541 | 305.082 | 1380.220 | 3.300 | 2.787 |
| EXPOSED_EVALUATION | LGBM | 41.7140% | 92.6610% | 0.02661 | 225.767 | 153.416 | 306.832 | 1381.302 | 3.282 | 2.763 |
| EXPOSED_EVALUATION | SEASONAL | 38.9205% | 91.8087% | 0.01809 | 229.578 | 154.312 | 308.624 | 1380.968 | 3.267 | 2.761 |
| EXPOSED_EVALUATION | TFT | 46.5909% | 91.5562% | 0.01556 | 224.594 | 155.706 | 311.411 | 1383.455 | 3.139 | 2.631 |
| MAY_HISTORICAL | DEEPAR | 39.9642% | 91.1290% | 0.01129 | 322.139 | 227.665 | 455.330 | 2605.264 | 2.820 | 2.319 |
| MAY_HISTORICAL | LGBM | 35.0806% | 89.3817% | 0.00618 | 310.683 | 228.079 | 456.157 | 2607.472 | 2.455 | 1.967 |
| MAY_HISTORICAL | SEASONAL | 32.7957% | 86.6935% | 0.03306 | 318.755 | 228.751 | 457.501 | 2608.269 | 2.218 | 1.770 |
| MAY_HISTORICAL | TFT | 42.1595% | 89.7849% | 0.00341 | 310.214 | 231.738 | 463.477 | 2609.989 | 2.357 | 1.878 |

Q50는 별도 보정을 하지 않았다. raw/calibrated와 모든 seed의 결과를 MODEL_METRICS.csv에 함께 보존한다. Coverage는 정확한 actual ≤ prediction이며 zero를 제외하지 않는다.

![고정 평가 결과 비교](FORECAST_COMPARISON.png)

## 7–8. 모델 선택과 day-block uncertainty

DEVELOPMENT에서 사전 고정한 모델은 **DEEPAR**다. 평가에서 다른 모델의 일부 지표가 더 좋아도 모델을 다시 선택하지 않았다. TFT는 PR #59의 소형 gated variable selection/LSTM/causal attention 구현이고 DeepAR는 hurdle-lognormal recurrent 구현이다. 원 논문의 완전한 대형 benchmark 구현이라는 주장은 하지 않는다.
3개 seed를 독립 day sample처럼 취급하지 않았다. 동일 날짜에서 seed 점수를 평균하고, 두 모델에 동일한 7일 block을 적용한 2,000회 paired bootstrap으로 불확실성을 계산했다. 음수 delta가 개선이며 CI가 0을 포함하면 우위를 주장하지 않는다.

**평가의 Q90 pinball 점추정은 TFT가 두 기간 모두 가장 낮지만, LightGBM 대비 통계적으로 입증된 우위는 없다.** TFT의 개선은 Dec–Feb 약 0.52%, May 약 0.15%이며 아래 두 신뢰구간이 모두 0을 포함한다. 사전 선택된 DeepAR는 May pinball이 LightGBM보다 약 3.69% 높고 그 악화의 신뢰구간은 0보다 크다. 따라서 확정적인 우승 모델을 선언하거나 TFT로 재선택하지 않는다.

위 표의 보정오차는 seed별 절대 보정오차의 평균이다. 아래 bootstrap 보정오차는 `abs(seed/day 평균 coverage−0.90)`의 차이다. 절댓값이 비선형이므로 두 요약을 서로 동일한 추정량으로 해석하지 않는다. LightGBM은 무작위 subsampling이 없는 결정적 설정이므로 세 seed의 동일 결과를 독립 반복의 증거로 세지 않는다.

| 기간 | 후보 vs LightGBM | 지표 | Δ | 95% CI |
|---|---|---|---:|---|
| EXPOSED_EVALUATION | TFT | Q90_pinball | -1.17283 | [-3.72591, 1.24196] |
| EXPOSED_EVALUATION | TFT | calibration_error | -0.01105 | [-0.01957, -0.00205] |
| EXPOSED_EVALUATION | TFT | requirement_ratio | -0.14280 | [-0.26728, -0.05731] |
| EXPOSED_EVALUATION | DEEPAR | Q90_pinball | 2.42526 | [-1.37332, 5.99998] |
| EXPOSED_EVALUATION | DEEPAR | calibration_error | -0.00473 | [-0.01199, 0.00363] |
| EXPOSED_EVALUATION | DEEPAR | requirement_ratio | 0.01841 | [-0.12021, 0.13497] |
| MAY_HISTORICAL | TFT | Q90_pinball | -0.46908 | [-5.25920, 4.30954] |
| MAY_HISTORICAL | TFT | calibration_error | -0.00403 | [-0.01434, 0.00717] |
| MAY_HISTORICAL | TFT | requirement_ratio | -0.09819 | [-0.20218, -0.03701] |
| MAY_HISTORICAL | DEEPAR | Q90_pinball | 11.45580 | [7.57779, 16.44556] |
| MAY_HISTORICAL | DEEPAR | calibration_error | 0.00511 | [-0.02581, 0.01927] |
| MAY_HISTORICAL | DEEPAR | requirement_ratio | 0.36464 | [0.26075, 0.53588] |

## 9–11. 과대예측, positive/burst, 기간 일관성

Burst는 TRAIN의 positive hourly GPU-work Q95=860.353222보다 큰 시간으로 미리 정의했다. 선택 모델 DEEPAR의 다음 수치는 모든 seed 평균이다.

| 기간 | regime | Q90 coverage | Q90 pinball |
|---|---|---:|---:|
| EXPOSED_EVALUATION | burst | 31.8182% | 2186.884 |
| EXPOSED_EVALUATION | positive | 89.9083% | 277.949 |
| EXPOSED_EVALUATION | zero | 100.0000% | 57.641 |
| MAY_HISTORICAL | burst | 38.6473% | 2290.334 |
| MAY_HISTORICAL | positive | 89.6714% | 365.230 |
| MAY_HISTORICAL | zero | 100.0000% | 59.895 |

사전 등록한 품질 gate의 실제 결과: `{"integrity": true, "all_registered_seed_runs_complete": true, "calibration_band_both_periods": false, "all_seed_band": true, "sharpness_vs_seasonal": false, "positive_burst_robustness": false}`.
88–92% coverage, seed 안정성, seasonal 대비 pinball·요구량, positive/burst 강건성을 **두 평가기간 모두** 확인한다. 98–100% coverage나 큰 요구량은 성공으로 간주하지 않는다. 상세 시간대·lead별 편차는 HOUR_OF_DAY_METRICS.csv와 LEAD_TIME_METRICS.csv에 모두 보존했다. 이 gate가 실패하면 약 90%의 전반적인 성공을 주장하지 않는다.

DeepAR의 Dec–Feb 92.1875%는 등록 범위 상단보다 **0.1875 percentage point** 높다. 26일 calibration의 거친 유한표본 순위를 고려하면 이 작은 초과만으로 예측기를 부정할 수 없다. 더 큰 문제는 두 기간 모두 큰 요구량, 낮은 burst coverage, May pinball 악화가 함께 나타난다는 점이다. 전체 coverage가 약 90%라는 관찰 자체는 유효하나 sharpness와 조건별 강건성을 포함하는 성공 판정은 실패다. Burst를 실제 workload로 정의했으므로 marginal Q90가 그 부분집합에서 반드시 90%여야 한다는 주장은 하지 않는다. 등록된 최소 강건성 기준과 비교한 결과다.

| 기간 | 6–11 h coverage | 12–17 h | 18–23 h | 24–29 h | 24개 개별 시각 coverage 범위 |
|---|---:|---:|---:|---:|---:|
| Dec–Feb | 91.8561% | 93.2449% | 92.7399% | 90.9091% | 78.7879–100% |
| May | 90.6810% | 91.9355% | 92.2939% | 89.6057% | 73.1183–100% |

전체/lead 묶음의 약 90%가 모든 개별 시간대의 안정적 90%를 의미하지 않는다. Q50 coverage도 약 40%로 낮아 중앙 예측의 보정이 완전하다고 볼 수 없다.

## 12. Production 교체 근거

Q90 보정·sharpness·강건성 지지: **False**. 교체 지지: **False**. Target의 과학적 단위 정합성과 ML의 예측 성능은 별개다. 상한 제거는 기존 인위적 ceiling을 제거하지만 좋은 보정과 정확도를 보장하지 않는다. 이 연구만으로 운영 reserve adequacy 90%를 주장할 수 없다. Production 승격은 수행하지 않았다.

**최종 interface 판단:** 도착한 lifetime-work와 optimizer의 시간별 service/headroom을 분리하므로 새 정의가 역할·단위 정합성 면에서 적절하다. 85.94% ceiling 없이 약 90% forecast coverage가 실제 관찰되었다. 그러나 이는 기존 H4의 81.44% operational/actionable 수치와 동일한 target/분모의 성능 향상 비교가 아니며, 강건하고 예리한 Q90 예측기를 확보했다는 결론도 아니다. 기존 production을 교체하거나 optimizer 통합을 진행할 근거는 아직 충분하지 않다.

## 13. 다음 optimizer/P2 연결 — 문서만

**ML predicts future workload. Optimizer determines headroom.**
차후 optimizer가 H_h(x)=C_h−L_h_known(x)를 정하고, 0≤S_h_future≤H_h(x)Δt로 미래 service를 배분해야 한다. Arrival workload를 같은 시간의 service 의무로 놓지 않아야 한다. 시간 간 누적 도착·service·carry-out과 실제 deadline authority를 정의한 뒤 누적/마감 기반 reserve 제약을 설계해야 한다. 시간별 marginal Q90의 단순 합은 하루 profile의 joint Q90가 아니므로 dependence/scenario 또는 별도 joint calibration 검증이 필요하다. 그 이후 P2 trade-off와 실제 미래 Job replay를 검증해야 한다. 이번 작업에서 optimizer, P2, scheduler, MESS, Fresh/Actual, OpenDSS, Gurobi를 변경하거나 실행하지 않았다.

```text
CC4_V2_FORECAST_TARGET_VALID = TRUE
Q90_90PCT_CALIBRATION_SUPPORTED = FALSE
MODEL_REPLACEMENT_SUPPORTED = FALSE
OPTIMIZER_INTEGRATION_READY = FALSE
PRODUCTION_MODEL_PROMOTED = FALSE
OPTIMIZER_CHANGED = FALSE
GRID_CAMPAIGN_EXECUTIONS = 0
NO_UNTOUCHED_CONFIRMATION = TRUE
```
