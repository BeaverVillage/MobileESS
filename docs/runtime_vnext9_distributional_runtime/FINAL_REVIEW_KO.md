# Runtime-vNext9 분포 기반 런타임 연구 검토

선택 **D1__ROLLING14**, 진단 전용=True. **V42_RESEARCH_RUNTIME_PROVIDER_READY=False**. April은 **EXPOSED_REGRESSION_ONLY**, May는 미개봉이다.

## 사전 계약 및 비교 요약

오차·pinball·학습시간 단위는 초, inference latency는 밀리초다. Proper score를 병합한 전체 CSV는 MODEL_COMPARISON_WITH_PROPER_SCORES.csv다.

| arm | Q50_MAE | Q90_coverage | min_fold_coverage | max_fold_coverage | coverage_std | gt4h_coverage | gt12h_coverage | Q90_pinball | proper_coarsened_survival_NLL | reservation_actual_GPUh | queue_starts_lt_H | training_seconds_5fold | batch1000_inference_ms_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W0 | 51918.4141 | 0.9702 | 0.9358 | 0.9831 | 0.0164 | 0.8808 | 0.8597 | 5199.2849 | N/A | 5.1407 | 3722 | N/A | N/A |
| B0 | 7886.6659 | 0.8956 | 0.7034 | 0.9439 | 0.0876 | 0.6149 | 0.5808 | 3046.9581 | N/A | 2.4366 | 3928 | N/A | N/A |
| Bconst | 11622.7606 | 0.9149 | 0.7249 | 0.9434 | 0.0844 | 0.4953 | 0.3172 | 7324.8808 | N/A | 5.9009 | 2780 | N/A | N/A |
| V8 | 7715.9489 | 0.9084 | 0.8744 | 0.9253 | 0.0204 | 0.7344 | 0.7073 | 2577.7416 | N/A | 2.3211 | 3879 | N/A | N/A |
| D1__NONE | 18835.7216 | 0.9174 | 0.6647 | 0.9709 | 0.1095 | 0.7107 | 0.6556 | 4923.7373 | 2.5066301837047376 | 3.8188 | 3728 | 148.9184 | 1143.3797 |
| D2_normal_1.0__NONE | 12616.0949 | 0.8196 | 0.5671 | 0.8907 | 0.1284 | 0.3521 | 0.3025 | 5590.1289 | 7.2750363310913295 | 1.9682 | 3932 | 64.1733 | 37.2462 |
| D2_logistic_1.5__NONE | 14583.2985 | 0.9773 | 0.9175 | 0.9905 | 0.0271 | 0.9128 | 0.9011 | 32121.4754 | 3.1578981218839224 | 20.9612 | 3356 | 61.6523 | 34.8921 |
| D3__NONE | 17224.9851 | 0.8988 | 0.6444 | 0.9463 | 0.1103 | 0.6495 | 0.5825 | 4689.6402 | N/A | 3.4418 | 3802 | 163.9931 | 81.6703 |
| V9_SELECTED | 19380.1783 | 0.9093 | 0.8090 | 0.9297 | 0.0440 | 0.8282 | 0.8080 | 4737.6289 | INFINITE | 4.0864 | 3745 | 148.9184 | 1143.3797 |

B0는 March14T08 이전 fold에서, Bconst/V8은 모든 과거 fold에서 NONCAUSAL_RETROSPECTIVE_REFERENCE다. 그 점수는 선택에 쓰지 않았다. Pinball gate는 인과적 D3 전체 fold와 March14T08 이후 B0 구간만 사용한다. Baseline 학습시간 N/A는 재학습하지 않았다는 뜻이다. MODEL_COMPARISON.csv의 coarsened_survival_NLL은 수치 확률 하한을 적용한 진단 점수다. 엄밀한 proper score는 POOLED_PROPER_DISTRIBUTION_SCORES.csv에 분리했다. 양의 additive shift가 짧은 관측 구간에 확률0을 주면 실제 NLL은 INFINITE다. 다른 수치적0은 NUMERICAL_FLOOR_UNRESOLVED로 표시하고 정확한 proper score라고 주장하지 않는다. 선택 후보도 zero-support 때문에 분포의 log score가 실패한다. 이는 Q90 보정 개선과 별개의 추가 한계다. Brier는 IPCW 모집단 IBS가 아니며 CRPS를 계산했다고 주장하지 않는다.

