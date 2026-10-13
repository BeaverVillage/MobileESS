"""Read frozen V5 production evidence; write B audit namespace only."""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path('D:/v42_policy_root_cause_20261013')
OUT=ROOT/'audit/source_grid'
RESULT=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
PRIOR=Path('D:/v42_integration_validation_20261013/CC4_POLICY_SOURCE_AUDIT')
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import numpy as np
from v42_integration.policy import digest
from v42_integration.sensitivity_policy import FrozenSensitivityPolicy


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def record(path):
    path=Path(path);raw=path.read_bytes()
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
def source(module,function):
    path=ROOT/module;tree=ast.parse(path.read_text(encoding='utf8'))
    name=function.rsplit('.',1)[-1]
    nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    return dict(module=module,function=function,**record(path),lines=[n.lineno for n in nodes])
def write(name,doc):
    (OUT/name).write_text(json.dumps(doc,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')


snapshot=read(ROOT/'audit/SOURCE_SNAPSHOT.json')
policy_path=RESULT/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'
policy=read(policy_path);frozen=read(RESULT/'PLANNING_FREEZE.json')
aidc=read(RESULT/'A2/A_RESULT.json');a1=read(RESULT/'A1/A_RESULT.json')
resource=read(RESULT/'A_STAGE_RESOURCE_ENVELOPE.json')
cc4=read(RESULT/'CC4_V21_SOURCE_BINDING_AUDIT.json')
runtime=read(RESULT/'CONTROL_POLICY_RUNTIME_MEMORY.json')
reload_receipt=read(RESULT/'CONTROL_POLICY_RELOAD_TEST.json')
reload_consumer=read(RESULT/'RELOAD_CONSUMPTION_RECEIPT.json')
manifest=read(RESULT/'CONTROL_POLICY_SHA_MANIFEST.json')
actual=read(RESULT/'ACTUAL_RESULT.json')
rules=read(RESULT/'RULE_CONSUMPTION_RECEIPT.json')
depletion=read(RESULT/'CC4_DEPLETION_LEDGER.json')
fresh=read(RESULT/'FRESH_PHYSICAL/FRESH_PHYSICAL_RESULT.json')
mess=read(RESULT/'MESS_ACTUAL_EXECUTION_RECEIPT.json')
diagnostic_path=Path('D:/v42_integration_validation_20261013/POLICY_V5_OFFLINE_FIXTURE/REAL_POLICY_FEASIBILITY_DIAGNOSTIC.json')
diagnostic=read(diagnostic_path)
signed=read(PRIOR/'SIGNED_GRID_AUTHORITY_SOURCE_AUDIT.json')
base=dict(schema='FROZEN_V5_PRODUCTION_SOURCE_RECEIPT_AUDIT_V1',
    written_utc=datetime.now(timezone.utc).isoformat(),workstream='B_READ_ONLY_SOURCE_GRID',
    A_exact_pushed_commit='8f0ea6e8f97147bb425530e8d787ca89f4a05053',
    source_sha=snapshot['source_sha'],source_snapshot=record(ROOT/'audit/SOURCE_SNAPSHOT.json'),
    evidence_kind='REAL_MAY01_V5_RECEIPTS_WITH_SEPARATELY_LABELLED_CONTROLLED_FIXTURES',
    Native_Optimize_calls=0,Actual_replays=0,Fresh_AC_calls=0,source_edits=0,
    result_tree_read_only=True,current_bindings=policy['bindings'])
assert base['source_sha']==frozen['source_freeze']['source_sha']==policy['bindings']['science_sha']
assert record(ROOT/'v42_integration/sensitivity_policy.py')['sha256']==policy['compiler_source_sha']

fields=('nominal_site_GPU','reserve_site_GPU','known_site_GPU','resource_sites','CC4_reserve_service','CC4_reserve_carryout')
dist={k:aidc[k] for k in fields};sites=resource['resource_sites']
nominal=np.asarray([aidc['nominal_site_GPU'][s] for s in sites]).T
known=np.asarray([aidc['known_site_GPU'][s] for s in sites]).T
stress=np.asarray([aidc['reserve_site_GPU'][s] for s in sites]).T
caps=np.asarray([max(policy['original_grid_authority']['rack_compatibility'][s]) for s in sites],float)
assert float(caps.sum())==780
rebuilt=np.full_like(nominal,np.nan)
for row in policy['envelope']:
    rebuilt[round((row['slot_start']-policy['begin_seconds'])/900),sites.index(row['site'])]=row['gpu_capacity']
assert np.array_equal(rebuilt,nominal)
assert digest(dist)==aidc['resource_distribution_sha']==resource['resource_distribution_sha']
assert all(resource[k]==aidc[k] for k in fields)
assert np.array_equal(np.asarray(policy['runtime_resource_baseline_GPU']),known+nominal)
support=policy['runtime_resource_support']
assert np.array_equal(np.asarray(support['lower_GPU']),known+nominal)
assert np.array_equal(np.asarray(support['upper_GPU']),known+nominal+stress)
assert aidc['aidc_anchor']==policy['bindings']['aidc_anchor']==frozen['aidc_anchor']
assert frozen['MESS_plan']['plan_sha']==mess['plan_sha']==policy['bindings']['mess_anchor']
q=policy['scenario_audit'];total=known+nominal+stress
profiles=[dict(slot=t,known_GPU=float(known[t].sum()),nominal_GPU=float(nominal[t].sum()),
    Q90_extra_target_GPU=float(stress[t].sum()),Q90_total_GPU=float(total[t].sum()),
    site_capacity_violations=int(np.sum(total[t]>caps+1e-8))) for t in range(96)]
rule_reasons=Counter(r['reason'] for r in rules)
rule_actions=Counter(r['action'] for r in rules)
source_receipts=[record(ROOT/rel) for rel in ('v42_integration/a_engine.py',
    'v42_integration/production_case.py','v42_integration/cc4_policy_inputs.py',
    'v42_integration/coordinator.py','v42_integration/sensitivity_policy.py',
    'v42_integration/actual.py','v42_integration/actual_validation.py',
    'v42_integration/policy.py','v42_job_capability.py')]

resource_audit=dict(base,
    status='FINAL_A2_CC4_RESOURCE_BINDING_PASS;FROZEN_Q90_TARGET_SCENARIO_NOT_CAPACITY_FEASIBLE',
    source_receipts=source_receipts,artifact_receipts=[record(RESULT/n) for n in
        ('A2/A_RESULT.json','A_STAGE_RESOURCE_ENVELOPE.json','CC4_V21_SOURCE_BINDING_AUDIT.json',
         'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json','CC4_DEPLETION_LEDGER.json')],
    final_A_stage='A2',final_MESS_stage='M2',stale_A1_envelope_reused=False,
    A1_anchor=a1['aidc_anchor'],A2_anchor=aidc['aidc_anchor'],
    equality_checks=dict(resource_distribution_SHA=True,all_six_exported_fields_exact=True,
        envelope_GPU_equals_final_A2_nominal_bytewise=True,absolute_seconds_axis=True,
        full96_by12_site_axis=True,known_GPU_kept_outside_anonymous_envelope=True,
        runtime_baseline_known_plus_nominal_exact=True,runtime_support_lower_baseline_exact=True,
        runtime_support_upper_baseline_plus_Q90_extra_exact=True,final_M2_anchor_exact=True),
    model_id=cc4['model_id'],prediction_index=cc4['prediction_index'],
    prediction_sha=cc4['prediction_sha'],runtime_sha=cc4['runtime_sha'],kernel_sha=cc4['kernel_sha'],
    prediction_source_receipts=cc4['source_receipts'],convolution=cc4['convolution'],
    forecast_mass=dict(Q50_GPUh=q['Q50_GPUh'],Q90_GPUh=q['Q90_GPUh'],
        Q90_minus_Q50_GPUh=q['Q90_minus_Q50_GPUh'],nominal_served_GPUh=float(nominal.sum()/4),
        nominal_carryout_GPUh=q['nominal_carryout_GPUh'],stress_day_GPUh=float(stress.sum()/4),
        stress_carryout_GPUh=q['Q90_stress_tail_GPUh'],
        nominal_mass_residual_GPUh=float(nominal.sum()/4+q['nominal_carryout_GPUh']-q['Q50_GPUh']),
        stress_mass_residual_GPUh=float(stress.sum()/4+q['Q90_stress_tail_GPUh']-q['Q90_minus_Q50_GPUh'])),
    reserve_semantic_audit=diagnostic['reserve_semantics'],all96_target_profile=profiles,
    target_versus_achieved=dict(target_role='FROZEN_ARRIVAL_TARGET_DEMAND',
        achieved_CC4_site_GPU_sum=float(sum(sum(v) for v in aidc['achieved_CC4_reserve_site_GPU'].values())),
        achieved_runtime_site_GPU_sum=float(sum(sum(v) for v in aidc['achieved_runtime_reserve_site_GPU'].values())),
        shortfall_permitted_in_original_P1=True,P2_calls=aidc['P2_calls'],
        source_labels_explicit_not_achieved_reserve=True,
        source_binding_bug=False,
        design_limitation='P1 optimizes nominal power and permits reserve shortfall; its CDF-constrained target timing/site arrays are not a capacity-backed reserve certificate. The compiler evaluates this literal fixed target as a demand stress, so even baseline can violate hard rows. This proves the selected fixed stress unsupported, not all possible multi-job queue policies infeasible.',
        substituting_achieved_zero_or_clipping_target_allowed=False,
        hypothetical_target_refinement_requires_new_scientific_scope=True),
    single_action_future_failure=diagnostic['hard_failure_single_action_bound'],
    Actual_forecast_depletion=dict(entries=len(depletion),unique_UIDs=len({r['uid'] for r in depletion}),
        max_depletion_count=max(r['depletion_count'] for r in depletion),
        all_anonymous_forecast_is_physical_false=all(r['anonymous_forecast_is_physical'] is False for r in depletion),
        once_per_observed_Dday_unknown_UID=True,prefix_unknown_depletion=False),
    Actual_guard=dict(controller_rule_events=len(rules),reason_counts=dict(rule_reasons),
        literal_policy_lookup_calls=runtime['lookup_calls'],
        literal_lookup_zero_evidence='SOURCE_BRANCH_RECONSTRUCTION: every recorded controller rule event failed the guard before select/select_migration',
        timing_counter_scope='runtime.lookup_calls is len(_lookup_times) from timed Pending select returns; it does not instrument raw lookup or select_migration',
        guard_precedes_select=True,forecast_support_is_necessary_guard_not_AC_certificate=True,
        no_support_events_at_policy_day_end=all(r['frozen_support_control_seconds']==policy['end_seconds']
            for r in rules if r['reason']=='NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY')),
    TRAIN_burst=dict(status=q['TRAIN_BURST_STRESS'],invented_burst_vectors=False,
        reason='Exact frozen TRAIN individual burst histories/provenance are unavailable; aggregate lifetime CDF/kernel does not establish request burst support.'),
    May_policy_effect='NOT_ESTABLISHED',forecast_scaled_or_refit=False)
write('CC4_POLICY_RESOURCE_ENVELOPE_AUDIT.json',resource_audit)

templates=policy['templates'];score_rows=[r for t in templates for r in t['scenario_comparisons']]
rejections=Counter(r['reason'] for t in templates for r in t['rejected_candidates'])
scenario_counts={}
for name in ('NOMINAL_Q50','HIGH_DEMAND_Q90'):
    detailed=[r['scenarios'][name] for t in templates for r in t['rejected_candidates'] if 'scenarios' in r]
    values=[r['scenario_scores'][name] for r in score_rows]
    assert len(values)==309 and all(np.isfinite(values))
    scenario_counts[name]=dict(serialized_scored_candidates=len(values),
        hard_feasible=sum(r['hard_feasible'] for r in detailed),hard_infeasible=sum(not r['hard_feasible'] for r in detailed),
        min_remaining_peak=min(values),max_remaining_peak=max(values))
unsupported=sum(any(r['reason']=='PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE' for r in t['rejected_candidates']) for t in templates)
assert unsupported==102 and len(score_rows)==309
grid_audit=dict(base,status='REAL_OFFLINE_GRID_SCORE_EXECUTED;ALL_Q90_VARIANTS_HARD_REJECTED',
    source_receipts=source_receipts,artifact_receipts=[record(policy_path),record(diagnostic_path),record(PRIOR/'SIGNED_GRID_AUTHORITY_SOURCE_AUDIT.json')],
    call_sources=[source('v42_integration/sensitivity_policy.py',name) for name in
        ('compile_sensitivity_policy','OriginalGridPacket.evaluate','OriginalGridPacket._at_slot')],
    counters=dict(templates=144,generated_counted_variants=policy['metrics']['bounded_candidates'],
        first_reference_unsupported_templates=unsupported,reference_supported_templates=144-unsupported,
        skipped_variants_under_unsupported_reference=3111,resource_guard_rejected_variants=972,
        serialized_candidate_scores=len(score_rows),approved_ordered_actions=sum(len(t['ordered_actions']) for t in templates),
        grid_evaluation_cache_misses=policy['metrics']['grid_evaluation_calls'],
        grid_evaluation_cache_hits=policy['metrics']['cache_hits'],
        migration_capability_refusals_outside_generated_variant_partition=rejections['NO_AUTHORITY_CAPABILITY_UNCONFIRMED']),
    generated_partition_equation='4392 = 3111 skipped under unsupported reference + 972 resource-guard rejected + 309 numerically scored',
    count_meanings='1083 is cached evaluator misses across scenario/endpoints and baseline selection;309 is serialized candidate variants. Rejection reason occurrences include separate migration attempts and template-reference reasons; do not sum them as4392.',
    scenario_counts=scenario_counts,rejection_reason_occurrences_not_exclusive_partition=dict(rejections),
    missing_versus_none=dict(score_function_not_called_for_reference_unsupported=True,
        skipped_score_representation='empty candidate_scores;not a numerical zero',
        scored_Q50_and_Q90_values_finite=True,no_missing_score_coerced_zero_or_infinity=True,
        selected_action_none_due_hard_rejection=True,no_ranked_score_vs_missing_confusion=True,
        median_actual_lookup_latency_null_because_lookup_calls_zero=True),
    exact_signed_original_operator={k:signed[k] for k in ('slots','control_count','branch_phase_count',
        'transformer_phase_count','line_phase_count','signed_face_count','anchor_loading_max_error',
        'signed_derivative_max_error','plus_minus_1kW_fixed_face_max_error','current_denominators',
        'thermal_rating_bytes_equal','absolute_value_sensitivity_used')},
    physical_and_direction_checks=dict(objective=policy['objective'],minimize_peak=True,
        signed_16face_current_correction=True,negative_sensitivity_preserved=True,
        AIDC_Q_coupled_into_aidc_load_kw_axis_once=True,voltage_squared_pu=True,
        transformer_current_and_kVA_guards=True,all_remaining_slots_including_rebound=True,
        candidate_delta='after GPU profile minus same reference profile',
        runtime_piecewise_endpoints_seconds=True,nominal_service_preserved=True,
        Q50_already_in_baseline=True,Q90_extra_added_once_offline=True,Q90_added_to_Actual=False,
        final_MESS_anchor_matches=True,FULL_or_Fresh_AC_certificate_from_score=False),
    direct_production_first_failures=dict(reference_template_gate=102,
        scored_Q90_hard_infeasible=309,other42_templates_no_ordered_action=True,
        future_slot95_obstruction=diagnostic['hard_failure_single_action_bound']),
    confirmed_separate_fixture_implementation_bugs=[record(OUT/'PREPLACE_ZERO_BUDGET_UNIVERSAL_MASK_REPRODUCTION.json'),
        record(OUT/'PAST_SLOT_CAPACITY_VETO_REPRODUCTION.json')],
    past_capacity_scope_bug=dict(frozen_condition='np.any(total>caps) across all96 slots while grid evaluates remaining_slot onward',
        fixture_past_only_overflow_rejects_valid_future=True,
        real_May_future_slot95_obstruction_survives_scope_fix=True,
        real_May_candidate_approval_after_fix_claimed=False),
    current_real_status=policy['status'],May_policy_effect='NOT_ESTABLISHED')
write('GRID_SCORE_EXECUTION_AUDIT.json',grid_audit)

loaded=FrozenSensitivityPolicy.load(policy_path,bindings=policy['bindings'])
legacy=FrozenSensitivityPolicy.load(RESULT/'UNKNOWN_CONTROL_POLICY.json',bindings=policy['bindings'])
assert loaded.sha==legacy.sha==reload_receipt['policy_sha']==manifest['policy_sha']==reload_consumer['policy_sha']
assert loaded.document==legacy.document==policy
assert all(r['policy_sha']==loaded.sha for r in rules)
binding_checks={k:policy['bindings'][k]==frozen[k]==manifest['bindings'][k]==reload_receipt['bindings'][k]==reload_consumer['anchors'][k]
    for k in policy['bindings']}
assert all(binding_checks.values())
write('POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json',dict(base,
    status='PRODUCTION_FREEZE_RELOAD_BINDINGS_PASS;ACTUAL_RESOURCE_GUARD_BLOCKED_LOOKUP',
    policy_sha=loaded.sha,policy_file=record(policy_path),legacy_consumer_file=record(RESULT/'UNKNOWN_CONTROL_POLICY.json'),
    semantic_document_equal=True,policy_file_byte_equal=policy_path.read_bytes()==(RESULT/'UNKNOWN_CONTROL_POLICY.json').read_bytes(),
    current_nine_binding_checks=binding_checks,final_A_stage=manifest['final_A_stage'],final_MESS_stage=manifest['final_MESS_stage'],
    stale_A1_policy_reused=manifest['stale_A1_policy_reused'],production_reloaded_before_actual=reload_receipt['reloaded_before_actual'],
    current_offline_readonly_load_check=True,source_functions=[source('v42_integration/coordinator.py','run_arm'),
        source('v42_integration/sensitivity_policy.py','FrozenSensitivityPolicy.load'),
        source('v42_integration/actual.py','JobEventController._policy_resource_guard'),
        source('v42_integration/actual.py','JobEventController.admit'),source('v42_integration/actual.py','JobEventController.migration')],
    artifact_receipts=[record(RESULT/n) for n in ('CONTROL_POLICY_SHA_MANIFEST.json','CONTROL_POLICY_RELOAD_TEST.json',
        'RELOAD_CONSUMPTION_RECEIPT.json','CONTROL_POLICY_RUNTIME_MEMORY.json','RULE_CONSUMPTION_RECEIPT.json')],
    literal_runtime_metrics=runtime,rule_ledger_count=len(rules),rule_unique_UIDs=len({r['uid'] for r in rules}),
    runtime_lookup_counter_measurement_scope='Pending select timing sample count only;raw lookup and select_migration not directly instrumented',
    zero_actual_literal_lookup_evidence='All5816 controller rule records contain the guard reason, whose branch bypasses both select and select_migration;source branch reconstruction,not a complete profiler counter',
    rule_action_counts=dict(rule_actions),rule_first_reason_counts=dict(rule_reasons),
    guard_wrapper_called_5816_not_literal_policy_lookup=True,
    literal_select_lookup_not_reached_for_all_recorded_events=True,
    selected_policy_optimized_actions=0,Actual_executed_optimized_actions=0,
    safe_baseline_fallback='Common JobEventController._reference_decision then PR125 EpisodeLedger/reservation admission',
    legacy_fixed_PCC_replay_used=False,source_input_or_anchor_mismatch=False,
    online_grid_evaluation_calls=0,online_global_optimizer_calls=0,
    runtime_missing_support_horizon_scope=dict(events=rule_reasons['NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY'],
        all_at_end_seconds=True,end_seconds=policy['end_seconds'],missing_binding_or_file=False),
    source_capability_semantics=dict(delay_budget_independent_of_initial_site_choice=True,
        frozen_universal_batch_gate_bug_separate=True,source_site_none_distinct_from_authorized_PREPLACE=True,
        can_prestart_place_false_alone_does_not_classify_unassigned_FCFS_initial_placement=True,
        all_real_authority_missing_claim_scope='Source protected/QoS/batch/capability must be evaluated independently; compiler and resource guards independently mask literal lookup.'),
    Event30=policy['Event30'],May_policy_effect='NOT_ESTABLISHED'))

def node(stage,module,function,count,outputs,executed=True,reason=None,**extra):
    return dict(stage=stage,source=source(module,function),production_executed=executed,
        evidence='CURRENT_REAL_RECEIPT_AND_FROZEN_SOURCE_BRANCH',count=count,
        outputs=[record(RESULT/p) for p in outputs],skip_or_reject_reason=reason,
        AIDC_anchor=policy['bindings']['aidc_anchor'],MESS_anchor=policy['bindings']['mess_anchor'],
        fixture=False,**extra)
nodes=[
    node('A1_A2_OPTIMIZE','v42_integration/a_engine.py','optimize_aidc',2,['A1/A_RESULT.json','A2/A_RESULT.json'],
        final_output_consumed='A2',M_full_joint_optimality_claimed=False),
    node('A2_RESOURCE_ENVELOPE','v42_integration/production_case.py','compile_production_control_policy',1152,
        ['A_STAGE_RESOURCE_ENVELOPE.json'],array_shape=[96,12],known_immutable=True),
    node('ORIGINAL_GRID_RESPONSE_BINDING','v42_integration/sensitivity_policy.py','build_grid_packet',96,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'],coefficient_SHA=policy['bindings']['response_sha']),
    node('CC4_RUNTIME_QOS_BINDING','v42_integration/production_case.py','compile_production_control_policy',1,
        ['CC4_V21_SOURCE_BINDING_AUDIT.json'],new_training_calls=0),
    node('BOUNDED_ANONYMOUS_CONDITIONS','v42_integration/sensitivity_policy.py','bounded_prototypes',144,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'],future_individual_UIDs=0),
    node('CANDIDATE_GENERATION','v42_integration/sensitivity_policy.py','compile_sensitivity_policy',4392,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json']),
    node('REFERENCE_SUPPORT_GATE','v42_integration/sensitivity_policy.py','compile_sensitivity_policy',102,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'],reason='PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE',
        count_unit='first-rejected templates;3111 associated generated variants skipped'),
    node('RESOURCE_GUARD','v42_integration/policy.py','ReservationLedger.feasible',972,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'],reason='NO_ENVELOPE_CAPACITY',count_unit='rejected generated variants'),
    node('GRID_SCORE','v42_integration/sensitivity_policy.py','OriginalGridPacket.evaluate',1083,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json','Q50_Q90_BURST_POLICY_COMPARISON.json'],
        serialized_variants=309,Q50_hard_feasible=112,Q90_hard_feasible=0,count_unit='cache miss evaluator calls'),
    node('OFFLINE_APPROVAL','v42_integration/sensitivity_policy.py','compile_sensitivity_policy',0,
        ['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'],reason='ALL_REMAINING_SCORED_Q90_VARIANTS_HARD_INFEASIBLE'),
    node('POLICY_FREEZE_RELOAD','v42_integration/coordinator.py','run_arm',1,
        ['PLANNING_FREEZE.json','CONTROL_POLICY_RELOAD_TEST.json','CONTROL_POLICY_SHA_MANIFEST.json'],
        semantic_equal=True,expanded_bindings=9),
    node('OBSERVED_JOB_EVENTS','v42_integration/actual.py','run_actual',len(actual['job_event_ledger']),
        ['JOB_EVENT_LEDGER.json'],active_job_UIDs=actual['receipt']['submitted_jobs'],Dday_depleted_unknown_UIDs=len(depletion)),
    node('ACTUAL_RESOURCE_SUPPORT_GUARD','v42_integration/actual.py','JobEventController._policy_resource_guard',len(rules),
        ['RULE_CONSUMPTION_RECEIPT.json'],reason=dict(rule_reasons)),
    node('LITERAL_FROZEN_POLICY_SELECT_LOOKUP','v42_integration/sensitivity_policy.py','FrozenSensitivityPolicy.lookup',0,
        ['CONTROL_POLICY_RUNTIME_MEMORY.json'],executed=False,reason='PRECEDING_ACTUAL_RESOURCE_GUARD_REJECTED_ALL5816_EVENTS'),
    node('BASELINE_FALLBACK_ACTION','v42_integration/actual.py','JobEventController._reference_decision',len(rules),
        ['RULE_CONSUMPTION_RECEIPT.json','ACTUAL_QUEUE_LEDGER.json'],count_unit='fallback/reject controller records,not unique starts',
        action_counts=dict(rule_actions),optimized_actions=0),
    node('GPU_WAN_RESERVATION','v42_integration/actual.py','JobEventController.admit',
        len(actual['reservation_ledger']['reservations']),['RESERVATION_LEDGER.json'],
        count_unit='reservation UID entries',checkpoint_migrations=len(actual['migration_receipts']),
        policy_optimized_reservations=0),
    node('ACTUAL_OCCUPANCY_PCC_POWER','v42_integration/actual.py','run_actual',96,
        ['ACTUAL_OCCUPANCY_POWER_TRACE.npz','ACTUAL_RESULT.json'],
        planning_power_copied=actual['physical']['planning_power_copied'],
        forecast_added_as_Actual=actual['physical']['anonymous_forecast_or_runtime_reserve_added'],
        actual_power_recomputed=actual['receipt']['actual_power_recomputed']),
    node('FROZEN_M2_PHYSICAL_CONSUMER','v42_integration/mess_actual.py','consume_frozen_mess',96,
        ['MESS_ACTUAL_EXECUTION_RECEIPT.json'],frozen_execution_validated=mess['frozen_execution_validated']),
    node('FRESH_AC','v42_integration/actual_validation.py','fresh_ac_minimum',96,
        ['FRESH_PHYSICAL/FRESH_PHYSICAL_RESULT.json'],PASS=fresh['PASS'],
        actual_power_trace_SHA_verified=record(RESULT/'ACTUAL_OCCUPANCY_POWER_TRACE.npz')['sha256']==fresh['actual_power_trace']['sha256'],
        original_Fresh96_body_executed=fresh['original_Fresh96_body_executed'],
        Original_full_source18r_case_certified=fresh['original_full_case_certified'],
        current_model_11SVR_153transformer_phase_scope=True,policy_benefit_certified=False),
]
write('CONTROL_POLICY_EXECUTION_CALLGRAPH.json',dict(base,status='PRODUCTION_CONNECTION_CONFIRMED_WITH_TWO_SEPARATE_FIRST_FAILURES',
    contribution_scope='SOURCE_GRID_CC4_FREEZE_ACTUAL_POWER_FRESH;lead merges Job eligibility/QoS cohort audits',
    nodes=nodes,source_receipts=source_receipts,
    first_failure_compiler='102templates fail anonymous-reference support; remaining42templates score309variants, allQ90hard-infeasible',
    first_failure_actual='5763observed-resource mismatch+53controlqueries at horizon end reject before literal policy lookup',
    actual_global_optimizer_calls=0,actual_online_grid_evaluations=0,
    no_V39_fixed_PCC_replay=True,May_policy_effect='NOT_ESTABLISHED',
    full_joint_global_gap='NOT_CERTIFIED',confirmed_masked_fixture_bugs=2,
    implementation_bug_proof_files=[record(OUT/'PREPLACE_ZERO_BUDGET_UNIVERSAL_MASK_REPRODUCTION.json'),
        record(OUT/'PAST_SLOT_CAPACITY_VETO_REPRODUCTION.json')]))
print(json.dumps(dict(written=[n for n in ('CC4_POLICY_RESOURCE_ENVELOPE_AUDIT.json','GRID_SCORE_EXECUTION_AUDIT.json',
    'POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json','CONTROL_POLICY_EXECUTION_CALLGRAPH.json')],
    A2_resource_exact=True,policy_lookup_calls=runtime['lookup_calls'],compiler_numeric_variants=len(score_rows),
    first_guard_reasons=dict(rule_reasons),Native_Optimize_calls=0),ensure_ascii=True))
