FINAL CLASSIFICATION: V40S5_DIRECT_RUNTIME_SAFETY_FAIL
SELECTED MODEL: NONE
SELECTED LIGHTGBM CONFIG: L2
HISTORICAL TRAINING JOBS: 421
Q50 MODEL: LightGBM quantile 0.50 / L2
Q90 MODEL: LightGBM quantile 0.90 / L2
Q95 MODEL: LightGBM quantile 0.95 / L2
Q99 MODEL: LightGBM quantile 0.99 / L2
UNCERTAINTY MODEL: LightGBM regression / historical OOF squared residuals
UARP-STYLE CANDIDATE: Q99 + max(0.20*Q99, 0.50*sigma)
DEV SAFETY: FAIL
CAL SAFETY: FAIL
EXPOSED SAFETY: FAIL (no selected candidate; all fixed candidates fail)
EFFICIENCY VS REQUESTED WALLTIME: PASS alone, safety FAIL
CURRENT RSP REPLACED: NO
OPTIMIZER INTEGRATION: NO
PRODUCTION READY: NO


지정된 S4 scientific 7d83ea7385b8b4596efe7791a7aad6a60926dcb7, receipt ea9e5133657d417ce66c8436cac7e05f8634926b, S3 scientific 836dfa1008c6810d077582892745b1892210c029, receipt bfeb9c3312b397fdd15a00dfc9eac37dd4b2b6aa를 Git에서 해석하고 순차 조상 관계를 검증했다. S4 분류와 모든 선택 NONE, optimizer integration NO를 보존했다. 상속 Git 항목은 실제 5,459개이며, S4가 보존했던 5,352개에 S4의 107개 경로(과학 파일 106개와 최종 receipt)가 더해진 수다. S4 106개 과학 파일과 S3 109개 파일의 바이트를 확인했다.

원본 73,504행 / 73,504개 고유 작업, 양의 runtime 72,292, 0초 1,212, 음수 0개. end < cutoff 작업은 425개, end >= cutoff는 73,079개다. cutoff 이전 0초 4개를 제외한 feature 구성 가능 학습 작업은 정확히 421개다. cutoff는 2025-03-14T08:00:00Z이며, 421개 모두 엄격한 end < cutoff를 만족한다.

학습 자료의 earliest/latest submit은 2025-03-14 00:00:56+00:00 / 2025-03-14 07:35:14+00:00, earliest start는 2025-03-14 00:01:11+00:00, latest end는 2025-03-14 07:53:15+00:00다. 월별 학습 수는 2025-03: 421이다. 원본 노출 자료가 시작되는 첫날의 약 8시간에 한정된 mature 표본이며, 장시간 실행 중 작업이 이 cutoff까지 완료되지 못하는 선택 효과가 있다. 이는 관측 범위에서 추론되는 한계이며 완전한 과거 scheduler history가 아니다.

TRAINING_LIBRARY_FULL_BACKLOG_AUTHORITY=NO; TRAINING_LIBRARY_COMPLETE_CASE_SELECTION_LIMITATION=YES. 기존 exposed terminal-service complete-case 원본의 한계와 검증되지 않은 backlog/censoring을 유지한다. 미래 완료 라벨을 끌어오거나 과거 원본을 새로 추정하지 않았다.

가정은 D1_SCHEDULER_REQUEST_STATE_PROXY_V1이다. HISTORICAL_D1_SNAPSHOT_PROVENANCE=UNVERIFIED, ORIGINAL_SUBMISSION_VALUE_PROVENANCE=UNVERIFIED, REQUEST_MODIFICATION_HISTORY=UNOBSERVED. 논문용 명칭은 ASSUMPTION-BASED TRACE-DRIVEN RUNTIME MODEL이다.

Track P feature: requested_seconds, num_gpus_req, num_nodes_req, num_cores_req, requested_memory_mib, partition, qos, submit_hour, submit_dow. 5개 request 양은 log1p, partition/qos는 historical-only vocabulary 및 UNKNOWN one-hot, numeric missing은 과거 median+indicator다. 실제 학습 자료 결측/invalid는 모든 feature에서 0이다. user/account/job/application identity, 실제 start/end/runtime/status, K0/reference_safe, 미래 상태·migration·전기 결과는 predictor에서 제외했다. RSP와 GPU 평가 가중치는 별도 읽기 전용 비교 값이다.

