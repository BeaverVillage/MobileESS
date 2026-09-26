# CC4 대체 모델 offline 비교 — 최종 검토

**판정: NO_REPLACEMENT_SUPPORTED / NO_UNTOUCHED_CONFIRMATION.** 사전 규칙에 따라 TFT 기반·DeepAR 기반 후보를 실제 학습하고 비교를 완료했다. 90% coverage만 달성했다는 이유로 모델 개선을 선언하지 않았다. 후속 optimizer 통합을 권할 충분한 근거는 없고 production 자동 교체도 하지 않았다.

실험 namespace: `CC4_REPLACEMENT_ML_OFFLINE_20260924_180000`. 지정한 GitHub commit 4개와 PR #42/#33/#34를 확인하고, 모델 hash→H4_AUTHORITY→May frozen ML_SNAPSHOT을 연결했다. 기존 R6/R6R1의 NONE/FAIL/NO_MODEL_PROMOTED 판정은 변경하지 않았다. 모델·특징·31일 snapshot 보호 hash 재검사는 통과했다.

## 1. 기존 CC4는 무엇을 언제 학습했는가

R6 L0 H4 LightGBM Q50/Q90, 71개 고정 순서 특징, log1p(target_GPUh), leaves=15/lr=.03/400 trees/min_child=50, seed=20260907이다. TRAIN 날짜 범위는 2024-03-15~08-30이나 실제 성숙 적격일은 167일(끝 적격일 08-28), H4 학습 row는 13,527개다. development 58일, calibration 26일, exposed 88일을 원본 maturity ledger/receipt와 확인했다. R6 CAL_FIT/CAL_SELECT와 R6R1 rolling calibration은 같은 방식으로 합치지 않았다.

예측 대상은 submit window에 새로 들어온 작업의 **전체 lifetime GPU·h**이다. GPU 점유량·전력부하·실제 여유용량·window 내 완료량과 다르다. D−1 18:00 고정 AEST(UTC+10), 다음날까지 6시간 gap, 15분 stride, 하루 안의 H4 81개 window를 유지했다. GPU 결측값을 0 또는 nodes×4로 채우지 않았고 synthetic 12개 AIDC를 시계열 12개로 복제하지 않았다.

전체 raw partition 10,559,977개 고유 작업을 검사했다. 원본 349일 15분 target과 H1/H4/H8 특징을 재현했다. May 31일의 71개 특징, frozen base Q90, 85% 보정값과 cap은 수치적으로 일치했으며 calibration membership SHA도 모두 일치한다. 개별 수치와 모델 SHA는 OLD_MODEL_REPRODUCTION_REPORT_KO.md 및 SOURCE_AND_MODEL_LINEAGE.json에 있다.

## 2. 이전 신경망 실패와 이번 변경

과거 R3 TFT/DeepAR/CMABF의 best epoch=1 기록을 확인했다. 학습 손실은 줄고 양수 Q90 development 지표는 악화됐다. 전체표본/composite/NLL 학습 목적과 양수-only early stopping 목적의 차이, zero-heavy 분포, 시간 이동이 원인 후보다. gradient 상세 기록이 없으므로 특정 구현 오류 또는 gradient 이상을 단정하지 않는다. 과거 N-HiTS best epoch는 22였으며 모두 동일한 실패로 묶지 않았다.

이번은 R3 30분 모델의 단순 반복이 아니다. H4 합계 target을 직접 예측한다. TFT 기반 소형 구현은 변수선택·gated residual·LSTM·causal attention, hidden=16, log1p 출력, 전체표본 원단위 Q50/Q90 pinball을 사용한다. DeepAR 기반 소형 구현은 autoregressive LSTM, 0 질량을 분리한 hurdle lognormal, 128개 경로표본을 사용한다. 두 모델 모두 같은 인과적 정보원의 336×8 과거 sequence 및 71개 window 특징을 쓴다. LightGBM은 요약 특징을 쓰므로 **구조와 입력 표현을 포함한 모델 계열 비교**이며 완전히 동일한 tensor 입력 ablation은 아니다.

learning rate .001/.0003 두 설정만 development에서 비교했다. 선택 설정의 고정 seed 20260924/25/26을 모두 평가했다. TFT 선택 epoch는 [6, 5, 5], DeepAR는 [11, 11, 14]이다. epoch 수를 무조건 늘리는 방식으로 선택하지 않았다. 이번에도 DeepAR의 likelihood 학습과 Q90 조기종료 목적 차이는 남아 있다.

