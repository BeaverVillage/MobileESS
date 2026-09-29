# Runtime-vNext11 최종 검토 — 사용자 stop 조건으로 Stage B 뒤 중단

**결론: 비승격, Stage C/최종 provider/April 미실행.** pooled 성능으로 temporal classifier 실패를 가리지 않았다. 요청서42절의 중단 조건과 데이터 확인 전에 등록한 최소 fold AUC0.55 규칙을 적용했다. Pooled AUC0.793이 모든 시기에서의 성공을 뜻하지 않으며 fold3는0.495였다. 판정 문턱을 사후에 낮추지 않았다.

기준 0e499999830207870a8ce86bb00839f87d8fd5b2, PR #82. 기존 v6–v10 과학 파일810개와 manifest5개를 그대로 유지한다. 이번 변경은 docs/runtime_vnext11_total_remaining에 한정된다. V42/CC4/MESS/kernel/optimizer/May를 변경하지 않았다.

Stage A를 완료·동결한 뒤 15개 base window/target 조합(5fold, Q50/Q90), 선택 D60_RAW의 classifier와 L1/L2 expert 및5개 gate 후보를 비교했다. 이 순차 설계는 사전 등록됐으며 모든 window/target/tail 조합을 망라한 탐색은 아니다. 모든 TOTAL 후보가 안전 gate를 실패했다. 이후 작업은 새 모델 학습이 아닌 체크포인트 생성기/ID 분리 감사와 결과 보존뿐이었다.

## 1. Fold4가 왜 어려웠는가?

판정은 MIXED다. TRAIN/CAL/VALID runtime 중앙값은 74/25/673초이고 Q90은 8,839/4,831.9/59,862초다. 짧은 CAL의 관계를 STATIC 보정으로 VALID에 이전한 V10은 raw 88.33%에서 39.56%로 악화됐다. 요청 mix, label marginal, 지원 손실 및 공통 exact-x 내 차이가 함께 존재한다. 단일 인과 원인이 입증된 것은 아니다. exact-x 공통 VALID mass 41.76%, 그 안의 가중 KS 0.3473다.

## 2. Fold1과 Fold4 문제 원인은 같은가?

같다고 단정할 수 없다. Fold1은 expanding TRAIN runtime 중앙값56초→VALID3,624초, raw V10부터 coverage66.47%였다. Fold4는 TRAIN74초→VALID673초이지만 특히 CAL25초가 더 짧아 STATIC 보정의 실패가 컸다. Fold1은 요청 지원 손실 기준을 넘지 않았고 fold4는 partition unseen10.36%를 포함한다.

## 3. 실제 runtime distribution이 시기별로 얼마나 달라지는가?

| fold | role | N | Q50 | Q90 | Q99 | mean | zero_rate | censored_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRAIN | 371713 | 56.0000 | 1147.0000 | 86411.0000 | 3015.9738 | 0.0045 | 0.0004 |
| 1 | CAL | 9775 | 837.0000 | 56227.6000 | 121982.8200 | 20049.9036 | 0.0002 | 0.0214 |
| 1 | VALID | 22144 | 3624.0000 | 70506.0000 | 140130.4700 | 28916.6351 | 0.0001 | 0.0148 |
| 2 | TRAIN | 392386 | 60.0000 | 2462.5000 | 86416.0000 | 4494.0360 | 0.0043 | 0.0008 |
| 2 | CAL | 10936 | 409.0000 | 54545.0000 | 93841.5500 | 17410.0407 | 0.0000 | 0.0290 |
| 2 | VALID | 36081 | 177.0000 | 54352.0000 | 99302.0000 | 9707.4809 | 0.0019 | 0.0075 |
| 3 | TRAIN | 416513 | 67.0000 | 4878.0000 | 86427.0000 | 5347.2150 | 0.0042 | 0.0008 |
| 3 | CAL | 24060 | 155.0000 | 23829.0000 | 99302.0000 | 7014.8987 | 0.0000 | 0.0111 |
| 3 | VALID | 85643 | 29.0000 | 35897.2000 | 108865.1000 | 8720.9282 | 0.0002 | 0.0058 |
| 4 | TRAIN | 464366 | 74.0000 | 8839.0000 | 86432.3500 | 6115.2590 | 0.0038 | 0.0006 |
| 4 | CAL | 63038 | 25.0000 | 4831.9000 | 102315.6000 | 5882.9234 | 0.0002 | 0.0079 |
| 4 | VALID | 21681 | 673.0000 | 59862.0000 | 172823.0000 | 19695.6878 | 0.0004 | 0.0160 |
| 5 | TRAIN | 541874 | 62.0000 | 11325.0000 | 99219.7000 | 6645.2708 | 0.0033 | 0.0002 |
| 5 | CAL | 8399 | 312.0000 | 54402.0000 | 172824.0000 | 15180.8025 | 0.0006 | 0.0394 |
| 5 | VALID | 64688 | 55.0000 | 20825.7000 | 109362.9200 | 7984.7228 | 0.0185 | 0.0039 |

