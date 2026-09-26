# CC4-v2.1 최종 검토

고정 선택: DEEPAR, weighted, 1일 refit, expanding residual calibration. 모든 선택은 DEVELOPMENT/CALIBRATION에서 종료했고 evaluation 결과로 재선택하지 않았다.

```text
             split  Q90_coverage  positive_coverage  burst_coverage  requirement_ratio  Q90_pinball
EXPOSED_EVALUATION        0.9193             0.8958          0.2753             2.5239     209.0425
    MAY_HISTORICAL        0.9315             0.9202          0.4493             2.8724     317.8462
```

## 판정

- target_interface_valid: **True**
- temporal_refit_improvement_supported: **True**
- new_model_superior_to_baseline: **False**
- improvement_statistically_robust: **False**
- production_replacement_supported: **False**
- optimizer_integration_ready: **False**

## 해석과 한계

PR63 target과 population, D−1 18:00 issue, UTC+10 고정 시계 및 기존 평가 날짜를 유지했다. May 예측의 refit에는 해당 시점에 성숙한 Mar–Apr와 이전 May label이 들어갈 수 있지만 May를 선택·튜닝에 쓰지 않았다. feature_available_time <= issue, 전체 하루 target의 label maturity < refit issue를 검사했다. 데이터 ingestion latency는 실제 운영 로그로 인증되지 않았다.

Stage A는 동일 LightGBM의 raw 예측, Stage B는 고정 temporal policy의 architecture, Stage C는 동일 예측의 calibration 효과다. 이 효과를 PAIRED_UNCERTAINTY.csv의 effect 열로 분리했다. 1일 paired bootstrap과 연속 날짜 구간을 넘지 않는 circular 7일 block bootstrap을 각각 2,000회 시행했다. neural seed는 독립적인 날짜처럼 부풀리지 않고 날짜별 seed 평균 loss로 계산했다. 다중 비교 후 evaluation winner를 고르지 않았다.

Hurdle은 P(W=0)을 포함한 무조건부 quantile 역산을 사용했다. burst expert의 혼합 CDF와 positive quantile 모델에는 알려진 TRAIN threshold만 사용했다. 임의 scaling/capping은 없으며 support와 quantile ordering만 보정했다. Calibration의 시계열 exchangeability 또는 distribution-free coverage는 주장하지 않는다.

모든 history·membership·model artifact는 새 namespace에 저장했다. 기존 frozen evidence, production, optimizer, MESS, IEEE123/8500, Actual/OpenDSS는 변경하거나 실행하지 않았다. 새 모델을 production으로 승격하거나 optimizer에 통합하지 않았다.

전체 모델 표, effect별 수치와 CI, 검증 결과 및 비교 그림은 [정량 검토 보충](REVIEW_SUPPLEMENT_KO.md)에 있다.
