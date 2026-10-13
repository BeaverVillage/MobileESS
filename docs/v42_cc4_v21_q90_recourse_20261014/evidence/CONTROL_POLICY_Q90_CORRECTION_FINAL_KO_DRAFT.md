# CC4 Q90 서비스 Recourse 정정 — D 최종 보고서 초안

이번 D에서는 **원래 CC4/A-stage 모델을 유지하면서 제어표의 Q90 승인 해석을 정정했다.** 같은 동결 익명 후보 4,392개 중 점수를 계산한 309개를 비교했고, 원래 Q50 hard-pass 112개만 유지했다. Q90 추가 수요를 실제 용량·원본 계통 제약 안에서 처리하고 잔량을 보존한 결과 offline 승인은 0개에서 112개로 바뀌었다. 112개 모두 서비스 CDF 하한 미달 위험이 있으므로 정상 완료·익명 Job QoS 준수로 분류하지 않는다.

Source-only Actual 96슬롯 이벤트 replay도 실행했다. 활성 작업 2,320개 중 1,690개 완료·630개 carry, GPU capacity 위반·작업 삭제 0개다. 보호·Batch·요청 QoS 권한을 새로 가정하지 않았으므로 제어표의 유연 행동 실행은 0개였다. 기존 strict E0 baseline과 GPU 점유·계산 점유·IT·PCC P/Q 배열은 정확히 같다. 새 A1/M1/A2/M2 최적화와 Fresh AC는 **NOT_RUN**이며 실제 최대 선로부하율은 **NULL**이다.

## 실행 경계와 식별자

| 구분 | 범위 |
|---|---|
| 기준 Commit | PR224 `c6f1a0f41164b7da4afe406dd692abd583a29d1e` |
| D 과학 정책 | `V42_CC4_V21_Q90_QUEUE_AWARE_RECOURSE_V1` |
| 최종 Source SHA | `fe2d882b3db6c43422436e4ea0f5dbd7f7bd1462298389031e18384293d3f0f5` |
| 최종 Policy SHA | `1f58e6a8b528d2085fafc18cf6749b7d080f07689c8e1f0f6a5f46a202efc0cd` |
| 고정 물리 기준 | 기존 V5 최종 A2/M2, 기존 D-day 초기 상태·관측 이벤트·Runtime Q50·CC4 입력 |
| 최종 검증 | Native0 Source/Fixture/Offline 후보 비교 + Source-only Actual 96슬롯 이벤트 replay |
| 미실행 | 새 A/M 최적화·새 FULL/LB/Gap·Fresh AC·Actual 전역 재최적화·Electrical P/Q repair |
| 운영 상태 | B2/B3 M 및 5월 31일 캠페인 HOLD 유지 |

첫 Attempt01은 Source `9598e69a...`로 보존했다. 원래 V5 compile/RSS 측정치를 새 실행의 측정치로 읽지 않도록 보고 필드만 정정하고 최종 Attempt02를 실행했다. Attempt01은 `audit/superseded_attempt01`에 있으며 최종 수치는 `audit/final`의 `fe2d882b...` 영수증을 사용한다. 기존 PR223/224와 V5 Full96/Fresh 영수증은 변경하거나 새 정책의 검증으로 이전하지 않았다.

## 14개 질문에 대한 답

### 1. CC4 v2.1은 실제로 어떤 시간해상도로 무엇을 예측하는가?

동결 모델 `LGBM_weighted_c1_s20260924`는 미래 24개 시간 각각에 도착할 Job의 **Lifetime GPUh 주변 Q50/Q90**를 예측한다. 시간당 해상도는 1시간이다. 해당 시간의 동시 GPU 점유나 잔여 GPU 용량을 예측하지 않는다. 24개 시간별 Q90 합계 24,408.063227 GPUh를 하루 총수요의 Q90 분위수로 부르지 않는다.

Prediction NPZ SHA는 `8a8a5e6ffd81ce4d2a619fbea61d8d5cb1de4ad08aa391e4c52fb7137d326077`이다. PR64·74의 정확한 Commit NPZ blob과 PR129의 외부 Prediction 경로·SHA 바인딩을 확인했고, 현재 NPZ bytes·May01 row 412를 다시 확인했다. PR64의 별도 DeepAR 연구 선택은 현재 V42 입력으로 승격되지 않았다.

### 2. CC4 Q50/Q90은 어느 함수에서 A1/A2로 전달되는가?

