- 최종 분류: **V40R4_COMPOUND_GPUWORK_SAFETY_FAIL**
- 선택 모델: **NONE**
- CCAF: **FAIL**
- CCAF superiority: **NO**
- 개발 단계 고정 최강 기준모델: **B2**
- EVT tail supported: **NO**
- Untouched confirmation: **NO**

ML은 외생 arriving GPU-service demand를 예측하고 optimizer는 이후 내생 service timing을 결정한다. 이 역할 분리, R3 타깃·코호트·F30 제거·GPU 결측 처리·성숙도·30분 증분 구조를 유지했다. R2는 SUPERSEDED_BY_V40R3, R3는 V40R3_FUTURE_GPUWORK_SAFETY_FAIL이며 원본을 수정하지 않았다.

**1. Target reproduction.** 적격 548,339 jobs, GPU 결측 제외 240,050, 349개 운영일 기여 545,553 jobs / 1,904,541.778333334 GPUh. 16,752개 30분 구간의 R3 대비 최대 절대 차이는 0.0 GPUh이다(고정 허용오차 1e-7). 발행은 D−1 18:00 fixed AEST=D−1 08:00 UTC이며 다음 운영일 48구간을 예측한다. Z=g×(end−start)/3600을 제출 구간에 전량 배정한다. GPUh는 관측 서비스 proxy이며 FLOPs나 하드웨어 독립 작업량이 아니다.

**2. Count distribution.** 성숙 TRAIN 8,016구간에서 N 평균 42.070235, 분산 11517.459945, 분산/평균 273.7674, zero 40.8683%. Poisson 예상 zero는 5.36e-19. N의 중앙값/P90/P95/P99/max=2/160/255/476.85/2067. BIC는 NB를 선택했다. ZINB의 추가 zero 확률은 거의 0 경계로 수렴했다. 이는 marginal 진단이며 조건부 예측 성능 보장이 아니다.

**3. Severity heavy tail.** TRAIN 양수 jobs 337,235개, 평균 1.766960, 중앙값 0.057778, P90/P95/P97.5/P99/P99.5=0.972222/2.506750/9.325278/36.212556/56.478211, max 6,145.208889 GPUh. Lognormal이 Gamma보다 낮은 TRAIN BIC를 보였다. Mean-excess, log-severity, Hill 민감도, QQ 자료를 보존했다. Heavy tail을 곧바로 특정 power law의 증명으로 해석하지 않는다.

**4. Tail threshold.** GPD용 선택 임계값은 없음이다. P1의 비-EVT spliced-lognormal 분기점은 별도로 사전등록한 TRAIN job Q95=2.506750 GPUh다. 이를 EVT가 지지된 threshold로 표현하지 않는다.

**5. GPD/EVT diagnostic.** 사전 Phase-0 규칙의 support·shape·finite-mean CI·인접 threshold 안정성·KS distance·QQ를 통과한 threshold가 없었다. B6는 EVT_TAIL_NOT_SUPPORTED로 미실행했다.

| TRAIN quantile | u GPUh | exceedance N | xi | xi 95% CI | sigma | KS | 허용 |
|---|---:|---:|---:|---|---:|---:|---|
| 0.900 | 0.972222 | 33,621 | 2.729277 | [1.688310, 4.036293] | 0.338995 | 0.132509 | FAIL |
| 0.950 | 2.506750 | 16,862 | 0.955710 | [0.723419, 1.102004] | 6.982551 | 0.076512 | FAIL |
| 0.975 | 9.325278 | 8,431 | 0.530869 | [0.409154, 0.680265] | 21.346319 | 0.055038 | FAIL |

Q90/Q95의 shape 추정은 finite-mean 안정성을 충족하지 못했고, Q97.5도 인접 xi 차이와 KS 기준에서 실패했다. CI는 운영일 단위 100회 bootstrap이며 고정 threshold 조건부 불확실성이다. Fitted-parameter KS의 잘못된 simple-null p-value를 제시하지 않았다.

