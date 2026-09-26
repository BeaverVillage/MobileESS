# 비교 효과의 해석 범위

이 문서는 evaluation 결과를 보기 전에 작성했다. 모든 평가는 동일 issue에서 이용 가능한 입력으로 계산하지만 다음 비교들은 서로 다른 질문에 답한다.

| comparison/effect | 식별 가능한 효과 | 한계 |
|---|---|---|
| `temporal_same_GPU_cohort` | 같은 positive-GPU cohort·MoE·causal pooled calibration에서 시간 정책 차이 | 과거 전체 Job production MoE에 대한 효과가 아니다. 정책별 과거 예측 변화에 따라 causal residual도 달라지는 전체 refit 정책 효과다. |
| `architecture_same_policy`, Pending | 같은 시간 정책·입력·OHE/SVD에서 MoE+pooled와 raw multi-quantile의 차이 | point+pooled와 직접 quantile이라는 uncertainty 방식도 함께 다르다. tree family 하나만의 효과라고 해석하지 않는다. |
| `architecture_same_policy`, Running/ALL | 기존 total-minus-elapsed 방식에서 elapsed 조건부 remaining quantile 방식으로 바꾸는 전략의 차이 | architecture와 target formulation을 함께 바꾸므로 순수 architecture 효과가 아니다. Pending 결과를 별도로 확인한다. |
| `hierarchical_calibration` | 같은 raw multi-quantile 예측에 hierarchical residual calibration을 적용한 차이 | 완료 Job 기반 historical residual이며 distribution-free 보장을 주장하지 않는다. |
| `vs_frozen_production` | 같은 Job-issue에서 연구 candidate와 frozen authority 출력의 차이 | 기준선별 training cohort·feature representation·runtime 처리 방식이 다르므로 특정 한 변경의 인과 효과가 아니다. |

PR31 reference panel은 Pending 기준선이다. EXPOSED 구간의 frozen production 대비 paired gate는 관측 가능한 Pending 교집합에만 적용된다. Running은 새 모델 전체 모집단, elapsed regime 및 공통 GPU MoE의 total-minus-elapsed 비교를 별도로 보고한다. May의 frozen LightGBM Running reference도 total-minus-elapsed proxy이며 인증된 기존 remaining-runtime 모델이 아니다. 결측 baseline을 새 모델 출력으로 채우지 않는다.

`POINT_ARCHITECTURE_DIAGNOSTICS.csv`는 calibration 이전의 Pending MoE point와 LightGBM Q50의 MAE를 동일 Job-issue에서 비교한다. 학습 정책·입력·표현과 total-runtime target을 고정한 model-family 비교를 보완한다. 1/7 observed issue-day paired bootstrap을 사용하며 이 진단은 모델 선택에 사용하지 않는다. Running의 target formulation 변경을 순수 architecture 효과로 세지 않는다.

통계적으로 유의한 pinball 개선과 모든 operational gate 충족은 별개의 판정이다. 낮은 pinball이나 높은 Q99만으로 promotion을 허용하지 않는다. historical request-state와 ingestion provenance가 미확인인 상태에서는 운영 target/interface 인증, production replacement 및 optimizer integration 준비 완료를 주장하지 않는다.
