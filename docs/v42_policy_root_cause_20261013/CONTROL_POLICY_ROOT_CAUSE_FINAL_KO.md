# V42 병렬 작업 결과 및 제어표 근본 원인

결론은 `POLICY_MULTIPLE_ROOT_CAUSES`입니다. 실제 May01의 후보 0은 익명 Reference 부족, 고정된 A2 Q90 수요목표 Scenario의 현재 단일 행동 범위에서의 Resource/Grid 불가능, Actual Resource Support 불일치와 독립적인 요청 권한 부족으로 설명됩니다. A2 수요목표는 Capacity-backed 실제 달성 Reserve가 아니며, 원본 P1 분해/FULL 모델은 합법적으로 Shortfall을 허용합니다. Source Binding Identity 검사는 PASS했습니다. 별도로 동결 V5에서 숨겨진 구현 오류를 재현하고 최소 수정했습니다. 수정 후 실제 May 제어 개선은 `NOT_ESTABLISHED`입니다.

## PART A — 기존 Integration PR

Draft PR: https://github.com/BeaverVillage/MobileESS/pull/223  
정확한 Push Commit: `8f0ea6e8f97147bb425530e8d787ca89f4a05053`  
실행 Source V5: `f488f3a99555eb2354ef52d0835078be816d2d988a2bf37010b9b09ff36568d8`

A1→M1→A2→M2는 실제 B3 May01에서 실행됐습니다. A1/A2는 원본 행 FULL 검사에 통과했습니다. M1 Native85.73초, M2 Native85.967초이며 모두 TIME_LIMIT의 FULL 가능한 UB입니다. M1 rho0.641266, Restricted Bound0.268437, Restricted Gap58.14%; M2 Restricted Gap58.31%입니다. 전체 원본 Joint Global Gap은 `NOT_CERTIFIED`입니다.

Full96 Actual은 활성2,320개를 유지해1,690개 완료/630개 Carryout, Job Drop0/GPU Capacity Violation0입니다. Fresh AC는 현재11SVR/153Transformer Phase와 실제 PCC P/Q를 대상으로 PASS했습니다. 사이트 초기화는 승인된 Model Assumption이며 Kestrel 관측 사이트 또는 Source18r 수치 동등성 인증이 아닙니다. 이 결과는 Unknown 최적화 제어 효과를 증명하지 않습니다.

보수적 Shared Solver 원장의 합계는 `621.285520/3600`초이며, 정확한 Native613.072999716초와 Other Solver Wall8.212520100초를 합산한 값입니다. AC35.169244100초는 별도 비용입니다. 이 원장은 앞선 NEW Integration 시도(V4 실패/Fixture/PR222 회귀)를 포함하며 기존 Campaign·PR221 원장 비용을 합산한 값이 아닙니다. 최종 시도 Wall2970.786초, 추가 Shared Solve260.420초입니다. PR222 Warm/Cold/Raw/Matrix/Source/Monitor를 변경하거나 재실행하지 않았습니다. B2/B3 캠페인 HOLD와 자동 재시작 차단을 유지했습니다.

## PART B — 제어표 원인에 대한 14개 답

1. **Unknown 평가 대상**: Origin Unknown774개는 자정 전 관측78개와 D-day 제출696개입니다. Unknown766개와 Known48개, 합814개 UID가 정책 Controller Dispatch에 진입했습니다. 당일 Pending Dispatch는693개입니다. Unknown8개 미진입은 다음 Checkpoint 전 완료5개와 마지막 Admission Boundary 이후 제출3개입니다. Known1,498개는 Unknown 정책 Dispatch에 진입하지 않았습니다. 활성2,320개와 모델용 익명 템플릿144개를 혼동하지 않았습니다.

2. **각 권한**: 실제 관측 QoS Cohort0/추가 지연 예산0입니다. `can_prestart_place=True`는 Known 초기 Pending1,245개이며 고정 Known 명령 경로로 처리됩니다. 모든 Unknown의 명시적 Pre-placement Flag는 False이고 Migration Capability Packet은0개입니다. Source Site가 None인 최초 FCFS 배치는 명시적 PREPLACE 제어 권한과 구분했습니다. 예산0을 Pre-placement0의 근거로 쓰지 않았습니다.

