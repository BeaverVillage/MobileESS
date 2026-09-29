# 동결 Q50 보정 감사

**PRIMARY_NOMINAL_RUNTIME_CANDIDATE=NONE**. Q50을90% 상한으로 요구하지 않았고, 신규 수치 PASS cutoff도 만들지 않았다. D2 extreme의 비교 장점과 시간/fold/꼬리 부담을 함께 검토한 정성적 결론이다. PR94의 별도 scalar-duration NONE 판정은 그대로다.

| Model | Q50 MAE [h] | Q50 coverage [%] | Q50 time ratio [x] | Raw Q90 [%] | >12h Raw Q90 [%] |
|---|---:|---:|---:|---:|---:|
| V9_D1_ROLLING14 | 5.383 | 65.83 | 2.046 | 90.93 | 80.80 |
| V9_D2_NORMAL_1P5_NONE | 3.190 | 63.58 | 0.547 | 91.75 | 71.09 |
| V9_D2_EXTREME_1P0_NONE | 4.467 | 65.24 | 1.347 | 94.21 | 86.78 |
| V9_D3_ROLLING14 | 5.030 | 68.97 | 1.757 | 91.14 | 71.41 |
| V13_EXPANDING_S4 | 6.575 | 64.88 | 2.158 | 91.84 | 64.25 |
| V9_D2_NORMAL_1P0_NONE | 3.504 | 63.27 | 0.651 | 81.96 | 30.25 |

## D2 extreme의 temporal fold

| Fold | N | Q50 MAE [h] | C50 [%] | Calibration error [pp] | Time ratio [x] | >12h C50 [%] |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 22,144 | 5.709 | 40.64 | 9.36 | 0.549 | 0.062 |
| 2 | 36,081 | 1.743 | 46.53 | 3.47 | 0.854 | 0.735 |
| 3 | 85,643 | 6.506 | 75.10 | 25.10 | 2.739 | 6.528 |
| 4 | 21,681 | 4.937 | 44.97 | 5.03 | 0.646 | 0.275 |
| 5 | 64,688 | 2.704 | 77.83 | 27.83 | 1.239 | 3.171 |

## 1. Q50 coverage 정의는?

C50 = (1/N) sum I(T_actual≤Q50)다. 동일값은 covered로 포함한다. Underprediction은 엄격히 T_actual>Q50이며 두 비율의 합은1이다.

## 2. 왜 목표가90%가 아니라 약50%인가?

Q50은 중앙값 예측이기 때문이다. 연속적인 이상적 median의 coverage는 약50%다. 유한 표본·동일값·0-runtime 질량 때문에 정확히50%일 필요는 없고, pooled50%만으로 조건부 calibration이 입증되지도 않는다. 90% 견고성은 Q50에 강요하지 않는다.

## 3. 동일한230,237 jobs인가?

그렇다. PR94의30개 VALID parquet byte SHA, 5개 fold membership hash, submit-time proxy, 실제 runtime, Q50/Q90를 그대로 재사용했다. 새 population이나 CAL 데이터는 열지 않았다.

## 4. zero-runtime1,290건은?

전체·fold MAE, coverage, aggregate 시간 합에는 포함했다. Q50/T 개별 비율에서만 제외해 양의 runtime228,947건을 사용했다. 양수 runtime bucket과 별도로 EXACT_ZERO_DIAGNOSTIC행을 제공하며, 이 행의 시간 비율은 분모0이므로 null이다.

## 5. D2 extreme Q50 MAE는?

16080.6156905304초 = 4.46683769시간이다. PR94와 저장 float값을 정확히 재현했다.

## 6. pooled C50는?

65.24%다. pooled 수준에서는 중앙값 예측이 높은 방향이지만, 모든 fold에 같은 방향은 아니다.

## 7. calibration error는?

|C50−0.5|=0.15236257, 즉 15.2363pp다. 설명 지표이며 새 PASS cutoff는 만들지 않았다.

## 8. 실제 runtime이 Q50을 넘는 비율은?

