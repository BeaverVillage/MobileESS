# May01 B1 R1-FLEX30-C1 Actual96 / Fresh96

Golden003 Planning 재계산 0회. B1 C1 Actual96 1회 완료. 물리 실행·UID/GPU/P/Q 독립 검산·Fresh96 PASS.
**Known 허용창 계약은 414 UID FAIL이며 서비스 동등성은 NOT_CERTIFIED이다.** 허용창을 변경하지 않았다.

## 실제 서비스

UID 수는 D-1 18:00 AEST부터 May01 종료까지 30시간 도착 코호트이며, Compute GPUh는 May01 24시간 적분이다.

| 구분 | 전체 | START | COMPLETED | Carryout | May01 Compute GPUh | 30h Compute GPUh |
|---|---:|---:|---:|---:|---:|---:|
| Known | 1649 | 1023 | 825 | 824 | 7893.357222222 | 10548.115000000 |
| Unknown | 849 | 800 | 751 | 98 | 5146.409166667 | 5224.253333333 |

의도적 부담 예산 초과 0 UID. 실제 latest-start 초과 1074 UID(START한 UID 402). 명시적 완료 Deadline 위반 0 UID.
Latest-start 초과는 용량 대기·미실행까지 포함한 연구 허용창 지표이며 고객 Source SLA 인증을 의미하지 않는다.

## Unknown Pre-site

| 지표 | UID 수 또는 후보 횟수 |
|---|---:|
| R1 적격 Unknown | 845 |
| R1 참여 Unknown | 251 |
| 기본 사이트 PENDING 지정 | 849 |
| Signed Sensitivity 평가 UID | 676 |
| 참여자 중 Signed Sensitivity 평가 UID | 212 |
| 다른 호환 사이트 후보 횟수(권한 차단 포함) | 67062 |
| 대체 사이트 권한 통과 후보 횟수 | 2365 |
| 대체 사이트 민감도 평가 횟수 | 1652 |
| 대체 사이트 민감도 평가 UID | 212 |
| Pre-site 선택 UID | 185 |
| 실제 Pre-site 후 START UID | 185 |
| 관측 Overrun 대기 후 Pre-site START UID | 3 |

185건의 선택 근거는 기본 사이트 NO_CAPACITY 88건, 기본 사이트도 Signed 점수가 있는 경우 97건이다. 후자에서 예측 최대 부하율 감소 0건, 예측 loading-hours 감소 97건이다. 이는 실제 일 최대 부하율 감소 인증이 아니다.

모든 변경은 실제 도착 이후 PENDING에서 이루어졌고, 실제 RUNNING 이벤트와 선택 시각·사이트를 UID별로 교차검증했다. Running Migration과 Unknown의 의도적 Time-shifting은 0건이다.
참여 권한은 R1_ASSUMED이다. Source 인증으로 승격하지 않는다. 비참여자와 명시적 Source 금지 대상은 대체 사이트가 차단된다. C0_BASIC_SITE_ONLY가 C1 후보에 적용된 건수는 0이다.
후보 Signed 점수는 원본 부호 있는 응답식을 사용한다. 정렬된 후보를 Current AC로 검사해 첫 안전 후보만 START한다. 선택되지 않아 AC를 실행하지 않은 후보의 물리 PASS를 주장하지 않는다.
D00 이전에는 원본 Signed 응답의 지원 범위가 없어 대체 사이트를 PREFIX_SIGNED_RESPONSE_UNAVAILABLE로 차단한다. 이후 실제 관측 이벤트에서 다시 평가한다.

실제 이동 UID 전체와 기본/선택 사이트의 평가값: [Pre-site UID CSV](V43_B1_R1_FLEX30_C1_PRESITE_UID.csv).

실제로 관측한 Overrun UID: {'Known': 764, 'Unknown': 410}. 관측 Overrun이 있는 사이트의 용량 대기로 QUEUE된 뒤 Pre-site START한 건수를 위 표에서 따로 집계했다.

## Known 허용창 및 대기

Golden003 selected_jobs, PR189 Original FULL 로더의 allowed_starts 바인딩, WINDOWS.json, OriginalKnownWindows.issue() 영수증 및 Actual _known_decision()을 UID별로 대조했다.
18:00 기준 slot→초 변환은 동일하며 Adapter 해석 오류가 아니다. 예: UID 8632559는 시작 슬롯 0만 허용하지만 Golden003 선택은 슬롯 2이다. Golden003의 수치 인증을 실행 권한 인증으로 사용하지 않는다.
계약 불일치 414건 중 이번에도 미실행 414건. 나머지 미실행 Known 212건의 마지막 사유: {'NO_CAPACITY': 187, 'PHYSICAL_CAPACITY_RUNNING_RETAINED': 25}.
유효 Planning 명령을 기다렸다가 실제 허용 시작시각을 넘겨 START한 Known은 172 UID이며 별도 Actual QoS 초과로 포함했다. 동결 명령과 허용창은 수정하지 않았다.
[414개 계약 FAIL UID](V43_B1_KNOWN_WINDOW_FAIL_UID.csv) · [나머지 미실행 Known UID](V43_B1_C1_OTHER_KNOWN_UNSTARTED_UID.csv). 기존 C0의 나머지 165 UID별 용량 대기 이벤트도 Preflight 원장에 보존했다.

## 전력망