**6. Count–severity dependence.** 양수 TRAIN 구간에서 Spearman(N,평균 Z)=-0.413108, Pearson=-0.057360. CCAF는 predicted mu를 severity head에 넣으며 realized future N은 넣지 않는다. 관측 연관성이며 인과 효과가 아니다. 시간대 평균 제거 후 residual ΔW lag1 상관 0.095484가 남으므로 조건부 독립 시나리오의 joint daily 해석에는 한계가 있다.

**7. January 12 misses.** R3의 102/114 coverage에서 빠진 12개는 COUNT_DRIVEN 8, SEVERITY_DRIVEN 2, MIXED 1, UNRESOLVED 1이다. TRAIN N Q95=255, 양수 구간 max Z Q95=146.529889를 사용했다. 다음 분류는 설명용이며 배포 규칙이 아니다.

| 일자 | slot | ΔW GPUh | N | 최대 Z GPUh | top1 share | top3 share | 분류 |
|---|---:|---:|---:|---:|---:|---:|---|
| 2025-01-07 | 4 | 6788.593 | 456 | 96.023 | 1.41% | 4.06% | COUNT_DRIVEN |
| 2025-01-07 | 7 | 7680.153 | 10 | 960.036 | 12.50% | 37.50% | SEVERITY_DRIVEN |
| 2025-01-08 | 26 | 20699.640 | 1226 | 533.350 | 2.58% | 3.21% | MIXED |
| 2025-01-14 | 16 | 10352.344 | 811 | 87.746 | 0.85% | 1.54% | COUNT_DRIVEN |
| 2025-01-15 | 22 | 7000.216 | 425 | 24.009 | 0.34% | 1.03% | COUNT_DRIVEN |
| 2025-01-18 | 31 | 6977.647 | 463 | 24.010 | 0.34% | 1.03% | COUNT_DRIVEN |
| 2025-01-19 | 19 | 13642.121 | 953 | 48.007 | 0.35% | 1.06% | COUNT_DRIVEN |
| 2025-01-20 | 18 | 6036.515 | 9 | 960.017 | 15.90% | 47.71% | SEVERITY_DRIVEN |
| 2025-01-23 | 10 | 5315.607 | 437 | 24.009 | 0.45% | 1.35% | COUNT_DRIVEN |
| 2025-01-24 | 29 | 14930.806 | 1336 | 36.009 | 0.24% | 0.72% | COUNT_DRIVEN |
| 2025-01-30 | 18 | 19263.816 | 933 | 48.009 | 0.25% | 0.75% | COUNT_DRIVEN |
| 2025-01-31 | 14 | 5830.278 | 232 | 71.594 | 1.23% | 2.87% | UNRESOLVED |

모든 R3 burst 구간의 mean/median/max, top3, TRAIN-tail 초과 수 및 percentile은 [전체 분해 CSV](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_V40R3_BURST_FAILURE_DECOMPOSITION.csv>)에 있다.

**8. Candidate registry.** B0 ZERO; B1 causal seasonal; B2 R3-style aggregate Hurdle LightGBM 재학습; B3 Tweedie aggregate; B4 parametric NB+Lognormal; B5 ML NB+Lognormal; B6 body+EVT 미실행; P1 CCAF NB+tail-exceedance+spliced-lognormal. 두 LR/설정 탐색은 B2/B3/B4/B5/P1에 동일하게 2개이며 P1만 모델 선택용으로 더 많은 설정을 탐색하지 않았다. B0/B1은 parameter fitting이 없다. 여기의 B0–B6는 ML 비교 모델 ID이며 금지된 전기 B0–B3 실험을 실행한 것이 아니다.

**9. Count model results.** 아래는 raw component diagnostics다. B0–B3 aggregate 모델에는 실제 job-count head가 없으므로 NOT_APPLICABLE로 명시했다.

| 모델 | Count MAE | RMSE | bias | mean log likelihood | 관측/예측 zero | P90/P95 coverage | large-count recall |
|---|---:|---:|---:|---:|---|---|---:|
| B4 | 50.9969 | 211.8137 | -4.7808 | -3.5798 | 32.79% / 42.75% | 91.71% / 94.03% | 2.40% |
| B5 | 39.2544 | 158.3118 | -19.4282 | -4.1296 | 32.79% / 28.93% | 89.51% / 91.67% | 0.00% |
| P1 | 61.3070 | 156.9413 | 10.1448 | -3.3334 | 32.79% / 44.07% | 94.82% / 96.85% | 0.00% |

