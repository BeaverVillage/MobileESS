"""Merge independent B audits with exact population and candidate semantics."""
import hashlib
import json
from pathlib import Path
import shutil

OUT = Path('D:/v42_policy_root_cause_20261013/audit')
REAL = Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write(name, body):
    (OUT/name).write_text(json.dumps(body,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


for name in ['MAY01_POLICY_ELIGIBILITY_FUNNEL.csv','MAY01_CANDIDATE_GENERATION_AUDIT.csv',
             'MAY01_CANDIDATE_REJECTION_REASONS.csv','QOS_ZERO_BUDGET_CAUSE_AUDIT.json']:
    shutil.copyfile(OUT/'job_actual'/name, OUT/name)
for name in ['CC4_POLICY_RESOURCE_ENVELOPE_AUDIT.json','GRID_SCORE_EXECUTION_AUDIT.json']:
    shutil.copyfile(OUT/'source_grid'/name, OUT/name)
runtime = read(OUT/'job_actual/POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json')
runtime['source_freeze_grid_runtime_contribution'] = read(OUT/'source_grid/POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json')
runtime['Pending_select_timing_counter_is_not_raw_lookup_profiler'] = True
runtime['zero_select_lookup_evidence'] = 'All5816 recorded controller attempts rejected by resource guard before select/select_migration in frozen source; source-branch reconstruction, not a comprehensive function-call profiler.'
assert runtime['dispatch_unique_UIDs'] == 814
assert runtime['dispatch_unknown_UIDs'] == 766 and runtime['actual_unknown_population'] == 774
assert runtime['unknown_not_evaluated_count'] == 8
assert runtime['dispatch_known_UIDs'] == 48 and runtime['known_not_entering_unknown_policy_dispatch_UID_count'] == 1498
assert runtime['actual_UNKNOWN_Dday_pending_attempt_UIDs'] == 693 and runtime['Dday_unknown'] == 696
assert 3111 + 972 + 309 == 4392
write('POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json', runtime)
qos = read(OUT/'QOS_ZERO_BUDGET_CAUSE_AUDIT.json')
grid = read(OUT/'GRID_SCORE_EXECUTION_AUDIT.json')
cc4 = read(OUT/'CC4_POLICY_RESOURCE_ENVELOPE_AUDIT.json')
diag = read(OUT/'REAL_POLICY_FEASIBILITY_DIAGNOSTIC.json')
a = read(OUT/'WORKSTREAM_A_SUBMISSION_RECEIPT.json')
patch = read(OUT/'CONTROL_POLICY_PATCH_VALIDATION.json')
snapshot = read(OUT/'SOURCE_SNAPSHOT.json')
policy = read(REAL/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json')
facts = dict(raw_UIDs=2498, original_known_UIDs=1649, active_known_UIDs=1546,
             historical_known_UIDs=103, post_issue_unknown_UIDs=849,
             historical_unknown_UIDs=75, historical_total_UIDs=178,
             initial_running_UIDs=324, initial_pending_UIDs=1300,
             pre_Dday_observed_origin_unknown_UIDs=78, Dday_unknown_UIDs=696,
             active_origin_unknown_UIDs=774, active_UIDs=2320,
             policy_controller_dispatch_unique_UIDs=814,
             unknown_dispatch_UIDs=766, known_dispatch_UIDs=48,
             unknown_no_due_policy_event_UIDs=8, known_no_unknown_dispatch_UIDs=1498,
             Dday_pending_dispatch_UIDs=693, late_Dday_no_admit_boundary_UIDs=3,
             valid_observed_QoS_cohort_UIDs=0, extra_delay_budget_UIDs=0,
             explicit_preplacement_flag_active_UIDs=1245,
             explicit_preplacement_flag_unknown_UIDs=0,
             migration_capability_packet_UIDs=0,
             offline_templates=144, offline_materialized_variants=4392,
             offline_reference_skipped_variants=3111, offline_envelope_rejected_variants=972,
             offline_resource_guard_passed_and_scored_variants=309,
             offline_Q50_hard_passed_variants=112, offline_Q90_hard_passed_variants=0,
             offline_both_scenarios_hard_passed_variants=0,
             grid_evaluation_calls_including_bucket_endpoints=1083,
             missing_capability_migration_destination_attempts_before_materialization=792,
             offline_approved_actions=0, actual_dispatch_events=5816,
             actual_resource_outside_support_events=5763, actual_no_horizon_support_events=53,
             actual_pending_policy_attempts=748, actual_running_policy_attempts=5068,
             actual_policy_select_or_lookup_invocations_reconstructed=0,
             actual_generated_individual_candidates=0, actual_online_grid_score_calls=0,
             actual_selected_optimized_control_actions=0,
             actual_completed_UIDs=1690, actual_carryout_UIDs=630)
proof = diag['hard_failure_single_action_bound']
common = dict(workstream='B_INDEPENDENT_ROOT_CAUSE', real_execution_source_sha=snapshot['source_sha'],
              A_exact_pushed_commit=a['exact_commit'], case_sha=policy['bindings']['case_sha'],
              policy_sha=policy['policy_sha'], final_A2_anchor=policy['bindings']['aidc_anchor'],
              final_M2_anchor=policy['bindings']['mess_anchor'], initial_state_sha=policy['bindings']['initial_state_sha'],
              Native_Optimize_calls=0, production_Actual_replays=0, AC_calls=0,
              campaign_HOLD=True, campaign_auto_restart_authorized=False,
              May_optimized_action_effect='NOT_ESTABLISHED', Original_joint_global_gap='NOT_CERTIFIED')
graph = read(OUT/'source_grid/CONTROL_POLICY_EXECUTION_CALLGRAPH.json')
graph['contribution_scope'] = 'MERGED_PRODUCTION_CALLGRAPH_SOURCE_GRID_CC4_QOS_UID_EPISODE_ACTUAL'
graph['population_and_candidate_facts'] = facts
graph['job_actual_partition_receipt'] = record(OUT/'job_actual/POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json')
graph['QOS_partition_receipt'] = record(OUT/'QOS_ZERO_BUDGET_CAUSE_AUDIT.json')
graph['whole_A_M_stage_handoffs'] = read(REAL/'A_M_CALLGRAPH.json')
graph['node_evidence_scope'] = 'Recorded current execution receipts plus immutable call-site branch reconstruction; no claim of a complete Python stack profiler.'
graph['confirmed_masked_fixture_bugs'] = 3
graph['additional_source_none_permission_proof'] = record(OUT/'CONTROL_POLICY_BEFORE_AFTER_REPLAY.json')
graph['nodes'].insert(2,dict(stage='KNOWN_UNKNOWN_QOS_AUTHORITY',
    source=dict(module='v42_integration/qos.py',function='TrainingStatistics.from_records;QoSWindowProvider.issue',
                **record(OUT.parent/'v42_integration/qos.py')),
    production_executed=True, real_May01=True, fixture=False,
    counts=dict(strict_TRAIN_input_rows=439534, strict_TRAIN_accepted_UIDs=0,
                original_Known_receipts=1649, active_Known_reused=1546,
                Actual_origin_unknown_issued=774, total_immutable_receipts=2423,
                active_positive_budget=0, source_preplace_flag_Known=1245, source_preplace_flag_Unknown=0),
    first_TRAIN_reject='UNSUPPORTED_REQUEST_PROVENANCE', first_May_issuer_reason='PROTECTION_UNCONFIRMED',
    source_authority_missing_is_separate_from_minimum100_backoff=True,
    artifacts=[record(OUT/'QOS_ZERO_BUDGET_CAUSE_AUDIT.json'),record(REAL/'QOS_BUDGET_LEDGER.json')]))
write('CONTROL_POLICY_EXECUTION_CALLGRAPH.json', graph)
first = dict(schema='POLICY_COMPILER_ONLY_FIRST_FAILURE_V1', classification='POLICY_MULTIPLE_ROOT_CAUSES',
    **common, facts=facts,
    compiler_first_failure_branches=[
      dict(function='compile_sensitivity_policy', source_module='v42_integration/sensitivity_policy.py',
           condition='baseline_supported = np.all(reference_profile <= anonymous + 1e-8)',
           location_line=348, templates=102, variants=3111,
           first_reason='PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE',
           meaning='Whole gang and continuous service unavailable in the fixed anonymous reference; Known service not borrowed.'),
      dict(function='ReservationLedger.feasible', source_module='v42_integration/policy.py',
           entry='compile_sensitivity_policy resource_reason before scoring', variants=972,
           first_reason='NO_ENVELOPE_CAPACITY'),
      dict(function='compile_sensitivity_policy;OriginalGridPacket.evaluate',
           source_module='v42_integration/sensitivity_policy.py', variants=309,
           first_reason='ORIGINAL_GRID_OR_RESOURCE_HARD_CONSTRAINT',
           nominal_hard_pass=112, high_Q90_hard_pass=0,
           future_failure_independent_of_past_capacity_bug=proof)],
    exact_status_condition=dict(function='compile_sensitivity_policy',
        condition="template status is validated iff len(scores)>=2 and ordered; body validated iff any validated template",
        effect='All144 templates have empty ordered_actions. Body status POLICY_COMPILER_ONLY.'),
    Actual_first_failure=dict(function='JobEventController._policy_resource_guard',
        source_module='v42_integration/actual.py', location_line=226,
        call_sites='JobEventController.admit;JobEventController.migration before policy.select/select_migration',
        earliest_reasons={'OBSERVED_RESOURCE_OUTSIDE_FROZEN_TEMPLATE_SUPPORT':5763,
                         'NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY':53},
        events=5816, unique_UIDs=814, policy_lookup_reached=0,
        later_QOS_capability_and_template_guards_not_reached_in_recorded_execution=True,
        horizon_missing53='43 at exact end plus10 off-grid checkpoint round-up to exact end; all lookup_at=end_seconds'),
    independent_authority_blockers=dict(strict_TRAIN_provenance_filter_rows=439534,
        active_observed_qos_UNCONFIRMED=2320, active_protection_unconfirmed=2320,
        active_batch_unconfirmed=2320, all_delay_budget_zero=True,
        explicit_unknown_can_prestart_place_TRUE=0, migration_capability_packets=0,
        unassigned_source_site_None_semantics='Grid-blind initial FCFS placement may choose a compatible site; that is distinct from an explicit ranked PREPLACE authority or extra temporal budget.'),
    confirmed_masked_implementation_bugs=['universal batch gate vetoes zero-delay source-authorized placement',
       'past-only GPU overcapacity vetoes current/future action despite grid remaining horizon',
       'explicit PREPLACE permission omitted when source_site=None'],
    causal_separation='Bugs reproduced on controlled inputs and fixed in separate V6 source; current May Q90 future overload, unsupported rights and resource guard remain independent. No new May action certified.',
    receipts=[record(OUT/name) for name in ['GRID_SCORE_EXECUTION_AUDIT.json','QOS_ZERO_BUDGET_CAUSE_AUDIT.json',
        'POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json','CONTROL_POLICY_BEFORE_AFTER_REPLAY.json']])
write('POLICY_COMPILER_ONLY_FIRST_FAILURE.json', first)
matrix = dict(schema='CONTROL_POLICY_ROOT_CAUSE_MATRIX_V1', **common,
    classification='POLICY_MULTIPLE_ROOT_CAUSES', production_primary_classes=['POLICY_RESOURCE_GRID_INFEASIBLE','POLICY_QOS_CAPABILITY_BLOCKED'],
    masked_source_defect_class='POLICY_IMPLEMENTATION_BUG_CONFIRMED', facts=facts,
    causes=[
      dict(id='RC1',scope='REAL_OFFLINE', kind='LEGITIMATE_REFERENCE_RESOURCE_BLOCKER',
           first_function='compile_sensitivity_policy baseline_supported', affected_templates=102, affected_variants=3111),
      dict(id='RC2',scope='REAL_OFFLINE', kind='LEGITIMATE_RESOURCE_GRID_BLOCKER_UNDER_LITERAL_FROZEN_TARGET',
           first_function='ReservationLedger.feasible;compile_sensitivity_policy scenario hard checks',
           envelope_rejected_variants=972, Q90_rejected_scored_variants=309, future_slot95_bound=proof,
           limitation='Not a global certificate for a different capacity-respecting Q90 queue/carryout scenario.'),
      dict(id='RC3',scope='REAL_ACTUAL',kind='OBSERVED_RUNTIME_OUTSIDE_FROZEN_SUPPORT',
           first_function='JobEventController._policy_resource_guard', events=5816, UID_count=814,
           select_lookup_reached=0, reason_counts=runtime['resource_outer_first_reasons']),
      dict(id='RC4',scope='REAL_TRAIN_AND_REQUEST',kind='SOURCE_AUTHORITY_MISSING',
           first_function='TrainingStatistics.from_records provenance filter;QoSWindowProvider.issue',
           TRAIN_rows_excluded=439534, active_zero_delay_budget_UIDs=2320,
           source_known_preplace_flags=1245, source_unknown_preplace_flags=0, migration_packets=0,
           note='Budget0 does not logically imply no placement; this source separately lacks Unknown explicit placement and migration authority.'),
      dict(id='BUG1',scope='CONTROLLED_MASKED_DEFECT',kind='IMPLEMENTATION_BUG_CONFIRMED',
           first_function='FrozenSensitivityPolicy.lookup',condition='universal batchTrue before pending action-specific capability',
           fixed=True, May_counterfactual_action_effect='NOT_ESTABLISHED'),
      dict(id='BUG2',scope='CONTROLLED_MASKED_DEFECT',kind='IMPLEMENTATION_BUG_CONFIRMED',
           first_function='compile_sensitivity_policy',condition='np.any(total>cap) on all96 instead of total[slot:]',
           fixed=True, May_counterfactual_action_effect='NOT_ESTABLISHED'),
      dict(id='BUG3',scope='CONTROLLED_MASKED_DEFECT',kind='IMPLEMENTATION_BUG_CONFIRMED',
           first_function='FrozenSensitivityPolicy.candidates',condition='source_siteNone bypasses explicitPREPLACE can_prestart_place permission',
           fixed=True, May_counterfactual_action_effect='NOT_ESTABLISHED')],
    hypotheses={
      'A_POLICY_NOT_USED':'Compiler/freeze/reload connected. Runtime inner lookup did not execute because earlier resource guards rejected all attempts; no legacy fixed-PCC bypass found.',
      'B_ORIGIN_UNKNOWN_GLOBAL_EXCLUSION':'Rejected:766 Unknown and48 Known entered outer policy dispatch; OriginUnknown is not a universal no-authority mask.',
      'C_QOS_BUDGET_ZERO':'Confirmed independent source blocker:accepted TRAIN0 plus allobserved request metadata unsupported; not minimum100 or inflated reference wait.',
      'D_WRONG_RESOURCE_ENVELOPE':'SHA/time/site/array equality PASS; literal target differs from achieved reserve and live physical population. No stale A1 envelope or axis-binding error found.',
      'E_SCORE_NOT_CALLED':'Rejected offline:309 candidate variants with Q50/Q90 finite scores,1083 numeric evaluations including endpoints. Online0 is intended lookup-only plus guards.',
      'F_FALLBACK_PREEMPTS_VALID_POLICY':'Resource guard correctly fails closed outside support; no eligible real candidate was demonstrated. Masked action-capability defect separately confirmed.'},
    finite_coverage_limits=dict(time_slots=[31,70,71,72,74,76,77,80], gpu_gangs=[1,4,16],
        runtime_upper_seconds=[900,3600,14400], template_qos='normal',
        active_observed_normal_UIDs=0, active_observed_standby_UIDs=0,
        planning_model_labels={'standby':1488,'normal':11},
        coverage_is_preregistered_bounded_not_all_future_UIDs=True,
        no_May_label_retuning_or_authority_invention=True),
    fix_scope=dict(base_commit=a['exact_commit'], source_sha=patch['followup_source_sha'], tests_passed=40,
        production_V6_A_M_Actual_Fresh='NOT_RUN', no_old_receipt_transferred=True,
        followup_Draft_PR='PENDING_ROOT_SUBMISSION_AT_AUDIT_WRITE'),
    sources=[record(OUT/name) for name in ['POLICY_COMPILER_ONLY_FIRST_FAILURE.json','CONTROL_POLICY_FIX_DIFF_AUDIT.json',
        'CONTROL_POLICY_BEFORE_AFTER_REPLAY.json','CONTROL_POLICY_PATCH_VALIDATION.json']])
write('CONTROL_POLICY_ROOT_CAUSE_MATRIX.json', matrix)

report = f'''# V42 병렬 작업 결과 및 제어표 근본 원인

결론은 `POLICY_MULTIPLE_ROOT_CAUSES`입니다. 실제 May01의 후보 0은 익명 Reference 부족, 고정된 A2 Q90 수요목표 Scenario의 현재 단일 행동 범위에서의 Resource/Grid 불가능, Actual Resource Support 불일치와 독립적인 요청 권한 부족으로 설명됩니다. A2 수요목표는 Capacity-backed 실제 달성 Reserve가 아니며, 원본 P1 분해/FULL 모델은 합법적으로 Shortfall을 허용합니다. Source Binding Identity 검사는 PASS했습니다. 별도로 동결 V5에서 숨겨진 구현 오류를 재현하고 최소 수정했습니다. 수정 후 실제 May 제어 개선은 `NOT_ESTABLISHED`입니다.

## PART A — 기존 Integration PR

Draft PR: {a['PR_URL']}  
정확한 Push Commit: `{a['exact_commit']}`  
실행 Source V5: `{snapshot['source_sha']}`

A1→M1→A2→M2는 실제 B3 May01에서 실행됐습니다. A1/A2는 원본 행 FULL 검사에 통과했습니다. M1 Native85.73초, M2 Native85.967초이며 모두 TIME_LIMIT의 FULL 가능한 UB입니다. M1 rho0.641266, Restricted Bound0.268437, Restricted Gap58.14%; M2 Restricted Gap58.31%입니다. 전체 원본 Joint Global Gap은 `NOT_CERTIFIED`입니다.

Full96 Actual은 활성2,320개를 유지해1,690개 완료/630개 Carryout, Job Drop0/GPU Capacity Violation0입니다. Fresh AC는 현재11SVR/153Transformer Phase와 실제 PCC P/Q를 대상으로 PASS했습니다. 사이트 초기화는 승인된 Model Assumption이며 Kestrel 관측 사이트 또는 Source18r 수치 동등성 인증이 아닙니다. 이 결과는 Unknown 최적화 제어 효과를 증명하지 않습니다.

보수적 Shared Solver 원장의 합계는 `{a['solver_budget_used_seconds']:.6f}/3600`초이며, 정확한 Native613.072999716초와 Other Solver Wall8.212520100초를 합산한 값입니다. AC35.169244100초는 별도 비용입니다. 이 원장은 앞선 NEW Integration 시도(V4 실패/Fixture/PR222 회귀)를 포함하며 기존 Campaign·PR221 원장 비용을 합산한 값이 아닙니다. 최종 시도 Wall2970.786초, 추가 Shared Solve260.420초입니다. PR222 Warm/Cold/Raw/Matrix/Source/Monitor를 변경하거나 재실행하지 않았습니다. B2/B3 캠페인 HOLD와 자동 재시작 차단을 유지했습니다.

## PART B — 제어표 원인에 대한 14개 답

1. **Unknown 평가 대상**: Origin Unknown774개는 자정 전 관측78개와 D-day 제출696개입니다. Unknown766개와 Known48개, 합814개 UID가 정책 Controller Dispatch에 진입했습니다. 당일 Pending Dispatch는693개입니다. Unknown8개 미진입은 다음 Checkpoint 전 완료5개와 마지막 Admission Boundary 이후 제출3개입니다. Known1,498개는 Unknown 정책 Dispatch에 진입하지 않았습니다. 활성2,320개와 모델용 익명 템플릿144개를 혼동하지 않았습니다.

2. **각 권한**: 실제 관측 QoS Cohort0/추가 지연 예산0입니다. `can_prestart_place=True`는 Known 초기 Pending1,245개이며 고정 Known 명령 경로로 처리됩니다. 모든 Unknown의 명시적 Pre-placement Flag는 False이고 Migration Capability Packet은0개입니다. Source Site가 None인 최초 FCFS 배치는 명시적 PREPLACE 제어 권한과 구분했습니다. 예산0을 Pre-placement0의 근거로 쓰지 않았습니다.

3. **후보 수**: Offline 익명 Variant4,392개를 구체화했습니다. 그중3,111개는 연속 익명 Reference가 없어 평가를 Skip했고972개는 Envelope Capacity에서 거부돼309개가 수치 Score에 도달했습니다. Migration Destination792번은 Capability 부재로 Variant 구체화 전에 거부된 별도 수치입니다. Actual 실제 UID 후보 생성은0개입니다.

4. **Hard Constraint**: 수치 평가309개 중 Q50 Hard 통과112개/실패197개, Q90 Hard 통과0개/실패309개입니다. Q90은 GPU용량과 원본 Voltage/Line Current/Transformer Current/kVA에서 실패했습니다. 마지막 슬롯의 Known+Nominal259.0585 GPU와 Q90 추가750.7861 GPU는 합1009.8446 GPU로 설치780 GPU보다229.8446 GPU 많습니다. 최대 단일 Gang100 GPU를 완전히 제거해도129.8446 GPU가 초과합니다. 현재 단일 행동 템플릿의 고정 Q90 Scenario에 대한 증명이며 다른 다중 Job Queue 모델의 전역 불가능성 증명이 아닙니다.

5. **Grid Score 실행**: 실제 동결 Compiler에서309개 Variant에 두 Scenario의 유한 Score가 저장됐고 Runtime Bucket Endpoint를 포함해1083회 수치 평가했습니다. Actual Online Grid Score와 Global MILP는0회입니다. Runtime Timing의 `lookup_calls=0`은 Pending Select Timing Sample 수이며 전체 Lookup Profiler가 아닙니다. 내부 Select/Lookup0은 아래 모든 Dispatch의 Guard Reject와 동결 Call Site로 재구성했습니다.

6. **A-stage 연결**: 최종 A2의96×12 익명 Envelope, Known/Nominal/Reserve 배열과 여섯 Distribution Field SHA가 일치합니다. A1의 오래된 Envelope를 사용하지 않았습니다. 최종 A2 Anchor `{policy['bindings']['aidc_anchor']}`와 M2 Anchor `{policy['bindings']['mess_anchor']}`가 Freeze/Reload/Actual Receipt에 연결됩니다.

7. **CC4 연결**: `LGBM_weighted_c1_s20260924`, Prediction SHA `{policy['bindings']['cc4_sha']}`의 literal Q50/Q90과 TRAIN Kernel을 실제 평가에 사용했습니다. Q50총5503.4415 GPUh, Q90총24408.0632 GPUh, 추가18904.6218 GPUh이며 추가 Day18904.3588/Tail0.2629 GPUh입니다. Nominal은 Baseline에 이미 포함돼 중복 추가하지 않았습니다. A2의 실제 달성 CC4/Runtime Reserve는 각각0 GPUh이며 원본 모델은 Reserve Shortfall을 허용합니다. 따라서 FULL 가능한 A2가 모든 Q90 예약 수요를 만족한다는 뜻은 아닙니다. Prediction Scaling/May Refit/학습은0회입니다. 당일696개만 ForecastBook에 UID당1회 차감됐고 자정 전 Prefix는 중복 차감되지 않았습니다.

8. **최초 실패 코드**: Compiler의 `compile_sensitivity_policy: baseline_supported=np.all(reference_profile<=anonymous+1e-8)`에서102개 Template/3,111개 Variant가 먼저 탈락했습니다. 지원되는 Reference의 Variant는 `ReservationLedger.feasible`와 Scenario의 `hard_feasible` 판정에서 탈락했습니다. 최종 `len(scores)>=2 and ordered` 조건을 만족한 Template이 없어 `POLICY_COMPILER_ONLY`가 됩니다. Actual은 `JobEventController._policy_resource_guard`가 Select보다 먼저5763회 `OBSERVED_RESOURCE_OUTSIDE_FROZEN_TEMPLATE_SUPPORT`,53회 `NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY`를 반환했습니다. 후자의 모든 Lookup 시각은 Horizon 끝이며43개 종료 이벤트+10개 Checkpoint Round-up입니다.

9. **구현 오류와 합법적 Blocker 구분**: 실제 Blocker에 더해 숨겨진 오류를 통제 입력에서 확인했습니다. (a) Batch 지연 권한을 Pending 모든 행동의 공통 Gate로 써서 승인된 Zero-delay/Budget0 PREPLACE를 차단했습니다. (b) Grid는 남은 구간을 검사하지만 GPU는 과거 Slot까지 검사해 과거만의 Q90 초과가 미래 후보를 차단했습니다. (c) Source Site=None이면 명시적 PREPLACE 권한 검사를 건너뛰었습니다. 이 오류들이 없어도 현재 May의 미래 Slot95 초과, Actual Support Guard, 관측 권한 부족은 독립적으로 남습니다.

10. **최소 수정**: 별도 C Worktree에서 Pending Batch 권한을 양의 의도적 지연 Candidate에 적용하고, 명시적 PREPLACE는 Source Site 존재 여부와 무관하게 `can_prestart_place=True`를 요구하게 했습니다. Capacity 검사는 `total[slot:]`로 Grid의 남은 구간과 맞췄습니다. Confirmed Nonprotected 범위, Running/Migration Gate, 예산/허용 Start/GPU/Rack/WAN/Checkpoint/1회 Migration, 현재·미래96 Hard Constraint는 유지했습니다. Source V6 `{patch['followup_source_sha']}`는 Source-only Epoch입니다.

11. **Fixture**: 같은 통제 입력에서 Batch None/False의 Budget0 승인 Placement는 기존 QUEUE→수정 PREPLACE, 권한 없는 Source=None은 기존 PREPLACE→수정 START, 과거만의 초과는 기존 승인0→수정 승인10입니다. 현재/미래 Slot2/3/95 초과는 수정 전후 모두 승인0입니다. 소형 DELAY15/PREPLACE/START_NOW/CHECKPOINT_MIGRATE/STAY/QUEUE와 Rebound 반례가 PASS했습니다. Follow-up40개 Focused Test(신규16+기존24)가 PASS했습니다. 이 Fixture를 May 실제 행동으로 주장하지 않습니다.

12. **실제 May 승인·실행**: Offline 승인0, Actual 최적화 제어 선택/실행0입니다. Controller의5816개 Rule Receipt는748개 QUEUE와5068개 STAY Guard/Fallback이며 내부 정책 Lookup으로 집계하지 않았습니다. 수정된 V6의 A/M/Full96 Actual/Fresh AC는 `NOT_RUN`입니다. V5 Receipt를 V6 실행으로 재발급하지 않았습니다.

13. **기존 PR 과학적 주장**: PR223의 FULL 가능성, 활성 Job 보존 및 현재 Fresh AC 범위는 유지됩니다. Unknown 최적화 제어의 유효성·성능·전역 최적성은 계속 `NOT_ESTABLISHED`입니다. TRAIN439534행은 요청 Provenance 부재로 전부 거부돼 Cohort0이며 최소100 UID나 Backoff가 주원인이 아닙니다. 실제2320개 QoS/Protection/Batch는 UNCONFIRMED/None/None입니다. Planning의 모델 Label1488 Standby+11 Normal을 관측 권한으로 승격하지 않았고 Normal-only/8시간점/1·4·16Gang/4시간 이하 Template은 선언된 제한 범위입니다.

14. **후속 PR**: 수정 Base는 PR223 정확한 Push Commit `{a['exact_commit']}`입니다. 본 감사 작성 시 후속 Draft PR URL/SHA는 Root 제출 대기입니다. Root가 별도 후속 PR로 제출하며 기존 PR 또는 실행 Epoch를 덮어쓰지 않습니다. 추가 Heavy Solver/AC/31일 캠페인은 시작하지 않았습니다.

## 재현 및 산출물

`audit/scripts/aggregate_root_cause.py`, `audit/job_actual/audit_job_actual.py`, `audit/source_grid/reproduce_masked_conditions.py`, `audit/scripts/replay_patch_conditions.py`에 읽기 전용 감사와 동일 입력 재현을 보존했습니다. 원본 동결 Snapshot1779개 Python SHA를 다시 검사해 변경0을 확인했습니다. Job별 최초 Guard와 도달하지 않은 추가 조건, Offline Candidate별 최초 실패와 모든 Scenario 위반을 각각 CSV/JSON으로 기록했습니다. 필수12개 파일과 Fix Diff/Before-After/Patch Validation을 별도 Namespace에 생성했습니다.
'''
(OUT/'CONTROL_POLICY_ROOT_CAUSE_FINAL_KO.md').write_text(report,encoding='utf-8')
required = ['CONTROL_POLICY_EXECUTION_CALLGRAPH.json','MAY01_POLICY_ELIGIBILITY_FUNNEL.csv',
 'MAY01_CANDIDATE_GENERATION_AUDIT.csv','MAY01_CANDIDATE_REJECTION_REASONS.csv','QOS_ZERO_BUDGET_CAUSE_AUDIT.json',
 'CC4_POLICY_RESOURCE_ENVELOPE_AUDIT.json','GRID_SCORE_EXECUTION_AUDIT.json','POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json',
 'POLICY_COMPILER_ONLY_FIRST_FAILURE.json','CONTROL_POLICY_ROOT_CAUSE_MATRIX.json','CONTROL_POLICY_SMALL_FIXTURE_RESULTS.json',
 'CONTROL_POLICY_ROOT_CAUSE_FINAL_KO.md']
assert all((OUT/name).exists() for name in required)
write('WORKSTREAM_B_ARTIFACT_MANIFEST.json',dict(schema='WORKSTREAM_B_ARTIFACT_MANIFEST_V1',status='COMPLETE',
    required_file_count=12, required_files=[record(OUT/name) for name in required],
    fix_files=[record(OUT/name) for name in ['CONTROL_POLICY_FIX_DIFF_AUDIT.json','CONTROL_POLICY_BEFORE_AFTER_REPLAY.json',
        'CONTROL_POLICY_PATCH_VALIDATION.json']], population_and_candidate_assertions_PASS=True,
    exact_A_base=a['exact_commit'], source_V5=snapshot['source_sha'], source_V6=patch['followup_source_sha'],
    real_May_effect='NOT_ESTABLISHED', production_V6='NOT_RUN'))
print(json.dumps({'required_files':12,'status':'COMPLETE','classification':matrix['classification'],
                  'V5':snapshot['source_sha'],'V6':patch['followup_source_sha'],'actual_lookup_reconstructed':0}))
