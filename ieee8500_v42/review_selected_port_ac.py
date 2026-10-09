"""Independent saved finite-port audit; no AC, Native or re-selection."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import ROOT,REPORT,read,write,receipt
from .geometry import read_csv

FOLDER=REPORT/'joint_selection_v3/selected_port_ac'


def audit_automatic_saved(rows,states,inventory,mapping,commands,legacy):
    """Recompute saved endpoint checks without calling the producing engine."""
    keys=['site','slot','P_injection_kw','Q_injection_kvar']
    if len(rows)!=384 or rows.duplicated(keys).any() or len(states)!=384:
        raise ValueError('AUTOMATIC_LOCAL_384_UNIQUE_ENDPOINTS_REQUIRED')
    for site,group in rows.groupby('site'):
        if site not in mapping or set(group.bus)!={mapping[site]['candidate_bus']} or set(group.slot)!={0,9,48,75} or len(group)!=32:
            raise ValueError('AUTOMATIC_SELECTED_PORT_OR_FOUR_TIMES_CHANGED')
        for _,slotrows in group.groupby('slot'):
            if set(zip(slotrows.P_injection_kw,slotrows.Q_injection_kvar))!=commands:
                raise ValueError('AUTOMATIC_EIGHT_COMMANDS_REQUIRED')
    if set(rows.site)!=set(mapping) or not rows.source_initial_reset.all() or not rows.converged.all() or not rows.control_actions_done.all() or rows.control_queue_size.any():
        raise ValueError('AUTOMATIC_ORIGINAL_RESET_OR_SETTLING_FAILED')
    if not np.isfinite(rows.select_dtypes(include='number').to_numpy()).all() or (rows.actual_VLL_V<=0).any():
        raise ValueError('AUTOMATIC_NONFINITE_READBACK')
    pqerr=np.maximum(abs(rows.actual_P_kw+rows.P_injection_kw),abs(rows.actual_Q_kvar+rows.Q_injection_kvar))
    pq_aggregate_error=float(abs(pqerr-rows.PQ_readback_error).max())
    if pq_aggregate_error>1e-12 or pqerr.max()>1e-6 or rows.hot_KCL_A.max()>1e-9:
        raise ValueError('AUTOMATIC_ACTUAL_PQ_OR_BALANCED_KCL_FAILED')
    apparent=np.hypot(rows.P_injection_kw,rows.Q_injection_kvar)
    commandI=apparent*1000/rows.actual_VLL_V
    actualI=np.hypot(rows.actual_P_kw,rows.actual_Q_kvar)*1000/rows.actual_VLL_V
    hot_error=float(np.maximum(abs(actualI-rows.hot1_A),abs(actualI-rows.hot2_A)).max())
    command_hot_error=float(np.maximum(abs(commandI-rows.hot1_A),abs(commandI-rows.hot2_A)).max())
    hardware=(abs(rows.P_injection_kw)<=5)&(abs(rows.Q_injection_kvar)<=3)&(apparent<=6)&(commandI<=27)
    local=(rows.local_voltage_min_pu>=.95)&(rows.local_voltage_max_pu<=1.05)&(rows.local_line_rho_max<=1)&(rows.CT_current_rho_max<=1)&(rows.CT_nameplate_rho_max<=1)
    if hot_error>1e-7 or command_hot_error>1e-6 or not (hardware==rows.interface_envelope_PASS).all() or not (local==rows.local_original_grid_PASS).all() or not hardware.all() or not local.all():
        raise ValueError('AUTOMATIC_LOCAL_HARDWARE_FLAGS_OR_ACTUAL_HOT_READBACK_MISMATCH')
    if (rows.CT_current_rho_max>rows.transformer_current_rho_max+1e-10).any() or (rows.CT_nameplate_rho_max>rows.transformer_nameplate_kva_rho_max+1e-10).any() or (rows.local_line_rho_max>rows.all_terminal_line_rho_max+1e-10).any():
        raise ValueError('AUTOMATIC_LOCAL_MAX_EXCEEDS_GLOBAL_MAX')
    state_by_key={}
    transformer={r['element'].split('.',1)[1].lower():r for r in inventory['transformers']}
    regnames={r['transformer'].lower() for r in inventory['regcontrols']}
    caps={r['name'].lower():r for r in inventory['capacitors']}
    step_error=0.
    for item in states:
        key=(item['site'],item['slot'],item['P'],item['Q'])
        if key in state_by_key:raise ValueError('AUTOMATIC_STATE_KEY_DUPLICATION')
        state=item['state']
        raw=json.dumps(state,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
        computed=hashlib.sha256(raw).hexdigest()
        if computed!=item['sha256']:raise ValueError('AUTOMATIC_PERSISTED_STATE_SHA_MISMATCH')
        if set(state)!= {'taps','capacitors'} or set(state['taps'])!=regnames or set(state['capacitors'])!=set(caps):
            raise ValueError('AUTOMATIC_ORIGINAL_CONTROL_AXES_CHANGED')
        for name,taps in state['taps'].items():
            windings=transformer[name]['windings']
            if len(taps)!=len(windings):raise ValueError('AUTOMATIC_ORIGINAL_WINDING_AXIS_CHANGED')
            for value,w in zip(taps,windings):
                if not np.isfinite(value) or value<w['mintap']-1e-10 or value>w['maxtap']+1e-10:
                    raise ValueError('AUTOMATIC_TAP_OUTSIDE_ORIGINAL_BOUNDS')
                if w['numtaps']:
                    step=(w['maxtap']-w['mintap'])/w['numtaps']
                    position=(value-w['mintap'])/step
                    step_error=max(step_error,abs(position-round(position)))
        for name,values in state['capacitors'].items():
            if len(values)!=int(caps[name]['properties']['NumSteps']) or any(v not in (0,1) for v in values):
                raise ValueError('AUTOMATIC_ORIGINAL_CAPACITOR_STEP_AXIS_CHANGED')
        state_by_key[key]=(computed,state)
    if step_error>1e-8:raise ValueError('AUTOMATIC_TAP_OFF_ORIGINAL_DISCRETE_LATTICE')
    indexed=rows.set_index(keys).sort_index();old=legacy.set_index(keys).sort_index()
    if not indexed.index.equals(old.index) or set(state_by_key)!=set(indexed.index):
        raise ValueError('AUTOMATIC_STATE_ROW_AND_ORIGINAL_ARCHIVE_KEYS_MISMATCH')
    legacy_numeric_error=0.
    for column in sorted(set(indexed.columns)&set(old.columns)):
        if indexed[column].dtype.kind in 'fi' and old[column].dtype.kind in 'fi':
            legacy_numeric_error=max(legacy_numeric_error,float(abs(indexed[column]-old[column]).max()))
        elif not indexed[column].equals(old[column]):
            raise ValueError('AUTOMATIC_ORIGINAL_GLOBAL_ARCHIVE_CHANGED')
    if legacy_numeric_error>1e-9:raise ValueError('AUTOMATIC_ORIGINAL_GLOBAL_NUMERIC_ARCHIVE_MISMATCH')
    for key,row in indexed.iterrows():
        checksum,state=state_by_key[key]
        if row.settled_state_sha256!=checksum or ast.literal_eval(old.loc[key,'tap_state'])!=state['taps']:
            raise ValueError('AUTOMATIC_ROW_STATE_SHA_OR_ORIGINAL_TAP_ARCHIVE_MISMATCH')
    globalpass=(rows.Vmin>=.95)&(rows.Vmax<=1.05)&(rows.all_terminal_line_rho_max<=1)&(rows.transformer_current_rho_max<=1)&(rows.transformer_nameplate_kva_rho_max<=1)
    if globalpass.any():raise ValueError('AUTOMATIC_BASELINE_GLOBAL_FAIL_SCOPE_CHANGED')
    return dict(rows=384,all_sampled_local_hardware_PASS=True,actual_PQ_max_error=float(pqerr.max()),
        PQ_error_column_aggregate_error=pq_aggregate_error,actual_hot_S_div_VLL_max_error_A=hot_error,
        command_hot_S_div_VLL_max_error_A=command_hot_error,balanced_hot_KCL_max_A=float(rows.hot_KCL_A.max()),
        local_voltage_min_pu=float(rows.local_voltage_min_pu.min()),local_voltage_max_pu=float(rows.local_voltage_max_pu.max()),
        maximum_port_hot_A=float(np.maximum(rows.hot1_A,rows.hot2_A).max()),maximum_local_Triplex_rho=float(rows.local_line_rho_max.max()),
        maximum_CT_current_rho=float(rows.CT_current_rho_max.max()),maximum_CT_nameplate_rho=float(rows.CT_nameplate_rho_max.max()),
        original_control_state_checksum_rows=384,original_tap_lattice_max_fractional_error=step_error,
        original_global_archive_max_numeric_error=legacy_numeric_error,original_global_archive_taps_match=True,
        persisted_state_proves_recorded_settled_taps_and_caps=True,original_initial_reset_verified_from_producer_code_and_row_declaration=True,
        initial_pre_solve_state_persisted=False,global_grid_PASS=0,full_automatic_domain_certified=False)


def review():
    p=read(FOLDER/'PREREGISTRATION.json')
    fixed=pd.read_csv(FOLDER/'PCC_FULL_RATING96_RESULTS.csv')
    hots=pd.read_csv(FOLDER/'TRIPLEX_ALL_HOT_CURRENT96.csv')
    neutral=pd.read_csv(FOLDER/'TRIPLEX_IMPLIED_NEUTRAL96.csv')
    summary=pd.read_csv(FOLDER/'PORT_QUALIFICATION_SUMMARY.csv')
    auto=pd.read_csv(FOLDER/'AUTOMATIC_FULL_RATING4_TIME.csv')
    inventory=read(REPORT/'ORIGINAL_FEEDER_INVENTORY.json')
    src={r['element']:r for r in inventory['lines']}
    mapping={r['location_id']:r for r in read_csv(REPORT/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv') if r['role']=='STA'}
    lvmeta={r['candidate_bus']:r for r in read_csv(REPORT/'LV_STA_CANDIDATES.csv')}
    keys=['site','slot','P_injection_kw','Q_injection_kvar']
    if len(fixed)!=9216 or fixed.duplicated(keys).any() or len(summary)!=12:
        raise ValueError('FIXED_12_96_8_COMMAND_COVERAGE_REQUIRED')
    commands={tuple(x) for x in p['commands']}
    if commands!={(5,0),(-5,0),(0,3),(0,-3),(5,3),(5,-3),(-5,3),(-5,-3)}:
        raise ValueError('EXACT_PREDEFINED_EIGHT_COMMANDS_REQUIRED')
    for site,group in fixed.groupby('site'):
        if site not in mapping or set(group.bus)!={mapping[site]['candidate_bus']}:
            raise ValueError('SELECTED_LV_BUS_CHANGED')
        if len(group)!=768 or set(group.slot)!=set(range(96)):
            raise ValueError('ALL_96_SLOT_PORT_COMMAND_COVERAGE_REQUIRED')
        for _,slotrows in group.groupby('slot'):
            if set(zip(slotrows.P_injection_kw,slotrows.Q_injection_kvar))!=commands:
                raise ValueError('MISSING_OR_DUPLICATE_FINITE_PQ_COMMAND')
    s=np.hypot(fixed.P_injection_kw,fixed.Q_injection_kvar)
    expectedI=s*1000/fixed.actual_VLL_V
    ierr=float(np.maximum(abs(expectedI-fixed.port_hot1_current_A),abs(expectedI-fixed.port_hot2_current_A)).max())
    hardware=(abs(fixed.P_injection_kw)<=5)&(abs(fixed.Q_injection_kvar)<=3)&(s<=6)&(expectedI<=27)
    local=(fixed.local_triplex_rho_max<=1)&(fixed.original_CT_current_rho_max<=1)&(fixed.original_CT_nameplate_rho_max<=1)&(fixed.local_PCC_Vmin>=.95)&(fixed.local_PCC_Vmax<=1.05)
    if ierr>1e-7 or not (hardware==fixed.interface_envelope_PASS).all() or not (local==fixed.local_original_grid_constraints_PASS).all():
        raise ValueError('ACTUAL_VLL_HOT_CURRENT_OR_LOCAL_CONSTRAINT_FLAGS_MISMATCH')
    if fixed.actual_PQ_readback_error.max()>1e-6 or fixed.hot_KCL_A.max()>1e-9:
        raise ValueError('ACTUAL_PQ_READBACK_OR_BALANCED_HOT_KCL_FAILED')
    if not hardware.all() or not local.all() or fixed.full_grid_AC_constraints_PASS.any():
        raise ValueError('SAMPLED_LOCAL_PASS_GLOBAL_FAIL_SCOPE_MISMATCH')
    if fixed.field_installed_or_protection_approved.any() or fixed.policy_schedule.any():
        raise ValueError('UNSUPPORTED_FIELD_OR_POLICY_CLAIM')
    # Every original Triplex conductor and both ends are retained. Independent
    # source NormalAmps and exact magnitude changes/rho are reconstructed.
    if hots.duplicated(keys+['element','terminal','node']).any():raise ValueError('HOT_AXIS_DUPLICATION')
    if set(hots.node)!={1,2} or set(hots.terminal)!={1,2}:raise ValueError('BOTH_HOTS_AND_TERMINALS_REQUIRED')
    if hots.groupby(keys).ngroups!=9216 or neutral.groupby(keys).ngroups!=9216:
        raise ValueError('ALL_COMMAND_LOCAL_LINE_NEUTRAL_CONTEXTS_REQUIRED')
    for key,group in hots.groupby(keys):
        paths=lvmeta[mapping[key[0]]['candidate_bus']]['triplex_path'].split('|')
        expected={(line,t,node) for line in paths for t in (1,2) for node in (1,2)}
        actual={(row.element.lower(),row.terminal,row.node) for row in group.itertuples()}
        if actual!=expected:raise ValueError('ALL_ORIGINAL_PATH_TERMINAL_HOT_AXES_REQUIRED')
    for key,group in neutral.groupby(keys):
        paths=lvmeta[mapping[key[0]]['candidate_bus']]['triplex_path'].split('|')
        if {(row.element.lower(),row.terminal) for row in group.itertuples()}!={(line,t) for line in paths for t in (1,2)}:
            raise ValueError('ALL_ORIGINAL_PATH_NEUTRAL_TERMINAL_AXES_REQUIRED')
    if any(row.normal_amps!=src[row.element]['normal_amps'] for row in hots.itertuples()):
        raise ValueError('ORIGINAL_TRIPLEX_HOT_AMPACITY_CHANGED')
    hotrhoerr=float(abs(hots.actual_current_A/hots.normal_amps-hots.actual_rho).max())
    hotchangeerr=float(abs(hots.actual_current_A-hots.baseline_current_A-hots.current_change_A).max())
    if max(hotrhoerr,hotchangeerr)>1e-10 or (hots.actual_rho>1).any():raise ValueError('HOT_CURRENT_MAGNITUDE_RHO_OR_OVERLOAD_MISMATCH')
    # Magnitudes alone cannot prove each phasor. The triangle inequality is an
    # independent necessary check of the archived implied-neutral magnitudes.
    hk=keys+['element','terminal']
    hp=hots.pivot(index=hk,columns='node',values=['actual_current_A','baseline_current_A'])
    nr=neutral.set_index(hk)
    if len(nr)!=len(hp) or not nr.index.equals(hp.index):nr=nr.reindex(hp.index)
    if nr.actual_implied_neutral_A.isna().any() or nr.rating_A.notna().any() or set(nr.independent_rating)!={'UNVERIFIED_SOURCE_KRON_REDUCED'}:
        raise ValueError('NEUTRAL_SOURCE_UNRATED_COVERAGE_OR_INVENTED_RATING')
    nerrors=[]
    for tag,column in [('actual','actual_implied_neutral_A'),('baseline','baseline_implied_neutral_A')]:
        i1=hp[(tag+'_current_A',1)];i2=hp[(tag+'_current_A',2)];value=nr[column]
        nerrors.extend([float(np.maximum(abs(i1-i2)-value,0).max()),float(np.maximum(value-i1-i2,0).max())])
    if max(nerrors)>1e-8:raise ValueError('IMPLIED_NEUTRAL_PHASOR_TRIANGLE_INCONSISTENT')
    # Local maximum current in each full-PQ row must be the maximum of all its
    # independently archived original Triplex hot terminal currents.
    hmax=hots.groupby(keys).actual_rho.max();fidx=fixed.set_index(keys)
    localrhoerr=float(abs(hmax-fidx.local_triplex_rho_max).max())
    if localrhoerr>1e-10:raise ValueError('FULL_RATING_ROW_TRIPLEX_MAX_MISMATCH')
    records=[];summaryerr=0.
    for site,rows in fixed.groupby('site'):
        sr=summary[summary.site.eq(site)].iloc[0]
        h=hots[hots.site.eq(site)]
        discharge=h[h.P_injection_kw.eq(5)&h.Q_injection_kvar.eq(0)]
        charge=h[h.P_injection_kw.eq(-5)&h.Q_injection_kvar.eq(0)]
        numbers=dict(minimum_discharge5kw_hot_current_change_A=float(discharge.current_change_A.min()),
            maximum_discharge5kw_hot_current_change_A=float(discharge.current_change_A.max()),
            maximum_charge5kw_hot_current_change_A=float(charge.current_change_A.max()),
            maximum_charge5kw_rho=float(charge.actual_rho.max()),
            maximum_original_CT_nameplate_rho=float(rows.original_CT_nameplate_rho_max.max()))
        summaryerr=max(summaryerr,max(abs(float(sr[name])-value) for name,value in numbers.items()))
        reverse_primary=bool((rows.original_CT_primary_P_kw<0).any())
        reverse_leg=bool((rows.original_CT_secondary_max_P_kw>0).any())
        if bool(sr.reverse_service_primary_power_seen)!=reverse_primary or bool(sr.reverse_individual_leg_power_seen)!=reverse_leg:
            raise ValueError('PASSIVE_CT_REVERSE_POWER_SIGN_CLASSIFICATION_FAILED')
        if int(sr.commands_checked)!=768 or not sr.hardware_full_box_PASS or not sr.full_box_local_grid_PASS or sr.local_grid_failed_command_cells:
            raise ValueError('PORT_SUMMARY_768_FIXED_SAMPLE_PASS_MISMATCH')
        if sr.field_reverse_power_protection!='UNVERIFIED' or sr.production_ready:
            raise ValueError('UNSUPPORTED_REVERSE_PROTECTION_APPROVAL')
        for slot,group in rows.groupby('slot'):
            pos=group[group.P_injection_kw.eq(5)&group.Q_injection_kvar.eq(0)].iloc[0]
            neg=group[group.P_injection_kw.eq(-5)&group.Q_injection_kvar.eq(0)].iloc[0]
            if pos.original_CT_primary_P_kw>=neg.original_CT_primary_P_kw:
                raise ValueError('DEMAND_POSITIVE_PASSIVE_CT_PRIMARY_DIRECTION_INCONSISTENT')
        records.append(dict(site=site,bus=sr.bus,fixed_sampled_commands=768,all_sampled_local_hardware_PASS=True,
            **numbers,reverse_primary_service_seen=reverse_primary,individual_secondary_leg_reverse_seen=reverse_leg,
            discharge_can_increase_one_hot_magnitude=bool((discharge.current_change_A>0).any()),
            aggregate_primary_min_P_kw=float(rows.original_CT_primary_P_kw.min()),
            ordinary_negative_secondary_is_not_service_reverse=True,reverse_protection='UNVERIFIED'))
    if summaryerr>1e-10:raise ValueError('PORT_SUMMARY_CURRENT_BOUNDS_MISMATCH')
    if len(auto)!=384 or auto.duplicated(keys).any() or set(auto.slot)!={0,9,48,75} or not auto.converged.all() or not auto.control_actions_done.all() or auto.control_queue_size.any():
        raise ValueError('AUTOMATIC_384_SAVED_CONVERGENCE_COVERAGE_FAILED')
    af=FOLDER/'automatic_local_audit'
    ap=read(af/'PREREGISTRATION.json');ar=read(af/'RECEIPT.json')
    if ap['mapping']['sha256']!=receipt(REPORT/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv')['sha256'] or set(tuple(x) for x in ap['commands'])!=commands or set(ap['slots'])!={0,9,48,75}:
        raise ValueError('AUTOMATIC_FROZEN_INPUT_IDENTITY_CHANGED')
    automatic=audit_automatic_saved(pd.read_csv(af/'AUTOMATIC_PCC_LOCAL_FULL_RATING.csv'),
        read(af/'ORIGINAL_AUTOMATIC_CONTROL_STATES.json'),inventory,mapping,commands,auto)
    if ar['cases']!=384 or not ar['all_sampled_local_PASS'] or not ar['all_sampled_hardware_PASS'] or not ar['original_source_identity'] or ar['continuous_domain_certificate'] or ar['baseline_global_voltage_PASS']:
        raise ValueError('AUTOMATIC_RECEIPT_SCOPE_OR_COUNTS_MISMATCH')
    if max(abs(ar['maximum_PQ_error']-automatic['actual_PQ_max_error']),abs(ar['maximum_KCL_A']-automatic['balanced_hot_KCL_max_A']))>1e-12:
        raise ValueError('AUTOMATIC_RECEIPT_MAXIMA_MISMATCH')
    response=REPORT/'joint_selection_v3/selected_response'
    bounded=pd.read_csv(response/'SELECTED_LOCAL_BOUNDED_ACTION_AC.csv')
    if len(bounded)!=48 or bounded.duplicated(['site','slot']).any() or not bounded.local_original_grid_PASS.all() or not bounded.interface_envelope_PASS.all():
        raise ValueError('SELECTED_48_BOUNDED_ACTION_SAMPLED_PASS_FAILED')
    if not bounded.converged.all() or not bounded.control_actions_done.all() or bounded.control_queue_size.any() or bounded.global_feasible_policy.any():
        raise ValueError('BOUNDED_RESPONSE_SETTLING_OR_SCOPE_MISMATCH')
    chosen=pd.read_csv(REPORT/'joint_selection_v3/score_selection/SELECTED_STA_SCORE_ACTIONS.csv').set_index(['location_id','slot'])
    actionerr=0.
    for row in bounded.itertuples():
        expected=chosen.loc[(row.site,row.slot)]
        actionerr=max(actionerr,abs(row.P_injection_kw-expected.P_design_choice_kw),abs(row.Q_injection_kvar-expected.Q_design_choice_kvar))
    if actionerr>1e-10:raise ValueError('SELECTED_BOUNDED_ACTION_CHANGED_AFTER_SCORE_SELECTION')
    inp=[Path(__file__),ROOT/'ieee8500_v42/selected_port_ac.py',ROOT/'ieee8500_v42/selected_response.py',ROOT/'ieee8500_v42/selected_auto_port_audit.py',REPORT/'ORIGINAL_FEEDER_INVENTORY.json',REPORT/'LV_STA_CANDIDATES.csv',REPORT/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv']
    inp+=[FOLDER/name for name in ('PREREGISTRATION.json','RECEIPT.json','PCC_FULL_RATING96_RESULTS.csv',
        'TRIPLEX_ALL_HOT_CURRENT96.csv','TRIPLEX_IMPLIED_NEUTRAL96.csv','PORT_QUALIFICATION_SUMMARY.csv','AUTOMATIC_FULL_RATING4_TIME.csv')]
    inp+=[response/name for name in ('PREREGISTRATION.json','RECEIPT.json','SELECTED_LOCAL_BOUNDED_ACTION_AC.csv',
        'SELECTED_STA_TARGET_LINE_EFFECT.csv','INSTANTANEOUS_COMPLEMENTARITY_NOT_POLICY.csv')]
    inp+=[af/name for name in ('PREREGISTRATION.json','RECEIPT.json','AUTOMATIC_PCC_LOCAL_FULL_RATING.csv','ORIGINAL_AUTOMATIC_CONTROL_STATES.json')]
    report=dict(status='PASS_ARCHIVED_FINITE_FIXED_SAMPLES_AND_BOUNDARY_AUDIT',ports=12,
        fixed_sampled_commands=9216,commands_per_port=768,original_auto_global_only_archive_rows=384,
        focused_automatic_local_saved_audit=automatic,
        local_hardware_constraints_all_fixed_samples_PASS=True,full_grid_PASS_fixed_samples=0,
        actual_hot_S_div_VLL_max_error_A=ierr,actual_PQ_readback_max_error=float(fixed.actual_PQ_readback_error.max()),
        balanced_PCC_hot_KCL_max_A=float(fixed.hot_KCL_A.max()),source_Triplex_rho_error=hotrhoerr,
        source_Triplex_current_change_error_A=hotchangeerr,Triplex_local_max_aggregate_error=localrhoerr,
        implied_neutral_triangle_max_excess_A=max(nerrors),neutral_independent_rating_unavailable=True,
        port_summary_maximum_error=summaryerr,site_records=records,
        selected_48_bounded_actions_local_hardware_PASS=True,selected_action_original_command_max_error=actionerr,
        new_global_line_overload_fixed_rows=int((fixed.new_global_line_overload_cells>0).sum()),
        new_global_voltage_violation_fixed_rows=int((fixed.new_global_voltage_violation_cells>0).sum()),
        reverse_primary_service_ports=sum(r['reverse_primary_service_seen'] for r in records),
        reverse_secondary_leg_ports=sum(r['individual_secondary_leg_reverse_seen'] for r in records),
        primary_reverse_power_definition='P into transformer PRIMARY winding <0; ordinary secondary delivered power is negative and is not aggregate reverse',
        both_discharge_current_decrease_and_increase_ports=[r['site'] for r in records if r['discharge_can_increase_one_hot_magnitude']],
        full_continuous_PQ_domain_certified=False,full_automatic_tap_domain_certified=False,
        routing_SOC_QoS_policy_certified=False,global_B0_voltage_qualified=False,field_reverse_protection_approved=False,
        archive_evidence_limits=['Fixed original_taps_caps_fixed_same_base field is a producer declaration; actual per-endpoint state hashes are not archived. Source solve restores fixed state and sets controlmode off.',
            'Original384 automatic rows retain global summaries/tap dictionaries only; a separate focused384 saved audit now supplies actual local PCC/hardware readbacks and settled tap/cap state hashes, with matching original global values and taps.',
            'Focused automatic hashes prove recorded final settled taps/caps, not a stored initial pre-solve state. Original initial reset is supported by producer code and each row declaration.',
            'Triplex hot CSV stores magnitudes and signed magnitude changes, not complex phasors or branch real power. Per-hot phase/power reversal cannot be inferred solely from magnitude increases.',
            'Eight points per time do not certify the continuous nonlinear P/Q box or full automatic-control domains.',
            'All fixed full-grid states retain baseline global failures; local pass is not global scenario or dispatch qualification'],
        Native_calls=0,AC_solves=0,full_model_builds=0,inputs={str(p.relative_to(ROOT)):receipt(p) for p in inp})
    write(FOLDER/'INDEPENDENT_PORT_REVIEW.json',report)
    lines=['# 선정 저압 포트 유한 AC 끝점 독립 검토','',
        '저장된 12개 STA×96개 시점×8개 P/Q 명령 **9,216개 fixed 끝점**, 원384개 automatic 요약, 별도 focused automatic384개 실제 국부 읽기를 검토했다. 원 수치·좌표·정격·선정 결과를 바꾸거나 추가 AC/Native를 실행하지 않았다. fixed9,216개와 automatic384개의 **표본 국부 계통/하드웨어 전부 PASS**가 재현되며, 두 검사 모두 전체 계통 PASS는 **0개**다.','',
        f'| 검사 | 최대 오차/결과 |\n|---|---:|\n| actual S/VLL 대 두 hot 전류 | {ierr:.3g} A |\n| 실제 P/Q 읽기 | {fixed.actual_PQ_readback_error.max():.3g} |\n| 두 hot 복소 전류 KCL | {fixed.hot_KCL_A.max():.3g} A |\n| 원 Triplex I/NormalAmps | {hotrhoerr:.3g} |\n| 실제−기준 hot 크기 변화 | {hotchangeerr:.3g} A |\n| 포트 요약 수치 재집계 | {summaryerr:.3g} |','',
        '원 Triplex의 모든 경로·양 단자·두 hot 축과 원 정격을 확인했다. 중성선은 원 Kron 축약의 추정값이고 독립 정격이 비어 있다. hot 크기와 추정 neutral 값의 삼각 부등식 및 원 기준/교란 대응을 검산했으나, 크기만으로 복소 neutral phasor나 독립 ampacity 통과를 증명하지 않는다.','',
        '원 transformer는 passive sign이다. **PRIMARY P<0가 전체 서비스 upstream 역송전**이고, 보통 부하로 전달되는 SECONDARY P<0를 역송전으로 잘못 세지 않았다. SECONDARY leg P>0는 그 개별 leg에서의 반대 방향 전력이다. '+f"전체 primary 역송전을 보는 포트는 {sum(r['reverse_primary_service_seen'] for r in records)}개, 개별 secondary leg 역송전은 {sum(r['individual_secondary_leg_reverse_seen'] for r in records)}개다. 원 보호 허용은 UNVERIFIED다.",'',
        '5kW 방전 때 일부 hot 크기는 줄지만 STA03/04/06의 다른 hot는 증가할 수 있다. 이는 불균형 원 부하와 단일 240V balanced 주입의 크기 반응이며, hot 크기 증가만으로 실제 분기 phasor/전력 방향을 단정할 수 없다. 충전5kW hot 증가와 최대 original rho를 포트 요약에서 그대로 재집계했다.','',
        '점수에서 선택한 48개 bounded P/Q 행동도 원 command와 일치하고 실제 국부/하드웨어 PASS다. 초기6대 동시 진단은 routing/SoC/QoS dispatch가 아닌 known-only/순간 전기 반응이다. 단일 포트8명령 검사, 제한된 자동 제어 검사, 48행의 국부 성공을 continuous P/Q×자동탭 전체 영역이나 전체 A/M 정책의 증명으로 확장하지 않는다.','',
        f"별도 automatic384개는 실제 P/Q 합산 오차 {automatic['actual_PQ_max_error']:.3g}, 실제 S/VLL–hot 전류 오차 {automatic['actual_hot_S_div_VLL_max_error_A']:.3g}A, hot KCL {automatic['balanced_hot_KCL_max_A']:.3g}A다. 원 CT current/권선 nameplate, 원 Triplex 양단 hot 최대 및 PCC 전압을 저장 열에서 독립 재판정했다. 모든 실제 국부 전압은 {automatic['local_voltage_min_pu']:.9f}–{automatic['local_voltage_max_pu']:.9f}pu, 최대 hot {automatic['maximum_port_hot_A']:.6f}A다.",'',
        'automatic의384개 persisted settled state를 표준 JSON 규칙으로 별도 SHA256 재계산해 각 command 행과 대조했다. 원12개 regulator transformer의 모든 권선, 원10개 capacitor의 step 축, tap 범위/격자와 capacitor0/1 상태를 확인했다. 별도 재검사와 원384개 global archive의 모든 공통 수치·제어 탭은 그대로 일치한다. 원 initial reset은 코드와 행 선언으로 확인하지만, 초기 solve 전 상태 자체는 별도로 저장되지 않았다.','',
        '고정 끝점의 taps-caps 동일 필드는 producer가 True로 선언했다. 코드가 매 probe에서 원 settled state를 복원하고 controlmode off로 푸는 것은 확인했지만, archived fixed 끝점별 상태 checksum이 없어 그 선언을 별도 기록으로 재검산할 수는 없다. 원384 automatic global-only 파일은 그대로 보존했고, 별도 focused384개가 local PCC/hardware 및 final settled-state 증거를 보완한다. 이것도 전체 자동탭/P/Q 영역 인증으로 확대하지 않는다.','',
        '수치·입력 SHA와 모든 한계는 `INDEPENDENT_PORT_REVIEW.json`에 있다. 재현: `python -B -m ieee8500_v42.review_selected_port_ac`. 새 AC/Native 호출은 0회다.','']
    (FOLDER/'INDEPENDENT_PORT_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf8')
    return report


if __name__=='__main__':print(review()['status'])