전체 Q10/Q25/Q50/Q75/Q90/Q95/Q99는 FOLD_DISTRIBUTION_SUMMARY.csv에 있다. exact completed subset의 비교이며 censored/unresolved maturity selection 차이를 없앤 causal-population 추정은 아니다.

## 4. >4h/>12h/>24h prevalence가 어떻게 변하는가?

| fold | role | threshold_seconds | N | long_N | rate |
| --- | --- | --- | --- | --- | --- |
| 1 | TRAIN | 14400 | 371713 | 14848 | 0.0399 |
| 1 | TRAIN | 43200 | 371713 | 7952 | 0.0214 |
| 1 | TRAIN | 86400 | 371713 | 4281 | 0.0115 |
| 1 | VALID | 14400 | 22144 | 9812 | 0.4431 |
| 1 | VALID | 43200 | 22144 | 8000 | 0.3613 |
| 1 | VALID | 86400 | 22144 | 607 | 0.0274 |
| 2 | TRAIN | 14400 | 392386 | 24756 | 0.0631 |
| 2 | TRAIN | 43200 | 392386 | 15073 | 0.0384 |
| 2 | TRAIN | 86400 | 392386 | 5041 | 0.0128 |
| 2 | VALID | 14400 | 36081 | 5440 | 0.1508 |
| 2 | VALID | 43200 | 36081 | 4353 | 0.1206 |
| 2 | VALID | 86400 | 36081 | 914 | 0.0253 |
| 3 | TRAIN | 14400 | 416513 | 31916 | 0.0766 |
| 3 | TRAIN | 43200 | 416513 | 20476 | 0.0492 |
| 3 | TRAIN | 86400 | 416513 | 6218 | 0.0149 |
| 3 | VALID | 14400 | 85643 | 11046 | 0.1290 |
| 3 | VALID | 43200 | 85643 | 7904 | 0.0923 |
| 3 | VALID | 86400 | 85643 | 2129 | 0.0249 |
| 4 | TRAIN | 14400 | 464366 | 41812 | 0.0900 |
| 4 | TRAIN | 43200 | 464366 | 28070 | 0.0604 |
| 4 | TRAIN | 86400 | 464366 | 7398 | 0.0159 |
| 4 | VALID | 14400 | 21681 | 4929 | 0.2273 |
| 4 | VALID | 43200 | 21681 | 3635 | 0.1677 |
| 4 | VALID | 86400 | 21681 | 1422 | 0.0656 |
| 5 | TRAIN | 14400 | 541874 | 51124 | 0.0943 |
| 5 | TRAIN | 43200 | 541874 | 35096 | 0.0648 |
| 5 | TRAIN | 86400 | 541874 | 10390 | 0.0192 |
| 5 | VALID | 14400 | 64688 | 7583 | 0.1172 |
| 5 | VALID | 43200 | 64688 | 4794 | 0.0741 |
| 5 | VALID | 86400 | 64688 | 1296 | 0.0200 |

rate는 fraction이다. >15m/30m/1h/2h/8h/48h도 FOLD_LONG_TAIL_PREVALENCE.csv에 보존했다.

