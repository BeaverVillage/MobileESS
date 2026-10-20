# V1_add — 독립 확장실험의 May01 Source Lineage 우선 감사

실험명/버전은 **V1_add**다. V44 r043은 동결 알고리즘·입력의 기준 출처다. V1_add는 별도 브랜치·worktree·runtime·산출물·실행 기록을 갖는 독립 실험이며, V44 Production 캠페인/버전/결과를 수정하거나 V1_add 결과와 합치지 않는다. 경로에 남아 있는 r043 표기는 출처 기준을 나타낸다.

현재 판정은 **INPUT_MAPPING_NOT_VERIFIED / B0_NOT_BUILT / INSUFFICIENT_EVIDENCE**다. Greensboro 최대 선로부하율과 민감도의 공식 결과는 없다. 최신 지시 이후 운영 AC와 최적화는 실행하지 않았다. 앞서 잘못된 전력 크기와 PV=0으로 계산한 AC 및 PCC 여유 결과는 별도 runtime의 `quarantine_before_input_correction`에 격리했고 판정에서 제외했다.

기준 Git 커밋은 `affc7226a519adbe072d7debbc3ae25ea71c3487`이다. 독립 worktree와 runtime만 사용했고 Production Worker·Source·원장·Native 예산·PID를 수정하지 않았다.

## 1. 실제 원본과 재귀 확인

May01 직접 입력/모델/교통 관련 **36개 receipt는 36개 모두 SHA 일치**다. 다른 날짜·연도를 May01 운영 입력으로 대체하지 않았다. 24 Prefix를 위한 원본 4월 말 raw 관측은 기존 r043 observer가 사용한 범위로만 유지했다.

재귀 명시적 receipt 감사는 8760개 JSON, 86262개 참조 edge를 처리했다. 중복 제거한 receipt는 37368개이며 10636개가 미확인이다. 따라서 **전체 ancestral lineage PASS를 선언하지 않는다**. 누락/다른 SHA 가능성이 있는 경로는 `SOURCE_LINEAGE_UNVERIFIED_UNIQUE.csv`, 모든 edge는 `SOURCE_LINEAGE_RECURSIVE.csv.gz`에 남겼다. 다른 날짜의 과거 실험 문서는 참조 파일의 SHA 확인과 May01 운영 입력 채택을 구분했다. bare path/semantic digest는 파일 SHA로 인증하지 않았다.

