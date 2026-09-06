# V40K post-selection 진단

진단 분류: **CONDITIONAL_POINT_BIAS_REMAINS**. V40K의 **V40K_POINT_MODEL_INSUFFICIENT / winner NONE**은 그대로다.

이미 개봉한 13,060행의 저장된 예측만 사용했다. 모델 fit/predict, 새 candidate, threshold 변경, safe calibration, shadow open은 수행하지 않았다. Support는 기존 N=100 기준과 Apr01 이전 end-known 역사만 사용했다.

| K0 subgroup | N | Pinball50 s | MAE s | Underprediction | Mean residual s | Median residual s |
|---|---:|---:|---:|---:|---:|---:|
| overall | 13,060 | 3020.167 | 6040.335 | 50.061% | 2523.583 | 0.523 |
| H100 | 12,733 | 2971.562 | 5943.124 | 50.035% | 2363.145 | 0.523 |
| H100-standby | 2,291 | 6671.855 | 13343.709 | 48.058% | 2789.850 | -11.837 |
| retrospective COMPLETED H100 | 9,751 | 2045.446 | 4090.892 | 55.707% | 1725.917 | 25.744 |
| retrospective COMPLETED H100-standby | 1,301 | 4833.013 | 9666.026 | 61.107% | 1799.743 | 751.466 |
| walltime <=1h | 7,329 | 384.261 | 768.522 | 50.266% | 284.102 | 1.927 |
| walltime >1h to6h | 1,249 | 823.145 | 1646.291 | 55.725% | 1258.327 | 1.523 |
| walltime >6h to24h | 2,586 | 7486.633 | 14973.266 | 50.425% | 7189.909 | 8.544 |
| walltime >24h to72h | 1,877 | 8461.416 | 16922.831 | 45.232% | 5470.150 | -1621.946 |
| walltime >72h | 19 | 18764.050 | 37528.099 | 26.316% | 23346.579 | -7662.466 |
| 12h exact | 512 | 4780.657 | 9561.314 | 7.812% | -7106.204 | -8970.479 |
| 24h exact | 1,611 | 9273.404 | 18546.808 | 66.605% | 11824.663 | 2231.124 |
| 48h exact | 1,181 | 10565.151 | 21130.302 | 47.163% | 11833.404 | -1040.946 |
| STRONG_SUPPORT | 3,453 | 5141.841 | 10283.683 | 46.945% | 4115.666 | -4.011 |
| SPARSE_SUPPORT | 1,107 | 6008.954 | 12017.908 | 37.669% | 7992.528 | -265.443 |
| REGIME_MISMATCH | 1,456 | 1766.158 | 3532.317 | 39.423% | 2000.275 | -677.136 |
| OUT_OF_SUPPORT | 7,044 | 1769.615 | 3539.230 | 55.735% | 991.833 | 180.429 |
| H100 / STRONG_SUPPORT | 3,307 | 5171.303 | 10342.606 | 46.356% | 3904.564 | -6.035 |
| H100-standby / STRONG_SUPPORT | 1,772 | 6750.636 | 13501.272 | 43.341% | 3405.569 | -1553.446 |
| retrospective COMPLETED H100 / STRONG_SUPPORT | 2,091 | 4215.083 | 8430.167 | 57.293% | 3866.564 | 2.523 |
| retrospective COMPLETED H100-standby / STRONG_SUPPORT | 1,009 | 5266.551 | 10533.102 | 54.906% | 2019.991 | 458.691 |

| 주요 subgroup residual s | P5 | P25 | P50 | P75 | P90 | P95 | Positive-only Q90 | Positive-only Q95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | -12374.8 | -527.6 | 0.5 | 1514.4 | 5922.1 | 23001.5 | 22962.6 | 55454.2 |
| H100 | -12376.8 | -531.6 | 0.5 | 1517.4 | 5671.3 | 22250.8 | 22225.7 | 55453.2 |
| H100-standby | -19121.6 | -11547.4 | -11.8 | 6830.4 | 22025.4 | 42803.9 | 47214.0 | 86381.0 |
| retrospective COMPLETED H100 | -9102.5 | -419.4 | 25.7 | 1525.4 | 2922.4 | 15341.9 | 12271.7 | 29052.3 |
| retrospective COMPLETED H100-standby | -18743.6 | -4079.9 | 751.5 | 9640.1 | 20118.7 | 25922.1 | 22679.7 | 33715.3 |

V40I forensic COMPLETED H100 ≈64.13%, V40J development COMPLETED H100-standby ≈73.64%, V40K April pooled 50.061%, V40K April COMPLETED H100-standby 61.107%. Population과 time split이 다르므로 개선 추세처럼 합치지 않는다.

진단용 Wilson 95% 구간과 UTC-day block bootstrap 민감도는 JSON에 함께 기록했다. 이는 새 point selection gate가 아니다. 최종 status는 평가 층화에만 사용했으며, conditional error 진단은 기존 causal Q50 정의를 바꾸지 않는다.

| Candidate pooled delta vs K0 | Pinball delta s | MAE delta s | Median-calibration-error delta |
|---|---:|---:|---:|
| K1_HUBER_RESIDUAL | +462.738 | +925.477 | +0.248239 |
| K1_L1_RESIDUAL | +385.239 | +770.477 | +0.181240 |
| K1_Q50_RESIDUAL | +385.239 | +770.477 | +0.181240 |
| K2_NORMALIZED_Q50 | +799.626 | +1599.252 | +0.073124 |
| K3_SOFT_CDF_MEDIAN | +162.491 | +324.981 | +0.220368 |
| K4_INTERVAL_HAZARD | +358.604 | +717.208 | +0.135375 |
| K5_STACKING | +462.738 | +925.477 | +0.248239 |

Subgroup별 candidate delta와 requested-walltime-normalized residual, GPU active miss 전체 표는 JSON에 저장했다. 이 진단으로 winner를 재선정하거나 V40K holdout을 학습·튜닝에 재사용하지 않았다.
