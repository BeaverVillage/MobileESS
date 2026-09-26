# CC4-v2.2 — fixed LightGBM burst-tail follow-up

[한국어 최종 검토](FINAL_REVIEW_KO.md), [선택 freeze](FINAL_SELECTION_FREEZE.json), [모델 비교](MODEL_METRICS.csv), [gate 판정](GATES.csv), [paired CI](PAIRED_UNCERTAINTY.csv)를 함께 확인한다.

PR64 commit `99a1d9d87eb1b6dd76ce41b734af8104099f992f` 위에 추가한 독립 evidence다. **May exposure 이후의 model-development 실험**이며 May와 기존 Dec–Feb는 diagnostic historical evaluation이다. 새로운 untouched confirmation이 아니다.

## 고정한 범위

- Temporal: expanding history, 30일 recency half-life, daily refit. 학습 membership·weight 수식과 LightGBM 파라미터는 PR64와 동일하다.
- C0: PR64 `LGBM_weighted_c1_s20260924`의 raw refitted Q50/Q90 예측을 그대로 사용한다.
- Burst magnitude threshold: TRAIN eligible positive-hour Q95, 860.3532222222221 GPU·h.
- Risk gate: causal LightGBM이 예측한 unconditional burst 확률 ≥0.10. Q90의 tail-mass 경계로 사전 지정했으며 gate level 검색은 하지 않는다.
- C1: 당시 high-risk로 예측했던 과거 시간들의 C0 residual을 사용한 expanding finite-rank Q90 보정. 50시간·10일 support 미만이면 C0로 돌아간다. 현재 실제 burst 여부로 gate하지 않는다.
- C2: 동일 LightGBM recipe의 burst-only expert. 고정 conditional quantile grid를 이용해 `u = 1 - 0.10/p`에서 tail quantile을 계산한다. 50 burst-hour·10일 미만이면 C0로 돌아간다.

두 보정 모두 high-risk 밖에서는 C0와 byte-exact 수치 일치를 유지하며 Q50은 바꾸지 않는다. 전체 scaling, upper capping, 새 feature, family/architecture 검색은 없다. `NEW_ARCHITECTURE_SEARCHED = FALSE`는 광범위한 family/architecture search를 재개하지 않았다는 뜻이며, 요청된 두 고정 burst component 자체는 비교했다.

DEV와 CAL 각각 positive coverage ≥85%, burst coverage ≥60%, pinball ≤C0인 challenger만 선택 가능하다. preferred overall/ratio 조건, burst coverage, pinball 순으로 정렬하며 통과 후보가 없으면 C0를 유지한다. 최종 선택 후 평가를 계산하고 재선택하지 않는다.

## 재현

완료 evidence는 write-once다. 새 checkout의 별도 새 evidence 디렉터리에서 `study.py`, `test_contract.py`, delivery 도구를 사용하고, sibling PR63/PR64 authority를 동일 경로에 제공한다. NumPy/pandas/LightGBM 버전은 `ENVIRONMENT.json`을 따른다. 원본 authority hash가 다르면 중단한다.

```powershell
python -m unittest test_contract -v
python study.py register
python study.py development
python study.py select
python study.py evaluation
python delivery_tools/audit.py
python study.py report
python delivery.py seal
python delivery.py verify
```

이 배포의 verifier amendment는 `AUDIT_AMENDMENT.json` 및 `audit_sources/study_before_weight_validation.py`에 보존했다. 새 실행의 코드 등록에는 현재 verifier가 그대로 포함되어 별도 amendment가 필요 없다. 기존 study의 registered code, DEV fit 91개, 모든 예측은 보존했다.

PR64 및 초기 v2.2 receipt의 weight는 pandas Index의 축약 문자열로 저장되었다. 실제 training에는 온전한 numeric vector가 전달됐다. 문자열을 역파싱하지 않으며, 독립 auditor가 frozen source·exact day membership·issue로 전체 numeric vector를 결정론적으로 재구성해 NPZ와 hash로 저장한다. 이 NPZ를 당시 기록된 원본 numeric receipt라고 주장하지 않는다.

## 감사·해석

`DAY_MEMBERSHIP.csv`, 일별 `fits/*/MEMBERSHIP.json`, `CALIBRATION_MEMBERSHIP.json`, 재구성된 numeric weights, 원본 PR64 audit bundle로 causal membership을 재현한다. 보조 audit는 risk의 finite/[0,1] 조건, tail prediction, 독립적인 calibration pool/출력 재구성, inherited source digest, 최종 prediction digest까지 검사한다.

Finite-rank residual은 서로 의존하는 시간별 residual에 대해 distribution-free coverage를 보장하지 않는다. CI는 이미 fit된 예측을 대상으로 1일 및 7개 **관측 target-day** circular block을 paired resampling한 조건부 불확실성이다. refit/모델 선택 자체의 불확실성이나 7일을 넘는 dependence 전체를 보장하지 않는다.

실제 ingestion 및 request-version provenance는 미인증이다. training/refit/residual은 strict maturity를 따르며 과거 evaluation label도 해당 issue 이전에 성숙한 경우에만 고정 prequential 규칙에 들어간다. selection/tuning에는 들어가지 않는다.

대량 model binary는 로컬 `fits/`에 보존하고 Git에는 exact recipe, membership, 예측, model digest를 저장한다. 기존 frozen evidence는 overwrite하지 않는다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS를 수정·실행하지 않으며 promotion/integration을 수행하지 않는다.
