"""Read-only derivation of preserved Q-step/control timing evidence."""
from pathlib import Path
import sys
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'v42_integration/release_actual.py').is_file())
sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record,write
from v42_integration.policy import digest

REPLAY=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
M2=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')


def main():
    output=REPLAY/'FIXED_M2_Q_STEP_AND_CONTROL_EVIDENCE.json'
    if output.exists():raise FileExistsError('NO_EXISTING_EVIDENCE_OVERWRITE')
    paths=[REPLAY/'ASOF_SUBSTEP_PHYSICAL_DIAGNOSIS.json',REPLAY/'C0/PUBLIC_PREFIX_ORIGINAL_C1.json',M2,Path(__file__)]
    before=[record(p) for p in paths]
    if before[2]['sha256']!='72be8ee7c73024643bcce927eb2373c40872bc06fb9e9c9da98b6b6b84cb8656':
        raise ValueError('ORIGINAL_FIXED_M2_BYTES_DRIFT')
    diagnostic,prefix,plan=[read(p) for p in paths[:3]]
    rows=[]
    for slot in (11,12,13):
        row=prefix[slot]
        rows.append(dict(slot=slot,interval_start_seconds=row['start_seconds'],
            average_observed_GPU=sum(row['GPU']),AIDC_PCC_P_kw=sum(row['P']),AIDC_PCC_Q_kvar=sum(row['Q']),
            demand_mw=row['observations']['demand']['values']['demand_mw'],
            pv_mw=row['observations']['pv']['values']['pv_mw'],
            fixed_STA01_P_kw=plan['P_by_site']['STA01'][slot],fixed_STA01_Q_kvar=plan['Q_by_site']['STA01'][slot]))
    changes=[dict(from_slot=a['slot'],to_slot=b['slot'],
        delta_STA01_Q_kvar=b['fixed_STA01_Q_kvar']-a['fixed_STA01_Q_kvar'],
        delta_AIDC_PCC_P_kw=b['AIDC_PCC_P_kw']-a['AIDC_PCC_P_kw'],
        delta_observed_average_GPU=b['average_observed_GPU']-a['average_observed_GPU']) for a,b in zip(rows,rows[1:])]
    first=diagnostic['first_violation'];local=next(r for r in first['SVR']['devices'] if r['id']=='STA08')
    local_parameters=[dict(phase=p['phase'],tap=p['tap'],tap_number=p['tap_number'],
        parameters={k:p['controller_parameters'][k] for k in ('Delay','TapDelay','VReg','Band','R','X','PTPhase')})
        for p in local['phases']]
    queue=first['event']['pending_queue']
    result=dict(schema='RC01_FIXED_M2_Q_STEP_AND_NATIVE_CONTROL_EVIDENCE_V1',
        status='EVIDENCE_SAVED_SINGLE_CAUSE_NOT_PROVEN',
        evidence_scope='READ_ONLY_PRESERVED_FIXED_M2_AND_ASOF_ALL_NATIVE_SUBSTEP_DIAGNOSIS',
        source_receipts=before,MESS_plan_sha=plan['plan_sha'],
        public_Q_step_rows=rows,adjacent_changes=changes,
        first_violation=dict(step=first['step'],event_kind=first['event']['kind'],
            absolute_seconds=first['event']['absolute_seconds'],previous_native_step=first['previous_native_step'],
            STA08_current_taps_and_original_control_parameters=local_parameters,
            pending_STA08_actions=[r for r in queue if r['device'].lower().startswith('svr_sta08')],
            pending_original_creg4a=[r for r in queue if r['device'].lower()=='creg4a'],
            native_event_log=first['event']['native_event_log'],
            executed_regulator_identity_not_inferred_from_future_queue=True),
        global_substep_diagnosis=dict(total=diagnostic['physical_substeps'],FAIL=diagnostic['violating_substeps'],
            minimum_voltage_pu=diagnostic['min_voltage_pu'],maximum_voltage_pu=diagnostic['max_voltage_pu'],
            violation_slots=sorted({s['slot'] for s in diagnostic['violating_step_summary']}),
            all_slot_last_solve_PASS=diagnostic['settled_last_solve_all_PASS'],
            last_solve_per_slot=diagnostic['last_solve_per_slot']),
        interpretation=dict(
            fixed_public_reactive_command_reverses_by_784_628_kvar=True,
            worst_undervoltage_and_overvoltage_nodes_correspond_to_STA01_Q_step_slots=True,
            existing_AUTO_delay_interaction_is_supported_evidence=True,
            sole_cause_proven=False,counterfactual_control_intervention_performed=False,
            Source_core_or_MESS_algorithm_changed=False,limits_or_control_parameters_changed=False,
            cannot_replace_all_native_substep_FAIL_with_last_solve_or_offline_Fresh_PASS=True,
            Gate2='PHYSICAL_FAIL',new_D0_full_chain_or_Full96_claim=False),Native_calls=0)
    if [record(p) for p in paths]!=before:raise ValueError('READ_ONLY_SOURCE_BYTES_CHANGED')
    result['receipt_sha']=digest(result);write(output,result)
    print(result['status'],[(r['slot'],r['fixed_STA01_Q_kvar']) for r in rows],flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
