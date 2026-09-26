# Runtime-vNext — causal temporal and tail study

PR #27/#30/#31 및 최신 PR #42 production authority를 구분하는 독립적인 offline 연구다. [최종 판정](FINAL_REVIEW_KO.md)과 [전체 모델·strata·효과별 CI 검토](REVIEW_SUPPLEMENT_KO.md)를 먼저 읽고, 원본 값은 `VERDICT.json`, `MODEL_METRICS.csv`, `MATCHED_REFERENCE_METRICS.csv`에서 확인한다.

## 두 기준선

`MOE_BASELINE_REPRODUCTION.json`은 과거 MoE XGBoost를 당시 NumPy 2.4.6, scikit-learn 1.5.2, SciPy 1.17.1, XGBoost 3.2.0 및 Arrow 자료형으로 재학습해 245개 예측을 byte-exact 비교한다. `MODERN_BASELINE_REPRODUCTION.json`은 최신 expanding LightGBM의 May 31일분 frozen 예측을 재현한다. 원래 전체 Job MoE와 positive-GPU LightGBM의 training population 차이는 숨기지 않는다.

`MODERN_REFIT_REPRODUCTION.json`은 2025-05-01 대표 issue에 대한 추가적인 재학습 검증이다. issue 이전 완료 Job 667,375개로 원래 1-thread recipe를 재학습해 전처리, 모든 tree, model text SHA-256 및 Pending 예측 1,395개가 frozen authority와 완전히 일치했다. May outcome을 읽거나 설정을 선택하지 않았다.

새 temporal/architecture arm들은 raw positive-GPU completed history를 공통으로 사용한다. 따라서 temporal 효과는 이 공통 GPU cohort에 한정된다. 과거 전체 Job production의 refit 효과를 입증한 것으로 해석할 수 없다. 동일 architecture 비교에는 입력 9개와 MoE의 학습된 OHE/SVD 표현을 동일하게 사용한다. 최신 production LightGBM의 원래 입력·전처리는 별도 기준선으로 유지한다.

May 31일 모두 raw expanding training membership의 개수·해시가 최신 frozen production과 정확히 일치함을 `PRODUCTION_COHORT_BRIDGE.json`으로 확인했다. 이는 과거 전체 Job MoE와의 차이를 해소하지 않는다. Pending과 Running 비교가 식별하는 효과 및 baseline 교집합의 범위는 평가 전에 작성한 `INTERPRETATION_CONTRACT.md`를 따른다.

## 순서와 membership

- `PROTOCOL.json`, `CODE_FREEZE.json`, `CODE_AMENDMENT_CHAIN.json`: 최초 설계, 보존된 코드, 평가 전 수정 사유·digest.
- `JOB_MEMBERSHIP.parquet`, `ISSUE_MEMBERSHIP.parquet`, `ISSUES.csv`: raw Job 및 issue별 정확한 구성.
- `fits/*/*/train_membership.npz`: `JOB_MEMBERSHIP.parquet.row_id`에 대응하는 정확한 학습 순서.
- `fits/*/*/MEMBERSHIP.json`: strict `end < issue`, window, decay와 source digest.
- `STAGE_A_DEVELOPMENT.csv`, `STAGE_A_FREEZE.json`: 사전에 고정한 세 DEVELOPMENT origin의 temporal 비교.
- `MODEL_SELECTION_METRICS.csv`, `FINAL_SELECTION_FREEZE.json`: chronological DEVELOPMENT/CALIBRATION 비교와 evaluation 전 최종 선택.
- `calibration/`: 이전 issue의 예측만 사용한 residual membership과 hierarchy/backoff 경로. pre-evaluation 자료는 별도 파일로 보존한다.
- `STRATIFIED_METRICS.csv`, `QUANTILE_DIAGNOSTICS.csv`, `PAIRED_UNCERTAINTY.csv`: subgroup·elapsed regime·quantile·통계 불확실성.

Pending은 total, Running은 elapsed를 입력으로 한 remaining runtime이다. remaining training의 elapsed landmark는 Job ID hash로 정하고, 완료 Job 중 그 elapsed까지 살아 있던 Job만 사용한다. censored-aware survival 성능은 주장하지 않는다. request 수정 이력과 historical scheduler snapshot provenance는 미확인이다. 운영 인과성 인증이나 production replacement를 허용하는 근거가 아니다.

## 재현

현재 결과는 write-once stage guard가 있다. 새 실행은 새 디렉터리에 루트 `*.py`와 `authority/`를 복사하고, `common.py`에 명시된 raw archive/HPC-ODA source/기존 frozen authority를 제공한 뒤 시작한다. source digest가 다르면 중단한다. 원본 branch는 sparse checkout으로도 결과만 검토할 수 있다.