development에서 후속 계열은 DEEPAR, learning rate=0.001, fixed epoch=11로 결정했다. calibrated development selection은 최초 20개 성숙 OOS residual day를 warmup으로 제외한 공통 34일을 사용했다. MODEL_METRICS의 development 진단은 58일 전체라 선택 score와 범위가 다르다. 모델/설정 선택에 사용된 development 지표는 독립 확인 성능이 아니다. refit 간격은 28/56일만 비교하여 두 계열 평균 development 손실로 28일을 선택했다. May 결과를 본 뒤 TFT로 재선정하지 않았다.

## 3. 동일 H4·90% 기준 결과

아래는 **seed별 지표의 산술평균**이며 평균 quantile ensemble 결과가 아니다. F0만 기존 85% 역사 reference다. 모든 새 모델의 공통 보정은 fully mature chronological OOS log1p residual의 90% one-sided finite-sample order statistic 하나로 고정했다. TRAIN fitted residual은 쓰지 않았다. raw→calibrated uncapped→historical/physical cap 이후 actionable을 별도로 저장했다.

### 이미 노출된 Dec–Feb: 88일 × 81 = 7,128 windows

| model | training_mode | raw_Q90_pinball | calibrated_Q90_pinball | calibrated_coverage | burst_coverage | mean_forecast_requirement | actionable_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F0_FROZEN | fixed | 710.58 | 628.05 | 0.87233 | 0.062038 | 2183 | 0.86714 |
| F1_LGBM | expanding | 673.07 | 671.66 | 0.92074 | 0.45938 | 4334 | 0.87977 |
| F1_LGBM | fixed | 710.58 | 614.07 | 0.91512 | 0.24225 | 3323 | 0.8938 |
| F2_TFT | fixed | 639.44 | 632.05 | 0.89801 | 0.13097 | 2825.5 | 0.8873 |
| F3_DEEPAR | expanding | 657.36 | 656.65 | 0.90727 | 0.31462 | 3854.8 | 0.87912 |
| F3_DEEPAR | fixed | 683.69 | 682.29 | 0.90119 | 0.3225 | 3703.6 | 0.87238 |
| SEASONAL | fixed | 695.63 | 645.28 | 0.89436 | 0.21861 | 2958 | 0.87556 |
| TRIVIAL_CAP | fixed | 667.7 | 667.7 | 0.90769 | 0.028065 | 3120 | 0.90769 |
| TRIVIAL_TRAIN_MAX | fixed | 2114 | 2114 | 0.99747 | 0.97341 | 22432 | 0.90769 |

### 이미 노출된 May: 31일 × 81 = 2,511 windows

| model | training_mode | raw_Q90_pinball | calibrated_Q90_pinball | calibrated_coverage | burst_coverage | mean_forecast_requirement | actionable_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F0_FROZEN | fixed | 1283.6 | 1058.9 | 0.82995 | 0.12256 | 2312 | 0.81442 |
| F1_LGBM | expanding | 989.3 | 1024.9 | 0.96296 | 0.74373 | 6785.2 | 0.85902 |
| F1_LGBM | fixed | 1283.6 | 1016.2 | 0.87575 | 0.27298 | 3267.8 | 0.83911 |
| F2_TFT | fixed | 1033.6 | 1000.5 | 0.90031 | 0.35005 | 3911.7 | 0.85265 |
| F3_DEEPAR | expanding | 1062 | 1104.3 | 0.91132 | 0.55617 | 5763.1 | 0.83393 |
| F3_DEEPAR | fixed | 1073 | 1105.6 | 0.92221 | 0.54318 | 6052.2 | 0.84694 |
| SEASONAL | fixed | 1181.8 | 1050.5 | 0.8861 | 0.38719 | 3787.4 | 0.83274 |
| TRIVIAL_CAP | fixed | 1069.5 | 1056.7 | 0.87694 | 0.13928 | 3593.8 | 0.85942 |
| TRIVIAL_TRAIN_MAX | fixed | 2285.2 | 2285.2 | 0.98765 | 0.91365 | 22432 | 0.85942 |

