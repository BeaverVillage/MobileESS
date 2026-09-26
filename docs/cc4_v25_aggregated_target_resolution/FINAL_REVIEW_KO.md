# CC4-v2.5 최종 검토 — Target-resolution comparison

DEV/CAL에서 동결한 primary resolution은 **H1**이다. 평가 후 재선택하지 않았다. 지원되는 사전 고정 family는 **없음**이다. May는 exposed historical diagnostic이며 tuning 또는 untouched confirmation에 사용하지 않았다.

## 무엇을 고정하고 비교했는가

PR70 C0를 만든 PR64 raw refitted H1 LightGBM Q50/Q90을 그대로 사용했다. 동일한 원시 hourly future-arrival GPUh에서 H3/H6는 자정 기준 non-overlapping block, CUM은 다음날 1..24시간 prefix이다. 모든 target은 완료된 총 GPU·h를 submit 시간에 귀속한다. GPU 용량·실행시간 cap이나 신규 exclusion은 없다.

기존 71개 feature의 block-end 행을 그대로 쓴다. history/seasonal/calendar/maturity 값의 pooling이나 새로운 feature를 추가하지 않았다. Legacy horizon_hours=1 및 window_start_slot은 원 hourly anchor의 값이고, 실제 target 구간은 별도 start/end/duration metadata다. 이 고정된 anchor 방식에서 direct model의 개선이 없다는 결과를 모든 가능한 aggregated feature 설계의 실패로 일반화하지 않는다.

Expanding history, 30일 half-life, daily refit, full-day label_matured_at<issue와 과거 issue/non-PURGE membership을 동일하게 유지했다. 짧은 block도 label을 더 일찍 학습에 넣지 않는다. LightGBM의 15 leaves/400 trees/lr0.03/min_child50/seed20260924 및 log1p target 변환을 고정했다. Target observation별 기존 day weight를 그대로 주므로 H3/H6의 하루 학습 행 수 감소는 target-resolution 변경의 일부다.

DIRECT와 AGGREGATED_H1을 비교한다. 후자는 frozen hourly Q50/Q90의 단순 합이며, 합산한 Q90이 aggregate의 실제 Q90임을 보장하지 않는다. H1의 두 method 행은 같은 frozen 예측이다. CUM은 기존 nonnegative/noncrossing quantile support만 적용한 marginal prefix 예측이며, 새로운 monotone projection은 적용하지 않았다.

## 단위·정규화·mass conservation

공통 정규화 분모는 eligible TRAIN의 hourly 평균 **148.672830242 GPUh**이다. normalized pinball은 각 target의 pinball을 target duration으로 나눈 후 day/output에 동일 가중 평균을 내고 이 분모로 나눈 값이다. CUM은 각 prefix의 시간당 손실을 동일 가중 평균한다. 모든 resolution과 기간에서 같은 TRAIN scale을 사용한다.

H1/H3/H6 requirement ratio는 비중복 block 합의 Q90/actual이다. CUM의 primary ratio는 24h terminal Q90/actual이며 각 prefix ratio를 별도 보고한다. Prefix들의 합을 daily mass 또는 예약량으로 해석하지 않는다. 원시 29 partitions 전체를 다시 읽어 eligible population과 10,632개 hourly label이 원 authority와 정확히 같음을 확인했다. H3/H6 합, CUM terminal 및 first difference의 질량 보존은 RAW_TARGET_AUDIT.json과 DAILY_TARGET_AUDIT.csv에 있다. 부동소수점 오차만 허용했고 label은 변경하지 않았다.

High-load는 TRAIN positive target의 Q95 초과로 정의한다. H1/H3/H6는 resolution별 pooled threshold, CUM은 prefix별 threshold를 사용한다. 따라서 resolution 간 high-load strata는 다른 사건이다. Cross-resolution 비교는 target 적합성 비교이며 hourly predictor superiority의 근거가 아니다.

## 사전 동결 선택 규칙

DEV/CAL 각각 requirement ratio<2, high-load coverage가 H1보다 최소 +5pp, normalized Q90 pinball≤H1을 hard gate로 두었다. Overall88–92%는 선호 기준이다. 이전 task의 positive85%/burst60%를 새 hard gate로 가져오지 않았다. DIRECT와 AGGREGATED_H1 중 각 family의 method를 동결했으며, eligible family 중 primary를 동결했다. 단순 집계만으로 효과가 나도 target-resolution 연구 근거가 될 수 있고, direct 학습 효과는 별도 같은-target 비교로 판단한다.

