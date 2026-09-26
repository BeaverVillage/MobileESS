# CC4-v2.1 — causal refit, hurdle and calibration

PR #63의 target·feature·split·raw population을 보존한 독립적인 offline 연구다. 기존 production과 optimizer/grid 코드에는 변경이 없다. `FINAL_REVIEW_KO.md`, `VERDICT.json`, `SEED_MEAN_METRICS.csv`, `PAIRED_UNCERTAINTY.csv`가 결과의 진입점이다.

모든 candidate의 지표 및 시간 정책·architecture·calibration 효과별 CI는 [정량 검토 보충](REVIEW_SUPPLEMENT_KO.md)에 정리했다. 동일 LightGBM의 causal refit 개선은 지지되지만, 고정 DeepAR 후보의 baseline 우월성·production replacement는 지지되지 않는다.

TFT/DeepAR는 PR63의 compact 연구 구현을 그대로 확장한 비교다. 모델의 구체적인 범위와 seed·sampling 해석은 `NEURAL_MODEL_SCOPE.md`를 따른다.

## 단계와 근거

- `PROTOCOL.json`, `CODE_FREEZE.json`: 최초 설계와 코드.
- `STAGE_A_DEVELOPMENT.csv`, `STAGE_A_FREEZE.json`: 5개 temporal policy와 1/7/28일 cadence의 DEVELOPMENT 비교.
- `STAGE_B_DEVELOPMENT.csv`, `STAGE_B_FREEZE.json`: 고정 temporal policy의 5개 architecture 비교.
- `STAGE_C_SELECTION.csv`, `FINAL_SELECTION_FREEZE.json`: calibration 선택과 평가 전 최종 freeze.
- `*_MEMBERSHIP.csv`, `fits/*/*/MEMBERSHIP.json`: 정확한 날짜별 학습 membership 및 weighting.
- `calibration/*.json`: issue별 과거 residual source, maturity, order rank와 additive correction.
- `STRATIFIED_METRICS.csv`: hour, lead band, zero/positive-body/burst별 지표.
- `PAIRED_UNCERTAINTY.csv`: temporal, architecture, calibration, PR63 baseline 차이의 paired 1일/7일 block bootstrap.

28일 calibration은 CALIBRATION 전체에 충분한 support가 없어 승격할 수 없다. `CALIBRATION_SUPPORT_AMENDMENT.json`은 예측 성능을 보기 전 maturity-only 감사에서 확인한 17/26일 support를 기록한다. 세 창의 DEVELOPMENT warmup 대상은 같은 34일이다. Timestamp 자료형 수정과 병렬 cache lock 추가도 원본 코드 및 사유를 보존했다. 모델·feature·target·하이퍼파라미터는 evaluation 결과로 변경하지 않았다.

## 재현

원본 `docs/cc4_v2_hourly_future_workload/`는 PR #63의 그대로인 parent authority이다. Python 3.11 및 `REPRODUCIBILITY_MANIFEST.json`의 패키지를 사용한다. 모델 코드에 Windows process lock을 사용하므로 등록된 Windows 환경이 기준이다.

기존 결과 디렉터리에서 `register`나 완료 단계를 다시 실행하면 중단한다. 재실험은 같은 `docs/` 아래 새 디렉터리에 루트의 `*.py`를 복사한 뒤 그 디렉터리에서 실행한다. parent PR63 데이터의 경로는 그대로 유지한다.

```powershell
python -m unittest test_contract -v
python experiment.py register
python experiment.py a
python experiment.py b
python experiment.py c
python experiment.py evaluate
python report.py
python verify_reproduction.py
```

`parallel_phases.py`는 B freeze 뒤 독립적인 모델 cache를 최대 4개 CPU process로 준비한다. neural training은 전역 lock으로 GPU 한 작업만 사용한다. 학습·선택·calibration 수식은 순차 실행과 같다. `reuse_components.py`는 같은 training membership·seed를 가진 hurdle/burst의 동일 구성요소만 해시를 남겨 재사용한다.

현재 실행의 감사에는 `python verify.py`를 사용한다. 이 명령은 보존된 최초 코드와 사전 평가 amendment 체인까지 확인한다. 새 directory에서 새로 등록한 실행에는 현재 실행의 amendment 자료를 덮어 복사하지 않는다.

위 재현 명령의 `verify_reproduction.py`는 수정 없이 새로 등록한 실행을 위한 감사다. 현재 배포 실행은 historical amendment가 있으므로 `verify.py`와 `verify_fit_receipts.py`로 감사한다. 두 검증 경로를 서로 대체하거나 amendment 이력을 삭제하지 않는다. 환경의 활성 패키지 버전은 `ENVIRONMENT_LOCK.txt`, 전체 import 위치는 `ENVIRONMENT_INVENTORY.json`에 있다.

## 저장 범위

Git에는 코드, protocol/freeze, membership, 예측, 지표, 감사, 환경, checkpoint digest를 저장한다. 수많은 daily-refit checkpoint의 중복 binary는 로컬 `fits/`에 보존하며 Git에서는 제외한다. `MODEL_CHECKPOINT_MANIFEST.csv`가 파일별 SHA-256·크기를 기록한다. checkpoint는 등록된 코드·입력·membership으로 다시 만들 수 있다. 원본 evidence와 local checkpoint를 삭제하거나 덮어쓰지 않았다.

수천 개 fit의 정확한 membership·receipt·예측은 `FIT_AUDIT_BUNDLE.tar.gz`에 원래 `fits/` 경로로 묶었으며, 모든 member digest는 `FIT_AUDIT_BUNDLE_MEMBERS.json`에 있다. Git checkout만으로는 `python verify_delivery.py`로 배포 파일과 bundle을 읽기 전용 검증할 수 있다. 전체 `verify.py` 감사에는 로컬 checkpoint 또는 재학습한 checkpoint가 필요하다.

이는 exposed historical study이다. 실제 ingestion latency 또는 운영 입력 계약을 인증하지 않으며, production 승격과 optimizer integration은 이 작업에 포함되지 않는다.