최대 선로·상 부하율 **69.492574104%**, line.l10 / 상 A. 발생 구간 시작 2025-05-01T06:45:00+09:00 KST(원본 축 2025-05-01T07:45:00+10:00 AEST, 15분 평균 Actual).
전압 범위 0.978216760–1.048959626 pu. 독립 Fresh96 수렴 96/96; 위반 {'voltage': 0, 'line_current': 0, 'transformer_current': 0, 'transformer_kVA': 0}.
C0(68.893996691%) 대비 +0.598577413%p, B0(71.818273624%) 대비 -2.325699519%p.
May01 Compute GPUh는 C1 13039.766388889, C0 12412.985555556, B0 18146.029166667이다. 처리량이 다르므로 부하율 차이를 동일 처리량 개선으로 해석하지 않는다.

## 성능

| 구간 | 초 |
|---|---:|
| Actual 입력 준비 | 9.786398 |
| Actual Event | 640.261047 |
| Fresh AC96(30h 연속 replay의 마지막 96) | 1.090934 |
| 본 Worker 전체 | 657.227221 |
| 최대 제어 Tick | 30.313193 |
| 별도 입력/계약 Preflight | 7.439056 |
| 한 번의 짧은 Canary 이벤트 실행 | 89.616883 |
| 독립 후처리 | 5.954835 |
| 측정 실행 구간 합계 | 760.237996 |

첫 Canary START부터 최종 독립 검산까지의 연속 Wall은 1032.748966초이다. 중간 기록 보완·입력 준비 시간까지 포함하며 개발 착수 시각을 의미하지 않는다.

세부 측정: {'reservation_seconds': 4.008800399933534, 'public_future_seconds': 10.378734499929124, 'sensitivity_seconds': 64.2790566999538, 'current_AC_seconds': 502.8545434997286, 'service_cache_hits': 2916526, 'service_cache_misses': 11214, 'residual_recomputations': 78}. Current AC 요청 6588회, cache miss 1722회, 실제 probe 합계 458.687199초.
reservation_seconds는 Unknown 후보 feasibility, public_future_seconds는 공개 예약·잔여 수요 계산, sensitivity_seconds는 Signed 후보 점수, current_AC_seconds는 모든 Known/Unknown guard 호출이다. Probe 시간은 guard 시간과 겹치므로 더하지 않는다.
동일 상태 프로파일/코호트 보존식/구간 적분/수치 Hash를 재사용했다. 단일 GPU 예약은 원본 UID별 max-union과 동일한 interval sweep을 사용하고 원본과 625개 무작위 후보를 대조했다. 기존 인증 Current AC 소스와 캐시는 유지했고 현재 후보 측정을 생략하지 않았다.

Native 호출 0회 / Runtime 0초. Worker 1·Threads 1 및 6개 Heavy OS Lock을 준수했다. 40분 중단 한계 안에서 전체 Actual을 한 번만 수행했다.

## 검증·범위

집중 테스트 45개 PASS. 실제 Canary 25 Tick 1회 후, 같은 관측 원장에서 D00 이전 공개 상태를 복원하여 대체 사이트 11개 점수를 검증했다(이벤트 궤적 재실행 0회). Overrun 대기→대체 사이트 START는 명명된 이벤트 fixture로 별도 검증했으며 실제 실험 건수와 구분한다.
Golden003 UB 0.6718471055537026 / 독립 LB 0.6715871456570585 / Gap 0.0386933%는 기존 인증을 보존한다. Phase I·Pricing·Integer Restoration·Native Optimize는 새로 실행하지 않았다.
CC4 Q50/Q90, 기존 AIDC 전기 C1 P/Q, 원본 IEEE123·7-RegControl을 유지했다. Unknown 제어 Variant C1은 전기 C1 계수와 다른 개념이다.
기존 C0/Golden003/B0/B2 원장과 분리된 Attempt를 사용했다. B2 종료 상태·소스·예산·원장, B0/B2 FCFS 경로를 이 변경에서 수정하지 않았다. May02–31과 Main Merge는 수행하지 않았다.
FORECAST_CAUSAL_AVAILABILITY=NOT_CERTIFIED, CAUSAL_PASS=False, 초기 RUNNING 44개 사이트 MODEL_ASSUMED 상태를 유지한다.
기존 공통 driver RESULT의 R1=NOT_EXECUTED_ASSUMED_SEPARATE는 Strict 공통 보고 필드가 남은 것이다. 이번 R1 실행의 근거는 새 CorrectivePolicy 영수증 및 독립 UID→실제 START 대조이며, 이 보고서의 R1_ASSUMED 상태가 권위 있는 해석이다.

## 원장

- Attempt: `D:\MobileESS_V43\runtime\may01_B1_R1_FLEX30_C1_actual96_attempt001`
- 독립 보고: `D:\MobileESS_V43\runtime\may01_B1_R1_FLEX30_C1_actual96_attempt001\INDEPENDENT_C1_REPORT.json`
- 후보별 원장: `D:\MobileESS_V43\runtime\may01_B1_R1_FLEX30_C1_actual96_attempt001\CORRECTIVE_POLICY_RECEIPTS.json`
- Fresh96: `D:\MobileESS_V43\runtime\may01_B1_R1_FLEX30_C1_actual96_attempt001\C1\FRESH_ORIGINAL7_AC.json`
- Known 계약 원장: `D:\MobileESS_V43\runtime\may01_B1_R1_FLEX30_C1_preflight_attempt002\KNOWN_WINDOW_AUDIT.json`
- 실제 Adapter 영수증 교차검증: `D:\MobileESS_V43\runtime\may01_B1_R1_FLEX30_C1_preflight_attempt002\CANARY_KNOWN_WINDOW_ADAPTER_CROSSCHECK.json`

기계 판독 요약과 SHA 바인딩: [RESULT JSON](V43_B1_R1_FLEX30_C1_RESULT.json).
