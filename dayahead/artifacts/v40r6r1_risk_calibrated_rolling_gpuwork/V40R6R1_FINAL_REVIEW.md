FINAL CLASSIFICATION: V40R6R1_JOINT_GPUWORK_RESERVE_FAIL
WORKLOAD RESERVE SERVICE LEVEL: 85%
PRIMARY HORIZONS: H4, H24
SELECTED H4 BASE: NONE
SELECTED H24 BASE: NONE
SELECTED H4 ROLLING UPPER: NONE
SELECTED H24 ROLLING UPPER: NONE
H4 CAL SAFETY: FAIL
H24 CAL SAFETY: FAIL
H4 EXPOSED SAFETY: FAIL (NONE; 후보 결과는 진단 전용)
H24 EXPOSED SAFETY: FAIL (NONE; 후보 결과는 진단 전용)
JOINT RESERVE STATUS: FAIL
FUTURE WORKLOAD ML STATUS: NO_MODEL_PROMOTED
OPTIMIZER INTEGRATION: NO
PRODUCTION READY: NO

85%는 외생 미래 workload reserve의 공학적 서비스 수준이다. 계통 보안·전압 신뢰도·전기적 안전확률이 아니다.
각 지표는 기존의 유효 날짜 및 원본 예측에 대해 계산했다. H4 누적 window가 겹치므로 under/over 합계는 고유 작업량 총계가 아니다.

1. Git lineage

86f3bf3a588d0c31e109a14e97ec2efd122d4508 → 528716aa36b02bbe0ebff3cf9639984c6b2c535e → 11ff08052da5231e2dc66eac5e28f064dfed83d2 → ea9b86e9f32808f255c14e498b895a6410d65fe3 → 2d6e22e2b448454bb4a860a07f38c20ad3ef834d

2. R6 불변 보존

R6=V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL, H1/H4/H8/H24=NONE, optimizer/production=NO 유지. R5/R5R1/R6 파일 해시 및 전체 보호 Git 범위 변경 없음.

3. 85% 설계 해석

85% WORKLOAD-RESERVE SERVICE LEVEL. H4/H24의 양수 coverage 85–92.5%, 일/지원 월 80% 하한과 효율 기준을 사전 고정했다. R6의 90% 실험을 재분류하지 않았다.

4. 동결 타깃 identity

{"PASS": true, "exact_R6_target_SHA256": "091025b3da865e88099d68e2993e841660ee8baa2a07064099e6b777d85774a8", "expected_SHA256": "091025b3da865e88099d68e2993e841660ee8baa2a07064099e6b777d85774a8", "native_N": 33504, "native_days": 349, "native_total_GPUh": 1904541.7783333336, "H4_rows": 28269, "H24_rows": 349, "identity_max_error_GPUh": 0.0, "new_target_construction": 0, "target_population_changes": 0, "unit": "GPUh", "not_GPU_occupancy": true}

5. 동결 B1/B2 identity

모두 READ_FROM_FROZEN_ARRAY. B1 baseline[:,2], B2 L0의 기존 crossing-repaired q[:,1]. 원본 파일별 SHA256은 BASE_PREDICTION_IDENTITY에 기록. base의 음수는 요청한 log1p(max(base,0)) 식에서만 처리.

6. 신규 fit 없음

{"new_LightGBM_fits": 0, "new_statistical_model_fits": 0, "new_classifier_fits": 0, "new_feature_engineering": 0, "new_target_construction": 0, "base_prediction_recompute": 0, "source": "Exact R6 saved prediction arrays; no model library imported or model fitted", "only_new_scientific_object": "Causal expanding calibration of frozen upper outputs", "R6_BASE_SKILL_LIMITATION": "PRESENT", "R6_fit_ledger_SHA256": "cb9b4bbcdd4475ab114c876e8d3c6c72232960ca6db147d974d488b457a6bb75"}

7. 잔차 인과성

사용자가 명시적으로 선택한 max(target_day_end,target_label_available_at)<issue_time. OOS 172일 중 159일은 날짜 종료 후 정답이 확정되므로 날짜 종료만으로 편입하지 않는다. 모든 historical day의 전체 window를 함께 포함한다.

8. DEVELOPMENT 초기 잔차

TRAIN fit에 대해 OOS인 DEVELOPMENT 58일만 초기화에 사용. TRAIN in-sample 잔차 0. DEVELOPMENT는 R6 설정 선택에도 쓰였으므로 완전히 미노출된 tuning holdout이라는 주장은 하지 않는다.

9. H4 지원량 증가

