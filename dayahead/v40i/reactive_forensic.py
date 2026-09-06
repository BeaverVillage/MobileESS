"""Read existing P/Q lineage and gradients; never generate AC coefficients or controls."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import write_json, sha
from dayahead.v40h.identity import file_record
from .pending_forensic import Evidence, ROOT as PENDING
from .may01_forensic import G, SMOKE
from .h100_forensic import ROOT

PF=0.95
TAN=0.3286841051788632


def pq_authority(kind, fixed_pf_parent):
    """A downstream solver/readback cannot upgrade a derived load boundary to measured Q."""
    if fixed_pf_parent:return 'DERIVED_FIXED_PF_BOUNDARY_NOT_INDEPENDENT_Q_AUTHORITY'
    return 'REQUIRES_SOURCE_REVIEW' if kind!='measured' else 'MEASURED_CANDIDATE_REQUIRES_SITE_TIME_IDENTITY'


def gradients(e,out):
    base=e.repo/G/'electrical/2025-05-01'
    vp=e.path(base/'data/D1_AC_ANCHOR_SENSITIVITY_2025-05-01.npz')
    cp=e.path(base/'data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_2025-05-01.npz')
    lineage=e.js(base/'V40E_ELECTRICAL_REBUILD_LINEAGE.json')
    assert sha(vp)==lineage['outputs']['voltage']['new']['sha256']
    assert sha(cp)==lineage['outputs']['current']['new']['sha256']
    with np.load(vp,allow_pickle=False) as z:
        v={k:z[k] for k in z.files}
    with np.load(cp,allow_pickle=False) as z:
        c={k:z[k] for k in z.files}
    names=c['control_names'].tolist();assert names==v['control_names'].tolist()
    b=c['branch_names'].tolist().index('line.sw2::A');rating=float(c['rating_a'][b]);t=73
    inventory=e.js(SMOKE/'B1/actual_readback/ENGINE_MAPPING_RATINGS_SOURCE.json')
    elements={r['name'].lower():r for r in inventory['elements']}
    prior=pd.read_csv(e.path(e.repo/PENDING/'V40I_FROZEN_SW2_PHASE_A_SENSITIVITY.csv'))
    rows=[];voltages=[];same_hv=True
    for i in range(12):
        aidc=f'AIDC{i+1:02d}';service=f'IDC{i+1:02d}'
        ia=names.index(f'aidc_load_kw[{aidc}]');ip=names.index(f'mess_p_kw[{service}]');iq=names.index(f'mess_q_kvar[{service}]')
        ga=float(c['current_sensitivity_pu_per_control'][t,ia,b])
        # MESS positive controls inject; negative gives extra load at its own, different PCC.
        gp=-float(c['current_sensitivity_pu_per_control'][t,ip,b]);gq=-float(c['current_sensitivity_pu_per_control'][t,iq,b])
        at=elements[f'transformer.idc_{service.lower()}_tx'];mt=elements[f'transformer.mess_{service.lower()}_tx']
        assert at['buses'][0].split('.')[0]==mt['buses'][0].split('.')[0]
        assert at['buses'][1]!=mt['buses'][1]
        row={'AIDC':aidc,'rating_A':rating,'AIDC_fixed_PF_direction_drho_per_kW':ga,
            'AIDC_fixed_PF_direction_dI_A_per_kW':ga*rating,
            'AIDC_pure_dI_dP_at_fixed_Q':None,'AIDC_pure_dI_dQ_at_fixed_P':None,
            'AIDC_pure_partial_status':'NOT_IDENTIFIABLE_FROM_SINGLE_COUPLED_AIDC_CONTROL',
            'nearby_MESS_extra_load_proxy_drho_dP':gp,'nearby_MESS_extra_load_proxy_drho_dQ':gq,
            'nearby_MESS_extra_load_proxy_dI_dP':gp*rating,'nearby_MESS_extra_load_proxy_dI_dQ':gq*rating,
            'proxy_1_kvar_extra_load_delta_I_A':gq*rating,
            'proxy_Q_over_P_sensitivity_ratio':gq/gp if gp else None,
            'proxy_P_plus_tanQ_direction_dI_A_per_kW':(gp+TAN*gq)*rating,
            'proxy_vs_actual_coupled_direction_residual_A_per_kW':(ga-gp-TAN*gq)*rating,
            'AIDC_transformer_buses':at['buses'],'MESS_transformer_buses':mt['buses'],
            'same_upstream_HV_bus':True,'same_PCC_or_transformer':False,
            'proxy_scope':'Frozen MESS perturbation gradient at separate 750-kVA transformer; AIDC has 1500-kVA transformer. Not exact AIDC independent Q sensitivity or AIDC equipment capability.'}
        dp=float(prior[prior.site==aidc].delta_PCC_kW.iloc[0]);row['Actual_B1_minus_B0_PCC_kW']=dp
        row['Actual_B1_minus_B0_derived_Q_kvar']=TAN*dp
        row['coupled_first_order_delta_I_A']=ga*rating*dp
        row['nearby_MESS_proxy_P_redistribution_delta_I_A']=gp*rating*dp
        row['nearby_MESS_proxy_PF_linked_Q_delta_I_A']=gq*rating*TAN*dp
        rows.append(row)
        va=v['sensitivity'][t,ia]/(2*np.sqrt(v['anchor_v_squared'][t]))
        qp=-v['sensitivity'][t,iq]/(2*np.sqrt(v['anchor_v_squared'][t]))
        pp=-v['sensitivity'][t,ip]/(2*np.sqrt(v['anchor_v_squared'][t]))
        for j,node in enumerate(v['node_names']):
            voltages.append({'AIDC':aidc,'node':str(node),'AIDC_fixed_PF_dVpu_per_kW':float(va[j]),
                'nearby_MESS_extra_load_proxy_dVpu_dP':float(pp[j]),'nearby_MESS_extra_load_proxy_dVpu_dQ':float(qp[j]),
                'AIDC_pure_dV_dP':None,'AIDC_pure_dV_dQ':None})
    final=e.js(G/'V40G_MAY01_FINAL_REPORT.json');crit=final['critical_metrics']
    observed=crit['Actual_B1']['critical_current_A']-crit['Actual_B0']['critical_current_A']
    predicted=sum(r['coupled_first_order_delta_I_A'] for r in rows)
    assert abs(predicted-0.14891585340271657)<1e-10 and abs(observed-0.14624172648016742)<1e-10
    result={'status':'FROZEN_GRADIENTS_READ_ONLY','coefficient_source':{'voltage':file_record(vp),'current':file_record(cp)},
        'coefficient_scope':'Existing approved V40G May01 inherited coefficient identity; not a new V40I certified generation',
        'critical_coordinate':{'line':'line.sw2','phase':'A','slot':73},'rows':rows,
        'AIDC_direction_identity':'g_AIDC = partial rho/partial P + tan(acos(.95))*partial rho/partial Q',
        'pure_AIDC_P_partial_identified':False,'pure_AIDC_Q_partial_identified':False,
        'why_MESS_Q_is_not_AIDC_Q':'Separate LV PCC/transformer and operating point; common upstream bus is insufficient for exact Jacobian substitution.',
        'predicted_coupled_delta_current_A':predicted,'observed_delta_current_A':observed,
        'absolute_mismatch_A':abs(predicted-observed),'signed_observed_minus_predicted_A':observed-predicted,
        'relative_mismatch_to_observed':abs(predicted-observed)/abs(observed),
        'relative_mismatch_to_predicted':abs(predicted-observed)/abs(predicted),
        'P_only_explanation_proven':False,
        'nearby_MESS_proxy_P_redistribution_delta_I_A':sum(r['nearby_MESS_proxy_P_redistribution_delta_I_A'] for r in rows),
        'nearby_MESS_proxy_PF_linked_Q_delta_I_A':sum(r['nearby_MESS_proxy_PF_linked_Q_delta_I_A'] for r in rows),
        'interpretation':'Frozen P placement with its prescribed PF-linked Q explains the stored delta to local-linear residual. This is not evidence that Q sensitivity is zero or a changed PF would be immaterial.',
        'small_reactive_perturbation':'Only multiplication of existing MESS Q gradients by 1 kvar at their own PCC; no network solve, control or AIDC authorization.',
        'new_coefficient_generation':False,'OpenDSS_calls':0}
    write_json(out/'V40I_AIDC_PQ_SENSITIVITY_FORENSIC.json',result)
    pd.DataFrame(rows).to_csv(out/'V40I_AIDC_PQ_SENSITIVITY_FORENSIC.csv',index=False)
    pd.DataFrame(voltages).to_csv(out/'V40I_AIDC_PQ_VOLTAGE_GRADIENTS.csv',index=False)
    return result


def run(repo):
    repo=Path(repo).resolve();out=repo/ROOT;out.mkdir(parents=True,exist_ok=True);e=Evidence(repo)
    sources=['dayahead/v40g/physical.py','dayahead/v40g/smoke.py','dayahead/v40g/actual.py',
        'dayahead/v40g/optimizer.py','dayahead/v40a/grid.py','dayahead/v40f/common_service.py',
        'dayahead/v40d_actual/power_replay.py','dayahead/v40d_actual/grid_replay.py','dayahead/v40e/smoke.py',
        'dayahead/v40e/readback.py','dayahead/v40e/mapping.py','dayahead/v28r2/opendss_backend.py',
        'dayahead/v28r2/opendss_mapping.py','dayahead/v36/contracts.py','dayahead/v28r2/formulation.py',
        'dayahead/v39a/power.py','dayahead/run_v16_3_voltage_candidate.py','dayahead/run_v16_3_correction.py',
        'dayahead/v40e/electrical.py','dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss',
        'dayahead/thermal/nlr_power.py']
    refs={p:file_record(e.path(p)) for p in sources}
    physical=e.js(G/'PHYSICAL_RUNNER_LINEAGE.json')
    assert physical['electrical_physics_changed'] is False
    stages=[];qrows=[]
    for case in ['B0','B1']:
        with np.load(e.path(SMOKE/(case+'_PRE_MESS_AIDC.npz')),allow_pickle=False) as z:
            p=z['pcc'];q=z['qcc']
        assert np.max(np.abs(q-p*TAN))<1e-10
        stages.append({'case':case,'stage':'Planning','P_origin':'Frozen job occupancy -> CENTER IT -> C1 PCC P',
            'Q_origin':'Fixed PF-derived','formula':'Q=P*tan(acos(0.95))','PF':PF,
            'P_control':'Frozen B0 reference or frozen B1 site/time decision','Q_control':'NO independent Q variable',
            'artifact':file_record(e.path(SMOKE/(case+'_PRE_MESS_AIDC.npz'))),
            'producer':'v40f.common_service for B0; v40g.smoke.prepare for B1',
            'max_Q_formula_error_kvar':float(np.max(np.abs(q-p*TAN)))})
        frame=e.frame(SMOKE/case/'aidc_site_timeseries.parquet')
        assert np.max(np.abs(frame.Q_PCC_kvar-frame.P_PCC_kW*TAN))<1e-10
        stages.append({'case':case,'stage':'Actual','P_origin':'Segment-aware frozen replay occupancy + actual weather -> CENTER/C1',
            'Q_origin':'Fixed PF-derived','formula':'Q=P*tan(acos(0.95))','PF':PF,
            'P_control':'Frozen policy realization; no Actual optimization','Q_control':'NO independent Q variable',
            'artifact':file_record(e.path(SMOKE/case/'aidc_site_timeseries.parquet')),
            'producer':'v40g.actual.power_from_execution -> v40d_actual.power_replay.power_from_execution',
            'max_Q_formula_error_kvar':float(np.max(np.abs(frame.Q_PCC_kvar-frame.P_PCC_kW*TAN)))})
        for namespace,directory in [('Fresh','fresh_readback'),('Actual','actual_readback')]:
            path=SMOKE/case/directory/'OPENDSS_COMPONENT_ELEMENTS.parquet';f=e.frame(path);f=f[f.component.eq('AIDC')]
            assert len(f)==1152 and np.max(np.abs(f.Q_kvar-f.P_kw*TAN))<1e-10
            stages.append({'case':case,'stage':namespace+'_OpenDSS_mapping','PCC_P':'Loads.kW() configured setpoint readback',
                'PCC_Q':'Loads.kvar() configured setpoint readback','PF':PF,'formula':'Q=P*tan(acos(0.95))',
                'control_status':'No AIDC independent Q control','artifact':file_record(e.path(path)),
                'origin':'v40e.readback.observe.applied: readback before SolveSnap; not CktElement.Powers measurement',
                'fixed_PF_binding_error_kvar':float(np.max(np.abs(f.Q_kvar-f.P_kw*TAN)))})
            for site,g in f.groupby('AIDC_site_id'):
                qrows.append({'case':case,'namespace':namespace,'AIDC':site,'N':len(g),
                    'Q_min_kvar':float(g.Q_kvar.min()),'Q_max_kvar':float(g.Q_kvar.max()),
                    'Q_time_variance_kvar2':float(g.Q_kvar.var(ddof=0)),
                    'Q_is_time_varying':bool(g.Q_kvar.max()!=g.Q_kvar.min()),
                    'Q_over_P_ratio_prescribed':TAN,'PF_prescribed':PF,
                    'authority':pq_authority('setpoint_readback',True),'measured_PF_variability':None,
                    'modeled_Q_sign':'LAGGING_POSITIVE_LOAD_Q','physical_leading_lagging_fraction':None})
    lineage={'status':'CURRENT_PRODUCTION_PATH_TRACED','PF_model':'FIXED_PF_0.95','fixed_Q':False,
        'Q_time_varying_with_P':True,'independent_AIDC_Q_control':False,'source_files':refs,'stages':stages,
        'actual_runner_lineage':file_record(e.path(G/'PHYSICAL_RUNNER_LINEAGE.json')),
        'planning_sensitivity_semantics':'AIDC control changes both P and PF-linked Q; no AIDC pure Q column.',
        'frozen_values_changed':False}
    write_json(out/'V40I_AIDC_REACTIVE_MODEL_LINEAGE.json',lineage)
    write_json(out/'V40I_AIDC_PCC_Q_AUTHORITY_AUDIT.json',{'status':'DERIVED_NOT_MEASURED','rows':qrows,
        'three_authority_kinds':{'independent_measured_Q':'No verified AIDC measurement source found',
            'OpenDSS_independently_realized_Q':'Branch/transformer terminal flows are simulated network responses, conditional on fixed-PF AIDC boundary; not independent facility Q authority.',
            'P_derived_Q':'Planning/Actual PCC columns and Fresh/Actual load setpoint readbacks use fixed PF 0.95'},
        'circular_validation_avoided':True})
    raw=e.js(ROOT/'V40I_Q_RAW_SEARCH_INVENTORY.json');candidate=e.js(ROOT/'V40I_Q_REPOSITORY_SCHEMA_CANDIDATES.json')
    schema=e.js('dayahead/artifacts/v24t_thermal_aware_aidc/V24T_NLR_POWER_SCHEMA.json')
    raw_power=e.path(schema['path']);assert sha(raw_power)==schema['sha256']
    import pyarrow.parquet as pq
    full_schema=pq.read_schema(raw_power).names
    facility={'path':file_record(raw_power),'schema':full_schema,'time_resolution_seconds':schema['inferred_cadence_seconds'],
        'date_coverage':[schema['timestamp_start'],schema['timestamp_end']],
        'site_coverage':'NLR ESIF; not measurements of the twelve synthetic AIDC sites',
        'measured_vs_derived':'Facility active-power components/PUE; no reactive/PF columns',
        'Q_authority_quality':'NONE_FOR_AIDC_Q'}
    registry_paths=['dayahead/artifacts/melbourne_aidc_april2025_scale/MELBOURNE_AIDC_APRIL2025_SCALE_SOURCE_REGISTRY.json',
        'dayahead/artifacts/v22s_melbourne_12site_scale/V22S_12SITE_SOURCE_REGISTRY.json',
        'dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_SOURCE_REVERIFICATION.json']
    registries=[file_record(e.path(p)) for p in registry_paths]
    pf={'status':'NO_INDEPENDENT_TIME_VARYING_Q_AUTHORITY','independent_AIDC_Q_authority':'NO_VERIFIED_SOURCE_IN_SEARCHED_SCOPE',
        'mean_PF':None,'min_PF':None,'max_PF':None,'P5_P50_P95':None,'time_variance':None,'site_variance':None,
        'leading_fraction':None,'lagging_fraction':None,'load_dependent_PF_buckets':None,
        'not_calculated_reason':'Derived Q cannot validate fixed PF; no independent facility Q/PF time series with mapped site/date authority.',
        'facility_source':facility,'raw_scan_files':raw['file_count'],'raw_schemas_read':len(raw['parquet_schemas']),
        'raw_schema_errors':raw['errors'],'repository_candidate_count':candidate['candidate_count'],
        'search_limits':'Raw filename/schema audit and available repo source/authority/production-path review; 45 encrypted RADDiT embedding files were unreadable as parquet. A universal absence claim over every inaccessible archive is not made.',
        'equipment_marketing_sources':registries,'modeled_positive_Q':'Lagging load sign is prescribed, not measured.'}
    write_json(out/'V40I_AIDC_TIME_VARYING_PF_FORENSIC.json',pf)
    capability={'status':'PHYSICAL_Q_CONTROL_AUTHORITY_NOT_ESTABLISHED','AIDC_REACTIVE_POWER_CONTROL_AUTHORIZED':'NO',
        'equipment_evidence':[{'kind':'UPS/DRUPS','evidence':'Saved facility source registry mentions UPS/DRUPS and 2N UPS; existence alone does not specify bidirectional VAR control.',
            'source_records':registries,'rated_kVA_for_controllable_device':None,'Q_range':None,'P_Q_capability':None,'response_time':None,
            'control_interval':None,'leading_lagging_capability':None},
            {'kind':'STATCOM/SVG/capacitor/inverter VAR','evidence':'No site-specific AIDC capability contract established.',
             'rated_kVA':None,'Q_range':None,'P_Q_capability':None,'response_time':None,'control_interval':None}],
        'excluded_authorities':['IEEE123 native capacitor banks are feeder devices, not AIDC controllable equipment.',
            'MESS generator/storage Q controls and ratings belong to MESS, not the AIDC facility.',
            'Generated AIDC transformer 1500 kVA is a network rating, not a facility Q actuator capability curve.'],
        'free_Q_variable_permitted':False,'equipment_added':False}
    write_json(out/'V40I_AIDC_REACTIVE_CONTROL_CAPABILITY_AUDIT.json',capability)
    sensitivity=gradients(e,out)
    penetration=e.js(PENDING/'V40I_AIDC_CONTROLLABLE_PENETRATION.json')
    write_json(out/'V40I_CONTROLLABLE_PENETRATION_FINAL.json',{'source':file_record(e.path(PENDING/'V40I_AIDC_CONTROLLABLE_PENETRATION.json')),
        'frozen_attribution':penetration,'interpretation':'Small controllable feeder share limits available load to redistribute; it does not prove optimizer weakness or quantify a universal bound on grid benefit. The fixed-domain primary optimum remains certified in historical Planning.',
        'new_optimization':False})
    final={'status':'FORENSIC_CLOSED_WITH_AUTHORITY_GAPS','AIDC_PF_model':'FIXED_PF_0.95','fixed_Q':False,
        'Q_time_varying':True,'Q_authority':'P_DERIVED_FIXED_PF; OPEN_DSS_LOAD_READBACK_IS_SETPOINT',
        'independent_measured_Q':False,'independent_time_varying_AIDC_Q_authority':'NO_VERIFIED_SOURCE',
        'actual_physical_PF_variability':'UNKNOWN','physical_leading_lagging_evidence':'UNAVAILABLE',
        'AIDC_REACTIVE_POWER_CONTROL_AUTHORIZED':'NO','PF_changed':False,'Q_control_added':False,
        'FIXED_PF_IMPACT_CLASSIFICATION':'FIXED_PF_AUTHORITY_INSUFFICIENT','FIXED_PF_MODEL_FIDELITY_QUESTION':'OPEN',
        'AIDC_REACTIVE_MODEL_PRIMARY_CAUSE_OF_MAY01_REVERSAL':'NO_ADDITIONAL_IDENTIFIED_CAUSE; PURE_P_ONLY_OR_CHANGED_PF_COUNTERFACTUAL_NOT_ESTABLISHED',
        'occupancy_reversal_primary_cause':'Runtime/placement reproduced independently of Q; Q representation maps that load to electrical metrics.',
        'current_delta_explanation':'P placement plus its mandated fixed-PF Q change explains saved current delta; cannot call it pure-P evidence.',
        'sensitivity_summary':{k:sensitivity[k] for k in ['predicted_coupled_delta_current_A','observed_delta_current_A','absolute_mismatch_A','relative_mismatch_to_observed']},
        'fidelity_not_proven_by_reconstruction':True,'new_AC_runs':0,'new_optimization':False}
    write_json(out/'V40I_AIDC_REACTIVE_AUTHORITY_FINAL.json',final)
    lines=['# AIDC reactive-power forensic 최종','',
        'B0/B1의 현재 Planning·Fresh·Actual 경로는 PF=0.95 고정이다. Q=P×0.3286841051788632이므로 Q는 P와 함께 시간에 따라 변한다. Fixed Q가 아니다.','',
        'PCC_Q와 Q_PCC 및 OPENDSS_COMPONENT_ELEMENTS의 Q는 고정 PF에서 파생되거나 설정값을 읽은 것이다. readback은 Loads.kvar()를 SolveSnap 전에 읽는다. 독립 측정 Q가 아니며, 별도의 branch/transformer AC Q flow도 해당 load boundary를 조건으로 계산된 계통 반응이다.','',
        f"Raw 목록 {raw['file_count']:,}개와 parquet schema {len(raw['parquet_schemas']):,}개, 기존 repository schema 후보 {candidate['candidate_count']:,}개를 선별하고 실제 producer/authority 경로를 추적했다. NLR 원본은 active-power/PUE만 제공한다. 독립 AIDC time-varying Q/PF authority는 확인되지 않았다. 미해독 RADDiT embedding parquet 45개 등 검색 한계를 JSON에 보존했다.",'',
        'UPS/DRUPS 존재 언급은 있으나 AIDC별 Q range, P-Q capability curve, 응답·제어 주기는 없다. Native feeder capacitor와 MESS Q capability는 AIDC authority로 옮기지 않았다. Q optimization authorization=NO. 실제 PF 분산·leading/lagging 비율은 계산 불가이며 0.95 재산출을 validation으로 사용하지 않았다.','',
        f"Frozen 방향 민감도에 따른 ΔI={sensitivity['predicted_coupled_delta_current_A']:.12f} A, 저장 Actual={sensitivity['observed_delta_current_A']:.12f} A. 절대 차이={sensitivity['absolute_mismatch_A']:.12f} A, Actual 대비 상대 차이={sensitivity['relative_mismatch_to_observed']:.6%}.",'',
        '이 방향 미분은 ∂I/∂P + tan(acos(.95))∂I/∂Q다. AIDC의 독립 P/Q partial은 현재 frozen cache에서 분리되지 않는다. 같은 상류 bus의 MESS P/Q gradients는 별도 750-kVA transformer/PCC를 거치므로 진단 proxy만 제공했다. 이를 1500-kVA AIDC PCC의 정확한 Q 미분으로 바꾸지 않았다.','',
        'Runtime/site가 +2 GPU occupancy 역전을 설명하며, 고정 PF로 연결된 P/Q가 전류 차이를 설명한다. 별도 reactive 원인이 확인된 것은 아니다. 하지만 순수 P만으로 설명됐다고 하거나 PF 변경의 영향이 작다고 확정할 근거는 없다. FIXED_PF_MODEL_FIDELITY_QUESTION=OPEN; FIXED_PF_AUTHORITY_INSUFFICIENT.','',
        'Level 0은 현 고정 PF 가정을 명시하고 유지하는 재현 baseline이다. Level 1 exogenous PF는 독립 P/Q 시계열과 pre-May 검증이 필요하다. Level 2 controllable Q는 장비 capability/control authority가 선행해야 한다. 어떤 level도 이번 작업에서 변경·적용하지 않았다.','']
    (out/'V40I_AIDC_REACTIVE_MODEL_FINAL_AUDIT.md').write_text('\n'.join(lines),encoding='utf-8')
    e.verify(out)
    (out/'V40I_REACTIVE_INPUT_HASHES.json').write_bytes((out/'V40I_ADDITIONAL_FORENSIC_INPUT_HASHES.json').read_bytes())
    print('Reactive forensic complete; fixed PF, no independent AIDC Q authority; coupled delta',sensitivity['predicted_coupled_delta_current_A'],flush=True)


if __name__=='__main__':run(Path.cwd())
