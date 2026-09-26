# CC4-v2.4 — Request-state Burst Forecast

[한국어 최종 검토](FINAL_REVIEW_KO.md), [최종 선택 freeze](FINAL_SELECTION_FREEZE.json), [모델 결과](MODEL_METRICS.csv), [detector 결과](DETECTOR_METRICS.csv), [strata](STRATIFIED_METRICS.csv), [paired uncertainty](PAIRED_UNCERTAINTY.csv), [판정](VERDICT.json)을 함께 확인한다.

PR69 commit `e672e4a81e22e9fdca3316f7e73611b39481faa6`에 추가한 독립 evidence다. May exposure 이후의 offline model development이며 May 및 기존 평가 기간을 untouched confirmation으로 주장하지 않는다.

## 명시적으로 허용된 proxy 경계

원 archive에는 요청 version/effective/observed history가 없다. 사용자는 이 한계를 확인한 뒤 기존 V40S4 **D1_SCHEDULER_REQUEST_STATE_PROXY_V1**를 계승해 실험을 계속하도록 명시했다. Archive의 requested GPU, walltime, partition, QoS를 scheduler-visible이었다고 가정하는 offline proxy로만 사용한다. Historical issue-time 값과의 정확한 일치, request immutability, 변경 빈도 0을 주장하지 않는다. Provenance는 **UNVERIFIED / UNOBSERVED**다. `NLR_scheduler_authority/07_hpc-oda-commons`는 code/model authority이며 historical request-state snapshot 증거로 사용하지 않는다.

원 authority 감사는 [REQUEST_STATE_AUTHORITY_AUDIT.json](REQUEST_STATE_AUTHORITY_AUDIT.json)에 보존하고, 사용자 지시와 계속 실험하는 경계를 [REQUEST_STATE_PROXY_AUTHORIZATION.json](REQUEST_STATE_PROXY_AUTHORIZATION.json)에 별도로 기록한다. Authority audit의 availability 실패를 PASS로 바꾸지 않았다. Production readiness는 이 provenance가 해결되지 않으면 fail-closed다.

## 고정 범위와 후보

C0는 PR64의 raw refitted LightGBM Q50/Q90을 그대로 사용한다. Expanding history, 30-day recency half-life, daily refit, base architecture와 TRAIN positive-hour Q95 burst threshold(860.3532222222221 GPU·h)는 고정이다. Target은 D−1 18:00의 다음날 24개 hourly future GPU-work arrival이며 변경하지 않는다.

새 feature는 request-only raw columns를 읽는다. Actual runtime/start/end는 읽지 않는다. 최근 6/12/24시간 submit count, 요청 GPU와 walltime·GPU×walltime의 moment/bucket, large-GPU/long-walltime count, TRAIN-only partition/QoS composition, intensity·trend·acceleration·168h ratio, 알려진 target hour/weekday별 과거 request intensity를 추가한다. Known CPU zero와 missing/invalid GPU를 구분하고 walltime/product의 missing support도 보존한다. Exact submitted Job membership은 archive member·원본 row index·Job ID·submit timestamp로 재현한다.

- C1: request-state balanced LightGBM detector + 과거 mature OOS high-risk C0 residual correction.
- C2: 같은 detector + request features로 학습한 burst-only conditional magnitude quantile LightGBM. DEV/CAL에서 conditional Q50/Q75/Q90 중 하나를 선택한다.

Detector gate는 두 후보 모두 **0.01 고정**이다. 이전 C2와 같고 이전 C1 0.0025보다 높다. Detector threshold search나 lowering은 하지 않는다. Gate 밖 Q50/Q90과 전체 Q50은 C0와 정확히 같다. C2 bound는 operational Q90 candidate이며 unconditional quantile calibration을 보장하지 않는다. 전체 scaling/capping은 없다.

## Selection과 stop rule

DEV와 CAL 각각에서 다음을 모두 충족해야 challenger를 선택한다: matched-gate PR69 balanced detector보다 AP·precision 각각 +0.01 이상, recall ≥60%, final burst coverage ≥60%, positive coverage ≥85%, requirement ratio <2, Q90 pinball ≤1.02×C0. Inclusive 비교의 부동소수점 tolerance는 1e−12로 사전 명시했고 ratio <2는 strict 비교다. Preferred overall coverage 88–92%와 recall/burst 70%를 우선하고 낮은 reserve·pinball로 비교한다. Feasible 후보가 없으면 C0를 유지하며 최소 normalized-deficit 후보는 연구용으로만 고정한다.

AP는 noninterpolated average precision이다. 최종 superiority는 DEV/CAL 선택과 historical diagnostic의 gate, 7일 block CI의 AP/precision 최소 +0.01·burst 개선·2% pinball noninferiority를 함께 요구한다. 실패하면 hourly burst 추가 개발을 중단하고 cumulative/3h/6h target을 후속 연구 후보로 제안만 한다. 이번 task에서는 target 변경을 구현하지 않는다.

CI는 같은 target-day를 paired로 묶은 1일/7개 관측일 circular block bootstrap 2,000회다. 매 draw에서 ratio·precision·FPR·AP를 다시 계산한다. Frozen forecasts에 조건부이며 refit/selection uncertainty나 multiple-comparison correction은 포함하지 않는다.

## 재현과 검증

완료 evidence는 write-once다. `python delivery.py verify`는 portable byte audit만 실행한다. 새 실험은 별도의 새 sibling 디렉터리에 source/test/delivery 도구만 복사하고 PR63/64/67/69 authority 디렉터리를 같은 상대 경로에 제공한다. 원 archive와 datacard는 authority audit의 path/hash를 따른다. 라이브러리는 `ENVIRONMENT.json`과 일치시킨다. Existing evidence에 다시 쓰지 않는다.

```powershell
python request_features.py --base ../cc4_v2_hourly_future_workload --output .
python request_features.py --base ../cc4_v2_hourly_future_workload --output . --prepare-authorized-proxy
python -m unittest test_contract test_request_features -v
python study.py prepare
python study.py register
python study.py development
python study.py select
python study.py evaluation
python study.py verify
python delivery_tools/independent_audit.py
python delivery_tools/uncertainty_audit.py
python study.py report
```

`DAY_MEMBERSHIP.csv`, `fits/*/TRAIN_MEMBERSHIP.npz`, `C1_CALIBRATION_MEMBERSHIP.json`, `FEATURE_MEMBERSHIP.json` 및 `REQUEST_EVENT_INDEX_MANIFEST.json`에 exact membership을 저장한다. 미래 submit 제거, 실제 outcome 열 변조, missing support, strict label maturity와 모든 saved checkpoint prediction을 검증한다. Model checkpoint는 로컬에 보존하고 Git에는 recipe·membership·prediction·digest를 저장한다. Runtime/optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production의 수정·실행은 없다.

Authority audit 재생성에는 기존 forensic snapshot provenance metadata와 Runtime authority 경로도 필요하다. 기본 경로는 `request_features.py --help`와 audit의 source 목록에 기록되어 있다. 새 위치에서는 `--snapshot-root`/`--runtime-root`를 지정하고 동일 digest를 확인한다. Model-only 재현은 이 evidence의 immutable prepared feature·request bins·event indices·vocabulary·authority/addendum 파일을 새 디렉터리에 복사해 첫 두 raw-preparation 단계를 생략할 수 있다. 이 경우에도 `study.py prepare`와 모든 digest/causal membership 검사는 유지한다.