| resolution | frozen method | DEV/CAL eligible |
|---|---|---|
| H3 | AGGREGATED_H1 | False |
| H6 | AGGREGATED_H1 | False |
| CUM | DIRECT | False |

## 모델/target 결과

| role | target | method | Q90 coverage | calibration error | normalized Q90 pinball | primary ratio | high-load coverage | positive coverage |
|---|---|---|---:|---:|---:|---:|---:|---:|
| DEVELOPMENT | H1 | AGGREGATED_H1 | 81.39% | 0.0861 | 1.083613 | 1.099 | 0.00% | 72.48% |
| DEVELOPMENT | H3 | AGGREGATED_H1 | 75.43% | 0.1457 | 0.836081 | 1.099 | 2.78% | 69.92% |
| DEVELOPMENT | H6 | AGGREGATED_H1 | 73.28% | 0.1672 | 0.719219 | 1.099 | 4.17% | 69.00% |
| DEVELOPMENT | CUM | AGGREGATED_H1 | 66.24% | 0.2376 | 0.694495 | 1.099 | 1.10% | 61.66% |
| DEVELOPMENT | H1 | DIRECT | 81.39% | 0.0861 | 1.083613 | 1.099 | 0.00% | 72.48% |
| DEVELOPMENT | H3 | DIRECT | 78.02% | 0.1198 | 0.818444 | 1.228 | 2.78% | 73.09% |
| DEVELOPMENT | H6 | DIRECT | 72.84% | 0.1716 | 0.747716 | 1.093 | 4.17% | 68.50% |
| DEVELOPMENT | CUM | DIRECT | 60.99% | 0.2901 | 0.815193 | 0.742 | 1.10% | 55.71% |
| CALIBRATION | H1 | AGGREGATED_H1 | 85.10% | 0.0490 | 1.888643 | 0.995 | 2.63% | 81.44% |
| CALIBRATION | H3 | AGGREGATED_H1 | 84.13% | 0.0587 | 1.640364 | 0.995 | 6.67% | 83.74% |
| CALIBRATION | H6 | AGGREGATED_H1 | 84.62% | 0.0538 | 1.460400 | 0.995 | 8.33% | 84.62% |
| CALIBRATION | CUM | AGGREGATED_H1 | 75.00% | 0.1500 | 1.929241 | 0.995 | 10.81% | 74.80% |
| CALIBRATION | H1 | DIRECT | 85.10% | 0.0490 | 1.888643 | 0.995 | 2.63% | 81.44% |
| CALIBRATION | H3 | DIRECT | 83.17% | 0.0683 | 1.662597 | 0.939 | 0.00% | 82.76% |
| CALIBRATION | H6 | DIRECT | 76.92% | 0.1308 | 1.516470 | 0.801 | 0.00% | 76.92% |
| CALIBRATION | CUM | DIRECT | 71.79% | 0.1821 | 1.827072 | 0.705 | 4.50% | 71.57% |
| EXPOSED_EVALUATION | H1 | AGGREGATED_H1 | 86.03% | 0.0397 | 1.365717 | 1.209 | 0.76% | 81.96% |
| EXPOSED_EVALUATION | H3 | AGGREGATED_H1 | 83.10% | 0.0690 | 1.100266 | 1.209 | 0.00% | 80.65% |
| EXPOSED_EVALUATION | H6 | AGGREGATED_H1 | 79.26% | 0.1074 | 0.942869 | 1.209 | 0.00% | 77.33% |
| EXPOSED_EVALUATION | CUM | AGGREGATED_H1 | 76.80% | 0.1320 | 0.965996 | 1.209 | 7.14% | 74.92% |
| EXPOSED_EVALUATION | H1 | DIRECT | 86.03% | 0.0397 | 1.365717 | 1.209 | 0.76% | 81.96% |
| EXPOSED_EVALUATION | H3 | DIRECT | 82.95% | 0.0705 | 1.129727 | 1.333 | 4.48% | 80.49% |
| EXPOSED_EVALUATION | H6 | DIRECT | 79.26% | 0.1074 | 0.972021 | 1.161 | 0.00% | 77.33% |
| EXPOSED_EVALUATION | CUM | DIRECT | 75.14% | 0.1486 | 1.046912 | 0.918 | 6.04% | 73.13% |
| MAY_HISTORICAL | H1 | AGGREGATED_H1 | 87.63% | 0.0237 | 2.070174 | 1.408 | 7.25% | 85.60% |
| MAY_HISTORICAL | H3 | AGGREGATED_H1 | 85.89% | 0.0411 | 1.638218 | 1.408 | 16.13% | 85.42% |
| MAY_HISTORICAL | H6 | AGGREGATED_H1 | 85.48% | 0.0452 | 1.357560 | 1.408 | 28.57% | 85.37% |
| MAY_HISTORICAL | CUM | AGGREGATED_H1 | 82.53% | 0.0747 | 1.443493 | 1.408 | 13.57% | 82.46% |
| MAY_HISTORICAL | H1 | DIRECT | 87.63% | 0.0237 | 2.070174 | 1.408 | 7.25% | 85.60% |
| MAY_HISTORICAL | H3 | DIRECT | 85.08% | 0.0492 | 1.608890 | 1.335 | 9.68% | 84.58% |
| MAY_HISTORICAL | H6 | DIRECT | 81.45% | 0.0855 | 1.431830 | 1.174 | 4.76% | 81.30% |
| MAY_HISTORICAL | CUM | DIRECT | 79.44% | 0.1056 | 1.639812 | 0.855 | 8.57% | 79.35% |