34.76%다. 작업 발생빈도이지 필요한 GPU reserve 양이나 동시 overrun 확률은 아니다.

## 9. aggregate Q50 time ratio는?

1.3472652795배다. GPU 가중치나15분 rounding 없이 sum(Q50 seconds)/sum(T seconds)다.

## 10. 1.347x와 median per-job4.001x는 왜 다른가?

개별 Q50/T 중앙값은 4.00117870배다. Aggregate는 긴 실제 runtime이 큰 분모를 차지하지만 median은 양의-runtime 작업마다 동등한 순위를 부여한다. 양의T에 한하면 aggregate는 runtime 가중 평균과 연결되며, 여기에는 별도로 T=0행의 Q50 합도 포함된다. 짧은 작업 다수와 긴 꼬리의 이질성이 차이를 만든다. Q10=0.3863, Q25=0.7260, Q75=455.17, Q90=1515.37, Q95=5510.03; 평균은 진단용으로만 보존했다.

## 11. fold별 C50는?

fold 1: 0.406385; fold 2: 0.465259; fold 3: 0.750978; fold 4: 0.449703; fold 5: 0.778290. 위 fold 표에서는 백분율로 표시했다.

## 12. fold별 시간 비율은?

fold 1: 0.549112; fold 2: 0.854035; fold 3: 2.738566; fold 4: 0.645814; fold 5: 1.239292. 이5개 fold에서 비율<1인1/2/4는 C50<50%, 비율>1인3/5는 C50>50%였다. 보편 법칙이나 원인 증명은 아니다.

## 13. worst Q50 coverage fold는?

50%에서 가장 먼 median-calibration 기준은 fold5: C50 77.83%, error27.83pp다. 최소 coverage인 fold1(40.64%, error9.36pp)을 자동으로 최악이라 부르면 median 평가를 잘못 해석한다.

## 14. fold coverage std는?

ddof=0, 0.16021825 = 16.0218pp. Min 40.64%, max 77.83%다.

## 15. >4h C50는?

14.62%

## 16. >12h C50는?

2.49%; 따라서 해당 실제 tail 작업의 97.51%가 Q50을 넘는다.

## 17. >24h C50는?

0.44%

## 18. 0<T≤15min에서는?

N=160,951, C50 79.02%, MAE 3.385h, bucket 시간 비율 113.463배다.

## 19. 15min<T≤1h에서는?

N=14,457, C50 63.72%, MAE 2.093h, bucket 시간 비율 4.520배다.

## 20. 1h<T≤4h에서는?

N=14,729, C50 46.38%, MAE 3.799h, bucket 시간 비율 1.972배다.

## 21. 4h<T≤12h에서는?

N=10,124, C50 48.98%, MAE 4.128h, bucket 시간 비율 1.054배다.

## 22. 12h<T≤24h에서는?

N=22,318, C50 3.08%, MAE 8.454h, bucket 시간 비율 0.523배다.

## 23. T>24h에서는?

N=6,368, C50 0.44%, MAE 26.124h, bucket 시간 비율 0.299배다.

## 24. short jobs를 심하게 overpredict하는가?

실제0–15분 작업160,951건에서는 총 예측 시간이 실제의113.463배이고 MAE3.385h로 큰 과대예측 부담이 보인다. 이 bucket은 실제 결과로 정의했으므로 이를 predictor에 사용하거나 각 bucket이50%여야 한다고 주장하지 않는다.

## 25. long jobs를 심하게 underpredict하는가?

실제12–24h에서 시간 비율0.523, C50 3.08%; >24h에서는0.299, C50 0.44%, MAE26.124h다. 실제 긴 작업에서 명목 종료 이후 실행이 지속되는 부담이 크다. 결과 조건부 분석 자체를 조건부 median calibration 실패의 독립 증명으로 혼동하지 않는다.

## 26. aggregate ratio가 이를 숨기는가?

단독 보고하면 그렇다. 짧은 작업의 예측 시간 과잉과 긴 작업의 예측 시간 부족이 합계에서 상쇄된다. 1.347배를 모든 작업의 예측이34.7% 길다는 뜻으로 읽을 수 없다.