## 5. requested walltime-runtime 관계가 시기별로 달라지는가?

그렇다. runtime/requested walltime CDF의 TRAIN→VALID KS는 fold1=0.4341, fold2=0.2697, fold3=0.5537, fold4=0.2205, fold5=0.3438다. ratio marginal 변화만으로 conditional shift를 선언하지 않고, 9개 raw 요청값 exact cell TRAIN≥50/VALID≥30의 within-cell KS를 별도 비교했다. 관측상 conditional 변화와 일치하는 증거이지 숨은 실행 종류나 archive revision 원인을 식별한 것은 아니다.

## 6. QoS/partition/account mix가 달라졌는가?

| field | JS_divergence | total_variation | unseen_rate | rare_rate |
| --- | --- | --- | --- | --- |
| qos | 0.0567 | 0.2023 | 0.0000 | 0.0000 |
| partition | 0.1432 | 0.3366 | 0.1036 | 0.0000 |
| account | 0.4114 | 0.6558 | 0.0575 | 0.0930 |
| array_status | 0.0013 | 0.0116 | 0.0000 | 0.0000 |

이는 fold4 표다. 모든 fold의 category별 TRAIN/VALID N·share·unseen/rare는 FOLD_CATEGORY_SUPPORT.csv에 있다. array status도 비교했다.

## 7. expanding vs 180/90/60/30-day training 중 무엇이 안정적인가?

fold coverage 표준편차만 보면 D60_RAW가 가장 작다(9.94pp). 하지만 어느 후보도 모든 안전 gate를 통과하지 못했다. 사전 실패 gate 수→pinball→reservation→MAE→std 순서에서 진단 후보 D60_RAW를 선택했다. 최종 배포용 window 검증이 아니다.

| arm | Q90_coverage | min_fold_coverage | coverage_std | gt4h_coverage | Q90_pinball | reservation_actual_GPUh |
| --- | --- | --- | --- | --- | --- | --- |
| EXPANDING_RAW | 0.8980 | 0.6300 | 0.1164 | 0.6419 | 4821.0084 | 3.5679 |
| EXPANDING_LOG | 0.8971 | 0.6463 | 0.1089 | 0.6369 | 4747.5696 | 3.3675 |
| EXPANDING_REL | 0.8841 | 0.6368 | 0.1071 | 0.5938 | 4739.1523 | 3.4500 |
| D180_RAW | 0.8971 | 0.6365 | 0.1133 | 0.6398 | 4686.9332 | 3.5374 |
| D180_LOG | 0.8939 | 0.6416 | 0.1097 | 0.6367 | 4683.2855 | 3.3918 |
| D180_REL | 0.8879 | 0.6261 | 0.1137 | 0.6302 | 4568.6608 | 3.4216 |
| D90_RAW | 0.8914 | 0.6577 | 0.1031 | 0.6552 | 5029.1018 | 3.8021 |
| D90_LOG | 0.8890 | 0.6342 | 0.1131 | 0.6410 | 4818.5480 | 3.3952 |
| D90_REL | 0.8893 | 0.6387 | 0.1111 | 0.6514 | 4877.5090 | 3.6040 |
| D60_RAW | 0.8943 | 0.6649 | 0.0994 | 0.6260 | 4477.3639 | 3.4028 |
| D60_LOG | 0.8802 | 0.6550 | 0.1004 | 0.5846 | 4593.8307 | 3.0737 |
| D60_REL | 0.8787 | 0.6377 | 0.1069 | 0.5719 | 4722.5463 | 3.1952 |
| D30_RAW | 0.8995 | 0.6733 | 0.1026 | 0.5954 | 4798.5962 | 3.4855 |
| D30_LOG | 0.8876 | 0.6526 | 0.1067 | 0.5554 | 5312.4331 | 3.2446 |
| D30_REL | 0.8858 | 0.6558 | 0.1029 | 0.5712 | 5289.9609 | 3.4001 |

## 8. 최근 데이터만 쓰는 것이 실제로 generalization을 개선했는가?