```powershell
python reproduce.py modern
$env:RUNTIME_BASELINE_NATIVE_THREADS='1'
python reproduce.py legacy
Remove-Item Env:RUNTIME_BASELINE_NATIVE_THREADS
python prepare.py
python reproduce_modern_refit.py
python -m unittest test_contract test_calibration_hierarchy -v
python experiment.py register
python experiment.py a
python check_thread_equivalence.py
python experiment.py b
python experiment.py evaluate
python report.py
python quantile_diagnostics.py
python point_architecture_diagnostics.py
python verify_reproduction.py
```

최초 MoE 재현은 Arrow `to_pylist()`의 null·정수 자료형까지 유지해야 한다. pandas record 변환 및 다른 수치 라이브러리로 재현이 실패한 시도도 로그로 남겼다. baseline 재현이 통과하지 않으면 registration이 진행되지 않는다.

`parallel_pipeline.py`는 A freeze 후 독립적인 issue fit을 2개 process로 계산한다. 각 issue의 training maturity는 동일하며 선택과 calibration은 순차적으로 처리한다. 중복 writer는 process lock으로 막는다. 현재 실행의 감사 명령은 `python verify.py`이며, 최초 코드와 amendment 원본 bytes도 검증한다.

위 재현 명령의 `verify_reproduction.py`는 현재 코드를 새로 등록하고 수정 없이 실행한 경우를 위한 감사다. 이 배포 실행은 historical amendment가 있으므로 `verify.py`와 `verify_fit_receipts.py`를 사용한다. 활성 패키지 버전과 import 위치는 `ENVIRONMENT_LOCK.txt`, `ENVIRONMENT_INVENTORY.json`에 있으며 HPC 소스는 별도 pinned commit을 사용한다.

`auxiliary_prewarmer.py`는 동일한 locked worker를 한 process 더 실행한다. 총 세 process가 독립적인 issue cache를 준비하며 evaluation issue는 최종 freeze 뒤에만 계산한다. 역순 계산도 각 issue의 학습 cutoff를 바꾸지 않고, 선택과 residual calibration은 본 pipeline에서 chronological 순서로 처리한다.

CC4 계산이 종료된 뒤에는 남은 CPU 용량에 동일 worker 한 개를 더 배정해 최대 네 process를 사용했다. `RESOURCE_SCHEDULING_RECEIPT.json`과 `delivery_tools/frozen_additional_worker.py`에 기록했다. 이 helper는 모든 frozen source의 해시·temporal policy·protocol을 먼저 확인하며, 모델별 4-thread 설정·학습 규칙·선택·calibration 순서는 바꾸지 않는다. 추가 실행은 CPU 사용량에 따른 계산 배치 변경이고 evaluation metric을 사용하지 않았다.

새 LightGBM fit은 4개 CPU thread를 사용한다. 189,426개 causal training 행과 1,202개 target-free query에 대한 사전 검사에서 1-thread와 모든 tree 및 예측이 완전히 같음을 확인했다. 모델 설정 중 계산 thread만 바뀌며 benchmark는 validation loss를 계산하지 않는다. 당시 production baseline은 원래 설정으로 재현했다.

## 저장과 해석

Git에는 recipe, source/membership, 예측, metric, audit, freeze 및 checkpoint digest를 저장한다. 대량 checkpoint binary와 원본에서 다시 만드는 `cache/`는 로컬에 보존하고 Git에서는 제외한다. `MODEL_CHECKPOINT_MANIFEST.csv`와 `REPRODUCIBILITY_MANIFEST.json`으로 정확한 환경과 파일을 확인한다.

배포 전 `verify_fit_receipts.py`로 예측·모델 파일의 digest를 확인하고, `delivery_tools/verify_authority_preservation.py`로 원본 archive·두 production 기준선·pinned HPC source가 그대로인지 검사한다. 모든 worker가 종료되고 보고서가 완성된 뒤 `package_evidence.py`를 한 번 실행해 파일 목록을 봉인한다. checkout만으로 수행하는 portable audit는 `python verify_delivery.py`다. plotting은 `PLOT_ENVIRONMENT.json`에 기록한 별도 환경을 사용하며 ML 환경을 변경하지 않는다. `delivery_tools/write_review_supplement.py`는 이미 계산한 CSV를 표로 표시할 뿐 선택이나 예측을 바꾸지 않는다.

PR31 frozen reference와의 비교는 사전에 정한 Job-issue 교집합이며 unmatched 수를 보고한다. PR31은 Q90만 권위 있는 기준선 출력이다. May Running 기준선은 frozen total-runtime LightGBM을 같은 issue에 적용한 total-minus-elapsed proxy이며 기존 production에서 사용한 remaining 모델이라고 부르지 않는다. GPU-slot 지표는 24시간 runtime occupancy proxy이며 실제 dispatch/optimizer/grid 결과가 아니다.

optimizer, MESS, IEEE123/8500, Actual/OpenDSS 실행·수정, production promotion은 수행하지 않는다.
