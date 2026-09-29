# 시간적 drift forensic

새 모델 학습 전에 완료했다. 미래 VALID outcome은 진단 요약에만 사용하며 후보/feature/window를 변경하지 않는다. Runtime은 모든 역할에서 end-start와 일치했고 label semantics drift 또는 해결되지 않은 데이터 불일치는 발견하지 못했다. 미완결은 exact 분포에서 제외되어 censor/maturity selection 편향이 남는다.

## Fold별 판정

- Fold 1: MIXED; COVARIATE_SHIFT, LABEL_SHIFT, CONDITIONAL_SHIFT; exact-x common VALID mass=60.924%, within-cell KS=0.7476616007151188.
- Fold 2: MIXED; COVARIATE_SHIFT, LABEL_SHIFT, CONDITIONAL_SHIFT; exact-x common VALID mass=60.464%, within-cell KS=0.23734991652316192.
- Fold 3: MIXED; COVARIATE_SHIFT, LABEL_SHIFT; exact-x common VALID mass=18.129%, within-cell KS=0.3804717852306087.
- Fold 4: MIXED; COVARIATE_SHIFT, LABEL_SHIFT, CONDITIONAL_SHIFT, SUPPORT_LOSS; exact-x common VALID mass=41.765%, within-cell KS=0.3473184799799362.
- Fold 5: MIXED; COVARIATE_SHIFT, LABEL_SHIFT, CONDITIONAL_SHIFT, SUPPORT_LOSS; exact-x common VALID mass=30.044%, within-cell KS=0.6875512974617386.

조건부 변화는 runtime marginal만으로 추론하지 않았다. 9개 raw descriptor exact cell의 충분한 공통 지원에서 비교했으며 미측정 요인 및 archive proxy 한계 때문에 원인의 인과적 식별은 아니다.

## TRAIN→VALID runtime CDF와 최근30일

fold,expanding_KS,recent30_KS,relative_reduction
1,0.46418103653147835,0.2179908410373701,0.5303753839961381
2,0.36362386407235625,0.3217746669949467,0.1150892480177872
3,0.2639394277098354,0.4663033933996849,-0.7667060864901187
4,0.31383222975843095,0.17684311663482843,0.43650428520056217
5,0.2703837704476572,0.2514775871266525,0.06992351386217788


## Stage B 이전 플래그

{
  "time": "2026-09-29T02:16:56.365687+00:00",
  "TEMPORAL_DRIFT_FORENSIC_COMPLETE": true,
  "DOES_RECENCY_MATTER": "INCONCLUSIVE",
  "DOES_RECENCY_MATTER_SCOPE": "Descriptive proximity only; generalization must be tested in unchanged predeclared windows",
  "DOES_LONG_TAIL_PREVALENCE_SHIFT": true,
  "DOES_REQUEST_RUNTIME_RELATIONSHIP_SHIFT": true,
  "DOES_CATEGORY_SUPPORT_SHIFT": true,
  "fold_classifications": [
    {
      "fold": 1,
      "primary": "MIXED",
      "evidence": [
        "COVARIATE_SHIFT",
        "LABEL_SHIFT",
        "CONDITIONAL_SHIFT"
      ],
      "exact_x_common_VALID_mass": 0.6092395231213873,
      "within_exact_x_weighted_KS": 0.7476616007151188,
      "conditional_identification": "Within archived full raw x common support; observational evidence, not causal attribution",
      "label_semantics_inconsistency": false
    },
    {
      "fold": 2,
      "primary": "MIXED",
      "evidence": [
        "COVARIATE_SHIFT",
        "LABEL_SHIFT",
        "CONDITIONAL_SHIFT"
      ],
      "exact_x_common_VALID_mass": 0.6046395609877775,
      "within_exact_x_weighted_KS": 0.23734991652316192,
      "conditional_identification": "Within archived full raw x common support; observational evidence, not causal attribution",
      "label_semantics_inconsistency": false
    },
    {
      "fold": 3,
      "primary": "MIXED",
      "evidence": [
        "COVARIATE_SHIFT",
        "LABEL_SHIFT"
      ],
      "exact_x_common_VALID_mass": 0.18128743738542555,
      "within_exact_x_weighted_KS": 0.3804717852306087,
      "conditional_identification": "Within archived full raw x common support; observational evidence, not causal attribution",
      "label_semantics_inconsistency": false
    },
    {
      "fold": 4,
      "primary": "MIXED",
      "evidence": [
        "COVARIATE_SHIFT",
        "LABEL_SHIFT",
        "CONDITIONAL_SHIFT",
        "SUPPORT_LOSS"
      ],
      "exact_x_common_VALID_mass": 0.4176467875098012,
      "within_exact_x_weighted_KS": 0.3473184799799362,
      "conditional_identification": "Within archived full raw x common support; observational evidence, not causal attribution",
      "label_semantics_inconsistency": false
    },
    {
      "fold": 5,
      "primary": "MIXED",
      "evidence": [
        "COVARIATE_SHIFT",
        "LABEL_SHIFT",
        "CONDITIONAL_SHIFT",
        "SUPPORT_LOSS"
      ],
      "exact_x_common_VALID_mass": 0.3004421221864952,
      "within_exact_x_weighted_KS": 0.6875512974617386,
      "conditional_identification": "Within archived full raw x common support; observational evidence, not causal attribution",
      "label_semantics_inconsistency": false
    }
  ],
  "STOP_UNRESOLVED_DATA_INCONSISTENCY": false,
  "STOP_LABEL_SEMANTICS_DRIFT": false,
  "stageB_allowed": true,
  "April_read": false,
  "May_read": false
}

원본 상세: FOLD_DISTRIBUTION_SUMMARY.csv, FOLD_FEATURE_SHIFT.csv, FOLD_LABEL_SHIFT.csv, FOLD_LONG_TAIL_PREVALENCE.csv, FOLD_CATEGORY_SUPPORT.csv, FOLD_RELATIONSHIP_SUMMARY.csv, FOLD_EXACT_X_CONDITIONAL_SHIFT.csv. PSI는 TRAIN decile과 작은 descriptive 확률 보정을 사용한다. JS는 base2 divergence, Wasserstein은 원래 단위, KS는 CDF 최대 거리다. support가 희소한 exact-x 결과를 전체 모집단으로 확대하지 않는다.