| horizon | candidate | phase | first_day | last_day | initial_days | final_days | initial_rows | final_rows | monotone_support | insufficient_issues |
|---|---|---|---|---|---|---|---|---|---|---|
| H4 | R85_B1 | CALIBRATION | 2024-11-01 | 2024-11-27 | 58 | 78 | 4698 | 6318 | True | 0 |
| H4 | R85_B1 | EXPOSED_EVALUATION | 2024-12-01 | 2025-02-26 | 84 | 165 | 6804 | 13365 | True | 0 |
| H4 | R85_B2 | CALIBRATION | 2024-11-01 | 2024-11-27 | 58 | 78 | 4698 | 6318 | True | 0 |
| H4 | R85_B2 | EXPOSED_EVALUATION | 2024-12-01 | 2025-02-26 | 84 | 165 | 6804 | 13365 | True | 0 |

10. H24 지원량 증가

| horizon | candidate | phase | first_day | last_day | initial_days | final_days | initial_rows | final_rows | monotone_support | insufficient_issues |
|---|---|---|---|---|---|---|---|---|---|---|
| H24 | R85_B1 | CALIBRATION | 2024-11-01 | 2024-11-27 | 58 | 78 | 58 | 78 | True | 0 |
| H24 | R85_B1 | EXPOSED_EVALUATION | 2024-12-01 | 2025-02-26 | 84 | 165 | 84 | 165 | True | 0 |
| H24 | R85_B2 | CALIBRATION | 2024-11-01 | 2024-11-27 | 58 | 78 | 58 | 78 | True | 0 |
| H24 | R85_B2 | EXPOSED_EVALUATION | 2024-12-01 | 2025-02-26 | 84 | 165 | 84 | 165 | True | 0 |

11. H4 일별 delta 분포

| horizon | candidate | month | issues | minimum | median | P90 | maximum | support_days_min | support_days_max | support_rows_min | support_rows_max | negative_q85_floored_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H4 | R85_B1 | ALL | 114 | 0.247839365 | 0.337872574 | 0.364286338 | 0.400062918 | 58 | 165 | 4698 | 13365 | 0 |
| H4 | R85_B1 | 2024-11 | 26 | 0.329132201 | 0.346734971 | 0.400062918 | 0.400062918 | 58 | 78 | 4698 | 6318 | 0 |
| H4 | R85_B1 | 2024-12 | 31 | 0.252746955 | 0.3030933 | 0.349318325 | 0.352854553 | 84 | 112 | 6804 | 9072 | 0 |
| H4 | R85_B1 | 2025-01 | 31 | 0.247839365 | 0.2682235 | 0.307923096 | 0.330793317 | 112 | 139 | 9072 | 11259 | 0 |
| H4 | R85_B1 | 2025-02 | 26 | 0.345005981 | 0.362689159 | 0.364788412 | 0.369668124 | 142 | 165 | 11502 | 13365 | 0 |
| H4 | R85_B2 | ALL | 114 | 0.583388979 | 0.63298679 | 0.804793296 | 0.858414162 | 58 | 165 | 4698 | 13365 | 0 |
| H4 | R85_B2 | 2024-11 | 26 | 0.710641527 | 0.801643088 | 0.858414162 | 0.858414162 | 58 | 78 | 4698 | 6318 | 0 |
| H4 | R85_B2 | 2024-12 | 31 | 0.605414332 | 0.65293932 | 0.710641527 | 0.710641527 | 84 | 112 | 6804 | 9072 | 0 |
| H4 | R85_B2 | 2025-01 | 31 | 0.583388979 | 0.605040517 | 0.627002211 | 0.638483245 | 112 | 139 | 9072 | 11259 | 0 |
| H4 | R85_B2 | 2025-02 | 26 | 0.588591855 | 0.630713619 | 0.638920025 | 0.647324076 | 142 | 165 | 11502 | 13365 | 0 |

12. H24 일별 delta 분포

| horizon | candidate | month | issues | minimum | median | P90 | maximum | support_days_min | support_days_max | support_rows_min | support_rows_max | negative_q85_floored_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H24 | R85_B1 | ALL | 114 | 0.486590294 | 0.51352864 | 0.540748287 | 0.591373639 | 58 | 165 | 58 | 165 | 0 |
| H24 | R85_B1 | 2024-11 | 26 | 0.486590294 | 0.51352864 | 0.51352864 | 0.535512398 | 58 | 78 | 58 | 78 | 0 |
| H24 | R85_B1 | 2024-12 | 31 | 0.51352864 | 0.513784749 | 0.535512398 | 0.535512398 | 84 | 112 | 84 | 112 | 0 |
| H24 | R85_B1 | 2025-01 | 31 | 0.486590294 | 0.51352864 | 0.513784749 | 0.535512398 | 112 | 139 | 112 | 139 | 0 |
| H24 | R85_B1 | 2025-02 | 26 | 0.535512398 | 0.540366479 | 0.540911919 | 0.591373639 | 142 | 165 | 142 | 165 | 0 |
| H24 | R85_B2 | ALL | 114 | 0.500758274 | 0.557274706 | 0.638840348 | 0.643189824 | 58 | 165 | 58 | 165 | 0 |
| H24 | R85_B2 | 2024-11 | 26 | 0.500758274 | 0.540523027 | 0.540523027 | 0.557274706 | 58 | 78 | 58 | 78 | 0 |
| H24 | R85_B2 | 2024-12 | 31 | 0.516228208 | 0.557274706 | 0.557274706 | 0.557274706 | 84 | 112 | 84 | 112 | 0 |
| H24 | R85_B2 | 2025-01 | 31 | 0.540523027 | 0.557274706 | 0.609133273 | 0.636165459 | 112 | 139 | 112 | 139 | 0 |
| H24 | R85_B2 | 2025-02 | 26 | 0.636165459 | 0.638840348 | 0.643189824 | 0.643189824 | 142 | 165 | 142 | 165 | 0 |

