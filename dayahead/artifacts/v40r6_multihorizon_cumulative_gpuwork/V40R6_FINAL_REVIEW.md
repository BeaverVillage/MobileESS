FINAL CLASSIFICATION: V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL
PRIMARY HORIZONS: H4, H24
SECONDARY HORIZONS: H1, H8
SELECTED MODEL FAMILY: NONE
SELECTED LGB CONFIG: L0
SELECTED H1 UPPER: NONE
SELECTED H4 UPPER: NONE
SELECTED H8 UPPER: NONE
SELECTED H24 UPPER: NONE
PRIMARY SAFETY: FAIL
FULL MULTI-HORIZON SAFETY: FAIL
OPTIMIZER INTEGRATION: NO
PRODUCTION READY: NO

아래 결과는 이미 노출된 과거 자료의 진단이다. 예측·안전성 실패와 코드/재현성 검증 통과를 구분한다.

1. lineage

ff1fec3a7d8f80b3c2af496758747fafc04bad7b → 488ca53a66e4babc4d3bd2ccca3f97dfb3433a0c → 5b2f6cea014110788147a3c0e2cf0d0a046c18b1 → 86f3bf3a588d0c31e109a14e97ec2efd122d4508 → 528716aa36b02bbe0ebff3cf9639984c6b2c535e

2. R5/R5R1 보존

R5=V40R5_BODY_FORECAST_INSUFFICIENT, selected_model=NONE 유지. R5R1=V40R5R1_ZERO_INFLATION_AWARE_EVALUATION_COMPLETE; 원본 바이트 및 전체 보호 Git 범위 변경 없음.

3. 15분 타깃 authority

{"SHA256": "be18f53ab8efc082f85dc519c5cb1efe0cc859cc3e8f58ddd99354196968a443", "expected_R5_preregistered_SHA256": "be18f53ab8efc082f85dc519c5cb1efe0cc859cc3e8f58ddd99354196968a443", "match": true, "native_intervals": 33504, "days": 349, "total_GPUh": 1904541.7783333336, "adjacent_pair_R4_max_error_GPUh": 2.9103830456733704e-11, "R4_authority": "R5 frozen inputs/causal_dataset.npz:target", "unit": "GPUh", "label_modifications": false}

4. 누적 타깃 개수

H1 32,457 / H4 28,269 / H8 22,685 / H24 349; 총 83,760행, 일별 240행.

5. 정확한 합산 identity

{"every_row_checked": 83760, "maximum_error_GPUh": 0.0, "mean_error_GPUh": 0.0, "H24_daily_sum_max_error_GPUh": 0.0, "tolerance_GPUh": 1e-07, "artificial_floating_correction": false, "PASS": true}

6. H1 분포

{"N": 32457, "mean": 230.23134103069705, "median": 17.041666666666664, "std": 1146.7055418608445, "P75": 123.4088888888889, "P90": 419.6732777777778, "P95": 849.7795555555549, "P99": 3697.0369222221866, "maximum": 53798.67749999993, "zero_fraction": 0.2775672428135687, "positive_fraction": 0.7224327571864313, "coefficient_of_variation": 4.980666562281599, "skewness": 20.948150899355294}

7. H4 분포

{"N": 28269, "mean": 943.6230333482694, "median": 289.99194444444436, "std": 2547.760910323095, "P75": 866.5733333333333, "P90": 2170.774944444445, "P95": 3765.9817222222146, "P99": 11245.889777777798, "maximum": 64130.885277777714, "zero_fraction": 0.1181506243588383, "positive_fraction": 0.8818493756411617, "coefficient_of_variation": 2.699977448921359, "skewness": 10.674218937263237}

8. H8 분포

{"N": 22685, "mean": 1914.300320133226, "median": 913.0244444444445, "std": 3729.0283375918466, "P75": 2067.7649999999994, "P90": 4474.105666666668, "P95": 6870.164277777785, "P99": 17826.435555555574, "maximum": 65919.22638888883, "zero_fraction": 0.08155168613621336, "positive_fraction": 0.9184483138637867, "coefficient_of_variation": 1.9479850148759963, "skewness": 7.4854830802876915}