일관되게 개선하지 못했다. 최근30일 label CDF는 fold1·fold4에 더 가깝지만 fold3에서는 오히려 더 멀다. window 비교의 최저 coverage도 모두85% 미만이다. DOES_RECENCY_MATTER는 Stage A에서 INCONCLUSIVE로 고정했다.

| fold | expanding_KS | recent30_KS | relative_reduction |
| --- | --- | --- | --- |
| 1 | 0.4642 | 0.2180 | 0.5304 |
| 2 | 0.3636 | 0.3218 | 0.1151 |
| 3 | 0.2639 | 0.4663 | -0.7667 |
| 4 | 0.3138 | 0.1768 | 0.4365 |
| 5 | 0.2704 | 0.2515 | 0.0699 |

## 9. base total model 중 raw/log/relative 무엇이 나았는가?

선택된 D60_RAW의 pooled pinball은 4477.36초다. RAW는 T, LOG는 log1p(T), REL은 V8의 log((T+1)/(walltime+1))를 쓴다. 가중치·threshold·global multiplier는 VALID coverage를 맞추려고 조정하지 않았다. 각 window에서 두 분위수300-tree 고정 learner만 사용했다. 모든15 base 후보 실패로 RAW의 일반적 우월성을 주장할 수 없다.

## 10. tail classifier의 >4h recall은?

사전 fixed threshold0.5에서 pooled recall 75.99%, precision 28.51%, >12h recall 86.05%다. 높은 pooled recall만으로 안전성을 통과시키지 않았다.

| fold | N | long4_N | ROC_AUC | PR_AUC | recall | precision | gt12h_recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 22144 | 9812 | 0.9117 | 0.8434 | 0.9184 | 0.8094 | 0.9667 |
| 2 | 36081 | 5440 | 0.9717 | 0.7937 | 0.9112 | 0.6814 | 0.9697 |
| 3 | 85643 | 11046 | 0.4948 | 0.2070 | 0.6594 | 0.1235 | 0.7866 |
| 4 | 21681 | 4929 | 0.8568 | 0.5434 | 0.7170 | 0.5489 | 0.8550 |
| 5 | 64688 | 7583 | 0.8253 | 0.3999 | 0.6203 | 0.2398 | 0.7098 |

## 11. tail classifier probability는 잘 calibrated되는가?

아니다. pooled Brier 0.225758는 TRAIN prevalence 상수의 0.166948보다 나쁘고 skill은 -0.3523다. pooled ROC-AUC 0.7932, PR-AUC 0.4959 및 prevalence 대비 lift 2.94는 평균적 구분력을 보여주지만 fold3 ROC-AUC 0.4948가 등록 최소0.55 아래다. 요청42절의 'tail classifier cannot meaningfully distinguish long jobs' 중단 조건을 temporal robustness 기준으로 적용했다. 모든 fold가 무구분이라는 주장이 아니다. calibration curve는 fixed10 bins이며 April로 보정하지 않았다.

## 12. tail expert가 >4h coverage를 얼마나 개선했는가?

base 62.60%에서 가장 높은 smooth L2가 64.24%로 약 1.63pp 개선했지만85%와 큰 차이가 남았다. tail 전문가의 보편적 안전성 개선은 검증되지 않았다.

| arm | Q90_coverage | min_fold_coverage | gt4h_coverage | gt12h_coverage | Q90_pinball | reservation_actual_GPUh |
| --- | --- | --- | --- | --- | --- | --- |
| GATE0_L0 | 0.8943 | 0.6649 | 0.6260 | 0.5458 | 4477.3639 | 3.4028 |
| GATE1_L1 | 0.8949 | 0.6613 | 0.6295 | 0.5498 | 4568.5666 | 3.5008 |
| GATE1_L2 | 0.8959 | 0.6650 | 0.6359 | 0.5589 | 4501.3725 | 3.5356 |
| GATE2_L1 | 0.8947 | 0.6632 | 0.6281 | 0.5500 | 4532.1960 | 3.4931 |
| GATE2_L2 | 0.8972 | 0.6653 | 0.6424 | 0.5632 | 4479.2487 | 3.5925 |

