# V40L 최종 검토

판정: **V40L_TAIL_MODEL_INSUFFICIENT**. Nominal은 frozen K0, tail winner는 None.

시작 commit `2434a0e8a870ad7c52c34fdc0e270c6e164aebd8`; 사전등록 `9ae21b99376c456be98ab2495e7a3396d8025b1c`. 최종 commit은 post-commit receipt에 기록한다.

K0 모델·Apr01–07 예측 SHA는 그대로이며 K0 재학습/offset/subgroup correction은 0회다. V40K_POINT_MODEL_INSUFFICIENT 및 CONDITIONAL_POINT_BIAS_REMAINS를 재해석하지 않았다.

Apr01–07은 visible development다. T1은 전체 signed rolling OOF residual 27,792행을 사용했다. T2는 Apr01 이전 end-known GPU 210,334행으로 direct quantile을 학습했으며 Q50는 nominal로 사용하지 않았다. T7만 positive excess를 별도로 학습하고 초과 확률과 결합했다.

일반 raw label은 block 종료 이전에 알려진 값만 사용했다. May 이후 submit/start/end가 포함된 row group은 값 decoding 전에 통째로 제외했다. Selection 표는 이 제한된 complete-case cohort의 결과이며, 제외된 long job/날짜를 포함한 전체 calendar population의 coverage가 아니다.

| Candidate | 상태 | Overall Q90 | H100 Q90 | H100-standby Q90 | Strong H100-standby Q90 | GPU-weighted Q90 | Overreserved GPUh | Active-miss GPU 5min slots |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| T0 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 56.937% | 53.913% | 14.579% | 75.000% | 65.988% | 13469.540 | 231,224 |
| T1 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 69.875% | 67.826% | 36.978% | 100.000% | 72.555% | 47099.461 | 144,438 |
| T2 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 85.391% | 84.565% | 78.967% | 100.000% | 86.904% | 58095.984 | 64,003 |
| T3_R | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 65.742% | 63.571% | 36.598% | 100.000% | 65.330% | 46239.695 | 146,137 |
| T3_D | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 76.699% | 77.112% | 74.487% | 100.000% | 76.018% | 53662.122 | 73,371 |
| T4_N100 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 52.633% | 50.031% | 16.249% | 75.000% | 57.795% | 82190.363 | 165,879 |
| T4_N200 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 52.633% | 50.031% | 16.249% | 75.000% | 57.795% | 82190.363 | 165,879 |
| T4_N500 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 51.076% | 47.888% | 11.010% | 75.000% | 57.162% | 82134.295 | 168,720 |
| T5 | NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE | — | — | — | — | — | — | — |
| T6 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 79.502% | 78.478% | 63.705% | 100.000% | 85.439% | 123488.099 | 48,504 |
| T7 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 90.827% | 90.373% | 91.268% | 100.000% | 91.385% | 61659.654 | 49,898 |
| T8_N100 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 29.304% | 27.547% | 9.188% | 100.000% | 25.348% | 11063.142 | 94,132 |
| T8_N200 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 29.304% | 27.547% | 9.188% | 100.000% | 25.348% | 11063.142 | 94,132 |
| T8_N500 | INELIGIBLE_COVERAGE_OR_SUPPORT_OR_ABSTENTION | 29.388% | 27.547% | 9.188% | 100.000% | 25.397% | 11078.209 | 94,061 |

T7은 overall 90.827%, H100 90.373%, 전체 H100-standby 91.268%, GPU-weighted 91.385%다. 그러나 사전등록한 strong-support H100-standby 평가 표본은 N=4로 최소 100에 못 미친다. 해당 gate는 INSUFFICIENT_SUPPORT이며 생략할 수 없어 winner NONE이다. 이는 T7의 aggregate coverage 실패라는 뜻이 아니다.
T7 overall day-block 95% CI=[0.8828419598119738, 0.9261330761812921]; GPU-weighted CI=[0.8801811215604319, 0.928595629341013]. Q95 overall coverage=94.677%는 별도 진단이다.
Baseline→winner active-miss/overreservation은 winner 부재로 비교값 없음(null)이다. 참고용 baseline→T7(비선정 후보)은 active miss 231,224→49,898 GPU 5분 슬롯, overreserved 13,469.540→61,659.654 GPUh다. T7을 winner나 배포 방법으로 재해석하지 않는다.

