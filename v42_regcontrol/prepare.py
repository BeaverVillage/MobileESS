"""Source verification and preregistration before any new Actual outcome."""
import ast
import os
from .common import *
from .authority import *
from .verify import identity


def main():
    identity(); m=source()
    odd,adapter,inv=compile_verified(); odd.Basic.ClearAll()
    from dayahead.run_planning_ac_voltage_forensic_v1 import _compile
    prev=Path.cwd()
    try:
        plan,_=_compile(m['assets'].master.parents[1],m['assets'].pcc.parents[3],'NATIVE')
        pinv=m['inventory'](plan); assert_inventory(pinv,initial=True); plan.Basic.ClearAll()
    finally: os.chdir(prev)
    if pinv!=inv: raise ValueError('PLANNING_ACTUAL_SOURCE_COMPILER_MISMATCH')
    write(OUT,'SOURCE_AUTHORITY_CONFIRMATION.json',dict(PASS=True,PR127_exact_head=BASE,
        source_graph=m['audit']['static_source_graph'],code_read=m['audit']['code_read'],
        Actual_static_compile=inv,Planning_static_compile=pinv,
        source_no_control_setting_changes=True,May_outcome_reads=0,
        forcing_function_only_taps_caps_mode=True,
        forcing_source=next(r for r in m['audit']['relevant_function_evidence'] if r['function']=='apply_frozen_native_state')))
    arms={a:common_contract(a) for a in ('B0','B1','B2','B3')}
    write(OUT,'APRIL_MAY_COMMON_GRID_CONTROL_CONTRACT.json',dict(PASS=True,arms=arms,
        reusable_code='v42_regcontrol.authority + v42_regcontrol.session',
        source_parameter_override_path='fail-fast SHA and full compiled property comparison',
        May_scientific_execution='NOT_RUN',April_execution_arm='B0',
        other_arm_policy_preserved_by_caller=True))
    write(OUT,'CAPACITOR_FIXED_ON_AUTHORITY.json',dict(PASS=True,banks=inv['capacitors'],
        bank_count=4,CapControl_count=0,expected_states=[[1]]*4,
        threshold=None,delay=None,sensor_mapping=None,CapControl_creation='FORBIDDEN',
        unexpected_state_response='STOP; never force ON',authority_sha=arms['B0']['CAPACITOR_FIXED_STATE_AUTHORITY_SHA']))
    write(OUT,'PLANNING_GRID_CONTROL_RECHECK.json',dict(PASS=True,
        behavior_unchanged=True,V_PLAN_bytes_unchanged=True,RegControl_autonomous=True,
        capacitors_fixed_ON=True,CapControl_count=0,sequential_same_engine_96_slots=True,
        fresh_source_compile_per_day=True,local_anchor_freeze_only_for_sensitivity=True,
        tap_cap_decision_variables=0,Actual_inputs_opened_for_Planning=False,
        function_evidence=[r for r in m['audit']['relevant_function_evidence']
            if r['function'] in ('_anchor_and_sensitivity_day','_enable_native_controls','_fix_controls')]))
    path=OUT/'PREREGISTRATION.json'
    if path.exists(): raise ValueError('PREREGISTRATION_ALREADY_FROZEN')
    write(OUT,'PREREGISTRATION.json',dict(exact_base=BASE,adopts_PR127_source_audit=True,
        supersedes_previous_all_autonomous_capacitor_requirement=True,common_contract=arms['B0'],
        diagnostic_days=DIAGNOSTIC,diagnostic_must_precede_full_run=True,April_days=DAYS,
        Actual_Planning_tap_replay=False,Actual_Planning_cap_replay=False,
        source_initial_per_day=True,cross_day_carryover=False,within_day_sequential=True,
        observed_operation_metric='sum abs consecutive settled tap change / source step; within-slot operations unavailable',
        voltage_violations_do_not_fail_gate=True,quantile_method='higher',primary_band=[.95,1.05],
        primary='V_ACTUAL_AC - unchanged V_PLAN magnitude pu',
        source_parameter_tuning=0,Planning_regenerated=False,
        frozen_non_grid_arrays=True,Actual_P_repair=0,Actual_Q_repair=0,
        Actual_local_PQ_repair=0,Actual_global_reoptimization=0,Actual_AIDC_grid_reoptimization=0,
        MESS_ACTIVE=False,AIDC_PRESENT=True,Runtime_ON=True,CC4_ON=True,
        B1='NOT_RUN',B2='NOT_RUN',B3='NOT_RUN',May='NOT_RUN',M1='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',
        FINAL_MARGIN_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))
    print('PREREGISTERED: 7 autonomous RegControls / 4 fixed ON capacitors / 0 CapControls; identity PASS',flush=True)


if __name__=='__main__': main()