## 1. V8의 직접적인 실패 원인은 무엇이었는가?

April 전체 Q90 coverage69.46%, >4h37.62%로 긴 작업을 심하게 과소예측했다. 시간별 보정 불안정도 남았다. reservation 감소를 안전성 개선으로 해석할 수 없다.

## 2. 왜 April은 이제 pristine holdout이 아닌가?

V8에서 이미 열어 실패 수치를 확인했고 그 지식이 V9 문제 설정에 쓰였다. 새 모델·분포·보정·gate 선택에는 사용하지 않았다. 노출 회귀 평가로만 명명한다.

## 3. 5개 blocked fold를 정확히 어떻게 나눴는가?

아래 UTC 표와 membership CSV에 사전 고정했다. validation 직전14일 CAL, 그 전까지 expanding TRAIN이며 label은 각 cutoff에서 마스킹했다.

| fold | TRAIN_cutoff | VALID_from | VALID_end |
| --- | --- | --- | --- |
| 1 | 2024-10-18T00:00:00+00:00 | 2024-11-01T00:00:00+00:00 | 2024-12-01T00:00:00+00:00 |
| 2 | 2024-11-17T00:00:00+00:00 | 2024-12-01T00:00:00+00:00 | 2025-01-01T00:00:00+00:00 |
| 3 | 2024-12-18T00:00:00+00:00 | 2025-01-01T00:00:00+00:00 | 2025-02-01T00:00:00+00:00 |
| 4 | 2025-01-18T00:00:00+00:00 | 2025-02-01T00:00:00+00:00 | 2025-03-01T00:00:00+00:00 |
| 5 | 2025-02-15T00:00:00+00:00 | 2025-03-01T00:00:00+00:00 | 2025-03-31T08:00:00+00:00 |

## 4. 각 fold의 Q90 coverage는?

| fold | N | Q90_coverage | Q90_pinball | Q50_MAE |
| --- | --- | --- | --- | --- |
| 1 | 22144 | 0.8950 | 4580.9658 | 25304.6071 |
| 2 | 36081 | 0.8957 | 1687.4047 | 6788.4266 |
| 3 | 85643 | 0.9297 | 6884.2336 | 31472.3033 |
| 4 | 21681 | 0.8090 | 5488.6307 | 16963.2687 |
| 5 | 64688 | 0.9285 | 3398.8976 | 9176.2394 |

## 5. temporal calibration stability가 개선됐는가?

선택 모델 범위 80.90%–92.97%, std=0.0440, stability gate=True. V8의 과거 fold 예측은 미래 학습된 모델의 소급 비교이므로 인과적 개선 증거로 사용하지 않았다.

## 6. hazard model은 어떻게 total runtime distribution을 만드는가?

x와 age/bin에서 interval hazard h를 예측해 S(t_k)=Π(1−h_m)를 만든다. 구간 안은 일정 hazard rate, 마지막 구간 이후는 마지막 rate 외삽이다. 127개 구간은 첫 TRAIN만 보고 고정했다. 초기15/60/300초 분해 후15분·1시간·6시간·1일 간격이며0초 종료는 첫 구간에 포함한다.

## 7. AFT model은 censored job을 어떻게 처리하는가?

원래 T의 정확한 lower/upper를 보존하고 라이브러리에는 U=T+1의 exact U/U 또는 censor (c−start+1)/∞를 전달했다. 세 분포×scale1.0/1.5를 비교했다. logU=mu+scale Z를 T=max(exp(logU)−1,0)로 복원한다. PENDING은 runtime 관측이 아니다.

## 8. D1/D2/D3 중 무엇이 pre-April에서 가장 안정적인가?

단순 std 최소 설정은 아래와 같다. 낮은 변동성만으로 안전성 PASS나 승자를 선언하지 않는다.

| family | minimum_std_arm | coverage_std | pooled_coverage | min_fold_coverage |
| --- | --- | --- | --- | --- |
| D1 | D1__ROLLING14 | 0.0440 | 0.9093 | 0.8090 |
| D2 | D2_logistic_1.5__NONE | 0.0271 | 0.9773 | 0.9175 |
| D3 | D3__ROLLING14 | 0.0404 | 0.9114 | 0.8248 |

