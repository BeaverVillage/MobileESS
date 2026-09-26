# CC4-v2.2 최종 검토

[고정 risk gate의 recall·달성 가능한 ceiling·비교 그림](GATE_DIAGNOSTIC_KO.md)과 [독립 재구성 감사](delivery_tools/AUDIT_README.md)를 함께 확인한다.

고정 선택: **C0**. expanding + 30일 recency weighting + daily refit + LightGBM을 유지했다. May는 이미 노출된 historical diagnostic이며 untouched confirmation이 아니다.

C0는 PR64의 raw refitted LightGBM과 동일하다. C1은 과거 high-risk residual의 유한표본 Q90 보정, C2는 burst 확률을 반영한 conditional tail quantile이다. TRAIN positive-hour Q95로 burst 크기 threshold를 고정했고, risk gate 0.10은 Q90의 tail mass 경계로 사전 지정했다. 전체 scaling/capping은 없다. high-risk 밖은 Q50/Q90 모두 C0와 동일하다.

| 구간 | 모델 | coverage | positive | burst | ratio | Q90 pinball |
|---|---|---:|---:|---:|---:|---:|
| DEVELOPMENT | C0 | 81.39% | 72.48% | 0.00% | 1.099 | 161.104 |
| DEVELOPMENT | C1 | 81.39% | 72.48% | 0.00% | 1.099 | 161.104 |
| DEVELOPMENT | C2 | 81.82% | 73.11% | 2.41% | 1.227 | 158.112 |
| CALIBRATION | C0 | 85.10% | 81.44% | 2.63% | 0.995 | 280.790 |
| CALIBRATION | C1 | 85.74% | 82.24% | 5.26% | 1.217 | 286.672 |
| CALIBRATION | C2 | 85.90% | 82.44% | 7.89% | 1.235 | 287.063 |
| EXPOSED_EVALUATION | C0 | 86.03% | 81.96% | 0.76% | 1.209 | 203.045 |
| EXPOSED_EVALUATION | C1 | 86.51% | 82.57% | 4.55% | 1.295 | 202.719 |
| EXPOSED_EVALUATION | C2 | 86.70% | 82.81% | 7.58% | 1.422 | 204.253 |
| MAY_HISTORICAL | C0 | 87.63% | 85.60% | 7.25% | 1.408 | 307.779 |
| MAY_HISTORICAL | C1 | 88.44% | 86.54% | 14.49% | 1.664 | 306.922 |
| MAY_HISTORICAL | C2 | 88.58% | 86.70% | 15.94% | 1.682 | 308.073 |

## Paired 95% CI

7개 관측 target-day circular block, 2,000회. 음수 pinball delta는 개선이다. burst delta는 양수가 개선이다. 1-day 결과도 CSV에 보존한다.

| 구간 | 모델 | 지표 | delta | 95% CI |
|---|---|---|---:|---|
| EXPOSED_EVALUATION | C1 | Q90_pinball | -0.3255 | [-1.9765, 0.9668] |
| EXPOSED_EVALUATION | C1 | burst_coverage | 0.0379 | [0.0079, 0.0735] |
| EXPOSED_EVALUATION | C2 | Q90_pinball | 1.2078 | [-2.1340, 4.3619] |
| EXPOSED_EVALUATION | C2 | burst_coverage | 0.0682 | [0.0207, 0.1214] |
| MAY_HISTORICAL | C1 | Q90_pinball | -0.8569 | [-4.4371, 2.8570] |
| MAY_HISTORICAL | C1 | burst_coverage | 0.0725 | [0.0455, 0.1136] |
| MAY_HISTORICAL | C2 | Q90_pinball | 0.2938 | [-3.2107, 4.0361] |
| MAY_HISTORICAL | C2 | burst_coverage | 0.0870 | [0.0395, 0.1342] |

## 판정

- TEMPORAL_POLICY_CHANGED = **FALSE**
- NEW_ARCHITECTURE_SEARCHED = **FALSE**
- PRODUCTION_REPLACEMENT_SUPPORTED = **FALSE**
- OPTIMIZER_INTEGRATION_READY = **FALSE**
- PRODUCTION_PROMOTED = **FALSE**

DEV/CAL에서 hard gate를 모두 만족하는 challenger가 없으면 C0를 유지한다. 평가 후 재선택하지 않는다. 모든 gate 원값은 GATES.csv, burst/risk strata와 gate recall은 별도 CSV에 있다. 과거 mature evaluation label의 prequential refit/residual 사용은 허용하지만 선택에는 사용하지 않는다.

훈련·residual exact membership과 PR64 temporal membership/weight 일치를 검증한다. 실제 ingestion 시각은 미인증이며 운영 인과성 인증이 아니다. 비교는 post-exposure model development이고 신규 untouched confirmation을 확보하지 않았다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 수정·실행 및 production promotion은 없다.