## Horizon robustness와 CUM coherence

| role | target | method | min/max horizon coverage | horizons in88–92% | Q50/Q90 downward prefix pairs | max prefix drop GPUh |
|---|---|---|---|---:|---:|---:|
| EXPOSED_EVALUATION | H1 | AGGREGATED_H1 | 79.55% / 95.45% | 4/24 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | H3 | AGGREGATED_H1 | 77.27% / 87.50% | 0/8 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | H6 | AGGREGATED_H1 | 76.14% / 81.82% | 0/4 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | CUM | AGGREGATED_H1 | 73.86% / 81.82% | 0/24 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | H1 | DIRECT | 79.55% / 95.45% | 4/24 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | H3 | DIRECT | 76.14% / 87.50% | 0/8 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | H6 | DIRECT | 72.73% / 88.64% | 1/4 | 0/0 | 0.000 |
| EXPOSED_EVALUATION | CUM | DIRECT | 63.64% / 95.45% | 0/24 | 339/440 | 1768.350 |
| MAY_HISTORICAL | H1 | AGGREGATED_H1 | 70.97% / 100.00% | 4/24 | 0/0 | 0.000 |
| MAY_HISTORICAL | H3 | AGGREGATED_H1 | 77.42% / 96.77% | 2/8 | 0/0 | 0.000 |
| MAY_HISTORICAL | H6 | AGGREGATED_H1 | 77.42% / 93.55% | 0/4 | 0/0 | 0.000 |
| MAY_HISTORICAL | CUM | AGGREGATED_H1 | 77.42% / 93.55% | 2/24 | 0/0 | 0.000 |
| MAY_HISTORICAL | H1 | DIRECT | 70.97% / 100.00% | 4/24 | 0/0 | 0.000 |
| MAY_HISTORICAL | H3 | DIRECT | 70.97% / 100.00% | 2/8 | 0/0 | 0.000 |
| MAY_HISTORICAL | H6 | DIRECT | 70.97% / 93.55% | 0/4 | 0/0 | 0.000 |
| MAY_HISTORICAL | CUM | DIRECT | 67.74% / 100.00% | 1/24 | 62/96 | 1158.377 |

모든 horizon/block, positive/zero/high-load strata와 Q50 결과는 HORIZON_METRICS.csv, STRATIFIED_METRICS.csv에 저장했다. Downward prefix가 있으면 coherent cumulative planning curve라고 주장하지 않는다. Forecast를 evaluation 후 교정하지 않았다.

## Paired statistical uncertainty

동일한 target-day 전체를 paired unit으로 하여 모든 block/prefix를 함께 resample했다. 1일 및7개 관측일 circular block 각2,000 draws이며 비율과 calibration error를 draw마다 재계산했다. Zero-denominator draw는 세고 해당 CI를 unavailable로 둔다. 제거하거나 재추출하지 않는다. 7-day 결과를 판정에 사용하고 day CI는 sensitivity로만 보고한다.