13. CAL H4 R85_B1

| phase | horizon | candidate | support_complete | N | evaluated_N | positive_N | positive_coverage | overall_coverage_DIAGNOSTIC | mean_day_positive_coverage | supported_positive_days | zero_fraction | under_GPUh | over_GPUh | positive_shortfall_ratio | positive_upper_WAPE | positive_pinball85 | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh | raw_base_under_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh | PASS | failure_reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H4 | R85_B1 | True | 2106 | 2106 | 2092 | 0.867112811 | 0.867996201 | 0.867091806 | 26 | 0.00664767331 | 1969270.79 | 2742534.65 | 0.554652537 | 1.31987245 | 994.939004 | 278 | 7083.70787 | 26290.4715 | 51525.0477 | 61612.2436 | 2180282.1 | 3958371.46 | 2677543.48 | False | over_GPUh_below_R6_static_U2 |

{"PASS": false, "checks": {"calibration_support": true, "positive_coverage_lower": true, "positive_coverage_upper": true, "supported_positive_days": true, "mean_day_coverage": true, "supported_month_positive_coverage": true, "supported_month_mean_day_coverage": true, "under_GPUh_below_own_raw_base": true, "over_GPUh_below_TRAIN_Q95": true, "over_GPUh_below_R6_static_U2": false, "positive_upper_WAPE_below_200pct": true}, "failure_reasons": ["over_GPUh_below_R6_static_U2"]}

14. CAL H4 R85_B2

| phase | horizon | candidate | support_complete | N | evaluated_N | positive_N | positive_coverage | overall_coverage_DIAGNOSTIC | mean_day_positive_coverage | supported_positive_days | zero_fraction | under_GPUh | over_GPUh | positive_shortfall_ratio | positive_upper_WAPE | positive_pinball85 | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh | raw_base_under_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh | PASS | failure_reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H4 | R85_B2 | True | 2106 | 2106 | 2092 | 0.895315488 | 0.896011396 | 0.89533492 | 26 | 0.00664767331 | 1912223.42 | 3127384.24 | 0.53858493 | 1.41217651 | 999.348706 | 219 | 8731.61377 | 24147.2475 | 53527.3682 | 61955.8385 | 2380483.69 | 3958371.46 | 2677543.48 | False | over_GPUh_below_R6_static_U2 |

{"PASS": false, "checks": {"calibration_support": true, "positive_coverage_lower": true, "positive_coverage_upper": true, "supported_positive_days": true, "mean_day_coverage": true, "supported_month_positive_coverage": true, "supported_month_mean_day_coverage": true, "under_GPUh_below_own_raw_base": true, "over_GPUh_below_TRAIN_Q95": true, "over_GPUh_below_R6_static_U2": false, "positive_upper_WAPE_below_200pct": true}, "failure_reasons": ["over_GPUh_below_R6_static_U2"]}

15. CAL H24 R85_B1

| phase | horizon | candidate | support_complete | N | evaluated_N | positive_N | positive_coverage | overall_coverage_DIAGNOSTIC | mean_day_positive_coverage | supported_positive_days | zero_fraction | under_GPUh | over_GPUh | positive_shortfall_ratio | positive_upper_WAPE | positive_pinball85 | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh | raw_base_under_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh | PASS | failure_reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H24 | R85_B1 | True | 26 | 26 | 26 | 0.807692308 | 0.807692308 | 0.807692308 | 26 | 0 | 86214.3008 | 144238.598 | 0.346833889 | 0.927095326 | 3650.69021 | 5 | 17242.8602 | 39490.725 | 46242.161 | 52993.597 | 117580.59 | 115479.76 | 400120.405 | False | positive_coverage_lower / over_GPUh_below_TRAIN_Q95 |