| 학습 분포 | median | P90 | P95 | P99 |
| --- | --- | --- | --- | --- |
| runtime_seconds | 93.000 | 2,091.000 | 3,144.000 | 8,376.800 |
| requested_seconds | 57,600.000 | 172,800.000 | 172,800.000 | 600,000.000 |
| num_gpus_req | 1.000 | 2.000 | 4.000 | 20.000 |
| actual_request_ratio | 0.002 | 0.236 | 0.284 | 0.337 |

학습 partition/QoS 빈도: {"partition": {"gpu-h100": 232, "gpu-h100-stdby": 80, "project_3": 73, "debug-gpu": 20, "gpu-h100l": 16}, "qos": {"normal": 331, "standby": 80, "high": 10}}.

시간순 HIST_FIT/HIST_TUNE는 332/89개다. 80% 경계의 동일 end timestamp 블록 전체를 HIST_TUNE에 넣었다. 전처리는 tuning용 HIST_FIT, 각 OOF의 이전 fold, 최종 전체 historical library에 각각 별도로 fit했다. PENDING TRAIN 1,190행은 모델 학습에 사용하지 않았으며 DEV 4,346 / CAL 2,634 / EXPOSED 2,713 job-issue의 S4 파일 바이트와 ID는 동일하다. 학습 작업과 PENDING 평가 작업의 중복은 0이다.

| 설정 | normalized pinball mean | Q50 pinball | Q90 | Q95 | Q99 |
| --- | --- | --- | --- | --- | --- |
| L0 | 0.596 | 387.569 | 516.133 | 314.906 | 86.715 |
| L1 | 0.595 | 387.560 | 515.620 | 313.702 | 86.148 |
| L2 | 0.562 | 379.216 | 398.788 | 331.890 | 120.517 |

선택 L2: num_leaves=31, learning_rate=.02, n_estimators=800, min_child_samples=100. L1 regularization=0, L2 regularization=1, subsample=1, feature_fraction=1, CPU, n_jobs=1, seed=4005. HIST_TUNE의 mean raw pinball을 mean actual runtime으로 나눈 점수로 공유 설정을 고정했다.

사전등록 원본 커밋은 8477fda59945815dc70e7896b42feff981d2936c다. 최초 fit 진입에서 출력 디렉터리 생성 누락으로 모델 fit 이전에 중단했고, 디렉터리 생성 및 receipt self-hash 제외를 수정한 최종 pre-fit 커밋은 7d24e148650bcef66e2182f904d13c2b89267f94다. 그 사이 모델 fit=0, tuning prediction=0이며 과학 규칙·설정은 동일하다. 원본 receipt와 erratum을 보존했다.

잔차용 Q50은 HIST_TUNE 선택을 통한 간접 정보 유입을 막기 위해 사전에 L0로 고정한 보조 OOF 모델이다. 최종 4개 분위수와 잔차 회귀는 L2를 공유한다. 시간순 OOF fold의 fit/validation 수는 70/69, 139/70, 209/71, 280/60, 340/81이다. 동일 timestamp는 분리하지 않았다. warmup 70개는 잔차 학습에서 제외하고 351개 OOF 오차만 사용했다. 첫 fold는 min_child_samples=50 조건상 분할이 없는 상수 LightGBM이며 이를 그대로 감사 기록했다. OOF Q50 MAE는 760.241초, 모든 fold에서 train/validation job 중복은 0이다.

