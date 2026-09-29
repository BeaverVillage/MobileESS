# Runtime 최종 duration calibration 검토

결론: **SELECTED_RUNTIME_MODEL=NONE, SELECTED_ALPHA=null**. 단위는 초이며 GPUh로 모델을 선택하지 않았다.

| Model | Q50 MAE [h] | Raw Q90 [%] | >12h Raw Q90 [%] | Q50 time [x] | Q90 time [x] | α (fold 1→5) | OP coverage [%] | OP time [x] |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| V9_D1_ROLLING14 | 5.383 | 90.93 | 80.80 | 2.046 | 4.357 | 1.00;1.00;0.90;1.00;1.00 | 89.90 | 4.235 |
| V9_D2_NORMAL_1P5_NONE | 3.190 | 91.75 | 71.09 | 0.547 | 3.743 | 1.00;0.60;0.35;0.15;1.00 | 86.22 | 2.546 |
| V9_D2_EXTREME_1P0_NONE | 4.467 | 94.21 | 86.78 | 1.347 | 4.476 | 1.00;0.55;0.65;0.25;1.00 | 90.46 | 3.560 |
| V9_D3_ROLLING14 | 5.030 | 91.14 | 71.41 | 1.757 | 3.919 | 1.00;1.00;0.90;0.40;1.00 | 89.84 | 3.642 |
| V13_EXPANDING_S4 | 6.575 | 91.84 | 64.25 | 2.158 | 3.807 | 1.00;0.70;0.95;0.15;1.00 | 87.84 | 3.529 |
| V9_D2_NORMAL_1P0_NONE | 3.504 | 81.96 | 30.25 | 0.651 | 2.346 | 1.00;1.00;0.75;0.35;1.00 | 80.56 | 2.085 |

Raw Q90→보정 duration의 시간 합 감소율: V9_D1_ROLLING14: 2.80%; V9_D2_NORMAL_1P5_NONE: 31.97%; V9_D2_EXTREME_1P0_NONE: 20.46%; V9_D3_ROLLING14: 7.06%; V13_EXPANDING_S4: 7.31%; V9_D2_NORMAL_1P0_NONE: 11.14%. 감소율은 동일 신뢰도에서의 무손실 이득이 아니다.

## 1. Runtime 출력 단위는?

초(seconds)다. MAE는 초와 시간으로 함께 보고한다.

## 2. 주 비율을 초로 측정한 이유는?

예측 대상과 같은 단위로 합산한 sum(predicted seconds)/sum(actual seconds)로 모델의 시간상 보수성을 측정한다. 개별 작업 비율의 평균·중앙값과 다르다.

## 3. GPUh를 선택에 사용했는가?

아니다. 주 계산 입력에서 GPU/node 열을 제거했고, 임의 GPU 가중치 변경에도 선택이 불변인지 테스트했다.

## 4. 후보별 aggregate Q50 time ratio는?

V9_D1_ROLLING14: 2.0465; V9_D2_NORMAL_1P5_NONE: 0.5474; V9_D2_EXTREME_1P0_NONE: 1.3473; V9_D3_ROLLING14: 1.7567; V13_EXPANDING_S4: 2.1580; V9_D2_NORMAL_1P0_NONE: 0.6513

## 5. 후보별 aggregate Q90 time ratio는?

V9_D1_ROLLING14: 4.3566; V9_D2_NORMAL_1P5_NONE: 3.7427; V9_D2_EXTREME_1P0_NONE: 4.4757; V9_D3_ROLLING14: 3.9189; V13_EXPANDING_S4: 3.8074; V9_D2_NORMAL_1P0_NONE: 2.3462

## 6. 작업별 Q50/actual 중앙값은?

V9_D1_ROLLING14: 3.3189; V9_D2_NORMAL_1P5_NONE: 2.6111; V9_D2_EXTREME_1P0_NONE: 4.0012; V9_D3_ROLLING14: 7.1896; V13_EXPANDING_S4: 2.4097; V9_D2_NORMAL_1P0_NONE: 2.2566

## 7. 작업별 Q90/actual 중앙값은?