3. **후보 수**: Offline 익명 Variant4,392개를 구체화했습니다. 그중3,111개는 연속 익명 Reference가 없어 평가를 Skip했고972개는 Envelope Capacity에서 거부돼309개가 수치 Score에 도달했습니다. Migration Destination792번은 Capability 부재로 Variant 구체화 전에 거부된 별도 수치입니다. Actual 실제 UID 후보 생성은0개입니다.

4. **Hard Constraint**: 수치 평가309개 중 Q50 Hard 통과112개/실패197개, Q90 Hard 통과0개/실패309개입니다. Q90은 GPU용량과 원본 Voltage/Line Current/Transformer Current/kVA에서 실패했습니다. 마지막 슬롯의 Known+Nominal259.0585 GPU와 Q90 추가750.7861 GPU는 합1009.8446 GPU로 설치780 GPU보다229.8446 GPU 많습니다. 최대 단일 Gang100 GPU를 완전히 제거해도129.8446 GPU가 초과합니다. 현재 단일 행동 템플릿의 고정 Q90 Scenario에 대한 증명이며 다른 다중 Job Queue 모델의 전역 불가능성 증명이 아닙니다.

5. **Grid Score 실행**: 실제 동결 Compiler에서309개 Variant에 두 Scenario의 유한 Score가 저장됐고 Runtime Bucket Endpoint를 포함해1083회 수치 평가했습니다. Actual Online Grid Score와 Global MILP는0회입니다. Runtime Timing의 `lookup_calls=0`은 Pending Select Timing Sample 수이며 전체 Lookup Profiler가 아닙니다. 내부 Select/Lookup0은 아래 모든 Dispatch의 Guard Reject와 동결 Call Site로 재구성했습니다.

6. **A-stage 연결**: 최종 A2의96×12 익명 Envelope, Known/Nominal/Reserve 배열과 여섯 Distribution Field SHA가 일치합니다. A1의 오래된 Envelope를 사용하지 않았습니다. 최종 A2 Anchor `6693158b53d01fc0f318cc81a72426dcdae2cc45428b204e27ba06f89006b464`와 M2 Anchor `49d136655fa762d45925ed8132aeb2b86b453d1495b15f0ff8f9e6dbe3075b3e`가 Freeze/Reload/Actual Receipt에 연결됩니다.

7. **CC4 연결**: `LGBM_weighted_c1_s20260924`, Prediction SHA `8a8a5e6ffd81ce4d2a619fbea61d8d5cb1de4ad08aa391e4c52fb7137d326077`의 literal Q50/Q90과 TRAIN Kernel을 실제 평가에 사용했습니다. Q50총5503.4415 GPUh, Q90총24408.0632 GPUh, 추가18904.6218 GPUh이며 추가 Day18904.3588/Tail0.2629 GPUh입니다. Nominal은 Baseline에 이미 포함돼 중복 추가하지 않았습니다. A2의 실제 달성 CC4/Runtime Reserve는 각각0 GPUh이며 원본 모델은 Reserve Shortfall을 허용합니다. 따라서 FULL 가능한 A2가 모든 Q90 예약 수요를 만족한다는 뜻은 아닙니다. Prediction Scaling/May Refit/학습은0회입니다. 당일696개만 ForecastBook에 UID당1회 차감됐고 자정 전 Prefix는 중복 차감되지 않았습니다.

8. **최초 실패 코드**: Compiler의 `compile_sensitivity_policy: baseline_supported=np.all(reference_profile<=anonymous+1e-8)`에서102개 Template/3,111개 Variant가 먼저 탈락했습니다. 지원되는 Reference의 Variant는 `ReservationLedger.feasible`와 Scenario의 `hard_feasible` 판정에서 탈락했습니다. 최종 `len(scores)>=2 and ordered` 조건을 만족한 Template이 없어 `POLICY_COMPILER_ONLY`가 됩니다. Actual은 `JobEventController._policy_resource_guard`가 Select보다 먼저5763회 `OBSERVED_RESOURCE_OUTSIDE_FROZEN_TEMPLATE_SUPPORT`,53회 `NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY`를 반환했습니다. 후자의 모든 Lookup 시각은 Horizon 끝이며43개 종료 이벤트+10개 Checkpoint Round-up입니다.