원본 NPZ의 literal row가 `C0_Q50/C0_Q90`로 들어가며, 공통 A engine의 `PlanningGridContext.bind`가 `ForecastBook`을 생성해 `v42_temporal.service.bind_forecast`에 전달한다. 원래 `v42_temporal.native.grid_binding`에도 같은 구조가 있다. `bind_forecast`는 Q50 nominal과 Q90−Q50 reserve 목표를 각각 `bind_service`에 전달한다. 원래 함수 6개 파일은 실제 V5 실행 Source SHA와 정확히 같았다.

### 3. A-stage의 x[h,t]는 무엇을 결정하는가?

`x[h,t]`는 hour h에 도착할 익명 Work 중 15분 slot t에서 처리할 **GPUh**다. `GPU[t]=4·Σ_h x[h,t]`, `Σ_s GPU[s,t]=GPU[t]`로 변환·분배한다. A-stage는 TRAIN 누적 Q10/Q90 서비스 범위 안에서 서비스 시점과 사이트 배분을 결정한다. TRAIN lag kernel은 참조 시점·deviation 기준이며 실제 x를 고정하는 실행 스케줄이 아니다.

### 4. A-stage에서 Capacity 초과 작업량은 어떻게 처리하는가?

원래 `Σ_t x[h,t]+carryout[h]=remaining W[h]`가 서비스와 이월을 보존한다. `served_before`가 있는 중간 재계획은 과거 서비스를 누적 CDF와 전체 수요 양쪽에 포함한다. 실제 물리 식은 `Known+nominal anonymous+achieved CC4 reserve+achieved runtime reserve≤site capacity`다. target과 achieved의 차이는 원래 shortfall 항이다.

저장된 A2 Q50 5,503.441472 GPUh는 3,225.157483 GPUh 서비스와 2,278.283989 GPUh carry로 보존된다. Q90−Q50 target timing은 18,904.358834 GPUh를 서비스 목표로 배분했지만 **achieved CC4 reserve는 0 GPUh**다. 이 target은 실행 가능한 예약·부하의 인증서가 아니다. 기존 A-model의 GPUh/CDF/site/물리 바인딩은 PASS이며 새 결함으로 등록하지 않았다. P1과 P2 호출 상태도 유지했다.

### 5. 기존 제어표가 Q90을 잘못 적용한 정확한 위치는 어디인가?

`sensitivity_policy._scenarios`가 A2의 `stress_site_GPU` target을 Q90 scenario delta로 반환하고, `compile_sensitivity_policy`가 이를 `OriginalGridPacket.evaluate(..., scenario_gpu=stress)` 및 site capacity 검사에 실행 부하처럼 더한 뒤 모든 scenario의 `hard_feasible`을 요구한 경계다. 원래 `bind_headroom`은 이 target을 achieved reserve와 구분하고 shortfall을 허용한다. 따라서 A-stage의 서비스·carry 설계가 없는 것이 아니라 제어표의 고정 Q90 occupancy 승인 해석과 맞지 않았다.

### 6. 기존 A-stage 서비스 배분·Carry-over를 어떻게 재사용했는가?

`load_nominal_service`는 저장된 A2의 `CC4_service`, `CC4_carryout`, `nominal_site_GPU`, `known_site_GPU`를 그대로 읽고 모든 hour의 질량·CDF·site projection을 검증해 봉인한다. D recourse는 이 Q50 물리 기준을 고정하고 **hourly Q90−Q50 추가 Work만** 처리한다. Q50 전체를 새로운 유체 스케줄로 다시 배치하지 않는다.

같은 후보의 기존 Q50 근거는 정확한 rejection 순서·action/site·모든 scenario peak 일치·전체 항목 소비를 확인해 연결했다. 지연이 다른 PREPLACE 후보를 같은 action/site로 합치지 않는다. 원래 숫자 Case·AIDC/MESS·CC4·Runtime·response·초기 상태 anchor가 같을 때만 점수를 재사용한다.

### 7. Q90 초과 작업이 Queue·Carry-over로 보존되는가?

보존된다. 원래 18,904.621755 GPUh 추가 Work는 Source 기준 recourse에서 3,848.076403 GPUh 서비스와 15,056.545352 GPUh 추가 carry로 나뉜다. 원래 nominal carry 2,278.283989 GPUh는 별도로 유지하므로 총 미완료 위험은 17,334.829341 GPUh다. 종료 시 같은 pending을 carry로 한 번 재분류하여 terminal pending은 0이며 이중 계상하지 않는다.