| 역할 | 실제 확인 경로 | 원본 SHA-256 | 상태 |
|---|---|---|---|
| native | `D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B1\2025-05-01\NATIVE_INPUT.json` | `365824518d8b3d380b6e2cc72a78d19d27ce8d39d304acdc8ffc5b5806b342fc` | PASS |
| windows | `D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B1\2025-05-01\WINDOWS.json` | `5aec44479490ea00c0532f87229850507623b3d365fcdfbd6b105208dc8317a8` | PASS |
| planning_input | `D:\MobileESS_V42\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\PLANNING_INPUT_BUNDLE.json` | `76abed1653a8a2eeea21d8cd808cb0d23f125472b7db2fc9b6848957236f0458` | PASS |
| actual_input | `D:\MobileESS_V42\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\ACTUAL_INPUT_BUNDLE.json` | `427f07f7b3f2617b434dc8b102a3c98e64d5cfd7a0d2dd224cb72f7aef327862` | PASS |
| provenance | `D:\MobileESS_V42\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\SOURCE_PROVENANCE.json` | `0374911663021904aa9e5d4b77bd1533946fa31a8b7debe4adb7103400efce96` | PASS |
| power_authority | `D:\MobileESS_V42\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\POWER_AUTHORITY.json` | `e873ac080c6c809c6dbe2ccc4baa886715dec0739b9f34a42f7c3b75f017e282` | PASS |
| R0_reference | `D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\frozen_artifacts\v41r3_may\inputs\2025-05-01\common_q90_v3\COMMON_B0_REFERENCE_JOBS.json` | `60a75be104f8df41a93ac14f50a9ddd8ce330e3bd0c12cce2aa4e23e4b202ddb` | PASS |
| route_table | `D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B1\2025-05-01\ROUTE_TABLE.json.gz` | `3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9` | PASS |
| electrical | `D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\frozen_artifacts\v41r4_may\e\20250501\V41_ELECTRICAL_CERTIFICATE.json` | `c6b649edc1b2b3e2f324b0e41f939e397bdfcb26b64fff2c7be56d3d27424d35` | PASS |
| runtime_provider | `D:\ChatGPT\Mobile ESS 2\v42_job_capability_pr\v42_final\runtime_bundle\INTEGRITY.json` | `de097089bee9484954d300951b2e368d8f7f82a84027eadfea9c45f4e1dbdb1b` | PASS |
| traffic_forecast | `D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B1\2025-05-01\TRAFFIC_FORECAST.npz` | `72f71b609de1301b4911cfabe3a7d02e5567e8c3889c50ac4892bab967246e8c` | PASS |
| initial_running_authority | `D:\MobileESS_V43\runtime\gate_b_c0_c1_actual96_attempt001\CASE\INITIALIZATION\SYNTHETIC_INITIALIZATION_POLICY.json` | `cfcf2ab87cf74ff9d8d5d52a1da942ff5039c83ee67db87b24298729e08e240c` | PASS |
| initial_MESS_authority | `D:\MobileESS_V44\runtime\initial_states_revision01\2025-05-01\MESS_DAILY_INITIAL_STATE.json` | `b7c42cacd6d2b3ea6cde034db0d684917bd7a33c6af013e05ed4fd1d4f151e95` | PASS |
| request_descriptors | `D:\v44_may01_07_prepare_20261016\docs\v44\input_metadata\2025-05-01\PUBLIC_REQUEST_DESCRIPTORS.json` | `822aa9039770d78302523f279dd6b67207ab46e8ef848ebd787b6a11b04f254f` | PASS |
| daily_sources:aemo_forecast.json | `D:\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend\cache\v28r2_campaign_sources\may_2025\days\2025-05-01\aemo_forecast.json` | `93e07ffbfd7ccef05782b8b81fed5b40a1b418446ec6cb8da1e4ee09143b5637` | PASS |
| daily_sources:gfs_d1_weather.parquet | `D:\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend\cache\v28r2_campaign_sources\may_2025\days\2025-05-01\gfs_d1_weather.parquet` | `314c71f7aa7a7f72170c0f52b8a92d614139564411464c5658e6584be452968c` | PASS |
| daily_sources:aemo_actual.parquet | `D:\ChatGPT\Mobile ESS 2\v42_may_b0_holdout_pr\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\DERIVED_AEMO_ACTUAL.parquet` | `d56f3854cbbc34835c9ec6cab150aa384a358c8f2f52a76f5b16dbcf230030fe` | PASS |
| daily_sources:noaa_actual_weather.parquet | `D:\ChatGPT\Mobile ESS 2\v42_may_b0_holdout_pr\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\DERIVED_NOAA_ACTUAL.parquet` | `b19d18b70eb702e534d1330f2c239b311e3bf6882e08caca83804a330e630dac` | PASS |
| raw_realized_sources:demand | `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\AEMO\Realized demand\PUBLIC_ARCHIVE#DISPATCHREGIONSUM#FILE01#202505010000.zip` | `89a3d7b9d793d164adeeeef7c4234f3a6a512aa63236ff0d1a3193d3d5eb5186` | PASS |
| raw_realized_sources:pv | `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\AEMO\AEMO Rooftop PV — forecast + actual\Actual\PUBLIC_ARCHIVE#ROOFTOP_PV_ACTUAL#FILE01#202505010000.zip` | `2a1d641d2447d7ddc7926690185058f508dde91657be84a3acfbdc6810cff65e` | PASS |
| raw_realized_sources:weather | `D:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v24t_thermal_aware_aidc\V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet` | `f9582754d309bf5d8444206a526869f4579020d1a45c011e02bf00ff3852cf52` | PASS |
| D1_snapshot | `D:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v37_r4a_per_day_aidc\days\2025-05-01\V37_R4A_D1_SNAPSHOT.parquet` | `8d74fcf0bc305bff983bff9607fe7d5120c8a61618631cfc6d6fdda81c71423a` | PASS |
| Kestrel_archive | `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip` | `3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f` | PASS |
| daily_aemo_forecast.json | `D:\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend\cache\v28r2_campaign_sources\may_2025\days\2025-05-01\aemo_forecast.json` | `93e07ffbfd7ccef05782b8b81fed5b40a1b418446ec6cb8da1e4ee09143b5637` | PASS |
| daily_gfs_d1_weather.parquet | `D:\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend\cache\v28r2_campaign_sources\may_2025\days\2025-05-01\gfs_d1_weather.parquet` | `314c71f7aa7a7f72170c0f52b8a92d614139564411464c5658e6584be452968c` | PASS |
| daily_aemo_actual.parquet | `D:\ChatGPT\Mobile ESS 2\v42_may_b0_holdout_pr\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\DERIVED_AEMO_ACTUAL.parquet` | `d56f3854cbbc34835c9ec6cab150aa384a358c8f2f52a76f5b16dbcf230030fe` | PASS |
| daily_noaa_actual_weather.parquet | `D:\ChatGPT\Mobile ESS 2\v42_may_b0_holdout_pr\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\DERIVED_NOAA_ACTUAL.parquet` | `b19d18b70eb702e534d1330f2c239b311e3bf6882e08caca83804a330e630dac` | PASS |
| raw_realized_demand | `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\AEMO\Realized demand\PUBLIC_ARCHIVE#DISPATCHREGIONSUM#FILE01#202505010000.zip` | `89a3d7b9d793d164adeeeef7c4234f3a6a512aa63236ff0d1a3193d3d5eb5186` | PASS |
| raw_realized_pv | `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\AEMO\AEMO Rooftop PV — forecast + actual\Actual\PUBLIC_ARCHIVE#ROOFTOP_PV_ACTUAL#FILE01#202505010000.zip` | `2a1d641d2447d7ddc7926690185058f508dde91657be84a3acfbdc6810cff65e` | PASS |
| raw_realized_weather | `D:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v24t_thermal_aware_aidc\V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet` | `f9582754d309bf5d8444206a526869f4579020d1a45c011e02bf00ff3852cf52` | PASS |
| D1_snapshot | `D:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v37_r4a_per_day_aidc\days\2025-05-01\V37_R4A_D1_SNAPSHOT.parquet` | `8d74fcf0bc305bff983bff9607fe7d5120c8a61618631cfc6d6fdda81c71423a` | PASS |
| power_C1 | `D:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v24t_thermal_aware_aidc\V24T_C1_QUASISTATIC_MODEL.json` | `02a19e6c2d8cb44ec6b90ff1a4c98f21d5e848cda2dc34f2aaf2f959f9e6579e` | PASS |
| power_C1_implementation | `D:\codex_mobileess_workspace\MobileESS_v41r2_780gpu_capacity_rebase\dayahead\v28r2\c1_affine.py` | `912c870a2c062431cac60f2157f3b4399ad824119facdafbd7ac3f1788c40c13` | PASS |
| power_GFS | `D:\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend\cache\v28r2_campaign_sources\may_2025\days\2025-05-01\gfs_d1_weather.parquet` | `314c71f7aa7a7f72170c0f52b8a92d614139564411464c5658e6584be452968c` | PASS |
| power_NOAA | `D:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v24t_thermal_aware_aidc\V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet` | `f9582754d309bf5d8444206a526869f4579020d1a45c011e02bf00ff3852cf52` | PASS |
| power_planning_C1 | `D:\ChatGPT\Mobile ESS 2\v42_may_b0_holdout_pr\docs\v42_may_b0_zero_margin_holdout\INPUT\BUNDLE\DAY_20250501\C1_PLANNING_COEFFICIENTS.csv` | `47b4cda5c7e2cfa357442874f0eef8b566aabc8d98d89cac05053275a31a5416` | PASS |

