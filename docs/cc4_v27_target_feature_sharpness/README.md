# CC4-v2.7 — Target / Feature Mapping and Sharpness

독립 branch `codex/cc4-v27-target-feature-sharpness`, PR #74 head `bae7916c759e1c845bb87a8ee0dff761b5db7f7a` lineage.

최종 결과는 [한국어 검토](FINAL_REVIEW_KO.md), [판정](FINAL_VERDICT.json), [검증](VALIDATION.json)에 있다. 결과가 아직 없으면 실험이 진행 중이다. 미생성 파일을 완료로 간주하지 않는다.

## 과학적 경계

* A0: 원시 T0·기존 F0 71개·기존 B0를 정확히 재현한다. baseline 273일을 새로 재학습하며 모든 원시 Q50/Q90이 bitwise equal이어야 진행한다.
* T0/T1은 제출량, T2/T3는 발행 후 미지 작업의 실현 실행 점유량이다. T3의 주 타깃은 평균 활성 GPU이고 GPUh 계산에 0.25를 곱한다.
* F0/F1/F2/F3/F4/F5의 24개 조합을 등록한다. F3는 정확한 과거 상태 스냅샷이 없으므로 F0의 명시적 alias다. 공휴일은 출처가 없어 제외한다.
* LightGBM quantile log1p, 400 trees, 15 leaves, lr .03, min leaf50, seed20260924, 1 thread. 매일 non-PURGE 성숙 과거 일만 expanding refit, 원래 30일 가중치 유지. T3도 같은 설정이다.
* 원시·보정 성능을 분리한다. 평가 Q90 보정량은 평가 전 CAL 성숙 잔차로 고정하며 May를 포함한 평가로 업데이트하지 않는다.
* DEV RAW coverage 88~92% 후보를 우선한 뒤 pinball·calibration error·requirement ratio로 각 타깃의 특징을 선택한다. 밴드 내 후보가 없으면 최소 손실 조합은 연구용 fallback이다. T2/T3 두 연구 후보의 인터페이스를 고정한 다음에만 같은 기준의 Stage2 M0/M1 리드 그룹 비교를 한다. 단일 운영 우승을 강제하지 않는다. 초기 등록에서 빠졌던 band-first 순위 규칙은 새 조합 지표 집계 전에 SELECTION_PROTOCOL_AMENDMENT로 보완했고 원본 코드를 registration_v1에 보존했다.
* OOS_EXTENSION은 원본 eligible=False를 그대로 보존하며 별도 확장 평가로 보고한다. May는 노출된 진단이다.
* 모든 검증은 논리적 event time 수준이다. 요청값 revision/ingestion provenance는 미확인이다. V42·optimizer·전력 모델을 수정하거나 실행하지 않는다.

## 새 위치에서 재현

기존 evidence를 덮어쓰지 않는다. 이 폴더의 `.py`, TARGET_DEFINITIONS.md, README.md, `.gitattributes`, `.gitignore`, USER_REQUEST만 **새 sibling 폴더**에 복사한다. 결과 JSON/CSV/NPZ/Parquet와 FINAL_REVIEW_KO.md는 복사하지 않는다. 상위 디렉터리에 같은 부모 CC4 namespace들을 제공한다. `ENVIRONMENT.json` 버전을 사용한다. 원시 zip의 경로·SHA256은 부모 SOURCE_MANIFEST에 있으며 전체 원시 재구성에 필요하다. 옮길 경우 원본 파일 해시를 확인한 별도 경로 해석을 기록한다.

```powershell
python -X utf8 anchor.py
python -X utf8 prepare.py
python -X utf8 test_contract.py
python -X utf8 eligibility_audit.py
python -X utf8 experiment.py register
python -X utf8 supplement.py
python -X utf8 placement_audit.py
python -X utf8 experiment.py development
python -X utf8 experiment.py freeze
python -X utf8 experiment.py evaluation
python -X utf8 experiment.py development --stage2
python -X utf8 experiment.py freeze --stage2
python -X utf8 experiment.py evaluation --stage2
python -X utf8 report.py
python -X utf8 validate.py
python -X utf8 finish.py
python -X utf8 plot.py
python -X utf8 delivery.py seal
```

`plot.py`만 matplotlib가 있는 별도 환경에서 실행 가능하다. 해당 환경은 모델 학습에 사용하지 않는다. `delivery.py verify`는 읽기 전용이다. 새 fit receipt는 날짜별 예측, 정확한 학습 날짜·가중치, 모델 텍스트 SHA256, feature importance, 실행시간을 저장한다. 전체 booster 텍스트는 저장하지 않으며 frozen code/data의 결정론적 재학습이 모델 재현 경로다. resume은 이미 완료된 fit 파일만 읽고 추가 작업을 수행한다.

`A0_ANCHOR.json`은 모델 재현 직후의 immutable receipt라 raw 타깃 재구성이 pending으로 남아 있다. 최종 `A0_VERIFIED.json`이 후속 원시 재구성 성공을 연결하며 이전 receipt를 덮어쓰지 않는다. `A0_PREDICTIONS.npz`의 수치 배열은 원본과 비트 단위로 같지만 새 zip container·실행시각·소요시간까지 같은 파일 바이트라고 주장하지 않는다. 원본 baseline 파일 자체는 변경 없이 보존한다.

보고 지표의 `actual_integrated_quantity`, `daily_integrated_quantity_MAE` 단위는 T0/T2/T3에서 GPUh, T1에서 requested GPU다. 원시 단위가 다른 타깃끼리 절대 loss를 비교하지 않는다. 타깃별 F0 대비 비율과 TRAIN 평균으로 정규화한 진단을 사용한다. 실험 CSV는 음성 결과·0 target·hard day를 포함한다. Q90 합은 joint daily Q90이 아니다.