{"PASS": false, "checks": {"calibration_support": true, "positive_coverage_lower": false, "positive_coverage_upper": true, "supported_positive_days": true, "mean_day_coverage": true, "supported_month_positive_coverage": true, "supported_month_mean_day_coverage": true, "under_GPUh_below_own_raw_base": true, "over_GPUh_below_TRAIN_Q95": false, "over_GPUh_below_R6_static_U2": true, "positive_upper_WAPE_below_200pct": true}, "failure_reasons": ["positive_coverage_lower", "over_GPUh_below_TRAIN_Q95"]}

16. CAL H24 R85_B2

| phase | horizon | candidate | support_complete | N | evaluated_N | positive_N | positive_coverage | overall_coverage_DIAGNOSTIC | mean_day_positive_coverage | supported_positive_days | zero_fraction | under_GPUh | over_GPUh | positive_shortfall_ratio | positive_upper_WAPE | positive_pinball85 | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh | raw_base_under_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh | PASS | failure_reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H24 | R85_B2 | True | 26 | 26 | 26 | 0.807692308 | 0.807692308 | 0.807692308 | 26 | 0 | 87837.1471 | 165818.748 | 0.353362483 | 1.0204393 | 3828.24567 | 5 | 17567.4294 | 39995.0988 | 47775.4921 | 55555.8854 | 119933.336 | 115479.76 | 400120.405 | False | positive_coverage_lower / over_GPUh_below_TRAIN_Q95 |

{"PASS": false, "checks": {"calibration_support": true, "positive_coverage_lower": false, "positive_coverage_upper": true, "supported_positive_days": true, "mean_day_coverage": true, "supported_month_positive_coverage": true, "supported_month_mean_day_coverage": true, "under_GPUh_below_own_raw_base": true, "over_GPUh_below_TRAIN_Q95": false, "over_GPUh_below_R6_static_U2": true, "positive_upper_WAPE_below_200pct": true}, "failure_reasons": ["positive_coverage_lower", "over_GPUh_below_TRAIN_Q95"]}

17. CAL 후보 선택

{"H4": "NONE", "H24": "NONE"}; 지원량→coverage→시간 안정성→miss→두 over anchor→WAPE를 모두 통과한 후보만 선택. 2% 효율 동률이면 B1.

18. 선택 동결 커밋

cfb7a3105ae39dd4c22a5522fd9b4f715e232d5c

19. EXPOSED H4

| phase | horizon | candidate | support_complete | N | evaluated_N | positive_N | positive_coverage | overall_coverage_DIAGNOSTIC | mean_day_positive_coverage | supported_positive_days | zero_fraction | under_GPUh | over_GPUh | positive_shortfall_ratio | positive_upper_WAPE | positive_pinball85 | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh | raw_base_under_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh | PASS | failure_reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EXPOSED_EVALUATION | H4 | R85_B1 | True | 7128 | 7128 | 6403 | 0.827893175 | 0.845398429 | 0.83284789 | 83 | 0.10171156 | 4223539.08 | 8982247.66 | 0.448199428 | 1.25313052 | 738.369524 | 1102 | 3832.61259 | 15056.0659 | 17643.174 | 24649.0921 | 4864897.18 | 13149881.8 | 10612434.7 | False | positive_coverage_lower / supported_month_positive_coverage / supported_month_mean_day_coverage |
| EXPOSED_EVALUATION | H4 | R85_B2 | True | 7128 | 7128 | 6403 | 0.857879119 | 0.872334456 | 0.861819011 | 83 | 0.10171156 | 3862978.5 | 10000289.2 | 0.409936956 | 1.40200791 | 731.817299 | 910 | 4245.03132 | 15434.9562 | 17543.4135 | 23119.7207 | 5179432.32 | 13149881.8 | 10612434.7 | True | nan |

20. EXPOSED H24

| phase | horizon | candidate | support_complete | N | evaluated_N | positive_N | positive_coverage | overall_coverage_DIAGNOSTIC | mean_day_positive_coverage | supported_positive_days | zero_fraction | under_GPUh | over_GPUh | positive_shortfall_ratio | positive_upper_WAPE | positive_pinball85 | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh | raw_base_under_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh | PASS | failure_reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EXPOSED_EVALUATION | H24 | R85_B1 | True | 88 | 88 | 83 | 0.819277108 | 0.829545455 | 0.819277108 | 83 | 0.0568181818 | 140180.516 | 527270.917 | 0.208511673 | 0.910072158 | 2287.96814 | 15 | 9345.36771 | 15689.8704 | 17886.2359 | 22540.2529 | 237915.886 | 390803.885 | 1415858.66 | False | positive_coverage_lower / supported_month_positive_coverage / supported_month_mean_day_coverage / over_GPUh_below_TRAIN_Q95 |
| EXPOSED_EVALUATION | H24 | R85_B2 | True | 88 | 88 | 83 | 0.831325301 | 0.840909091 | 0.831325301 | 83 | 0.0568181818 | 116305.766 | 629008.161 | 0.172999149 | 1.02108582 | 2221.49463 | 14 | 8307.55475 | 15922.7045 | 16876.5161 | 17641.7561 | 229612.141 | 390803.885 | 1415858.66 | False | positive_coverage_lower / supported_month_positive_coverage / supported_month_mean_day_coverage / over_GPUh_below_TRAIN_Q95 |

