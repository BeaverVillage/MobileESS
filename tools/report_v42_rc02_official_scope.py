"""Append the user's corrected official scope; never rewrite diagnostic Raw."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.rc02_voltage_audit import write_new
from v42_integration.actual_validation import read,record
from v42_integration.release_ac_contract import CONTRACT


def main():
    out=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/VOLTAGE'
    run=out/'ASOF_E0_E3_01'
    old=read(out/'VOLTAGE_GATE_A_CAUSE_AND_MINIMUM_CONTRACT.json')
    result=dict(schema='RC02_OFFICIAL_VOLTAGE_SCOPE_CORRECTION_V1',
        authority='EXPLICIT_LATER_USER_CHAT_CORRECTION_RELAYED_BY_SUPERVISOR',
        Gate_contract=CONTRACT,official_model='15_MINUTE_96_SLOT_QUASI_STEADY',
        official_operation='ORIGINAL_CLOCK_SETTLE_SLOT_THEN_MEASURE_FULL_NETWORK',
        original_11SVR_7AUTO_Delay_TapDelay_LDC_history_limits_unchanged=True,
        retained_diagnostic=record(out/'VOLTAGE_GATE_A_CAUSE_AND_MINIMUM_CONTRACT.json'),
        diagnostic_substep_status=old['status'],diagnostic_RAW_code_or_source_rewritten=False,
        diagnostic_substep_FAIL_is_global_official_veto=False,
        diagnostic_all_E0_E3_16_last_solve_PASS=all(all(r['PASS'] for r in read(run/(label+'_SUMMARY.json'))['last_solve_per_slot'])
            for label in ('E0','E1','E2','E3')),
        original_diagnostic_physical_values_are_still_valid=True,
        continuous_time_voltage_safety_CERTIFIED=False,
        official_96_current_D0_Fresh='NOT_RUN',historical_PR223_PASS_transferred_to_D0=False,
        superseded_claims=['DIAGNOSTIC_SUBSTEP_FAIL_AUTOMATICALLY_BLOCKS_OFFICIAL_GLOBAL_GATE',
            'CURRENT_D0_PRODUCTION_ACTUAL96_REQUIRES_ITS_OWN_FRESH96_PASS_IN_ADVANCE'],
        production_order=['SOURCE_CONTRACT_AND_CURRENT_A2_M2_FULL_ACCEPTANCE',
            'SAME_CASE_SETTLED_16_CANARY','ACTUAL96','SAME_CASE_ORIGINAL_FRESH96',
            'CAMPAIGN_LAUNCH_REQUIRES_INTEGRATED_MAY01_96_PASS_AND_SEPARATE_BUDGET'],
        all_source_and_diagnostic_raw_preserved=True,Native_calls=0,P2_calls=0,source=record(__file__))
    write_new(out/'OFFICIAL_GATE_SCOPE_CORRECTION.json',result)
    print(CONTRACT,result['diagnostic_all_E0_E3_16_last_solve_PASS'])


if __name__=='__main__':main()
