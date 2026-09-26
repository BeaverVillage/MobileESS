# Runtime-vNext 최종 검토

[전체 모델·Pending/Running·elapsed strata·효과별 CI와 최종 해석](REVIEW_SUPPLEMENT_KO.md)을 함께 확인한다. 아래 target/interface의 True는 offline event-time proxy에 한정하며 운영 provenance 인증을 뜻하지 않는다.

선택은 평가 전 MULTI_QUANTILE으로 고정했다. 평가 후 target·feature·hyperparameter·calibration·제외 규칙을 바꾸지 않았다.

```text
              role  Q90_coverage  GPU_coverage  long_under  missed_GPU_slots  overreserved_GPUh  requested_overreserved_GPUh
EXPOSED_EVALUATION        0.8718        0.8664      0.1780        19728.0000        251443.9116                  231793.4319
    MAY_HISTORICAL        0.8558        0.8781      0.2739       210805.0000       1194291.5958                 2474000.1425
```

## 판정

- target_interface_valid: **True**
- temporal_refit_improvement_supported: **False**
- new_model_superior_to_baseline: **False**
- improvement_statistically_robust: **False**
- production_replacement_supported: **False**
- optimizer_integration_ready: **False**

## 기준선과 모집단

PR27 MoE는 당시 전체 Job training과 고정 recipe로 245개 예측을 정확히 재현한다. PR42 `ROLLING_Q90_TRACK_P_L2`는 frozen May 31일분을 저장된 예측과 비교한다. 두 기준선은 모델뿐 아니라 학습 모집단도 다르다. 새 temporal/architecture 연구는 raw positive-GPU completed history를 모든 arm에 공통으로 적용한다. 따라서 새 MoE arm을 과거 전체 Job production과 동일하다고 부르지 않으며, 전체 Job production temporal refit 효과는 이 연구로 확정할 수 없다. PR31의 고정 reference는 사전에 정해진 동일 Job-issue 교집합에서만 paired 비교한다. unmatched 수를 숨기지 않는다. May는 최신 production 모델로 동일 feature를 재계산하며 Running에는 total-minus-elapsed라는 명시적인 naive remaining baseline을 사용한다.

## Causality와 Pending/Running

학습은 `job_end_time < issue_time`을 지킨다. 요청 feature는 submit 이후 관측 가능하다는 event-time proxy이며 실제 request 수정 이력 및 historical scheduler snapshot provenance는 미확인이다. 이를 운영 인과성 인증으로 해석할 수 없다. Pending은 total runtime, Running은 elapsed를 입력으로 하는 remaining runtime이다. Running training의 landmark는 Job ID의 고정 hash로만 선택하고, 해당 elapsed까지 살아 있던 완료 Job만 사용한다. 완료 Job만 학습하는 조건에 따른 completion selection bias가 있을 수 있으며 censored-aware survival 성능을 주장하지 않는다.

Hierarchical calibration은 충분한 과거 support가 있을 때 hardware → standby/state → requested-walltime bucket → GPU bucket 순으로 세분한다. support가 부족하면 causal parent로 돌아간다. residual은 당시 issue에서 나온 out-of-sample 예측만 사용하고 current issue 전에 완료된 Job만 남긴다. 동일 Job/state는 최신 한 관측만 남겨 support를 부풀리지 않는다. Q50/Q90/Q95/Q99는 모두 추정하되 승격 판단은 Q90 gate로 하며 Q99/UARP로 coverage만 끌어올리지 않는다. 임의 cap/scaling은 없다.

## 통계와 해석

학습기간·architecture·calibration 효과를 PAIRED_UNCERTAINTY.csv의 effect로 분리했다. paired issue-day bootstrap과 관측된 issue-day 순서의 circular 7-issue block bootstrap을 각 2,000회 시행했다. block_days는 관측 issue-day 개수이며 Apr15 누락을 사이에 둔 관측도 순서를 유지한다. 5일짜리 짧은 구간을 따로 circular 7일 resampling하여 그 구간의 기여가 고정되는 문제를 피한다. 오래 남는 Job의 dependence가 7개 issue를 넘을 수 있으므로 CI는 모든 종속성에 대한 보장이 아니다. GPU-weighted coverage는 requested GPU 개수로 가중한다. GPU-slots는 runtime-origin에서 24시간 동안의 predicted-finished/actually-active occupancy proxy이다. optimizer schedule, 실제 dispatch 또는 OpenDSS 결과가 아니다. overreserved GPU·h는 동일 target에 대한 requested-walltime reference와 비교한다.

기존 frozen evidence는 보존했다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS를 수정하거나 실행하지 않았으며 production promotion과 integration을 수행하지 않았다.