21. 2024-12 안정성

| horizon | candidate | positive_N | positive_coverage | mean_day_positive_coverage | under_GPUh | over_GPUh | positive_upper_WAPE | mean_miss_GPUh | maximum_miss_GPUh |
|---|---|---|---|---|---|---|---|---|---|
| H4 | R85_B1 | 1842 | 0.851248643 | 0.862434645 | 1157925.99 | 3624743.22 | 1.42702127 | 4226.00726 | 24649.0921 |
| H4 | R85_B2 | 1842 | 0.855591748 | 0.865598291 | 1123960.1 | 3051679.42 | 1.4984763 | 4225.41391 | 23119.7207 |
| H24 | R85_B1 | 26 | 0.846153846 | 0.846153846 | 48583.6616 | 236746.89 | 1.27868236 | 12145.9154 | 22540.2529 |
| H24 | R85_B2 | 26 | 0.807692308 | 0.807692308 | 42626.3898 | 211426.5 | 1.08660275 | 8525.27796 | 17641.7561 |

22. 2025-01 안정성

| horizon | candidate | positive_N | positive_coverage | mean_day_positive_coverage | under_GPUh | over_GPUh | positive_upper_WAPE | mean_miss_GPUh | maximum_miss_GPUh |
|---|---|---|---|---|---|---|---|---|---|
| H4 | R85_B1 | 2469 | 0.770352369 | 0.773012557 | 2417459.97 | 2691527.85 | 1.08153288 | 4263.59782 | 20878.1121 |
| H4 | R85_B2 | 2469 | 0.837181045 | 0.839904421 | 2013818.13 | 4228230.99 | 1.31706859 | 5009.49784 | 20531.5147 |
| H24 | R85_B1 | 31 | 0.709677419 | 0.709677419 | 77530.0223 | 131059.59 | 0.644106067 | 8614.44692 | 15891.6572 |
| H24 | R85_B2 | 31 | 0.741935484 | 0.741935484 | 65698.2462 | 172182.446 | 0.734554302 | 8212.28078 | 16464.4637 |

23. 2025-02 안정성

| horizon | candidate | positive_N | positive_coverage | mean_day_positive_coverage | under_GPUh | over_GPUh | positive_upper_WAPE | mean_miss_GPUh | maximum_miss_GPUh |
|---|---|---|---|---|---|---|---|---|---|
| H4 | R85_B1 | 2092 | 0.875239006 | 0.874603264 | 648153.126 | 2665976.59 | 1.41703521 | 2483.34531 | 16406.1415 |
| H4 | R85_B2 | 2092 | 0.884321224 | 0.884168666 | 725200.269 | 2720378.75 | 1.47233463 | 2996.69533 | 16585.8489 |
| H24 | R85_B1 | 26 | 0.923076923 | 0.923076923 | 14066.8318 | 159464.437 | 1.02803102 | 7033.4159 | 13704.2478 |
| H24 | R85_B2 | 26 | 0.961538462 | 0.961538462 | 7981.13038 | 245399.214 | 1.50107157 | 7981.13038 | 7981.13038 |

24. miss severity

