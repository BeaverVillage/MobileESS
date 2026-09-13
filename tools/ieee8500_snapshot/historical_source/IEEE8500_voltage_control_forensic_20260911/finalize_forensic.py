import csv,json,math
from pathlib import Path
from collections import defaultdict
import numpy as np
from forensic import HERE,OLD,ROOT,read,save,table,sha

def main():
    ws=read(HERE/'GLOBAL_WITNESSES_FULL.json');states=read(HERE/'ALL_NATIVE_CONTROL_STATES_480.json');cf=read(HERE/'COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.json');model=read(HERE/'STATIC_NATIVE_CONTROL_MODEL.json');zero=read(HERE/'INDEPENDENT_ALPHA_ZERO_CONFIRMATION.json')
    assert len(ws)==10 and len(states)==480 and len(cf)==100
    regrows=[];caprows=[];sr=[];neighborhood=[];pathdeltas=[];onsets=[]
    for st in states:
        for bank in sorted(set(r['bank'] for r in st['regulators'])):
            rr=[r for r in st['regulators'] if r['bank']==bank]
            regrows.append(dict(alpha=st['alpha'],slot=st['slot'],bank=bank,regcontrols=[r['regcontrol'] for r in rr],accepted_tap_numbers=[r['accepted_tap_number'] for r in rr],accepted_tap_ratios=[r['accepted_tap_pu'] for r in rr],Vreg_V=[r['Vreg_V'] for r in rr],target_pu=[r['target_pu'] for r in rr]))
        for bank in sorted(set(r['bank'] for r in st['capacitors'])):
            rr=[r for r in st['capacitors'] if r['bank']==bank]
            caprows.append(dict(alpha=st['alpha'],slot=st['slot'],bank=bank,capacitors=[r['capacitor'] for r in rr],effective_ON_by_element=[r['effective_ON'] for r in rr],bank_state='ON' if all(r['effective_ON'] for r in rr) else 'OFF' if not any(r['effective_ON'] for r in rr) else 'PARTIAL',nameplate_kvar=sum(r['nameplate_kvar'] for r in rr),nominal_ON_kvar=sum(r['nominal_ON_kvar'] for r in rr),physical_injected_kvar=sum(r['physical_injected_kvar'] for r in rr),native_controlled=all(r['native_controlled'] for r in rr)))
        sr.append(dict(alpha=st['alpha'],slot=st['slot'],**st['source'][0]))
    table(HERE/'REGULATOR_BANK_ACCEPTED_TAPS_ALL_480_SLOTS.csv',regrows);table(HERE/'CAPACITOR_BANK_STATES_AND_KVAR_ALL_480_SLOTS.csv',caprows);table(HERE/'SOURCE_VOLTAGES_ALL_480_SLOTS.csv',sr)
    for w in ws:
        with np.load(OLD/f'screen/alpha_{w["alpha"]:.2f}/B0_ALL_PHASE_ARRAYS.npz') as z:
            volts=dict(zip(z['node_names'],z['voltage_pu'][w['slot']]))
        for r in w['all_regulator_states']:
            u,b=r['terminal_buses'];assert u in volts and b in volts
            neighborhood.append(dict(alpha=w['alpha'],witness=w['witness'],slot=w['slot'],regcontrol=r['regcontrol'],bank=r['bank'],upstream_node=u,upstream_pu=float(volts[u]),downstream_node=b,downstream_pu=float(volts[b]),accepted_tap_number=r['accepted_tap_number'],accepted_tap_pu=r['accepted_tap_pu'],Vreg_V=r['Vreg_V'],target_pu=r['target_pu'],deadband_low_pu=r['deadband_low_pu'],deadband_high_pu=r['deadband_high_pu'],upstream_is_native_global_witness=u==w['node'],downstream_is_native_global_witness=b==w['node']))
        for prev,r in zip(w['root_to_bus_path'],w['root_to_bus_path'][1:]):
            pathdeltas.append(dict(alpha=w['alpha'],witness=w['witness'],slot=w['slot'],order=r['order'],upstream_node=prev['node'],downstream_node=r['node'],upstream_pu=prev['voltage_pu'],downstream_pu=r['voltage_pu'],voltage_pu_increment=r['voltage_pu']-prev['voltage_pu'],incoming_element=r['incoming_element'],regulator_banks=r['banks_on_incoming_corridor'],crosses_up_into_overvoltage=r['crosses_up_into_overvoltage']))
        source_phase=w['root_to_bus_path'][0]['voltage_pu']
        onsets.append(dict(alpha=w['alpha'],witness=w['witness'],slot=w['slot'],native_witness_node=w['node'],source_path_node=w['root_to_bus_path'][0]['node'],source_path_pu=source_phase,source_path_already_exceeds_hard_ceiling=source_phase>1.05+1e-9,first_upcrossing_after_source=next((dict(incoming_element=r['incoming_element'],node=r['node'],pu=r['voltage_pu']) for r in w['root_to_bus_path'] if r['crosses_up_into_overvoltage']),None),all_upcrossings=[dict(incoming_element=r['incoming_element'],node=r['node'],pu=r['voltage_pu']) for r in w['root_to_bus_path'] if r['crosses_up_into_overvoltage']],interpretation='No crossing list does not mean no overvoltage: the path can start above the strict ceiling at the source terminal. Source deviations of order 1e-8 pu are explicitly distinguished from the material downstream rise.'))
    table(HERE/'REGULATOR_UPSTREAM_DOWNSTREAM_AT_WITNESSES.csv',neighborhood);table(HERE/'WITNESS_PATH_VOLTAGE_INCREMENTS.csv',pathdeltas);save(HERE/'OVERVOLTAGE_ONSET_CLASSIFICATION_AT_WITNESSES.json',onsets)
    index={(r['alpha'],r['witness'],r['case'],r['view']):r for r in cf};deltas=[];qc=[];unstable=[]
    for r in cf:
        key=(r['alpha'],r['witness']);b=index[(*key,'NATIVE',r['view'])]
        deltas.append(dict(alpha=r['alpha'],witness=r['witness'],slot=r['slot'],case=r['case'],view=r['view'],diagnostic_status=r['diagnostic_status'],usable_as_settled_comparison=r['diagnostic_status']=='CONVERGED',delta_global_Vmax_pu=r['Vmax_pu']-b['Vmax_pu'],delta_global_Vmin_pu=r['Vmin_pu']-b['Vmin_pu'],delta_at_original_witness_pu=r['original_witness_voltage_pu']-b['original_witness_voltage_pu'],delta_line_loading_pu=r['max_phase_line_loading_pu']-b['max_phase_line_loading_pu'],delta_cap_injection_kvar=r['total_cap_injected_kvar']-b['total_cap_injected_kvar']))
        folder=HERE/'diagnostic_no_instrumentation'/f'alpha_{r["alpha"]:.2f}'/f'{r["witness"]}_slot_{r["slot"]:02d}'/r['case'];detail=read(folder/'DIAGNOSTIC_RESULT.json');z=detail['views'][r['view']]
        assert detail['telemetry_setting_edits']==0 and not detail['production_adoption']
        if r['case']=='ALL_CAP_INJECTIONS_DISABLED':assert all(not c['enabled'] and abs(c['physical_injected_kvar'])<1e-8 for c in z['capacitors'])
        if r['case']=='UNCONTROLLED_CAP_ONLY_DISABLED':assert [c['capacitor'] for c in z['capacitors'] if not c['enabled']]==['capbank3']
        if r['case']=='SOURCE_AND_ALL_VREG_GLOBAL_SCALE':
            assert len(detail['parameter_changes'])==13
            for a,breg in zip(z['regulators'],model['regulators']):assert abs(a['Vreg_V']-breg['Vreg_V']/1.05)<1e-10
        if r['case']=='SOURCE_PU_1_ONLY':assert [x['Vreg_V'] for x in z['regulators']]==[x['Vreg_V'] for x in model['regulators']]
        if r['view']=='STATE_HELD':
            assert [x['accepted_tap_pu'] for x in z['regulators']]==[x['accepted_tap_pu'] for x in detail['native_accepted_regulators']]
            assert [x['step_states'] for x in z['capacitors']]==[x['step_states'] for x in detail['native_accepted_capacitors']]
        if r['diagnostic_status']!='CONVERGED':unstable.append(dict(alpha=r['alpha'],witness=r['witness'],slot=r['slot'],case=r['case'],control_iterations=z['control_iterations'],pending_queue=z['pending_control_queue'],last_iterate_metrics=z['metrics'],interpretation='Control response did not settle within the unchanged 1000-iteration solver limit. Last-iterate voltages are not a converged counterfactual result.'))
    table(HERE/'PAIRED_COUNTERFACTUAL_DELTAS.csv',deltas);save(HERE/'DIAGNOSTIC_CONTROL_NONSETTLING_CASES.json',unstable)
    # Paired direct-effect check: Vreg changes have no material physical effect with taps held.
    hold_error=max(abs(index[(w['alpha'],w['witness'],'SOURCE_PU_1_ONLY','STATE_HELD')]['original_witness_voltage_pu']-index[(w['alpha'],w['witness'],'SOURCE_AND_ALL_VREG_GLOBAL_SCALE','STATE_HELD')]['original_witness_voltage_pu']) for w in ws)
    assert hold_error<1e-5
    probe=read(HERE/'TELEMETRY_EDIT_SIDE_EFFECT_AUDIT.json');assert [r['step_states'] for r in probe['before']['caps']]==[r['step_states'] for r in probe['after_capcontrol_eventlog_edits']['caps']]
    comparisons=[]
    oldidx={(r['alpha'],r['witness'],r['case'],r['view']):r for r in read(HERE/'COUNTERFACTUAL_COMPARISON.json')}
    for r in cf:
        o=oldidx[(r['alpha'],r['witness'],r['case'],r['view'])]
        if abs(r['Vmax_pu']-o['Vmax_pu'])>1e-8 or r['diagnostic_status']!=o['diagnostic_status']:
            comparisons.append(dict(alpha=r['alpha'],witness=r['witness'],slot=r['slot'],case=r['case'],view=r['view'],earlier_status=o['diagnostic_status'],no_instrumentation_status=r['diagnostic_status'],earlier_Vmax=o['Vmax_pu'],no_instrumentation_Vmax=r['Vmax_pu']))
    save(HERE/'COUNTERFACTUAL_VERIFICATION_SCOPE.json',dict(status='PASS_DIAGNOSTIC_SCOPE_AND_STATE_MATCHING',primary_comparison='COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.csv',intervention_cases=50,views=100,initial_states='Each case replays the same native prefix, verified against frozen voltage arrays',state_held_taps_and_switch_states_exact=True,targeted_capacitor_disabling_verified=True,source_only_preserves_all_Vreg=True,global_case_factor=1/1.05,global_case_regulator_count=12,source_vs_coupled_held_witness_max_difference_pu=hold_error,telemetry_setting_edits_in_primary_comparison=0,earlier_counterfactual_set='Preserved in diagnostic_only/. The first 19 cases had no EventLog edits; later cases edited EventLog before control execution. Re-editing control objects produced different controller responses in some conditions despite unchanged visible starting taps/cap states. The fully uninstrumented 50-case set is used for classification.',earlier_vs_uninstrumented_differences=comparisons,nonsettling_cases=len(unstable),nonsettling_last_iterates_excluded_from_settled_effect_claims=True,production_adoptions=0))
    selected=read(OLD/'SELECTED_ALPHA_AND_B0_STATUS.json');assert selected['selected_alpha'] is None
    a0={c:index[(0.,'Vmax',c,'CONTROL_SETTLED')] for c in read(HERE/'DIAGNOSTIC_PREREGISTRATION.json')['cases']}
    cause=dict(classification='NATIVE_VOLTAGE_CONTROL_COMPATIBILITY_MISMATCH',scope='Root cause only; no production parameter selection',native_all_480_slots_converged_and_reproduced=True,original_NO_FEASIBLE_ALPHA_ON_FROZEN_GRID_preserved=True,original_selected_alpha=None,findings=[dict(code='FEEDER_REGULATOR_TARGET_DEADBAND_OVERLAPS_AND_EXCEEDS_HARD_CEILING',evidence=dict(Vreg=126.5,target_pu=model['regulators'][0]['target_pu'],deadband_high_pu=model['regulators'][0]['deadband_high_pu'],alpha1_Vmax_node='_hvmv_sub_lsb.3',alpha1_Vmax_pu=1.062024869600977)),dict(code='FIXED_CAPBANK3_SUPPORTS_LIGHT_LOAD_OVERVOLTAGE',evidence=dict(alpha0_native_background_P_kw=0,alpha0_native_background_Q_kvar=0,alpha0_PV_kw=0,fixed_bank='capbank3',nameplate_kvar=900,physical_kvar_at_native_witness=zero['total_capacitor_physical_injection_kvar'],native_Vmax=zero['metrics']['Vmax_pu'],fixed_cap_only_disabled_settled_Vmax=a0['UNCONTROLLED_CAP_ONLY_DISABLED']['Vmax_pu'])),dict(code='REGULATOR_INPUT_OVERVOLTAGE_IS_OUTSIDE_DOWNSTREAM_SENSING_TERMINAL',evidence=[r for r in neighborhood if r['upstream_is_native_global_witness']]),dict(code='SOURCE_ONLY_REDUCTION_IS_COUNTERACTED_BY_NATIVE_REGULATION',evidence=dict(alpha0_source_only_held_Vmax=index[(0.,'Vmax','SOURCE_PU_1_ONLY','STATE_HELD')]['Vmax_pu'],alpha0_source_only_control_settled_Vmax=a0['SOURCE_PU_1_ONLY']['Vmax_pu']))],background_scaling_alone='Independently insufficient on the preserved 21-point grid; alpha0 full background/PV removal still has Vmax>1.05. This does not assert a theorem about untested continuous alpha values.',diagnostic_limitations=dict(nonsettling_global_scaling_cases=unstable,native_controls_are_not_nonconvergent=True,witness_comparisons_are_not_96_slot_counterfactual_feasibility_certificates=True,finite_difference_effects_are_conditional_and_nonadditive=True),production_changes=0,B1_B2_B3_runs=0)
    save(HERE/'ROOT_CAUSE_CLASSIFICATION.json',cause)
    bad=[];before=read(HERE/'PROTECTED_AUTHORITIES_BEFORE.json')
    for r in before:
        p=Path(r['path']);s=p.stat()
        if sha(p)!=r['sha256'] or s.st_size!=r['bytes'] or s.st_mtime_ns!=r['mtime_ns']:bad.append(r['path'])
    assert not bad
    save(HERE/'IMMUTABILITY_FINAL_AUDIT.json',dict(status='PASS',protected_files=len(before),changed_files=bad,checks=['SHA256','bytes','mtime_ns'],prior_failure_result_preserved=True,source_PCC_topology_authority_changes=0,AIDC_MESS_scale_changes=0,mapping_changes=0,hard_limit_changes=0,production_parameter_adoptions=0,B1_B2_B3_runs=0))
    witness_lines='\n'.join(f"| {w['alpha']:.2f} | {w['witness']} | {w['slot']} | {w['node']} | {w['upstream_primary_phase']} | {w['value_pu']:.9f} |" for w in sorted(ws,key=lambda x:(-x['alpha'],x['witness'])))
    labels={'NATIVE':'Native','ALL_CAP_INJECTIONS_DISABLED':'All capacitors disabled','UNCONTROLLED_CAP_ONLY_DISABLED':'Fixed CAPBank3 only disabled','SOURCE_PU_1_ONLY':'Source pu=1.00 only','SOURCE_AND_ALL_VREG_GLOBAL_SCALE':'Source + all Vreg ×20/21'}
    a0lines='\n'.join(f"| {labels[c]} | {index[(0.,'Vmax',c,'STATE_HELD')]['Vmax_pu']:.9f} | {r['Vmin_pu']:.9f} | {r['Vmax_pu']:.9f} | {r['max_phase_line_loading_pu']:.6f} |" for c,r in a0.items())
    uns_lines='\n'.join(f"- alpha={r['alpha']:.2f}, {r['witness']}, slot {r['slot']}: 1000 control iterations; pending queue {r['pending_queue'][1:]}." for r in unstable)
    report=f'''# IEEE8500 B0 voltage-control compatibility forensic

**결론: NATIVE_VOLTAGE_CONTROL_COMPATIBILITY_MISMATCH.** 기존 `NO_FEASIBLE_ALPHA_ON_FROZEN_GRID`, selected alpha=null, FINAL 24-location mapping, PCC overlay, AIDC/MESS 규모와 hard limits를 모두 보존했다. 이 문서는 root-cause classification이며 production parameter 제안·선정·변경이 아니다.

## Native 96-slot 재현과 witness

대표 alpha 1.00, 0.60, 0.55, 0.25, 0.00의 총 480 slots를 새 엔진에서 재실행했다. 모든 슬롯이 수렴했고, 원본의 모든 전압·선로 current·transformer current/kVA 배열과 accepted tap/cap states가 일치했다. 최대 배열 차이는 0이다. 입력은 동결된 2025-05-21 B0 forecast/PQ이며 Actual 및 B1/B2/B3를 사용하지 않았다.

| Alpha | Witness | Slot (0-based) | Bus.local node | Upstream primary phase | Voltage pu |
|---:|---|---:|---|---|---:|
{witness_lines}

Local secondary node 2는 primary B상이 아니다. 각 witness는 service transformer의 실제 primary phase로 역추적했다. Source bus부터 frozen feeder root `_hvmv_sub_lsb`를 거치는 경로와 모든 bank의 accepted tap을 저장했다. Substation delta/wye의 phase label은 topology label이며 위상각이 보존된다는 뜻이 아니다.

## 분리된 원인

1. **Feeder-root regulator 제어 목표와 1.05 pu hard ceiling의 불일치.** Vreg=126.5 V, PT ratio=60, band=2 V는 compiled nominal base에서 target **{model['regulators'][0]['target_pu']:.9f} pu**, deadband **{model['regulators'][0]['deadband_low_pu']:.9f}–{model['regulators'][0]['deadband_high_pu']:.9f} pu**에 해당한다. Alpha 1.00의 global Vmax는 FEEDER_REGC 출구이며 accepted tap은 +2, 1.0125 pu다. Native controller가 자신의 허용 범위에 도달해도 uniform 1.05 pu hard limit는 위반할 수 있다.

2. **Fixed/uncontrolled CAPBank3의 light-load voltage rise.** Native model은 controlled capacitor 9개와 별도 uncontrolled 900-kvar three-phase CAPBank3를 포함한다. Alpha=0 Vmax witness에서 controlled capacitors는 OFF이고 CAPBank3는 약 **992.074821 kvar**를 주입한다. 독립 실행에서 native background P=Q=0, PV disabled를 모두 직접 확인했지만 Vmax **1.058661486 pu**가 재현됐다. AIDC 부하는 약 **550.730351 kW**로 그대로 남는다. 따라서 alpha=0은 전체 feeder 무부하 조건이 아니다.

3. **일부 과전압 witness는 regulator의 제어 대상 downstream bus가 아닌 upstream terminal이다.** Alpha 0.60/0.55는 VREG3 입구 `regxfmr_190-8581`, alpha 0.25/0.00은 VREG4 입구 `regxfmr_190-7361`에서 global Vmax가 발생한다. 해당 regulator의 buck tap으로 downstream voltage를 낮춰도 upstream witness는 직접 clamp되지 않는다. 각 phase의 입·출구 전압과 accepted tap은 별도 CSV에 있다.

4. **Source-only 변경에 대한 regulator의 보상 반응.** Source setpoint 1.05 pu는 이미 hard upper ceiling에 놓여 있다. Alpha=0의 동일 witness에서 source만 1.00으로 낮추면 taps-held Vmax는 **1.007828619 pu**로 내려가지만, native control response 후 **1.059430218 pu**로 다시 상승한다. 이는 source 설정 하나의 효과와 regulator feedback을 분리해 보여준다.

5. **Global scaling은 진단이며 안정한 production 해가 아니다.** Algebraic factor 20/21을 source 및 12개 Vreg에 함께 적용했다. Native bands와 capacitor settings는 유지했다. 일부 조건은 undervoltage/thermal 문제가 남고, 아래 세 조건은 native control response가 1000 iterations 안에 settle하지 않았다. 원래 native trajectories는 모두 수렴했으므로 이 진단에서 발생한 미수렴을 native alpha screen의 원인으로 혼동하면 안 된다.

## 동일 alpha=0 Vmax witness (slot 37) 비교

모든 case는 같은 native prefix, 같은 AIDC/background/PV/time, 같은 accepted tap/cap state에서 시작한다. State-held는 제어 실행을 멈추어 직접 전기적 효과를 보며, control-settled는 intervention 후 native feedback을 허용한다. 두 비교 모두 진단용이다.

| Diagnostic case | State-held global Vmax | Control-settled Vmin | Control-settled Vmax | Line max pu |
|---|---:|---:|---:|---:|
{a0lines}

이 witness에서는 all-capacitor 제거와 fixed CAPBank3만 제거한 결과가 거의 동일하다. Native controlled banks가 이미 OFF였다는 state evidence와 일치한다. 이 조건부 비교는 fixed shunt의 기여를 보여주며, production에서 capacitor를 제거하라는 결론이 아니다. 다른 alpha/witness에서는 controlled capacitor와 regulator feedback이 함께 작용하므로 차이를 additive 기여율로 합산하지 않는다.

## Counterfactual control 미수렴과 검증 범위

Primary 비교는 `diagnostic_no_instrumentation/`와 `COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.csv`이다. 10 native witness conditions ×5 cases ×2 views=100 비교를 모두 저장했다. 아래 CONTROL_SETTLED 요청은 실제로 **CONTROL_ITERATION_LIMIT_EXCEEDED**이며, 저장값은 converged 해가 아닌 last iterate다:

{uns_lines}

초기 실행의 첫 control-limit 예외를 보존하고 동일 조건으로 재검증했다. 중간 EventLog property 편집이 일부 control response를 바꾸는 현상이 확인돼, 최종 원인 분류는 **계측용 property 편집도 없는** 독립 비교만 사용한다. 이전 실행도 `diagnostic_only/` 및 비교 audit에 보존했으며 숨기거나 정상 해로 대체하지 않았다. Visible initial tap/cap states는 같았지만 내부 controller-state reset 여부는 인증하지 않았으므로 해당 runtime 내부 원인은 단정하지 않는다. Solver iteration cap이나 hard limits를 늘리지 않았다.

Native의 모든 96-slot data는 전체 trajectory 검증이다. Counterfactual은 두 global witness 조건만의 비교이므로, 어떤 variant에 대해서도 하루 전체 feasibility나 production 적합성을 주장하지 않는다.

## 과전압 시작 위치의 해석

`OVERVOLTAGE_ONSET_FRONTIERS_ALL_480_SLOTS.csv`는 모든 native slot에서 1.05+1e-9 경계를 아래에서 위로 통과하는 모든 oriented bus-phase link를 기록한다. Witness path의 재진입 crossing도 별도로 저장했다. Source terminal이 이미 threshold보다 약 1e-8 pu 높게 계산되는 경우에는 첫 crossing이 없을 수 있어 source-origin flag를 함께 기록한다. 이 작은 source-terminal 수치와 downstream의 0.0036–0.0209 pu 수준 rise를 구분한다. Hard threshold 자체는 변경하지 않았다.

## 최종 판정과 보존

**Background scaling alone은 원래 21-point grid에서 insufficient하다.** 원본 alpha=0의 Vmax>1.05 사실은 독립적으로 재현됐고 원본 전체 screen도 유지된다. 이는 미시험 continuous alpha 전체에 대한 불가능성 정리가 아니라, 동결된 model·limits·grid에 대한 결과다.

주요 산출물:

- `GLOBAL_WITNESSES.csv`, `GLOBAL_WITNESSES_FULL.json`, `native/alpha_*/Vmax_ROOT_TO_BUS_PATH.csv`, `Vmin_ROOT_TO_BUS_PATH.csv`
- `REGULATOR_BANK_ACCEPTED_TAPS_ALL_480_SLOTS.csv`, `CAPACITOR_BANK_STATES_AND_KVAR_ALL_480_SLOTS.csv`, `SOURCE_VOLTAGES_ALL_480_SLOTS.csv`
- `REGULATOR_UPSTREAM_DOWNSTREAM_AT_WITNESSES.csv`, `WITNESS_PATH_VOLTAGE_INCREMENTS.csv`, `OVERVOLTAGE_ONSET_CLASSIFICATION_AT_WITNESSES.json`
- `COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.csv`, `PAIRED_COUNTERFACTUAL_DELTAS.csv`, 각 case의 `DIAGNOSTIC_RESULT.json` 및 voltage array
- `DIAGNOSTIC_CONTROL_NONSETTLING_CASES.json`, `INDEPENDENT_ALPHA_ZERO_CONFIRMATION.json`, `ROOT_CAUSE_CLASSIFICATION.json`
- `IMMUTABILITY_FINAL_AUDIT.json`: 이전 source/PCC/topology 및 alpha-screen **{len(before)}개 파일**의 SHA256·size·mtime 변경 0
- `FORENSIC_EVIDENCE_FREEZE_MANIFEST.json`와 `.sha256`: 진단 evidence만의 seal. Production parameter authority가 아니다.

AIDC/MESS 규모 변경 0, 24-location/PCC 변경 0, hard voltage/thermal limit 변경 0, production parameter 채택 0, B1/B2/B3 실행 0.
'''
    (HERE/'IEEE8500_B0_VOLTAGE_CONTROL_FORENSIC_REPORT.md').write_text(report,encoding='utf-8')
    save(HERE/'EXECUTION_ACCOUNTING.json',dict(final_native_96_slot_replays=5,native_replayed_slots=480,initial_interrupted_attempt_native_replays_repeated=2,interrupted_attempt_note='Two completed 96-slot native trajectories and 19 completed counterfactual cases preceded the first #485 exception in the twentieth case. Native trajectories were repeated to persist complete 480-slot device-state evidence; 19 completed first-pass case artifacts were reused.',first_counterfactual_set_completed_cases=50,primary_no_instrumentation_independent_cases=50,primary_no_instrumentation_views=100,primary_nonsettling_cases=len(unstable),independent_alpha_zero_prefix_solves=38,telemetry_side_effect_probe_prefix_solves=31,telemetry_side_effect_probe_state_held_solves=1,B1_B2_B3_runs=0,optimizer_calls=0,production_setting_changes=0))
    files=[dict(path=p.relative_to(HERE).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name not in ['FORENSIC_EVIDENCE_FREEZE_MANIFEST.json','FORENSIC_EVIDENCE_FREEZE_MANIFEST.sha256'] and '__pycache__' not in p.parts]
    save(HERE/'FORENSIC_EVIDENCE_FREEZE_MANIFEST.json',dict(classification=cause['classification'],purpose='DIAGNOSTIC_ROOT_CAUSE_ONLY',production_parameter_authority=False,original_failure_result_preserved=True,protected_files_unchanged=len(before),files=files));h=sha(HERE/'FORENSIC_EVIDENCE_FREEZE_MANIFEST.json');(HERE/'FORENSIC_EVIDENCE_FREEZE_MANIFEST.sha256').write_text(h+'  FORENSIC_EVIDENCE_FREEZE_MANIFEST.json\n',encoding='ascii')
    assert all(sha(HERE/r['path'])==r['sha256'] for r in files)
    print(json.dumps(dict(classification=cause['classification'],protected_files=len(before),frozen_files=len(files),nonsettling_diagnostic_cases=len(unstable),manifest_sha256=h)))
if __name__=='__main__':main()
