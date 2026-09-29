# Frozen Q50 audit for nominal V42 scheduling

6개 동결 모델의 동일230,237개 VALID 작업만 재평가했습니다. 모델 학습·추론·CAL 보정·reserve/headroom 계산·V42 실행은 없습니다. PR94의 scalar-duration NONE 결과를 대체하지 않습니다.

| Model | Q50 MAE [h] | Q50 coverage [%] | Q50 time ratio [x] | Raw Q90 [%] | >12h Raw Q90 [%] |
|---|---:|---:|---:|---:|---:|
| V9_D1_ROLLING14 | 5.383 | 65.83 | 2.046 | 90.93 | 80.80 |
| V9_D2_NORMAL_1P5_NONE | 3.190 | 63.58 | 0.547 | 91.75 | 71.09 |
| V9_D2_EXTREME_1P0_NONE | 4.467 | 65.24 | 1.347 | 94.21 | 86.78 |
| V9_D3_ROLLING14 | 5.030 | 68.97 | 1.757 | 91.14 | 71.41 |
| V13_EXPANDING_S4 | 6.575 | 64.88 | 2.158 | 91.84 | 64.25 |
| V9_D2_NORMAL_1P0_NONE | 3.504 | 63.27 | 0.651 | 81.96 | 30.25 |

D2 extreme: C50 65.24%, 초과34.76%, fold40.64–77.83%, >12h C50 2.49%. 총시간1.347배만으로 안정적인 nominal provider라고 채택하지 않았습니다. **PRIMARY_NOMINAL_RUNTIME_CANDIDATE=NONE**이며 Pareto 연구 후보 지위는 남습니다.

[한국어50항목 검토](FINAL_REVIEW_KO.md), [사전등록](PREREGISTRATION.json), [공통 population 재검증](COMMON_POPULATION_RECHECK.json), [검증](VERIFICATION.json)을 참조하세요. Coverage는[0,1] 단위 CSV이며 표에서는%입니다. Calibration error/std의 pp 표시와 fraction을 구분합니다. Actual-runtime bucket은 결과 진단이며 각 bucket에서50%를 요구하는 calibration test가 아닙니다.

의도된 향후 구조: Planning=total Q50+별도 overrun reserve; Actual=관측 RUNNING gang의 실제 점유 유지, PENDING 시작 전 현재 capacity 확인, duplicate reserve 없음. 제출된 D-day 작업도 같은 provider 개념이며 제출 전 unknown 개별 작업 예측은 하지 않습니다. 이번에는 구현하지 않았습니다.

재현 순서: exact NumPy/pandas 환경과 PR94 SHA-bound 로컬 VALID 파일에서 `preregister.py` → `audit.py` → `finalize.py` → `test_audit.py` → `verify.py`. 기존 사전등록을 덮어쓰지 않습니다. Public Git 파일은 DELIVERY_MANIFEST, 로컬 로그는 LOCAL_EVIDENCE_MANIFEST로 묶었습니다.

## 사용자 추가 요청에 따른 전체 버전 확장

위 원 요청 비교표·50문답의 최선/Pareto는 고정6개 후보 범위다. 추가 요청으로100개 저장 변형까지 확장했고, **V10의 Q50가 D2 extreme보다 유리한 후보를 발견했다.** 아래 표와 [전체 버전 해석](CROSS_VERSION_REVIEW_KO.md)을 함께 읽어야 한다.

| 모델 | MAE [h] | C50 [%] | 시간비율 [x] | fold C50 min–max [%] | >12h C50 [%] |
|---|---:|---:|---:|---:|---:|
| V9::D2_extreme_1.0__NONE | 4.467 | 65.24 | 1.347 | 40.64–77.83 | 2.49 |
| V10::T3_LOGISTIC_ROLLING14_calibrated | 2.700 | 45.04 | 0.803 | 30.90–58.34 | 14.27 |
| V10::T3_ISOTONIC_ROLLING14_calibrated | 2.727 | 46.79 | 0.853 | 36.35–63.08 | 19.01 |
| V11::SELECTED_TOTAL | 5.257 | 72.50 | 1.871 | 46.72–82.08 | 27.34 |
| V12::EXPANDING_R2 | 3.333 | 62.84 | 0.852 | 28.25–76.12 | 7.73 |
| V13::EXPANDING_S4 | 6.575 | 64.88 | 2.158 | 38.60–80.16 | 14.06 |
| V15::R2 | 5.318 | 68.05 | 1.806 | 39.79–80.69 | 17.61 |
| V16::R16-A | 6.183 | 68.87 | 2.088 | 39.57–82.46 | 19.43 |
| V16::R16-B | 5.495 | 68.29 | 1.693 | 47.40–81.95 | 2.18 |
| V16::R16-C | 6.318 | 68.31 | 2.096 | 36.49–81.28 | 18.81 |
