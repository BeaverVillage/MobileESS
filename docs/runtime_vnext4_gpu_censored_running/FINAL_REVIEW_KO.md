# Runtime-vNext4 최종 검토

DEV/CAL에서 동결한 연구 후보는 **R3의 실제 Q90**이다. 이는 안전성 조건을 만족한 연구 후보 선택이며 운영 채택을 뜻하지 않는다. 최종 판정은 **NEW_MODEL_SUPERIOR = FALSE**, **PRODUCTION_REPLACEMENT_SUPPORTED = FALSE**, **OPTIMIZER_INTEGRATION_READY = FALSE**, **PRODUCTION_PROMOTED = FALSE**이다. Pending은 모든 arm에서 frozen R0와 정확히 동일하며 운영 변경은 없다.

## 사전 결정과 비교 범위

- R0: 최신 frozen production Q90. May에만 권위 있는 출력이 존재한다. Running은 total−elapsed naive transport이다. DEV/CAL/April로 역적용하지 않았다.
- R1: PR65의 고정된 elapsed-conditioned remaining MULTI_QUANTILE. 180-day/14-day recency와 기존 issue refit을 그대로 사용한다.
- R2: R1과 같은 완료 Job landmark, 전처리, LightGBM 구조와 hyperparameter. 학습 가중치만 recency×GPU×(관측 total>4h이면 2, 아니면 1)로 바꾸고 총 recency weight를 보존하도록 정규화했다. GPU/long multiplier는 DEV 전에 고정했다.
- R3: 동일 완료 landmark에 해당 issue까지 관측된 archive-conditional right-censored landmark를 추가한 고정 log-normal XGBoost AFT. 800 rounds, scale=1.0과 모든 hyperparameter를 DEV 전에 고정했다. R3−R2에는 모델 구조와 censored 학습 모집단의 효과가 함께 있으므로 순수 구조 효과로 해석하지 않는다.
- Q90만 운영 bound 후보이다. Q50/Q95는 각 명목 수준을 유지한 진단이며 Q95를 Q90으로 이름 바꾸거나 threshold/selector를 탐색하지 않았다. scaling/capping은 없다. R2의 고정 monotone quantile 정렬은 부모와 동일하다.

`REGISTRATION.json` → DEV/CAL metric → `FINAL_SELECTION_FREEZE.json` 및 `FREEZE_BUNDLE.json` → 평가의 순서를 지켰다. 별도 `VERDICT_RULE_FREEZE.json`은 신규 평가 전 판정 규칙을 고정했다. May는 이미 노출된 historical diagnostic이며 untouched confirmation이 아니다. May/April 결과로 학습 weight, feature, model, quantile, 선택 rule을 변경하지 않았다.

**TEMPORAL_POLICY_CHANGED = FALSE**: 180-day window와 14-day half-life, issue cadence를 유지한다. R3의 censored row는 마지막 관측 시각이 현재 issue이므로 recency age=0이다. 완료 row의 age는 완료 시각 기준이다. 이 관측 시각 확장은 censored population 처리의 일부이며 별도 temporal search가 아니다.

## DEV/CAL 선택