9. H24 분포

{"N": 349, "mean": 5457.139765998091, "median": 3676.5869444444447, "std": 6384.724344659793, "P75": 7224.967500000001, "P90": 11887.208666666666, "P95": 16990.344111111102, "P99": 29475.70901111104, "maximum": 66246.27305555549, "zero_fraction": 0.045845272206303724, "positive_fraction": 0.9541547277936963, "coefficient_of_variation": 1.16997632797335, "skewness": 3.832923625879787}

10. 0값 비율

{"H1": 0.2775672428135687, "H4": 0.1181506243588383, "H8": 0.08155168613621336, "H24": 0.045845272206303724}

11. 게이트 수학적 가능성

전체 coverage 상한은 안전 게이트에서 제외. 각 H/분할의 양수 coverage 정수 격자까지 계산했으며 상세는 EVALUATION_GATE_FEASIBILITY_AUDIT.

12. 시간 분할

{"roles": {"TRAIN": {"start": "2024-03-15", "end": "2024-08-30", "eligible_days": 167}, "DEVELOPMENT": {"start": "2024-09-01", "end": "2024-10-30", "eligible_days": 58}, "CALIBRATION": {"start": "2024-11-01", "end": "2024-11-29", "eligible_days": 26}, "EXPOSED_EVALUATION": {"start": "2024-12-01", "end": "2025-02-26", "eligible_days": 88}}, "purged_days": [], "maturity_ledger_SHA256": "64fb7614531f7aabbc6c76741299c7023b23421906485c341087d4c6d42140ed", "same_parent_rows": true}

13. CAL_FIT/CAL_SELECT

CAL 달력 2024-11-01~15 / 2024-11-16~29. 유효일은 15일/11일. 기존 성숙도 제외 11/26, 11/28, 11/29는 복원하지 않음. 원래 stage cutoff에 따른 오프라인 평가.

14. 특징 authority

R5 61개 특징을 각 window 시작 슬롯에서 그대로 사용. 시작 슬롯/시간폭 2개와 성숙한 7/14/21/28일 누적 lag 및 mask 8개를 추가해 71개. 미래 실현 count/runtime/severity, classifier 출력, 새 외부 입력 없음.

15. 성숙도 증명

83,760개 window의 inherited availability <= issue와 각 lag 전체의 latest raw availability < issue를 저장·독립 재계산했다. 실제 telemetry ingestion 지연까지 보증하는 자료는 아니다.

16. B0

최근 이용 가능한 7/14/21/28일 동일 window 중심값. 없는 경우 인과적으로 성숙한 TRAIN 동일 window 중앙값 → horizon 중앙값 → 0. 중심 예측 기준선 전용.

17. B1

TRAIN만 사용하고 각 issue 이전에 완전히 성숙한 날만 참조. horizon/start/weekday → horizon/start → horizon → TRAIN horizon fallback; support 8/20/50/1. Q50/Q90 empirical linear quantile.

18. B2

H1/H4/H8/H24별 Q50/Q90 LightGBM. CPU 1 thread, seed 20260907. TRAIN log1p 타깃에 학습; expm1 역변환. 실질적 음수값은 절단하지 않고 NEGATIVE_PREDICTION_AUDIT에 기록.

19. 하이퍼파라미터 비교

| config | mean_normalized_pinball | mean_Q90_normalized_pinball | mean_Q50_MAE | simplicity |
|---|---|---|---|---|
| L0 | 0.73256643 | 0.79098294 | 1638.1441 | 0 |
| L2 | 0.75653973 | 0.83328393 | 1698.6326 | 2 |
| L1 | 0.75724601 | 0.84072291 | 1638.1913 | 1 |

20. 공통 선택 설정

L0; {"num_leaves": 15, "learning_rate": 0.03, "n_estimators": 400, "min_child_samples": 50}; DEV-only, CAL/EXPOSED 재선택 없음.

21. horizon별 Q50