UARP 식과 고정 계수는 [Choi & Oh (2026), §4.3–4.4](https://link.springer.com/article/10.1007/s11227-026-08422-8)에서 확인했다. 원문의 데이터·스케줄러 결과 재현이 아닌 식의 적용이며, 경험적 Q99가 99% coverage를 보장한다고 주장하지 않는다. 요청 walltime 상한은 적용하지 않았다.

DEVELOPMENT 후보 결과 (coverage는 %, GPU_under는 GPU·초, GPU_over는 GPU·시간):

| 후보 | coverage | GPU coverage | GPU_under_sec | GPU_over_h | 안전성 / 효율성 |
| --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 66.27% | 71.73% | 48,173,935.178 | 45,388.015 | 비교 기준 |
| R1_RECORDED_REQUESTED_WALLTIME | 98.04% | 95.26% | 3,356.000 | 237,173.455 | 비교 기준 |
| R2_Q90 | 43.05% | 45.74% | 145,950,564.974 | 2,732.718 | FAIL / PASS |
| R3_Q95 | 43.74% | 46.78% | 138,269,463.154 | 3,997.957 | FAIL / PASS |
| R4_Q99 | 43.83% | 46.86% | 136,769,782.368 | 4,500.409 | FAIL / PASS |
| R5_UARP_STYLE | 45.84% | 49.31% | 132,384,330.325 | 5,629.163 | FAIL / PASS |

DEVELOPMENT 분위수 정확도 (초, WAPE는 %; pinball은 raw prediction, 나머지는 고정 하한·단조 보정 후):

| 모델 | MAE | WAPE | bias | pinball |
| --- | --- | --- | --- | --- |
| Q50 | 25,067.902 | 99.89% | -24,999.521 | 12,535.156 |
| Q90 | 24,313.896 | 96.88% | -22,021.020 | 20,965.390 |
| Q95 | 23,618.700 | 94.11% | -19,936.970 | 20,780.104 |
| Q99 | 23,691.607 | 94.41% | -19,617.840 | 21,459.053 |

CALIBRATION 후보 결과 (coverage는 %, GPU_under는 GPU·초, GPU_over는 GPU·시간):

| 후보 | coverage | GPU coverage | GPU_under_sec | GPU_over_h | 안전성 / 효율성 |
| --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 84.13% | 90.51% | 32,834,240.735 | 11,716.042 | 비교 기준 |
| R1_RECORDED_REQUESTED_WALLTIME | 98.71% | 98.09% | 241,373.000 | 147,600.691 | 비교 기준 |
| R2_Q90 | 52.89% | 77.01% | 55,749,417.429 | 6,183.295 | FAIL / PASS |
| R3_Q95 | 64.20% | 81.78% | 53,444,455.456 | 8,351.955 | FAIL / PASS |
| R4_Q99 | 69.70% | 83.68% | 53,052,509.858 | 11,355.362 | FAIL / PASS |
| R5_UARP_STYLE | 73.61% | 85.93% | 51,763,019.207 | 14,048.025 | FAIL / PASS |

CALIBRATION 분위수 정확도 (초, WAPE는 %; pinball은 raw prediction, 나머지는 고정 하한·단조 보정 후):

| 모델 | MAE | WAPE | bias | pinball |
| --- | --- | --- | --- | --- |
| Q50 | 13,863.924 | 98.61% | -13,805.886 | 6,934.815 |
| Q90 | 13,437.388 | 95.57% | -10,632.373 | 10,971.760 |
| Q95 | 13,963.012 | 99.31% | -8,839.445 | 10,959.256 |
| Q99 | 14,549.194 | 103.48% | -8,024.816 | 11,206.866 |

EXPOSED_EVALUATION 후보 결과 (coverage는 %, GPU_under는 GPU·초, GPU_over는 GPU·시간):

| 후보 | coverage | GPU coverage | GPU_under_sec | GPU_over_h | 안전성 / 효율성 |
| --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 34.32% | 38.65% | 33,086,831.036 | 3,410.337 | 비교 기준 |
| R1_RECORDED_REQUESTED_WALLTIME | 93.03% | 92.88% | 6,881.000 | 52,182.568 | 비교 기준 |
| R2_Q90 | 23.48% | 28.61% | 67,436,163.696 | 1,780.339 | FAIL / PASS |
| R3_Q95 | 26.61% | 30.42% | 63,374,812.200 | 2,511.308 | FAIL / PASS |
| R4_Q99 | 27.20% | 31.05% | 61,771,541.012 | 3,381.167 | FAIL / PASS |
| R5_UARP_STYLE | 28.31% | 32.95% | 58,538,463.833 | 4,287.391 | FAIL / PASS |

EXPOSED_EVALUATION 분위수 정확도 (초, WAPE는 %; pinball은 raw prediction, 나머지는 고정 하한·단조 보정 후):

| 모델 | MAE | WAPE | bias | pinball |
| --- | --- | --- | --- | --- |
| Q50 | 14,376.018 | 98.44% | -14,322.523 | 7,188.009 |
| Q90 | 13,456.205 | 92.14% | -11,761.916 | 11,432.869 |
| Q95 | 12,976.693 | 88.86% | -10,285.494 | 11,116.819 |
| Q99 | 13,119.414 | 89.83% | -9,603.600 | 11,356.209 |

안전성은 DEV와 CAL에서 각각 coverage≥90%, GPU coverage≥90%, N≥100인 모든 issue-day에서 두 coverage≥88%, GPU_under<RSP를 모두 요구했다. 효율성은 각 split에서 GPU_over<requested walltime를 별도로 요구했다. 4개 후보 모두 효율성만 만족하고 안전성은 실패했다. 따라서 selected=NONE이며 EXPOSED 후보 결과는 고정 비교의 설명 자료다.

선택 동결 커밋 d8ae2354c7b10296c641f71110f16105db69f2e3 후 정확히 1회 P-W sensitivity와 1회 독립 P 재학습을 마쳤다. EXPOSED 이전 전체 모델 동결 커밋은 817e073c682db113c9289d91d54503c438b061b3다. 이후 모델 재학습·계수 수정·후보 승격은 0이다.

| EXPOSED 후보 | RSP 대비 GPU_under 감소율 | request 대비 GPU_over 감소율 |
| --- | --- | --- |
| R2_Q90 | -103.82% | 96.59% |
| R3_Q95 | -91.54% | 95.19% |
| R4_Q99 | -86.70% | 93.52% |
| R5_UARP_STYLE | -76.92% | 91.78% |

감소율 음수는 악화를 뜻한다. UARP는 RSP보다 GPU 과소예측량이 76.92% 늘었다. 91.78%의 과잉예약 감소를 안전한 효율 개선으로 해석할 수 없다. 현재 RSP도 EXPOSED에서 충분히 안전하다고 볼 수 없지만 이번 실험으로 대체 권한이 생기지 않았다.

15분 완료 슬롯: actual과 candidate 각각 ceil(sec/900)를 한 번 적용했다. 96슬롯 상한을 덧씌우지 않았다.

| EXPOSED 후보 | 슬롯 MAE | signed error | ≥1슬롯 조기 | ≥4슬롯 조기 | ≥8슬롯 조기 | GPU ≥1슬롯 조기 |
| --- | --- | --- | --- | --- | --- | --- |
| R0_CURRENT_RSP | 9.411 | -4.516 | 64.98% | 51.38% | 36.34% | 60.67% |
| R1_RECORDED_REQUESTED_WALLTIME | 41.382 | 41.243 | 6.97% | 0.00% | 0.00% | 7.12% |
| R2_Q90 | 15.112 | -13.309 | 76.15% | 72.39% | 69.59% | 71.12% |
| R3_Q95 | 14.363 | -11.367 | 73.09% | 71.21% | 68.26% | 69.29% |
| R4_Q99 | 14.459 | -10.600 | 72.54% | 70.44% | 67.45% | 67.91% |
| R5_UARP_STYLE | 14.499 | -9.677 | 71.58% | 70.03% | 65.46% | 66.94% |

| split | raw crossing N / % | 보정 후 crossing | raw 음수 값 수 | 평균 보정량(초) | A≥B | B>A | sigma median / P99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TRAIN | 217 / 18.24% | 0 | 2 | 2.665 | 100.00% | 0.00% | 1,483.327 / 2,269.489 |
| DEVELOPMENT | 1623 / 37.34% | 0 | 168 | 6.144 | 92.89% | 7.11% | 1,483.327 / 2,293.166 |
| CALIBRATION | 181 / 6.87% | 0 | 282 | 1.510 | 99.43% | 0.57% | 1,483.327 / 2,769.206 |
| EXPOSED_EVALUATION | 1345 / 49.58% | 0 | 0 | 23.097 | 66.79% | 33.21% | 1,483.327 / 4,109.350 |

모든 raw 예측을 보존했다. 비음수 runtime 요구를 위해 학습 전 등록한 max(raw,0) 물리적 하한 후 누적 max 단조 보정을 적용했다. 후보는 모두 finite/nonnegative다. sigma는 요청한 sqrt(max(predicted_r2,0))를 그대로 사용했다. EXPOSED residual r2 음수 예측은 1,145/2,713개(42.20%)로 sigma가 0이 된다. 잔차 회귀의 불안정성을 보여주는 진단이며 조정하지 않았다.

actual>requested 행은 historical 0개, TRAIN 1개, DEV 85개, CAL 34개, EXPOSED 189개로 모두 유지했다. actual/request median은 historical .002448, TRAIN .080171, DEV .051678, CAL .044722, EXPOSED .290208이다. request를 hard upper bound로 사용하지 않았다.

Unique-job sensitivity는 split별 earliest issue만 사용했다: TRAIN 1,160 / DEV 2,893 / CAL 1,738 / EXPOSED 1,812개. 선택에는 사용하지 않았다. 모든 후보 결과는 UNIQUE_JOB_SENSITIVITY.json에 있다.

| unique-job split | UARP coverage | GPU coverage | GPU_under_sec | GPU_over_h |
| --- | --- | --- | --- | --- |
| TRAIN | 17.93% | 34.23% | 21,307,492.908 | 1,192.639 |
| DEVELOPMENT | 55.65% | 56.12% | 71,103,532.257 | 4,896.222 |
| CALIBRATION | 66.17% | 82.45% | 43,789,396.397 | 9,074.644 |
| EXPOSED_EVALUATION | 37.47% | 42.69% | 37,858,986.139 | 3,969.232 |

시간 분포 이동은 historical reference decile bins와 1e-6 probability floor를 사용하는 사전등록 PSI로 확인했다. runtime/actual-request/request/GPU/submit hour/weekday 분포와 partition/QoS 빈도도 전 split에 저장했다. 진단 후 적응 학습은 하지 않았다.

| split | runtime median | request median | actual/request median | request PSI | GPU PSI |
| --- | --- | --- | --- | --- | --- |
| HISTORICAL_TRAINING_LIBRARY | 93.000 | 57,600.000 | 0.002 | 0.000 | 0.000 |
| TRAIN | 13,702.000 | 172,800.000 | 0.080 | 5.426 | 0.837 |
| DEVELOPMENT | 8,689.500 | 172,800.000 | 0.052 | 1.052 | 0.604 |
| CALIBRATION | 2,691.000 | 172,800.000 | 0.045 | 2.050 | 1.031 |
| EXPOSED_EVALUATION | 13,626.000 | 43,200.000 | 0.290 | 0.923 | 2.081 |

P-W는 requested_seconds와 그 missing indicator만 제거했다. 모델 family·설정·분위수·잔차 OOF 절차·수식은 동일하고 별도 winner search는 없다. selected=NONE이므로 모든 등록 수식의 변화는 진단으로만 보고했다.

| split | Q50 MAE Δ(P-W − P) | Q90 pinball Δ | Q95 Δ | Q99 Δ | UARP coverage Δ(pp) | GPU Δ(pp) |
| --- | --- | --- | --- | --- | --- | --- |
| TRAIN | -97.271 | 110.100 | 117.260 | -286.096 | 1.597 | 1.715 |
| DEVELOPMENT | -128.272 | 33.610 | 93.748 | -99.771 | 1.266 | 1.670 |
| CALIBRATION | 72.332 | 87.969 | 41.566 | -69.604 | 0.645 | 0.439 |
| EXPOSED_EVALUATION | -455.879 | -83.533 | -76.797 | -271.966 | -0.111 | -0.036 |

| 모델 | walltime gain 비중 | HIST_TUNE permutation loss Δ |
| --- | --- | --- |
| Q50 | 40.80% | 30.494 |
| Q90 | 12.19% | 13.450 |
| Q95 | 37.25% | -10.019 |
| Q99 | 22.90% | -16.354 |
| RESIDUAL | 49.58% | -3,845,551,013,649.990 |

Gain은 최종 모델, permutation은 HIST_FIT 전용 보조 모델에서 HIST_TUNE만 사용했다. quantile은 pinball, 잔차는 OOF squared-error target의 MSE를 사용하므로 잔차 permutation의 단위는 초⁴이다. Q50/Q90에서는 walltime 순열이 오차를 늘리지만 Q95/Q99와 residual에서는 반대다. 이 작은 단일 오전 자료로 walltime의 일반적 무용성을 결론낼 수 없다. feature 제거 또는 계수 조정 근거로 사용하지 않았다.

May runtime/outcome/training/calibration/selection/sensitivity scientific row reads=0, Apr24–30 shadow=SEALED, scientific reads=0. Git 경로·index·blob identity 메타데이터 discovery는 nonzero로 공개했다. Phase 0에서는 SHA로 검증된 pre-Apr24 source의 전체 완료 시각/라벨을 집계·정합성 검사했고, 학습은 cutoff 이전 421개로 제한했다. EXPOSED는 이미 노출된 역사 자료다.

Optimizer/Gurobi/OpenDSS/Fresh calls=0. A0/A1/M1/MF, RUNNING/PENDING migration, WAN, Rack, terminal, MESS route/P/Q, AC restoration, event trigger, local repair, rolling MPC는 모두 변경 0이다. normative sequence와 production q=5576.44921875s, PF=.95, Q control=NO, electrical=HOLD, B0–B3=NO, FULL_MAY=NO를 유지했다.

검증은 pytest 50개 통과(실패·오류·skip=0). 사용자 최소 87항목을 테스트/최종 receipt 검증에 연결했다. 독립 재학습은 1회이며 Q50/Q90/Q95/Q99/sigma 및 모든 새 safe candidate의 max/mean 차이가 모두 0이고 최종 모델 파일 SHA도 일치한다. 반복 결과로 선택을 바꾸지 않았다.

실행환경: Python 3.11.7 (tags/v3.11.7:fa7a6f2, Dec  4 2023, 19:24:49) [MSC v.1937 64 bit (AMD64)]; libraries {"numpy": "2.2.6", "pandas": "2.2.3", "scikit-learn": "1.6.1", "lightgbm": "4.6.0", "pyarrow": "18.1.0"}; CPU Intel64 Family 6 Model 186 Stepping 2, GenuineIntel, threads=1, seed=4005. 전체 fit 인스턴스 43개(설정 비교 12, primary 및 진단 11, P-W 10, 독립 repeat 10), 합계 학습 시간 2.499s. 추론 기록 합계 2.959s. 파일별 학습 대상·시각·전처리·SHA와 실행 시간은 COMPUTE_LEDGER.json에 있다.

실패 해석: 이용 가능한 complete-case Kestrel trace, 명시적 request-state proxy 가정, cutoff 이전 mature historical library, 사전등록된 direct quantile/UARP-style 모델군에서는 요구 신뢰성–효율성 절충을 만족하는 대체 모델이 없었다. runtime prediction이 불가능하다는 의미는 아니다. 학습 가능 이력이 421개/약 8시간이라는 제약을 포함한 이 계약의 실패다.

RECOMMENDED_OPERATIONAL_RUNTIME=CURRENT_RSP. CURRENT_RSP_REMAINS_OPERATIONAL. FURTHER_RUNTIME_MODEL_PROLIFERATION=NO. FURTHER_RUNTIME_MODEL_WORK=DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA. 추가 quantile, 계수 조정, 새 모델군, BODY/tail 복원, 게이트 완화는 하지 않았다. 향후 재검토에는 검증된 snapshot, 더 긴 과거 이력·full backlog/censoring 권한, 승인된 application/job context 또는 progress/checkpoint 정보 같은 새로운 권한·자료가 필요하다.

Adapter: proposal_only=true, optimizer_use_allowed=false, recommended_rows=[]. 과학 커밋과 최종 receipt 커밋은 자기참조를 피하기 위해 V40S5_FINAL_COMMIT_RECEIPT.json과 git log -1 --format=%H -- 해당 파일로 확인한다.