| 구간 | 모델 | N | coverage | GPU coverage | 총 길이>4h under | missed GPU-slots | 초과예약/요청 초과예약 | 총예약/요청 총예약 | Q90 pinball (s) | bound MAE (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | R1 | 1466 | 74.28% | 84.61% | 23.96% | 4,243.000 | 2.356 | 1.405 | 8,272.289 | 57,254.740 |
| CALIBRATION | R2 | 1466 | 90.31% | 91.72% | 11.15% | 2,404.000 | 2.111 | 1.334 | 7,547.341 | 58,354.706 |
| CALIBRATION | R3 | 1466 | 97.20% | 96.99% | 3.14% | 2,119.000 | 16.793 | 5.740 | 35,499.624 | 349,483.719 |
| DEVELOPMENT | R1 | 2522 | 81.92% | 81.47% | 19.53% | 7,518.000 | 1.018 | 0.983 | 6,442.946 | 42,851.898 |
| DEVELOPMENT | R2 | 2522 | 83.03% | 82.08% | 18.33% | 7,126.000 | 1.019 | 0.985 | 6,410.223 | 45,258.258 |
| DEVELOPMENT | R3 | 2522 | 94.96% | 93.53% | 5.35% | 3,081.000 | 5.840 | 3.239 | 19,286.313 | 181,118.969 |

R3만 두 구간 모두 coverage≥90%, GPU coverage≥90%, total>4h under≤15%를 충족했다. 요청 대비 초과예약은 selection의 선호 조건이었고 hard safety gate가 아니었다. R3의 DEV/CAL 초과예약 비율은 각각 5.84×/16.79×이고 총예약 비율은 3.24×/5.74×이다. 따라서 `selected=R3`은 안전성 우선 규칙에 따른 연구 후보이며 예약 효율이나 채택 근거가 아니다. R0의 pre-evaluation missed-slot 성능은 알 수 없어 선택에 넣지 않았다.

## 동결 이후 평가

| 구간 | 모델 | N | coverage | GPU coverage | 총 길이>4h under | missed GPU-slots | 초과예약/요청 초과예약 | 총예약/요청 총예약 | Q90 pinball (s) | bound MAE (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| EXPOSED_EVALUATION | R1 | 2767 | 83.85% | 88.59% | 15.83% | 8,597.000 | 2.812 | 1.428 | 8,597.991 | 64,760.525 |
| EXPOSED_EVALUATION | R2 | 2767 | 85.54% | 85.87% | 13.93% | 8,250.000 | 2.701 | 1.385 | 8,301.010 | 67,323.859 |
| EXPOSED_EVALUATION | R3 | 2767 | 97.25% | 95.78% | 2.38% | 1,283.000 | 20.834 | 5.818 | 53,111.515 | 515,386.368 |
| MAY_HISTORICAL | R0 | 7073 | 54.06% | 56.35% | 48.77% | 136,902.000 | 0.685 | 0.682 | 32,197.514 | 52,508.338 |
| MAY_HISTORICAL | R1 | 7073 | 81.95% | 81.53% | 19.28% | 42,242.000 | 1.400 | 1.083 | 15,114.685 | 68,857.576 |
| MAY_HISTORICAL | R2 | 7073 | 86.53% | 84.65% | 14.36% | 41,286.000 | 1.355 | 1.076 | 13,058.722 | 68,694.589 |
| MAY_HISTORICAL | R3 | 7073 | 96.93% | 93.33% | 3.17% | 31,579.000 | 26.531 | 10.970 | 225,310.199 | 2,242,503.811 |

최종 superiority는 두 평가 구간 모두 안전성 조건과 `overreserved GPUh <= requested-walltime overreserved GPUh`를 충족하고, 7-issue block CI에서 missed-slot 감소가 R1 대비 두 구간 및 R0 대비 May에서 지지되는지를 함께 요구했다. 안전성 통과=True, 요청 초과예약 기준 통과=False. coverage만 높이는 과예약 모델은 운영 우수성으로 채택하지 않는다.

Pending R0(모든 후보 동일):

| 구간 | 모델 | N | coverage | GPU coverage | 총 길이>4h under | missed GPU-slots | 초과예약/요청 초과예약 | 총예약/요청 총예약 | Q90 pinball (s) | bound MAE (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| MAY_HISTORICAL | R0 | 40419 | 91.22% | 93.70% | 22.60% | 17,373.000 | 0.757 | 0.793 | 2,827.758 | 23,996.645 |

`QUANTILE_DIAGNOSTICS.csv`는 R1/R2/R3 Q50/Q90/Q95의 명목 pinball, coverage와 예약량을 각각 보고한다. R0에는 authoritative Q90만 존재하므로 median MAE나 Q95 자체 예측을 만들어 넣지 않았다. 각 bound에서 tau=.90/.95 loss를 계산한 항목은 그 bound를 해당 loss로 평가한 값이며 quantile 이름 변경을 뜻하지 않는다.

## 통계적 불확실성

| 구간 | 후보 | 기준 | 지표 | 효과 | 95% low | 95% high |
|---|---|---|---|---|---|---|
| EXPOSED_EVALUATION | R2 | R1 | coverage | 0.017 | 0.005 | 0.027 |
| EXPOSED_EVALUATION | R2 | R1 | GPU_coverage | -0.027 | -0.053 | 0.002 |
| EXPOSED_EVALUATION | R2 | R1 | long_under | -0.019 | -0.030 | -0.006 |
| EXPOSED_EVALUATION | R2 | R1 | pinball_Q90 | -296.981 | -1,306.190 | 929.566 |
| EXPOSED_EVALUATION | R2 | R1 | overreserve_vs_requested | -0.112 | -0.224 | 0.036 |
| EXPOSED_EVALUATION | R2 | R1 | missed_slots_reduction | 0.040 | -0.207 | 0.376 |
| EXPOSED_EVALUATION | R3 | R1 | coverage | 0.134 | 0.082 | 0.173 |
| EXPOSED_EVALUATION | R3 | R1 | GPU_coverage | 0.072 | 0.054 | 0.089 |
| EXPOSED_EVALUATION | R3 | R1 | long_under | -0.135 | -0.175 | -0.083 |
| EXPOSED_EVALUATION | R3 | R1 | pinball_Q90 | 44,513.524 | 40,193.132 | 49,717.657 |
| EXPOSED_EVALUATION | R3 | R1 | overreserve_vs_requested | 18.022 | 11.941 | 26.526 |
| EXPOSED_EVALUATION | R3 | R1 | missed_slots_reduction | 0.851 | 0.730 | 0.924 |

| 구간 | 후보 | 기준 | 지표 | 효과 | 95% low | 95% high |
|---|---|---|---|---|---|---|
| MAY_HISTORICAL | R2 | R1 | coverage | 0.046 | 0.023 | 0.075 |
| MAY_HISTORICAL | R2 | R1 | GPU_coverage | 0.031 | 0.002 | 0.065 |
| MAY_HISTORICAL | R2 | R1 | long_under | -0.049 | -0.082 | -0.024 |
| MAY_HISTORICAL | R2 | R1 | pinball_Q90 | -2,055.963 | -4,703.708 | -216.142 |
| MAY_HISTORICAL | R2 | R1 | overreserve_vs_requested | -0.045 | -0.135 | 0.053 |
| MAY_HISTORICAL | R2 | R1 | missed_slots_reduction | 0.023 | -0.379 | 0.370 |
| MAY_HISTORICAL | R3 | R1 | coverage | 0.150 | 0.069 | 0.246 |
| MAY_HISTORICAL | R3 | R1 | GPU_coverage | 0.118 | 0.051 | 0.194 |
| MAY_HISTORICAL | R3 | R1 | long_under | -0.161 | -0.269 | -0.076 |
| MAY_HISTORICAL | R3 | R1 | pinball_Q90 | 210,195.514 | 22,217.063 | 598,948.491 |
| MAY_HISTORICAL | R3 | R1 | overreserve_vs_requested | 25.132 | 6.696 | 50.496 |
| MAY_HISTORICAL | R3 | R1 | missed_slots_reduction | 0.252 | -1.191 | 0.662 |
| MAY_HISTORICAL | R3 | R0 | coverage | 0.429 | 0.365 | 0.515 |
| MAY_HISTORICAL | R3 | R0 | GPU_coverage | 0.370 | 0.298 | 0.445 |
| MAY_HISTORICAL | R3 | R0 | long_under | -0.456 | -0.554 | -0.387 |
| MAY_HISTORICAL | R3 | R0 | pinball_Q90 | 193,112.685 | 18,797.747 | 566,011.501 |
| MAY_HISTORICAL | R3 | R0 | overreserve_vs_requested | 25.847 | 7.531 | 51.225 |
| MAY_HISTORICAL | R3 | R0 | missed_slots_reduction | 0.769 | 0.510 | 0.927 |

위 표는 7-observed-issue circular-block 결과다. 전체 paired day=1/block=7 2,000 draws와 모든 지표는 `PAIRED_UNCERTAINTY.csv`에 있다. 후보−기준 차이에서 coverage는 양수가, under/missed/reserve/loss는 음수가 개선이다. `missed_slots_reduction`은 1−후보/기준으로 양수가 개선이다. 총량과 비율은 각 bootstrap sample에서 다시 계산했으며 denominator=0인 draw 수를 저장한다. `N_days`는 실제 달력 간격이 아닌 관측 issue 수다. April 13, May 31 issue이며 block=7의 유효 정보량이 작다. 고정 예측의 조건부 CI이고 재학습/모델 선택 불확실성이나 반복 Job 의존성 전체를 제거하지 않는다. 여러 arm/지표를 보고하며 다중비교 보정이나 untouched confirmatory 유의성 주장은 하지 않는다.

## Causal / maturity / provenance

사용자는 V40S4 **D1_SCHEDULER_REQUEST_STATE_PROXY_V1**에 따라 archive request field를 scheduler-visible proxy로 명시적으로 허용했다. provenance는 **UNVERIFIED/UNOBSERVED**다. 요청값의 역사적 정확성·불변성·zero-change, 실제 historical census의 완전성, outcome-independent archive inclusion을 주장하지 않는다. `07_hpc-oda-commons`는 code/model authority일 뿐 snapshot authority가 아니다. 초기 엄격 authority assessment와 이후 사용자 허용은 각각 `CENSORING_AUTHORITY.json`, `PROXY_AUTHORIZATION.json`으로 보존했다. 후자의 'no outcome-based population exclusion'은 **이미 관측된 archive 내부 cache filter**에 한정되며 upstream archive completeness의 주장이 아니다.

원시 전체 GPU 1,034,072행을 읽었고 null-end GPU는 0행이었다. 관련 pre-June 723,148행은 end/state/label_valid로 제외하지 않고 부모 cache와 정확히 일치한다. 관측되지 않은 never-completed Job을 만들어 보충하거나 실제 위험집단 전체를 안다고 주장하지 않았다. raw rebuild는 부모 normalized input과 byte SHA-256까지 같다.

R2 완료 학습은 end<issue만 허용한다. R3에서 end<issue일 때만 exact remaining label을 사용하고, 그 외 future/end==issue/null은 observed_end를 제거하고 lower=issue−start−이미 도달한 landmark, upper=∞로 만든다. final state/runtime/label_valid는 censored 학습 입력·label·weight에 들어가지 않는다. censored long weight는 그때 이미 관측된 total elapsed>4h 여부만 쓴다. R3의 issue별 censored 수 범위는 6–381이며 작은 archive-conditional 보강이다. 실제 모집단 censor bias 해소는 입증하지 않는다.

feature는 기존 9개 scheduler proxy와 log1p(elapsed)이다. request version의 실제 availability timestamp는 UNOBSERVED이며 임의 시각을 발명하지 않았다. submit/start와 issue의 event-time eligibility, 완료 target encoding의 maturity, query matrix의 기존 전처리와 bit-exact 동등성은 검증했다. feature의 운영 causality 인증과 event-time proxy 검증을 구분한다.

`>4h long-job underprediction`은 **actual TOTAL runtime>4h**인 Job에서 Running remaining prediction이 실제 remaining보다 작은 비율이다. 요청 기준 remaining은 max(requested−elapsed,0)이다. GPU-slots는 부모의 15분/24시간 runtime-origin occupancy proxy이며 optimizer dispatch 결과가 아니다. 이 지표의 96-slot horizon 때문에 24시간 이후의 차이는 측정하지 않는다. prediction 자체에는 이 cap을 적용하지 않는다. 평가 query 전체를 유지하고 invalid label만 unscorable로 표시한다. `RUNNING_ELAPSED_METRICS.csv`에 <1h, 1–2h, 2–4h, 4–8h, >8h를 보고한다. GPU bucket 추가 진단은 `RUNNING_GPU_METRICS.csv`에 있다.

## 재현·검증·보존

118개 신규 fit의 exact ordered membership, safe label/time/weight digests, 학습 receipt와 prediction을 저장했다. 거대한 원본 fit-time MEMBERSHIP Parquet와 model weights는 local에서 변경 없이 보존하고 SHA manifest를 제공한다. Git에는 같은 ordered row_id NPZ와 parent JOB_MEMBERSHIP + 동결 censor_proxy로 모든 safe column을 lossless 재구성·검증한 증거를 전달한다. `PORTABLE_MEMBERSHIP_AUDIT.json` 및 독립 review가 원본과의 동등성을 확인한다. 모델 입력 전체는 pinned raw archive로 재구성한다. portable sklearn preprocessors와 query-transform bit-exact bridge를 포함한다.

검증은 synthetic censor/future-end invariance/weight/AFT/selection/CI contract test 6개, 118 memberships 및 model/prediction digests, Pending R0 exact preservation, 모든 parent delivery hash, 독립 paired uncertainty 재계산을 포함한다. 정확한 결과는 `TEST_RESULTS.json`, `VALIDATION.json`, `INDEPENDENT_REVIEW.json`, `PORTABLE_MEMBERSHIP_AUDIT.json`을 참조한다. 기존 frozen evidence는 overwrite하지 않았다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 실행·수정 및 production promotion은 없다.