| horizon | family | MAE | RMSE | WAPE | bias | positive_MAE | positive_WAPE |
|---|---|---|---|---|---|---|---|
| H1 | B0 | 500.55243 | 1823.8674 | 1.5562635 | -25.849006 | 593.35792 | 1.4298135 |
| H1 | B1 | 311.20772 | 1405.6861 | 0.9675734 | -295.53591 | 397.08083 | 0.95684495 |
| H1 | B2 | 308.95043 | 1406.2396 | 0.96055528 | -300.0266 | 397.03325 | 0.95673031 |
| H4 | B0 | 1686.6139 | 3851.7821 | 1.275787 | -190.53018 | 1781.0985 | 1.2102253 |
| H4 | B1 | 1186.3533 | 3158.1366 | 0.89738027 | -1103.4175 | 1296.5699 | 0.88099659 |
| H4 | B2 | 1121.3829 | 3103.3894 | 0.8482354 | -1005.0284 | 1237.9906 | 0.84119293 |
| H8 | B0 | 3098.99 | 5610.2506 | 1.13666 | -409.04587 | 3219.7867 | 1.0808319 |
| H8 | B1 | 2297.1387 | 4754.8588 | 0.84255378 | -2107.878 | 2452.2059 | 0.8231671 |
| H8 | B2 | 2143.3757 | 4538.238 | 0.78615596 | -1704.9468 | 2296.099 | 0.77076444 |
| H24 | B0 | 6668.7434 | 9402.7715 | 0.87290985 | -1795.3286 | 6659.0919 | 0.82212115 |
| H24 | B1 | 5662.5209 | 8689.1939 | 0.74119965 | -5114.5429 | 5851.5438 | 0.72242252 |
| H24 | B2 | 4988.8625 | 7983.9547 | 0.65302067 | -4193.6937 | 5201.0341 | 0.64211159 |

22. horizon별 Q90/upper

| horizon | candidate | positive_coverage | positive_pinball | positive_MAE | positive_WAPE | overall_coverage_DIAGNOSTIC |
|---|---|---|---|---|---|---|
| H1 | U0 | 0.73782122 | 278.98813 | 488.83697 | 1.1779496 | 0.79679863 |
| H1 | U1 | 0.75311367 | 270.1608 | 459.23932 | 1.1066282 | 0.80865103 |
| H1 | U2 | 0.88790793 | 253.75457 | 736.43134 | 1.7745773 | 0.91312317 |
| H4 | U0 | 0.76214275 | 758.46502 | 1506.3779 | 1.0235575 | 0.78633558 |
| H4 | U1 | 0.7388724 | 785.76295 | 1386.3725 | 0.94201589 | 0.7654321 |
| H4 | U2 | 0.86084648 | 682.85638 | 2139.7785 | 1.4539421 | 0.875 |
| H8 | U0 | 0.72798472 | 1295.3647 | 2609.831 | 0.87607936 | 0.75104895 |
| H8 | U1 | 0.65062082 | 1421.9413 | 2304.183 | 0.77347811 | 0.68024476 |
| H8 | U2 | 0.9243553 | 1055.0778 | 6433.6928 | 2.1596898 | 0.93076923 |
| H24 | U0 | 0.57831325 | 2773.9932 | 4808.2806 | 0.59362286 | 0.60227273 |
| H24 | U1 | 0.62650602 | 2711.9984 | 4988.6937 | 0.61589638 | 0.64772727 |
| H24 | U2 | 0.95180723 | 1783.7498 | 16004.758 | 1.9759226 | 0.95454545 |

23. crossing 감사