## 27. D2 normal1.5와 비교하면?

V9_D2_NORMAL_1P5_NONE: MAE 3.190h, C50 63.58%, 시간 비율 0.547, fold 표준편차 16.32pp, >12h C50 0.87%. D2 extreme은 MAE 4.467h / C50 65.24% / 1.347배 / std 16.02pp / >12h 2.49%이므로 어느 한 지표만으로 우위를 판정하지 않는다.

## 28. D1 rolling14와 비교하면?

V9_D1_ROLLING14: MAE 5.383h, C50 65.83%, 시간 비율 2.046, fold 표준편차 10.03pp, >12h C50 39.45%. D2 extreme은 MAE 4.467h / C50 65.24% / 1.347배 / std 16.02pp / >12h 2.49%이므로 어느 한 지표만으로 우위를 판정하지 않는다.

## 29. D3 rolling14와 비교하면?

V9_D3_ROLLING14: MAE 5.030h, C50 68.97%, 시간 비율 1.757, fold 표준편차 7.02pp, >12h C50 28.07%. D2 extreme은 MAE 4.467h / C50 65.24% / 1.347배 / std 16.02pp / >12h 2.49%이므로 어느 한 지표만으로 우위를 판정하지 않는다.

## 30. V13과 비교하면?

V13_EXPANDING_S4: MAE 6.575h, C50 64.88%, 시간 비율 2.158, fold 표준편차 15.07pp, >12h C50 14.06%. D2 extreme은 MAE 4.467h / C50 65.24% / 1.347배 / std 16.02pp / >12h 2.49%이므로 어느 한 지표만으로 우위를 판정하지 않는다.

## 31. normal1.0 진단과 비교하면?

V9_D2_NORMAL_1P0_NONE: MAE 3.504h, C50 63.27%, 시간 비율 0.651, fold 표준편차 16.32pp, >12h C50 0.91%. D2 extreme은 MAE 4.467h / C50 65.24% / 1.347배 / std 16.02pp / >12h 2.49%이므로 어느 한 지표만으로 우위를 판정하지 않는다. 낮은 Q90 신뢰도 때문에 과거 진단 대조군이었던 상태도 바꾸지 않는다.

## 32. MAE 최선은?

V9_D2_NORMAL_1P5_NONE, 3.1904h.

## 33. C50가50%에 가장 가까운 후보는?

V9_D2_NORMAL_1P0_NONE, 63.27%. 가장 가까워도 calibrated median이라고 승인한 것은 아니다.

## 34. time ratio가1에 가장 가까운 후보는?

V9_D2_EXTREME_1P0_NONE, 1.347265배. Normal1.0의0.651251배도 |ratio−1|=0.348749로 D2 extreme의0.347265와 거의 같다. 이 작은 차이로 모델을 선택하지 않는다.

## 35. 세 최선 모델이 동일한가?

아니다. MAE normal1.5, pooled calibration normal1.0, 시간 합의1근접성 extreme1.0이다.

## 36. D2 extreme은 Pareto 관점에서 합리적인가?

추가 연구의 비교 후보로는 합리적이다. 사전 고정 core3축에서는 normal1.5/normal1.0/extreme1.0이 frontier이며, temporal2축을 추가하면6개 모두 남는다. 하지만 Pareto membership만으로 provider를 선택하지 않는다. 방향이 바뀌는 fold calibration과 큰 short/long 오차, 미평가 reserve 부담을 함께 고려해 최종 primary nominal 채택은 NONE이다. 수치 PASS 기준을 추가한 판단이 아니다.

## 37. Q90를 optimizer nominal duration으로 쓰는가?

아니다. 의도된 nominal duration은 total Q50다. 이번에는 optimizer나 provider 통합도 하지 않았다.

## 38. Q90는 어떤 보조 정보인가?

