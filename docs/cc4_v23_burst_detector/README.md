# CC4-v2.3 — causal high-recall burst detector

[한국어 최종 검토](FINAL_REVIEW_KO.md), [선택 freeze](FINAL_SELECTION_FREEZE.json), [모델 비교](MODEL_METRICS.csv), [detector 비교](DETECTOR_METRICS.csv), [strata](STRATIFIED_METRICS.csv), [paired CI](PAIRED_UNCERTAINTY.csv)를 함께 확인한다.

PR67 commit `73c719186fdc460ca172632112ae595848bd36da` 위에 추가한 독립 evidence다. **May exposure 이후의 model-development 실험**이며 May와 기존 Dec–Feb는 diagnostic historical evaluation이다. 새로운 untouched confirmation이 아니다. 변경은 이 디렉터리에만 있다.

## 고정한 범위와 비교

- Target: D−1 18:00에 아직 submit되지 않은 다음날 각 시간의 future GPU-work arrival [GPU·h]. Runtime 및 이미 알려진 backlog와 섞지 않는다.
- C0: PR64 raw refitted LightGBM 예측을 그대로 재사용한다. Expanding history, 30일 recency half-life, daily refit과 base LightGBM은 바꾸지 않는다.
- Burst: 기존 TRAIN positive-hour Q95인 860.3532222222221 GPU·h 초과. Threshold 재추정은 없다.
- D0: PR67의 기존 71-feature detector, gate 0.10을 비교 기준으로만 사용한다.
- D1/D2: 같은 고정 LightGBM classifier recipe에 causal training class-balance weight를 적용한다. D1은 기존 71개 feature, D2는 92개 burst feature를 추가한 163개 feature다. Training weight에서 산출한 class prior로 odds를 되돌린 확률 추정값이며 calibration 보장은 아니다.
- C1: 새 detector gate 안에서 과거 mature OOS high-risk C0 residual의 expanding finite-rank Q90 보정을 적용한다. 50시간·10일 미만이면 보정은 0이다.
- C2: PR67의 고정 conditional-tail checkpoint를 그대로 사용한다. 새 detector gate 안에서 conditional Q50/Q75/Q90 중 DEV/CAL에서 선택한 값을 적용한다. **Operational Q90 후보이며 unconditional quantile의 수학적 보장을 주장하지 않는다.**

Q50과 gate 밖 Q90은 C0와 정확히 같다. 전체 scaling/capping은 없다. C2의 tail magnitude 학습/architecture를 새로 탐색하지 않는다. 기존 burst expert의 전체 5-quantile grid를 같은 규칙으로 monotonic repair한 뒤 필요한 열을 사용하며 기존 PR67 tail 예측도 bit-exact replay한다.

새 feature는 최근 6/12/24시간 workload 통계·max·variance·burst 횟수·last-burst age·arrival/workload acceleration·recent/long-term ratio·hour/weekday burst frequency다. 원본 `past`는 336개 **30분 bin**이다. Workload는 strict maturity mask와 positive maturity age를 만족하는 bin만 사용한다. Hour burst 집계는 두 bin 모두 mature일 때만 사용한다. Arrival count는 all-job submit count이며 GPU-only count라고 해석하지 않는다. Missing support와 zero-denominator flag를 별도로 저장한다.

## Selection과 불확실성

Classifier 설정, feature ablation, gate grid, C2 quantile grid와 2% pinball noninferiority margin을 개발 결과 확인 전에 등록했다. DEV와 CAL 각각에서 recall ≥60%, final burst coverage ≥60%, positive coverage ≥85%, ratio <2, pinball ≤1.02×C0를 모두 만족해야 challenger 선택이 가능하다. Preferred overall 88–92%, recall/burst 70%를 먼저 보고 reserve·precision·FPR·PR-AUC·pinball로 비교한다. 통과 후보가 없으면 C0를 유지하고, 각 family의 최소 normalized-deficit 후보는 연구용으로만 freeze한다. May 결과로 재선택하지 않는다.

