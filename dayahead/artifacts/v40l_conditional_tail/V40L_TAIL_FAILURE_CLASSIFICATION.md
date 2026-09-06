# V40L post-selection tail failure diagnostic

추가 진단 분류: **MIXED_FAILURE**. 기존 **V40L_TAIL_MODEL_INSUFFICIENT / winner NONE / shadow SEALED**는 유지한다.

새 fit/runtime prediction/threshold/support-rule/conformal retuning은 0회다. 이미 저장된 selection 예측과 기존 동결 support lookup만 사용했다.

T7은 overall 90.827%, H100 90.373%, 전체 H100-standby 91.268%, GPU-weighted 91.385%다. 유일한 필수 gate 실패는 strong-support H100-standby의 **N=4 <100**이다. 관측 4/4=100%를 충분한 검증으로 인정하지 않았다.

Conservatism의 절대 FAIL threshold는 사전등록에 없다. 모든 후보가 필수 gate를 통과하지 못해 efficiency 순위 단계는 도달하지 않았다. T7의 overreservation 증가를 사후 hard gate로 만들지 않는다.

| Candidate | Overall Q90 | H100 Q90 | H100-standby Q90 | Support-sufficient standby Q90 | GPU Q90 | Active-miss GPU slots | GPU-underprediction seconds | Overreserved GPUh | Mean inflation s | Crossing raw→repaired | Abstentions | Historical insufficient jobs | Required insufficient groups |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T0 | 56.937% | 53.913% | 14.579% | 75.000% (N=4) | 65.988% | 231,224 | 69,370,623.697 | 13,469.540 | 5,576.449 | 0→0 | 0 | 3164 | 1 |
| T1 | 69.875% | 67.826% | 36.978% | 100.000% (N=4) | 72.555% | 144,438 | 43,341,547.645 | 47,099.461 | 19,929.228 | 384→0 | 0 | 3164 | 1 |
| T2 | 85.391% | 84.565% | 78.967% | 100.000% (N=4) | 86.904% | 64,003 | 19,202,587.637 | 58,095.984 | 26,574.427 | 1030→0 | 0 | 3164 | 1 |
| T3_R | 65.742% | 63.571% | 36.598% | 100.000% (N=4) | 65.330% | 146,137 | 43,853,205.126 | 46,239.695 | 19,474.240 | 0→0 | 0 | 3164 | 1 |
| T3_D | 76.699% | 77.112% | 74.487% | 100.000% (N=4) | 76.018% | 73,371 | 22,015,927.102 | 53,662.122 | 24,084.963 | 0→0 | 0 | 3164 | 1 |
| T4_N100 | 52.633% | 50.031% | 16.249% | 75.000% (N=4) | 57.795% | 165,879 | 49,781,864.070 | 82,190.363 | 20,767.856 | 0→0 | 0 | 3164 | 1 |
| T4_N200 | 52.633% | 50.031% | 16.249% | 75.000% (N=4) | 57.795% | 165,879 | 49,781,864.070 | 82,190.363 | 20,767.856 | 0→0 | 0 | 3164 | 1 |
| T4_N500 | 51.076% | 47.888% | 11.010% | 75.000% (N=4) | 57.162% | 168,720 | 50,638,311.533 | 82,134.295 | 20,446.436 | 0→0 | 0 | 3164 | 1 |
| T5 | NOT EVALUATED: censor authority unavailable | — | — | — | — | — | — | — | — | — | — | — | — |
| T6 | 79.502% | 78.478% | 63.705% | 100.000% (N=4) | 85.439% | 48,504 | 14,552,482.180 | 123,488.099 | 38,958.236 | 0→0 | 0 | 3164 | 1 |
| T7 | 90.827% | 90.373% | 91.268% | 100.000% (N=4) | 91.385% | 49,898 | 14,960,009.137 | 61,659.654 | 31,814.359 | 0→0 | 0 | 3164 | 1 |
| T8_N100 | 29.304% | 27.547% | 9.188% | 100.000% (N=4) | 25.348% | 94,132 | 28,244,175.197 | 11,063.142 | 11,838.952 | 0→0 | 1164 | 3164 | 1 |
| T8_N200 | 29.304% | 27.547% | 9.188% | 100.000% (N=4) | 25.348% | 94,132 | 28,244,175.197 | 11,063.142 | 11,838.952 | 0→0 | 1164 | 3164 | 1 |
| T8_N500 | 29.388% | 27.547% | 9.188% | 100.000% (N=4) | 25.397% | 94,061 | 28,226,168.449 | 11,078.209 | 11,861.784 | 0→0 | 1164 | 3164 | 1 |

