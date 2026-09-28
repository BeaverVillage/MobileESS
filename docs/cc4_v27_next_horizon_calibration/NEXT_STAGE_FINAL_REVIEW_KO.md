# CC4-v2.7 후속 축소 연구 최종 검토

선택한 계산 백엔드 CPU_MULTIPROCESS는 대표 배치에서 단일 실행 대비 2.52배의 속도를 보였고 동등성 기준을 통과했다. 이번 CPU4 예측과 지표는 비트 단위로 같았다. GPU는 실제 NVIDIA 장치에서 실행됐으나 더 느리고 수치 차이가 커서 선택하지 않았다. 과학적 결과는 음성이다. 새 리드 그룹 보정과 국소 스케일 보정이 CAL 단계에서 기존 슬롯 보정을 이기지 못했고, 최종 두 후보는 기존 방법을 유지했다. 교체·optimizer 통합 준비는 FALSE다.

## 현재 실험 보존과 분리

원 CC4-v2.7의 24개 조합 및 등록된 M0/M1 비교를 중단·가속·가지치기 없이 완료했다. CPU/GPU, n_jobs, 정의, 날짜, 후보, 보정, May 규칙을 실행 중 변경하지 않았다. 5,733개 신규 일별 학습 기록과 275,184개 예측 행을 검증하고 최종 검토와 5,859개 파일 명세를 동결한 다음에만 이 후속 연구를 시작했다. 이전 결과는 [원 최종 검토](../cc4_v27_target_feature_sharpness/FINAL_REVIEW_KO.md)에 보존했다.

T0의 수명량을 제출 시간에 집중하는 방식은 TRAIN CV 3.89, 상위1% 질량 32.12%였고 T2는 1.12, 4.90%였다. 발행 후 자정 전 제출은 D일 미지 실행량의 6.383%를 차지했다. 같은 D일 제출 모집단 수명량의 54.33%는 D일 뒤에 실행됐다. 이 운영상 매핑 문제와 확률적 Q90 보정 문제는 별개다. 원 DEV의 raw 24개 조합 모두 명목 88~92% 밴드에 실패했다.

## 백엔드 벤치마크

2024-09-15/10-15의 T2F0·T3F2 × M0/M1을 같은 데이터·성숙 규칙·가중치로 실행했다. 백엔드별 8개 작업, 40개 Q50/Q90 booster다. CPU는 각각 n_jobs=1을 유지했다. LightGBM 4.6.0, Python3.11.7, CPU 10코어/16스레드, RAM 약32GB, NVIDIA RTX4060 Laptop 8GB 환경이다. GPU는 설치된 device_type=gpu, double precision 요청을 사용했고 라이브러리를 재빌드하지 않았다. 별도 verbose 확인 로그가 NVIDIA 장치 사용과 GPU 비결정성 경고를 보여준다.

| backend | total_wall_seconds | mean_fit_seconds | P95_fit_seconds | mean_CPU_utilization_percent | mean_GPU_utilization_percent | peak_RAM_MiB | peak_VRAM_MiB | max_prediction_abs_diff | max_metric_abs_diff | prediction_equivalence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CPU_SINGLE | 35.481 | 0.87239 | 3.1447 | 9.7623 | 0 | 195.37 | 789 | 0 | 0 | True |
| CPU_MULTIPROCESS | 14.054 | 0.88056 | 3.219 | 21.729 | 0 | 912.35 | 789 | 0 | 0 | True |
| GPU | 70.497 | 1.7476 | 3.2371 | 13.716 | 30.142 | 390.87 | 911 | 63.754 | 2.0897 | False |

선택은 CPU_MULTIPROCESS, workers=4, fit별 n_jobs=1이다. 동등성 한계는 prediction atol/rtol 1e-8, 지표 절대 차이1e-6으로 측정 전에 고정했다. GPU 최대 예측 차이는 63.75여서 탈락했다. CPU/GPU 사용률과 VRAM은 시스템·장치 전체 관측치이며, VRAM 약789MiB의 기존 점유도 포함한다. RAM은 프로세스 트리 RSS 합으로 공유 페이지 중복 가능성이 있다. 0.5초 간격 표본이며 단일 순서 측정이라 열 상태·캐시·실행간 분산을 분리한 일반적 성능 주장은 아니다. 그래도 이 동일 배치에서 CPU4가 더 빠르고 정확히 재현됐다는 관측은 유효하다.

## Stage A: 구조 축소

T0F0는 역사적 도착량 기준으로만 남겼다. 운영 정합 후보 T2F0와 T3F2의 M0/M1을 DEV/CAL에서 비교하고 DEV로 구조를 선택했다. 두 후보 모두 M0를 유지했으며 M1은 pinball·Q50 MAE·보정 오차가 모두 더 나빴다. 96개 개별 모델이나 TFT/DeepAR 검색을 수행하지 않았다.