V9_D1_ROLLING14: 25.1540; V9_D2_NORMAL_1P5_NONE: 17.9154; V9_D2_EXTREME_1P0_NONE: 13.3377; V9_D3_ROLLING14: 28.3018; V13_EXPANDING_S4: 9.9136; V9_D2_NORMAL_1P0_NONE: 8.2251; T=0인 1,290행은 개별 비율에서 제외했다. 나머지 228,947행의 Q25/Q75/Q90/진단용 평균도 CSV에 있다. 0행은 aggregate 합·MAE·coverage에서는 유지했다.

## 8. Q50 MAE [h]는?

V9_D1_ROLLING14: 5.3834; V9_D2_NORMAL_1P5_NONE: 3.1904; V9_D2_EXTREME_1P0_NONE: 4.4668; V9_D3_ROLLING14: 5.0297; V13_EXPANDING_S4: 6.5748; V9_D2_NORMAL_1P0_NONE: 3.5045

## 9. Raw Q90 coverage는?

V9_D1_ROLLING14: 90.93%; V9_D2_NORMAL_1P5_NONE: 91.75%; V9_D2_EXTREME_1P0_NONE: 94.21%; V9_D3_ROLLING14: 91.14%; V13_EXPANDING_S4: 91.84%; V9_D2_NORMAL_1P0_NONE: 81.96%

## 10. >12h raw Q90 coverage는?

V9_D1_ROLLING14: 80.80%; V9_D2_NORMAL_1P5_NONE: 71.09%; V9_D2_EXTREME_1P0_NONE: 86.78%; V9_D3_ROLLING14: 71.41%; V13_EXPANDING_S4: 64.25%; V9_D2_NORMAL_1P0_NONE: 30.25%

## 11. 운영 duration 공식은?

T_op = Q50 + α(Q90−Q50), 0≤α≤1. α<1일 때 Q90라고 부르지 않으며 CALIBRATED_OPERATIONAL_RUNTIME이다. 15분 반올림도 하지 않는다.

## 12. 새 ML을 학습했는가?

아니다. V9 CAL 저장 quantile과 V13 동결 모델의 CAL 추론만 사용했다. V13은 저장된 VALID 32행/fold의 추론을 비트 단위 재현했다. fit 호출 금지 guard를 적용했다.

## 13. α grid는?

0.00, 0.05, …, 1.00의 21개 값이다. 6×5×21=630개 CAL 조합을 사전 고정했다.

## 14. α를 VALID에서 골랐는가?

아니다. CAL에서 coverage≥90% 중 최소 시간 비율을 택했다. 불가능하면 최대 coverage, 동일하면 최소 시간 비율·최소 α를 택했다. 30개 α를 SHA로 동결한 후 VALID 운영 지표를 계산했다. 기존 raw VALID 결과가 이미 알려진 연구라는 점은 공개한다.

## 15. May를 사용했는가?

아니다. April/May labels를 새로 디코딩하거나 선택에 사용하지 않았다. 기존 evidence 보존은 byte hash 검사다.

## 16. 90% 목표를 85%로 바꿨는가?

아니다. α 보정과 최종 판정 모두 90% 명목 기준을 유지했다. 최종 선택은 pooled 및 모든 fold≥90%라는 보수적 규칙을 CAL/운영 VALID 실행 전에 고정했다.

## 17. 후보별 α는?

V9_D1_ROLLING14: 1.00;1.00;0.90;1.00;1.00; V9_D2_NORMAL_1P5_NONE: 1.00;0.60;0.35;0.15;1.00; V9_D2_EXTREME_1P0_NONE: 1.00;0.55;0.65;0.25;1.00; V9_D3_ROLLING14: 1.00;1.00;0.90;0.40;1.00; V13_EXPANDING_S4: 1.00;0.70;0.95;0.15;1.00; V9_D2_NORMAL_1P0_NONE: 1.00;1.00;0.75;0.35;1.00. 순서는 fold 1→5이며 단일 평균 α를 만든 적 없다.

## 18. VALID 운영 coverage는?

