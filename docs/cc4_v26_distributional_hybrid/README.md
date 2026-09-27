# CC4-v2.6 — Distributional / Hybrid Forecast Comparison

[한국어 최종 검토](FINAL_REVIEW_KO.md) · [선택 동결](FINAL_SELECTION_FREEZE.json) · [최종 판정](FINAL_VERDICT.json) · [모델 지표](MODEL_METRICS.csv) · [paired CI](PAIRED_UNCERTAINTY.csv)

PR #73 commit `65b26fb3663b766b1dbd9d258d4fced6c3eaa13a`에서 분기한 독립 offline evidence다. 모델 기준은 PR #64 raw causal-refit LightGBM이며 PR #67/#69/#70/#73 결과를 그대로 보존한다. Target/population/split/feature authority 및 expanding/30-day weighting/daily refit를 변경하지 않는다. May는 exposed diagnostic이고 tuning에 사용하지 않는다.

| arm | 정의 |
|---|---|
| B0 | PR64 raw LightGBM Q50/Q90 |
| B1 | zero-atom lognormal: LightGBM occurrence + positive log-location, TRAIN-only OOS dispersion |
| B2 | B0 + causal distributional burst gate 안에서만 B1 quantiles |
| B3 | B0 + 3-seed DeepAR quantile convex ensemble; 같은 weight로 Q50/Q90 순서 유지 |
| B4 | 기존 compact TFT, 3-seed prediction 평균 |
| B5 | 기존 compact DeepAR, 3-seed prediction 평균 |

B1은 허용된 distributional 대안이며 Tweedie가 아니다. Zero mass를 반영한 analytic unconditional quantile을 사용한다. 계산 가능성과 empirical model support를 구분한다. B2는 gate 밖에 B0를 정확히 유지한다. B3는 quantile 평균이며 mixture distribution의 quantile로 주장하지 않는다. DeepAR의 기존128-path sampling을 변경하지 않고 그 Monte Carlo 한계도 계승한다. 개별 seed 결과는 `SEED_METRICS.csv`에 있다.

## Authority와 audit

`SOURCE_MANIFEST.json`은 부모 evidence 전체 chain의 byte digest를 고정한다. 원 hourly labels, TRAIN burst definition, exact eligible evaluation days는 변경하지 않는다. Raw mass/population reconstruction은 PR73의 raw audit와 원 DATA를 byte 검증하여 계승하며 원 archive를 다시 해석하지 않는다.

학습은 `label_matured_at < issue_time`과 과거 issue의 non-PURGE day만 사용한다. Feature proof는 `feature_available_at <= issue_time`이다. OOS prediction을 생성한 source model이 당시 보지 못한 TRAIN positive labels로만 sigma를 추정하고, 첫 DEV issue 이전에 성숙한 residual만 사용한다. Sigma는 DEV 전에 동결된다. 이후 성숙한 evaluation labels는 고정 daily location/occurrence refit에만 들어갈 수 있고 sigma/gate/weight/hyperparameter tuning에는 사용하지 않는다.

기존 PR64 weight receipt는 full numeric 배열이 아닌 축약 Index 문자열이다. `REUSE_AUDIT.json`은 그 한계를 명시하고, frozen formula로 재구성한 전체 숫자를 `reused_numeric_membership/`에 저장한다. 기존 forecast byte receipt1,911개와 exact date membership을 확인했다. 원 neural checkpoint를 이번 task에서 새로 replay/refit한 것처럼 주장하지 않는다.

`D1_SCHEDULER_REQUEST_STATE_PROXY_V1` 경계의 request/ingestion version provenance는 **UNVERIFIED / UNOBSERVED**다. Historical exactness, request immutability 또는 변경빈도0을 주장하지 않는다. Production/integration readiness는 fail-closed다.

## 재현

기존 evidence는 write-once다. 현재 디렉터리에서 실험 명령을 재실행하지 않는다. `python delivery.py verify`는 읽기 전용 검증이다. 새 sibling 디렉터리에 `study.py`, `distribution.py`, `test_contract.py`, `audit.py`, `delivery.py`, `delivery_tools/`를 복사한다. 부모 PR73/64 namespace를 같은 상대 경로에 제공한다. `ENVIRONMENT.json`의 numpy/pandas/scipy/lightgbm/pyarrow 버전을 사용한다.

```powershell
python -m unittest -v test_contract *> tests.log
python delivery_tools/record_tests.py
python audit.py reuse *> reuse_audit.log
python study.py register
python study.py train_dispersion *> train_dispersion.log
python study.py development *> development.log
python study.py evaluation *> evaluation.log
python audit.py final *> independent_audit.log
python delivery_tools/review_results.py
python delivery_tools/parameter_metadata.py
python delivery_tools/report.py
python delivery.py seal
```

Fresh model reproduction은 부모 repo에 저장된 DATA 및 frozen forecast/fit receipt bundle만 필요하다. External raw archive 또는 GPU는 필요하지 않다. Neural predictions를 검증하여 재사용하기 때문이다. Neural 모델 자체의 재학습 recipe와 원 환경은 PR64 `neural.py`, `experiment.py`, `PROTOCOL.json`, `REPRODUCIBILITY_MANIFEST.json`에 있다. 이 경로와 현재 비교 재현을 구분한다.

새 LightGBM checkpoint는 local `fits/`에 보존하고, Git에는 exact membership/parameters/receipts와 checkpoint digest 및 deterministic recipe를 저장한다. `audit.py final`의 full new-checkpoint replay에는 재생성한 checkpoint가 필요하다. 결과 CSV만 검증하는 `delivery_tools/review_results.py`는 checkpoint 없이 실행 가능하다. `record_tests`/`report`/`seal`은 새 디렉터리에서만 실행한다.

새 디렉터리 이름으로 인한 model 결과 변경은 없지만 timestamp, timing, environment/receipt bytes는 재실행마다 다를 수 있다. Numerical result 및 model digest 재현과 전체 delivery byte 동일성을 구분한다.

선택적으로 matplotlib가 있는 `PLOT_ENVIRONMENT.json` 환경에서 `python delivery_tools/plot.py`를 실행하면 COMPARISON.png/pdf를 만든다. Figure는 모델 학습·선택에 사용하지 않는다.

## 통계와 비용

동일 target-day의24시간을 함께 resample하는 paired1-day/7-day block2,000회 CI다. Nonfinite draw가 있으면 해당 CI를 unavailable로 두며 draw를 제거하지 않는다. CI는 frozen forecast 조건부의 unadjusted per-contrast exploratory 구간이고 refit/selection uncertainty나 multiple-comparison correction을 포함하지 않는다.

계산 비용은 historical source receipt와 이번 새 fit timing을 분리한다. 재사용 모델의 새 학습시간0을 원 모델의 계산 비용0으로 해석하지 않는다. B2/B3는 공유 base cost를 중복 계상하지 않는다. 서로 다른 장비/receipt granularity의 timings를 동일 hardware benchmark라고 주장하지 않는다.

변경 범위는 이 새 docs namespace뿐이다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production 수정·실행 및 coupling/promotion은 없다.
