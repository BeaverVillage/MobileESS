FINAL CLASSIFICATION: V40S4_PROXY_BODY_RUNTIME_INSUFFICIENT

SELECTED TRACK: NONE

SELECTED u: NONE

SELECTED BODY MODEL: NONE

SELECTED TAIL CLASSIFIER: NONE

SELECTED eta: NONE

SELECTED ROBUST POLICY: NONE

PROXY ASSUMPTION: D1_SCHEDULER_REQUEST_STATE_PROXY_V1

HISTORICAL D-1 SNAPSHOT VERIFIED: NO / UNVERIFIED

BODY SAFETY: FAIL

TAIL DETECTION: FAIL / NO CAL-ELIGIBLE ETA

HYBRID SAFETY: N/A / NOT ELIGIBLE

OPTIMIZER INTEGRATION: NO

PRODUCTION READY: NO

**1. 정확한 Git lineage**

S3 시작 PR27: `a2a21c904535125c66668a294f91d73a66f5d4a7` → S3 scientific: `836dfa1008c6810d077582892745b1892210c029` → S3 receipt / S4 base: `bfeb9c3312b397fdd15a00dfc9eac37dd4b2b6aa`.

조회 시 live PR27: `a2a21c904535125c66668a294f91d73a66f5d4a7`; metadata만 조회했고 merge하지 않았다. Branch: `codex/v40s4-request-state-proxy-runtime-risk`. Worktree: `C:\codex_mobileess_workspace\MobileESS_v40s4_request_state_proxy_runtime_risk`.

S4 사전등록 commit: `81e35dcc3de21f9004a18d97d50e73c008488ee7`; model/NONE 선택 freeze: `46b5f60d3461ecc046819a71f550a934c71054d1`. 새 fit은 사전등록 뒤, exposed scoring은 선택 freeze 뒤에 수행했다.

**2. S3 보존**

S3 판정 `V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT`, 선택값 전부 NONE, integration NO를 유지했다. S3 source/artifact 109개는 원본 worktree와 S4 복제본에서 byte identity PASS. S3 strict-provenance 결론을 proxy track으로 다시 이름 붙이지 않았다.

**3. Assumption contract**

`D1_SCHEDULER_REQUEST_STATE_PROXY_V1`; `REQUEST_STATE_ROLE=ASSUMPTION_BASED_SCHEDULER_VISIBLE_PROXY`. historical D1 snapshot과 original submission provenance는 모두 UNVERIFIED. operational availability만 FROZEN. 요청 변경 이력 UNOBSERVED, 변경 모델 OUT_OF_SCOPE. 변경 빈도=0이라고 주장하지 않는다. 논문 표현은 `ASSUMPTION-BASED TRACE-DRIVEN RUNTIME MODEL`. [V40S4_ASSUMPTION_BOUNDARY.md](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_ASSUMPTION_BOUNDARY.md>)

**4. Source population**

원본 73,504행 = positive 72,292 + zero 1,212; negative 0, timestamp missing 0, duplicate 0. Runtime은 정확히 end−start. Source SHA256 `fed0270c4e90362bc97b3583d92bfc6e00d6083297ee502b098e08896e086df9`. Zero는 identity audit에 보존하고 모든 모델에서 동일하게 제외했다. 성공/실패 terminal status는 없으므로 COMPLETED-only가 아니다. 기존 exposed terminal-service complete-case population이며 full cluster backlog, censoring 해소, raw rowgroup exclusion bias 해소를 주장하지 않는다.

**5. PENDING population**

10,883 job-issue / 7,603 unique jobs. `submit<=issue AND (start missing OR start>issue) AND end>issue`를 독립 재구성해 S3 ID·순서·label·split·feature와 일치함을 확인했다. start/end는 membership·target·label availability에만 사용했고 predictor에는 없다. RUNNING redesign=0.

**6. Split**

| 역할 | issue UTC 시작(포함) | issue UTC 끝(제외) | N | unique jobs | 최대 label end UTC |
| --- | --- | --- | --- | --- | --- |
| TRAIN | 2025-03-14T08:00Z | 2025-03-22T08:00Z | 1190 | 1160 | 2025-03-22T07:43:55+00:00 |
| DEVELOPMENT | 2025-03-22T08:00Z | 2025-04-01T08:00Z | 4346 | 2893 | 2025-03-31T00:00:45+00:00 |
| CALIBRATION | 2025-04-01T08:00Z | 2025-04-08T08:00Z | 2634 | 1738 | 2025-04-07T18:21:08+00:00 |
| EXPOSED_EVALUATION | 2025-04-08T08:00Z | 2025-04-24T00:00Z | 2713 | 1812 | 2025-04-23T23:52:58+00:00 |

D-1 18:00 fixed AEST=08:00 UTC. end_time은 각 단계 cutoff보다 엄격히 이전이다. TRAIN completion은 모든 이후 prediction issue보다 이전이다. 무작위 분할 없이 S3를 그대로 유지했다. 반복 job-issue는 같은 block 내에서 유지하고 block 간 동일 job 누출은 없다.

**7. Proxy feature inventory**

P: `requested_seconds, num_gpus_req, num_nodes_req, num_cores_req, requested_memory_mib, partition, qos, submit_hour, submit_dow`. P-W는 `requested_seconds`만 제거한 8개 필드. encoded columns는 P19/P-W17. GPU request는 두 track 모두 predictor이면서 모든 track의 사전 고정 평가 weight다. 실제 allocation으로 해석하지 않는다. Memory는 MiB로 확인했다. 별도 hardware request field는 없고 파생 hardware만 있어 제외했다. Partition은 요청 queue 의미로 유지했다.

**8. Missingness**

원본·PENDING·TRAIN/DEV/CAL/EVAL 모두 9개 feature의 nonmissing=100%, invalid=0. TRAIN median을 사전등록했고 log1p+missing indicator를 사용했다. Categorical TRAIN vocabulary 외 값은 UNKNOWN으로 처리했다.

| scope | feature | N | unique | unseen N | unseen values |
| --- | --- | --- | --- | --- | --- |
| SOURCE_ALL | partition | 73504 | 8 | 4983 | debug-gpu, debug-gpu-stdby, gpu-h100l, gpu-h100s, gpu-h100s-stdby |
| SOURCE_ALL | qos | 73504 | 3 | 1159 | high |
| PENDING_PANEL | partition | 10883 | 4 | 10 | gpu-h100l |
| PENDING_PANEL | qos | 10883 | 3 | 24 | high |
| DEVELOPMENT | partition | 4346 | 4 | 6 | gpu-h100l |
| DEVELOPMENT | qos | 4346 | 3 | 24 | high |
| CALIBRATION | partition | 2634 | 3 | 1 | gpu-h100l |
| EXPOSED_EVALUATION | partition | 2713 | 3 | 3 | gpu-h100l |

Zero·impossible·unique 수는 feature별 JSON에 모두 보존했다. Categorical impossible은 수치 불가능값을 정의할 수 없어 null이며 unseen과 구분했다. [V40S4_PROXY_FEATURE_MISSINGNESS_AUDIT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_PROXY_FEATURE_MISSINGNESS_AUDIT.json>)

**9. 제외 feature**

user/account/username/job name/application identity·job ID·actual start/end/runtime·K0·reference safe seconds·support counts는 새 predictor에서 제외했다. Derived hardware도 제외했다. TRAIN-only vocabulary/median이며 target encoding은 없다. Clock은 고정 raw hour/weekday를 사용했으며 post-outcome scaling/subset search는 하지 않았다.

**10. Actual/requested walltime forensic**

| scope | N | median | P90 | P95 | P99 | actual>request N | fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SOURCE_POSITIVE | 72292 | 0.015000 | 0.499073 | 0.815650 | 1.008333 | 2925 | 4.046% |
| PENDING_PANEL | 10883 | 0.091377 | 0.626083 | 0.798485 | 1.000787 | 309 | 2.839% |
| TRAIN | 1190 | 0.080171 | 0.291645 | 0.484208 | 0.623442 | 1 | 0.084% |
| DEVELOPMENT | 4346 | 0.051678 | 0.437307 | 0.601372 | 1.000021 | 85 | 1.956% |
| CALIBRATION | 2634 | 0.044722 | 0.787222 | 0.899623 | 1.000127 | 34 | 1.291% |
| EXPOSED_EVALUATION | 2713 | 0.290208 | 0.747222 | 1.000310 | 1.001204 | 189 | 6.966% |

