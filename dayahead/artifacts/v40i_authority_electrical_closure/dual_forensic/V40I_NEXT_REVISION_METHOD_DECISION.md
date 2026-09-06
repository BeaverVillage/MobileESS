# V40I 다음 revision 의사결정

**권고 연구 방향: HYBRID_PREDICTION_AND_ROBUST_SCHEDULING.** COMPLETED subgroup point misfit를 먼저 조사하고, causal subgroup upper bound와 robust envelope/reserve의 추가 효과를 독립 pre-May 시간 블록에서 비교한다. 구현·fit·q선정·정책 변경은 하지 않았다.

| 후보 | Supporting evidence | Missing authority | Expected benefit | Leakage risk | Complexity | Required pre-May data | May evaluation boundary |
|---|---|---|---|---|---|---|---|
| A Subgroup upper-bound calibration | Pooled q is only67.02 percentile for COMPLETED H100 residual; conditional coverage fails | Independent temporal calibration/test splits; request-family support | Tail coverage matched to causal subgroup | High if May q/coverage guides selection | Medium | Pre-May submission features, end/start, GPU, separate calibration/test | May excluded from fitting/tuning; May01 no longer blind |
| B Point predictor redesign | COMPLETED point error +7,064s, under64.13%; identity visible; multimodal mixtures | Persisted final encoder/tree audit, outcome semantics, conditional/request drift support | Reduce point misfit without using future status | High if May features or model selected for May reversal | Medium/High | Pre-May causal features plus outcomes for labels only; FAILED retained/audited per predeclared target | May01 diagnostic only; use genuinely unseen blocks for confirmation |
| C Robust runtime envelope/reserve | Large positive-residual tail and joint occupancy risk | Predeclared uncertainty set and service/headroom validation | Scheduling protection when runtime uncertainty remains | High if reserve calibrated from May critical slot | High | Pre-May job/feeder joint backtests and untouched stress/test blocks | May not used to size envelope |
| D Hybrid point + conditional bound + reserve | Point misfit, conditional q failure and multiple regimes coexist | All A–C evidence and ablations under one causal protocol | Assess combined forecast/coverage/scheduling tradeoff | High if three components tuned to May outcome | High | Time-separated pre-May train/calibration/validation; locked comparison metrics | Recommended research direction only, no fitted/selected replacement |
| E Retain fixed PF0.95 baseline | Current lineage reproducible; no independent AIDC Q/control authority | Physical PF fidelity remains OPEN; weak Q impact is not proven | Preserve comparability and disclose assumption | Low if PF unchanged | Low | Independent P/Q data needed before any physical accuracy claim | Current frozen baseline retained, not validated by circular PF reconstruction |
| F Exogenous time/load-dependent PF | Possible fidelity question; currently no qualifying measurements | Site/time-aligned independent P/Q or device telemetry and pre-May forecast validation | Represent Q variability without granting control | High if PF chosen to improve May current | Medium | Pre-May signed P/Q with cadence/site/cause; no fixed-PF-derived labels | Future held-out evaluation required; current implementation not authorized |
| G Controllable Q | No qualifying AIDC capability authority found | UPS/STATCOM asset identity, ratedkVA, Qrange, P-Q curve, response/control interval | Only if physically available VAR operation is demonstrated | High if invented capability improves May | High | Equipment contract plus pre-May operating telemetry | NOT AUTHORIZED; MESS/native capacitors not transferable authority |

COMPLETED/FAILED는 retrospective stratification label이다. Production feature로 넣거나 FAILED를 제거한 모델을 이번 단계에서 학습하지 않는다. 기존 q와 diagnostic subgroup q의 차이는 설명값이며 새 q를 선정한 것이 아니다.

Runtime 범위의 historical support는 충분하지만 같은 9-feature 조합은 학습에 0개였다. 같은 8-feature 조합 1,501개는 모두48h 요청으로 May12h 요청과 다르다. 이 문제는 final tree state 없이 FAILED 혼합의 직접 효과로 단정할 수 없다.

Reactive level0 고정 PF는 현재 재현 baseline으로 유지한다. Level1은 독립 time/load-dependent P/Q authority, level2는 추가 장비 P-Q capability/control authority가 필요하다. Q sensitivity가 작다고 입증된 것은 아니며 exact AIDC pure-Q gradient도 없다. 현재 Q control authorization=NO.

May-01은 이미 원인 분석과 연구 질문 형성에 사용했다. 새 revision에 대해 untouched/blind confirmatory test라고 주장하지 않는다. 모든 May label의 fitting/calibration/parameter selection 사용은 금지하고, 이후 확인 실험은 실제로 아직 보지 않은 사전 고정 evaluation을 사용해야 한다.

현재 상태: 31-day electrical regeneration HOLD; B0/B1/B2/B3/AIDC/MESS optimization NO; retraining NO; q/PF/Q-control 변경 NO; full-May execution NO. 이 문서는 실행 승인이 아니다.