V9_D1_ROLLING14: 89.90%; V9_D2_NORMAL_1P5_NONE: 86.22%; V9_D2_EXTREME_1P0_NONE: 90.46%; V9_D3_ROLLING14: 89.84%; V13_EXPANDING_S4: 87.84%; V9_D2_NORMAL_1P0_NONE: 80.56%

## 19. 최저 fold 운영 coverage는?

V9_D1_ROLLING14: 80.90%; V9_D2_NORMAL_1P5_NONE: 57.26%; V9_D2_EXTREME_1P0_NONE: 67.16%; V9_D3_ROLLING14: 72.81%; V13_EXPANDING_S4: 53.79%; V9_D2_NORMAL_1P0_NONE: 56.71%

## 20. >12h 운영 coverage는?

V9_D1_ROLLING14: 76.57%; V9_D2_NORMAL_1P5_NONE: 59.12%; V9_D2_EXTREME_1P0_NONE: 73.17%; V9_D3_ROLLING14: 65.80%; V13_EXPANDING_S4: 56.20%; V9_D2_NORMAL_1P0_NONE: 28.49%

## 21. 운영 시간 비율은?

V9_D1_ROLLING14: 4.2345; V9_D2_NORMAL_1P5_NONE: 2.5462; V9_D2_EXTREME_1P0_NONE: 3.5599; V9_D3_ROLLING14: 3.6421; V13_EXPANDING_S4: 3.5293; V9_D2_NORMAL_1P0_NONE: 2.0848

## 22. <1.2x가 나왔는가?

아니다. 모든 후보가 2배보다 컸다. 낮은 Q50 하한만으로 1.2배를 달성했다고 주장하지 않는다.

## 23. <1.5x가 나왔는가?

아니다. 이 CAL-only grid에서 실측되지 않았다. 모든 보정법의 불가능성을 증명한 것은 아니다.

## 24. <2.0x가 나왔는가?

아니다. 최소는 진단 대조군 D2 normal1.0의 2.0848배이며 coverage 80.56%로 심각한 undercoverage도 남는다.

## 25. Q50 floor에서 exact1.0x는 가능한가?

D1 2.0465, extreme1.0 1.3473, D3 1.7567, V13 2.1580은 하한만으로 불가능하다. normal1.5 0.5474, normal1.0 0.6513은 하한이 배제하지 않을 뿐, 90% 신뢰도·grid에서 실현 가능하다는 뜻이 아니다. 특히 D1/V13은 α≥0이면 2배 미만도 구조적으로 불가능하다.

## 26. Q50 MAE 최선은?

D2 normal1.5: 3.1904시간이다.

## 27. >12h coverage 최선은?

Raw Q90는 D2 extreme1.0 86.78%, 보정 후는 D1 76.57%다. 서로 다른 질문이다.

## 28. 운영 비율 최저는?

전체 진단 포함 normal1.0 2.0848; primary만 보면 normal1.5 2.5462다. 신뢰도 통과를 뜻하지 않는다.

## 29. 정확도·tail·최저 비율의 최선이 같은가?

아니다. 위 26–28번처럼 서로 다른 후보와 평가 역할이다.

## 30. D1이 Pareto에 남는가?

그렇다. 5개 primary 모두 5축 Pareto에 남는다. D1은 높은 최저 fold·운영 tail coverage와 큰 시간 비율의 trade-off다. Pareto membership은 안전성 통과가 아니다.

## 31. normal1.5가 D1을 이겼는가?

MAE 3.190 vs 5.383h, 시간 비율 2.546 vs 4.235로 낮지만 최저 fold 57.26% vs 80.90%, >12h 59.12% vs 76.57%로 낮다. 단일 우승으로 볼 수 없다.

## 32. extreme1.0이 D1을 이겼는가?

Pooled 90.46%와 시간 비율 3.560는 유리하지만 최저 fold 67.16%와 >12h 73.17%는 D1보다 낮다. 공동 지배하지 않는다.

## 33. D3는 경쟁력이 있는가?