`SELECTION_METRICS.csv`는 모든 DEV/CAL 후보를 저장한다. `DETECTOR_METRICS.csv`의 evaluation threshold별 결과는 진단용이며 선택에 사용하지 않았다. PR-AUC는 stepwise average precision (`sklearn.average_precision_score`)이다. Paired CI는 1일 및 7개 **관측 target-day** circular block을 2,000회 resampling한다. Ratio, precision, FPR, average precision을 각 draw에서 재계산한다. CI는 frozen forecast에 조건부이며 refit/selection uncertainty를 포함하지 않는다.

과거 evaluation label은 issue 이전에 성숙하면 고정 prequential feature/refit/residual 규칙에만 들어간다. Threshold/feature/parameter tuning에는 사용하지 않는다. 실제 ingestion latency와 request-version provenance는 미인증이다. Finite-rank residual 보정이 시간 의존 데이터에 distribution-free coverage를 보장한다고 주장하지 않는다.

## Exact membership와 감사

- `DAY_MEMBERSHIP.csv`, `fits/*/TRAIN_MEMBERSHIP.npz`: exact day IDs, 온전한 numeric recency weights, burst training row IDs.
- `FEATURE_MEMBERSHIP.json`, `FEATURE_AVAILABILITY_AUDIT.json`: issue별 최근 bin/hour IDs, mature history day IDs, feature availability. 모든 443개 issue의 미래/미성숙 값 변경 counterfactual invariance test를 포함한다.
- `C1_CALIBRATION_MEMBERSHIP.json`: 당시 예측된 high-risk residual pool의 exact day/hour IDs와 support/delta.
- `CODE_FREEZE.json`, `PROTOCOL.json`, `FINAL_SELECTION_FREEZE.json`: 코드·규칙·선택의 순서와 digest.
- `VALIDATION.json`, `INDEPENDENT_AUDIT.json`: base/parent 보존, strict maturity, gate 밖 동일성, checkpoint probability replay와 별도 계산 검증.

## 재현

완료 evidence는 write-once다. Portable byte audit만 할 때는 `python delivery.py verify`를 실행한다. 새 실험은 별도 새 디렉터리에서 실행하며 완료 evidence에 `register`/`select`/`evaluation`을 덮어쓰지 않는다. `study.py`, `causal_features.py`, 두 test 파일과 delivery 도구를 새 디렉터리에 복사하고 PR63/64/67 sibling authority를 같은 상대 경로에 제공한다. `ENVIRONMENT.json`의 Python/library 버전을 사용한다.

PR67 tail 모델은 Git에 대량 binary를 넣지 않았으므로 `MODEL_CHECKPOINT_MANIFEST.json`에 일치하는 원본 local PR67 checkpoint를 `CC4_V23_TAIL_CHECKPOINTS`로 지정한다. 없다면 PR67의 고정 recipe를 별도 scratch evidence 디렉터리에서 재현하고 checkpoint hash가 원본 manifest와 일치하는지 확인한다. 원본 PR67 evidence는 수정하지 않는다. Checkpoint 누락/hash 불일치는 fail-closed다.

```powershell
$env:CC4_V23_TAIL_CHECKPOINTS = 'PATH_TO_PR67_EVIDENCE_WITH_CHECKPOINTS'
python -m unittest test_contract test_features -v
python study.py prepare
python study.py register
python study.py development
python study.py select
python study.py evaluation
python delivery_tools/verify_frozen.py
python delivery_tools/independent_audit.py
python study.py report
```

Delivery-only 도구는 freeze된 model 코드와 분리되어 있으며 scientific decisions를 바꾸지 않는다. Local detector checkpoint 546개는 exact recipe/membership/digest와 함께 로컬에 보존하고 Git에는 membership·예측·digest를 저장한다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS 및 production은 수정·실행하지 않았고 integration/promotion을 수행하지 않는다.

Frozen `study.py verify`의 calibration 비교에는 Timestamp 객체와 JSON `default=str` 문자열의 표현 차이가 있다. `delivery_tools/verify_frozen.py`는 다른 모든 membership 값이 이미 같음을 확인하고 Timestamp만 기존 writer와 동일하게 문자열로 정규화한 뒤 원래 verifier의 모든 검사를 실행한다. 원본 코드, 예측, membership, 선택은 수정하지 않았다. `VERIFIER_SERIALIZATION_AUDIT.json`에 원래 오류와 273개 표현 차이 및 수정 범위를 보존했다. 별도 독립 replay도 모든 예측과 exact pool을 확인한다.
