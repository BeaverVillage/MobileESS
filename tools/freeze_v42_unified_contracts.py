"""Freeze one shared interface before either workstream may implement it."""
from pathlib import Path
import json
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v42_integration.unified_contract import REPORT, digest, file_sha

ROOT = REPORT.parents[1]
BASE = 'f32b22adf8e3e53ab68256458cb991f9d30d2ecb'
BRANCH = 'codex/v42-unified-aidc-mess-sensitivity-runtime-scale'


def write(name, doc):
    (REPORT / name).write_text(json.dumps(doc, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')


def main():
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != BASE:
        raise ValueError('EXACT_PR230_HEAD_REQUIRED_FOR_FIRST_FREEZE')
    REPORT.mkdir(exist_ok=True)
    historical_path = ROOT/'docs/v42_trajectory_tracking_may01_canary_20261014/DIAGNOSTIC_FINAL/PLANNING_TARGET_IDENTITY.json'
    historical = json.loads(historical_path.read_text())
    interface = dict(schema='V42_UNIFIED_INTERFACE_V1', base_commit=BASE, branch=BRANCH,
        slots=96, slot_seconds=900, aidc_gpu_gang='WHOLE_INTEGER',
        aidc_P_Q='ORIGINAL_C1_CONSUMPTION_KW_KVAR', mess_P_Q='SIGNED_INJECTION_POSITIVE_DISCHARGE',
        net_load='AIDC_CONSUMPTION_MINUS_MESS_INJECTION_EACH_ONCE',
        stages=['A1','M1','A2','M2'], Actual_global_optimize_calls=0,
        max_start_delay_seconds=0, start_delay_candidates_seconds=[0],
        policy='DDAY_DETERMINISTIC_KNOWN_UNKNOWN_SITE_ONLY',
        binding_fields=['science_sha','case_sha','physical_sha','time_axis_sha','qos_sha','cc4_sha',
                        'runtime_sha','response_sha','initial_state_sha','aidc_anchor','mess_anchor','interface_sha'],
        reservations={'Observed_RUNNING':'HARD_UNTIL_OBSERVED_COMPLETION',
                      'Known_frozen':'HARD','Unknown_committed':'HARD','CC4_Q50_Q90':'SOFT_FORECAST'},
        unknown_primary_score='MIN_PREDICTED_MAX_LOADING_CURRENT_ALL_LINE_PHASE_ROWS',
        hard_grid='ORIGINAL_VOLTAGE_CURRENT_TRANSFORMER;NONWORSENING_IS_NOT_SAFE_PASS',
        known='CURRENT_DDAY_SOURCE_COMPATIBLE_DETERMINISTIC_FCFS;INDEPENDENT_DIAGNOSTIC_NOT_A1_OPTIMUM',
        running_runtime='Q50_Q90_NOT_COMPLETION_GUARANTEE;CONDITIONAL_PROVIDER_NOT_CERTIFIED',
        native={'Threads':1,'Heavy_workers':1,'owner':'Supervisor','ledger':'UNIFIED_NATIVE_RUNTIME_LEDGER.json'},
        modules={'AIDC':'v42_integration.aidc_sensitivity_runtime','MESS':'v42_integration.mess_scaling',
                 'Supervisor':'v42_integration.unified_contract'},
        certification='FIXTURE_AND_REAL_DIAGNOSTIC_SCOPE_EXPLICIT;NO_HISTORICAL_CERTIFICATE_TRANSFER')
    interface.update(validation_priority='MAY01_B1_AIDC_AND_EXACT_S1_MESS_STANDALONE_FIRST',
        allowed_AIDC_Heavy_arms=[],allowed_AIDC_Heavy_days=['2025-05-01'],
        new_Known_A_Heavy_authorized=False,
        AIDC_active_comparison=['C0_BASIC_SITE_ONLY','C1_SIGNED_SITE_ONLY'],
        AIDC_active_day='2025-05-01',AIDC_active_arm='B1',
        AIDC_TimeShifting_authorized=False,AIDC_RuntimeRepair_authorized=False,
        AIDC_CheckpointMigration_authorized=False,
        AIDC_candidate_start='ACTUAL_EXECUTABLE_EVENT_TIME_ONLY',
        AIDC_candidate_sites='SOURCE_COMPATIBLE_AT_MOST_12;GPU_RACK_AND_ORIGINAL_GRID_GUARDS',
        Known_initial_state='CURRENT_DDAY_OBSERVED_RUNNING_AND_PENDING',
        Known_priority='SAME_RULE_AND_FIRM_BOOKING_PRIORITY_BOTH_VARIANTS',
        Known_execution_fairness='REQUIRE_IDENTICAL_UID_SITE_START_SERVICE_COMPLETION_TRACE',
        historical_Known_anchor='HISTORY_AND_ELECTRICAL_NUMERIC_REFERENCE_ONLY;NOT_EXECUTION_AUTHORITY',
        Unknown_runtime_reservation='UNBOUNDED_HOLD_THROUGH_STUDY_HORIZON_UNTIL_OBSERVED_COMPLETION',
        inactive_extension_contract='TIME_SHIFT_60MIN_QOS_CONTRACT.json;NOT_ACTIVE_SITE_ONLY_AUTHORITY',
        four_stage_Heavy_authorized=False,S2_to_S7_Heavy_authorized=False,
        combined_Heavy_prerequisite='USER_RESUMES_AFTER_STANDALONE_VALIDATION')
    preserved = ['v42_integration/production_case.py','v42_integration/actual_validation.py',
                 'v42_integration/sensitivity_policy.py','v42_thermal/authority.py',
                 'v42_svr11/authority.py','v42_integration/m_engine.py','v42_common_mess/model.py']
    physical = dict(schema='V42_UNIFIED_PHYSICAL_V1',IEEE='IEEE123',AIDC_count=12,
        installed_GPU=780,MESS_count=4,charging_site_count_expected=24,
        charging_sites='READ_ORIGINAL_SOURCE_NO_SYNTHETIC_NODES',installed_SVR=11,
        existing_RegControl=7,original_regcontrol_and_LDC='PRESERVED_AUTO_ACTUAL',
        voltage_limits='ORIGINAL_UNCHANGED',NormalAmps='ORIGINAL_UNCHANGED',
        transformer='ALL_ORIGINAL_PHASE_AXES_UNCHANGED',
        source_artifact_shas={p:file_sha(ROOT/p) for p in preserved},
        historical_signed_grid_authority_sha=historical['Signed_Grid_Authority_SHA'],
        response_sha=historical['response_sha'],C1_power_sha=historical['C1_Power_Model_SHA'],
        historical_case_equality='NOT_ASSUMED;PR223_PR230_NUMERICAL_IDENTITY_REQUIRED')
    axis = dict(schema='V42_SHARED_TIME_AXIS_V1',day='2025-05-01',source_timezone='Australia/Brisbane',
        presentation_timezone='Asia/Seoul',slots=96,slot_seconds=900,
        planning_slot_zero_relative_Dday_seconds=-21600,planning_native_Dday_slots=[24,120],
        Dday_actual_begin_seconds=0,Dday_actual_end_seconds=86400,
        issue='D-1_18:00_AEST',Known_rule='SUBMIT_OBSERVED_BY_ISSUE',
        initial_state='OBSERVED_DDAY_STATE_ONLY_NO_FUTURE_COMPLETION')
    ownership = dict(schema='V42_AGENT_FILE_OWNERSHIP_V1',shared_worktree=str(ROOT),branch=BRANCH,
        Supervisor=['v42_integration/coordinator.py','v42_integration/unified_contract.py',
                    'v42_integration/unified_resource.py','v42_integration/unified_research.py',
                    'tests/test_v42_unified_integration.py','tools/freeze_v42_unified_contracts.py',
                    'tools/run_v42_unified_research.py','tools/run_v42_unified_handoff_pilot.py',
                    'tools/run_v42_unified_b1_pilot.py','tools/revise_v42_unified_contracts.py',
                    'tools/run_v42_frozen_known_site_only.py','tools/run_v42_b1_actual_only.py',
                    'tools/run_v42_unknown_current_ac_probe.py','tools/audit_v42_known_seed_box.py',
                    'tools/audit_v42_known_cc4_headroom.py','tools/audit_v42_known_native_interval.py',
                    'tools/audit_v42_known_service_authority.py','tests/test_v42_authorized_geometry.py',
                    'tests/test_v42_seed_member_choices.py','v42_integration/unified_native0.py',
                    'tests/test_v42_integration_dday_actual_loader.py',
                    'docs/v42_unified_aidc_mess_research_20261014/COMMON_AND_FINAL'],
        Agent_A=['v42_integration/aidc_sensitivity_runtime.py','tests/test_v42_aidc_sensitivity_runtime.py',
                 'tools/run_v42_aidc_sensitivity_canary.py','docs/v42_unified_aidc_mess_research_20261014/AIDC_ARTIFACTS'],
        Agent_B=['v42_integration/mess_scaling.py','tests/test_v42_mess_scaling.py',
                 'tools/run_v42_mess_scaling_pilot.py','docs/v42_unified_aidc_mess_research_20261014/MESS_ARTIFACTS'],
        agents_git_mutations=False,agents_heavy_solver=False,
        existing_file_changes='SUPERVISOR_APPROVES_OWNER_AND_RANGES_BEFORE_EDIT')
    ownership['registered_existing_changes']=[dict(path='v42_integration/actual_validation.py',owner='Supervisor',
        section='fresh_ac_minimum trace axis gate and scoped receipt',
        reason='Explicit actual prefix AC without padding unobserved Full96 data'),
        dict(path='v42_integration/coordinator.py',owner='Supervisor',section='Optional unified binding and Actual adapter',
        reason='Connect shared bindings and new runtime algorithm while preserving historical runner'),
        dict(path='v42_integration/a_engine.py',owner='Supervisor',section='Exact geometry reuse and seed diagnostic hooks',
        reason='Preserved prior authorized implementation; new Known execution currently HOLD'),
        dict(path='v42_integration/a_seed.py',owner='Supervisor',section='Exact per-member seed assignment and bounded IIS diagnostic',
        reason='Preserved prior authorized implementation; new Known execution currently HOLD'),
        dict(path='v42_a_stage_domain_v2/domain.py',owner='Supervisor',section='Exact necessary domain timestamp bound',
        reason='All original option masks retained and tested; additional domain development currently HOLD')]
    graph = dict(schema='V42_WORKSTREAM_DAG_V1',parallel=['Agent_A_NATIVE0','Agent_B_NATIVE0','Supervisor_AUDIT'],
        edges=[['COMMON_CONTRACT_FREEZE','Agent_A_NATIVE0'],['COMMON_CONTRACT_FREEZE','Agent_B_NATIVE0'],
               ['A1','M1'],['M1','A2'],['A2','M2'],['M2','Actual']],
        resource_serialization='ONE_SUPERVISOR_HEAVY_CALL_AT_A_TIME',
        integration_refuses='SCIENCE_CASE_ELECTRICAL_FORECAST_QOS_OR_ANCHOR_DRIFT')
    docs={'UNIFIED_INTERFACE_CONTRACT.json':interface,'UNIFIED_PHYSICAL_AUTHORITY.json':physical,
          'SHARED_TIME_AXIS_CONTRACT.json':axis,'AGENT_FILE_OWNERSHIP.json':ownership,
          'WORKSTREAM_DEPENDENCY_GRAPH.json':graph}
    for name,doc in docs.items():write(name,doc)
    from v42_integration.actual_validation import load_stats
    strict_path=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/QOS_EMPIRICAL_STATS_STRICT.json')
    strict=load_stats(strict_path)
    research_qos=dict(schema='V42_RESEARCH60_QOS_V1',source_training_sha=strict.sha,
        source_statistics_file_sha=file_sha(strict_path),source_train_raw_sha=strict.source_sha,
        strict_accepted_unique_uids=len(strict.accepted_uids),
        historical_E1_research_policy_sha=historical['qos_sha'],
        participation='FLEX30_DETERMINISTIC_30_PERCENT_ELIGIBLE_BATCH',max_start_delay_seconds=3600,
        protected_urgent_interactive_extra_delay_seconds=0,shared_intentional_budget=True,
        reissue_on_retry=False,customer_SLA_claim=False,deadline_is_separate=True)
    research_qos.update(known_reference_rule='ISSUE_ONLY_DDAY_FCFS_REFERENCE_V1',
        known_pending_start_floor_slot=24,original_reference_kept=True,
        original_submission_queue_wait_kept=True,hard_source_deadlines_unchanged=True,
        future_Dday_observation_used_at_Planning=False,
        known_Actual_reoptimization=False,reference_scope='NEW_MODEL_REFERENCE_NOT_Kestrel_OBSERVED_QUEUE')
    research_qos.update(known_execution_rule='ATTEMPT_AT_FROZEN_START_THEN_UNAVOIDABLE_RESOURCE_WAIT_SAME_SITE',
        known_resource_wait_requires_observed_frozen_tick_attempt=True,
        known_resource_wait_same_site_service=True,
        known_resource_wait_preserves_original_intentional_budget=True,
        known_resource_wait_noncapacity_veto_invalidates_permission=True,
        historical_missed_commands_repaired_by_resource_wait=False)
    write('TIME_SHIFT_60MIN_QOS_CONTRACT.json',research_qos)
    docs['TIME_SHIFT_60MIN_QOS_CONTRACT.json']=research_qos
    science=digest(dict(base_science=historical['science_sha'],physical=digest(physical),interface=digest(interface),qos=digest(research_qos)))
    case=digest(dict(base_case=historical['case_sha'],science_sha=science,axis=digest(axis),delay=3600))
    bindings={k:historical[k] for k in ('qos_sha','cc4_sha','runtime_sha','response_sha','initial_state_sha','aidc_anchor','mess_anchor')}
    bindings.update(science_sha=science,case_sha=case,physical_sha=digest(physical),time_axis_sha=digest(axis),interface_sha=digest(interface))
    bindings['qos_sha']=digest(research_qos)
    write('SHARED_SOURCE_CASE_MANIFEST.json',dict(schema='V42_SHARED_SOURCE_CASE_MANIFEST_V1',base_commit=BASE,
        branch=BRANCH,bindings=bindings,contract_file_shas={name:file_sha(REPORT/name) for name in docs},
        historical_reference={k:historical[k] for k in ('science_sha','case_sha','original_anchor_case_sha','Source_SHA')},
        historical_reference_file=dict(path=str(historical_path),sha256=file_sha(historical_path)),
        anchor_status='HISTORICAL_NUMERIC_ANCHOR_ONLY;DDAY_KNOWN_EXECUTION_BASELINE_HAS_SEPARATE_CASE;NEW_A_NATIVE_HOLD',
        new_science_differs_from_30min=True,unknown_future_information_allowed=False,
        reusable_certificates=[],code_freeze_status='FINAL_SOURCE_SHA_TO_BE_RECORDED_AFTER_IMPLEMENTATION'))
    print(json.dumps(bindings, indent=2))


if __name__=='__main__':main()