NB deviance·zero Brier도 count metrics에 저장했다. 최종 모델 선택은 count 점수가 아니라 aggregate GPUh 점수로 한다. P1은 pooled count P90 coverage가 높아도 실제 large-count 125구간의 recall은 0%다. 큰 arrival count를 구분하는 능력이 부족했음을 보여준다.

**10. Severity results.** 같은 인과 구간 문맥으로 모든 미래 jobs의 분포를 예측한다. 미래 GPU/walltime/partition/QoS/hardware/cores/memory는 predictor가 아니다. Lognormal 충분통계를 통해 개별 job likelihood를 보존했다.

| 모델 | log MAE | median abs log error | Q90 pinball | Q90 coverage | tail probability error | TRAIN top1% Q90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| B4 | 2.957599 | 2.898131 | 4.963433 | 79.91% | 0.093057 | 0.37% |
| B5 | 3.499673 | 3.636559 | 3.694039 | 84.08% | 0.024632 | 0.00% |
| P1 | 2.607138 | 2.244505 | 3.982077 | 76.24% | 0.153396 | 0.00% |

Tail conditional quantile pinball·coverage와 conditional log likelihood를 별도 저장해 body 성능에 tail 실패가 가려지지 않도록 했다. P1의 u 초과 예측 확률 평균은 5.0126%, 실제는 20.3522%였다. Tail-conditional Q90 coverage는 96.5216%지만 TRAIN top-1% severity 2,950 jobs의 unconditional Q90 coverage는 0%다. 이 지표들을 함께 보면 tail 발생 확률의 과소예측과 severity 분포 변화가 aggregate burst 실패의 주요 설명이라는 해석이 가능하다. 이는 사후 진단이며 인과 효과나 새 모델 선택 근거로 사용하지 않았다.

**11. Aggregate results.** 표는 DEVELOPMENT에서 고정한 trial/calibration 조합만 대상으로 한다. C0는 무보정, C1은 positive-CAL log-ratio 보정이다.

| 모델 | 고정 보정 | Primary | 양수 WAPE | 전체 coverage | 양수 coverage | burst coverage | 안전 |
|---|---|---:|---:|---:|---:|---:|---|
| B0 | C0 | 0.900000 | 100.00% | 32.79% | 0.00% | 0.00% | FAIL |
| B1 | C0 | 0.853230 | 102.48% | 80.61% | 71.15% | 13.33% | FAIL |
| B2 | C0 | 0.681887 | 96.71% | 87.50% | 81.40% | 2.92% | FAIL |
| B3 | C1 | 0.691220 | 116.20% | 92.35% | 88.62% | 16.25% | FAIL |
| B4 | C0 | 61.969815 | 1809.95% | 78.41% | 67.88% | 1.67% | FAIL |
| B5 | C0 | 0.759730 | 98.65% | 78.98% | 68.72% | 2.08% | FAIL |
| P1 | C0 | 0.681094 | 98.96% | 88.30% | 82.60% | 0.00% | FAIL |

B6: EVT_TAIL_NOT_SUPPORTED, 미실행이며 성적을 만들어 넣지 않았다. B4는 January/February point WAPE가 각각 2,450.04%/2,480.81%로 catastrophic gate에도 실패했다. 높은 aggregate 오차를 누락하거나 결과를 본 후 예측 상한을 추가하지 않았다.

**12. Raw Q90 coverage.** 아래 raw/C1 열은 모든 후보의 진단 비교이며 최종 결과를 보고 calibration 종류를 바꾸지 않았다. C1은 전체 aggregate CDF의 변환이므로 Q50도 바뀐다. 원시 compound sum과 보정된 aggregate scenarios를 구분한다.

