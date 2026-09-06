# 별도 method revision 후보 — 제안만

아래는 구현·학습·선택하지 않은 비교안이다. May Actual은 학습·validation·model selection·margin calibration에 사용하지 않는다. 별도 승인 후 pre-May 데이터를 시간 순으로 training/calibration/untouched validation으로 나누고 현재 방법과 사전 정의한 지표로 비교해야 한다. May-01에서 관측한 수치로 hyperparameter나 q를 결정하지 않는다.

| 후보 | 기대 역할 | 한계/비용 | 필요한 pre-May 자료 |
|---|---|---|---|
| Conditional runtime regression | 요청 GPU·walltime·tier별 point bias 분석 | point만으로 tail coverage 보장 없음 | 제출 feature, start/end, GPU/tier 충분 표본 |
| Quantile runtime prediction | 상단 조건부 runtime 예측 | quantile 선택·calibration 별도 필요 | 독립 시간 validation과 long-job 표본 |
| Conformal upper bound | 보정 split에서 upper residual 관리 | 시간 drift·조건부/GPU coverage 별도 검증 필요 | 분리된 calibration/validation, drift 기록 |
| Survival model | 미완료 job과 censoring 포함 | censoring/event 의미와 runtime/remaining 구분 필요 | 각 cutoff의 at-risk 상태와 종료/검열 시각 |
| Distributionally robust envelope | runtime 불확실성을 사전 scheduling에 반영 | ambiguity set·보수성 및 계산 비용 | pre-May 오차 분포와 사전 결정한 stress 평가 |
| GPU-weighted asymmetric loss | underprediction의 GPU-service 비용 반영 | 평균 point 정확도/큰 job 편향 tradeoff | GPU별 runtime·pre-May 비용 정의 |
| Explicit scheduling reserve | 사전 headroom으로 overlap 위험 완화 | 활용률·서비스 완료와 tradeoff | pre-May feeder/scheduler 공동 validation |

RUNNING requested-minus-elapsed 규칙, PENDING predictor, q, migration penalty, objective hierarchy는 이번 V40I에서 변경하지 않았다. 위 후보의 우월성을 주장하지 않는다.