## 9. 전체 Q90 coverage는 nominal90% 부근인가?

90.93%; 88–92% gate=True.

## 10. fold 하나에 성능 collapse가 있는가?

최저 80.90%. 사전 안정성 기준 min≥80%, max≤97%, std≤0.06; 통과=True.

## 11. >4h coverage는 개선됐는가?

pre-April 82.82%, fold별 long gate=False. April 81.23%를 V8 37.62%와 비교하며 목표85%도 함께 평가한다.

## 12. >8h/>12h/>24h는 어떤가?

pre-April 81.75% / 80.80% / 59.61%. April 74.04% / 67.31% / 53.24%. 9개 세부 bucket과 N은 두 LONG_TAIL CSV에 보존했다.

## 13. walltime/scheduler descriptor는 계속 유용한가?

V8 pre-April ablation 근거로 유지했다. V9의 새 feature search나 April ablation은 하지 않아 각각의 추가 인과 효과를 주장하지 않는다. walltime은 predictor이며 label이나 기본 상한이 아니다.

## 14. right-censored job을 포함한 것이 성능에 어떤 영향을 주는가?

normal AFT scale1.0 검열 포함/완료만: coverage 81.96% / 81.84%, pinball 5590.1289 / 5497.8800, >4h 35.21% / 34.37%. 이 compact ablation의 관측 효과이며 모든 분포의 개선을 보장하지 않는다.

## 15. reservation/actual GPUh는 W0/B0/V8 대비 어떤가?

pre-April W0=5.1407, B0=2.4366, V8=2.3211, V9=4.0864. Sharpness gate=True. 과소 coverage로 얻은 절감을 성공으로 해석하지 않는다.

## 16. pre-April queue utility는 개선됐는가?

Queue gate=True. 고정5일 empty-background780GPU 연구 replay다. 전체 과거 V42 재구성이 아니며 예약 forecast와 완료 관측 기반 현재-slot stress를 분리했다.

| fold | arm | start_lt_H | start_ge_H | forecast_horizon_exhausted | causal_unresolved_at_horizon | capacity_violations | overrun_extensions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | W0 | 414 | 5 | 0 | 0 | 0 | 31 |
| 1 | B0 | 414 | 5 | 0 | 0 | 0 | 13340 |
| 1 | V8 | 414 | 5 | 0 | 0 | 0 | 15 |
| 1 | D1__ROLLING14 | 414 | 5 | 0 | 0 | 0 | 64 |
| 2 | W0 | 617 | 3 | 0 | 0 | 0 | 16 |
| 2 | B0 | 617 | 3 | 0 | 0 | 0 | 663 |
| 2 | V8 | 617 | 3 | 0 | 0 | 0 | 810 |
| 2 | D1__ROLLING14 | 617 | 3 | 0 | 0 | 0 | 756 |
| 3 | W0 | 1016 | 12 | 0 | 0 | 0 | 30 |
| 3 | B0 | 1016 | 12 | 0 | 0 | 0 | 1132 |
| 3 | V8 | 1016 | 12 | 0 | 0 | 0 | 798 |
| 3 | D1__ROLLING14 | 1016 | 12 | 0 | 0 | 0 | 2184 |
| 4 | W0 | 1047 | 243 | 0 | 0 | 0 | 35 |
| 4 | B0 | 1253 | 37 | 0 | 0 | 0 | 4011 |
| 4 | V8 | 1204 | 86 | 0 | 0 | 0 | 3928 |
| 4 | D1__ROLLING14 | 1070 | 220 | 0 | 0 | 0 | 2061 |
| 5 | W0 | 628 | 14 | 0 | 0 | 0 | 48 |
| 5 | B0 | 628 | 14 | 0 | 0 | 0 | 269 |
| 5 | V8 | 628 | 14 | 0 | 0 | 0 | 855 |
| 5 | D1__ROLLING14 | 628 | 14 | 0 | 0 | 0 | 2629 |

## 17. April exposed regression은 어떻게 나왔는가?