| phase | config | horizon | raw_crossing_count | raw_crossing_fraction | N | repair | post_crossing_count |
|---|---|---|---|---|---|---|---|
| DEVELOPMENT | L0 | H1 | 27 | 0.0050055617 | 5394 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L0 | H4 | 52 | 0.01106854 | 4698 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L0 | H8 | 157 | 0.041644562 | 3770 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L0 | H24 | 0 | 0 | 58 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L1 | H1 | 84 | 0.015572859 | 5394 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L1 | H4 | 312 | 0.066411239 | 4698 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L1 | H8 | 160 | 0.042440318 | 3770 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L1 | H24 | 0 | 0 | 58 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L2 | H1 | 19 | 0.0035224323 | 5394 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L2 | H4 | 305 | 0.064921243 | 4698 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L2 | H8 | 92 | 0.024403183 | 3770 | Q90=max(Q90_raw,Q50_raw) | 0 |
| DEVELOPMENT | L2 | H24 | 0 | 0 | 58 | Q90=max(Q90_raw,Q50_raw) | 0 |
| CAL_FIT_CAL_SELECT | L0 | H1 | 0 | 0 | 2418 | Q90=max(Q90_raw,Q50_raw) | 0 |
| CAL_FIT_CAL_SELECT | L0 | H4 | 0 | 0 | 2106 | Q90=max(Q90_raw,Q50_raw) | 0 |
| CAL_FIT_CAL_SELECT | L0 | H8 | 16 | 0.0094674556 | 1690 | Q90=max(Q90_raw,Q50_raw) | 0 |
| CAL_FIT_CAL_SELECT | L0 | H24 | 0 | 0 | 26 | Q90=max(Q90_raw,Q50_raw) | 0 |
| EXPOSED_EVALUATION | L0 | H1 | 0 | 0 | 8184 | Q90=max(Q90_raw,Q50_raw) | 0 |
| EXPOSED_EVALUATION | L0 | H4 | 74 | 0.010381594 | 7128 | Q90=max(Q90_raw,Q50_raw) | 0 |
| EXPOSED_EVALUATION | L0 | H8 | 337 | 0.058916084 | 5720 | Q90=max(Q90_raw,Q50_raw) | 0 |
| EXPOSED_EVALUATION | L0 | H24 | 0 | 0 | 88 | Q90=max(Q90_raw,Q50_raw) | 0 |

24. horizon별 보정 delta

{"H1": 0.8027171081334946, "H4": 0.6759847992968178, "H8": 1.2911352452031426, "H24": 1.1408130820355156}

25. CAL_SELECT 양수 coverage

| horizon | candidate | positive_coverage | gate_PASS | failure_reasons |
|---|---|---|---|---|
| H1 | U0 | 0.73006834 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month |
| H1 | U1 | 0.69134396 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month / development_skill |
| H1 | U2 | 0.84738041 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / development_skill |
| H4 | U0 | 0.77288136 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month |
| H4 | U1 | 0.70282486 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month / development_skill |
| H4 | U2 | 0.86666667 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / development_skill |
| H8 | U0 | 0.79440559 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month |
| H8 | U1 | 0.67412587 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month / development_skill |
| H8 | U2 | 0.90629371 | False | over_GPUh_below_TRAIN_Q95_anchor / development_skill |
| H24 | U0 | 0.72727273 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month |
| H24 | U1 | 0.54545455 | False | positive_coverage_lower / mean_day_coverage / supported_month_day_coverage / no_catastrophic_month / development_skill |
| H24 | U2 | 1 | False | positive_coverage_upper / over_GPUh_below_TRAIN_Q95_anchor / development_skill |

26. day-cluster coverage

| horizon | candidate | supported_days | mean_supported_day_coverage |
|---|---|---|---|
| H1 | U0 | 11 | 0.72488664 |
| H1 | U1 | 11 | 0.68818772 |
| H1 | U2 | 11 | 0.84747405 |
| H4 | U0 | 11 | 0.77306397 |
| H4 | U1 | 11 | 0.70428732 |
| H4 | U2 | 11 | 0.86756453 |
| H8 | U0 | 11 | 0.79440559 |
| H8 | U1 | 11 | 0.67412587 |
| H8 | U2 | 11 | 0.90629371 |
| H24 | U0 | 11 | 0.72727273 |
| H24 | U1 | 11 | 0.54545455 |
| H24 | U2 | 11 | 1 |

27. under GPUh