## 13. long weighting은 short-job reservation을 얼마나 악화시켰는가?

전체 TRAIN의 tail 가중치 최대4로 제한했다. 아래는 실제 T≤4h job에 unconditional tail Q90 expert를 적용한 진단 비교이며 gating 결과와 구분한다. reservation_change_vs_L0는 상대 증가 fraction이다.

| weight | N | reserved_GPUh | actual_GPUh | reservation_change_vs_L0 |
| --- | --- | --- | --- | --- |
| L0 | 191427 | 2630868.7500 | 104147.3847 | 0.0000 |
| L1 | 191427 | 2716707.0000 | 104147.3847 | 0.0326 |
| L2 | 191427 | 2950901.0000 | 104147.3847 | 0.1216 |

## 14. hard gate와 smooth gate 중 어떤 방식이 나았는가?

둘 다 실패했다. L2에서 smooth가 >4h64.24%로 hard63.59%보다 높고 Q90 pinball4479.25초로 hard4501.37초보다 낮았지만 예약 비율은 더 높았다. Gate0 base만의 pinball4477.36초보다 개선되지 않았고 classifier temporal 실패 때문에 최종 tail 사용을 중단했다. threshold0.5/alpha=p는 TRAIN 전에 등록했다.

## 15. 실제 long label을 inference에 사용했는가?

NO. 역사적으로 cutoff 전에 완결된 TRAIN label만 classifier target과 weight에 썼다. gating은 predicted p_long4만 사용했다. 실제 T>4h는 VALID 결과 집계에만 사용했고 feature에 넣지 않았다. quantile feature 생성은 기존9개 raw field whitelist만 읽는다.

## 16. 최종 TOTAL Q90 pooled coverage는?

진단 선택 D60_RAW/GATE0_L0의 pre-April coverage는 89.43% (N=230,237)다. 중단 때문에 final provider 학습은 하지 않았으므로 '최종 provider 성능'은 아니다.

## 17. TOTAL 최저 fold coverage는?

66.49%로85% 미달이다.

| fold | N | Q90_coverage | Q90_pinball | Q50_MAE | reservation_actual_GPUh | VALID_censored_N | quantile_repair_N |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 22144 | 0.6649 | 7489.0680 | 18794.6438 | 1.5907 | 340 | 0 |
| 2 | 36081 | 0.8867 | 1561.4414 | 6610.0454 | 2.7669 | 280 | 0 |
| 3 | 85643 | 0.9416 | 5866.3628 | 30913.6921 | 5.6445 | 503 | 0 |
| 4 | 21681 | 0.8686 | 5050.5868 | 17456.4326 | 3.5405 | 356 | 0 |
| 5 | 64688 | 0.9230 | 3041.7368 | 10454.9586 | 3.0125 | 257 | 0 |

## 18. TOTAL >4h coverage는?

62.60% / N=38,810;85% gate 실패다.

## 19. TOTAL >12h/>24h coverage는?

각각 54.58% / N=28,686, 27.75% / N=6,368다. >8h는 58.12%다.

## 20. TOTAL reservation/actual GPUh는?

3.4028; W0 대비 33.81% 작아20% 감소 gate만은 통과했다. 양의 실제 runtime에서 median Q90/actual 17.32, P90 4077.78로 짧은 job의 과도한 예약은 남아 있다.

## 21. V10보다 total runtime이 실제로 개선됐는가?

일부 지표만 개선됐다. V10 대비 min-fold 39.56%→66.49%, pinball 5235.03→4477.36초지만 >4h 69.65%→62.60%, >24h 54.98%→27.75%로 악화했다. 연구 provider 검증 실패다. B0/V8/Bconst의 과거 예측은 일부 또는 전체가 retrospective라 선택 기준의 causal baseline으로 사용하지 않았다.

## 22. checkpoint row를 어떻게 생성했는가?