## 2. 최종 IEEE123 입력과 계수 적용

`IEEE123_FROZEN_ELECTRICAL_INPUTS.npz`에 Planning 96슬롯과 Actual 120슬롯(24 Prefix+96 평가)을 분리했다. 배경부하 P/Q, PV P/Q, AIDC12 P/Q, 버스·상/사이트 축, 전체 순부하 P/Q가 포함된다. `ELECTRICAL_ARRAY_SHA256.json`에 dtype/shape/단위/.npy 직렬화 SHA를, `IEEE123_FINAL_POWER_TOTALS_216.csv`에 모든 총량을 기록했다. 사이트별 IT·Cooling/aux·P/Q는 `IEEE123_AIDC12_POWER_2592.csv`에 있다. 순부하는 gross background + AIDC − PV이며 MESS가 없는 B0 입력 정의다. 계통 손실을 포함한 변전소 유입 전력과 구분한다.

| 96 평가 슬롯 범위 | Planning | Actual |
|---|---:|---:|
| 배경 P kW | 1772.844526~2705.984027 | 1765.562270~2712.793328 |
| 배경 Q kvar | 683.742979~1570.647080 | 686.007971~1624.377654 |
| PV P 최대 kW | 320.738595 | 327.947863 |
| PV Q kvar | 0 | 0 |
| AIDC 총 P kW | 228.141568~568.257478 | 461.451308~568.257491 |
| 전체 순 P kW | 1757.845077~3135.580088 | 2027.722516~3271.676384 |

