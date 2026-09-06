# V40K 최종 검토

판정: **V40K_POINT_MODEL_INSUFFICIENT**. Point winner: None; safe winner: None.

시작 HEAD `a2a21c904535125c66668a294f91d73a66f5d4a7`, 사전등록 `81a2415f092b435422a33aa34518389db8c89bdf`. 최종 commit은 별도 post-commit receipt로 검증한다.

이번 revision은 conditional median Q50를 prospective estimand로 사용했다. Pinball50=MAE/2이며 두 지표를 독립 근거처럼 해석하지 않는다. Mean signed error는 diagnostic만 보고했다. V40J 결과와 winner NONE은 보존했다.

March08–21은 V40J C0 학습 입력에 노출되어 독립 holdout에서 제외했다. Inner CV는 Feb22–Mar07, 최종 후보 fit은 end-known Apr01 이전, 새 point selection은 Apr01–07, safe fit은 Apr08–14, safe selection은 Apr15–23, shadow는 Apr24–30 UTC로 사전등록했다.

April native partition에는 post-May timestamps와 5월 이후 종료 작업이 섞여 있다. Strict firewall은 block 및 cutoff를 가로지르는 row group 전체를 값 배열 decoding 전에 제외한다. 실제 제출 범위·날짜·누락 group은 timestamp firewall에 기록했다. 이 제한된 complete-case cohort를 전체 날짜/모든 작업으로 일반화하지 않는다.

| Point candidate | Q50 pinball (s) | MAE (s) | Underprediction | Median calibration error | Mean signed error (s), diagnostic | Eligible |
|---|---:|---:|---:|---:|---:|---|
| K0 | 3020.167 | 6040.335 | 50.0613% | 0.000613 | 2523.583 | False |
| K1_HUBER_RESIDUAL | 3482.906 | 6965.811 | 25.1149% | 0.248851 | 910.537 | False |
| K1_L1_RESIDUAL | 3405.406 | 6810.812 | 31.8147% | 0.181853 | 711.326 | False |
| K1_Q50_RESIDUAL | 3405.406 | 6810.812 | 31.8147% | 0.181853 | 711.326 | False |
| K2_NORMALIZED_Q50 | 3819.793 | 7639.586 | 57.3737% | 0.073737 | 423.958 | False |
| K3_SOFT_CDF_MEDIAN | 3182.658 | 6365.316 | 72.0980% | 0.220980 | 2492.701 | False |
| K4_INTERVAL_HAZARD | 3378.772 | 6757.543 | 63.5988% | 0.135988 | 1222.692 | False |
| K5_STACKING | 3482.906 | 6965.811 | 25.1149% | 0.248851 | 910.537 | False |

Subgroup별 catastrophic regression 및 COMPLETED H100-standby median gate 결과는 POINT_MODEL_COMPARISON JSON에 모두 남겼다.

실제 point holdout은 13,060 GPU jobs, 제출 2025-04-01 06:06:27+00:00–2025-04-07 22:32:31+00:00, accepted max end 2025-04-07 23:58:24+00:00다. 275개 late-completing GPU rows는 Apr08 end-known 조건으로 제외했다.

새 후보가 모두 pooled MAE/pinball에서 baseline보다 나빴다. 새 후보 중 pinball이 가장 낮은 K3도 winner가 아니며, 아래 workload 수치는 nominal prediction 진단에만 해당한다. Q90 safe-bound 단계는 실행하지 않았다.

| Nominal workload diagnostic | Active-miss GPU 5-min slots | Overreserved GPU-hours |
|---|---:|---:|
| K0 | 407,480 | 10,335.834 |
| K3 soft CDF median (not winner) | 435,267 | 11,888.716 |

Shadow: **NOT_OPENED_POINT_GATE_FAILED**. Winner 변경/q 변경/refit은 하지 않았다.

신규 V40K 회귀 45 PASS; candidate 독립 반복 18회, K0 exact reproduction PASS. CPU configuration 유지, 실제 GPU candidate fit 0회. 한 차례 사용자 GPU 지시로 CPU process를 중단한 뒤 CPU 유지 정정에 따라 검증된 중간 모델을 재사용해 재개했다. 실제 GPU 학습 결과는 섞지 않았다.

외부 P/Q는 V40J의 PLAUSIBLE_APPROXIMATION 및 PF P5/P50/P95=0.943389/0.950123/0.958954를 그대로 보존했다. PF=0.95, Q control NO. 72 authority blockers 유지, electrical generation HOLD, B0/B1/B2/B3 NO, FULL_MAY NO.

요청된 post-selection 진단: **CONDITIONAL_POINT_BIAS_REMAINS**. V40K point selection은 변경하지 않았다.

K0 pooled underprediction 50.061%, H100 50.035%, H100-standby 48.058%지만 retrospective COMPLETED H100-standby는 61.107%다. Exact 12h 7.813%, 24h 66.605%, 48h 47.163%로 조건부 편향이 서로 상쇄된다. 중앙값이 모든 조건집단에서 정상이고 tail만 문제라고 결론내릴 수 없다.

Wilson 진단과 별도로 일별 block bootstrap을 공개했다. COMPLETED H100-standby의 일별 의존성을 반영한 interval은 50%를 포함하므로, 이 cohort의 조건부 오차를 기간 밖의 확정적 systematic bias로 일반화하지 않는다.

Support 집계의 int/float 문자열 표현 차이는 diagnostic key에서만 정규화했고 독립 numeric groupby와 일치했다. Strong 3,453 / sparse 1,107 / regime mismatch 1,456 / out-of-support 7,044다. 원래 예측·모델·선택·N=100 기준은 그대로다. 초기 잘못된 집계도 superseded audit에 보존했다.

전체 subgroup 지표·잔차 quantile·positive-only Q90/Q95·normalized residual·GPU active miss·candidate delta는 V40K_POST_SELECTION_DIAGNOSTICS.md 및 대응 JSON을 참조한다. V40I 64.13%, V40J 73.64%, V40K pooled 50.061%는 서로 다른 population/time split으로 분리했다.
