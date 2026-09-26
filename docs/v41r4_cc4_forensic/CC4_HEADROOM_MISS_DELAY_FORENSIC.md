# CC4 HEADROOM MISS / JOB DELAY — READ-ONLY FORENSIC AUDIT

> 저장소 사본 안내: 원본 감사 수치와 판정은 유지했다. 링크만 저장소 경로로 바꾸었으며 archive 원본 artifact 링크는 [로컬 증거 안내](ARCHIVE_EVIDENCE.md)로 연결한다. 전체 Job CSV는 무손실 `.csv.gz`로 제공한다. 원본 로컬 경로는 감사 당시 provenance로 보존했다.

감사일: 2026-09-22. PR 포장: 2026-09-26 (새 과학 계산 없음). 대상: 사용자가 지정한 동결 V41R4 May 2025 archive. 새 최적화·Actual replay·OpenDSS·ML 학습/추론을 실행하지 않았다. 아래 계산은 저장된 결과의 재집계와 동일성 검증이다.

## Executive conclusion

[결론]
- CC4 reserve 예측이 실제보다 부족했던 경우: **있었음 — 466 / 2,511 window, 18.5583433%**.
- 그때 실제 Job delay가 발생했는지: **미래 도착 Job에 대해서는 직접 판별 불가**. 기존 동결 Job의 대기 구간이 miss window와 겹치는 사례는 B1 228, B3 229 job-day로 확인된다.
- delay가 있었다면 직접 원인: 기존 Job의 GPU capacity contention. 코드/기록의 정확한 reason은 `RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN`. Migration 중단·WAN 대기·restart는 별도 기록이다.
- CC4 miss가 원인이라고 말할 수 있는지: **NOT_IDENTIFIABLE**. 해당 미래 도착 Job들이 같은 날 Actual replay queue에 들어가지 않는다.
- 실제 runtime에서 부족 상황을 처리한 알고리즘: 동결된 site/우선순위를 유지하는 deterministic, event-driven physical dispatch. GPU가 확보될 때까지 기다린다.
- online re-optimization 여부: **CC4 reserve 재계산·미래 도착 Job scheduling·AIDC schedule 재최적화 모두 NO**.
- 교수님께 한 문장으로 설명할 내용: **“CC4의 reserve 과소예측은 466개 window에서 확인됐지만, 그 미래 도착 Job은 Actual replay에 투입되지 않아 그로 인한 지연은 평가할 수 없고, 관측된 기존 Job 지연은 동결 스케줄의 GPU 자원 경합으로 처리됐습니다.”**

## Exact answer to the professor's question

`H_k > R_k`는 확인된다. 그러나 이 실험의 replay 입력은 issue 시점에 이미 알려진 RUNNING/PENDING Job의 동결된 `AIDC_decision`이다. 전체 **124 policy-day**에서 replay ledger의 Job ID 집합이 동결 decision의 ID 집합과 같고, 모든 replay Job의 submit time이 issue 이하임을 검증했다. H4 window는 issue 이후 6시간부터 시작하므로, window 내 신규 제출 Job이 같은 날 replay에 추가되는 경로는 없다.

저장된 contributor 표가 있는 **30일의 49,803개 고유 day-job**과 same-day replay ID를 대조한 결과 교집합은 **0**이다. 5월 21일은 contributor 개별 행이 archive에 없고 H4_SCORE의 81개 label만 있다. 이 날짜는 miss가 0개이므로 **466개 miss window 전체의 contributor 증거는 확보**되었다. Non-miss Job 모집단은 5월 21일 누락 때문에 부분 관측이다.

Kestrel contributor 표의 `start_time/end_time`은 원래 관측 trace의 label이다. 이것을 B1/B3 정책하의 `ACTUAL_EXECUTION_START/END`로 바꾸어 쓰지 않았다. Job link CSV는 원래 trace 시각을 `observed_trace_*` 열에만 보관하고, 미래 Job의 정책 실행 지연은 `NOT_AVAILABLE`로 남겼다. JSON의 지연 `null`은 **0이 아니라 식별 불가**이다.