추가 Work backlog 면적은 250,652.582749 GPUh·h다. 서비스된 추가 Work의 평균 hour-origin lag는 13.891835시간, 최대는 23.75시간이다. 이는 집계적 Work 지연이며 실제 개별 Job의 지연 또는 E1/E2 계약 준수 수치가 아니다. CDF 하한 미달 1,057개 관측·최대 791.699451 GPUh가 남으므로 `TIMING_INFEASIBLE` 위험으로 기록한다.

500 GPUh/추가 가용 200 GPU fixture에서는 첫 1시간에 200 GPUh를 처리하고 300 GPUh가 대기한 뒤 이후 슬롯에서 처리된다. Work를 삭제하거나 처음부터 전부 terminal carry로 밀어 넣지 않는다.

### 8. Q90 Queue 모델에서 실제 Hard Constraint는 무엇인가?

서비스된 extra만 GPU·전력 부하에 추가한다. site의 잔여 capacity와 원본 signed affine 전압·선로 전류·모든 변압기 전류·16-face kVA 제약을 만족하는 양만 허용한다. 원래 scalar guard를 경계에서 유지하며 용량·정격·계수·Q50/Q90 forecast를 확대·절단하지 않는다. CDF upper는 누적 서비스 상한이며 lower 필요량을 먼저 처리하고 충족하지 못하면 명시적 timing risk로 남긴다.

이 divisible anonymous approximation은 Job별 whole-gang·Rack·WAN 스케줄의 최적해 또는 고객 QoS 증명이 아니다. Actual에서 관측된 개별 Job은 원래 whole-gang·Rack·예약·Checkpoint·WAN·Restart·공유 QoS 예산 검사를 사용한다. 이미 지난 slot의 candidate delta는 0이어야 한다. `begin=0` risk는 모든 행동에 같은 full-day counterfactual이며 현재 Actual backlog 또는 ForecastBook 잔여량으로 표현하지 않는다.

### 9. 제어표의 승인 후보 수가 어떻게 달라졌는가?

144개 template·4,392개 bounded prototype variant·309개 scored variant를 그대로 유지했다. Q50 hard-pass 112개/Q50 reject 197개도 같다. 기존 고정 Q90 승인 0개에서 D physical recourse 승인 112개가 됐다. 구성은 START_NOW 21·PREPLACE 70·STAY 21개이며 DELAY/MIGRATE 승인 0개다. 112개 모두 CDF timing risk가 있으므로 익명 서비스 정상 완료·QoS 준수의 승인이 아니다. 이 수는 개별 Actual UID 수나 실행 행동 수가 아니다.

### 10. 실제 Unknown Job의 Policy Lookup이 가능한가?

예측 편차만으로 lookup 전체를 막던 경계는 원래 물리 capacity 범위와 실제 예약 검사를 사용하도록 바뀌었다. 최종 replay의 rule dispatch는 5,816회·814 UID다. 그중 4,128회는 policy lookup의 요청 권한 gate에 도달했지만 `ACTION_QOS_AUTHORITY_UNCONFIRMED`로 거부됐다. off-grid checkpoint 1,635회와 day-end 지원 부재 53회는 별도 거부다. 4,128회는 source branch·원장으로 재구성한 도달 수이며 포괄적인 timing profiler 값으로 표현하지 않는다.

활성 2,320개 metadata는 QoS `UNCONFIRMED`, protected/batch 미확인 상태다. 원래 Known 완료 103개를 포함한 2,423개 issuer receipt의 B는 모두 0이다. Source-only D는 이 권한을 확대하지 않았으므로 실제 제어표 유연 행동·Migration은 0개, 최대 의도적 QoS 부담은 0초다. 임의 Site 선택의 FCFS admission과 명시적인 PREPLACE 정책 행동도 구분한다.

CC4 차감은 D-day 제출 696 UID에 각각 한 번, 총 696회다. 기존 prefix Unknown 78개는 이미 관측된 초기 상태로 유지하고 D-day CC4에서 다시 차감하지 않는다. 미래 완료·duration의 controller read는 0이며 actual 전역 optimizer·online grid horizon evaluation은 사용하지 않는다.

### 11. Q50/Q90에서 계통 최대 선로부하율은 어떻게 달라지는가?

승인된 112개 prototype의 Q50 remaining-horizon peak 범위는 0.641266–0.643597, Q90 queue-aware peak는 0.681858–0.705803이다. 기본 Source recourse의 Q90 peak는 0.705803이며 원본 affine hard rows 안에서 평가한 예측치다. 미처리 Work와 CDF 위험을 함께 보고하므로 선로부하 감소를 무제한 지연의 정당화로 사용하지 않는다.