| horizon | candidate | under_GPUh | positive_under_GPUh |
|---|---|---|---|
| H1 | U0 | 201037.68 | 201037.68 |
| H1 | U1 | 213229.34 | 213229.34 |
| H1 | U2 | 158009.91 | 158009.91 |
| H4 | U0 | 457829.42 | 457829.42 |
| H4 | U1 | 565677.7 | 565677.7 |
| H4 | U2 | 396845.28 | 396845.28 |
| H8 | U0 | 598133.26 | 598133.26 |
| H8 | U1 | 863149.32 | 863149.32 |
| H8 | U2 | 342678.74 | 342678.74 |
| H24 | U0 | 23721.411 | 23721.411 |
| H24 | U1 | 24807.779 | 24807.779 |
| H24 | U2 | 0 | 0 |

28. over GPUh

| horizon | candidate | over_GPUh | TRAIN_Q95_anchor_over_GPUh |
|---|---|---|---|
| H1 | U0 | 183264.69 | 428928.78 |
| H1 | U1 | 117840.27 | 428928.78 |
| H1 | U2 | 339470.71 | 428928.78 |
| H4 | U0 | 632203.7 | 1627466.3 |
| H4 | U1 | 344325.81 | 1627466.3 |
| H4 | U2 | 998361.17 | 1627466.3 |
| H8 | U0 | 966986.84 | 2145850.5 |
| H8 | U1 | 381003.89 | 2145850.5 |
| H8 | U2 | 3081269.2 | 2145850.5 |
| H24 | U0 | 16435.6 | 47197.654 |
| H24 | U1 | 21597.777 | 47197.654 |
| H24 | U2 | 161783.47 | 47197.654 |

29. 양수 upper WAPE

| horizon | candidate | positive_WAPE |
|---|---|---|
| H1 | U0 | 1.1138652 |
| H1 | U1 | 0.98497845 |
| H1 | U2 | 1.4413534 |
| H4 | U0 | 1.0132784 |
| H4 | U1 | 0.84629246 |
| H4 | U2 | 1.2965078 |
| H8 | U0 | 0.91912645 |
| H8 | U1 | 0.73063666 |
| H8 | U2 | 2.0107346 |
| H24 | U0 | 0.49769636 |
| H24 | U1 | 0.57513932 |
| H24 | U2 | 2.0051055 |

30. H1 선택

NONE; CAL_SELECT frozen hierarchy.

31. H4 선택

NONE; CAL_SELECT frozen hierarchy.

32. H8 선택

NONE; CAL_SELECT frozen hierarchy.

33. H24 선택

NONE; CAL_SELECT frozen hierarchy.

34. 선택 동결 커밋

11ff08052da5231e2dc66eac5e28f064dfed83d2

35. EXPOSED 결과

V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL; 동결된 NONE은 그대로 유지하며, U0/U1/U2 진단을 결과 후 추천으로 사용하지 않음.

36. 2024-12 월별 안정성

| horizon | candidate | days | positive_windows | pooled_positive_coverage | mean_day_coverage | under_GPUh | over_GPUh | Q50_WAPE | upper_WAPE |
|---|---|---|---|---|---|---|---|---|---|
| H1 | U0 | 31 | 1829 | 0.74521597 | 0.77162263 | 514621.56 | 672825.51 | 1.0048962 | 1.2610549 |
| H1 | U1 | 31 | 1829 | 0.72389284 | 0.74400838 | 531749.14 | 382151.44 | 0.97447195 | 1.1024931 |
| H1 | U2 | 31 | 1829 | 0.85073811 | 0.86300826 | 444342.72 | 983845.65 | 0.97447195 | 1.5929472 |
| H4 | U0 | 31 | 1842 | 0.79967427 | 0.81699201 | 1302218.5 | 2473514 | 0.95690459 | 1.1597763 |
| H4 | U1 | 31 | 1842 | 0.74429967 | 0.76022996 | 1442385.9 | 1249810.9 | 0.89720637 | 0.99595775 |
| H4 | U2 | 31 | 1842 | 0.85559175 | 0.86574752 | 1114745.3 | 3076052.6 | 0.89720637 | 1.5023604 |
| H8 | U0 | 31 | 1533 | 0.8297456 | 0.84031887 | 1454526 | 3899687.8 | 0.89792771 | 1.08979 |
| H8 | U1 | 31 | 1533 | 0.66601435 | 0.69084484 | 1888220.8 | 1459063.9 | 0.86828611 | 0.85265864 |
| H8 | U2 | 31 | 1533 | 0.91324201 | 0.91605851 | 829545.97 | 8627692.5 | 0.86828611 | 2.3348576 |
| H24 | U0 | 31 | 26 | 0.73076923 | 0.73076923 | 69752.519 | 107933.35 | 0.80501034 | 0.80598768 |
| H24 | U1 | 31 | 26 | 0.65384615 | 0.65384615 | 75835.59 | 97356.171 | 0.80777785 | 0.77467724 |
| H24 | U2 | 31 | 26 | 0.92307692 | 0.92307692 | 11214.277 | 461150.97 | 0.80777785 | 2.0366904 |

