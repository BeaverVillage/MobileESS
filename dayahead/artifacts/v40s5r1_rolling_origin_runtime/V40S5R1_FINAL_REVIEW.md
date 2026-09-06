FINAL CLASSIFICATION: V40S5R1_ROLLING_DIRECT_RUNTIME_SAFETY_FAIL
SELECTED MODEL: R5_UARP_STYLE
SELECTED CANDIDATE: R5_UARP_STYLE
S5 STATIC RESULT: V40S5_DIRECT_RUNTIME_SAFETY_FAIL
S5R1 ROLLING RESULT: V40S5R1_ROLLING_DIRECT_RUNTIME_SAFETY_FAIL
INITIAL HISTORICAL TRAINING JOBS: 421
FINAL HISTORICAL TRAINING JOBS: 72291
ROLLING UPDATE MATERIAL IMPROVEMENT: ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME
DEV SAFETY: PASS
CAL SAFETY: PASS
EXPOSED SAFETY: FAIL
EFFICIENCY VS REQUESTED WALLTIME: see frozen gate table
CURRENT RSP REPLACED: NO
OPTIMIZER INTEGRATION: NO
PRODUCTION READY: NO


S5 scientific 788832de4d622bf4ab95189cc8943769bd3b3eae, 최종 receipt fb541bb421a7313d6debf2c7f9c00c8a5c037a89와 clean Git·필수 artifact·receipt 검증을 먼저 확인한 후 독립 branch codex/v40s5r1-rolling-origin-runtime을 만들었다. S5 source/models/predictions/classification은 변경하지 않았다. S5는 고정된 static 실험으로 보존한다.

S5에서 초기 mature 이력은 421개, HIST_FIT/HIST_TUNE는 332/89개였다. 고정 direct-runtime 후보가 안전성에 실패했다는 결과와, 과거 이력이 약 8시간에 집중됐다는 자료 한계를 구분했다. 이번 실험은 모델군 추가 없이 학습 갱신 정책만 expanding-origin으로 바꿨다.

S4/S5 PENDING 파일 SHA256 fbd99e403891139150441c7374640ae5607a8671e9c511cc52f92f3959e795b7의 동일 바이트를 사용했다. TRAIN/DEV/CAL/EXPOSED job-issue 수는 1,190/4,346/2,634/2,713, 합계 10,883, 고유 작업 7,603이다. 순서도 동일하다. 실제 패널에 있는 36개 08:00 UTC issue만 사용했고 빈 날짜를 새로 생성하지 않았다. 고정 AEST D-1 18:00 계약이다.

처음/마지막 학습 작업 수는 421/72,291개다. 모든 issue에서 source/cohort가 같은 unique 작업 중 end_time < issue_time, runtime=end-start>0 finite, S5 feature 구성 가능 조건을 적용했다. end==issue는 제외했다. 과거 작업은 버리지 않았고 새로운 작업의 end는 이전 issue 이상, 현재 issue 미만임을 전수 검증했다.

Arrow scanner는 end_time predicate를 내부에서 평가하지만 Python에 전달되는 scientific training row는 해당 시각 이전 완료 작업뿐이다. 현재 평가의 start/end/runtime은 P와 P-W 예측 파일을 저장·해시·검증한 뒤에만 열었다. 이벤트 로그는 FIT→PREDICT→HASH→LABEL READ→SCORE 순서를 기록한다. S5와 이전 대화의 역사 결과가 이미 노출됐으므로 이 검사는 R1 실행의 데이터 흐름 인과성에 대한 검증이며 untouched holdout이라는 뜻은 아니다.

최종 분위수 4개와 residual regression은 S5의 L2를 그대로 사용했다: num_leaves=31, learning_rate=.02, n_estimators=800, min_child_samples=100, reg_alpha=0, reg_lambda=1, subsample=1, colsample_bytree=1, CPU, n_jobs=1, seed=4005. 하이퍼파라미터 선택은 0회다. 잔차 OOF Q50은 S5에 동결된 L0 보조 모델을 그대로 사용했다.

Track P features: requested_seconds, num_gpus_req, num_nodes_req, num_cores_req, requested_memory_mib, partition, qos, submit_hour, submit_dow. user/account/job/application identity, actual start/end/runtime/status, K0/reference-safe, migration/전기 결과는 predictor에서 제외했다. D1_SCHEDULER_REQUEST_STATE_PROXY_V1, 과거 D1 및 최초 submission provenance UNVERIFIED, request modification history UNOBSERVED를 유지한다.