Requested-walltime bins, GPU count, partition/QoS(N>=100)별 분포도 [V40S4_REQUEST_RUNTIME_RELATIONSHIP.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_REQUEST_RUNTIME_RELATIONSHIP.json>)에 기록했다.

**11. Actual > request**

Positive 원본 2,925/72,292=4.046%; PENDING 309/10,883=2.839%; exposed 189/2,713=6.966%. 해당 행을 그대로 유지했다. Walltime은 predictive metadata이며 hard upper bound가 아니다. 새 Q50/Q90를 walltime으로 cap하지 않았다.

**12. Track C reference**

S3의 submit_hour/submit_dow 두 feature 결과를 read-only로 비교했다. Retrain=NO, S3 eta 규칙과 판정은 그대로다. 동일 u/model/split에 대한 P/P-W minus C body delta를 [V40S4_TRACK_C_REFERENCE.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_TRACK_C_REFERENCE.json>)에 보존했다. S3 R1(RW)은 S4 R2에 대응하며 S4 R1은 새 threshold floor다. B0는 S3 current-recipe seconds를 재사용한 comparator이며 exact production Apr01 final-state equivalence를 주장하지 않는다.

| track | u | body | DEV coverage Δ(pp) | CAL coverage Δ(pp) | EVAL coverage Δ(pp) |
| --- | --- | --- | --- | --- | --- |
| P | 4 | B1 | -0.352 | -0.485 | -19.137 |
| P | 4 | B2 | 0.470 | -0.388 | -20.755 |
| P | 4 | B3 | 0.000 | 0.000 | 0.000 |
| P | 6 | B1 | 2.017 | 0.000 | -11.823 |
| P | 6 | B2 | 1.080 | 0.656 | -23.599 |
| P | 6 | B3 | 0.000 | 0.000 | 0.000 |
| P | 8 | B1 | 1.856 | 0.000 | -18.053 |
| P | 8 | B2 | 2.591 | 0.092 | -21.464 |
| P | 8 | B3 | 0.000 | 0.000 | 0.000 |
| P | 12 | B1 | 2.104 | 0.298 | -12.146 |
| P | 12 | B2 | 3.691 | 0.085 | -18.069 |
| P | 12 | B3 | 0.000 | 0.000 | 0.000 |
| P | 24 | B1 | 25.136 | 0.926 | 5.085 |
| P | 24 | B2 | 24.285 | 2.393 | 0.965 |
| P | 24 | B3 | 0.000 | 0.000 | 0.000 |
| PW | 4 | B1 | -0.352 | -0.485 | -19.137 |
| PW | 4 | B2 | 0.470 | -0.388 | -20.755 |
| PW | 4 | B3 | 0.000 | 0.000 | 0.000 |
| PW | 6 | B1 | 2.017 | 0.000 | -11.823 |
| PW | 6 | B2 | 1.080 | 0.656 | -23.599 |
| PW | 6 | B3 | 0.000 | 0.000 | 0.000 |
| PW | 8 | B1 | 1.856 | 0.000 | -18.053 |
| PW | 8 | B2 | 2.591 | 0.092 | -21.464 |
| PW | 8 | B3 | 0.000 | 0.000 | 0.000 |
| PW | 12 | B1 | 2.104 | 0.298 | -12.146 |
| PW | 12 | B2 | 3.725 | 0.170 | -15.919 |
| PW | 12 | B3 | 0.000 | 0.000 | 0.000 |
| PW | 24 | B1 | 25.136 | 0.926 | 5.085 |
| PW | 24 | B2 | 24.734 | 2.393 | 4.306 |
| PW | 24 | B3 | 0.000 | 0.000 | 0.000 |

**13. Track P body table**

B0는 reference only; B1=LGB quantile, B2=XGB quantile, B3=TRAIN-body empirical quantile. 모든 표는 oracle BODY `T<=u`의 조건부 평가이며 total hybrid 성능이 아니다.

**DEVELOPMENT**