read-only generator 감사에서 start+1800*k < known end인 시점만 만들었다. 타깃은 T−elapsed>0이고 모든 완결은 fold cutoff 전에 관측돼 있어야 한다. VALID의 1,450,526개 checkpoint를 검사했다. unresolved remaining label은 만들지 않았다. 생성기 검사만 완료했고 Stage C 모델 학습/점수 산출은 중단했다. future checkpoint count는 feature가 아니다.

## 23. 같은 job checkpoint가 TRAIN/VALID 양쪽에 들어갔는가?

NO. episode ID의 TRAIN/CAL/VALID 역할을 먼저 결정한 뒤 확장했으며 각 fold의 교집합0을 확인했다. 기존 expanding chronology 때문에 과거 VALID job이 완료 후 미래 fold TRAIN으로 들어갈 수는 있다. 이것을 동일 fold 내 label leakage와 혼동하지 않는다.

## 24. elapsed_seconds가 remaining prediction에 얼마나 중요한가?

V11의 정량 효과는 미평가다. R3_RAW/R4_LOG 및 R3_NO_ELAPSED ablation은 등록했지만 사용자 stop 조건으로 학습하지 않았다. 이미12시간 생존했다는 정보가 신규 제출 때 없다는 물리적 차이는 맞지만 효과 크기를 결과 없이 주장하지 않는다.

## 25. remaining direct model이 total-minus-elapsed보다 나은가?

미평가. remaining 모델을 학습하지 않았으므로 R0/R1 대비 개선을 주장할 수 없다. REMAINING_MODEL_COMPARISON.csv는 NOT_RUN_USER_STOP_CONDITION 상태를 명시한다.

## 26. remaining direct model이 V9/V10 conditional survival보다 나은가?

미평가. V9/V10의 기존 수치로 V11의 결과를 대신하지 않았다. 기존 hazard/CDF/finite-support 수치 구현과 산출물은 바이트 그대로 보존했다.

## 27. remaining Q90 coverage는 88–92%인가?

미평가이므로 통과 아님. REMAINING_Q90_GATE_PASS=FALSE는 fail-closed 상태이며 측정 coverage가0이라는 뜻이 아니다.

## 28. elapsed 0.5–1h와 >12h에서 모두 안정적인가?

미평가. elapsed0.5–1/1–2/2–4/4–8/8–12/12–24/>24h 및 actual-remaining strata는 등록했지만 성능표를 만들어내지 않았다.

## 29. overrun extension은 감소했는가?

V11 total-only pre-April stress는 queue gate를 통과하지 못했다. FORECAST 예약과 CAUSAL_CURRENT_SLOT_STRESS를 별도 행으로 보존했다. 완성된 TOTAL+REMAINING V11 시스템의 감소 여부는 미평가다. RUNNING GPU 유지/900초 연장/STAY 규칙을 바꾸지 않았다.

| fold | phase | start_lt_H | start_ge_H | reserved_GPUh | actual_GPUh | queue_wait_seconds | overrun_extensions | capacity_violations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | FORECAST_RESERVATION | 414 | 5 | 9420.2500 | 7274.3944 | 0.0000 | — | 0 |
| 1 | CAUSAL_CURRENT_SLOT_STRESS | 414 | 5 | — | 7274.3944 | 0.0000 | 439.0000 | 0 |
| 2 | FORECAST_RESERVATION | 617 | 3 | 20212.2500 | 9090.6478 | 90.0000 | — | 0 |
| 2 | CAUSAL_CURRENT_SLOT_STRESS | 617 | 3 | — | 9090.6478 | 0.0000 | 3020.0000 | 0 |
| 3 | FORECAST_RESERVATION | 1016 | 12 | 15448.7500 | 9131.4997 | 0.0000 | — | 0 |
| 3 | CAUSAL_CURRENT_SLOT_STRESS | 1016 | 12 | — | 9131.4997 | 0.0000 | 2266.0000 | 0 |
| 4 | FORECAST_RESERVATION | 1119 | 171 | 29035.5000 | 7719.1969 | 3759.0698 | — | 0 |
| 4 | CAUSAL_CURRENT_SLOT_STRESS | 1257 | 33 | — | 7719.1969 | 20.2326 | 867.0000 | 0 |
| 5 | FORECAST_RESERVATION | 628 | 14 | 16689.0000 | 8021.7150 | 0.0000 | — | 0 |
| 5 | CAUSAL_CURRENT_SLOT_STRESS | 628 | 14 | — | 8021.7150 | 0.0000 | 2016.0000 | 0 |