9. **구현 오류와 합법적 Blocker 구분**: 실제 Blocker에 더해 숨겨진 오류를 통제 입력에서 확인했습니다. (a) Batch 지연 권한을 Pending 모든 행동의 공통 Gate로 써서 승인된 Zero-delay/Budget0 PREPLACE를 차단했습니다. (b) Grid는 남은 구간을 검사하지만 GPU는 과거 Slot까지 검사해 과거만의 Q90 초과가 미래 후보를 차단했습니다. (c) Source Site=None이면 명시적 PREPLACE 권한 검사를 건너뛰었습니다. 이 오류들이 없어도 현재 May의 미래 Slot95 초과, Actual Support Guard, 관측 권한 부족은 독립적으로 남습니다.

10. **최소 수정**: 별도 C Worktree에서 Pending Batch 권한을 양의 의도적 지연 Candidate에 적용하고, 명시적 PREPLACE는 Source Site 존재 여부와 무관하게 `can_prestart_place=True`를 요구하게 했습니다. Capacity 검사는 `total[slot:]`로 Grid의 남은 구간과 맞췄습니다. Confirmed Nonprotected 범위, Running/Migration Gate, 예산/허용 Start/GPU/Rack/WAN/Checkpoint/1회 Migration, 현재·미래96 Hard Constraint는 유지했습니다. Source V6 `f1381aab980ed7ced26184294a7abc82e1062af2bd6d41e6f0d9429b226c2358`는 Source-only Epoch입니다.

11. **Fixture**: 같은 통제 입력에서 Batch None/False의 Budget0 승인 Placement는 기존 QUEUE→수정 PREPLACE, 권한 없는 Source=None은 기존 PREPLACE→수정 START, 과거만의 초과는 기존 승인0→수정 승인10입니다. 현재/미래 Slot2/3/95 초과는 수정 전후 모두 승인0입니다. 소형 DELAY15/PREPLACE/START_NOW/CHECKPOINT_MIGRATE/STAY/QUEUE와 Rebound 반례가 PASS했습니다. Follow-up40개 Focused Test(신규16+기존24)가 PASS했습니다. 이 Fixture를 May 실제 행동으로 주장하지 않습니다.

12. **실제 May 승인·실행**: Offline 승인0, Actual 최적화 제어 선택/실행0입니다. Controller의5816개 Rule Receipt는748개 QUEUE와5068개 STAY Guard/Fallback이며 내부 정책 Lookup으로 집계하지 않았습니다. 수정된 V6의 A/M/Full96 Actual/Fresh AC는 `NOT_RUN`입니다. V5 Receipt를 V6 실행으로 재발급하지 않았습니다.

13. **기존 PR 과학적 주장**: PR223의 FULL 가능성, 활성 Job 보존 및 현재 Fresh AC 범위는 유지됩니다. Unknown 최적화 제어의 유효성·성능·전역 최적성은 계속 `NOT_ESTABLISHED`입니다. TRAIN439534행은 요청 Provenance 부재로 전부 거부돼 Cohort0이며 최소100 UID나 Backoff가 주원인이 아닙니다. 실제2320개 QoS/Protection/Batch는 UNCONFIRMED/None/None입니다. Planning의 모델 Label1488 Standby+11 Normal을 관측 권한으로 승격하지 않았고 Normal-only/8시간점/1·4·16Gang/4시간 이하 Template은 선언된 제한 범위입니다.

14. **후속 PR**: 수정 Base는 PR223 정확한 Push Commit `8f0ea6e8f97147bb425530e8d787ca89f4a05053`입니다. 본 감사 작성 시 후속 Draft PR URL/SHA는 Root 제출 대기입니다. Root가 별도 후속 PR로 제출하며 기존 PR 또는 실행 Epoch를 덮어쓰지 않습니다. 추가 Heavy Solver/AC/31일 캠페인은 시작하지 않았습니다.

## 재현 및 산출물

`audit/scripts/aggregate_root_cause.py`, `audit/job_actual/audit_job_actual.py`, `audit/source_grid/reproduce_masked_conditions.py`, `audit/scripts/replay_patch_conditions.py`에 읽기 전용 감사와 동일 입력 재현을 보존했습니다. 원본 동결 Snapshot1779개 Python SHA를 다시 검사해 변경0을 확인했습니다. Job별 최초 Guard와 도달하지 않은 추가 조건, Offline Candidate별 최초 실패와 모든 Scenario 위반을 각각 CSV/JSON으로 기록했습니다. 필수12개 파일과 Fix Diff/Before-After/Patch Validation을 별도 Namespace에 생성했습니다.