근거: [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/input_adapter.py](source/archive/v41r4_actual_eta95_qsafe_robust_v2_perf1/input_adapter.py)의 44–68행과 107–120행; [dayahead/v41/actual.py:138](source/dayahead/v41/actual.py#L138); [ANALYSIS_VALIDATION.json](ANALYSIS_VALIDATION.json); 일별 최종 경로와 SHA는 [CC4_EVIDENCE_SOURCE_MAP.json](CC4_EVIDENCE_SOURCE_MAP.json).

## Exact artifact semantics

사용자가 부른 CC4-GWRF의 해당 archive 인터페이스 모델 ID는 `H4_R85_B2`이다. 이름을 근거로 다른 알고리즘을 가정하지 않고, 동결 `H4_ACTIONABLE_RESERVE_GPUh` / `ACTIONABLE_H4_GPUh`를 분석했다.

시간축은 source의 fixed **UTC+10 modeled day**이다. `issue_time(day) = day 00:00(+10) - 6h`; D-day는 issue+6h부터 24시간이다. k는 **0–80**, 간격 15분, 각 window는 **[start, end)** 4시간이다. CSV에는 UTC offset을 포함한 ISO 시각을 썼다. 예: modeled 2025-05-20 k=37은 UTC 2025-05-19 23:15–2025-05-20 03:15, UTC+10에서는 5월 20일 09:15–13:15이다. 근거: [dayahead/v41/data.py:41](source/dayahead/v41/data.py#L41), [dayahead/v41/persistence.py:61](source/dayahead/v41/persistence.py#L61).

| 기호 | 실제 정의 / 계산식 | archive field / artifact | source |
| --- | --- | --- | --- |
| H_k | `sum(gpus_requested × (observed end − observed start)/3600)` for Job submit ∈ window. **제출 Job의 전체 lifetime service GPUh**이며 window 내 실제 GPU 점유량이 아니다. | `H4_SCORE.json.realized_H4_GPUh[k]`; 과거 보존본 `H4_ACTUAL_WINDOW_EVALUATION.parquet.ACTUAL_H4_GPUh`; contributor `GPU_service_GPUh, arrival_slot` | `actual.py:138–180` |
| R_k | `min(raw_R85_B2, historical_cap, physical_cap_k)`인 최종 actionable reserve | `ml/H4_WINDOW_PREDICTIONS.parquet.ACTIONABLE_H4_GPUh`; snapshot `H4_ACTIONABLE_RESERVE_GPUh` | `reserve.py:35–48`; `persistence.py:59–71` |
| A_k | `0.25 × sum_(t=k..k+15, eligible sites)(capacity_gpu[t,s] − selected_known_GPU[t,s])` | 최종 `PLANNING_RESULT.json.reserve.H_available_GPUh`; `H4_OPTIMIZER_WINDOWS.parquet.available_headroom_GPUh` | `reserve.py:89–116` |
| xi_k | 계획 reserve shortfall `max(R_k − A_k,0)`; optimizer constraint `A_k + xi_k >= R_k`, xi≥0 | `PLANNING_RESULT.json.reserve.xi_GPUh`; `reserve_shortfall_xi_GPUh` | `reserve.py:89–116`; `persistence.py:97–112` |
| actionable coverage | `H_k <= R_k`, tolerance 없이 부등식 그대로; equality는 covered | `ACTIONABLE_COVERED`; `actual_rows()` summary | `persistence.py:115–136` |
| raw coverage | `H_k <= RAW_R85_B2_GPUh`; capped forecast coverage와 다름 | `RAW_COVERED` | `persistence.py:115–136` |
| cap binding | 해당 cap == actionable **AND** actionable < raw; 두 cap 동률이면 둘 다 가능 | `hist_cap_binding`, `phys_cap_binding` | `persistence.py:66–70,110–111` |

위 표의 실행 소스 링크: [dayahead/v41/actual.py:138](source/dayahead/v41/actual.py#L138), [dayahead/v41/reserve.py:35](source/dayahead/v41/reserve.py#L35), [dayahead/v41/persistence.py:97](source/dayahead/v41/persistence.py#L97).
실제 artifact 예: [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/H4_SCORE.json](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-01/B1/dayahead/ml/H4_WINDOW_PREDICTIONS.parquet](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-01/B1/dayahead/H4_OPTIMIZER_WINDOWS.parquet](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-01/B1/dayahead/PLANNING_RESULT.json](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-01/B1/actual/authority/ACTUAL_WORKLOAD_CONTRIBUTORS.parquet](ARCHIVE_EVIDENCE.md).

**세 가지 부등식을 분리한다.** `A<R`는 계획 shortfall, `H>R`는 예측 miss, `H>A`는 실현 label이 계획 headroom을 넘는 사후 지표다. 마지막도 4시간 내 동시 점유량 초과나 queue 지연의 증명은 아니다. H에는 4시간 이후에 수행될 긴 Job의 service도 전부 들어간다.

## Forecast miss statistics

| 항목 | 값 |
| --- | --- |
| 전체 window | 2511 |
| covered window | 2045 |
| miss window | 466 |
| miss 비율 (%) | 18.558343 |
| actionable coverage (%) | 81.441657 |
| positive miss mean (GPUh) | 5,750.760597 |
| positive miss median (GPUh) | 1,963.951911 |
| positive miss P90 (GPUh) | 13,165.702778 |
| positive miss max (GPUh) | 55,546.619764 |
| physical cap binding window | 517 |
| historical cap binding window | 0 |
| miss 중 physical cap binding | 131 |
| raw forecast miss | 427 |
| cap 적용으로 추가된 miss | 39 |

Positive miss의 평균·중앙값·P90·최댓값은 **466개 양의 H−R**만 대상으로 한다. P90은 NumPy/Pandas 선형 보간이다. 전체 31일에서 policy 간 R/H 동일성을 확인하여 네 정책을 중복 집계하지 않았다. 기존 **81.44%와 소수 둘째 자리 반올림 기준 정확히 일치**한다. 81.44는 반올림 표현이고 정확한 비율은 2045/2511이다. Raw coverage는 82.99482278%이므로 raw/capped를 바꾸어 쓰면 불일치한다. 4시간 windows 합계를 고유 workload 총량으로 해석하지 않는다.

출처: [CC4_HEADROOM_MISS_WINDOWS.csv](CC4_HEADROOM_MISS_WINDOWS.csv), 각 행의 `R_source`, `H_source`, `contributors_source`. 30일·2,430개 label은 contributor service를 다시 합산해 1e-8 GPUh 이내 일치했고, 5월 21일 81개는 최종 H4_SCORE의 저장 label을 사용했다.

### 최대 miss 상위 10개

| day | k | window start (UTC) | window end (UTC) | R GPUh | H GPUh | H−R GPUh |
| --- | --- | --- | --- | --- | --- | --- |
| 2025-05-20 | 37 | 2025-05-19T23:15:00+00:00 | 2025-05-20T03:15:00+00:00 | 2,939.387458 | 58,486.007222 | 55,546.619764 |
| 2025-05-20 | 36 | 2025-05-19T23:00:00+00:00 | 2025-05-20T03:00:00+00:00 | 2,987.749647 | 58,485.727778 | 55,497.97813 |
| 2025-05-20 | 22 | 2025-05-19T19:30:00+00:00 | 2025-05-19T23:30:00+00:00 | 3,120 | 58,441.31 | 55,321.31 |
| 2025-05-20 | 23 | 2025-05-19T19:45:00+00:00 | 2025-05-19T23:45:00+00:00 | 3,120 | 58,402.902222 | 55,282.902222 |
| 2025-05-20 | 35 | 2025-05-19T22:45:00+00:00 | 2025-05-20T02:45:00+00:00 | 3,016.865553 | 58,291.709722 | 55,274.844169 |
| 2025-05-20 | 24 | 2025-05-19T20:00:00+00:00 | 2025-05-20T00:00:00+00:00 | 3,120 | 58,378.736667 | 55,258.736667 |
| 2025-05-20 | 25 | 2025-05-19T20:15:00+00:00 | 2025-05-20T00:15:00+00:00 | 3,120 | 58,377.753333 | 55,257.753333 |
| 2025-05-20 | 26 | 2025-05-19T20:30:00+00:00 | 2025-05-20T00:30:00+00:00 | 3,120 | 58,351.005556 | 55,231.005556 |
| 2025-05-20 | 34 | 2025-05-19T22:30:00+00:00 | 2025-05-20T02:30:00+00:00 | 3,076.24826 | 58,199.704722 | 55,123.456462 |
| 2025-05-20 | 27 | 2025-05-19T20:45:00+00:00 | 2025-05-20T00:45:00+00:00 | 3,120 | 58,240.95 | 55,120.95 |

출처: [CC4_TOP10_MISS_WINDOWS.csv](CC4_TOP10_MISS_WINDOWS.csv) (동일 행에 원본 경로 포함). 상위 10개는 같은 날짜의 overlapping windows이며 10개의 독립 사건이 아니다.

### Planned shortfall와 forecast miss 교차표

B1/B3 각각 동일한 window 수이며 GPUh 크기는 정책마다 다르다. xi의 양수 판정에는 수치 잔차 방지를 위해 1e-8 GPUh를 사용했다. Forecast miss에는 tolerance를 적용하지 않았다.

| 조건 | B1 window | B3 window |
| --- | --- | --- |
| H>R 및 xi>0 | 423 | 423 |
| H>R 및 xi=0 | 43 | 43 |
| H<=R 및 xi>0 | 1852 | 1852 |
| H<=R 및 xi=0 | 193 | 193 |

| 계획/실현 진단 | B1 | B3 |
| --- | --- | --- |
| mean xi GPUh | 1,691.584144 | 1,691.051886 |
| max xi GPUh | 3,109 | 3,109 |
| xi>0 windows | 2275 | 2275 |
| H>A windows | 1676 | 1676 |

출처: [CC4_HEADROOM_MISS_WINDOWS.csv](CC4_HEADROOM_MISS_WINDOWS.csv), `A_k_B1_GPUh/xi_k_B1_GPUh/A_k_B3_GPUh/xi_k_B3_GPUh`, 최종 `PLANNING_RESULT.json` source 열. 최종 H4_SCORE의 frozen headroom도 124 policy-day 모두 최종 DA 값과 일치했다.

## Actual delay statistics

아래 표는 **H4 future-arrival Job의 지연이 아니다.** 각 정책에서 동결 decision에 선택된 기존 Job **46,092 job-day**를 집계했다. 같은 Job은 독립적인 여러 날짜의 snapshot에 반복될 수 있다(고유 job_uid 18,425). 미선택 backlog 917 job-day는 지연 평균 분모에서 제외했다.

| 기존 selected Job 지표 | B1 | B3 |
| --- | --- | --- |
| selected job-days | 46092 | 46092 |
| delayed job-days | 1465 | 1466 |
| delayed fraction | 0.031784 | 0.031806 |
| total start delay (job·s) | 5,631,697 | 5,632,997 |
| mean start delay, zero 포함 (s) | 122.183828 | 122.212032 |
| P95 start delay, zero 포함 (s) | 0 | 0 |
| max start delay (s) | 58,413 | 58,413 |
| sum(GPU × start delay) (GPU·s) | 21,197,694 | 21,198,994 |
| GPU weighted mean start delay (s) | 185.544299 | 185.555678 |
| 미완료 selected job-days at H | 20873 | 20872 |
| remaining service at H (GPUh, daily sum) | 464,268.570833 | 464,317.714167 |
| contention-added RW lateness (job·s) | 0 | 0 |
| delay가 있는 날짜 | 26 | 26 |
| miss와 delay가 모두 있는 날짜 | 21 | 21 |
| wait interval이 miss window와 겹치는 고유 job-day | 228 | 229 |

P95가 0인 것은 지연 비율이 약 3.18%이기 때문이다. 지연 Job만의 평균은 B1 3,844.161775s, B3 3,842.426330s이다. `GPU_weighted_delay_seconds`라는 원본 KPI명은 실제로 ΣGPU×seconds이며, 단위는 **GPU·s**이다. mean은 이를 ΣGPU로 나눈 seconds이다.

`remaining_GPU_hours_at_H`는 실제 계산 service의 잔량이다. 이미 장기 실행 중인 Job의 잔량과 migration 영향을 포함하며, CC4 delay GPUh가 아니다. 위 daily sum은 독립 day replay의 잔량 합으로, 연속 월간 단일 backlog 총량으로 해석하면 안 된다. `contention_added_completion_lateness_seconds=0`은 frozen RW deadline 기준 추가 lateness가 0이라는 뜻이며, 시작 지연 또는 migration 중단이 0이라는 뜻이 아니다.

대조 정책 B0/B2는 각각 delayed 1,464 job-day, total 5,501,174 job·s, mean 119.352035s이다. 이는 동일한 입력 Job을 다른 동결 schedule로 실행한 비교일 뿐 CC4 miss counterfactual이 아니다.

출처: [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/ACTUAL_EXECUTION_DELAY_KPIS.json](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/ACTUAL_JOB_REPLAY.json](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/aidc/PHYSICAL_EXECUTION_DISPATCH.parquet](ARCHIVE_EVIDENCE.md); [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/aidc/DELAYED_JOBS.parquet](ARCHIVE_EVIDENCE.md). 전체 일자 경로는 [CC4_EVIDENCE_SOURCE_MAP.json](CC4_EVIDENCE_SOURCE_MAP.json), 검증은 [OUTPUT_VALIDATION.json](OUTPUT_VALIDATION.json). 124개 dispatch 표의 delayed count/총 지연과 KPI를 대조했다. B1/B3 모든 Job 행은 [CC4_MISS_JOB_DELAY_LINK.csv](CC4_MISS_JOB_DELAY_LINK.csv.gz)에 포함했다.

### 각 miss window와 Job 연결

각 window 안에 제출된 contributor Job은 `[start,end)`로 식별했다. 모두 same-day replay Job과 다르므로 신규 도착 Job의 delayed count/total/mean/max/GPU-weighted delay/completion/unfinished는 **NOT_IDENTIFIABLE**이다. 관측되지 않은 지연을 0으로 넣지 않았다.

[CC4_WINDOW_POLICY_DELAY_DIAGNOSTICS.csv](CC4_WINDOW_POLICY_DELAY_DIAGNOSTICS.csv)는 B1/B3의 모든 5,022개 policy-window를 담는다. `incoming_jobs`와 `incoming_jobs_explicitly_replayed`를 구분하고, 별도 `known_jobs_wait_interval_overlap_*` 열에는 기존 Job의 대기 `[planned_start,actual_start)`가 window와 겹치는 경우만 표시했다. 이 열의 full delay는 Job 전체 시작 지연이며 window 안의 조각 지연이 아니다. Overlapping windows 간 합산하면 중복된다. 228/229 수치는 한 날짜/정책/Job을 한 번만 센 값이다.

정확한 delay reason은 `RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN`이고 `BLOCKING_JOB_IDS`가 저장되어 있다. 그러나 이 reason은 capacity check가 실패하면 붙이는 코드의 공통 label이다. **모든 지연을 해당 Job 자신의 ROQ-RP 오차로 입증하는 개별 원인 판정은 아니다.** PENDING overrun, RUNNING의 잔여 runtime, 이전 blocking Job의 연쇄 대기, migration destination contention을 구분해서 읽어야 한다. 개별 blocker와 예측/관측 runtime 표본: [CC4_DELAY_BLOCKER_EXAMPLES.json](CC4_DELAY_BLOCKER_EXAMPLES.json).

## Migration interruption / post-horizon service separation

| 별도 지표 | B1 | B3 |
| --- | --- | --- |
| planned migration extra post-H service vs frozen B0 (GPUh) | 15,897 | 16,020.5 |
| 해당 planned extra service job-days | 306 | 313 |
| migration selected job-days | 333 | 344 |
| actual migration executed job-days | 244 | 254 |
| actual interruption GPUh (WAN wait+transfer+restart+destination GPU wait) | 6,512.394444 | 6,590.894444 |
| actual WAN queue (job·s) | 3,234,091 | 3,302,491 |
| actual restart GPU queue (job·s) | 13,044 | 13,044 |

15,897 / 16,020.5 GPUh는 최종 **DA compute_segments의 post-H service와 동일 day B0 reference의 차이(양수 부분)**를 다시 계산하여 확인했다. 식은 `sum_j max(postH_slots_policy − postH_slots_B0,0) × requested_GPU/4`, post-H 기준은 issue-relative slot 120이다. 모든 양의 차이 Job에 `migration_selected=true`가 있었다. 이것은 actual start delay 합도, future-arrival miss delay 합도 아니다.

Actual interruption은 실제 source compute 종료부터 destination compute 재개까지의 gap × GPU이다. 실제 runtime이 checkpoint 전에 끝나면 migration은 취소될 수 있으므로 선택 건수와 실행 건수가 다르다. Actual interruption 전체와 planned post-H extra는 정의와 runtime authority가 달라 서로 같아야 하는 값이 아니다. `RESTART_GPU_QUEUE_DELAY_SECONDS`는 initial start delay에 드러나지 않을 수 있어 따로 집계했다. `TOTAL_MIGRATION_DELAY_SECONDS`는 actual restart − planned restart의 **signed clock shift**이므로 이름만 보고 비음수 중단 시간으로 합치지 않았다.

출처: 최종 [frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-01/B1/dayahead/FROZEN_JOINT_DECISION.json](ARCHIVE_EVIDENCE.md)와 B0 같은 파일의 `decision.AIDC_decision[].compute_segments`, 실제 [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/ACTUAL_JOB_REPLAY.json](ARCHIVE_EVIDENCE.md)의 `actual_compute_segments/actual_migration_execution`; [CC4_MIGRATION_DELAY_SEPARATION.csv](CC4_MIGRATION_DELAY_SEPARATION.csv); [dayahead/v41r1/migration_dispatch.py:104](source/dayahead/v41r1/migration_dispatch.py#L104).

## Runtime algorithm behavior

최종 authority를 따라가는 실제 call chain은 다음과 같다.

```text
FINAL_RESULT_INDEX.json.final_actual
  -> 해당 namespace actual_worker.py::main
  -> frozen worker main의 input_for(day, policy, ...)
     -> 검증된 common_inputs 재사용 또는 input_adapter.py::prepare
        -> verify_old_or_current -> frozen decision['AIDC_decision']
        -> dayahead.v41.actual_dispatch.replay_jobs(jobs, observations, ...)
           -> dayahead.v41.actual.replay_jobs (realized runtime을 동결 Job에 결합)
           -> migration이 있으면 dayahead.v41r1.migration_dispatch.execute
           -> migration이 없으면 actual_dispatch 내부 deterministic queue
        -> ACTUAL_JOB_REPLAY.json / persist -> dispatch / delayed / KPI artifacts
        -> 별도 H4_SCORE 저장 (reporting only, future_scheduling_calls=0)
```

[frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/actual_worker.py](source/archive/v41r4_actual_eta95_qsafe_robust_v2_perf1/actual_worker.py):13–26,28–45,47–58; [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/input_adapter.py](source/archive/v41r4_actual_eta95_qsafe_robust_v2_perf1/input_adapter.py):44–68,107–120; [dayahead/v41/actual_dispatch.py:18](source/dayahead/v41/actual_dispatch.py#L18):18–91; [dayahead/v41r1/migration_dispatch.py:9](source/dayahead/v41r1/migration_dispatch.py#L9). 5월 31일 B3의 최종 namespace는 `v41r4_selective_actual_revision_v1`이며 그 namespace의 `input_adapter.py:66`도 같은 `actual_dispatch.replay_jobs`를 호출한다. 이전 `execution.py::actual` 경로도 [dayahead/v41/execution.py:328](source/dayahead/v41/execution.py#L328):328–359,385–406에서 같은 분리를 보여 준다. 최종 worker의 경로와 이전 경로를 혼동하지 않았다.

| 확인 항목 | source와 artifact에서 확인한 동작 |
| --- | --- |
| planned start 강제? | 조기 시작은 금지하며, capacity가 부족하면 actual start가 늦어진다. 동결 `start_slot`은 수정하지 않는다. |
| capacity 부족? | `used[site]+requested_GPU > capacity[site]`이면 request를 남겨 두고 release/checkpoint/restart event 후 다시 시도한다. Non-migration 분기는 realized duration 구간의 capacity 충돌을 검사한다. |
| priority | frozen start_slot → QoS tier → submit timestamp → job_uid. 실제 priority tuple과 authority를 사용한다. Migration 분기는 초기 RUNNING의 immutable 실행을 먼저 처리하며 동일 시각에는 releases가 starts보다 먼저이다. |
| migration | frozen checkpoint progress와 site/path/payload를 유지. WAN은 frozen UID order로 직렬 처리하며 transfer 후 1 slot(900s) restart 및 destination GPU 대기가 가능하다. |
| Actual start 재최적화? | NO. 실행 timestamp 변화는 deterministic dispatch 결과이다. `start_changes=0`과 `actual_execution_timestamp_changes>0`는 양립한다. |
| future arrival explicit enqueue? | NO. replay에는 decision Job들만 전달된다. H4 contributor는 별도의 label 집계이다. |
| CC4 miss detection → online rescheduling? | NO. H4_SCORE는 reporting-only; 미래 scheduling calls=0. |
| reserve 재계산/DA 재최적화? | NO. Actual은 sealed snapshot을 읽으며 ML_prediction_calls/DayAhead_feedback_calls/scheduling_optimizer_calls 모두 0이다. |

이 코드는 관측된 runtime을 이미 알고 실행을 재구성하는 **replay**이다. 운영 중 아직 모르는 runtime을 예측하며 미래 도착 queue까지 운영한 online 실험이라고 해석할 수 없다. `Actual_optimizer_calls=0`은 Job scheduling 범위의 진술이며, 별도 전력 Q-support controller의 수치 탐색 존재와 혼동하지 않는다.

시작 지연: [dayahead/v41/actual_dispatch.py:92](source/dayahead/v41/actual_dispatch.py#L92):92–136. KPI: 같은 파일 144–184. 저장/priority authority: 같은 파일 192–213. Migration의 직접 capacity wait 조건과 reason: [dayahead/v41r1/migration_dispatch.py:52](source/dayahead/v41r1/migration_dispatch.py#L52):52–62. 실제 priority authority: [frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/2025-05-01/B1/aidc/DISPATCH_PRIORITY_AUTHORITY.json](ARCHIVE_EVIDENCE.md).

## Quantitative comparison and causal attribution limits

Canonical assignment는 `k = min(floor((submit − D-day start)/15min),80)`이다. 즉 submit을 포함하는 가장 늦은 complete H4 window에 고유 day-job을 한 번만 배정한다. 20:00 이후 제출도 20:00–24:00인 k=80에 들어간다. Missing 5월 21일을 0개의 신규 Job으로 간주하지 않았다.

| 모집단 (B1/B3 각각) | M: H>R | C: H<=R |
| --- | --- | --- |
| canonical incoming Job 수 | 24359 | 25444 |
| same-day explicit replay 수 | 0 | 0 |
| delayed fraction | NOT_IDENTIFIABLE | NOT_IDENTIFIABLE |
| mean start delay (s) | NOT_IDENTIFIABLE | NOT_IDENTIFIABLE |
| P95 start delay (s) | NOT_IDENTIFIABLE | NOT_IDENTIFIABLE |
| GPU-weighted delay | NOT_IDENTIFIABLE | NOT_IDENTIFIABLE |
| unfinished/post-horizon GPUh | NOT_IDENTIFIABLE | NOT_IDENTIFIABLE |
| 범위 | 모든 miss 날짜 포함 | 5월 21일 contributor 미보존으로 부분 모집단 |

한 번이라도 miss window에 포함되는 고유 incoming Job은 **34345개**이다. 이는 canonical M과 정의가 다르며 overlapping window에서 같은 Job을 반복 합산하지 않았다. 출처: [CC4_MISS_JOB_DELAY_LINK.csv](CC4_MISS_JOB_DELAY_LINK.csv.gz)의 `population=FUTURE_ARRIVAL_LABEL_ONLY`, `canonical_window`, `window_miss_flag`, `any_covering_window_miss`.

일별 독립 집계는 [CC4_DAY_POLICY_AGGREGATION.csv](CC4_DAY_POLICY_AGGREGATION.csv)에 124 policy-day로 제공했다. B1/B3의 miss severity는 하루 81개 window의 `mean(max(H−R,0))`, delay는 하루 existing selected Job의 total start delay다. Pearson은 B1 -0.120509, B3 -0.120470; Spearman은 각각 -0.344248, -0.340193. 각 n=31의 **기술적 상관**이며 효과 추정이나 통계적 유의성 검정이 아니다. 일자 사이에도 workload/Job이 반복될 수 있다.

예를 들어 5월 6일은 miss 46개지만 B1/B3 start delay 0개, 5월 11일은 miss 0개지만 B1/B3 각각 start delay 266개다. 25일에 forecast miss가 있었고, 그중 21일에는 existing-job delay도 있었다. 이 관측은 두 현상이 동일하지 않음을 보여 줄 뿐 특정 원인의 causal effect를 추정하지 않는다.

CC4 causal delay를 판정할 수 없는 핵심 이유는 (1) future Job들이 정책 replay의 실행 대상에 없고, (2) 동일 arrivals/runtime에서 reserve만 바꾼 counterfactual 실행이 없고, (3) H4 label은 실제 동시 점유보다 넓은 lifetime work이며, (4) site/우선순위/기존 Job overrun/migration 경합을 단일 H−R 값으로 구분할 수 없기 때문이다. 본 감사에서는 요청대로 새로운 counterfactual을 실행하지 않았다.

## Evidence paths and integrity

원본 archive: `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz`

- SHA-256: `1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`.
- 크기: 13,524,418,762 bytes. Archive 69,297 regular members(패키지 metadata 포함). 원본을 `rb`로 읽어 해시를 확인하고 크기/mtime 불변을 검사했다.
- 분석 폴더 `evidence/V41R4_May2025_raw/`에는 선택한 archive member의 별도 사본을 저장했다. 파일별 해시는 archive `FILE_MANIFEST.json`과 대조했다. 원본 archive와 기존 결과 파일은 수정하지 않았다.
- 선택한 124개 최종 decision의 파일 SHA와 READY의 decision_SHA가 일치하고, replay ID 집합이 해당 decision ID 집합과 일치한다.
- 실행 핵심 source는 archive 내 `ACTUAL_BOUNDARY_RECEIPT.json.source.files`의 SHA와 로컬 final source를 대조한 뒤 `verified_source/`에 복사했다. archive 밖에서 가져온 **새 결과**는 사용하지 않았다. `source_bindings.json`에 원본 경로·사본 경로·SHA·archive receipt를 기록했다. `v40d_actual/job_replay.py`는 해당 receipt에 직접 해시가 없어 참고 사본으로만 구분했으며, 실제 ordering 결론은 저장된 `DISPATCH_PRIORITY_AUTHORITY.json` 및 replay의 `frozen_priority_key`와 해시가 확인된 caller를 근거로 한다.
- 최종 archive의 worker/adapter 자체는 직접 보존된 source이다. 과거 source receipt만으로 모든 실행 시점의 미기록 source를 완전히 복원했다고 주장하지 않는다. 보존된 source·call chain·final output contract의 일치 범위에서 판단했다.

무결성/검증: [archive_verification.json](archive_verification.json), [method_extraction_verification.json](method_extraction_verification.json), [extracted_evidence_manifest.json](ARCHIVE_EVIDENCE.md), [source_bindings.json](source_bindings.json), [ANALYSIS_VALIDATION.json](ANALYSIS_VALIDATION.json), [OUTPUT_VALIDATION.json](OUTPUT_VALIDATION.json).

최종 artifact 경로 규칙(모두 실제 archive inventory로 확인):

| 용도 | archive path |
| --- | --- |
| 최종 authority | `V41R4_May2025_raw/FINAL_RESULT_INDEX.json` |
| 일반 final Actual의 Job evidence | `frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1/common_inputs/{day}/{policy}/ACTUAL_JOB_REPLAY.json` 및 `aidc/PHYSICAL_EXECUTION_DISPATCH.parquet`, `aidc/DELAYED_JOBS.parquet` |
| 5/31 B2/B3 최종 Actual | `frozen_artifacts/v41r4_selective_actual_revision_v1/common_inputs/2025-05-31/{policy}/` |
| R/cap | `frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{policy}/dayahead/ml/H4_WINDOW_PREDICTIONS.parquet` |
| A/xi | 최종 accepted joint와 같은 `dayahead/PLANNING_RESULT.json`; 보존된 `H4_OPTIMIZER_WINDOWS.parquet`와 일치 확인 |
| H | 최종 common_inputs의 `H4_SCORE.json.realized_H4_GPUh` |
| 5/1–5/20 contributor | `frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{policy}/actual/authority/ACTUAL_WORKLOAD_CONTRIBUTORS.parquet`의 일별 대표 copy |
| 5/22–5/31 contributor | 최종 namespace `common_inputs/{day}/workload/REALIZED_WORKLOAD_CONTRIBUTORS.parquet` |
| 5/21 contributor | **NOT_AVAILABLE**: archive 전체 inventory에 없음; H4_SCORE는 있음 |

`EXACT_JOB_SLOT_OVERLAP.parquet`도 archive에 존재한다. 본 감사의 submit/actual-start 연결은 더 직접적인 dispatch와 full job ledger를 사용했고, event-time wait interval은 timestamp로 계산했다. 이 overlap 파일을 사용했다고 주장하지 않는다.

## Final YES / NO / NOT_IDENTIFIABLE table

| 질문 | 판정 | 정확한 범위 |
| --- | --- | --- |
| A. CC4 underprediction window에 제출된 미래 Job이 실제 replay에서 delay되었는가? | **NOT_IDENTIFIABLE** | 그 Job의 policy execution 자체가 없음. 0 delay라는 뜻이 아님. |
| A의 별도 시간 동시성: 기존 Job의 대기가 miss window와 겹치는가? | **YES** | B1 228 / B3 229 고유 job-day. 원인 연결이 아님. |
| B. 관측 delay가 CC4 underprediction 때문에 발생했다고 증명 가능한가? | **NOT_IDENTIFIABLE** | 관련 arrival 실행과 CC4 counterfactual이 없음. |
| C. CC4 miss에 대한 online recourse가 수행되는가? | **NO** | reporting-only H4 score, future scheduling calls=0. |
| D. 관측 start delay의 직접 코드상 메커니즘? | **GPU capacity wait** | `RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN`; migration destination wait는 별도 필드도 사용. |
| E. 미래 미제출 Job들이 same-day Actual에 explicit arrival로 실행되는가? | **NO** | reserve label/score만 평가. Issue-known frozen Job만 실행. |
| Planned xi와 realized miss가 같은가? | **NO** | A<R와 H>R는 별개. |
| 15,897 / 16,020.5 GPUh를 CC4 miss delay로 분류 가능한가? | **NO** | 별도의 planned migration post-H service deferral. |

## Deliverables and reading notes

1. [CC4_HEADROOM_MISS_DELAY_FORENSIC.md](CC4_HEADROOM_MISS_DELAY_FORENSIC.md) — 본 보고서.
2. [CC4_HEADROOM_MISS_WINDOWS.csv](CC4_HEADROOM_MISS_WINDOWS.csv) — 2,511개 전체 window, signed `forecast_miss_GPUh=H−R`, nonnegative `positive_miss_GPUh`, B1/B3 A/xi를 별도 열로 기록. 정책이 없는 단일 A/xi를 임의 선택하지 않았다.
3. [CC4_MISS_JOB_DELAY_LINK.csv](CC4_MISS_JOB_DELAY_LINK.csv.gz) — B1/B3의 기존 frozen Job과 미래 label Job을 `population`으로 분리. 정책별 Job 수를 전체 unique arrivals로 합산하지 않는다. `NOT_AVAILABLE`는 해당 값이 없거나 정의되지 않음을 뜻하며 mapping_status가 이유를 설명한다.
4. [CC4_HEADROOM_MISS_DELAY_SUMMARY.json](CC4_HEADROOM_MISS_DELAY_SUMMARY.json) — 필수 키, 숫자, 정책별 통계, 식별 한계. JSON `null`을 0으로 치환하지 않는다.

추가 검증표: [CC4_DAY_POLICY_AGGREGATION.csv](CC4_DAY_POLICY_AGGREGATION.csv), [CC4_WINDOW_POLICY_DELAY_DIAGNOSTICS.csv](CC4_WINDOW_POLICY_DELAY_DIAGNOSTICS.csv), [CC4_MIGRATION_DELAY_SEPARATION.csv](CC4_MIGRATION_DELAY_SEPARATION.csv), [CC4_TOP10_MISS_WINDOWS.csv](CC4_TOP10_MISS_WINDOWS.csv). 모든 숫자는 이 표들의 원본 artifact 경로 또는 source map으로 추적할 수 있다.