| phase | horizon | candidate | month | under_GPUh | positive_shortfall_ratio | miss_N | mean_miss_GPUh | P90_miss_GPUh | P95_miss_GPUh | maximum_miss_GPUh |
|---|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H4 | R85_B1 | ALL | 1969270.79 | 0.554652537 | 278 | 7083.70787 | 26290.4715 | 51525.0477 | 61612.2436 |
| CALIBRATION | H4 | R85_B1 | 2024-11 | 1969270.79 | 0.554652537 | 278 | 7083.70787 | 26290.4715 | 51525.0477 | 61612.2436 |
| CALIBRATION | H4 | R85_B2 | ALL | 1912223.42 | 0.53858493 | 219 | 8731.61377 | 24147.2475 | 53527.3682 | 61955.8385 |
| CALIBRATION | H4 | R85_B2 | 2024-11 | 1912223.42 | 0.53858493 | 219 | 8731.61377 | 24147.2475 | 53527.3682 | 61955.8385 |
| CALIBRATION | H24 | R85_B1 | ALL | 86214.3008 | 0.346833889 | 5 | 17242.8602 | 39490.725 | 46242.161 | 52993.597 |
| CALIBRATION | H24 | R85_B1 | 2024-11 | 86214.3008 | 0.346833889 | 5 | 17242.8602 | 39490.725 | 46242.161 | 52993.597 |
| CALIBRATION | H24 | R85_B2 | ALL | 87837.1471 | 0.353362483 | 5 | 17567.4294 | 39995.0988 | 47775.4921 | 55555.8854 |
| CALIBRATION | H24 | R85_B2 | 2024-11 | 87837.1471 | 0.353362483 | 5 | 17567.4294 | 39995.0988 | 47775.4921 | 55555.8854 |
| EXPOSED_EVALUATION | H4 | R85_B1 | ALL | 4223539.08 | 0.448199428 | 1102 | 3832.61259 | 15056.0659 | 17643.174 | 24649.0921 |
| EXPOSED_EVALUATION | H4 | R85_B1 | 2024-12 | 1157925.99 | 0.47851556 | 274 | 4226.00726 | 18815.3629 | 21524.9914 | 24649.0921 |
| EXPOSED_EVALUATION | H4 | R85_B1 | 2025-01 | 2417459.97 | 0.517030532 | 567 | 4263.59782 | 15771.5311 | 17430.3152 | 20878.1121 |
| EXPOSED_EVALUATION | H4 | R85_B1 | 2025-02 | 648153.126 | 0.278433451 | 261 | 2483.34531 | 4878.07208 | 15989.3554 | 16406.1415 |
| EXPOSED_EVALUATION | H4 | R85_B2 | ALL | 3862978.5 | 0.409936956 | 910 | 4245.03132 | 15434.9562 | 17543.4135 | 23119.7207 |
| EXPOSED_EVALUATION | H4 | R85_B2 | 2024-12 | 1123960.1 | 0.464479079 | 266 | 4225.41391 | 17951.594 | 21034.0015 | 23119.7207 |
| EXPOSED_EVALUATION | H4 | R85_B2 | 2025-01 | 2013818.13 | 0.430702256 | 402 | 5009.49784 | 15671.6224 | 17163.119 | 20531.5147 |
| EXPOSED_EVALUATION | H4 | R85_B2 | 2025-02 | 725200.269 | 0.311531342 | 242 | 2996.69533 | 4067.99248 | 15795.9852 | 16585.8489 |
| EXPOSED_EVALUATION | H24 | R85_B1 | ALL | 140180.516 | 0.208511673 | 15 | 9345.36771 | 15689.8704 | 17886.2359 | 22540.2529 |
| EXPOSED_EVALUATION | H24 | R85_B1 | 2024-12 | 48583.6616 | 0.270438455 | 4 | 12145.9154 | 20394.3341 | 21467.2935 | 22540.2529 |
| EXPOSED_EVALUATION | H24 | R85_B1 | 2025-01 | 77530.0223 | 0.239405774 | 9 | 8614.44692 | 14653.8948 | 15272.776 | 15891.6572 |
| EXPOSED_EVALUATION | H24 | R85_B1 | 2025-02 | 14066.8318 | 0.0833344883 | 2 | 7033.4159 | 12370.0814 | 13037.1646 | 13704.2478 |
| EXPOSED_EVALUATION | H24 | R85_B2 | ALL | 116305.766 | 0.172999149 | 14 | 8307.55475 | 15922.7045 | 16876.5161 | 17641.7561 |
| EXPOSED_EVALUATION | H24 | R85_B2 | 2024-12 | 42626.3898 | 0.237277608 | 5 | 8525.27796 | 16448.4935 | 17045.1248 | 17641.7561 |
| EXPOSED_EVALUATION | H24 | R85_B2 | 2025-01 | 65698.2462 | 0.202870308 | 8 | 8212.28078 | 13702.6003 | 15083.532 | 16464.4637 |
| EXPOSED_EVALUATION | H24 | R85_B2 | 2025-02 | 7981.13038 | 0.0472816783 | 1 | 7981.13038 | 7981.13038 | 7981.13038 | 7981.13038 |

25. overreservation

| phase | horizon | candidate | over_GPUh | TRAIN_Q95_anchor_over_GPUh | R6_static_U2_over_GPUh |
|---|---|---|---|---|---|
| CALIBRATION | H4 | R85_B1 | 2742534.65 | 3958371.46 | 2677543.48 |
| CALIBRATION | H4 | R85_B2 | 3127384.24 | 3958371.46 | 2677543.48 |
| CALIBRATION | H24 | R85_B1 | 144238.598 | 115479.76 | 400120.405 |
| CALIBRATION | H24 | R85_B2 | 165818.748 | 115479.76 | 400120.405 |
| EXPOSED_EVALUATION | H4 | R85_B1 | 8982247.66 | 13149881.8 | 10612434.7 |
| EXPOSED_EVALUATION | H4 | R85_B2 | 10000289.2 | 13149881.8 | 10612434.7 |
| EXPOSED_EVALUATION | H24 | R85_B1 | 527270.917 | 390803.885 | 1415858.66 |
| EXPOSED_EVALUATION | H24 | R85_B2 | 629008.161 | 390803.885 | 1415858.66 |