37. 2025-01 월별 안정성

| horizon | candidate | days | positive_windows | pooled_positive_coverage | mean_day_coverage | under_GPUh | over_GPUh | Q50_WAPE | upper_WAPE |
|---|---|---|---|---|---|---|---|---|---|
| H1 | U0 | 31 | 2466 | 0.72952149 | 0.72940321 | 931962.09 | 574478.76 | 0.96412647 | 1.1237195 |
| H1 | U1 | 31 | 2466 | 0.76723439 | 0.76692532 | 889074.35 | 604638.58 | 0.96516194 | 1.1159903 |
| H1 | U2 | 31 | 2466 | 0.89659367 | 0.89680875 | 732228.92 | 1669528.4 | 0.96516194 | 1.7585303 |
| H4 | U0 | 31 | 2469 | 0.70554881 | 0.70716209 | 2705947.9 | 1767619.2 | 0.89790975 | 0.94818525 |
| H4 | U1 | 31 | 2469 | 0.72093965 | 0.72560733 | 2679488.2 | 1750012.5 | 0.85234284 | 0.93757747 |
| H4 | U2 | 31 | 2469 | 0.84163629 | 0.84428515 | 1937279.2 | 4628925.4 | 0.85234284 | 1.3851105 |
| H8 | U0 | 31 | 2012 | 0.61182903 | 0.61240695 | 4240068.3 | 2248311.2 | 0.85258502 | 0.7934652 |
| H8 | U1 | 31 | 2012 | 0.57852883 | 0.57915633 | 4457244.5 | 1694535.5 | 0.77141396 | 0.75263067 |
| H8 | U2 | 31 | 2012 | 0.89214712 | 0.89230769 | 1542348.5 | 13032219 | 0.77141396 | 1.7821705 |
| H24 | U0 | 31 | 31 | 0.4516129 | 0.4516129 | 133915.05 | 38528.107 | 0.76199214 | 0.53248903 |
| H24 | U1 | 31 | 31 | 0.5483871 | 0.5483871 | 126730.47 | 48435.668 | 0.64251031 | 0.54089735 |
| H24 | U2 | 31 | 31 | 0.93548387 | 0.93548387 | 7800.3923 | 452421.49 | 0.64251031 | 1.421124 |

38. 2025-02 월별 안정성

