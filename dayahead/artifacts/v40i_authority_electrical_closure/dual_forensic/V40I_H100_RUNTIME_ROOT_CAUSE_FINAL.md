# H100-standby COMPLETED/FAILED forensic 최종

COMPLETED H100-standby 2,562개의 저장된 point prediction은 체계적으로 짧았다. 과소예측률 64.1296%, 평균(actual−point) +7064.205s, 중앙값 +332.336s, MAE 11006.651s, RMSE 19652.901s다. 종료 상태로 나눈 기존 예측 평가이며 COMPLETED-only 모델을 학습하지 않았다.

| COMPLETED H100 layer | Underprediction | Coverage |
|---|---:|---:|
| point | 64.1296% | 35.8704% |
| q_only | 32.9820% | 67.0180% |
| effective | 32.6698% | 67.3302% |

ALL H100의 q-only→ceil 과소예측률 감소는 0.215227 percentage points다. 28.38%/28.17%는 ALL H100이며 pooled population이나 COMPLETED-only 수치가 아니다. 15MIN_CEIL_PRIMARY_CAUSE=NO.

기존 pooled q=5576.44921875s; COMPLETED diagnostic q90=29813.46171875s, q95=37685.34094238s. q90은 pooled q의 5.3463배이며 24237.013s 더 크다. Pooled q는 이 subgroup의 약 67.0180% empirical percentile이다. 새 q는 적용·선택하지 않았다.

Training H100 87,319개 중 FAILED 54,057개(중앙값 23s), COMPLETED 28,394개다. 검증 FAILED 675/3,717, COMPLETED 2,562/3,717로 population mix가 다르다. TRAIN_DEPLOYMENT_DISTRIBUTION_MISMATCH는 이 관측 범위에서 CONFIRMED다. FAILED가 개별 fitted tree를 얼마나 짧게 만들었는지는 PLAUSIBLE_NOT_PROVEN이다. Final status는 D-1에 알 수 없으므로 production feature로 금지한다.

COMPLETED runtime: skew=0.721, excess kurtosis=-0.054, P95/median=4.650. Positive residual: skew=3.071, excess kurtosis=12.784, P95/median=113.395. Runtime은 requested-walltime/account regime이 분리되는 MULTIMODAL_EVIDENCE, residual은 경험적 heavy right tail이다. Formal asymptotic heavy-tail distribution은 입증하지 않았다.

H100/standby identity는 partition/QoS에 있고 GPU·walltime도 feature다. SUBGROUP_VISIBLE_BUT_MODEL_MISFIT으로 판정한다. 명시적 submit-hour/day, per-user runtime rolling statistics, queue state, final outcome은 point feature에 없다. 최종 encoder/tree state가 보존되지 않아 정확한 leaf attribution은 불가능하다.

May +29 runtime 구간 28577–43227s 안의 학습 표본은 ALL 1,107, COMPLETED 691개로 runtime support는 WELL_SUPPORTED다. 다만 같은 9-feature 조합은 0개다. Walltime을 제외한 같은 8-feature 조합 1,501개는 모두 48h 요청이며 May cohort는 12h 요청이다. 따라서 runtime tail support와 조건부 feature-combination support를 분리한다.

29 UID는 broad preMay COMPLETED runtime의 56.5964%–60.3825%, point residual의 74.0047%–88.0952% 위치다. {'NORMAL_HISTORICAL_TAIL': 29}. 새 runtime 범위가 출현했다고 볼 근거는 없다.

다음 연구 방향은 HYBRID_PREDICTION_AND_ROBUST_SCHEDULING이다. Point predictor의 subgroup misfit를 조사하고, causal subgroup upper bound와 robust envelope/reserve를 독립 pre-May 시간 블록에서 비교한다. FAILED 제거, COMPLETED-only fitting, 새 q 선정은 수행하지 않았다. May-01은 이미 원인 분석에 사용했으므로 새 방법의 untouched blind test라고 주장할 수 없다. May의 fitting/calibration/tuning 사용은 계속 금지한다.