`POWER_AUTHORITY.json`의 `alpha_BG=1.15`는 May01 원본에도 있다. `V41_ELECTRICAL_CERTIFICATE.json`의 날짜 결합 → `v41r4_electrical.py` → 최종 `V41R3_BACKGROUND_SCALE_AUTHORITY.json` → 저장된 ORIGINAL_DAYAHEAD_BACKGROUND 계보를 확인했다. export된 최종 P/Q에는 원래 적용이 이미 반영돼 있다. Greensboro에는 export된 최종 총량을 직접 분배하므로 alpha_BG/alpha_grid를 다시 곱하지 않는다. April runner를 호출하거나 새 계수 선택의 근거로 사용하지 않았다. 코드의 transitive import가 과거 runner로 이어진다는 사실은 별도로 기록했다.

V16.2의 alpha_grid, 3490/7100.2615 수요 정규화, 698.000002861023/4021.226 PV 정규화, 기존 residual/Q lookup, P/Q에만 적용되는 원래 1.15, GPU IT idle/swing, C1의 NLR equivalent scale와 normalization, PF0.95는 `NORMALIZATION_AND_APPLICATION_ORDER.json`에 모두 기록했다. C1 normalization은 원래 함수 내부에서 적용되며 사후 추가 배율을 사용하지 않았다.

Actual은 raw as-of 관측을 사용하는 r043 실행 경로를 재현했다. 새 AC를 풀지 않고 load/generator setpoint를 읽어 **120/120 슬롯에서 저장된 Actual setpoint SHA와 정확히 일치**했다. `DERIVED_AEMO_ACTUAL`과 `DERIVED_NOAA_ACTUAL`도 SHA를 확인하고 보존했지만, interval-end/보간 derivative를 원래 online as-of 값 대신 넣지 않았다. 차이는 `ACTUAL_RAW_ASOF_VS_DERIVED_AUDIT.csv`에 보인다. Planning은 D-1 forecast와 GFS를 사용하고 Actual 정보는 Planning으로 넘기지 않았다. 기존 Forecast ingestion의 인과성 미인증 한계는 유지한다. 별도 Planning 24-prefix 배열을 새로 만들지 않았다.

2,498개 Job의 독립 FCFS 재생은 capacity violation 0, dropped 0, Native 호출 0이다. Actual GPU/IT/P/Q는 기존 비전기적 B0 trace와 최대 차이 0이다. 이는 **Greensboro AC 인증이 아니다**. 초기 Running 위치에 남아 있는 원래 연구 가정도 유지한다.

## 3. Greensboro 연결 규칙과 보존량

SMART-DS에서는 v1.0 base_peak의 토폴로지·임피던스·정격·부하 접속점/상·원본 제어설비만 확보했다. 2016~2018 운영 시계열을 사용하지 않는다. 원본은 **6572 buses / 12749 electrical nodes / 5649 lines / 931 transformers / RegControl 1 / capacitor 5 / PVSystems 0**이다. 피더는 `uhs2_1247--udt10746`, `uhs2_1247--udt12473`, `uhs2_1247--udt9312`다. 공식 파일 URL/바이트/SHA는 `SMARTDS_SOURCE_AND_SUBSTATION_ID.json`에 있다.

P/Q 공간 분배의 후보 가정은 `wP_i=P_nom_i/sum(P_nom)`, `wQ_i=Q_nom_i/sum(Q_nom)`이다. 원본 부하의 버스·상·전압 연결을 유지하고 시간에 불변인 가중치만 사용한다. 원본 nominal load를 운영 부하로 더하지 않는다. 매 슬롯 수신량을 기존 load setpoint의 대체값으로 정의하므로 이중 투입을 하지 않는다. float64 fsum 총량의 잔여 반올림은 최대 가중치 수신점에서 보정하며 오차 기준/물리 허용치를 변경하지 않는다.