| 모델 | Raw primary | C1 primary | Raw 전체 coverage | C1 전체 coverage | C1 score (log units) | C1 overconservative |
|---|---:|---:|---:|---:|---:|---|
| B0 | 0.900000 | 0.900000 | 32.79% | 32.79% | 0.000000 | False |
| B1 | 0.853230 | 4.204543 | 80.61% | 95.12% | 2.761327 | True |
| B2 | 0.681887 | 0.705903 | 87.50% | 94.37% | 0.985621 | False |
| B3 | 0.801386 | 0.691220 | 70.34% | 92.35% | 2.158922 | False |
| B4 | 61.969815 | 420.501833 | 78.41% | 95.00% | 1.925278 | True |
| B5 | 0.759730 | 0.868808 | 78.98% | 94.93% | 1.982407 | True |
| P1 | 0.681094 | 0.661801 | 88.30% | 93.75% | 0.693955 | False |

**13. Calibrated Q90 coverage.** P1 C1 전체/양수/burst coverage는 93.750000%/90.700951%/12.916667%, primary는 0.661800841다. Burst gate는 여전히 실패한다. 최종 고정 pipeline은 C0이며 C1 결과로 사후 교체하지 않았다.

**14. Positive coverage.** P1 고정 pipeline은 82.599507%; 허용 범위는 90–95%다.

**15. Burst coverage.** P1 0.000000%, N=240; 허용 범위는 90–97.5%다. Burst 기준 441.777542 GPUh는 R3 TRAIN에서 고정한 그대로다.

**16. Monthly stability.** 아래는 P1 결과다. 모든 모델의 December/January/February primary/coverage/burst miss/WAPE/bias는 temporal report에 별도 저장했다. September/October도 [개발 월별 진단](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_DEVELOPMENT_TEMPORAL_DIAGNOSTIC.json>)에 보존했다. 해당 두 달은 epoch/calibration/pipeline 선택에 사용된 노출 자료이므로 미노출·순차적 검증이라고 주장하지 않는다. N<100의 월별 burst는 숫자를 기록하되 INSUFFICIENT_SUPPORT로 처리한다.

| 월 | Primary | 전체 coverage | burst N | burst coverage | missed burst GPUh | WAPE | bias GPUh |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-12 | 0.719595 | 91.20% | 61 | 0.00% | 123015.322 | 100.09% | -118.445 |
| 2025-01 | 0.708782 | 85.75% | 114 | 0.00% | 227811.456 | 99.14% | -214.477 |
| 2025-02 | 0.586998 | 87.90% | 65 | 0.00% | 87682.631 | 98.42% | -132.490 |

**17. Calibration error.** P1 전체/양수/burst 절대 오차는 각각 1.6951/7.4005/90.0000 percentage points다. Coverage가 90%를 넘는 것만으로 우수하다고 판정하지 않는다.

**18. Positive normalized Q90 pinball.** P1 0.681093855; 과학적 유용성의 최소 기준은 ZERO의 0.9 미만이다.

**19. Overprediction.** P1 고정 pipeline의 Q90 overprediction 합 637,013.303656 GPUh, underprediction 합 463,240.777103 GPUh.

**20. Missed burst.** P1 438,509.409918 GPUh, captured fraction 11.6455%, mean shortfall 1827.122541 GPUh. Worst20 및 모든 miss의 COUNT/SEVERITY/MIXED/UNRESOLVED 분류는 개별 candidate report에 있다.

**21. Cumulative WAPE.** P1 72.560211%. 각 시나리오의 비음수 increments를 먼저 합산하고 누적량의 quantile을 계산했다. Marginal Q90들의 합을 true cumulative Q90이라고 부르지 않는다. 단, 조건부 독립 시나리오 law 자체의 적합성은 별도 한계다.

**22. Daily total.** P1 MAE 5,224.662004 GPUh, bias -4,294.723538 GPUh; 최대 누적 underforecast 25,618.244375 GPUh.

**23. Horizon crossing.** P1=0. 모든 모델에 비음수 scenario increments를 적용했고 각 누적 quantile의 시간 단조성을 검사했다.

**24. Strongest baseline.** B2를 October DEVELOPMENT에서 고정하고 commit 1a178ceba65a4bf830c6e0955effb4838d922f3f에 저장한 다음 최종 노출 비교를 시작했다. DEVELOPMENT에서 안전 적격 baseline은 없었으며 B2는 비교 기준으로만 고정됐다. 최종 B2 primary 0.681887115 대비 P1 0.681093855의 수치상 차이는 0.000793259다. 양측 모두 안전 실패이므로 우월성 근거로 해석하지 않는다. September provisional calibration은 October 시작 전에 성숙한 label만 사용했다. 최종 C1 score는 November CAL에서만 계산했다.

