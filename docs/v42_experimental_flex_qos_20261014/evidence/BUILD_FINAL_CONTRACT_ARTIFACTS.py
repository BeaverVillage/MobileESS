"""Publish boundaries of the shared Q90 evaluator and research contracts."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def record(p):p=Path(p);return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
def main():
    shared=Path('D:/v42_q90_service_recourse_20261014/docs/v42_cc4_v21_q90_recourse_20261014')
    mass=read(shared/'Q90_WORK_MASS_CONSERVATION.json')
    write(ROOT/'audit/Q90_QUEUE_CARRYOVER_REFORMULATION.json',dict(
        science_version='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1',
        common_module='v42_integration/q90_recourse.py',shared_Q90_commit='97da5c097f0eefc30a057c51378676c6402138c8',
        shared_Q90_PR=225,shared_Q90_source_sha='fe2d882b3db6c43422436e4ea0f5dbd7f7bd1462298389031e18384293d3f0f5',
        scope='ALL_CANDIDATES_SAME_FULL_DAY_COUNTERFACTUAL_LITERAL_A2_Q50_PLUS_Q90_MINUS_Q50',
        Q50='LITERAL_A2_X_AND_SITE_NOMINAL_SERVICE_PLUS_CANDIDATE_MINUS_CAUSAL_REFERENCE_GPU_DELTA',
        Q90='ONLY_ADDITIONAL_HOURLY_WORK_SERVICED_UNDER_ORIGINAL_CDF_CAPACITY_AND_SIGNED_GRID_ROWS',
        actual_live_ForecastBook_depletion='ORIGINAL_SUBMIT_ONCE_INDEPENDENT_FROM_STATIC_OFFLINE_Q90_RECOURSE',
        lower_CDF_unmet_is_timing_risk=True,lower_CDF_unmet_is_normal_completion_or_Job_QoS_certificate=False,
        terminal_pending_plus_carry_double_count=False,forecast_clipping=False,
        source_baseline_mass=mass,source_baseline_mass_receipt=record(shared/'Q90_WORK_MASS_CONSERVATION.json'),
        superseded_full_Q50_fluid_scheduler='ARCHIVED_DIAGNOSTIC_NOT_PRODUCTION',
        final_case_risks='audit/control/FINAL_FLEX_COMPARISON/COMPARISON_DETAIL.json'))
    numeric=read(ROOT/'audit/migration/MIGRATION_SOURCE_NUMERIC_AUTHORITY.json')
    handoff=read(ROOT/'audit/migration/MIGRATION_PACKET_API_HANDOFF.json')
    write(ROOT/'audit/MIGRATION_ASSUMPTION_AUTHORITY.json',dict(
        science_version='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1',
        E0='SOURCE_RIGHTS_ONLY',E1_E2='ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT_MAX_ONE_MIGRATION',
        observed_Kestrel_checkpoint_or_SLA_claim=False,checkpoint_period_seconds=1800,
        shared_start_delay_plus_migration_interruption_budget=True,
        original_numeric_authority=numeric,original_numeric_authority_receipt=record(ROOT/'audit/migration/MIGRATION_SOURCE_NUMERIC_AUTHORITY.json'),
        hold_protocol_assumptions=handoff['protocol'],
        source_hold_until='transfer_start',destination_hold_from='transfer_end',
        source_destination_whole_gang_and_each_route_link_and_global_one_transfer=True,
        WAN_saveIO_energy_joules=None,extra_WAN_energy_scope='UNMODELED_NOT_ZERO',
        GPU_hold_C1_power_accounted_in_Actual=True,
        payload_restart_sensitivity=read(ROOT/'audit/migration/MIGRATION_PAYLOAD_RESTART_SENSITIVITY.json'),
        source_private_actual_runtime_used_for_packet=False))
    write(ROOT/'audit/PREPLACEMENT_ZERO_DELAY_REGRESSION.json',dict(
        scope='PR224_REGRESSION_REUSED_WITH_NEW_RESEARCH_PROJECTION',
        exact_fix_commit='c6f1a0f41164b7da4afe406dd692abd583a29d1e',PR224_done=True,
        source_B_code_not_reimplemented_or_changed=True,zero_delay_pending_preplace_independent_capability=True,
        source_explicit_none_permission_not_granted_by_E0=True,
        source_Known_DD00_initializer_permissions=1245,initializer_permission_is_observed_Kestrel_SLA=False,
        source_protected_and_explicit_nonbatch_not_overridden=True,
        test_results=record(ROOT/'audit/FINAL_INTEGRATED_TEST_RESULTS.xml'),
        test_scope='FINAL_INTEGRATED_XML_PASS_NATIVE0;FINAL_ACTUAL_COUNTS_IN_COMPARISON_TABLE'))
    print(json.dumps(dict(required_contract_artifacts=3,duplicate_production_queue=False)))
if __name__=='__main__':main()