단위는 coverage를 제외하고 GPU·h이며 Q90 loss는 원단위 pinball이다. Q50 MAE/WAPE, 양수·zero 수, 양수 coverage, burst miss 및 under/over 평균·P90, seed별 결과는 MODEL_METRICS.csv에 있다. `raw_Q90_pinball`은 원본 interface와 같은 nonnegative/crossing repair 이후 raw forecast이며, repair 이전 수치는 `unrepaired_raw_Q90_pinball` 및 prediction의 `raw_q90_unrepaired`로 따로 보존했다. log-space score도 별도 열이다.

F1과 F0는 같은 base predictor다. May F0 85%→F1 90% 변경으로 coverage가 82.995%→87.575%, 요구량이 2,312→3,268 GPU·h가 된다. 이는 calibration 효과이며 신경망 구조의 이득이 아니다.

fixed DeepAR는 May raw pinball이 F1보다 낮지만, 동일 90% 보정 후 pinball은 **8.80% 높고**, 평균 요구량은 **85.21% 크다**. burst coverage 상승만으로 이 모델이 더 효율적이라고 할 수 없다. Dec–Feb의 보정 pinball도 **11.11% 높다**. TFT는 May 보정 pinball이 **1.55% 낮고**, coverage가 약 **90.03%**이나 요구량은 **19.70% 크다**. Dec–Feb에서는 보정 pinball이 **2.93% 높다**. May에서 관측된 TFT의 작은 이득만으로 사전 development 선택을 뒤집지 않는다.

### Paired day-block 불확실성

7일 circular moving block, 1,000회, 날짜별 seed 평균 차이를 resample했다. 겹치는 2,511개 window를 독립표본으로 처리하지 않았다. 차이는 후보−동일 갱신규칙 LightGBM이며 loss 차이는 음수가 유리하다.

| model | mode | role | difference_to_LGBM | CI95_low | CI95_high | N_paired_days |
| --- | --- | --- | --- | --- | --- | --- |
| F2_TFT | fixed | EXPOSED_EVALUATION | 17.987 | -15.626 | 54.303 | 88 |
| F2_TFT | fixed | MAY_HISTORICAL | -15.727 | -69.164 | 29.841 | 31 |
| F3_DEEPAR | expanding | EXPOSED_EVALUATION | -15.011 | -59.335 | 26.755 | 88 |
| F3_DEEPAR | expanding | MAY_HISTORICAL | 79.35 | -45.682 | 192.72 | 31 |
| F3_DEEPAR | fixed | EXPOSED_EVALUATION | 68.226 | 28.21 | 114.01 | 88 |
| F3_DEEPAR | fixed | MAY_HISTORICAL | 89.417 | 22.935 | 150.48 | 31 |

TFT May pinball 차이의 95% 구간이 0을 포함한다. fixed DeepAR는 두 역사 구간에서 보정 pinball 악화 구간이 0 위에 있다. 시계열 regime shift와 31일의 짧은 May 길이 때문에 이것을 미래 성능 보증으로 해석하지 않는다. burst miss는 TRAIN 양수 target Q95로 정한 subset에서 계산했으며, window-weighted 전체 지표와 day-weighted bootstrap 차이는 표본가중 방식이 다르다.

## 4. 최근 자료/refit 효과

| model | horizon_hours | role | fixed_pinball | expanding_pinball | pinball_change | fixed_coverage | expanding_coverage | fixed_requirement | expanding_requirement | fixed_burst_coverage | expanding_burst_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F1_LGBM | 4 | EXPOSED_EVALUATION | 614.07 | 671.66 | 57.593 | 0.91512 | 0.92074 | 3323 | 4334 | 0.24225 | 0.45938 |
| F1_LGBM | 4 | MAY_HISTORICAL | 1016.2 | 1024.9 | 8.733 | 0.87575 | 0.96296 | 3267.8 | 6785.2 | 0.27298 | 0.74373 |
| F3_DEEPAR | 4 | EXPOSED_EVALUATION | 682.29 | 656.65 | -25.645 | 0.90119 | 0.90727 | 3703.6 | 3854.8 | 0.3225 | 0.31462 |
| F3_DEEPAR | 4 | MAY_HISTORICAL | 1105.6 | 1104.3 | -1.3341 | 0.92221 | 0.91132 | 6052.2 | 5763.1 | 0.54318 | 0.55617 |