| u(h) | 모델 | BODY N | Q90 coverage | GPU coverage | Q50 MAE(s) | Q90 MAE(s) | Q90 WAPE | GPU miss(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | B0 | 2554 | 99.491% | 97.489% | 29,415.150 | 34,901.888 | 12.098 | 230,625.770 |
| 4 | B1 | 2554 | 96.789% | 96.724% | 7,323.897 | 9,357.429 | 3.244 | 207,577.236 |
| 4 | B2 | 2554 | 96.789% | 96.768% | 7,261.245 | 9,392.907 | 3.256 | 197,099.633 |
| 4 | B3 | 2554 | 98.356% | 98.646% | 6,266.092 | 10,544.851 | 3.655 | 35,900.000 |
| 6 | B0 | 2777 | 99.028% | 95.727% | 29,066.758 | 34,496.780 | 8.514 | 863,647.292 |
| 6 | B1 | 2777 | 94.887% | 91.785% | 7,608.757 | 11,736.558 | 2.897 | 1,441,503.337 |
| 6 | B2 | 2777 | 93.338% | 90.927% | 7,447.738 | 11,287.668 | 2.786 | 1,277,118.477 |
| 6 | B3 | 2777 | 97.479% | 94.478% | 8,484.717 | 14,583.710 | 3.599 | 270,211.000 |
| 8 | B0 | 2856 | 98.599% | 94.900% | 28,622.544 | 34,005.850 | 7.349 | 1,430,008.592 |
| 8 | B1 | 2856 | 92.927% | 90.123% | 9,224.148 | 11,748.469 | 2.539 | 2,028,679.918 |
| 8 | B2 | 2856 | 92.927% | 90.787% | 9,102.550 | 11,884.609 | 2.568 | 1,697,403.387 |
| 8 | B3 | 2856 | 96.359% | 95.773% | 9,237.362 | 16,155.288 | 3.491 | 785,985.600 |
| 12 | B0 | 2899 | 97.930% | 93.630% | 28,391.313 | 33,694.513 | 6.671 | 2,682,125.569 |
| 12 | B1 | 2899 | 93.584% | 91.285% | 9,854.311 | 13,630.263 | 2.699 | 2,655,657.661 |
| 12 | B2 | 2899 | 94.101% | 92.855% | 8,957.825 | 14,497.363 | 2.870 | 2,156,548.951 |
| 12 | B3 | 2899 | 96.723% | 95.366% | 9,763.187 | 18,807.778 | 3.724 | 1,783,839.400 |
| 24 | B0 | 4229 | 67.463% | 74.495% | 22,860.221 | 24,778.745 | 1.122 | 11,225,275.714 |
| 24 | B1 | 4229 | 92.362% | 93.495% | 17,834.895 | 16,956.558 | 0.768 | 5,583,241.515 |
| 24 | B2 | 4229 | 91.866% | 91.987% | 19,173.025 | 16,692.789 | 0.756 | 5,762,580.762 |
| 24 | B3 | 4229 | 67.983% | 78.157% | 21,397.408 | 26,493.608 | 1.200 | 40,103,726.100 |

**CALIBRATION**

| u(h) | 모델 | BODY N | Q90 coverage | GPU coverage | Q50 MAE(s) | Q90 MAE(s) | Q90 WAPE | GPU miss(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | B0 | 2060 | 97.864% | 98.837% | 4,481.311 | 7,963.381 | 3.310 | 177,940.948 |
| 4 | B1 | 2060 | 98.786% | 99.361% | 6,947.669 | 10,429.605 | 4.335 | 29,164.778 |
| 4 | B2 | 2060 | 99.175% | 99.506% | 8,478.666 | 10,329.168 | 4.293 | 23,024.842 |
| 4 | B3 | 2060 | 99.320% | 99.709% | 6,284.268 | 11,008.174 | 4.575 | 5,805.000 |
| 6 | B0 | 2134 | 94.564% | 96.814% | 4,755.496 | 7,931.899 | 2.714 | 1,074,150.065 |
| 6 | B1 | 2134 | 97.657% | 98.578% | 9,282.208 | 13,745.888 | 4.703 | 241,204.036 |
| 6 | B2 | 2134 | 97.751% | 98.634% | 8,967.832 | 13,437.849 | 4.598 | 236,257.250 |
| 6 | B3 | 2134 | 98.922% | 99.346% | 8,990.245 | 15,668.408 | 5.361 | 55,494.000 |
| 8 | B0 | 2168 | 93.081% | 95.954% | 4,993.465 | 8,032.600 | 2.450 | 1,968,680.354 |
| 8 | B1 | 2168 | 95.895% | 97.561% | 10,604.025 | 14,691.274 | 4.482 | 860,685.402 |
| 8 | B2 | 2168 | 95.987% | 97.617% | 10,737.760 | 14,785.914 | 4.510 | 843,787.018 |
| 8 | B3 | 2168 | 98.155% | 98.943% | 9,811.649 | 17,413.185 | 5.312 | 309,359.000 |
| 12 | B0 | 2352 | 90.561% | 94.560% | 6,087.401 | 8,983.619 | 1.470 | 4,472,987.169 |
| 12 | B1 | 2352 | 90.009% | 95.530% | 12,931.683 | 17,846.220 | 2.920 | 4,641,368.961 |
| 12 | B2 | 2352 | 89.286% | 95.161% | 11,817.510 | 17,019.852 | 2.784 | 5,168,818.943 |
| 12 | B3 | 2352 | 90.986% | 96.255% | 11,534.489 | 19,942.855 | 3.263 | 3,565,812.600 |
| 24 | B0 | 2591 | 85.527% | 92.401% | 8,280.436 | 10,717.297 | 0.927 | 11,737,235.578 |
| 24 | B1 | 2591 | 90.004% | 94.987% | 13,650.188 | 27,743.107 | 2.400 | 5,530,924.908 |
| 24 | B2 | 2591 | 89.888% | 94.921% | 13,467.891 | 22,578.846 | 1.953 | 6,986,170.826 |
| 24 | B3 | 2591 | 84.408% | 93.879% | 15,668.082 | 26,561.612 | 2.298 | 10,883,161.400 |

**EXPOSED_EVALUATION**

| u(h) | 모델 | BODY N | Q90 coverage | GPU coverage | Q50 MAE(s) | Q90 MAE(s) | Q90 WAPE | GPU miss(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | B0 | 1484 | 61.860% | 65.788% | 4,684.795 | 4,750.906 | 0.731 | 2,524,208.295 |
| 4 | B1 | 1484 | 69.542% | 72.177% | 5,432.351 | 6,263.316 | 0.964 | 1,316,816.262 |
| 4 | B2 | 1484 | 66.442% | 69.665% | 6,897.913 | 6,395.925 | 0.984 | 1,856,089.099 |
| 4 | B3 | 1484 | 89.016% | 90.199% | 5,353.807 | 7,027.643 | 1.082 | 164,147.000 |
| 6 | B0 | 2123 | 43.570% | 47.545% | 7,137.116 | 5,536.214 | 0.571 | 10,734,544.625 |
| 6 | B1 | 2123 | 83.655% | 80.915% | 5,326.144 | 7,670.252 | 0.792 | 1,833,254.510 |
| 6 | B2 | 2123 | 65.520% | 68.207% | 7,163.109 | 7,286.229 | 0.752 | 4,428,516.234 |
| 6 | B3 | 2123 | 92.699% | 93.624% | 5,853.220 | 9,079.640 | 0.937 | 389,774.000 |
| 8 | B0 | 2404 | 38.727% | 42.871% | 8,614.380 | 6,569.170 | 0.584 | 17,384,444.442 |
| 8 | B1 | 2404 | 78.037% | 77.033% | 6,197.471 | 8,923.014 | 0.794 | 4,221,090.345 |
| 8 | B2 | 2404 | 71.880% | 71.863% | 8,223.718 | 8,417.996 | 0.749 | 5,012,045.140 |
| 8 | B3 | 2404 | 86.398% | 87.910% | 6,412.396 | 9,879.727 | 0.879 | 1,275,895.600 |
| 12 | B0 | 2651 | 35.119% | 40.015% | 9,827.749 | 7,453.525 | 0.555 | 23,241,102.856 |
| 12 | B1 | 2651 | 77.744% | 78.526% | 8,518.911 | 11,750.647 | 0.876 | 7,219,042.575 |
| 12 | B2 | 2651 | 71.860% | 75.687% | 9,835.878 | 10,874.470 | 0.810 | 8,099,440.996 |
| 12 | B3 | 2651 | 87.514% | 90.460% | 7,840.250 | 12,265.300 | 0.914 | 4,148,946.600 |
| 24 | B0 | 2694 | 34.558% | 39.186% | 10,273.888 | 7,848.551 | 0.562 | 26,938,746.552 |
| 24 | B1 | 2694 | 87.751% | 89.204% | 8,892.117 | 18,112.943 | 1.297 | 3,974,091.850 |
| 24 | B2 | 2694 | 84.039% | 86.877% | 10,682.607 | 15,320.953 | 1.097 | 5,248,396.564 |
| 24 | B3 | 2694 | 90.794% | 92.875% | 8,233.991 | 17,791.842 | 1.274 | 3,586,870.200 |

**14. Track P-W body table**

Walltime만 제거한 사전 고정 sensitivity track.

**DEVELOPMENT**

| u(h) | 모델 | BODY N | Q90 coverage | GPU coverage | Q50 MAE(s) | Q90 MAE(s) | Q90 WAPE | GPU miss(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | B0 | 2554 | 99.491% | 97.489% | 29,415.150 | 34,901.888 | 12.098 | 230,625.770 |
| 4 | B1 | 2554 | 96.789% | 96.724% | 7,323.897 | 9,357.429 | 3.244 | 207,577.236 |
| 4 | B2 | 2554 | 96.789% | 96.768% | 7,261.245 | 9,392.907 | 3.256 | 197,099.633 |
| 4 | B3 | 2554 | 98.356% | 98.646% | 6,266.092 | 10,544.851 | 3.655 | 35,900.000 |
| 6 | B0 | 2777 | 99.028% | 95.727% | 29,066.758 | 34,496.780 | 8.514 | 863,647.292 |
| 6 | B1 | 2777 | 94.887% | 91.785% | 7,608.757 | 11,736.558 | 2.897 | 1,441,503.337 |
| 6 | B2 | 2777 | 93.338% | 90.927% | 7,447.738 | 11,287.668 | 2.786 | 1,277,118.477 |
| 6 | B3 | 2777 | 97.479% | 94.478% | 8,484.717 | 14,583.710 | 3.599 | 270,211.000 |
| 8 | B0 | 2856 | 98.599% | 94.900% | 28,622.544 | 34,005.850 | 7.349 | 1,430,008.592 |
| 8 | B1 | 2856 | 92.927% | 90.123% | 9,224.148 | 11,748.469 | 2.539 | 2,028,679.918 |
| 8 | B2 | 2856 | 92.927% | 90.787% | 9,102.550 | 11,884.609 | 2.568 | 1,697,403.387 |
| 8 | B3 | 2856 | 96.359% | 95.773% | 9,237.362 | 16,155.288 | 3.491 | 785,985.600 |
| 12 | B0 | 2899 | 97.930% | 93.630% | 28,391.313 | 33,694.513 | 6.671 | 2,682,125.569 |
| 12 | B1 | 2899 | 93.584% | 91.285% | 9,854.311 | 13,630.263 | 2.699 | 2,655,657.661 |
| 12 | B2 | 2899 | 94.136% | 93.852% | 9,914.246 | 14,697.610 | 2.910 | 2,107,633.244 |
| 12 | B3 | 2899 | 96.723% | 95.366% | 9,763.187 | 18,807.778 | 3.724 | 1,783,839.400 |
| 24 | B0 | 4229 | 67.463% | 74.495% | 22,860.221 | 24,778.745 | 1.122 | 11,225,275.714 |
| 24 | B1 | 4229 | 92.362% | 93.495% | 17,834.895 | 16,956.558 | 0.768 | 5,583,241.515 |
| 24 | B2 | 4229 | 92.315% | 93.173% | 18,665.630 | 16,894.203 | 0.765 | 5,672,392.379 |
| 24 | B3 | 4229 | 67.983% | 78.157% | 21,397.408 | 26,493.608 | 1.200 | 40,103,726.100 |

**CALIBRATION**

| u(h) | 모델 | BODY N | Q90 coverage | GPU coverage | Q50 MAE(s) | Q90 MAE(s) | Q90 WAPE | GPU miss(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | B0 | 2060 | 97.864% | 98.837% | 4,481.311 | 7,963.381 | 3.310 | 177,940.948 |
| 4 | B1 | 2060 | 98.786% | 99.361% | 6,947.669 | 10,429.605 | 4.335 | 29,164.778 |
| 4 | B2 | 2060 | 99.175% | 99.506% | 8,478.666 | 10,329.168 | 4.293 | 23,024.842 |
| 4 | B3 | 2060 | 99.320% | 99.709% | 6,284.268 | 11,008.174 | 4.575 | 5,805.000 |
| 6 | B0 | 2134 | 94.564% | 96.814% | 4,755.496 | 7,931.899 | 2.714 | 1,074,150.065 |
| 6 | B1 | 2134 | 97.657% | 98.578% | 9,282.208 | 13,745.888 | 4.703 | 241,204.036 |
| 6 | B2 | 2134 | 97.751% | 98.634% | 8,967.832 | 13,437.849 | 4.598 | 236,257.250 |
| 6 | B3 | 2134 | 98.922% | 99.346% | 8,990.245 | 15,668.408 | 5.361 | 55,494.000 |
| 8 | B0 | 2168 | 93.081% | 95.954% | 4,993.465 | 8,032.600 | 2.450 | 1,968,680.354 |
| 8 | B1 | 2168 | 95.895% | 97.561% | 10,604.025 | 14,691.274 | 4.482 | 860,685.402 |
| 8 | B2 | 2168 | 95.987% | 97.617% | 10,737.760 | 14,785.914 | 4.510 | 843,787.018 |
| 8 | B3 | 2168 | 98.155% | 98.943% | 9,811.649 | 17,413.185 | 5.312 | 309,359.000 |
| 12 | B0 | 2352 | 90.561% | 94.560% | 6,087.401 | 8,983.619 | 1.470 | 4,472,987.169 |
| 12 | B1 | 2352 | 90.009% | 95.530% | 12,931.683 | 17,846.220 | 2.920 | 4,641,368.961 |
| 12 | B2 | 2352 | 89.371% | 95.216% | 12,837.153 | 17,407.913 | 2.848 | 5,008,617.891 |
| 12 | B3 | 2352 | 90.986% | 96.255% | 11,534.489 | 19,942.855 | 3.263 | 3,565,812.600 |
| 24 | B0 | 2591 | 85.527% | 92.401% | 8,280.436 | 10,717.297 | 0.927 | 11,737,235.578 |
| 24 | B1 | 2591 | 90.004% | 94.987% | 13,650.188 | 27,743.107 | 2.400 | 5,530,924.908 |
| 24 | B2 | 2591 | 89.888% | 94.921% | 14,007.508 | 23,365.263 | 2.021 | 6,665,398.238 |
| 24 | B3 | 2591 | 84.408% | 93.879% | 15,668.082 | 26,561.612 | 2.298 | 10,883,161.400 |

**EXPOSED_EVALUATION**

| u(h) | 모델 | BODY N | Q90 coverage | GPU coverage | Q50 MAE(s) | Q90 MAE(s) | Q90 WAPE | GPU miss(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | B0 | 1484 | 61.860% | 65.788% | 4,684.795 | 4,750.906 | 0.731 | 2,524,208.295 |
| 4 | B1 | 1484 | 69.542% | 72.177% | 5,432.351 | 6,263.316 | 0.964 | 1,316,816.262 |
| 4 | B2 | 1484 | 66.442% | 69.665% | 6,897.913 | 6,395.925 | 0.984 | 1,856,089.099 |
| 4 | B3 | 1484 | 89.016% | 90.199% | 5,353.807 | 7,027.643 | 1.082 | 164,147.000 |
| 6 | B0 | 2123 | 43.570% | 47.545% | 7,137.116 | 5,536.214 | 0.571 | 10,734,544.625 |
| 6 | B1 | 2123 | 83.655% | 80.915% | 5,326.144 | 7,670.252 | 0.792 | 1,833,254.510 |
| 6 | B2 | 2123 | 65.520% | 68.207% | 7,163.109 | 7,286.229 | 0.752 | 4,428,516.234 |
| 6 | B3 | 2123 | 92.699% | 93.624% | 5,853.220 | 9,079.640 | 0.937 | 389,774.000 |
| 8 | B0 | 2404 | 38.727% | 42.871% | 8,614.380 | 6,569.170 | 0.584 | 17,384,444.442 |
| 8 | B1 | 2404 | 78.037% | 77.033% | 6,197.471 | 8,923.014 | 0.794 | 4,221,090.345 |
| 8 | B2 | 2404 | 71.880% | 71.863% | 8,223.718 | 8,417.996 | 0.749 | 5,012,045.140 |
| 8 | B3 | 2404 | 86.398% | 87.910% | 6,412.396 | 9,879.727 | 0.879 | 1,275,895.600 |
| 12 | B0 | 2651 | 35.119% | 40.015% | 9,827.749 | 7,453.525 | 0.555 | 23,241,102.856 |
| 12 | B1 | 2651 | 77.744% | 78.526% | 8,518.911 | 11,750.647 | 0.876 | 7,219,042.575 |
| 12 | B2 | 2651 | 74.010% | 77.635% | 8,427.826 | 11,485.524 | 0.856 | 7,250,441.617 |
| 12 | B3 | 2651 | 87.514% | 90.460% | 7,840.250 | 12,265.300 | 0.914 | 4,148,946.600 |
| 24 | B0 | 2694 | 34.558% | 39.186% | 10,273.888 | 7,848.551 | 0.562 | 26,938,746.552 |
| 24 | B1 | 2694 | 87.751% | 89.204% | 8,892.117 | 18,112.943 | 1.297 | 3,974,091.850 |
| 24 | B2 | 2694 | 87.379% | 88.949% | 9,529.561 | 16,905.305 | 1.210 | 3,676,361.465 |
| 24 | B3 | 2694 | 90.794% | 92.875% | 8,233.991 | 17,791.842 | 1.274 | 3,586,870.200 |

**15. Body Q90/GPU safety**

DEV+CAL 모두에서 overall Q90 90–95%, GPU>=90%, major issue-day N>=100에서 coverage/GPU>=88%를 통과한 새 body/u 쌍은 0개다. >95%도 FAIL이며 >97.5%는 추가 warning이다. 예: P 12h B1의 실패 subgroup은 다음과 같다.

| split | group | N | coverage | GPU coverage | coverage gate | GPU gate |
| --- | --- | --- | --- | --- | --- | --- |
| DEVELOPMENT | 2025-03-22 | 652 | 88.650% | 86.217% | PASS | FAIL |
| DEVELOPMENT | 2025-03-25 | 223 | 73.094% | 73.094% | FAIL | FAIL |
| CALIBRATION | 2025-04-02 | 211 | 78.673% | 80.384% | FAIL | FAIL |
| CALIBRATION | 2025-04-03 | 525 | 75.238% | 83.201% | FAIL | FAIL |
| CALIBRATION | 2025-04-05 | 276 | 84.783% | 90.642% | FAIL | PASS |
| CALIBRATION | GPU_1 | 968 | 85.021% | 85.021% | FAIL | FAIL |

높은 pooled coverage만으로 일자별 실패를 무시하지 않았다. 이는 등록된 cohort/model family의 안전성 실패이지 모든 runtime 예측의 불가능성 증명은 아니다.

**16. Body MAE/WAPE/miss**

13–14 표에서 Q50 MAE와 Q90 duration MAE/WAPE를 분리했다. 전체 CSV에는 Q50 pinball/WAPE, log-MAE, positive residual seconds, GPU-weighted miss, completion-slot MAE와 temporal/GPU subgroup도 있다. Native Q90 coverage를 평가하며 scheduler metrics는 `ceil(seconds/900)`을 한 번 적용한다. [V40S4_TRACK_P_BODY_RESULTS.csv](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_TRACK_P_BODY_RESULTS.csv>) / [V40S4_TRACK_PW_BODY_RESULTS.csv](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_TRACK_PW_BODY_RESULTS.csv>)

**17. Track P classifier table**

C0=TRAIN base rate, C1=logistic, C2=LGB, C3=XGB. ROC/PR/Brier/ECE는 body model과 무관하므로 B1 행으로 중복을 제거했다. Eta feasibility는 모든 body별로 따로 계산했다.

**DEVELOPMENT**

| u(h) | 분류기 | N / tail N | ROC-AUC | PR-AUC(AP) | Brier | ECE | eta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | C0 | 4346 / 1792 | 0.500000 | 0.412333 | 0.245611 | 0.057415 | NONE |
| 4 | C1 | 4346 / 1792 | 0.904371 | 0.884427 | 0.118423 | 0.168677 | NONE |
| 4 | C2 | 4346 / 1792 | 0.754782 | 0.664339 | 0.232375 | 0.171127 | NONE |
| 4 | C3 | 4346 / 1792 | 0.629848 | 0.573399 | 0.213773 | 0.307164 | NONE |
| 6 | C0 | 4346 / 1569 | 0.500000 | 0.361022 | 0.251241 | 0.143375 | NONE |
| 6 | C1 | 4346 / 1569 | 0.909366 | 0.858677 | 0.135251 | 0.177730 | NONE |
| 6 | C2 | 4346 / 1569 | 0.760284 | 0.635999 | 0.174968 | 0.267307 | NONE |
| 6 | C3 | 4346 / 1569 | 0.790478 | 0.655846 | 0.176295 | 0.240590 | NONE |
| 8 | C0 | 4346 / 1490 | 0.500000 | 0.342844 | 0.262979 | 0.194104 | NONE |
| 8 | C1 | 4346 / 1490 | 0.941018 | 0.876973 | 0.135392 | 0.191168 | NONE |
| 8 | C2 | 4346 / 1490 | 0.958078 | 0.936005 | 0.079466 | 0.129078 | NONE |
| 8 | C3 | 4346 / 1490 | 0.948375 | 0.893969 | 0.128882 | 0.134630 | NONE |
| 12 | C0 | 4346 / 1447 | 0.500000 | 0.332950 | 0.274805 | 0.229588 | NONE |
| 12 | C1 | 4346 / 1447 | 0.950212 | 0.886974 | 0.120495 | 0.174966 | NONE |
| 12 | C2 | 4346 / 1447 | 0.971331 | 0.951292 | 0.060466 | 0.092830 | NONE |
| 12 | C3 | 4346 / 1447 | 0.865497 | 0.737177 | 0.137908 | 0.208965 | NONE |
| 24 | C0 | 4346 / 117 | 0.500000 | 0.026921 | 0.026424 | 0.015095 | NONE |
| 24 | C1 | 4346 / 117 | 0.474360 | 0.115782 | 0.028610 | 0.031899 | NONE |
| 24 | C2 | 4346 / 117 | 0.560610 | 0.112120 | 0.025955 | 0.023833 | NONE |
| 24 | C3 | 4346 / 117 | 0.765941 | 0.076270 | 0.025837 | 0.010415 | NONE |

**CALIBRATION**

| u(h) | 분류기 | N / tail N | ROC-AUC | PR-AUC(AP) | Brier | ECE | eta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | C0 | 2634 / 574 | 0.500000 | 0.217920 | 0.233848 | 0.251828 | NONE |
| 4 | C1 | 2634 / 574 | 0.713517 | 0.540107 | 0.148750 | 0.172215 | NONE |
| 4 | C2 | 2634 / 574 | 0.718605 | 0.481801 | 0.297090 | 0.371647 | NONE |
| 4 | C3 | 2634 / 574 | 0.570509 | 0.259973 | 0.296589 | 0.354757 | NONE |
| 6 | C0 | 2634 / 500 | 0.500000 | 0.189825 | 0.154566 | 0.027822 | NONE |
| 6 | C1 | 2634 / 500 | 0.777314 | 0.643527 | 0.108833 | 0.063942 | NONE |
| 6 | C2 | 2634 / 500 | 0.761616 | 0.449715 | 0.123281 | 0.089602 | NONE |
| 6 | C3 | 2634 / 500 | 0.655217 | 0.283503 | 0.150827 | 0.161932 | NONE |
| 8 | C0 | 2634 / 466 | 0.500000 | 0.176917 | 0.146412 | 0.028178 | NONE |
| 8 | C1 | 2634 / 466 | 0.819456 | 0.665409 | 0.103387 | 0.107351 | NONE |
| 8 | C2 | 2634 / 466 | 0.804078 | 0.658483 | 0.119787 | 0.141186 | NONE |
| 8 | C3 | 2634 / 466 | 0.818804 | 0.639044 | 0.112736 | 0.110630 | NONE |
| 12 | C0 | 2634 / 282 | 0.500000 | 0.107062 | 0.095613 | 0.003700 | NONE |
| 12 | C1 | 2634 / 282 | 0.788211 | 0.388601 | 0.089344 | 0.101301 | NONE |
| 12 | C2 | 2634 / 282 | 0.781480 | 0.309151 | 0.104156 | 0.110905 | NONE |
| 12 | C3 | 2634 / 282 | 0.817055 | 0.319975 | 0.082985 | 0.047865 | NONE |
| 24 | C0 | 2634 / 43 | 0.500000 | 0.016325 | 0.016719 | 0.025692 | NONE |
| 24 | C1 | 2634 / 43 | 0.196202 | 0.010662 | 0.034080 | 0.040635 | NONE |
| 24 | C2 | 2634 / 43 | 0.477933 | 0.016109 | 0.026589 | 0.057642 | NONE |
| 24 | C3 | 2634 / 43 | 0.544384 | 0.017905 | 0.016652 | 0.021381 | NONE |

**EXPOSED_EVALUATION**

| u(h) | 분류기 | N / tail N | ROC-AUC | PR-AUC(AP) | Brier | ECE | eta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | C0 | 2713 / 1229 | 0.500000 | 0.453004 | 0.248072 | 0.016744 | NONE |
| 4 | C1 | 2713 / 1229 | 0.379606 | 0.475349 | 0.356443 | 0.397176 | NONE |
| 4 | C2 | 2713 / 1229 | 0.512328 | 0.495788 | 0.263318 | 0.166470 | NONE |
| 4 | C3 | 2713 / 1229 | 0.351330 | 0.372012 | 0.327035 | 0.220633 | NONE |
| 6 | C0 | 2713 / 590 | 0.500000 | 0.217471 | 0.170178 | 0.000176 | NONE |
| 6 | C1 | 2713 / 590 | 0.620526 | 0.518402 | 0.148008 | 0.130987 | NONE |
| 6 | C2 | 2713 / 590 | 0.294950 | 0.172197 | 0.249578 | 0.291111 | NONE |
| 6 | C3 | 2713 / 590 | 0.487212 | 0.309523 | 0.194894 | 0.188013 | NONE |
| 8 | C0 | 2713 / 309 | 0.500000 | 0.113896 | 0.102138 | 0.034843 | NONE |
| 8 | C1 | 2713 / 309 | 0.841199 | 0.652298 | 0.057951 | 0.057098 | NONE |
| 8 | C2 | 2713 / 309 | 0.777202 | 0.538896 | 0.081575 | 0.113726 | NONE |
| 8 | C3 | 2713 / 309 | 0.841505 | 0.661571 | 0.067820 | 0.060508 | NONE |
| 12 | C0 | 2713 / 62 | 0.500000 | 0.022853 | 0.028812 | 0.080508 | NONE |
| 12 | C1 | 2713 / 62 | 0.686004 | 0.118892 | 0.058905 | 0.069871 | NONE |
| 12 | C2 | 2713 / 62 | 0.767805 | 0.054274 | 0.078896 | 0.105165 | NONE |
| 12 | C3 | 2713 / 62 | 0.766826 | 0.053693 | 0.037797 | 0.044180 | NONE |
| 24 | C0 | 2713 / 19 | 0.500000 | 0.007003 | 0.008180 | 0.035013 | NONE |
| 24 | C1 | 2713 / 19 | 0.038722 | 0.006386 | 0.009267 | 0.029509 | NONE |
| 24 | C2 | 2713 / 19 | 0.106748 | 0.009116 | 0.007279 | 0.002936 | NONE |
| 24 | C3 | 2713 / 19 | 0.282665 | 0.009572 | 0.007789 | 0.027030 | NONE |

**18. Track P-W classifier table**

**DEVELOPMENT**

| u(h) | 분류기 | N / tail N | ROC-AUC | PR-AUC(AP) | Brier | ECE | eta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | C0 | 4346 / 1792 | 0.500000 | 0.412333 | 0.245611 | 0.057415 | NONE |
| 4 | C1 | 4346 / 1792 | 0.802059 | 0.715712 | 0.153751 | 0.227134 | NONE |
| 4 | C2 | 4346 / 1792 | 0.754782 | 0.664339 | 0.232375 | 0.171127 | NONE |
| 4 | C3 | 4346 / 1792 | 0.629848 | 0.573399 | 0.213773 | 0.307164 | NONE |
| 6 | C0 | 4346 / 1569 | 0.500000 | 0.361022 | 0.251241 | 0.143375 | NONE |
| 6 | C1 | 4346 / 1569 | 0.895243 | 0.822593 | 0.142441 | 0.135919 | NONE |
| 6 | C2 | 4346 / 1569 | 0.760284 | 0.635999 | 0.174968 | 0.267307 | NONE |
| 6 | C3 | 4346 / 1569 | 0.790478 | 0.655846 | 0.176295 | 0.240590 | NONE |
| 8 | C0 | 4346 / 1490 | 0.500000 | 0.342844 | 0.262979 | 0.194104 | NONE |
| 8 | C1 | 4346 / 1490 | 0.929057 | 0.860332 | 0.136018 | 0.208731 | NONE |
| 8 | C2 | 4346 / 1490 | 0.958078 | 0.936005 | 0.079466 | 0.129078 | NONE |
| 8 | C3 | 4346 / 1490 | 0.948375 | 0.893969 | 0.128882 | 0.134630 | NONE |
| 12 | C0 | 4346 / 1447 | 0.500000 | 0.332950 | 0.274805 | 0.229588 | NONE |
| 12 | C1 | 4346 / 1447 | 0.941357 | 0.876237 | 0.116462 | 0.185245 | NONE |
| 12 | C2 | 4346 / 1447 | 0.971331 | 0.951292 | 0.060466 | 0.092830 | NONE |
| 12 | C3 | 4346 / 1447 | 0.865497 | 0.737177 | 0.137908 | 0.208965 | NONE |
| 24 | C0 | 4346 / 117 | 0.500000 | 0.026921 | 0.026424 | 0.015095 | NONE |
| 24 | C1 | 4346 / 117 | 0.460736 | 0.119677 | 0.025773 | 0.024086 | NONE |
| 24 | C2 | 4346 / 117 | 0.560610 | 0.112120 | 0.025955 | 0.023833 | NONE |
| 24 | C3 | 4346 / 117 | 0.765941 | 0.076270 | 0.025837 | 0.010415 | NONE |

**CALIBRATION**

| u(h) | 분류기 | N / tail N | ROC-AUC | PR-AUC(AP) | Brier | ECE | eta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | C0 | 2634 / 574 | 0.500000 | 0.217920 | 0.233848 | 0.251828 | NONE |
| 4 | C1 | 2634 / 574 | 0.598612 | 0.358667 | 0.288248 | 0.314135 | NONE |
| 4 | C2 | 2634 / 574 | 0.718605 | 0.481801 | 0.297090 | 0.371647 | NONE |
| 4 | C3 | 2634 / 574 | 0.570509 | 0.259973 | 0.296589 | 0.354757 | NONE |
| 6 | C0 | 2634 / 500 | 0.500000 | 0.189825 | 0.154566 | 0.027822 | NONE |
| 6 | C1 | 2634 / 500 | 0.594477 | 0.323438 | 0.226508 | 0.199213 | NONE |
| 6 | C2 | 2634 / 500 | 0.761616 | 0.449715 | 0.123281 | 0.089602 | NONE |
| 6 | C3 | 2634 / 500 | 0.655217 | 0.283503 | 0.150827 | 0.161932 | NONE |
| 8 | C0 | 2634 / 466 | 0.500000 | 0.176917 | 0.146412 | 0.028178 | NONE |
| 8 | C1 | 2634 / 466 | 0.634309 | 0.325502 | 0.189051 | 0.267420 | NONE |
| 8 | C2 | 2634 / 466 | 0.804078 | 0.658483 | 0.119787 | 0.141186 | NONE |
| 8 | C3 | 2634 / 466 | 0.818804 | 0.639044 | 0.112736 | 0.110630 | NONE |
| 12 | C0 | 2634 / 282 | 0.500000 | 0.107062 | 0.095613 | 0.003700 | NONE |
| 12 | C1 | 2634 / 282 | 0.716470 | 0.314856 | 0.110113 | 0.171602 | NONE |
| 12 | C2 | 2634 / 282 | 0.781480 | 0.309151 | 0.104156 | 0.110905 | NONE |
| 12 | C3 | 2634 / 282 | 0.817055 | 0.319975 | 0.082985 | 0.047865 | NONE |
| 24 | C0 | 2634 / 43 | 0.500000 | 0.016325 | 0.016719 | 0.025692 | NONE |
| 24 | C1 | 2634 / 43 | 0.195211 | 0.010313 | 0.031868 | 0.040103 | NONE |
| 24 | C2 | 2634 / 43 | 0.477933 | 0.016109 | 0.026589 | 0.057642 | NONE |
| 24 | C3 | 2634 / 43 | 0.544384 | 0.017905 | 0.016652 | 0.021381 | NONE |

**EXPOSED_EVALUATION**

| u(h) | 분류기 | N / tail N | ROC-AUC | PR-AUC(AP) | Brier | ECE | eta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | C0 | 2713 / 1229 | 0.500000 | 0.453004 | 0.248072 | 0.016744 | NONE |
| 4 | C1 | 2713 / 1229 | 0.321302 | 0.385427 | 0.335906 | 0.311347 | NONE |
| 4 | C2 | 2713 / 1229 | 0.512328 | 0.495788 | 0.263318 | 0.166470 | NONE |
| 4 | C3 | 2713 / 1229 | 0.351330 | 0.372012 | 0.327035 | 0.220633 | NONE |
| 6 | C0 | 2713 / 590 | 0.500000 | 0.217471 | 0.170178 | 0.000176 | NONE |
| 6 | C1 | 2713 / 590 | 0.647124 | 0.481556 | 0.164680 | 0.186667 | NONE |
| 6 | C2 | 2713 / 590 | 0.294950 | 0.172197 | 0.249578 | 0.291111 | NONE |
| 6 | C3 | 2713 / 590 | 0.487212 | 0.309523 | 0.194894 | 0.188013 | NONE |
| 8 | C0 | 2713 / 309 | 0.500000 | 0.113896 | 0.102138 | 0.034843 | NONE |
| 8 | C1 | 2713 / 309 | 0.800154 | 0.600981 | 0.067989 | 0.071988 | NONE |
| 8 | C2 | 2713 / 309 | 0.777202 | 0.538896 | 0.081575 | 0.113726 | NONE |
| 8 | C3 | 2713 / 309 | 0.841505 | 0.661571 | 0.067820 | 0.060508 | NONE |
| 12 | C0 | 2713 / 62 | 0.500000 | 0.022853 | 0.028812 | 0.080508 | NONE |
| 12 | C1 | 2713 / 62 | 0.572590 | 0.098211 | 0.048035 | 0.059881 | NONE |
| 12 | C2 | 2713 / 62 | 0.767805 | 0.054274 | 0.078896 | 0.105165 | NONE |
| 12 | C3 | 2713 / 62 | 0.766826 | 0.053693 | 0.037797 | 0.044180 | NONE |
| 24 | C0 | 2713 / 19 | 0.500000 | 0.007003 | 0.008180 | 0.035013 | NONE |
| 24 | C1 | 2713 / 19 | 0.047962 | 0.006399 | 0.008676 | 0.023290 | NONE |
| 24 | C2 | 2713 / 19 | 0.106748 | 0.009116 | 0.007279 | 0.002936 | NONE |
| 24 | C3 | 2713 / 19 | 0.282665 | 0.009572 | 0.007789 | 0.027030 | NONE |

**19. ROC/PR/ECE 해석**

PR-AUC는 average precision(AP), ECE는 동일 폭 10-bin N-weighted absolute calibration gap이다. S4에서는 ECE를 diagnostic으로 고정했다. Exposed P 8h C3의 ROC 0.841505 / AP 0.661571이 좋아도 CAL-eligible eta가 없으므로 승격하지 않는다. Exposed tail N은 u4/6/8/12/24에서 1,229/590/309/62/19이므로 12h/24h tail support<100을 명시한다.

**20. Recall / GPU recall**

선택된 eta가 없으므로 primary recall, precision, specificity, FNR/FPR, GPU recall/FNR는 null(N/A)이다. 0으로 대체하지 않았다. CAL saved predictions의 전체 eta feasibility를 별도 독립 brute-force test로 재검증했다. Selectivity를 제거한 사후 tradeoff 수치는 selected policy 성능이 아니다.

**21. Danger-mass capture**

정의: `sum(g*max(T−Q90_body,0)*flag) / sum(g*max(T−Q90_body,0))`. Body별로 CAL eta feasibility에 80% gate를 적용했다. 실제 primary capture는 eta NONE으로 N/A. 등록된 weighting은 requested GPU이며 measured GPU occupancy가 아니다.

**22. Flagged fraction / selectivity**

기본 cap=60%; true tail prevalence>60%이면 min(80%, prevalence+20pp). 아래는 CAL에서 세 safety target을 만족시키기 위해 필요한 최소 flag fraction을 사후 분해한 값이다. Eta를 바꾸거나 exposed에 적용하지 않았다.

| track | u | CAL tail N | support | cap | 필요 flag | recall | GPU recall | capture |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P | 4 | 574 | True | 60.000% | 100.000% | 100.000% | 100.000% | 100.000% |
| P | 6 | 500 | True | 60.000% | 100.000% | 100.000% | 100.000% | 100.000% |
| P | 8 | 466 | True | 60.000% | 89.332% | 95.064% | 92.868% | 95.297% |
| P | 12 | 282 | True | 60.000% | 99.051% | 95.745% | 97.156% | 94.862% |
| P | 24 | 43 | False | 60.000% | 99.582% | 95.349% | 98.734% | 98.219% |
| PW | 4 | 574 | True | 60.000% | 100.000% | 100.000% | 100.000% | 100.000% |
| PW | 6 | 500 | True | 60.000% | 100.000% | 100.000% | 100.000% | 100.000% |
| PW | 8 | 466 | True | 60.000% | 89.332% | 95.064% | 92.868% | 95.297% |
| PW | 12 | 282 | True | 60.000% | 99.051% | 95.745% | 97.156% | 94.862% |
| PW | 24 | 43 | False | 60.000% | 99.582% | 95.349% | 98.734% | 98.219% |

예: u8 B1+C2는 89.332%를 flag해야 해서 60% cap을 초과한다. 24h는 CAL tail N=43이라 support gate도 실패한다.

**23. Eta**

P/P-W × 5u × 3개 새 body × 4 classifiers의 CAL-eligible eta 수=0. Largest feasible eta 규칙을 유지했고 NONE을 .5/all-tail/all-body로 대체하지 않았다. DEV/EVAL에서 threshold를 다시 선택하지 않았다. [V40S4_ETA_SELECTION.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_ETA_SELECTION.json>)

**24. R0**

Flagged job에 current-recipe `reference_safe_sec`를 적용하는 등록 comparator. 유효 eta가 없으므로 data hybrid replay는 `NOT_EXECUTED_NO_CAL_ELIGIBLE_ETA`. Formula synthetic test PASS. [V40S4_R0_REPORT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_R0_REPORT.json>)

**25. R1**

Flagged job에 `max(reference_safe_sec,u_seconds)` 적용. S3의 RW policy와 구분되는 S4 threshold floor. Data hybrid replay N/A, formula test PASS. [V40S4_R1_REPORT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_R1_REPORT.json>)

**26. R2**

Flagged job에 recorded requested walltime을 적용하는 comparator. Guaranteed runtime bound가 아니다. Data hybrid replay N/A, formula test PASS. [V40S4_R2_REPORT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_R2_REPORT.json>)

**27. Hybrid overall coverage**

모든 candidate hybrid metric은 eta NONE에 따라 null이다. BODY+TAIL requested denominator(DEV 4,346/CAL 2,634/EVAL 2,713)를 보존했다. Below table은 전체 denominator의 별도 baseline comparator이며 S4 hybrid가 아니다.

| split | reference | coverage | GPU coverage | GPU miss(s) | overreserve GPU-h |
| --- | --- | --- | --- | --- | --- |
| CALIBRATION | current_recipe | 84.396% | 90.682% | 32,411,781.000 | 12,156.249 |
| CALIBRATION | RW | 98.709% | 98.087% | 241,373.000 | 147,606.025 |
| DEVELOPMENT | current_recipe | 66.475% | 71.896% | 47,450,218.000 | 45,747.639 |
| DEVELOPMENT | RW | 98.044% | 95.257% | 3,356.000 | 237,197.955 |
| EXPOSED_EVALUATION | current_recipe | 35.017% | 39.333% | 32,291,178.000 | 3,632.428 |
| EXPOSED_EVALUATION | RW | 93.034% | 92.883% | 6,881.000 | 52,207.568 |
| TRAIN | current_recipe | 89.664% | 92.464% | 1,863,187.000 | 16,316.799 |
| TRAIN | RW | 99.916% | 99.819% | 60.000 | 81,812.514 |

**28. Hybrid GPU coverage**

N/A / NOT ELIGIBLE. Mandatory >=90% gate를 충족했다고 주장하지 않는다. [V40S4_HYBRID_RESULTS.csv](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_HYBRID_RESULTS.csv>)

**29. Underprediction reduction**

Selected reduction=N/A. 등록된 조건은 current reference보다 GPU-positive miss가 엄격히 작아야 한다. Eta 없이 대체 duration을 만들어 감소율을 계산하지 않았다. [V40S4_GPU_WEIGHTED_UNDERPREDICTION.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_GPU_WEIGHTED_UNDERPREDICTION.json>)

**30. Overreservation ratio**

Selected ratio=N/A. 3.0× cap은 유지했고 완화하지 않았다. Reference가 0인 경우 smoothing 없이 candidate도 0을 요구한다. R2 coverage가 좋다는 이유로 cap을 무시한 승격은 없다. [V40S4_OVERRESERVATION_REPORT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_OVERRESERVATION_REPORT.json>)

**31. Selected policy**

Track/u/body/classifier/eta/robust policy 전부 NONE. Primary failure는 selection hierarchy의 body safety 단계다. Tail eta도 독립적으로 모두 부적격이다. Adapter proposal 12개 field만 명시했고 recommended_rows=[]; export/integration하지 않았다.

**32. Walltime dependence**

P와 P-W 모두 실패: `REQUEST_STATE_PROXY_INFORMATION_STILL_INSUFFICIENT`. 동일 u/model/split의 body coverage/GPU/MAE/WAPE/miss 및 classifier ROC/AP/Brier/ECE deltas를 보존했다. Recall/capture/hybrid deltas는 eta가 없어 null이다. B1과 tree classifiers는 P/P-W 결과가 동일하고 B2 12h/24h 및 logistic에서 차이가 있다. Walltime을 추가하면 항상 좋아진다고 주장하지 않는다. [V40S4_WALLTIME_DEPENDENCE_ANALYSIS.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_WALLTIME_DEPENDENCE_ANALYSIS.json>)

**33. Feature importance**

DEVELOPMENT only, original-field grouped gain, 고정 seed로 3회 permutation. LGB total gain, XGB total_gain. 동률은 dense rank. Exposed importance/SHAP feature selection=NO.

| u | tree model | alpha | wall gain rank | relative gain | permutation loss Δ |
| --- | --- | --- | --- | --- | --- |
| 4 | B1 | 0.5 | 6 | 0.000000 | 0.000000 |
| 4 | B1 | 0.9 | 6 | 0.000000 | 0.000000 |
| 4 | B2 | 0.5 | 6 | 0.000000 | 0.000000 |
| 4 | B2 | 0.9 | 7 | 0.000000 | 0.000000 |
| 4 | C2 | None | 7 | 0.000000 | 0.000000 |
| 4 | C3 | None | 7 | 0.000000 | 0.000000 |
| 6 | B1 | 0.5 | 7 | 0.000000 | 0.000000 |
| 6 | B1 | 0.9 | 6 | 0.000000 | 0.000000 |
| 6 | B2 | 0.5 | 7 | 0.000000 | 0.000000 |
| 6 | B2 | 0.9 | 7 | 0.000000 | 0.000000 |
| 6 | C2 | None | 7 | 0.000000 | 0.000000 |
| 6 | C3 | None | 6 | 0.000000 | 0.000000 |
| 8 | B1 | 0.5 | 6 | 0.000000 | 0.000000 |
| 8 | B1 | 0.9 | 7 | 0.000000 | 0.000000 |
| 8 | B2 | 0.5 | 7 | 0.000000 | 0.000000 |
| 8 | B2 | 0.9 | 7 | 0.000000 | 0.000000 |
| 8 | C2 | None | 7 | 0.000000 | 0.000000 |
| 8 | C3 | None | 7 | 0.000000 | 0.000000 |
| 12 | B1 | 0.5 | 7 | 0.000000 | 0.000000 |
| 12 | B1 | 0.9 | 7 | 0.000000 | 0.000000 |
| 12 | B2 | 0.5 | 7 | 0.005148 | 83.166342 |
| 12 | B2 | 0.9 | 6 | 0.010702 | 12.955683 |
| 12 | C2 | None | 8 | 0.000000 | 0.000000 |
| 12 | C3 | None | 6 | 0.000000 | 0.000000 |
| 24 | B1 | 0.5 | 6 | 0.000000 | 0.000000 |
| 24 | B1 | 0.9 | 7 | 0.000000 | 0.000000 |
| 24 | B2 | 0.5 | 5 | 0.017004 | 364.307102 |
| 24 | B2 | 0.9 | 7 | 0.001615 | 5.362137 |
| 24 | C2 | None | 8 | 0.000000 | 0.000000 |
| 24 | C3 | None | 4 | 0.000000 | 0.000000 |

Walltime gain은 모든 LGB model과 XGB classifier에서 0. XGB body 12h/24h의 상대 gain만 약0.16–1.70%였다. 이 제한된 TRAIN/모델의 결과이며 walltime이 일반적으로 쓸모없다는 결론은 아니다.

**34. ±10% proxy sensitivity**

Winner NONE에 대한 사전등록 고정 diagnostic anchor=P/P-W u4 B1 C2 R1을 사용했다. S0=1.0/S1=.9/S2=1.1, refit0/reselectionNO.

| track | scenario | max Q50 Δ(s) | max Q90 Δ(s) | max p Δ | flag Δ | hybrid |
| --- | --- | --- | --- | --- | --- | --- |
| P | S0 | 0.000 | 0.000 | 0.000 | N/A | N/A |
| P | S1 | 0.000 | 0.000 | 0.000 | N/A | N/A |
| P | S2 | 0.000 | 0.000 | 0.000 | N/A | N/A |
| PW | S0 | 0.000 | 0.000 | 0.000 | N/A | N/A |
| PW | S1 | 0.000 | 0.000 | 0.000 | N/A | N/A |
| PW | S2 | 0.000 | 0.000 | 0.000 | N/A | N/A |

Anchor의 출력 변화0을 runtime decision robustness 인증으로 해석하지 않는다. Eta가 없어 discrete flag/hybrid decision 자체가 없으며 ±10%는 관측된 변경 이력이 아니다.

**35. Exposed evaluation**

Model/NONE freeze commit 뒤에만 실행했다. Selection result를 바꾸지 않았다. 예: P/P-W 12h B1 Q90 coverage=77.744%, GPU=78.526%. B3의 일부 exposed pooled gate가 좋아도 DEV+CAL 실패를 지우거나 winner를 재선정하지 않았다. 추가 fit/prediction/retuning 없이 최종 보고한다.

**36. Bootstrap**

`NOT_EXECUTED_SAFETY_FAIL`; runs0, confidence interval=null. 실패 후 유리한 CI를 계산하지 않았다.

**37. Confirmation**

`TRUE_CONFIRMATORY_AVAILABLE=NO`. 이 평가도 이미 exposed된 자료이며 untouched confirmation이 아니다. Apr-24–30 shadow는 계속 SEALED, row reads0.

**38. May firewall**

Canonical fixed AEST(+10): `2025-05-01T00:00:00+10:00` = UTC `2025-04-30T14:00:00Z`. 사용 source의 더 엄격한 timestamp boundary는 `2025-04-24T00:00:00Z`. May runtime/status/outcome/fit/calibration/threshold/eta/selection/sensitivity scientific reads는 모두0. Git path/index metadata discovery는 NONZERO로 별도 공개했고 May total read=0이라고 주장하지 않았다. [V40S4_MAY_FIREWALL.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_MAY_FIREWALL.json>)

**39. Optimizer/Gurobi/OpenDSS calls**

모두0. Fresh0. Runtime 연구용 CPU model fit/prediction만 수행했다.

**40. Migration/WAN/terminal**

A0/A1/M1/MF, migration, RUNNING, WAN, Rack, terminal, event-trigger/local-repair/rolling-MPC 변경0. Future consumers `dayahead/v37/aidc_materializer.py`, `dayahead/v40a/initial.py`도 unchanged. Production q=5576.44921875s, PF=.95, Q control NO, electrical HOLD, B0–B3 electrical NO, FULL_MAY NO를 유지했다.

**41. Tests**

Pytest 105 PASS, failure/error/skip0. Independent eta feasibility, exact row/metric/slot checks, forbidden predictor invariance, TRAIN-only preprocessing, source/selection locks와 보호 범위를 검증했다. 최종 artifact presence와 clean Git는 scientific commit 뒤 별도 receipt 검증에 포함한다. [V40S4_TEST_REPORT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_TEST_REPORT.json>)

**42. Reproducibility**

Python3.11.7, numpy2.2.6, pandas2.2.3, sklearn1.6.1, LGB4.6.0, XGB3.2.0. CPU threads1/seed4003. Primary fits70 + independent repeats70; empirical body10/base-rate10. 70개 model pair의 TRAIN+DEV+CAL prediction이 byte-identical, max/mean difference=0.0. Repeat 중 더 좋은 결과를 고르지 않았다.

Measured model fit 합계 2.308949s; DEV/CAL inference 합계 0.913766s; exposed inference 합계 0.225397s. 데이터 준비/diagnostics/Git 작업을 포함한 전체 wall time이 아니다. 모델별 시간은 compute ledger에 기록했다. Benign LGB sklearn feature-name warnings는 stderr log에 보존했다.

**43. Protected scope**

S3 receipt에서 상속한 tracked Git entries 5,352개를 모두 유지했다. S3 tracked109개는 원본과 복제본 byte identity 검증. 변경은 S4 source/artifact/test 경로로만 한정한다. Final receipt에서 staged/untracked 포함 경로 검증과 Git blob↔working bytes를 다시 확인한다. [V40S4_PROTECTED_SCOPE_DIFF.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_PROTECTED_SCOPE_DIFF.json>)

**44. Scientific commit**

최종 scientific commit의 full SHA 및 owned-file SHA256 manifest는 [V40S4_FINAL_COMMIT_RECEIPT.json](<C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_FINAL_COMMIT_RECEIPT.json>)의 `scientific_commit`과 `owned_files_SHA256`에 기록한다. Self-reference를 만들지 않기 위해 이 보고서를 담는 commit SHA는 후속 receipt가 증명한다.

**45. Receipt commit**

Receipt commit은 `V40S4_FINAL_COMMIT_RECEIPT.json`을 최초 추가하는 후속 commit이다. Full SHA는 최종 응답과 `git log -1 --format=%H -- dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_FINAL_COMMIT_RECEIPT.json`으로 확인한다. Receipt를 commit한 다음 clean Git와 receipt Git blob identity를 다시 확인한다.

현재 입증된 strict provenance와 명시적 request-state proxy assumption을 구분한다. 등록된 feature/model family 안에서는 proxy 정보를 추가해도 안전하고 선택적인 runtime handling에 충분하지 않았다. 새 model family나 optimizer 변경으로 이 결과를 덮지 않는다.
