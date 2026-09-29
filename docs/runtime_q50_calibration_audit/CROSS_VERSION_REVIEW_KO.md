# 사용자 추가 요청: v1–v16 동결 Q50 확장 비교

100개 저장 변형(고유 Q50 배열87개)을 원래230,237개 작업에 정확히 맞췄다. 이 중3개는 미래 학습/보정이 과거 fold에 적용된 비인과적 소급 참고치다. 같은 배열의 alias·Q90-only 차이를 독립 모델 개선으로 중복 계산하지 않는다. 고유 causal Q50 비교는 84개다.

| 모델 | MAE [h] | C50 [%] | 시간비율 [x] | fold C50 min–max [%] | >12h C50 [%] |
|---|---:|---:|---:|---:|---:|
| V9::D2_extreme_1.0__NONE | 4.467 | 65.24 | 1.347 | 40.64–77.83 | 2.49 |
| V10::T3_LOGISTIC_ROLLING14_calibrated | 2.700 | 45.04 | 0.803 | 30.90–58.34 | 14.27 |
| V10::T3_ISOTONIC_ROLLING14_calibrated | 2.727 | 46.79 | 0.853 | 36.35–63.08 | 19.01 |
| V11::SELECTED_TOTAL | 5.257 | 72.50 | 1.871 | 46.72–82.08 | 27.34 |
| V12::EXPANDING_R2 | 3.333 | 62.84 | 0.852 | 28.25–76.12 | 7.73 |
| V13::EXPANDING_S4 | 6.575 | 64.88 | 2.158 | 38.60–80.16 | 14.06 |
| V15::R2 | 5.318 | 68.05 | 1.806 | 39.79–80.69 | 17.61 |
| V16::R16-A | 6.183 | 68.87 | 2.088 | 39.57–82.46 | 19.43 |
| V16::R16-B | 5.495 | 68.29 | 1.693 | 47.40–81.95 | 2.18 |
| V16::R16-C | 6.318 | 68.31 | 2.096 | 36.49–81.28 | 18.81 |

**확장 비교는 결론을 보강한다. D2 extreme은 전체 모델 중 최선의 명목 Q50가 아니다.** V10 T3 isotonic rolling14가 MAE·pooled50% 근접성·시간 비율1 근접성이라는 사전 고정3축에서 D2 extreme을 엄격하게 지배한다. 이 모델의 coverage46.79%를90% 미달이라는 이유로 기각하지 않는다. Median으로는50%가 기준이다. 다만 fold36.35–63.08%, 실제>12h C50 19.01%라는 편차와 overrun 부담이 있으므로 이 감사에서 새 provider 승격이나 reserve 충분성을 주장하지 않는다.

전체 unique causal 최저 MAE는 V10::T3_LOGISTIC_ROLLING14_calibrated (2.700359h)다. Pooled median coverage가 가장50%에 가까운 모델은 V9::D2_logistic_1.0__STATIC14이지만, 그 pooled 수치만으로 시간적 안정성을 결론내리지 않는다.

V13만 따로 본다면 expanding S4는 MAE6.575h, C50 64.88%, 시간 비율2.158이다. V15 R2는5.318h/68.05%/1.806배, V16 A/B/C는6.183/5.495/6.318h 및 C50 68.87/68.29/68.31%다. 더 뒤의 버전이라는 이유만으로 Q50가 우수하지 않다. 모든 원래5-fold 결과와 bucket/ratio분포는 CROSS_VERSION_Q50_*.csv에 있다.

V10 rolling calibration은 당시 완료가 관측된 선행 이벤트로 업데이트한 기존 동결 확률 보정이다. 이번에는 저장 Q50/Q90만 읽었으며 보정값·모델을 새로 학습하지 않았다. 기존 causal audit의 미래 event/residual read=0 및 max_completion_used<day를 재검증한다. PR94의 CAL-only alpha 보간과 동일한 방법으로 혼동하지 않는다.

계보별 범위: v6 NONCAUSAL_RETROSPECTIVE_REFERENCE: 1개; v8 NONCAUSAL_RETROSPECTIVE_REFERENCE: 1개; v9 FROZEN_CAUSAL_TOTAL: 33개; v9 NONCAUSAL_RETROSPECTIVE_REFERENCE: 1개; v10 FROZEN_CAUSAL_TOTAL: 19개; v11 FROZEN_CAUSAL_TOTAL: 21개; v12 FROZEN_CAUSAL_TOTAL: 9개; v13 FROZEN_CAUSAL_TOTAL: 10개; v15 FROZEN_CAUSAL_TOTAL: 2개; v16 FROZEN_CAUSAL_TOTAL: 3개.

v1–v5는 다른 issue/state 모집단, Running remaining 또는 May 노출 계보이므로 해당 payload를 새로 열어 비교하지 않았다. v6 constant/v8 M3_F2와 B0의 저장 소급 예측은 별도 NONCAUSAL_RETROSPECTIVE_REFERENCE이며 원래 모델 fit/보정이 과거 fold 이후라 causal 우승 후보가 아니다. v7은 source 포렌식, v14/J0·J1은 V13 재현이고 J2–J5 미실행, v14R1/R2도 포렌식이다. V13 ABL_E의 미완료 fold는 NOT_POOLED_INCOMPLETE_FROZEN_FOLDS이며 수치를 채우거나 새로 학습하지 않았다. 전체 계보/제외 근거는 RUNTIME_VERSION_INVENTORY.csv다.

공식 PRIMARY_NOMINAL_RUNTIME_CANDIDATE는 NONE으로 유지한다. 이는 원 요청의 D2 extreme 채택 여부에 대한 결론이며, 확장100개 모두가 무용하다거나 모든 nominal 설계가 불가능하다는 뜻이 아니다. 후속 Planning reserve 연구에서는 V10 T3 isotonic rolling14와 최저 MAE logistic rolling14 등을 비교 기준으로 검토할 근거가 생겼다. 신규 선정 threshold·reserve/headroom·optimizer·remaining 모델은 이번 범위에 추가하지 않았다. PR94 NONE/alpha-null도 변경하지 않았다.