LightGBM expanding refit의 May coverage는 96.30%로 높아지지만 요구량은 fixed의 약 2.08배이고, 보정 pinball은 오히려 8.73 GPU·h 증가한다. DeepAR refit의 May 보정 pinball 개선은 1.33 GPU·h에 그치며 같은 refit LightGBM보다 나쁘다. Dec–Feb DeepAR 자체의 refit 개선과 모델 구조 우월성은 별개다. 각 issue의 cutoff, 실제 training membership/date range/N은 refit_memberships/*.json에 저장했고 1,874개 issue membership의 성숙 경계를 독립 재검사했다. 모든 refit은 frozen 설정으로 처음부터 재학습했으며 fit 시점 이전에 full-day label이 성숙한 자료만 쓴다.

## 5. 다른 시간창이 H4보다 유리한가

H1/H2/H4/H8은 같은 15분 atomic GPU-work를 직접 합해 93/89/81/65 window/day를 생성했다. 1시간 Q90 네 개를 더해 H4 Q90로 취급하지 않았다. 후속 계열은 development에서 고른 DeepAR와 LightGBM이고 각 horizon은 같은 horizon LightGBM에 대한 비율로 비교했다.

| horizon_hours | role | Q90_pinball_ratio_to_same_H_LGBM | requirement_ratio_to_same_H_LGBM | coverage | N_zero | N_windows |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | EXPOSED_EVALUATION | 1.0446 | 1.029 | 0.90954 | 1841 | 8184 |
| 1 | MAY_HISTORICAL | 1.0626 | 1.2459 | 0.91282 | 391 | 2883 |
| 2 | EXPOSED_EVALUATION | 1.0365 | 0.96839 | 0.90666 | 1157 | 7832 |
| 2 | MAY_HISTORICAL | 1.0772 | 1.4557 | 0.92099 | 157 | 2759 |
| 4 | EXPOSED_EVALUATION | 1.1111 | 1.1145 | 0.90119 | 725 | 7128 |
| 4 | MAY_HISTORICAL | 1.088 | 1.8521 | 0.92221 | 48 | 2511 |
| 8 | EXPOSED_EVALUATION | 1.1175 | 1.0761 | 0.88934 | 485 | 5720 |
| 8 | MAY_HISTORICAL | 1.1026 | 1.3467 | 0.90769 | 12 | 2015 |

DeepAR의 보정 pinball 비율은 모든 horizon의 두 역사 구간에서 1보다 크다. 짧은 창의 작은 raw loss나 높은 zero 비율로 창을 우승자로 고르지 않았다. **현재 결과만으로 H4를 다른 시간창으로 바꿀 근거는 없다.** 기존 H1/H4/H8/H24 연구와 실패 판정은 historical reference로 보존했다. H2는 이번 별도 비교다.

## 6. 90%와 cap, 실제 reserve 구분

May physical-cap oracle coverage는 **85.9418558343%**로, actionable ≥90%를 성공 gate로 두지 않았다. H4 May physical cap=3,120 GPU·h이며 exact frozen caps를 공통 사용한다. 다른 horizon과 Dec–Feb의 cap 결과는 동일 780-GPU 용량을 적용한 offline 시나리오로, 과거 당시의 실제 설치/확보 용량에 대한 주장이 아니다.

TRIVIAL_CAP의 원시 constant는 capacity를 항상 요구하며, 보정 후 값은 이를 초과할 수 있으므로 cap 전후를 분리했다. TRAIN max 상수는 May coverage 약 98.77%를 얻지만 요구량은 약 22,432 GPU·h이고 pinball도 훨씬 크다. coverage 상승 자체가 개선이 아니라는 대조다. 양수/zero coverage의 weighted identity를 검사했으며 양수·전체 coverage에 모순되는 동시 gate를 만들지 않았다.

새 모델에 대한 실제 확보 reserve나 optimizer shortfall은 계산하지 않았다. PREDICTIONS.secured_reserve는 의도적으로 결측이고 NOT_RUN이다. 모델마다 다른 요구량의 shortfall로 우열을 정하지 않았다. 두 quantile만으로 CRPS를 만들어내지 않았고 overlapping window GPU·h의 합을 고유 작업량 총합으로 부르지 않았다.

## 7. 남은 한계와 후속 통합 판정

사전 선택된 DeepAR는 통합 후보로 권고하지 않는다. TFT의 May 결과는 추가 연구를 생각할 단서지만 development에서 선택되지 않았고 기간 간 우위와 통계적 개선이 확인되지 않았다. 이번 실행에서 후보를 바꾸거나 추가 sweep하지 않았다. 가장 큰 한계는 heavy-tail burst miss, 시간 이동, model calibration의 효율 손실, raw sequence와 요약 표현 차이, DeepAR likelihood/selection 목적 차이, 그리고 진짜 미사용 확인 구간의 부재다.

raw archive의 29개 partition에는 submit timestamp 기준 2023-08-10 04:13:58 UTC~2026-01-01 06:48:47 UTC 자료가 있다. 이 최댓값을 이후 전체 날짜의 completeness·label maturity 보증으로 해석하지 않았다. 이전 연구에서의 노출 여부도 인증할 증거가 없어 새로운 holdout으로 지정하지 않았다. `NO_UNTOUCHED_CONFIRMATION`이며 새 학습과 역사 비교는 정상 완료했다. May에 맞추어 재튜닝하지 않았다.

## 실행·재현성

| family | run_records | training_seconds | peak_memory_MiB | parameter_count |
| --- | --- | --- | --- | --- |
| DEEPAR | 48 | 61.633 | 99.443 | 7539 |
| LGBM | 53 | 153.36 | 0 | 12000 |
| TFT | 4 | 8.5848 | 113.65 | 15730 |

training worker=1, CPU/BLAS/PyTorch threads=1, DataLoader workers=0, GPU 한 작업만 사용했다. 위 run records에는 search, seed 반복, cadence 비교, refit 및 frozen reference load가 포함된다. LightGBM parameter count는 두 quantile의 leaf-value 수이며 neural parameter 수와 같은 정의가 아니다. 학습/추론 시간은 TRAINING_RUN_LEDGER.csv와 fits/*/receipt.json, 전체 추론 시간은 inference_receipt.json에 기록했다. GPU peak는 PyTorch allocated peak이며 시스템 전체 GPU 메모리와 다르다. OOM이나 학습 실패로 target/표본을 줄인 실행은 없다.