Pareto에는 남지만 운영 3.6421배, pooled89.84%, min-fold72.81%, >12h65.80%다. D1보다 저렴한 시간 합과 약한 tail/temporal reliability의 trade-off이며 선택되지 않았다.

## 34. V13의 장점은?

D1보다 운영 시간 비율이 3.529 vs 4.235로 작다. 그러나 MAE 6.575h, >12h 56.20%, min-fold 53.79%로 악화된다. D1보다 일괄 우월하지 않다.

## 35. normal1.0은 단순 underprediction인가?

낮은 비율에 raw 81.96%, 운영 80.56%, >12h 운영 28.49%가 동반된다. 안전한 sharpness로 해석할 수 없다. 모든 오차의 원인을 단일 메커니즘으로 단정하지는 않는다.

## 36. V9 zero-support를 고쳤는가?

아니다. 기존 full-distribution 결함은 남는다.

## 37. 그런데 V9 quantile은 왜 비교할 수 있는가?

저장된 유한·비음수·순서 일치 Q50/Q90 값의 경험적 정확도와 coverage는 별도로 검증할 수 있다. full-density 적합성을 인정한다는 뜻은 아니다.

## 38. scheduler가 full distribution을 사용하는가?

아니다. 이번에는 scheduler 자체도 실행하지 않았다. 후보 인터페이스는 초 단위 Q50/Q90와 duration scalar뿐이다.

## 39. submission metadata를 observable로 간주했는가?

그렇다. 사용자가 승인한 historical proxy 가정이다. immutable initial-submit byte receipt가 있다는 주장은 하지 않는다.

## 40. 그 가정은 RADDiT 때문인가?

아니다. RADDiT 이전부터 존재한 역사적 archive/version 문제다. 그 provenance 부족만으로 후보를 기각하지 않았다.

## 41. RADDiT를 재학습했는가?

아니다. 신규 의미 특징·embedding·external telemetry 탐색도 하지 않았다.

## 42. CC4를 변경했는가?

아니다. T0/B0와 다른 CC4 연구 후보도 그대로 보존했다.

## 43. V42를 실행했는가?

아니다. PR93 canary/A1/M1/A2/M2/OpenDSS/IEEE123/IEEE8500도 실행하지 않았다.

## 44. 주 선택 어디에도 GPU weighting이 있었는가?

없다. sum T, sum Q50, sum Q90, sum T_op 및 작업별 동일 가중 coverage만 사용했다.

## 45. GPUh는 downstream 진단으로만 남는가?

그렇다. 수정 지시 이전의 GPU 기반 예비 감사는 .local/superseded_shared_reserve에 보존했으며 선택·논문 주 표에 들어가지 않는다. 공유 reserve fitting/queue replay는 시작하지 않았다.

## 46. 정확한 선택 모델은?

NONE. 이전 과학적 negative result를 바꾸지 않았고, 새 duration-interface 판정에서도 선택 후보가 없다.

## 47. 정확한 최종 α는?

null. 모든 candidate-fold α는 표에 있지만 운영 승격용 단일 α는 없다.

## 48. V42가 사용할 정확한 공식은?

연구 후보 공식은 Q50+α(Q90−Q50)지만 이번에 승인된 모델/α는 없다. V42에 적용하거나 현재 provider를 바꾸지 않는다.

## 49. 논문에 공개할 한계는?

이미 노출된 pre-April 5-fold의 exact-matured 작업 조건부 표본이다. Censored/pending을 0으로 만들지 않았고 평가에서 동일하게 제외했다. CAL→VALID temporal shift, CAL rolling warm-up(min200/부족시0), coarse α grid, 가정된 제출 metadata provenance, 모델별 CAL 추론 재생성 범위, 기존 full-distribution 결함을 공개해야 한다. 기준을 만족하지 못했다는 결과는 모든 미래 예측법의 불가능성 증명이 아니다.

## 50. 선택은 동결됐는가?

그렇다. FINAL_SELECTION_FREEZE.json과 alpha/evidence SHA로 NONE 판정을 동결했다. 기존 증거 보존·검증 결과는 VERIFICATION.json에 있다.