| arm | model | Q90_coverage | Q90_pinball | Q50_MAE | requirement_ratio |
| --- | --- | --- | --- | --- | --- |
| T2_F0 | M0 | 0.75 | 34.716 | 80.317 | 1.4716 |
| T2_F0 | M1 | 0.66739 | 39.863 | 84.177 | 1.2587 |
| T3_F2 | M0 | 0.70384 | 37.116 | 82.67 | 1.2445 |
| T3_F2 | M1 | 0.65661 | 38.587 | 84.773 | 1.1673 |
| T0_F0 | M0 | 0.81394 | 161.1 | 229.54 | 1.0985 |

## Stage B: 보정 축소

RAW, 원 슬롯별 보정, 6시간 리드 그룹 가산 잔차 보정, 그룹별 국소 스케일 잔차 보정만 비교했다. 국소 스케일은 max(Q90−Q50, 0.05×TRAIN 평균)으로 정의하고 미래 관측을 사용하지 않았다. 새 방법의 DEV/CAL 잔차는 가장 최근의 성숙한 26일을 사용하며 20일 미만 warmup은 raw로 남겼다. CAL에서 먼저 88~92% 밴드, 그다음 pinball과 요구량 비율을 적용했다.

| arm | method | Q90_coverage | Q90_pinball | requirement_ratio | excess_reserve_proxy | positive_coverage | burst_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T2_F0 | RAW | 0.77404 | 32.813 | 1.4923 | 0.67782 | 0.77368 | 0 |
| T2_F0 | LEGACY_SLOT | 0.90545 | 26.041 | 2.454 | 1.4949 | 0.9053 | 0.1875 |
| T2_F0 | HORIZON_ADD | 0.91186 | 28.209 | 2.704 | 1.7354 | 0.91172 | 0.25 |
| T2_F0 | HORIZON_LOCAL_SCALE | 0.95353 | 38.155 | 3.4802 | 2.5052 | 0.95345 | 0.70833 |
| T3_F2 | RAW | 0.73197 | 40.121 | 1.3003 | 0.55731 | 0.73024 | 0 |
| T3_F2 | LEGACY_SLOT | 0.88702 | 27.398 | 2.3814 | 1.4393 | 0.88629 | 0.078788 |
| T3_F2 | HORIZON_ADD | 0.89103 | 31.096 | 2.5924 | 1.6556 | 0.89032 | 0.13939 |
| T3_F2 | HORIZON_LOCAL_SCALE | 0.89944 | 55.36 | 4.2121 | 3.2869 | 0.89879 | 0.41818 |

T2F0는 기존 슬롯 보정 coverage90.54%, pinball26.04, 비율2.45가 선택됐다. 그룹 가산은91.19%지만 손실28.21·비율2.70으로 더 나빴고, 국소 스케일은95.35%·비율3.48로 과도했다. T3F2는 기존88.70%·손실27.40·비율2.38이 선택됐다. 국소 스케일은89.94%로 명목에 가깝지만 손실55.36·비율4.21로 악화됐다. coverage만 최적화하지 않은 결과다.

이 비교에서 원 슬롯 방법의 DEV/CAL 잔차 은행은 기존 expanding 방식이고 새 방법은 최근26일이다. 따라서 그룹화만의 순수 인과 효과를 분리한 실험은 아니다. 등록된 전체 보정 전략의 성능 비교이며, 모든 horizon-aware 또는 conformal 방식이 불가능하다는 결론은 내리지 않는다. 그룹 내 상관된 슬롯을 풀링했으므로 분포 독립적인 conformal coverage 보장을 주장하지 않는다. 국소 스케일은 예측 폭에 적응하지만 평가 잔차를 온라인 갱신하는 방식은 아니다.

## Stage C: 동결한 최종 후보만 평가

두 후보 모두 M0+LEGACY_SLOT로 동결됐다. 타깃·피처·모델·파라미터·날짜·가중치가 원 실험과 같으므로 546개 일별 모델 기록을 재사용했다. 그중 평가 날짜의 기록은364개이며, 새 전체 기간 학습은0회다. 캐시 해시, 학습 날짜, 가중치, 성숙 시각과 Q50/Q90을 검증했다. 이는 일별 refit을 생략한 정적 모델 평가가 아니라 이미 수행된 동일한 인과적 일별 refit의 정확한 재사용이다. 탈락한 새 보정 전략은 전체 OOS에 확장하지 않았다.

