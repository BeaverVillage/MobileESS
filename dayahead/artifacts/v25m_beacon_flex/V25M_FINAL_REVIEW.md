# V25M BEACON-Flex 최종 과학 검토

RESULT CLASSIFICATION: `V25M_BEACON_NOVELTY_PASS_HAZARD_SIGNAL_FAIL`
## 결론

BEACON-Flex BEC-A는 burst WAPE와 질량비 일부는 개선했지만 hazard signal, body 보호, 전체 mean, calibration, 통계적 유의성 gate를 통과하지 못했다. 따라서 production 권위는 B2 mean과 B3 Q50/Q90으로 유지한다.
## 핵심 수치

- Mean WAPE: 1.171953571503
- Q50 WAPE: 0.938359761863
- CRPS: 2583.019386918855
- Burst WAPE: 0.799034629542
- Mass ratio: 1.007675578352
- P90 Brier skill: -0.064270944924
## 수학 및 절차 검증

CDF·hazard 순서·hazard–severity 질량·baseline recovery·96×6×5 질량보존은 통과했다. April은 freeze SHA 검증 후에만 열었고 이후 fit/calibration/selection 호출은 모두 0이다. GPU-h facility scale, beta_AIDC, PUE 호출도 모두 0이다.
## Q1–Q18

- Q1: 동일한 전체 prior architecture는 발견되지 않았고 부분 중첩이 있는 별개의 조합이다.
- Q2: 예, canonical B2/B3가 1e-9 이내 재현됐다.
- Q3: 같은 151일에서 weekday-factorized Mean WAPE 0.946736으로 B2 0.976108보다 낮았지만 이 감사만으로 production authority를 바꾸지 않았다.
- Q4: 예, 교차 0·음수 0·BR-A 평균오차 9.05e-11로 reconcile됐다.
- Q5: 아니오. 일부 양의 AP skill은 있었으나 bootstrap/Brier/calibration gate를 통과하지 못했다.
- Q6: 최종 hazard audit P90 AUPRC=0.175175017001, Brier skill=-0.083319087229.
- Q7: 명시적 pressure는 fold별로 불안정했고 강한 일반 집계 대비 일관된 개선을 입증하지 못했다.
- Q8: TCN/SSL은 false gate 규칙으로 full config에 채택되지 않았다.
- Q9: 아니오. multi-threshold 구조는 유효했지만 성능 우위를 입증하지 못했다.
- Q10: 예, 최대 질량 오차 1.11e-16이다.
- Q11: false gate 때문에 최종 모델에서 analog를 사용하지 않아 우위를 주장하지 않는다.
- Q12: 예, 최대 CDF 복귀오차 1.11e-16이다.
- Q13: BEC-A Mean WAPE=1.171953571503, Q50 WAPE=0.938359761863, CRPS=2583.019386918855.
- Q14: 아니오. body Mean WAPE가 3.090411로 비열등성에 실패했다.
- Q15: Burst WAPE=0.799034629542로 0.763990 강한 목표에는 실패했다.
- Q16: 아니오. BEACON을 proposed/production model로 채택하지 않는다.
- Q17: NO. frozen facility scale을 GPU-h에 곱하지 않았다.
- Q18: NO. 새 grid science는 승인되지 않는다.