| arm | N | Q50_MAE | Q90_coverage | Q90_pinball | reservation_actual_GPUh |
| --- | --- | --- | --- | --- | --- |
| W0 | 49712 | 40397.1178 | 0.9453 | 4057.4987 | 4.3042 |
| B0 | 49712 | 9330.5513 | 0.8171 | 3350.4044 | 2.7739 |
| Bconst | 49712 | 11318.2002 | 0.9567 | 7615.6077 | 4.1889 |
| V8 | 49712 | 10381.1726 | 0.6946 | 4584.6257 | 2.4227 |
| V9 | 49712 | 11106.2565 | 0.8256 | 3405.1613 | 2.9770 |

V9 >4h=81.23%. 이전 V8 결과를 덮어쓰지 않았다.

## 18. April 결과를 보고 재튜닝했는가?

NO. 다섯 freeze 이후 모델·분포·bin·feature·보정 알고리즘·threshold·provider bytes 변경은 없다. Rolling이면 예정된 과거 관측 상태 갱신만 수행한다.

## 19. April2 start<H는 W0/B0/V8/V9 각각 몇 개인가?

150 / 47 / 111 / 127. 같은332개 background와 site ledger, baseline150/47/111 정확 재현이다. 전체 optimizer 통합 결과로 해석하지 않는다.

## 20. conditional remaining inference는 total-minus-elapsed보다 나은가?

| arm | N | remaining_Q50_MAE_seconds | remaining_MAE_seconds | remaining_Q90_coverage | overrun_checkpoint_fraction |
| --- | --- | --- | --- | --- | --- |
| R0_Bconst | 299805 | 62047.4189 | 63586.0179 | 0.4883 | 0.2893 |
| R1_B0 | 299805 | 57823.5902 | 30755.0361 | 0.5941 | 0.1621 |
| R2_V8 | 299805 | 46571.2027 | 31067.6581 | 0.3679 | 0.3276 |
| R3_V9 | 299805 | 32431.3487 | 52167.4271 | 0.9302 | 0.1320 |

생존한 작업의 반복 checkpoint는 긴 작업에 더 큰 가중치를 주며 미완료 정답은 제외한다.

## 21. checkpoint remaining Q90 coverage는?

93.02%, N=299805, jobs=23294; 잔여시간 성능 gate=False. 수학적 조건부 추론의 타당성과 실제 예측 성능은 구분한다.

## 22. overrun frequency는 줄었는가?

checkpoint 비율 Bconst=28.93%, B0=16.21%, V8=32.76%, V9=13.20%. 원래 total Q90 대비 overrun을 측정해 조건부 잔여 Q90로 계획 초과를 숨기지 않았다.

## 23. 별도 remaining-runtime model이 여전히 필요한가?

INCONCLUSIVE. 별도 모델은 학습하지 않았다. 조건부 예측 실패가 곧 별도 모델의 필수성을 입증하지는 않는다.

## 24. selected provider는 완전히 새 job에 호출 가능한가?

YES. CPU predict_total/predict_remaining, UNKNOWN0, 신규 ID 불변성, outcome 거부와 직렬화 예측 일치를 검증했다. 연구 opt-in이 필요하다.

## 25. online model refit이 필요한가?

NO. Booster bytes는 고정이며 rolling이면 완료 관측 API가 residual 보정 상태만 갱신한다.

## 26. rolling calibration을 사용했다면 미래 residual leakage가 없는가?

선택=ROLLING14; 미래 residual 읽기0. end<예측 UTC day를 먼저 적용한 뒤 잔차를 계산한다. out-of-training 관측만 쓰며 미래 label 교란 불변성과 날짜별 감사 CSV가 있다. April2 counterfactual은 issue 시점 보정 상태를 고정해 off-policy 미래 잔차를 쓰지 않는다.

## 27. CPU/GPU 어느 backend가 적합한가?

| backend | supported | training_seconds | actual_device_identity_verified | preApril_1000_max_quantile_difference_seconds | selected_for_provider |
| --- | --- | --- | --- | --- | --- |
| CPU4 | True | 45.6791 | True | 0.0000 | True |
| CPU1 | True | 143.0479 | True | 0.0000 | False |
| GPU | True | 23.6666 | True | 347.1786 | False |