초기 데이터 준비 중 timestamp 문자열형·GPU 수량 dtype·Windows Unicode model-file 경로를 고쳤다. 또한 May 원본 대조에서 빈 과거 bin maturity/합계 정밀도를 원본과 일치시킨 후에만 후보 학습을 시작했다. 실행 후 상수 대조군의 정수 배열에서 최대 1 GPU·h 절삭을 발견해 **TRIVIAL_CAP만** 같은 delta/membership로 float64 재계산했다. EXECUTION_CORRECTION.json에 전후 hash를 남겼고 신경망/LightGBM 학습·설정·선택·고정 코드 hash는 변경하지 않았다. 추가 검증 스크립트에서 NPZ 배열을 row마다 반복 압축 해제하며 메모리 할당 오류가 났다. 배열을 한 번만 읽어 vector indexing하도록 고친 후 전체 665,874개 prediction row 검증을 완료했다. 이 오류는 학습 실행의 OOM이 아니며 target/평가 표본 축소는 없다. 실제 재생성할 때는 run_experiment 이후 verify_and_enrich의 보정 단계를 포함해야 한다.

검증: raw target/feature 재현, 원본 모델·snapshot·membership hash, 모든 window 수, refit maturity, 미래 미완료 작업량을 100만 배로 바꾼 feature 불변성, 예측 유한성, cap 경계 및 보호 파일 hash 검사 통과. 정확한 범위는 VALIDATION.json에 기록했으며 시스템 전체 파일 변경 감사를 했다는 주장은 아니다.

필수 산출물: SOURCE_AND_MODEL_LINEAGE.json, ORIGINAL_TRAINING_PERIODS.csv, OLD_MODEL_REPRODUCTION_REPORT_KO.md, PREVIOUS_FAILURE_DIAGNOSIS_KO.md, EXPERIMENT_PROTOCOL.json, DATA_SPLITS_AND_MATURITY.json, TRAINING_RUN_LEDGER.csv, PREDICTIONS.parquet, MODEL_METRICS.csv, HORIZON_COMPARISON.csv, REFIT_COMPARISON.csv, FINAL_REVIEW_KO.md.

NEW_MODEL_AUTO_DEPLOYED = FALSE
OPTIMIZER_CHANGED = FALSE
GRID_CAMPAIGN_EXECUTIONS = 0
EXISTING_PRODUCTION_MODIFIED = FALSE
