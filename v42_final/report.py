"""Assemble the delivered status without rerunning inference or holdout replay."""
from .common import *


def main():
    resource=read(OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json')
    require(resource['full_A1_infeasible_proven'],'THIS_REPORT_REQUIRES_PROVEN_RESOURCE_FAILURE')
    metrics=read(OUT/'V42_RUNTIME_PROVIDER_FREEZE.json')['intrinsic_metrics']
    gamma=read(OUT/'RUNTIME_RESERVE_CALIBRATION.json');valid=read(OUT/'RUNTIME_RESERVE_HOLDOUT_RECEIPT.json')
    rows=[]
    for stage in ('A1','M1','A2','M2'):
        row=dict(stage=stage,status='NOT_RUN_RESOURCE_NECESSITY_FAILURE',run=False,accepted_native_plan=False,
            build_seconds=None,presolve_seconds=None,solve_wall_seconds=None,incumbent_objective=None,
            best_bound=None,final_MIP_gap=None,node_count=None,binary_count=None,continuous_count=None,
            presolved_rows=None,presolved_columns=None,warm_start_accepted=None,
            raw_complete_options=None,retained_complete_options=None,exact_safe_option_reduction=None,
            configured_optimize_limit_seconds=600,configured_target_MIP_gap=.001,
            optimize_calls=0,termination_reason='STOP_BEFORE_A1_BY_NEW_NECESSARY_RESOURCE_PROOF',
            timing_scope='No native build/optimize; analytic proof and relaxed-LP timings are separate evidence')
        dump(stage+'_MODEL_STATS.json',row);rows.append(row)
    csv('V42_FINAL_SOLVER_SUMMARY.csv',rows)
    dump('FRESH_AC_VALIDATION.json',dict(status='NOT_RUN_NO_ACCEPTED_FINAL_PLAN',RUN=False,PASS=False,
        Vmin=None,Vmax=None,line_phase_loading=None,new_violations=None,plan_sha=None,
        stale_AC_used=False,required_stage='Accepted final M2',reason=resource['status']))
    flags=dict(RUNTIME_MODEL_RETRAINED=False,FINAL_NOMINAL_RUNTIME_PROVIDER=MODEL,RUNTIME_NOMINAL_QUANTILE='Q50',
        RUNTIME_Q50_MAE_HOURS=metrics['Q50_MAE_hours'],RUNTIME_Q50_COVERAGE=metrics['Q50_coverage'],
        RUNTIME_Q50_TIME_RATIO=metrics['Q50_time_ratio'],Q90_USED_AS_HARD_RUNTIME_DURATION=False,Q50_Q90_ALPHA_INTERFACE_USED=False,
        PLANNING_RUNTIME_RESERVE_ENABLED=True,PLANNING_RUNTIME_RESERVE_TARGET=.90,PLANNING_RUNTIME_RESERVE_NATIVE_ACCEPTED=False,
        ACTUAL_RUNTIME_RESERVE_ENABLED=False,ACTUAL_RUNNING_USES_OBSERVED_TRUTH=True,
        CC4_PROVIDER_CHANGED=False,CC4_GPUH_DIRECT_TO_GPU_BINDING=False,CC4_EXECUTION_LAG_KERNEL_ENABLED=True,
        CC4_FORECAST_DEPLETION_ENABLED=True,PENDING_PHYSICAL_GPU_ZERO=True,RUNNING_PHYSICAL_GPU_FULL_GANG=True,
        EPISODE_SITE_LEDGER_ENABLED=True,LEGACY_UNASSIGNED_OVERLAP_BLOCKER=False,
        TIMESHIFT_RUNTIME_DURATION_RULE=False,TIMESHIFT_CONDITIONAL_WAIT_RULE=True,
        MESS_P_DECISION_VARIABLE=True,MESS_Q_DECISION_VARIABLE=True,PCS_16_FACE_LINEAR=True,
        A1_RUN=False,M1_RUN=False,A2_RUN=False,M2_RUN=False,FRESH_AC_RUN=False,FINAL_RESPONSE_KERNEL_FROZEN=False,
        NATIVE_V42_ACTIVATED=False,MAY_ACTUAL_REPLAY_RUN=False,CL_MC_BD_RUN=False,
        flag_scope='Enabled means implemented/tested contract and frozen native input; never an accepted native operating plan',
        native_blocker=resource['status'])
    dump('FINAL_FLAGS.json',flags)
    dump('FINAL_VERDICT.json',dict(status='INTERFACES_VERIFIED_NATIVE_ACTIVATION_BLOCKED_BY_NEW_RESOURCE_PROOF',
        accepted_plan=False,resource=rec(OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json'),
        Runtime_provider_reproduced=True,Runtime_fit=False,gamma_90=gamma['gamma_90'],
        reserve_CAL_coverage=gamma['coverage'],reserve_fold5_coverage=valid['validation_summary']['coverage'],
        holdout_retuned=False,CC4_unit_error_fixed=True,old_certificate_reused_as_current_proof=False,
        A1_M1_A2_M2_run=False,Fresh_AC_run=False,final_kernel_created=False,
        next_dependency='Resolve fixed-start nominal demand versus frozen WAN/restart/780-GPU authority through a separately authorized source-backed change; do not relax it here.',
        completed_scope='Frozen provider, empirical reserve, lag conversion, depletion/state/timeshift contracts, native input, independent necessary-condition proof and tests',
        open_scope='Accepted native 4-block plan, measured native scalability, Fresh AC, final response kernel, native Actual policy activation'))
    dump('PR93_SUPERSESSION.json',dict(status='SUPERSEDED_FOR_V42_FINAL_INTERFACE',
        source=rec(ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json'),
        original_files_modified=False,reason='Lifetime arrival GPUh requires execution-lag conversion before slot occupancy',
        replacement=rec(OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json'),
        old_failure_not_reused=True))
    dump('NATIVE_INPUT_FIELD_AUTHORITY.json',dict(source_bundle=rec(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),
        canonical_consumer='v42_final.native.canonical_jobs',canonical_view=rec(OUT/'MAY01_CANONICAL_Q50_INPUT_VIEW.csv'),
        authoritative_Q50_fields=['V10_Q50_total_seconds','exact_service_seconds','service_slots','reference_end','runtime_authority'],
        inherited_PR93_forensic_fields_not_new_authority=['duration_authority','remaining_service_seconds','full_reservation_GPUh',
            'exact_compute_GPUh','post_H_reserved_GPUh','FLEX','FIX','Q25_seconds','T2_reason'],
        candidate_mask_receipt=rec(OUT/'CANONICAL_CAPABILITY_COUNTS.json'),
        legacy_source_mask_receipt='FINAL_CAPABILITY_COUNTS.json preserves old PS/MG candidates before local Q50 checkpoint recheck',
        not_accepted_schedule=True))
    dump('PREREGISTRATION_AUTHORITY_ADDENDUM.json',dict(authority='Subsequent explicit user replies, before freeze/holdout evaluation',
        original_preregistration_preserved=True,
        provider='Matched fold5 model/preprocessing and 2025-03-31 Isotonic Rolling14 map as V42-specific study provider',
        reserve='Stored causal fold1-4 VALID predictions become reserve CAL/development; fold5 once-only reserve holdout',
        original_Runtime_fold_membership_unchanged=True,March31_retrospective_inference=False,
        May_uses_same_fold1_4_gamma=True,TRAIN_CC4_wait_authority_unchanged=True))


if __name__=='__main__':main()