**216행 모두 P/Q 총량 최대 절대 오차=0, 상대 오차=0**이다(Planning96+Actual120). 두 운영 역할 각각의 96 평가 슬롯 비교는 `INPUT_IDENTITY_METRICS_96.csv`에 있다. 새 공간 배열의 SHA는 원본과 다르며 가중치·배열별 SHA를 별도로 봉인했다. AIDC12 P/Q는 사이트 축 identity binding으로 최대 오차 0이다. Job UID/GPU/QoS/Deadline과 route ETA/energy는 원본 native/windows/request/Route Table 전체 파일의 SHA를 유지하며 다시 작성하지 않는다. 이는 물리 PCC 수용성을 인증하지 않는다.

**PV P/Q 및 전체 순부하 동일성은 NOT_VERIFIED**다. 원본 PV는 상별 2.4kV `Generator Model=1`, Q=0의 기존 전력 모델이다. Greensboro bus의 kV_LN은 약 0.120089/0.277128/7.199558/39.837169이며 직접 2.4kV 접속 대응을 확인하지 못했다. 원본에 PVSystem이 없다는 이유로 기존 PV를 0으로 만들거나 net load에 숨기지 않았다. 적격 PCC/위상·전압 변환·변압기/선로 정격 및 모델 계약의 대응이 필요하다. 승인되지 않은 재배치를 인증된 입력으로 사용하지 않는다.

3상 LV 변압기 후보는 63개, nameplate 400kVA 이상은 2개다. 이는 후보 목록이며 실제 site headroom, 접속 포트, AIDC 공간 순서, 8대 동시 접속 PASS가 아니다. 기준/분산/혼잡 배치 모두 최종 선정하지 않았다. 원본 AIDC12+STA12의 SUMO 좌표·ID·경로는 유지했다.

## 4. 실행 Gate와 남은 검증

`INPUT_MAPPING_GATE.json`과 `INPUT_IDENTITY_CERTIFICATION.json`은 AC_ALLOWED=false다. 미확인 항목은 재귀 ancestral receipt, PV의 전기적 이전, AIDC12+STA12 전체 PCC와 AIDC 공간 순서다. B0, 전체 물리 제약, Top-K/무교란/양방향 민감도, 실행 가능한 Job/MESS/joint pilot은 NOT_VERIFIED다. `B0_NOT_BUILT`를 배경망 PASS 또는 NO_QUALIFIED_B0_SCENARIO로 바꾸지 않았다. 차단된 결과 CSV에는 수치 대신 빈 값과 사유가 있다.

r043 Planning의 RegControl 7개와 Actual의 SVR12 포함 43개는 Greensboro 원본 1개와 일치하지 않는다. 동일 물리 계약을 원본 설비 그대로 구현했다고 주장할 수 없다. 복사·설비 개조를 하지 않았다. 차량 4대의 상위 입출력/guard 하드코딩과 8대의 추정 차원은 `V44_R043_8MESS_PORT_AUDIT.md`에 있으며 실제 8대 모델 생성/성능 측정과 구분했다.

현재 최종 질문의 답은 **동일 입력에서 전역 최대 선로부하율을 실제 제어할 수 있는지 아직 인증하지 못했다**이다. 핵심 직접 원본과 실제 적용값은 확보됐지만, 전체 계보·PV/PCC 입력 Gate가 닫혀 있다. A1/M1/A2/M2, K48, Beam, Joint MILP와 캠페인은 실행하지 않았다.

`WORKLOAD_ROUTE_IDENTITY.json`은 UID/GPU/원래 window·QoS/Deadline provider 입력 및 원본 route travel/connection-ready/energy 배열의 논리 SHA를 별도로 기록한다. 입력은 동일 파일 참조로 유지하며 없는 hard deadline을 생성하지 않는다.

재현 순서: 독립 `v1_add_preflight`의 `fetch.py`(공식 정적 설비만) → `ac.py`(설비 inventory만) → `replay_jobs.py`(독립 FCFS) → `authority.py`(원본 적용값 readback) → `mapping.py`(P/Q 후보 산술) → `export_arrays.py` → `source_stage.py` → `contracts.py` → `lineage.py` → `figures.py` → `finalize.py`. `measure()`는 현재 Gate에서 예외를 발생시킨다. `lineage.py`는 격리 runtime의 ijson 3.4.0으로 큰 JSON을 streaming하고 Production lock/ledger를 사용하지 않는다. 원본 전기 입력과 정적 계통도 그림만 제공하며, 생성되지 않은 AC/민감도/pilot 그림을 실측 결과로 표현하지 않았다.
