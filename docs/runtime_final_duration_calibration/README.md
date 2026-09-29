# Frozen Runtime duration calibration

선택은 **NONE**입니다. 230,237개 동일 작업, 6개 동결 후보, 5개 temporal fold를 비교했습니다. GPU 가중치 없는 초 단위 비율을 사용합니다.

| Model | Q50 MAE [h] | Raw Q90 [%] | >12h Raw Q90 [%] | Q50 time [x] | Q90 time [x] | α (fold 1→5) | OP coverage [%] | OP time [x] |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| V9_D1_ROLLING14 | 5.383 | 90.93 | 80.80 | 2.046 | 4.357 | 1.00;1.00;0.90;1.00;1.00 | 89.90 | 4.235 |
| V9_D2_NORMAL_1P5_NONE | 3.190 | 91.75 | 71.09 | 0.547 | 3.743 | 1.00;0.60;0.35;0.15;1.00 | 86.22 | 2.546 |
| V9_D2_EXTREME_1P0_NONE | 4.467 | 94.21 | 86.78 | 1.347 | 4.476 | 1.00;0.55;0.65;0.25;1.00 | 90.46 | 3.560 |
| V9_D3_ROLLING14 | 5.030 | 91.14 | 71.41 | 1.757 | 3.919 | 1.00;1.00;0.90;0.40;1.00 | 89.84 | 3.642 |
| V13_EXPANDING_S4 | 6.575 | 91.84 | 64.25 | 2.158 | 3.807 | 1.00;0.70;0.95;0.15;1.00 | 87.84 | 3.529 |
| V9_D2_NORMAL_1P0_NONE | 3.504 | 81.96 | 30.25 | 0.651 | 2.346 | 1.00;1.00;0.75;0.35;1.00 | 80.56 | 2.085 |

α는 각 fold CAL의 21개 고정 grid에서 선택했고 VALID 적용 전에 동결했습니다. 모든 후보의 OP time ratio는 2배 이상이며 모든 primary가 fold별 90% 기준을 실패했습니다. 기존 provider gate와 V9 full-distribution 결함을 변경하지 않았습니다.

[한국어 50항목 검토](FINAL_REVIEW_KO.md), [사전등록](PREREGISTRATION.json), [공통 population](COMMON_RUNTIME_POPULATION_AUDIT.json), [CAL 감사](CAL_CAUSALITY_AUDIT.json), [선택 동결](FINAL_SELECTION_FREEZE.json), [검증](VERIFICATION.json)을 참조하세요.

재현: 동결 로컬 입력과 exact environment가 필요합니다. `prepare.py`는 원 요청 수정 직전의 보존된 population 감사에서 입력을 준비하고, `calibrate.py`는 CAL quantile/alpha를 생성합니다. 두 단계는 이미 동결된 파일이 있으면 덮어쓰지 않고 중단합니다. `evaluate.py`, `finalize.py`, `test_duration.py`, `verify.py`가 결과·보고·검증을 수행합니다. 모델 학습 엔트리포인트는 호출하지 않습니다. 큰 행별 CAL/VALID/OP 예측과 폐기된 shared-reserve 초안은 로컬 SHA manifest로 보존됩니다.