동결 upper-quantile 신뢰도와 tail 위험의 보조 정보다. D2 extreme raw Q90 94.21%, >12h raw Q90 86.78%를 재현했다. 이를 Q50의 안전성이나 향후 pooled reserve의 충분성으로 바꾸어 해석하지 않는다. Full-distribution 결함도 수리하지 않았다.

## 39. Planning reserve를 구현했는가?

아니다. headroom도 계산하지 않았다. 의도된 구조는 total-Q50 nominal + 별도 overrun reserve이며 다음 연구 범위다.

## 40. Actual에 duplicate reserve를 두는가?

아니다. 관측된 RUNNING gang의 실제 점유를 유지한다. 같은 overrun을 별도 Actual reserve로 또 더하지 않는 구조를 문서화했다.

## 41. Actual RUNNING job 처리는?

실제 완료가 관측될 때까지 full GPU gang 점유가 유지된다. PENDING 시작 전 현재 physical capacity를 검사한다. 예측 nominal end나 remaining 값이 현재 점유를 해제할 수 없다. 이번에 실행한 로직은 아니다.

## 42. known과D-day submitted job이 같은 provider인가?

의도된 설계에서는 제출 후 metadata가 존재하면 동일 provider를 사용한다. 원래 알려진 작업인지 D-1에는 몰랐던 D-day 작업인지는 개별 Runtime 예측 규칙을 바꾸지 않는다. 이번 감사에서는 아직 provider를 선택하지 않았다.

## 43. D-day submission 전 unknown에 개별ML을 쓰는가?

아니다. 개별 작업이 제출되기 전에는 그 작업 metadata에 근거한 individual Runtime ML을 적용하지 않는다.

## 44. GPUh를 선택에 사용했는가?

아니다. 입력은 fold/job_id/submit_time/runtime_seconds/q50/q90 여섯 열뿐이고, GPU weighting은 없다.

## 45. Pinball을 main table에 쓰는가?

아니다. MAE/C50/time ratio의3열은 오차·median calibration·시간 합을 구분하는 좋은 주 표이지만, 이3개만으로 채택을 판단하기에는 부족하다. 반드시 fold 안정성과 실제 tail burden 표를 함께 제공해야 한다. Q90 및 >12h Q90는 보조 열이다.

## 46. May를 사용했는가?

아니다. April 선택, May payload, CC4/V42 optimizer outcome도 사용하지 않았다.

## 47. 새 ML을 학습했는가?

아니다. 추론조차 새로 하지 않았고 PR94 저장 VALID 예측의 산술만 계산했다. Conditional remaining도 바꾸지 않았다.

## 48. PR94 NONE 판정을 바꿨는가?

아니다. Q50+α(Q90−Q50) 규칙의 SELECTED_RUNTIME_MODEL=NONE, SELECTED_ALPHA=null과 원본 파일 모두 보존했다. 이번 nominal 인터페이스의 질문은 별개다.

## 49. PRIMARY_NOMINAL_RUNTIME_CANDIDATE는?

NONE. D2 extreme의 후보성은 연구 비교에 한정한다. PRIMARY_* 선택 지표는 null이며, 평가한 D2 extreme의 실제값은 comparison/FINAL_VERDICT의 audited_primary_metrics에 그대로 남긴다.

## 50. 다음 Planning reserve 설계로 넘어갈 수 있는가?

별도 사전등록 설계 연구를 위한 입력과 위험 특성은 확보했다. D2 extreme을 포함한 동결 baseline으로 overrun과 Actual 점유를 검증하는 연구는 가능하지만, 이 감사가 기본 provider 채택·V42 통합·reserve 충분성을 승인하지 않는다. 다음 연구 전까지 기존 provider/PR94 판정을 유지한다.

## 사용자 추가 요청에 따른 전체 버전 확장

위 원 요청 비교표·50문답의 최선/Pareto는 고정6개 후보 범위다. 추가 요청으로100개 저장 변형까지 확장했고, **V10의 Q50가 D2 extreme보다 유리한 후보를 발견했다.** 아래 표와 [전체 버전 해석](CROSS_VERSION_REVIEW_KO.md)을 함께 읽어야 한다.

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