## 30. April total regression 결과는?

미실행. Stage B 중단 후 final fit/provider가 없어 April을 열지 않았다. APRIL_EXPOSED_TOTAL_METRICS.csv에는 NOT_RUN 상태만 있다. 기존에 노출된 April의 성격은 EXPOSED_REGRESSION_ONLY로 유지한다.

## 31. April remaining regression 결과는?

미실행. V11 remaining 모델이 없고 April을 평가하지 않았다. V10의94.12%를 V11 결과로 재사용하지 않았다.

## 32. April2 start<H는 W0/B0/V8/V9/V10/V11 각각 몇 개인가?

이 V11 실행에서는 재평가하지 않았다. 이전에 확인된 reference는150/47/111/127/91이고 V11은 NOT_RUN이다. 마지막 값을0으로 기록하거나 기존 예측을 V11이라고 부르지 않는다.

## 33. April 결과를 보고 수정했는가?

NO. 이 실행에서는 April payload를 읽지 않았고 V11 April 결과도 없다. 중단 결정은 pre-April classifier 결과와 사전 판정 기준으로만 내렸다.

## 34. May를 열었는가?

NO. 파일 payload 조회, 예측, descriptive table, calibration 모두 수행하지 않았다.

## 35. V42 research Runtime provider로 승격 가능한가?

아니다. TOTAL의 min-fold·>4h·>12h·queue gate 및 classifier temporal 구분력 실패, Stage C/최종 provider 미구현이다. RUNTIME_PROVIDER는 NOT_BUILT 설명만 담는다. 6개 이름의 freeze 파일 중 remaining/provider는 미실행 상태를 동결한 것이며 April 실행 허가가 아니다.

## 36. strict causal provider가 여전히 FALSE인 이유는?

Kestrel public archive의 requested walltime/GPU/nodes/cores/memory/QoS/partition/account/array descriptor가 최초 submit 당시 immutable 요청값임을 증명할 version authority가 없다. 29 engineered/9 raw 연구 descriptor를 그대로 사용했고 STRICT_CAUSAL_FEATURE_COUNT=0, REQUEST_VERSION_AUTHORITY_FOUND=FALSE다. elapsed는 RUNNING 이후 관측 가능한 값이지만 submit-time 요청 provenance 문제를 해결하지 않는다.

## 실행 및 재현 한계

CPU4 고정 learner, 독립 모델 최대2개 동시 학습을 사용했다. GPU trial은 생략했으며 backend를 혼합하지 않았다. 직접 quantile은 cutoff 전 exact completed labels만 학습하므로 administrative censor/maturity selection 한계가 남는다. 모든 window에서 등록한 최소 completed5,000/>4h200/>12h100 지원은 충족했다. 양의 Q50 및 Q90≥Q50 ordering은 등록된 deterministic repair로 처리했고 빈도를 기록했다. V11은 전체 CDF를 정의하지 않으므로 V10 proper NLL을 V11에 붙이지 않는다.

실행 순서: prepare11.py → forensic11.py → train_total11.py → tail11.py → STOP → close_stopped11.py → review11.py → verify_delivery11.py. checkpoint11.py의 생성기만 검사했으며 train_remaining11.py는 미실행 scaffold이고 stop guard가 새 학습을 차단한다. JSON은 exclusive-create이고 완료 연구 디렉터리에서 덮어쓰기 재실행하지 않는다. 후보 base75개 model-pair는 local hash-pinned cache에, 선택 base5개와 tail booster는 FOLD_MODELS에 보존했다. BASE_MODEL_FIT_RECEIPTS.json과 FOLD_MEMBERSHIP_REFERENCE.json을 이용해 재현한다. April 또는 May 데이터 없이 이번까지의 연구를 재현할 수 있다.