Actual 최대 선로부하율은 Fresh AC를 실행하지 않아 NULL이다. 기존 strict E0와 Actual GPU/compute/IT/PCC P/Q 배열 최대 차이는 모두 0이므로 이번 Source-only D에서 실제 계통 성능 개선을 주장하지 않는다. 기존 PR223 Fresh 결과를 재발급하지 않는다.

### 12. 모든 GPUh가 서비스 또는 미완료 잔량으로 보존되는가?

독립 저장 결과 재검증에서 extra의 hour별 질량 최대 오차는 1.136868e−12 GPUh, site projection 최대 오차는 1.421085e−14 GPUh, full Q90 오차는 3.637979e−12 GPUh다. `Q90 sum = nominal served + nominal carry + extra prior/admitted + extra carry`가 성립한다. CDF upper 위반과 Source scenario capacity 위반은 0이다. CDF lower risk를 삭제하지 않았고 서비스량이 없어진 것으로 처리하지 않았다.

Actual은 작업 삭제·capacity 위반 0개, 실제 계산 17,210.68 GPUh·점유 17,510.25 GPUh다. 익명 forecast 또는 runtime reserve를 Actual 물리 GPU로 더한 양은 0이다. Actual 완료·carry Job 수와 forecast GPUh carry를 서로 다른 단위와 원장으로 유지한다.

### 13. 기존 PR224 버그 수정과 과학 정책 변경은 정확히 분리됐는가?

분리했다. PR224의 zero-delay pre-placement, past-slot capacity veto, explicit permission 수정은 완료된 기존 경계이며 D에서 재구현하지 않았다. D는 원래 source 파일을 보존하고 새 `q90_recourse.py`/`q90_policy.py`를 추가한 과학 정책이다. CC4 모델·예측·Runtime provider·원래 A-stage/P1·MESS·IEEE123 물리를 수정하지 않았다.

별도 C의 `V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1` 및 E1/E2/FLEX20/30/40은 연구용 계약 가정이다. 이 보고서의 D Source-only Actual에는 그 가정을 적용하지 않았다. C의 계약·참여율·Native0 audit와 fixture를 D의 실제 Source-only 유연 행동 또는 통합 Full 결과로 합치지 않는다.

### 14. 새 정책의 실제 May Full96/AC는 수행됐는가, 아니면 NOT_RUN인가?

**고정 A2/M2를 기준으로 한 Source-only Actual 96슬롯 이벤트 replay는 수행했다.** 이는 새 A/M 최적화부터 Fresh AC까지 연결한 통합 Full96 canary가 아니다. 새 A1/M1/A2/M2·새 FULL/LB/Gap·Fresh AC는 NOT_RUN이다. 새 Native Optimize·ML fit·calibration·공유 Solver 예산 debit은 0이며 원장은 초기화하지 않았다.

최종 queue-aware compile wall은 54.508867초, 현재 process peak RSS는 935,628,800 bytes(참조 입력 로딩 포함)다. Actual event 실행과 영수증 기록 wall은 17.571043초다. 기존 strict E0의 14.157060초는 별도 실행이며 wall 측정 범위가 달라 직접 속도 비율로 비교하지 않는다. 기존 V5 compiler 측정치는 `original_frozen_compiler_metrics`에 구분해 보존했다. B2/B3 M과 5월 전체 캠페인 HOLD는 계속 유지한다.

## 근거 파일

- `audit/cc4_service/CC4_V21_HOURLY_TARGET_CONTRACT.json`
- `audit/cc4_service/CC4_24H_96SLOT_BINDING_AUDIT.json`
- `audit/cc4_service/A_STAGE_SERVICE_TIMING_REUSE_AUDIT.json`
- `audit/recourse/Q90_WORK_MASS_CONSERVATION.json`
- `audit/recourse/INDEPENDENT_CDF_RECOURSE_REVIEW.json`
- `audit/final/Q90_HARD_GUARD_BEFORE_AFTER.json`
- `audit/final/CONTROL_POLICY_CANDIDATE_FUNNEL_BEFORE_AFTER.csv`
- `audit/final/ACTUAL_POLICY_LOOKUP_QUEUE_REPLAY.json`
- `audit/final/SOURCE_ONLY_CORRECTED_ACTUAL_FULL96.json.gz`
- `audit/CONTROL_POLICY_SOURCE_SHA_MANIFEST.json`

이 초안의 Source·Policy·시나리오·Actual 수치는 최종 Attempt02에서 읽었다. Source별 과거 영수증을 보존하며 최종 Commit·Draft PR 번호는 별도 제출 영수증에서 확정한다.