Calibration: 12955행, dates ['2025-04-09', '2025-04-10', '2025-04-11', '2025-04-12', '2025-04-13', '2025-04-14']. Selection: 3532행, dates ['2025-04-15', '2025-04-16', '2025-04-17', '2025-04-18', '2025-04-19', '2025-04-20'].

선택 순서는 native Q90 coverage gates 이후 overreservation → mean safe-duration inflation → active miss → registry order다. 일별 block bootstrap CI는 comparison JSON에 공개했으며 iid/기간 밖 보장은 주장하지 않는다. Q95는 extreme-risk diagnostic이며 Q90 실패를 덮지 않는다.

Shadow: NOT_OPENED_NO_TAIL_WINNER; 실제 row payload opened=False, read rows=0. Winner/q/model/support threshold를 변경하지 않았다.

T5: 설치된 XGBoost의 AFT objective는 synthetic CPU probe에서 지원됐다. 하지만 cutoff-time alive/status snapshot이 없어 실제 censored job census와 AFT 학습은 제외했다. Censored count/GPU/walltime/hardware/standby/requested GPUh는 unknown(null)이며 0이라고 쓰지 않았다. May completion value를 읽거나 누락 label을 임의 runtime으로 채우지 않았다.

T6는 V40K K4의 동결된 CPU survival curve에서 Q90/Q95를 복원했다. T8의 OOD는 abstain이며 전체 coverage denominator에서 빠지지 않고 winner를 차단한다. Walltime 전용 hand correction이나 검증되지 않은 walltime ceiling을 만들지 않았다.

검증: 신규 pytest 52 PASS; T1/T2/T7 gate/excess 독립 CPU 반복 학습 4쌍 byte-identical; frozen K0/OOF prediction max diff 0.0초; 기존 보호 metadata 5362개와 V40J/V40K SHA 367개 일치.

May scientific counters 전부 0. 초기 path/code discovery 및 footer metadata 접근은 NONZERO로 분리 공개했다. CPU only; GPU scientific fit 0.

PF=0.95, Q control NO, 72 authority blockers, 31-day electrical generation HOLD, B0–B3 NO, FULL_MAY NO. Production model/q와 외부 P/Q authority는 바꾸지 않았다.

XGBoost API 확인: https://xgboost.readthedocs.io/en/release_3.2.0/parameter.html . 실제 objective 가용성은 설치된 3.2.0 CPU synthetic probe로 검증했다.

사용자 요청 post-selection 진단: **MIXED_FAILURE**. 기존 classification/winner/shadow lock은 그대로다. 새 fit/runtime prediction/threshold/support-rule/conformal retuning은 0회이며, selection 당시 동결된 support lookup을 저장된 selection rows에 조인했다.
T7 miss 324개 job의 GPU-underprediction은 14,960,009.137초다. Miss jobs 기준 top 1%/5%/10% (4/17/33개)가 전체 miss mass의 22.625% / 50.932% / 66.374%를 설명한다.
T0–T8 모든 variant의 exact metric/gate 표와 threshold, T7 실패 분해, raw-vs-calibrated delta, Pareto 분모별 표는 V40L_POST_SELECTION_TAIL_DIAGNOSTIC.json 및 V40L_TAIL_FAILURE_CLASSIFICATION.md에 있다. 324개 miss job의 상세 행은 V40L_TAIL_MISS_COHORT.csv에 저장했다.
이 진단에서 standby는 기존 동결된 QoS==standby 정의다. Partition에 stdby가 포함돼도 QoS가 normal인 경우는 별도 partition/QoS 조합으로 공개했다. 정의를 변경하지 않았다. T5의 후속 진단 표기는 CENSOR_AUTHORITY_INSUFFICIENT다.

Strong-support standby N=4 provenance 추가 확인: **TEMPORAL_COVARIATE_SHIFT**. 기간별 total/strong은 Apr01–07 2291/1772, Apr08–14 383/130, Apr15–23 1317/4다. Selection의 12h 1223개 중 1153개는 과거 48h로만 관측된 두 feature8 profile(과거 지원 3237/1501개)에 해당한다. Exact walltime 포함 9개 key를 그대로 적용해 exact_count=0, REGIME_MISMATCH가 됐다.
세 기간 모두 동일한 support lookup, hardware/standby 정의, numeric/string key 정규화를 사용했다. 원인 분류는 허용된 cohort의 walltime covariate shift이며, implementation inconsistency가 발견되거나 support gate가 변경된 것은 아니다. 상세 기간별 수치·분포·4개 strong row provenance는 V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.json/.md에 기록했다.
