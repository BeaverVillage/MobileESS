"""Prepare an inert dated campaign plan and exact downstream budget gates."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_integration.release_campaign import may_dates,STAGES
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'
FINAL=OUT/'FINAL_PREPARATION'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    target=FINAL/'CAMPAIGN_PREPARATION_PLAN.json'
    if target.exists():raise FileExistsError('CAMPAIGN_PREPARATION_MUST_NOT_OVERWRITE')
    p1=read(OUT/'A1_P1_120/INDEPENDENT_P1_ACCEPTANCE.json')
    exact=read(OUT/'A1_P1_120/PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json')
    inventory=read(OUT/'MESS/FINAL/REPRESENTATIVE_DATE_SOURCE_INVENTORY.json')
    representatives={r['day']:r for r in inventory['dates']}
    dates=[]
    for day in may_dates():
        dates.append(dict(day=day,status='NOT_RUN',execution_started=False,
            evaluation='INDEPENDENT_DATE_D0_ONLY',May01_initial_state_copied=False,carry_imported=False,
            date_initial_authority='APPROVED_MAY01_MODEL_STATE' if day=='2025-05-01' else
                representatives[day]['D0_initial_authority']['status'] if day in representatives else 'NOT_AUDITED',
            case_sha=exact['identity']['case_sha'] if day=='2025-05-01' else None,
            stages={s:dict(status='NOT_RUN',result_generated=False) for s in STAGES},
            reason='INTEGRATED_FULL96_AND_BUDGET_GATE_HOLD'))
    plan=dict(schema='V42_INERT_MAY_RELEASE_PREPARATION_V1',status='CAMPAIGN_BLOCKED_WITH_EXACT_REASONS',
        Worker=1,Threads=1,dates=may_dates(),automatic_start=False,Native_launch_authorized=False,
        release_sha=None,release_state='FREEZE_CANDIDATE_PENDING_INTEGRATED_VALIDATION',
        pipeline=list(STAGES),day_evaluation_mode='INDEPENDENT_CAUSAL_D0',
        native_parameter_policy='PRESERVE_ORIGINAL_A_P1_P2_AND_M_BEAM_JOINT_K48',
        checkpoint_contract='DATE_LEDGER_AND_STAGE_RAW;RECONCILE_INTERRUPTED_ATTEMPT_BEFORE_ANY_RETRY',
        failed_date_policy='RECORD_ERROR_AND_NOT_RUN_TAIL_THEN_CONTINUE_NEXT_DATE',
        prior_case_UB_LB_or_plan_transfer=False,day_practicality_target_wall_seconds=3600,
        runtime_target_achieved_for_new_pipeline=False,
        required_launch_gates=['May01_same_case_A1_P2_M1_A2_M2_FULL','May01_Actual96_Fresh_AC_PASS',
            'May02_May10_May12_same_frozen_algorithm_PASS','ALL_DATE_CAUSAL_D0_SOURCE_CERTIFICATES',
            'FROZEN_PRODUCTION_DATE_ADAPTERS','EXPLICIT_CAMPAIGN_NATIVE_BUDGET_AND_LAUNCH_APPROVAL'],
        generic_state_runner=file_record(ROOT/'v42_integration/release_campaign.py'),
        production_date_generalization_status='NOT_CERTIFIED;CURRENT_D0_FACTORY_IS_MAY01_SPECIFIC',
        representative_sources=file_record(OUT/'MESS/FINAL/REPRESENTATIVE_DATE_SOURCE_INVENTORY.json'))
    plan['preparation_plan_sha']=digest(plan);_write(target,plan)
    _write(FINAL/'DATE_PREPARATION_LEDGER.json',dict(status='PREPARATION_ONLY_NOT_EXECUTION_RESULTS',dates=dates))
    # Conservative initial per-component proposals, not spend permissions or
    # certified runtimes. M1/M2 retain their existing 140s per Joint call cap.
    proposals=[dict(stage='A1_P2',components=['migration_count','shift_magnitude','prestart_relocation'],
        native_stage_cap_seconds=90.,scope='PROPOSAL_ONLY_CURRENT_P1_POINT_REPLAY_BEFORE_RESUME'),
        dict(stage='M1_UB',native_stage_cap_seconds=180.,joint_single_call_cap_seconds=140.),
        dict(stage='K48_AFTER_M1',native_stage_cap_seconds=180.,binding='EXACT_M1_FIXED_AIDC_CASE_ONLY'),
        dict(stage='A2_P1',native_stage_cap_seconds=120.),dict(stage='A2_P2',native_stage_cap_seconds=90.),
        dict(stage='M2_UB',native_stage_cap_seconds=180.,joint_single_call_cap_seconds=140.),
        dict(stage='K48_AFTER_M2',native_stage_cap_seconds=180.,binding='EXACT_M2_FIXED_AIDC_CASE_ONLY')]
    native=sum(r['native_stage_cap_seconds'] for r in proposals)
    _write(FINAL/'FOLLOWUP_NATIVE_BUDGET_PROPOSAL.json',dict(status='PROPOSAL_NOT_AUTHORIZATION',stages=proposals,
        total_proposed_stage_native_caps_seconds=native,return_reserve_seconds=30.,overshoot_buffer_seconds=60.,
        proposed_separate_ceiling_seconds=native+90.,success_within_caps_guaranteed=False,
        wall_forecast_status='NOT_CERTIFIED_FOR_NEW_D0_STAGES',
        A1_measured_Native_seconds=p1['Native_seconds'],A1_measured_total_wall_seconds=p1['build_solve_audit_wall_seconds'],
        other_measured_evidence=file_record(OUT/'MESS/FINAL/FOLLOWUP_BUDGET_EVIDENCE.json'),
        new_180s_unused_balance_authorizes_followups=False,Native_calls_this_preparation=0,
        next_immediate_gate='A1_ORIGINAL_P2_ACCEPTANCE_OR_PROVEN_EXISTING_P1_ONLY_RULE',
        later_stages_only_after_upstream_full_acceptance=True,full_31_day_budget_proposed_or_authorized=False))
    print(json.dumps(dict(status=plan['status'],dates=len(dates),automatic_start=False,
        followup_proposed_ceiling=native+90.),indent=2))


if __name__=='__main__':main()