| arm | role | method | Q90_coverage | Q90_pinball | requirement_ratio | excess_reserve_proxy | positive_coverage | burst_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T2_F0 | EXPOSED_EVALUATION | LEGACY_SLOT | 0.94223 | 26.245 | 2.5107 | 1.5372 | 0.93659 | 0.47967 |
| T2_F0 | OOS_EXTENSION | LEGACY_SLOT | 0.95172 | 22.825 | 2.0092 | 1.0181 | 0.95064 | 0.69536 |
| T2_F0 | MAY_HISTORICAL | LEGACY_SLOT | 0.98656 | 25.172 | 2.739 | 1.7405 | 0.98656 | 0.97222 |
| T3_F2 | EXPOSED_EVALUATION | LEGACY_SLOT | 0.9665 | 28.055 | 2.6916 | 1.7123 | 0.963 | 0.60253 |
| T3_F2 | OOS_EXTENSION | LEGACY_SLOT | 0.94692 | 24.454 | 2.0336 | 1.0479 | 0.94569 | 0.68571 |
| T3_F2 | MAY_HISTORICAL | LEGACY_SLOT | 0.99429 | 27.157 | 2.8822 | 1.8833 | 0.99429 | 1 |

기존 평가/확장의 최종 coverage는 T2F0 94.22%/95.17%, T3F2 96.65%/94.69%로 모두 상한92%를 넘었다. 요구량 비율도 각각2.51/2.01, 2.69/2.03이다. CAL의 명목 근접이 다음 기간까지 유지되지 않았다. 최종 예측은 기존 슬롯 보정과 같아 그 대비 차이·CI는 정확히0이다. 따라서 새 방법의 개선으로 보고하지 않는다.

리드 그룹별 최종 coverage 범위:

| arm | role | min | max |
| --- | --- | --- | --- |
| T2_F0 | EXPOSED_EVALUATION | 0.91288 | 0.97538 |
| T2_F0 | MAY_HISTORICAL | 0.97312 | 1 |
| T2_F0 | OOS_EXTENSION | 0.93915 | 0.97884 |
| T3_F2 | EXPOSED_EVALUATION | 0.94744 | 0.98438 |
| T3_F2 | MAY_HISTORICAL | 0.97715 | 1 |
| T3_F2 | OOS_EXTENSION | 0.92262 | 0.97156 |

raw 대비 Q90 손실 차이의 7일 블록95% CI:

| arm | role | delta | CI_low | CI_high |
| --- | --- | --- | --- | --- |
| T2_F0 | EXPOSED_EVALUATION | -6.726 | -15.73 | 2.5967 |
| T2_F0 | OOS_EXTENSION | -14.965 | -32.846 | 0.59696 |
| T2_F0 | MAY_HISTORICAL | -2.4919 | -11.447 | 7.2939 |
| T3_F2 | EXPOSED_EVALUATION | -7.1162 | -17.752 | 3.2037 |
| T3_F2 | OOS_EXTENSION | -19.8 | -36.451 | -5.4108 |
| T3_F2 | MAY_HISTORICAL | 0.43152 | -10.007 | 10.819 |

이 raw 대비 보정 효과는 이미 원 연구의 효과이며 후속 신기술의 성과가 아니다. 원 슬롯 대비 개선 CI는0이다. 전체 paired1일/7일 2,000회 CI, 양수·0·버스트·리드 그룹 지표는 개별 CSV에 보존했다. 0 라벨·어려운 날짜를 유지했고 NaN CI는 일부 resample에서 조건부 분모가0이 되는 경우 미정의로 남겼다.

## 결론과 제한

계산 가속은 확인됐지만, 이번에 시험한 보정 전략으로 명목 Q90와 낮은 예비량을 동시에 개선했다는 다기간 근거는 없다. 운영 점유량에 맞는 T2F0·T3F2는 연구 후보로 유지한다. 운영 교체를 승인하거나 V42·optimizer·MESS·IEEE/OpenDSS를 수정·실행하지 않았다. May는 역사적 진단으로만 사용했다. 모든 평가 기간은 이미 노출돼 있어 독립 확인시험이 아니며, 잔존 오차의 본질적 불가약성을 증명한 것도 아니다.

## 최종 계산 플래그

| flag | value |
| --- | --- |
| CURRENT_V27_RUN_COMPLETED_UNCHANGED | True |
| CURRENT_V27_DEVICE_CHANGED_MIDRUN | False |
| CPU_MULTIPROCESS_BENCHMARKED | True |
| GPU_LIGHTGBM_BENCHMARKED | True |
| SELECTED_BACKEND | CPU_MULTIPROCESS |
| PREDICTION_EQUIVALENCE_VERIFIED | True |
| NEXT_STAGE_SEARCH_SPACE_REDUCED | True |
| FULL_DAILY_REFIT_LIMITED_TO_FINALISTS | True |

재현과 캐시 범위는 README.md, backend 선택은 COMPUTE_BACKEND_SELECTION.json, 동결 후보는 FINALIST_FREEZE.json, 현재 증거 보존은 SOURCE_MANIFEST.json과 NEXT_STAGE_VALIDATION.json에서 확인할 수 있다.
