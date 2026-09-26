# CC4-v2.5 — Target-resolution comparison

[한국어 최종 검토](FINAL_REVIEW_KO.md), [선택 freeze](FINAL_SELECTION_FREEZE.json), [최종 판정](FINAL_VERDICT.json), [모델 결과](MODEL_METRICS.csv), [horizon](HORIZON_METRICS.csv), [strata](STRATIFIED_METRICS.csv), [paired CI](PAIRED_UNCERTAINTY.csv).

PR70 commit `74e190bf38f75a8c091d514ba7686d6c4684bc87`의 frozen evidence를 보존한 독립 후속 실험이다. Hourly detector 개발을 재개하지 않는다. Base71 feature family, expanding/30-day weighting/daily refit 및 raw LightGBM architecture/hyperparameter는 고정이다. May는 exposed historical diagnostic이며 tuning/untouched confirmation으로 사용하지 않는다.

## Targets와 비교

H1은 기존1시간, H3/H6는 자정부터 비중복3/6시간 block, CUM은 다음날1..24시간 prefix다. 같은 full-lifetime arrival GPUh labels를 사용한다. 각 resolution의 DIRECT Q50/Q90과 frozen H1의 Q50/Q90을 단순 합산한 baseline을 비교한다. H1 DIRECT는 authoritative frozen prediction 자체다. 합산 Q90을 aggregate의 참 Q90이라고 가정하지 않는다.

71 feature는 해당 block/prefix 마지막 hourly anchor의 값을 그대로 사용한다. 시간/calendar/lag/maturity feature를 pooling하지 않는다. 실제 target span은 metadata이며 legacy horizon_hours=1은 원 hourly anchor의 값으로 보존한다. 모든 resolution의 day-level label maturity, training membership, numeric day weights가 동일하다. CUM은 raw marginal prefix curve로 유지하고 monotonicity 위반을 별도 보고하며, 평가 후 projection하지 않는다.

Normalized pinball은 target duration으로 나눈 시간당 pinball을 하나의 고정된 TRAIN hourly mean GPUh로 나눈다. H1/H3/H6의 ratio는 비중복 target 합 기준이며 CUM의 primary reserve ratio는 terminal24h만 사용한다. CUM prefix의 합을 daily mass/reserve로 계산하지 않는다. High-load threshold는 각 resolution의 positive TRAIN Q95이며 CUM은 prefix별 TRAIN Q95다.

DEV/CAL 각각 ratio<2, high-load coverage≥H1+5pp, normalizedQ90pinball≤H1을 요구한다. Overall88–92%는 선호 기준이다. 각 family의 DIRECT/AGGREGATED_H1 method와 primary resolution을 평가 전에 동결한다. Dec–Feb·May 각각 point gate와 paired7-day directional CI를 만족한 사전 eligible family만 탐색적 target-resolution 근거로 인정한다. 평가 후 ranking/selection은 바꾸지 않는다. Direct-vs-summedH1의 같은-target 학습 효과와 target 자체의 집계 효과는 별도 contrasts다.

## Raw authority와 proxy 한계

29개 raw partition을 다시 읽어 SHA-pinned population과 모든443×24 hourly labels를 확인했다. Exact raw target Job717,901개 membership, maturity, H3/H6 합 및 CUM terminal/first difference mass conservation을 저장했다. 원시 completion은 label 재구성에만 사용하고 feature 또는 미성숙 학습 label로 넣지 않는다.

원 authority의 request/ingestion version history는 **UNVERIFIED / UNOBSERVED**다. 기존 V40S4 `D1_SCHEDULER_REQUEST_STATE_PROXY_V1` 경계를 계승하며 historical exactness·immutability·zero-change를 주장하지 않는다. Target 단위를 바꾼다고 provenance가 인증되지 않는다. Production replacement/integration readiness는 fail-closed이며 optimizer coupling을 구현하지 않는다.

## 재현

현재 evidence는 write-once다. 기존 디렉터리에서 단계들을 다시 실행하지 않는다. `python delivery.py verify`만 portable byte audit으로 실행할 수 있다. 새 sibling 디렉터리에 source/test/delivery scripts를 복사하고 PR70에 포함된 `cc4_v2_hourly_future_workload`, `cc4_v21_causal_refit_hurdle`, `cc4_v22_burst_tail`, `cc4_v23_burst_detector`, `cc4_v24_request_state_burst` authority를 같은 상대 경로에 제공한다. 환경은 `ENVIRONMENT.json`에 기록된 버전을 사용한다.

Raw preparation은 PR63 `SOURCE_MANIFEST.json`의 exact raw archive와 pinned `raw_work.parquet`를 read-only로 사용한다. 경로와 SHA가 기록되어 있으며 없거나 다르면 중단한다. 미래 completion을 관측 feature로 사용하지 않는다.

```powershell
python prepare_targets.py *> target_preparation.log
python delivery_tools/finalize_preparation.py
python delivery_tools/run_tests.py
python study.py register
python study.py development *> development.log
python study.py select
python study.py evaluation *> evaluation.log
python study.py verify
python delivery_tools/independent_audit.py
python delivery_tools/uncertainty_audit.py
python delivery_tools/report.py
```

Raw source를 사용할 수 없는 model-only 재현에서는 prepared13 artifacts와 `PREPARATION_RECEIPT.json`을 그대로 복사한 뒤 `run_tests`부터 시작한다. Registration은 prepared labels/features/spans/thresholds를 원 authority와 비교하고, 이후 모든 model stage의 guard가 receipt artifact byte digest를 다시 검증한다. 새로운 timestamp가 포함된 receipt bytes까지 원 실행과 같다고 주장하지 않는다.

Checkpoint는 local에 보존하고 Git에는 exact membership/recipe/seed/prediction/digest를 제공한다. 재현 시 원 checkpoint 없이 동일 source/config/membership으로 재학습할 수 있다. 독립 verifier의 full checkpoint replay에는 재생성한 model files가 필요하다. Paired day/block CI는 frozen forecasts에 조건부이며 refit/selection uncertainty와 multiple-comparison correction을 포함하지 않는다.

변경 범위는 이 새 evidence 디렉터리뿐이다. 기존 PR70 및 optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production을 수정·실행하지 않는다.