**25. Bootstrap.** 상태 NOT_EXECUTED_CCAF_FAILED_SAFETY_OR_CALIBRATION. CCAF가 안전/보정 gate를 통과하지 못했으므로 사전 규칙에 따라 실행하지 않았다. CI를 사후 계산해 종합 우위처럼 제시하지 않는다.

**26. Selection.** NONE; V40R4_COMPOUND_GPUWORK_SAFETY_FAIL. Authority→temporal safety/calibration 및 MC→primary→burst miss→cumulative WAPE→단순성 순서를 적용했다. 안전에 실패한 모델은 점수가 좋아도 선택하지 않는다.

**27. Confirmation.** TRUE_CONFIRMATORY_AVAILABLE=NO. R3의 모든 과거 구간은 이미 노출되어 DEVELOPMENT/STRESS이며 미노출 확인으로 이름을 바꾸지 않았다. 최대 긍정 표현은 PREVALIDATED다.

**28. May.** 2025년 5월 scientific reads=0. 새 raw archive 및 미노출 기간을 열지 않았다. User protocol, git 경로/index, R3 provenance의 metadata 접근은 NONZERO다. 과거 V40P/R2 노출 이력은 지우지 않았다.

**29. Tests/compute.** Final 63/63 PASS, 실패·오류·미실행 0. Synthetic gradient 검사는 optimizer step 없이 했다. 테스트 PASS와 모델 safety PASS를 구분한다. Monte Carlo는 10,000개로 고정했고 TRAIN/CAL 24개 문맥에서 1,000/2,500/5,000/10,000 및 독립 10,000개를 비교했다. 수렴 gate 결과: B0=PASS, B1=FAIL, B2=PASS, B3=PASS, B4=PASS, B5=PASS, P1=PASS.

CCAF 독립 동일-seed 학습 2회(원본+재현)의 예측 max/mean 차이는 0.000000000/0.000000000 GPUh, development raw primary는 0.676529797/0.676529797다. 더 좋은 재현을 선택하지 않았다. GPU bitwise 동일성을 일반적으로 주장하지 않는다. 장치·CUDA·library 버전·seed·threads·epoch·실제 fit time은 [compute ledger](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_COMPUTE_LEDGER.json>)에 있다. 추가 결과 검증의 첫 실행에서 날짜 object-array 로더 오류 1건이 발생했다. 자체 생성 NPZ의 문자열 읽기만 정정 후 63개를 재실행했으며 모델/평가 결과는 변경하지 않았다. 최초 실행과 정정 기록도 보존했다.

**30. Protected scope.** 변경은 R4 두 namespace만이다. R3 source/artifact 234파일의 초기 byte hash를 종료 시점까지 확인했다. R2는 재개·학습·merge/reuse·수정·삭제하지 않았다. R3의 SAFETY_FAIL 분류와 V40S/S2를 변경하지 않았다. 초기 R4 index 누락은 분석 전 index-only 복구 후 자체 미공개 커밋을 정정했고 원본 worktree 파일은 삭제되지 않았다. 첫 타깃 시각 정밀도 오류도 진단 전에 중단·정정했으며 재검증 오차는 0이다. 두 기술 정정 기록을 숨기지 않았다.

**31. Holds.** production q=UNCHANGED; PF=0.95; Q control=NO; electrical regeneration=HOLD; electrical B0/B1/B2/B3=NO; FULL_MAY=NO; optimizer=NO. V40S2 integration도 하지 않았다.

시작 receipt 43710c96c36f7e66257885a56ef6df697b3c53bb, V40R3 scientific 6e2f0791952a9001d2fdd4a6564e0f699ec3fc90, V40R4 preregistration **f10187e0b0cbaadde5b28186e70822f5ff258f76**. [최종 연구 및 receipt 기록](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_FINAL_COMMIT_RECEIPT.json>).

[문헌 근거](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_SCI_BENCHMARK_REVIEW.md>) · [사전등록](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_PREREGISTRATION.json>) · [모델별 안전 gate](<C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival/dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_SAFETY_GATE_TABLE.json>)