| role | target | method | contrast | metric | delta | 7-day95% CI | invalid draws |
|---|---|---|---|---|---:|---|---:|
| EXPOSED_EVALUATION | H3 | DIRECT | SAME_TARGET_DIRECT_EFFECT | normalized_Q90_pinball | 0.029461 | [-0.007724, 0.068136] | 0 |
| EXPOSED_EVALUATION | H3 | DIRECT | SAME_TARGET_DIRECT_EFFECT | requirement_ratio | 0.123823 | [-0.003434, 0.271565] | 0 |
| EXPOSED_EVALUATION | H3 | DIRECT | SAME_TARGET_DIRECT_EFFECT | high_load_coverage | 0.044776 | [0.000000, 0.105263] | 0 |
| EXPOSED_EVALUATION | H3 | AGGREGATED_H1 | RESOLUTION_EFFECT | normalized_Q90_pinball | -0.265451 | [-0.319254, -0.210796] | 0 |
| EXPOSED_EVALUATION | H3 | AGGREGATED_H1 | RESOLUTION_EFFECT | requirement_ratio | -0.000000 | [-0.000000, 0.000000] | 0 |
| EXPOSED_EVALUATION | H3 | AGGREGATED_H1 | RESOLUTION_EFFECT | high_load_coverage | -0.007576 | [-0.024590, 0.000000] | 0 |
| EXPOSED_EVALUATION | H6 | DIRECT | SAME_TARGET_DIRECT_EFFECT | normalized_Q90_pinball | 0.029152 | [-0.015105, 0.074926] | 0 |
| EXPOSED_EVALUATION | H6 | DIRECT | SAME_TARGET_DIRECT_EFFECT | requirement_ratio | -0.048350 | [-0.132109, 0.043957] | 0 |
| EXPOSED_EVALUATION | H6 | DIRECT | SAME_TARGET_DIRECT_EFFECT | high_load_coverage | 0.000000 | [0.000000, 0.000000] | 0 |
| EXPOSED_EVALUATION | H6 | AGGREGATED_H1 | RESOLUTION_EFFECT | normalized_Q90_pinball | -0.422848 | [-0.518464, -0.331787] | 0 |
| EXPOSED_EVALUATION | H6 | AGGREGATED_H1 | RESOLUTION_EFFECT | requirement_ratio | -0.000000 | [-0.000000, 0.000000] | 0 |
| EXPOSED_EVALUATION | H6 | AGGREGATED_H1 | RESOLUTION_EFFECT | high_load_coverage | -0.007576 | [-0.024590, 0.000000] | 0 |
| EXPOSED_EVALUATION | CUM | DIRECT | SAME_TARGET_DIRECT_EFFECT | normalized_Q90_pinball | 0.080916 | [-0.016770, 0.187745] | 0 |
| EXPOSED_EVALUATION | CUM | DIRECT | SAME_TARGET_DIRECT_EFFECT | requirement_ratio | -0.291325 | [-0.387663, -0.211262] | 0 |
| EXPOSED_EVALUATION | CUM | DIRECT | SAME_TARGET_DIRECT_EFFECT | high_load_coverage | -0.010989 | [-0.079426, 0.035714] | 0 |
| EXPOSED_EVALUATION | CUM | DIRECT | RESOLUTION_EFFECT | normalized_Q90_pinball | -0.318805 | [-0.577693, -0.059468] | 0 |
| EXPOSED_EVALUATION | CUM | DIRECT | RESOLUTION_EFFECT | requirement_ratio | -0.291325 | [-0.387663, -0.211262] | 0 |
| EXPOSED_EVALUATION | CUM | DIRECT | RESOLUTION_EFFECT | high_load_coverage | 0.052864 | [0.003128, 0.125009] | 0 |
| MAY_HISTORICAL | H3 | DIRECT | SAME_TARGET_DIRECT_EFFECT | normalized_Q90_pinball | -0.029328 | [-0.087274, 0.024034] | 0 |
| MAY_HISTORICAL | H3 | DIRECT | SAME_TARGET_DIRECT_EFFECT | requirement_ratio | -0.072691 | [-0.158167, -0.005326] | 0 |
| MAY_HISTORICAL | H3 | DIRECT | SAME_TARGET_DIRECT_EFFECT | high_load_coverage | -0.064516 | [-0.206897, 0.068966] | 0 |
| MAY_HISTORICAL | H3 | AGGREGATED_H1 | RESOLUTION_EFFECT | normalized_Q90_pinball | -0.431957 | [-0.561971, -0.285549] | 0 |
| MAY_HISTORICAL | H3 | AGGREGATED_H1 | RESOLUTION_EFFECT | requirement_ratio | 0.000000 | [-0.000000, 0.000000] | 0 |
| MAY_HISTORICAL | H3 | AGGREGATED_H1 | RESOLUTION_EFFECT | high_load_coverage | 0.088827 | [0.027014, 0.202352] | 0 |
| MAY_HISTORICAL | H6 | DIRECT | SAME_TARGET_DIRECT_EFFECT | normalized_Q90_pinball | 0.074269 | [-0.022763, 0.161791] | 0 |
| MAY_HISTORICAL | H6 | DIRECT | SAME_TARGET_DIRECT_EFFECT | requirement_ratio | -0.233531 | [-0.344865, -0.155918] | 0 |
| MAY_HISTORICAL | H6 | DIRECT | SAME_TARGET_DIRECT_EFFECT | high_load_coverage | -0.238095 | [-0.400000, -0.090909] | 0 |
| MAY_HISTORICAL | H6 | AGGREGATED_H1 | RESOLUTION_EFFECT | normalized_Q90_pinball | -0.712614 | [-0.925649, -0.504375] | 0 |
| MAY_HISTORICAL | H6 | AGGREGATED_H1 | RESOLUTION_EFFECT | requirement_ratio | 0.000000 | [-0.000000, 0.000000] | 0 |
| MAY_HISTORICAL | H6 | AGGREGATED_H1 | RESOLUTION_EFFECT | high_load_coverage | 0.213251 | [0.083333, 0.333333] | 0 |
| MAY_HISTORICAL | CUM | DIRECT | SAME_TARGET_DIRECT_EFFECT | normalized_Q90_pinball | 0.196319 | [0.049704, 0.364472] | 0 |
| MAY_HISTORICAL | CUM | DIRECT | SAME_TARGET_DIRECT_EFFECT | requirement_ratio | -0.553201 | [-0.782467, -0.412669] | 0 |
| MAY_HISTORICAL | CUM | DIRECT | SAME_TARGET_DIRECT_EFFECT | high_load_coverage | -0.050000 | [-0.139248, 0.019740] | 0 |
| MAY_HISTORICAL | CUM | DIRECT | RESOLUTION_EFFECT | normalized_Q90_pinball | -0.430363 | [-0.663827, -0.135529] | 0 |
| MAY_HISTORICAL | CUM | DIRECT | RESOLUTION_EFFECT | requirement_ratio | -0.553201 | [-0.782467, -0.412669] | 0 |
| MAY_HISTORICAL | CUM | DIRECT | RESOLUTION_EFFECT | high_load_coverage | 0.013251 | [-0.043868, 0.094412] | 0 |