전처리는 매 issue의 D_train에서만 fit했다. request 수량 5개는 log1p, continuous missing은 해당 이력 median+indicator, partition/qos는 이력 vocabulary와 UNKNOWN one-hot이다. 각 OOF fold도 해당 validation보다 일찍 끝난 부분집합으로만 전처리한다. 전역 미래 전처리·target encoding은 없다.

S5와 동일하게 raw runtime seconds를 예측하고 사전등록된 max(raw,0) 하한 후 Q50→Q90→Q95→Q99 누적 max를 적용했다. raw 값과 crossing/보정량은 모두 저장했다. 요청 walltime이나 기간 상한은 적용하지 않았다.

잔차 crossfit은 N≥250이면 5개 expanding fold, 100≤N<250이면 3개, N<100이면 중단하도록 사전등록했다. 실제 모든 issue는 5-fold 경로다. 각 residual row를 예측한 Q50은 그 작업 및 이후 완료 작업을 학습하지 않았다. warmup block은 residual target에서 제외한다. sigma=sqrt(max(predicted_r2,0)), UARP=Q99+max(.20×Q99,.50×sigma)이며 계수 변화는 없다.

UARP 식의 문헌 연결은 S5에서 검증한 [Choi & Oh (2026), §4.3–4.4](https://link.springer.com/article/10.1007/s11227-026-08422-8)를 유지한다. 이번 결과는 해당 논문의 데이터나 scheduler 결과 재현이 아니다.

일별 학습 증가와 사전 지정 UARP 진단 결과:

| UTC issue 날짜 | split | N_train | 추가 작업 | N_eval | coverage | GPU coverage | MAE 초 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-03-14 | TRAIN | 421 | 421 | 275 | 5.82% | 14.86% | 9,724.037 |
| 2025-03-15 | TRAIN | 2202 | 1781 | 16 | 100.00% | 100.00% | 56,106.665 |
| 2025-03-16 | TRAIN | 2864 | 662 | 3 | 100.00% | 100.00% | 82,435.397 |
| 2025-03-17 | TRAIN | 3309 | 445 | 48 | 83.33% | 88.24% | 77,851.005 |
| 2025-03-18 | TRAIN | 8354 | 5045 | 53 | 94.34% | 94.34% | 72,942.755 |
| 2025-03-19 | TRAIN | 9201 | 847 | 24 | 100.00% | 100.00% | 80,872.832 |
| 2025-03-20 | TRAIN | 10640 | 1439 | 366 | 93.99% | 95.76% | 30,542.660 |
| 2025-03-21 | TRAIN | 11879 | 1239 | 405 | 99.75% | 99.70% | 43,612.268 |
| 2025-03-22 | DEVELOPMENT | 13285 | 1406 | 720 | 98.89% | 98.96% | 43,208.456 |
| 2025-03-23 | DEVELOPMENT | 15036 | 1751 | 338 | 98.52% | 98.93% | 33,197.797 |
| 2025-03-24 | DEVELOPMENT | 16103 | 1067 | 744 | 100.00% | 100.00% | 103,186.648 |
| 2025-03-25 | DEVELOPMENT | 18442 | 2339 | 235 | 91.06% | 91.06% | 13,015.334 |
| 2025-03-26 | DEVELOPMENT | 20085 | 1643 | 501 | 100.00% | 100.00% | 44,625.180 |
| 2025-03-27 | DEVELOPMENT | 20554 | 469 | 555 | 100.00% | 100.00% | 51,642.704 |
| 2025-03-28 | DEVELOPMENT | 20597 | 43 | 567 | 99.82% | 99.72% | 54,737.804 |
| 2025-03-29 | DEVELOPMENT | 25939 | 5342 | 624 | 100.00% | 100.00% | 36,177.407 |
| 2025-03-30 | DEVELOPMENT | 35376 | 9437 | 62 | 100.00% | 100.00% | 55,272.001 |
| 2025-04-02 | CALIBRATION | 44910 | 9534 | 229 | 97.82% | 98.24% | 56,611.183 |
| 2025-04-03 | CALIBRATION | 46477 | 1567 | 716 | 95.95% | 96.74% | 49,816.731 |
| 2025-04-04 | CALIBRATION | 47491 | 1014 | 312 | 98.72% | 98.77% | 70,506.182 |
| 2025-04-05 | CALIBRATION | 49373 | 1882 | 292 | 94.52% | 96.64% | 54,435.953 |
| 2025-04-06 | CALIBRATION | 51706 | 2333 | 911 | 93.30% | 97.86% | 28,082.834 |
| 2025-04-07 | CALIBRATION | 54981 | 3275 | 174 | 100.00% | 100.00% | 79,234.349 |
| 2025-04-10 | EXPOSED_EVALUATION | 57775 | 2794 | 123 | 89.43% | 85.31% | 124,942.767 |
| 2025-04-11 | EXPOSED_EVALUATION | 64572 | 6797 | 45 | 100.00% | 100.00% | 169,809.207 |
| 2025-04-12 | EXPOSED_EVALUATION | 65603 | 1031 | 398 | 100.00% | 100.00% | 46,821.619 |
| 2025-04-13 | EXPOSED_EVALUATION | 66902 | 1299 | 542 | 97.42% | 97.40% | 39,587.031 |
| 2025-04-14 | EXPOSED_EVALUATION | 68059 | 1157 | 215 | 100.00% | 100.00% | 53,260.503 |
| 2025-04-16 | EXPOSED_EVALUATION | 69069 | 1010 | 7 | 100.00% | 100.00% | 94,085.560 |
| 2025-04-17 | EXPOSED_EVALUATION | 69815 | 746 | 6 | 100.00% | 100.00% | 61,632.709 |
| 2025-04-18 | EXPOSED_EVALUATION | 70459 | 644 | 596 | 100.00% | 100.00% | 31,971.222 |
| 2025-04-19 | EXPOSED_EVALUATION | 71000 | 541 | 545 | 100.00% | 100.00% | 34,944.951 |
| 2025-04-20 | EXPOSED_EVALUATION | 71605 | 605 | 90 | 100.00% | 100.00% | 41,395.549 |
| 2025-04-21 | EXPOSED_EVALUATION | 72067 | 462 | 140 | 100.00% | 100.00% | 36,953.723 |
| 2025-04-22 | EXPOSED_EVALUATION | 72282 | 215 | 5 | 100.00% | 100.00% | 78,323.781 |
| 2025-04-23 | EXPOSED_EVALUATION | 72291 | 9 | 1 | 100.00% | 100.00% | 178,628.317 |

DEVELOPMENT 후보 결과. GPU under 단위는 GPU·초, GPU over는 GPU·시간이다.

| 후보 | coverage | GPU coverage | GPU under | GPU over | 안전성 | 효율성 |
| --- | --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 66.27% | 71.73% | 48,173,935.178 | 45,388.015 | anchor | anchor |
| R1_RECORDED_REQUESTED_WALLTIME | 98.04% | 95.26% | 3,356.000 | 237,173.455 | anchor | anchor |
| R2_Q90 | 84.70% | 83.72% | 31,923,769.970 | 30,309.439 | False | True |
| R3_Q95 | 88.89% | 88.54% | 21,652,964.460 | 57,767.284 | False | True |
| R4_Q99 | 93.95% | 93.70% | 3,951,264.074 | 87,534.886 | False | True |
| R5_UARP_STYLE | 99.19% | 99.30% | 1,147,895.092 | 119,401.354 | True | True |

DEVELOPMENT 분위수 정확도: pinball은 raw, MAE/WAPE/bias는 고정 보정 후.

| Q | MAE 초 | WAPE | bias 초 | raw pinball |
| --- | --- | --- | --- | --- |
| Q50 | 10,765.479 | 42.90% | -1,131.126 | 5,382.994 |
| Q90 | 16,267.227 | 64.82% | 9,387.852 | 4,304.317 |
| Q95 | 27,350.158 | 108.98% | 22,678.311 | 3,586.467 |
| Q99 | 38,842.185 | 154.78% | 37,694.841 | 970.208 |

CALIBRATION 후보 결과. GPU under 단위는 GPU·초, GPU over는 GPU·시간이다.

| 후보 | coverage | GPU coverage | GPU under | GPU over | 안전성 | 효율성 |
| --- | --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 84.13% | 90.51% | 32,834,240.735 | 11,716.042 | anchor | anchor |
| R1_RECORDED_REQUESTED_WALLTIME | 98.71% | 98.09% | 241,373.000 | 147,600.691 | anchor | anchor |
| R2_Q90 | 76.08% | 88.51% | 15,993,462.871 | 19,286.234 | False | True |
| R3_Q95 | 80.64% | 91.08% | 10,551,672.506 | 28,406.552 | False | True |
| R4_Q99 | 87.36% | 95.10% | 4,006,845.478 | 52,266.403 | False | True |
| R5_UARP_STYLE | 95.63% | 98.27% | 2,186,583.407 | 89,188.400 | True | True |

CALIBRATION 분위수 정확도: pinball은 raw, MAE/WAPE/bias는 고정 보정 후.

| Q | MAE 초 | WAPE | bias 초 | raw pinball |
| --- | --- | --- | --- | --- |
| Q50 | 9,414.481 | 66.96% | -3,688.617 | 4,710.089 |
| Q90 | 16,760.368 | 119.21% | 10,561.756 | 4,234.458 |
| Q95 | 21,348.272 | 151.84% | 17,374.897 | 3,071.551 |
| Q99 | 36,918.032 | 262.58% | 34,842.826 | 1,472.578 |

EXPOSED_EVALUATION 후보 결과. GPU under 단위는 GPU·초, GPU over는 GPU·시간이다.

| 후보 | coverage | GPU coverage | GPU under | GPU over | 안전성 | 효율성 |
| --- | --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 34.32% | 38.65% | 33,086,831.036 | 3,410.337 | anchor | anchor |
| R1_RECORDED_REQUESTED_WALLTIME | 93.03% | 92.88% | 6,881.000 | 52,182.568 | anchor | anchor |
| R2_Q90 | 95.39% | 95.11% | 5,066,812.588 | 30,916.577 | False | True |
| R3_Q95 | 96.61% | 96.09% | 4,487,204.342 | 39,466.404 | False | True |
| R4_Q99 | 97.86% | 97.35% | 1,567,687.580 | 48,509.777 | False | True |
| R5_UARP_STYLE | 99.00% | 98.57% | 283,115.450 | 65,340.554 | False | False |

EXPOSED_EVALUATION 분위수 정확도: pinball은 raw, MAE/WAPE/bias는 고정 보정 후.

| Q | MAE 초 | WAPE | bias 초 | raw pinball |
| --- | --- | --- | --- | --- |
| Q50 | 8,398.494 | 57.51% | -1,555.840 | 4,206.278 |
| Q90 | 21,388.270 | 146.45% | 20,174.634 | 2,623.642 |
| Q95 | 26,570.599 | 181.94% | 25,573.988 | 1,991.364 |
| Q99 | 33,823.311 | 231.60% | 33,461.953 | 652.401 |

안전성은 각 DEV와 CAL에서 coverage≥90%, GPU coverage≥90%, N≥100 issue-day의 두 coverage≥88%, GPU under<RSP를 모두 요구한다. 효율성은 각 split에서 GPU over<recorded requested walltime이다. coverage 상한 게이트는 없고 >99.5%는 보수성 경고다. CAL GPU over 최소→CAL GPU under→DEV+CAL GPU over→단순성 순으로만 선택했다.

선택 결과는 R5_UARP_STYLE이다. 사전등록 커밋 8efc9b5316af1c1d75d8913ba67563cf33ae37e7, 선택 동결 커밋 682388356c74dfe59dfa0e1de07f3705ffc3c147를 각각 첫 rolling fit 및 첫 rolling EXPOSED issue 이전에 완료했다. EXPOSED 중에는 후보·설정·feature·계수·전처리 정책·학습 window를 바꾸지 않았다.

이전 EXPOSED issue의 작업도 현재 issue 전에 완료됐으면 현재 학습에 포함했다. 이 성숙 규칙은 원본 전체 같은 cohort에 동일하게 적용했다. 이후 issue의 결과가 이전 예측에 영향을 주는 경로는 없다. EXPOSED PREQUENTIAL HISTORICAL EVIDENCE이며 TRUE_CONFIRMATORY_AVAILABLE=NO다.

동일 후보에서 rolling−static S5 변화:

| split | 후보 | coverage Δpp | GPU coverage Δpp | GPU under Δ | GPU over Δ | material 진단 |
| --- | --- | --- | --- | --- | --- | --- |
| TRAIN | R2_Q90 | 48.571 | 45.623 | -17,855,097.377 | 7,639.114 | True |
| TRAIN | R3_Q95 | 52.353 | 48.466 | -16,430,976.140 | 9,575.848 | True |
| TRAIN | R4_Q99 | 57.731 | 52.437 | -18,074,754.661 | 15,997.969 | True |
| TRAIN | R5_UARP_STYLE | 56.387 | 49.729 | -17,464,335.299 | 20,966.313 | True |
| DEVELOPMENT | R2_Q90 | 41.647 | 37.982 | -114,026,795.004 | 27,576.721 | True |
| DEVELOPMENT | R3_Q95 | 45.145 | 41.757 | -116,616,498.694 | 53,769.327 | True |
| DEVELOPMENT | R4_Q99 | 50.115 | 46.836 | -132,818,518.294 | 83,034.477 | True |
| DEVELOPMENT | R5_UARP_STYLE | 53.359 | 49.993 | -131,236,435.233 | 113,772.192 | True |
| CALIBRATION | R2_Q90 | 23.197 | 11.502 | -39,755,954.558 | 13,102.939 | True |
| CALIBRATION | R3_Q95 | 16.439 | 9.305 | -42,892,782.950 | 20,054.597 | True |
| CALIBRATION | R4_Q99 | 17.654 | 11.424 | -49,045,664.379 | 40,911.041 | True |
| CALIBRATION | R5_UARP_STYLE | 22.020 | 12.342 | -49,576,435.801 | 75,140.375 | True |
| EXPOSED_EVALUATION | R2_Q90 | 71.913 | 66.493 | -62,369,351.107 | 29,136.238 | True |
| EXPOSED_EVALUATION | R3_Q95 | 69.996 | 65.669 | -58,887,607.858 | 36,955.096 | True |
| EXPOSED_EVALUATION | R4_Q99 | 70.660 | 66.296 | -60,203,853.432 | 45,128.610 | True |
| EXPOSED_EVALUATION | R5_UARP_STYLE | 70.697 | 65.615 | -58,255,348.383 | 61,053.163 | True |

material은 coverage 또는 GPU coverage가 동일 static 후보보다 10%p 이상 좋아지는 사전등록 진단이다. 안전성 게이트를 대체하지 않는다. 주 진단 대상은 결과를 보기 전에 R5_UARP_STYLE로 고정했다. 주 해석은 ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME.

학습량–성능의 일별 Spearman 상관은 인과관계가 아니다. 마지막 EXPOSED issue는 N_eval=1이므로 마지막 하루만으로 성능을 판단하지 않는다.

| 후보 | 최소 N | 중앙 N | 최대 N | N vs coverage | N vs GPU coverage | N vs MAE |
| --- | --- | --- | --- | --- | --- | --- |
| R2_Q90 | 421 | 45693.5 | 72291 | 0.231 | 0.321 | 0.062 |
| R3_Q95 | 421 | 45693.5 | 72291 | 0.397 | 0.472 | 0.096 |
| R4_Q99 | 421 | 45693.5 | 72291 | 0.328 | 0.350 | 0.092 |
| R5_UARP_STYLE | 421 | 45693.5 | 72291 | 0.405 | 0.406 | 0.078 |

훈련 composition과 평가 runtime/request/actual-request/GPU 분포 및 partition/QoS 빈도를 issue 또는 split별로 저장했다. EXPOSED 월·ISO 주별 결과도 분리했다. 표본 수와 분포 이동의 영향을 단독 원인으로 분리해 입증한 실험은 아니다.

| EXPOSED 구간 | N_eval | 학습 N 시작/끝 | 후보 | coverage | GPU coverage | GPU under | GPU over |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-04 | 2713 | 57775/72291 | R2_Q90 | 95.39% | 95.11% | 5,066,812.588 | 30,916.577 |
| 2025-04 | 2713 | 57775/72291 | R3_Q95 | 96.61% | 96.09% | 4,487,204.342 | 39,466.404 |
| 2025-04 | 2713 | 57775/72291 | R4_Q99 | 97.86% | 97.35% | 1,567,687.580 | 48,509.777 |
| 2025-04 | 2713 | 57775/72291 | R5_UARP_STYLE | 99.00% | 98.57% | 283,115.450 | 65,340.554 |
| 2025-W15 | 1108 | 57775/66902 | R2_Q90 | 95.31% | 93.42% | 4,195,817.727 | 13,690.885 |
| 2025-W15 | 1108 | 57775/66902 | R3_Q95 | 96.21% | 94.40% | 3,930,472.422 | 18,368.059 |
| 2025-W15 | 1108 | 57775/66902 | R4_Q99 | 96.75% | 95.20% | 1,416,221.903 | 23,042.412 |
| 2025-W15 | 1108 | 57775/66902 | R5_UARP_STYLE | 97.56% | 96.44% | 283,115.450 | 30,666.124 |
| 2025-W16 | 1459 | 68059/71605 | R2_Q90 | 95.27% | 96.20% | 853,909.687 | 16,516.700 |
| 2025-W16 | 1459 | 68059/71605 | R3_Q95 | 96.57% | 97.11% | 556,731.920 | 20,048.186 |
| 2025-W16 | 1459 | 68059/71605 | R4_Q99 | 98.49% | 98.74% | 151,465.677 | 24,277.040 |
| 2025-W16 | 1459 | 68059/71605 | R5_UARP_STYLE | 100.00% | 100.00% | 0.000 | 33,078.939 |
| 2025-W17 | 146 | 72067/72291 | R2_Q90 | 97.26% | 97.26% | 17,085.174 | 708.992 |
| 2025-W17 | 146 | 72067/72291 | R3_Q95 | 100.00% | 100.00% | 0.000 | 1,050.160 |
| 2025-W17 | 146 | 72067/72291 | R4_Q99 | 100.00% | 100.00% | 0.000 | 1,190.325 |
| 2025-W17 | 146 | 72067/72291 | R5_UARP_STYLE | 100.00% | 100.00% | 0.000 | 1,595.491 |

P-W는 동일 일별 membership·모델 설정·residual 방법·수식에서 requested_seconds와 그 indicator만 제거한 1회 고정 민감도다. 운영 후보가 될 수 없고 별도 tuning/selection은 없다.

| split | Q50 MAE Δ(PW−P) | Q90 pinball Δ | Q95 Δ | Q99 Δ | UARP coverage Δpp | GPU coverage Δpp |
| --- | --- | --- | --- | --- | --- | --- |
| TRAIN | 1,683.330 | 664.954 | -1,639.151 | -330.116 | 1.176 | 0.496 |
| DEVELOPMENT | 6,167.043 | 261.094 | 597.116 | 1,200.561 | -2.646 | -3.297 |
| CALIBRATION | 464.822 | -139.767 | 50.128 | 613.356 | 1.405 | 0.401 |
| EXPOSED_EVALUATION | 1,142.814 | 981.273 | 470.446 | 288.973 | -1.180 | -1.112 |

requested_seconds grouped gain은 모든 일별 quantile/residual 모델에서 기록했다. permutation은 사전 지정 5일에 해당 issue 이전 historical 80/20 slice만 사용해 3회 순열을 적용했다. feature 선택·변경에는 사용하지 않았다. 전체 시계열은 WALLTIME_DEPENDENCE_ANALYSIS.json에 있다.

| 날짜 | 모델 | walltime gain 비중 | historical permutation loss Δ |
| --- | --- | --- | --- |
| 2025-03-14 | Q50 | 40.80% | 30.494 |
| 2025-03-14 | Q90 | 12.19% | 13.450 |
| 2025-03-14 | Q95 | 37.25% | -10.019 |
| 2025-03-14 | Q99 | 22.90% | -16.354 |
| 2025-03-14 | RESIDUAL | 49.58% | -3,845,551,013,649.990 |
| 2025-03-22 | Q50 | 44.20% | 3,449.388 |
| 2025-03-22 | Q90 | 15.52% | 4,280.736 |
| 2025-03-22 | Q95 | 15.70% | 3,223.725 |
| 2025-03-22 | Q99 | 8.24% | 4,110.060 |
| 2025-03-22 | RESIDUAL | 25.64% | 15,599,000,655,248,955,392.000 |
| 2025-04-02 | Q50 | 5.13% | 570.041 |
| 2025-04-02 | Q90 | 31.25% | 1,939.123 |
| 2025-04-02 | Q95 | 20.33% | 1,769.321 |
| 2025-04-02 | Q99 | 11.52% | 1,961.141 |
| 2025-04-02 | RESIDUAL | 27.96% | 2,660,509,363,882,597,888.000 |
| 2025-04-10 | Q50 | 9.72% | 3,259.297 |
| 2025-04-10 | Q90 | 26.44% | 4,063.672 |
| 2025-04-10 | Q95 | 17.58% | 4,178.801 |
| 2025-04-10 | Q99 | 15.97% | 3,393.755 |
| 2025-04-10 | RESIDUAL | 37.47% | -1,265,755,375,954,404,096.000 |
| 2025-04-23 | Q50 | 13.01% | 1,291.564 |
| 2025-04-23 | Q90 | 29.49% | 3,174.869 |
| 2025-04-23 | Q95 | 24.40% | 3,727.334 |
| 2025-04-23 | Q99 | 16.07% | 3,222.850 |
| 2025-04-23 | RESIDUAL | 48.53% | 6,093,342,293,070,221,312.000 |

15분 완료 슬롯은 actual/candidate 각각 ceil(seconds/900)를 한 번 적용했다. EXPOSED의 signed/weighted 지표도 모두 저장했다.

| 후보 | slot MAE | signed error | ≥1 slot early | ≥4 | ≥8 | GPU ≥1 early |
| --- | --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 9.411 | -4.516 | 64.98% | 51.38% | 36.34% | 60.67% |
| R1_RECORDED_REQUESTED_WALLTIME | 41.382 | 41.243 | 6.97% | 0.00% | 0.00% | 7.12% |
| R2_Q90 | 23.721 | 22.349 | 4.50% | 3.32% | 2.32% | 4.79% |
| R3_Q95 | 29.601 | 28.483 | 3.02% | 2.47% | 1.77% | 3.55% |
| R4_Q99 | 37.729 | 37.313 | 1.99% | 1.62% | 0.92% | 2.51% |
| R5_UARP_STYLE | 50.327 | 50.247 | 0.92% | 0.88% | 0.00% | 1.36% |

Unique-job는 split별 earliest issue만 사용한 보조 진단이며 재선택하지 않았다.

| split | 고유 작업 N | UARP coverage | GPU coverage | GPU under | GPU over |
| --- | --- | --- | --- | --- | --- |
| TRAIN | 1160 | 74.74% | 84.23% | 3,965,096.294 | 21,238.221 |
| DEVELOPMENT | 2893 | 98.96% | 99.23% | 1,009,480.057 | 91,686.427 |
| CALIBRATION | 1738 | 93.79% | 97.56% | 1,203,605.013 | 49,036.818 |
| EXPOSED_EVALUATION | 1812 | 98.51% | 97.95% | 283,115.450 | 41,109.763 |

일별 sigma·UARP margin·quantile crossing은 다음과 같다. 음수 predicted_r2는 고정 식대로 0으로 내려 sigma를 계산했으며 raw 결과를 숨기거나 재조정하지 않았다.

| 날짜 | sigma median | sigma P99 | 음수 r2 N | A≥B | B>A | raw crossing N | 보정후 N |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-03-14 | 2,269.489 | 2,269.489 | 0 | 100.00% | 0.00% | 0 | 0 |
| 2025-03-15 | 3,793.790 | 3,793.790 | 3 | 100.00% | 0.00% | 1 | 0 |
| 2025-03-16 | 12,294.325 | 13,650.029 | 1 | 100.00% | 0.00% | 3 | 0 |
| 2025-03-17 | 27,085.724 | 57,586.618 | 0 | 70.83% | 29.17% | 48 | 0 |
| 2025-03-18 | 33,135.990 | 33,135.990 | 0 | 100.00% | 0.00% | 0 | 0 |
| 2025-03-19 | 30,010.554 | 109,205.687 | 1 | 8.33% | 91.67% | 5 | 0 |
| 2025-03-20 | 6,500.150 | 45,070.328 | 2 | 64.48% | 35.52% | 120 | 0 |
| 2025-03-21 | 17,259.528 | 33,342.950 | 0 | 7.41% | 92.59% | 1 | 0 |
| 2025-03-22 | 20,154.188 | 131,905.731 | 1 | 12.08% | 87.92% | 8 | 0 |
| 2025-03-23 | 8,139.619 | 28,297.257 | 90 | 98.82% | 1.18% | 87 | 0 |
| 2025-03-24 | 25,268.487 | 50,519.696 | 1 | 97.85% | 2.15% | 653 | 0 |
| 2025-03-25 | 33,167.553 | 33,167.553 | 0 | 0.00% | 100.00% | 0 | 0 |
| 2025-03-26 | 49,094.687 | 49,094.687 | 100 | 20.16% | 79.84% | 0 | 0 |
| 2025-03-27 | 12,241.480 | 113,538.447 | 108 | 92.25% | 7.75% | 136 | 0 |
| 2025-03-28 | 13,567.131 | 114,250.396 | 110 | 89.07% | 10.93% | 158 | 0 |
| 2025-03-29 | 0.000 | 20,344.788 | 527 | 99.36% | 0.64% | 525 | 0 |
| 2025-03-30 | 13,959.073 | 201,770.559 | 0 | 93.55% | 6.45% | 1 | 0 |
| 2025-04-02 | 17,587.720 | 119,653.476 | 1 | 94.76% | 5.24% | 1 | 0 |
| 2025-04-03 | 21,763.778 | 100,660.747 | 1 | 5.59% | 94.41% | 245 | 0 |
| 2025-04-04 | 16,237.868 | 104,011.253 | 0 | 97.44% | 2.56% | 6 | 0 |
| 2025-04-05 | 13,600.903 | 85,274.696 | 17 | 92.12% | 7.88% | 21 | 0 |
| 2025-04-06 | 0.000 | 51,239.937 | 550 | 81.34% | 18.66% | 717 | 0 |
| 2025-04-07 | 18,158.647 | 40,560.505 | 0 | 94.83% | 5.17% | 9 | 0 |
| 2025-04-10 | 22,326.695 | 98,796.498 | 32 | 88.62% | 11.38% | 64 | 0 |
| 2025-04-11 | 81,228.145 | 147,753.927 | 2 | 8.89% | 91.11% | 1 | 0 |
| 2025-04-12 | 21,991.356 | 83,444.338 | 2 | 27.89% | 72.11% | 109 | 0 |
| 2025-04-13 | 7,360.150 | 66,997.947 | 6 | 79.34% | 20.66% | 178 | 0 |
| 2025-04-14 | 25,652.580 | 73,107.132 | 6 | 18.14% | 81.86% | 139 | 0 |
| 2025-04-16 | 32,498.692 | 40,286.922 | 2 | 100.00% | 0.00% | 1 | 0 |
| 2025-04-17 | 9,940.131 | 29,683.311 | 1 | 100.00% | 0.00% | 5 | 0 |
| 2025-04-18 | 19,354.595 | 19,354.595 | 0 | 0.17% | 99.83% | 0 | 0 |
| 2025-04-19 | 11,476.635 | 27,460.046 | 1 | 89.36% | 10.64% | 33 | 0 |
| 2025-04-20 | 16,941.989 | 38,441.993 | 1 | 74.44% | 25.56% | 20 | 0 |
| 2025-04-21 | 18,002.225 | 29,253.322 | 0 | 0.71% | 99.29% | 1 | 0 |
| 2025-04-22 | 38,972.918 | 38,972.918 | 0 | 20.00% | 80.00% | 0 | 0 |
| 2025-04-23 | 23,211.971 | 23,211.971 | 0 | 100.00% | 0.00% | 0 | 0 |

May runtime/outcome/feature fitting/training/selection/calibration/sensitivity scientific reads=0. Apr24–30 shadow=SEALED, scientific reads=0. Git 경로/index/blob identity 및 schema 메타데이터 discovery는 nonzero로 별도 공개했다.

Optimizer/Gurobi/OpenDSS/Fresh calls=0. A0/A1/M1/MF·RUNNING·migration·WAN·Rack·terminal·MESS route/PQ·AC restoration·event trigger·local repair·rolling MPC·second route search 변경=0. rolling-origin ML은 rolling MPC와 연결하지 않았다.

production q=5576.44921875s, PF=.95, Q control=NO, electrical=HOLD, B0–B3=NO, FULL_MAY=NO, optimizer integration=NO를 유지한다. Adapter는 proposal_only=true, optimizer_use_allowed=false이며 recommended_rows=[]다.

pytest 124개 통과, 실패/오류/skip=0. 실행 전 단위 테스트 34개와 첫 issue의 static S5 예측 완전 일치도 검증했다. 최소 88개 요청 항목을 테스트 및 최종 receipt 검증에 연결했다. 사전 지정 5개 issue에서 전체 P 모델 패키지를 각각 1회 독립 재학습했고 Q50/Q90/Q95/Q99/sigma/UARP 최대·평균 차이는 모두 0, 모델 및 OOF 파일 SHA도 동일하다. 더 나은 repeat 선택은 하지 않았다.

CPU 1 thread, seed 4005. 환경 {"Python": "3.11.7 (tags/v3.11.7:fa7a6f2, Dec  4 2023, 19:24:49) [MSC v.1937 64 bit (AMD64)]", "executable": "C:\\codex_mobileess_workspace\\v40s2_runtime_env\\Scripts\\python.exe", "CPU": "Intel64 Family 6 Model 186 Stepping 2, GenuineIntel", "device": "CPU", "threads": 1, "seed": 4005, "libraries": {"numpy": "2.2.6", "pandas": "2.2.3", "scikit-learn": "1.6.1", "lightgbm": "4.6.0", "pyarrow": "18.1.0", "scipy": "1.15.3"}}. 일별 P/PW 모델 패키지는 각 36개, 독립 repeat는 5개, historical permutation 진단 패키지는 5개다. 총 fit 795회, 학습 905.368s, 추론(모델 읽기 포함) 13.996s. Cache 재사용은 0이다.

기존 Git 항목 5,615개 전체를 보존했고 변경 경로는 지정 S5R1 source/artifacts/tests 내부뿐이다. scientific 및 receipt 커밋은 FINAL_COMMIT_RECEIPT.json과 해당 파일의 git log에서 독립 확인한다.

일별 인과적 모델 갱신은 static S5 대비 runtime 예측을 사전등록된 기준에서 실질적으로 개선했지만, 미리 정한 reliability–efficiency 요건은 충족하지 못했다. 초기 historical maturity 부족은 S5 실패와 관련된 중요한 요인이었지만 표본 수가 유일한 원인이었다고 입증하지 않았다.

원본은 기존 exposed terminal-service complete-case extract이며 full cluster backlog 또는 검증된 scheduler snapshot이 아니다. 이 결과를 runtime prediction의 일반적 불가능성이나 보편적 성공으로 확대하지 않는다.

CURRENT_RSP_REMAINS_OPERATIONAL. FURTHER_RUNTIME_MODEL_PROLIFERATION=NO. FURTHER_RUNTIME_MODEL_WORK=DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA. 실패에 따라 S5R2/S6·추가 quantile·계수 조정·새 모델군·BODY/tail·user별 모델을 만들지 않는다. 향후 재검토에는 검증된 snapshot, 더 긴 pre-study history, 승인된 application/job context, full backlog/censoring/status 또는 progress/checkpoint 자료가 필요하다.