| horizon | candidate | days | positive_windows | pooled_positive_coverage | mean_day_coverage | under_GPUh | over_GPUh | Q50_WAPE | upper_WAPE |
|---|---|---|---|---|---|---|---|---|---|
| H1 | U0 | 26 | 2048 | 0.74121094 | 0.7374363 | 377856.92 | 454338.9 | 0.93390486 | 1.1938464 |
| H1 | U1 | 26 | 2048 | 0.76220703 | 0.76050192 | 357094.54 | 397046.85 | 0.93650135 | 1.0928308 |
| H1 | U2 | 26 | 2048 | 0.91064453 | 0.91013503 | 251486.9 | 1147239.7 | 0.93650135 | 2.0024845 |
| H4 | U0 | 26 | 2092 | 0.7958891 | 0.79494364 | 856730.77 | 1559543.5 | 0.83444067 | 1.033347 |
| H4 | U1 | 26 | 2092 | 0.75525813 | 0.75447968 | 1057558.3 | 1035190.2 | 0.78907951 | 0.89485768 |
| H4 | U2 | 26 | 2092 | 0.88814532 | 0.88811728 | 700762.1 | 2907456.7 | 0.78907951 | 1.5418636 |
| H8 | U0 | 26 | 1690 | 0.7739645 | 0.7739645 | 1074140.4 | 2243415.9 | 0.77085687 | 0.85457843 |
| H8 | U1 | 26 | 1690 | 0.72248521 | 0.72248521 | 1451563.4 | 1440519.3 | 0.74211984 | 0.74497951 |
| H8 | U2 | 26 | 1690 | 0.97278107 | 0.97278107 | 322223.23 | 10523265 | 0.74211984 | 2.7937191 |
| H24 | U0 | 26 | 26 | 0.57692308 | 0.57692308 | 34248.321 | 47601.938 | 0.63339752 | 0.48489593 |
| H24 | U1 | 26 | 26 | 0.69230769 | 0.69230769 | 27046.085 | 72680.33 | 0.50848205 | 0.59079755 |
| H24 | U2 | 26 | 26 | 1 | 1 | 0 | 502286.2 | 0.50848205 | 2.9756354 |

39. H4 최종 안전성

False; {"selected": "NONE", "DEV_central_and_positive_pinball_skill_pass": false, "CAL_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill"], "U2": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "development_skill"]}, "EXPOSED_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill", "under_GPUh_vs_B1"], "U2": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "development_skill"]}, "frozen_selected_exposed_pass": false}

40. H24 최종 안전성

False; {"selected": "NONE", "DEV_central_and_positive_pinball_skill_pass": false, "CAL_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill"], "U2": ["positive_coverage_upper", "over_GPUh_below_TRAIN_Q95_anchor", "development_skill"]}, "EXPOSED_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill"], "U2": ["over_GPUh_below_TRAIN_Q95_anchor", "development_skill"]}, "frozen_selected_exposed_pass": false}

41. H1/H8 진단