SAME_TARGET_DIRECT_EFFECT는 DIRECT−동일 target의 H1 합산이며 학습 방법 효과다. RESOLUTION_EFFECT는 해당 target−H1이며 target 자체와 high-load 사건이 달라진 비교다. 고정 예측에 조건부인 CI로 refit/selection uncertainty를 포함하지 않는다. 여러 family와 지표의 unadjusted95% CI이므로 simultaneous familywise95% confirmation이나 새로운 untouched 검증으로 주장하지 않는다.

## 최종 판정과 한계

지원 판정은 DEV/CAL에서 eligible로 동결한 family에만 가능하다. Dec–Feb와 May 각각 point gate를 통과하고 7-day CI의 high-load 차이 lower>0 및 normalized pinball 차이 upper≤0이어야 한다. +5pp는 point의 실질적 개선 기준이며 CI lower≥5pp인 더 강한 증거는 GATES.csv의 robust_five_pp_gain으로 구분했다. 평가로 method나 primary를 다시 선택하지 않았다.

- AGGREGATED_CC4_TARGET_SUPPORTED = **FALSE**
- PRODUCTION_REPLACEMENT_SUPPORTED = **FALSE**
- OPTIMIZER_INTEGRATION_READY = **FALSE**
- PRODUCTION_PROMOTED = **FALSE**
- CC4_ML_DEVELOPMENT_STOPPED = **TRUE**

H3/H6/CUM의 사전 고정 후보 모두 지원 기준에 실패했다. CC4 추가 ML 개발을 종료하고 현재 frozen interface를 유지한다. 이번 task에서는 optimizer coupling이나 production promotion을 구현하지 않았다.

요청 상태와 실제 ingestion version/effective-time은 기존 V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1의 UNVERIFIED/UNOBSERVED 경계를 계승한다. Historical exactness, request immutability 또는 변경 빈도0을 주장하지 않는다. Raw actual completion은 label 재구성에만 사용하며 issue 이후 label은 학습에 들어가지 않는다. 이 한계와 untouched confirmation 부재 때문에 production replacement와 integration readiness는 fail-closed다.

19개 contract/preparation tests, raw Job membership, exact day membership/weights, feature time, checkpoint/prediction replay와 독립 paired CI 감사의 결과는 TEST_RESULTS.json, RAW_TARGET_AUDIT.json, VALIDATION.json, INDEPENDENT_AUDIT.json, UNCERTAINTY_AUDIT.json에 저장했다. 과거 frozen evidence는 overwrite하지 않았다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production은 수정하거나 실행하지 않았다.