GPU가 학습23.67초로 CPU4의45.68초, CPU1의143.05초보다 빨랐다. 실제 RTX4060 Laptop 실행을 로그로 확인했다. 다만 pre-April1000건 분위수 최대 차이는347.18초였고 CPU1/4끼리는0이었다. 동결 CPU4 학습/CPU1 추론 bundle을 유지한다. 이후 연구 학습 가속에는 GPU가 유리하지만 이 CPU 모델과 같은 예측값을 보장하지 않는다. CPU 추론 median은1/10/100/1000건에서21.72/33.54/163.60/1410.45ms다.

## 28. May를 열었는가?

NO. MAY_PAYLOAD_OPENED=FALSE, MAY_USED_FOR_SELECTION=FALSE. 이전 namespace byte hash와 raw ZIP 식별은 May record decoding이 아니다.

## 29. V42 research Runtime provider로 사용할 수 있는가?

검증된 provider 준비=False. 선택 D1__ROLLING14, 전체 gate 통과 후보 0개. Callable 진단 bundle을 검증 통과로 바꾸지 않는다. V42/AIDC/MESS/electrical kernel은 수정하지 않았다.

## 30. provenance limitation은 여전히 무엇인가?

Kestrel_trace_proxy archived request descriptor다. 최초 submit 값인지 최종 수정 값인지 증명할 immutable request-version authority가 없다. Strict feature0, authorityFALSE, strict providerFALSE를 유지한다.

## 표본 및 재현 범위

| fold | role | N | exact | censored | no_runtime_information | observed_long_gt4h | high_GPU |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRAIN | 371864 | 371713 | 151 | 0 | 14848 | 27093 |
| 1 | CAL | 9989 | 9775 | 214 | 0 | 3723 | 376 |
| 1 | VALID | 22937 | 22144 | 340 | 453 | 9812 | 622 |
| 2 | TRAIN | 392695 | 392386 | 309 | 0 | 24756 | 27783 |
| 2 | CAL | 11729 | 10936 | 340 | 453 | 3218 | 310 |
| 2 | VALID | 37293 | 36081 | 280 | 932 | 5440 | 512 |
| 3 | TRAIN | 416865 | 416513 | 352 | 0 | 31916 | 28385 |
| 3 | CAL | 25272 | 24060 | 280 | 932 | 2593 | 221 |
| 3 | VALID | 86206 | 85643 | 503 | 60 | 11046 | 775 |
| 4 | TRAIN | 464642 | 464366 | 276 | 0 | 41812 | 29003 |
| 4 | CAL | 63601 | 63038 | 503 | 60 | 5291 | 379 |
| 4 | VALID | 22313 | 21681 | 356 | 276 | 4929 | 640 |
| 5 | TRAIN | 541997 | 541874 | 123 | 0 | 51124 | 29540 |
| 5 | CAL | 9031 | 8399 | 356 | 276 | 1609 | 484 |
| 5 | VALID | 65287 | 64688 | 257 | 342 | 7583 | 403 |

Validation 미완료 작업은 quantile 오차에서 제외되고 검열 정보는 분포 score에 남는다. 완료 표본 coverage에는 행정 검열/선택 편향 가능성이 있다. RIGHT_CENSORING_AUDIT의 VALID는 cutoff까지 전체 제출 관측 상태이며 support 표가 실제 validation cohort다. High-GPU N<100은 INSUFFICIENT_SUPPORT로 보고한다. April V9의 GPU≥16은 N298, coverage79.19%로 FAIL이고 GPU≥64는 N53으로 INSUFFICIENT_SUPPORT다.

재현 순서: prepare9.py → verify_causality9.py / verify_math9.py → train9.py → baselines9.py → evaluate9.py → audit_proper_score9.py → finalize_model9.py → evaluate_april9.py → queue_april9.py → verify_provider_external9.py → report9.py → complete_delivery9.py. 실패한 checkpoint datetime 연산만 resume_april_diagnostics9.py로 재개했으며 예측값 변화0과 provider byte 불변을 확인했다. 사전 계약/freeze는 배타적 생성이다. 원본 경로·hash는 SOURCE_MANIFEST.json, 계산 캐시 .local은 Git 제외다. 이전 v6/v7/v8의355개 과학 산출물과3개 manifest byte hash를 다시 검증했다.