{"H1": {"selected": "NONE", "DEV_central_and_positive_pinball_skill_pass": false, "CAL_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill"], "U2": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "development_skill"]}, "EXPOSED_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill"], "U2": ["positive_coverage_lower", "supported_month_day_coverage", "over_GPUh_below_TRAIN_Q95_anchor", "development_skill"]}, "frozen_selected_exposed_pass": false}, "H8": {"selected": "NONE", "DEV_central_and_positive_pinball_skill_pass": false, "CAL_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill"], "U2": ["over_GPUh_below_TRAIN_Q95_anchor", "development_skill"]}, "EXPOSED_candidate_failures": {"U0": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month"], "U1": ["positive_coverage_lower", "mean_day_coverage", "supported_month_day_coverage", "no_catastrophic_month", "development_skill", "under_GPUh_vs_B1"], "U2": ["over_GPUh_below_TRAIN_Q95_anchor", "development_skill"]}, "frozen_selected_exposed_pass": false}}

42. 15분 central shape

{"status": "SHAPE_ONLY", "source": "Frozen R5 DEV-selected B3 full-target Q50", "prediction_SHA256": "a9504b8f4d5d7605e516e8b407fd49246cadc563e7c9864e5d7feb9cecb72045", "new_R6_family": false, "new_model_fits": 0, "15MIN_SAFETY_FORECAST": false, "Q90_burst_safety_claim": false, "results": {"DEVELOPMENT": {"overall": {"N": 5568, "MAE": 59.18707259124898, "RMSE": 384.14454061580585, "WAPE": 1.0016369089620127, "bias": -58.750827843113456, "error_sum_GPUh": -327124.6094304557}, "positive": {"N": 2410, "MAE": 136.60640795857194, "RMSE": 583.8891913289126, "WAPE": 1.0006272985949736, "bias": -135.87418524413766, "error_sum_GPUh": -327456.78643837175}}, "CALIBRATION": {"overall": {"N": 2496, "MAE": 99.87258466527203, "RMSE": 1309.878549427461, "WAPE": 1.002843320032907, "bias": -98.92582134756371, "error_sum_GPUh": -246918.85008351904}, "positive": {"N": 1301, "MAE": 191.22606952324753, "RMSE": 1814.3096446787176, "WAPE": 1.0008445088491484, "bias": -190.1734857481115, "error_sum_GPUh": -247415.70495829303}}, "EXPOSED_EVALUATION": {"overall": {"N": 8448, "MAE": 79.63516731269074, "RMSE": 657.1941019941863, "WAPE": 1.0006945184079126, "bias": -78.6405716355376, "error_sum_GPUh": -664355.5491770216}, "positive": {"N": 4592, "MAE": 146.33929615987822, "RMSE": 891.3835455638417, "WAPE": 0.999552385730242, "bias": -144.84394483198432, "error_sum_GPUh": -665123.394668472}}}}

43. bootstrap

{"status": "NOT_EXECUTED_SAFETY_FAIL", "resampling_unit": "calendar day", "draws": 0}

44. 확인 검증 상태

TRUE_CONFIRMATORY_AVAILABLE=NO. 최대 허용 해석은 PREVALIDATED이며 EXPOSED는 독립 확증이 아니다.

45. interface proposal

recommended_rows=0; proposal_only=TRUE, optimizer_use_allowed=FALSE.

46. GPUh 물리 의미

누적 도착 GPU 서비스 작업량이다. 순간 GPU 점유/개수 또는 IT/PCC 전력이 아니다. 미래 B[t+1]=B[t]+A[t]-S[t], S[t]=0.25*r[t] backlog 연결이 필요하지만 이번에는 구현하지 않았다.

47. May/shadow firewall

May scientific reads=0, Apr24–30 shadow scientific reads=0, SEALED. Git 경로/index·기존 provenance 메타데이터 접근은 NONZERO로 별도 공개. 초기 sparse checkout으로 materialize된 R4 자료에는 과학적 row query 없음.

48. optimizer/Gurobi/OpenDSS/Fresh

모두 0회. 새 optimizer/전기 계산 호출 없음.

49. 시스템 동결

A0/A1/M1/MF/migration/WAN/terminal 포함 전체 상속 Git 범위 변경 0. q=5576.44921875 s, PF=.95, Q control=NO, electrical=HOLD, FULL_MAY=NO.

50. tests

PREFIT 79 checks PASS. POSTFIT 113 checks PASS. 최종 TEST_REPORT 및 receipt에 postfit/closure 실제 결과를 기록. 과학적 안전성 판정과 별개.

51. 동일 seed 재현성

최종 8개 모델 독립 재학습 1회. CAL과 EXPOSED Q50/Q90/calibrated upper의 최대·평균 차이는 각 재현성 감사에 기록.

52. 보호 범위

R5/R5R1 모든 materialized 파일 SHA256와 전체 inherited Git diff를 검사하여 변경 0. R6 source/artifacts/tests만 추가.

53. 과학 커밋

FINAL_COMMIT_RECEIPT.json의 scientific_commit에서 정확한 SHA를 확인한다.

54. receipt 커밋

git log -1 --format=%H -- dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/V40R6_FINAL_COMMIT_RECEIPT.json 으로 최종 receipt commit을 독립 확인한다.

실행 교정 공개: 첫 L0/H1/Q50의 음수 출력에서 임의 중단하던 실행 검사를 제거했다. 모델·expm1 변환·지표·안전 게이트는 변경하지 않았고 첫 모델 바이트를 재사용했다. 교정 커밋은 EXECUTION_CORRECTION_COMMIT_RECEIPT에서 확인할 수 있다.
처음 모델의 학습 소요시간은 프로세스 중단 전에 저장되지 않아 null로 남겼다. 전체 32개 적합 중 나머지 31개 시간만 합산한다.
실패 결과를 미래 workload 예측 불가능성으로 일반화하지 않는다. 중앙 예측 skill, upper coverage, 시간 안정성, 과예약 중 실제 실패 항목을 구분한다.