| Candidate | Overall ≥90%, N≥100 | H100 ≥90%, N≥100 | Support standby ≥90%, N≥100 | GPU ≥90% | Abstentions=0 | Repaired crossings=0 | Safe<K0 violations=0 | Efficiency |
|---|---|---|---|---|---|---|---|---|
| T0 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T1 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T2 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T3_R | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T3_D | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T4_N100 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T4_N200 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T4_N500 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T5 | NOT EVALUATED | — | — | — | — | — | — | — |
| T6 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | PASS | PASS | PASS | NOT REACHED |
| T7 | PASS | PASS | INSUFFICIENT_SUPPORT | PASS | PASS | PASS | PASS | NOT REACHED |
| T8_N100 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | FAIL | PASS | PASS | NOT REACHED |
| T8_N200 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | FAIL | PASS | PASS | NOT REACHED |
| T8_N500 | FAIL | FAIL | INSUFFICIENT_SUPPORT | FAIL | FAIL | PASS | PASS | NOT REACHED |

전체 H100-standby ≥90%는 진단용 reference이며 추가 hard gate가 아니다. Underprediction seconds에는 절대 threshold가 없고, overreservation/inflation/active-miss는 eligible 후보끼리 최소화할 값이다. Historical insufficient jobs는 exact support<100인 개별 job 수로, critical subgroup 표본 N=4와 다른 개념이다.

T7 miss cohort: N=324, requested GPU count 합=694, GPU-underprediction seconds=14,960,009.137, active-miss GPU 5분 slots=49,898. 상세 job CSV 및 hardware/standby/walltime/support/partition/QoS/status 분해는 JSON에 저장했다. 최종 status는 retrospective diagnostic만 사용한다.

| Pareto denominator | Top share | Selected jobs | GPU-underprediction mass share |
|---|---:|---:|---:|
| miss_jobs | 1% | 4 | 22.625% |
| miss_jobs | 5% | 17 | 50.932% |
| miss_jobs | 10% | 33 | 66.374% |
| all_selection_jobs | 1% | 36 | 68.607% |
| all_selection_jobs | 5% | 177 | 96.495% |
| all_selection_jobs | 10% | 354 | 100.000% |

실패 분류는 MIXED_FAILURE다. T1/T2 raw conditional undercoverage, calibration correction의 selection 이전 적합성 부족, support 이질성과 fallback/abstention이 함께 관측됐다. T7은 aggregate coverage를 통과하므로 모든 ML tail model이 실패했다고 일반화하지 않는다. Pareto 집중도는 남아 있는 miss mass의 진단이며 GPU-weighted coverage FAIL을 뜻하지 않는다.

T5는 CENSOR_AUTHORITY_INSUFFICIENT다. AFT objective는 사용 가능하지만 registered inputs에 cutoff 시점 alive/status snapshot과 그 시점에 알려진 start-time 관측 근거가 없다. Static retrospective completion/footer만으로 이를 대체하지 않았다. Censored count는 unknown이며 새 authority 탐색이나 May completion read는 하지 않았다.

이 진단은 차기 revision 설계 근거다. V40L 모델·threshold·선택 결과를 변경하거나 Apr24–30 shadow를 열지 않았다.

Population 정의: standby는 동결된 QoS.lower()==standby이며 partition substring이 아니다. GPU count 합은 job별 requested GPU의 합으로 고유 장치 수가 아니다. 모든 selection job을 분모로 한 Pareto top10%는 354개 중 양수 miss 324개와 기여 0인 30개를 포함한다. 부가 평균 runtime/GPU 합은 그 top set의 양수 miss 구성원에 대한 값이다.