26. positive upper WAPE

| phase | horizon | candidate | positive_upper_WAPE |
|---|---|---|---|
| CALIBRATION | H4 | R85_B1 | 1.31987245 |
| CALIBRATION | H4 | R85_B2 | 1.41217651 |
| CALIBRATION | H24 | R85_B1 | 0.927095326 |
| CALIBRATION | H24 | R85_B2 | 1.0204393 |
| EXPOSED_EVALUATION | H4 | R85_B1 | 1.25313052 |
| EXPOSED_EVALUATION | H4 | R85_B2 | 1.40200791 |
| EXPOSED_EVALUATION | H24 | R85_B1 | 0.910072158 |
| EXPOSED_EVALUATION | H24 | R85_B2 | 1.02108582 |

27. H4 정적90 대비 rolling85

| phase | horizon | candidate | reference | positive_coverage_delta | mean_day_coverage_delta | under_GPUh_delta | over_GPUh_delta | upper_WAPE_delta | safe_to_actual_ratio_delta |
|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H4 | R85_B1 | R6_STATIC_U2_90 | -0.0181644359 | -0.0182716049 | -8156.88104 | 64991.171 | 0.0150121928 | {'median': -0.023177923347628138, 'P90': 8.994196413111588, 'P95': 16.934533923801624, 'P99': 408.70981667286014} |
| CALIBRATION | H4 | R85_B2 | R6_STATIC_U2_90 | 0.0100382409 | 0.00997150997 | -65204.253 | 449840.764 | 0.10731625 | {'median': 0.40606127984268614, 'P90': 6.128174242721421, 'P95': 21.853271155639533, 'P99': 143.2262276042361} |
| EXPOSED_EVALUATION | H4 | R85_B1 | R6_STATIC_U2_90 | -0.0329533031 | -0.0318909593 | 470752.493 | -1630187.02 | -0.200811535 | {'median': -0.93817921232601, 'P90': -10.720002895834732, 'P95': -30.369012548571035, 'P99': -656.3484795714393} |
| EXPOSED_EVALUATION | H4 | R85_B2 | R6_STATIC_U2_90 | -0.00296735905 | -0.00291983864 | 110191.914 | -612145.511 | -0.0519341447 | {'median': -0.17771600122963616, 'P90': -1.7182275151150534, 'P95': -3.658443480483129, 'P99': -113.04188490537285} |

28. H24 정적90 대비 rolling85

| phase | horizon | candidate | reference | positive_coverage_delta | mean_day_coverage_delta | under_GPUh_delta | over_GPUh_delta | upper_WAPE_delta | safe_to_actual_ratio_delta |
|---|---|---|---|---|---|---|---|---|---|
| CALIBRATION | H24 | R85_B1 | R6_STATIC_U2_90 | -0.115384615 | -0.115384615 | 35127.6748 | -255881.807 | -0.888077888 | {'median': -3.0439914713013243, 'P90': -3.7168619864432477, 'P95': -6.421737785036003, 'P99': -11.4494436586651} |
| CALIBRATION | H24 | R85_B2 | R6_STATIC_U2_90 | -0.115384615 | -0.115384615 | 36750.5211 | -234301.657 | -0.794733915 | {'median': -2.373607295099609, 'P90': -3.70648291329543, 'P95': -5.434143606533711, 'P99': -9.563309421405018} |
| EXPOSED_EVALUATION | H24 | R85_B1 | R6_STATIC_U2_90 | -0.13253012 | -0.13253012 | 121165.846 | -888587.74 | -1.06585045 | {'median': -2.0309857698623537, 'P90': -6.141994414593069, 'P95': -4.786577227210714, 'P99': -146.49724257727496} |
| EXPOSED_EVALUATION | H24 | R85_B2 | R6_STATIC_U2_90 | -0.120481928 | -0.120481928 | 97291.0966 | -786850.496 | -0.95483679 | {'median': -1.7025589700647386, 'P90': -4.767279895321704, 'P95': -5.34286011091365, 'P99': -219.12898104820738} |

29. bootstrap

{"status": "NOT_EXECUTED_SAFETY_FAIL", "draws": 0, "resampling_unit": "calendar day"}

30. 물리적 해석

Arriving GPU-service work [GPUh]. GPU 점유/개수 또는 IT/PCC 전력이 아니다. 미래 backlog 식 B[t+1]=B[t]+A[t]-S[t], S[t]=0.25*r[t]는 설명용이며 구현하지 않았다. 전기적 feasibility는 별도 계층이다.

31. interface proposal

추천 행 0개. proposal_only=TRUE, optimizer_use_allowed=FALSE. 실패 시 []이며 합성 job/runtime/GPU request/site/migration 없음.

32. 미래 workload 연구 종료

NO_MODEL_PROMOTED; FURTHER_FUTURE_WORKLOAD_MODEL_WORK=DEFER_UNTIL_NEW_DATA_OR_AUTHORITY. 현 authority 아래 CLOSED. R6R2/R7/새 모델/새 horizon/새 calibration family/service-level search를 생성하지 않는다.

33. May/shadow firewall

May scientific reads=0; Apr24–30 shadow=SEALED, scientific reads=0. Git/index/path 및 기존 provenance 메타데이터 접근은 NONZERO로 별도 공개.

34. optimizer/Gurobi/OpenDSS/Fresh 호출

각각 0/0/0/0회. rolling calibration은 잔차 풀 갱신이며 optimizer 재해결·rolling MPC가 아니다.

35. A0/A1/M1/MF

전체 상속 Git 범위 변경 0. 운영 순서 및 joint freeze/electrical layer 변경 없음.

36. migration/WAN/terminal/MESS

변경 없음. production q=5576.44921875 s; PF=.95; Q control=NO; electrical=HOLD; electrical B0-B3=NO; FULL_MAY=NO.

37. tests

사전 검증 84개 통과. 최종 과학 검증 103개 통과. receipt commit 후 --closure --read-only로 Git clean과 필수 산출물을 검증한다.

38. 재현성

{"entire_calibration_repeated_once": true, "new_model_fits": 0, "better_repeat_selection": false, "delta_sequence_max_difference": 0.0, "upper_prediction_max_difference": 0.0, "metrics_max_difference": 0.0, "rows": [{"phase": "CALIBRATION", "horizon": "H4", "candidate": "R85_B1", "metrics_max_difference": 0.0}, {"phase": "CALIBRATION", "horizon": "H4", "candidate": "R85_B2", "metrics_max_difference": 0.0}, {"phase": "CALIBRATION", "horizon": "H24", "candidate": "R85_B1", "metrics_max_difference": 0.0}, {"phase": "CALIBRATION", "horizon": "H24", "candidate": "R85_B2", "metrics_max_difference": 0.0}, {"phase": "EXPOSED_EVALUATION", "horizon": "H4", "candidate": "R85_B1", "metrics_max_difference": 0.0}, {"phase": "EXPOSED_EVALUATION", "horizon": "H4", "candidate": "R85_B2", "metrics_max_difference": 0.0}, {"phase": "EXPOSED_EVALUATION", "horizon": "H24", "candidate": "R85_B1", "metrics_max_difference": 0.0}, {"phase": "EXPOSED_EVALUATION", "horizon": "H24", "candidate": "R85_B2", "metrics_max_difference": 0.0}], "membership_proof_exact": true, "PASS": true}

39. 보호 범위

{"PASS": true, "inherited_file_count": 363, "changed_inherited_files": [], "entire_inherited_Git_diff_empty": true, "R6_90pct_result_and_predictions_unchanged": true}

40. 과학 커밋

FINAL_COMMIT_RECEIPT.json의 scientific_commit에 기록한다.

41. receipt 커밋

git log -1 --format=%H -- dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork/V40R6R1_FINAL_COMMIT_RECEIPT.json 으로 확정한다.

일별 무평활 delta 및 지원량 전개는 V40R6R1_DAILY_DELTA_SEQUENCE.csv와 원본 parquet ledger에 저장했다.
H1/H8와 15분 SHAPE_ONLY는 기존 R6 읽기 전용 진단으로 보존했으며 새 보정·학습·선택에 사용하지 않았다.
R6 static U2는 CAL_FIT에서 보정된 기존 비교 대상이다. R6R1의 CAL 평가는 전체 CAL에 대해 issue별로 인과적으로 실행되며, 비교 대상의 보정 과정을 다시 수행하지 않았다.
EXPOSED는 과거 prequential 진단이며 TRUE_CONFIRMATORY_AVAILABLE=NO다. 시간 의존성이 있는 window에 교환가능성 기반의 distribution-free coverage 보증을 주장하지 않는다.

사용 가능한 trace와 feature authority 아래 정확한 burst 예측과 누적 risk-calibrated reserve 예측은 사전 정의된 신뢰성·효율성 요건을 충족하지 못했다. 따라서 optimizer에 승격한 future-workload forecast는 없다.
이 결론은 해당 자료와 동결된 계약에 한정한다. 현재 authority의 미래 workload 모델 연구를 종료하고 새 데이터 또는 authority가 생길 때까지 유보한다.
