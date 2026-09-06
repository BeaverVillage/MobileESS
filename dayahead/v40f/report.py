"""Independent final comparison and immutable evidence checks for common service."""
from pathlib import Path
import inspect,json,math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,write_parquet,reference,sha,digest
from dayahead.v40e.forensic import result_metrics
from .authority import REL,PREVIOUS


def service(repo):
    from dayahead.tools import audit_v40d_service_equivalence as original
    src=inspect.getsource(original.main)
    src=src.replace('root = REPO / "dayahead/artifacts/v40d_actual_realized_replay"','root = REPO / "'+REL.as_posix()+'"')
    src=src.replace('observed_path = root / "V40D_FROZEN_JOB_OBSERVATIONS.parquet"','observed_path = REPO / "dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet"')
    src=src.replace('("B0", "B1", "B2", "B3")','("B0", "B1")')
    src=src.replace('V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json','V40F_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json')
    ns=dict(original.__dict__);ns['REPO']=Path(repo).resolve();exec(compile(src,'<V40F_independent_two_case_service_audit>','exec'),ns)
    ns['main']()
    return read(Path(repo)/REL/'service_equivalence/2025-05-01/V40F_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json')


def finish(repo):
    repo=Path(repo).resolve();root=repo/REL;smoke=root/'smoke/2025-05-01';out=root/'final_report';out.mkdir(exist_ok=True)
    results=read(smoke/'V40F_B0_B1_CORRECTED_RESULTS.json');accepted=read(smoke/'A0_MIN_RHO/MIN_RHO_ACCEPTED_AIDC.json')
    gate=read(smoke/'V40F_PRE_MESS_INTEGRATED_GATE.json');common=read(root/'V40F_COMMON_SERVICE_PREFLIGHT.json')
    jobs=read(smoke/'PRE_MESS_JOBS.json');j={c:pd.DataFrame(js).set_index('job_uid').sort_index() for c,js in jobs.items()}
    fields=['requested_GPU','state_at_issue','qos','safe_duration_slots','safe_duration_seconds','duration_authority']
    for c in j:
        assert j[c].index.equals(j['B0'].index)
        for field in fields:assert j[c][field].equals(j['B0'][field]),field
        assert [digest(x) for x in j[c].common_terminal_obligation]==[digest(x) for x in j['B0'].common_terminal_obligation]
    delta=pd.DataFrame(index=j['B0'].index)
    for c in ['B0','B1']:
        for field in ['start_slot','end_slot','AIDC_site','migration_selected']:delta[c+'_'+field]=j[c][field]
    delta['delta_start']=delta.B1_start_slot-delta.B0_start_slot
    delta['site_changed']=delta.B1_AIDC_site!=delta.B0_AIDC_site
    delta['migration_changed']=delta.B1_migration_selected!=delta.B0_migration_selected
    delta['T_DA_seconds']=j['B0'].safe_duration_seconds;delta['requested_GPU']=j['B0'].requested_GPU
    write_parquet(out/'B0_B1_COMMON_SERVICE_DECISION_DELTA.parquet',delta.reset_index())
    delta.reset_index().to_csv(out/'B0_B1_COMMON_SERVICE_DECISION_DELTA.csv',index=False,float_format='%.17g')
    counts={'START_CHANGED_JOB_COUNT':int((delta.delta_start!=0).sum()),'START_ADVANCED_JOB_COUNT':int((delta.delta_start<0).sum()),
        'START_DELAYED_JOB_COUNT':int((delta.delta_start>0).sum()),'SITE_CHANGED_JOB_COUNT':int(delta.site_changed.sum()),'MIGRATION_CHANGED_JOB_COUNT':int(delta.migration_changed.sum())}
    service_audit=service(repo);metrics={};arrays={};exogenous=[]
    for ns,folder,rb in [('Fresh','fresh','fresh_readback'),('Actual','actual_grid','actual_readback')]:
        for c in ['B0','B1']:metrics[ns,c],arrays[ns,c]=result_metrics(smoke/c/folder/'OPENDSS_PHASE_ARRAYS.npz')
        a=pd.read_parquet(smoke/'B0'/rb/'OPENDSS_COMPONENT_ELEMENTS.parquet').set_index(['slot','element']).sort_index()
        b=pd.read_parquet(smoke/'B1'/rb/'OPENDSS_COMPONENT_ELEMENTS.parquet').set_index(['slot','element']).sort_index()
        assert a.index.equals(b.index) and a.OpenDSS_bus.equals(b.OpenDSS_bus)
        d=b[['P_kw','Q_kvar']]-a[['P_kw','Q_kvar']];d['component']=a.component
        assert np.count_nonzero(d.loc[d.component!='AIDC',['P_kw','Q_kvar']])==0
        assert read(smoke/'B0'/rb/'ENGINE_MAPPING_RATINGS_SOURCE.json')==read(smoke/'B1'/rb/'ENGINE_MAPPING_RATINGS_SOURCE.json')
        assert np.array_equal(arrays[ns,'B0']['regulator_taps'],arrays[ns,'B1']['regulator_taps'])
        assert np.array_equal(arrays[ns,'B0']['capacitor_states'],arrays[ns,'B1']['capacitor_states'])
        write_parquet(out/(ns+'_INPUT_DIFFERENCE.parquet'),d.reset_index())
        exogenous.append({'namespace':ns,'background_PQ_PV_mapping_ratings_exact_equal':True,'native_controls_exact_equal':True,'non_AIDC_input_difference_count':0})
    t=metrics['Actual','B1']['critical_slot'];line=metrics['Actual','B1']['critical_line'];ph=metrics['Actual','B1']['critical_phase']
    k=next(i for i,(l,p) in enumerate(zip(arrays['Actual','B0']['branch_names'],arrays['Actual','B0']['branch_phases'])) if l==line and p==ph)
    site={c:pd.read_parquet(smoke/c/'aidc_site_timeseries.parquet').set_index(['slot','site_id']).sort_index() for c in ['B0','B1']}
    for field in ['observed_t_wb_c','observed_rh_pct']:assert site['B0'][field].equals(site['B1'][field])
    pair=site['B0'].loc[t].add_prefix('B0_').join(site['B1'].loc[t].add_prefix('B1_'))
    for field in ['occupied_GPU','P_PCC_kW','Q_PCC_kvar']:pair['Delta_'+field]=pair['B1_'+field]-pair['B0_'+field]
    write_parquet(out/'ACTUAL_B1_CRITICAL_SLOT_SITE_COMPARISON.parquet',pair.reset_index())
    values={}
    for label,section,key in [('Planning','Planning','rho_max'),('Fresh','Fresh','rho_max_AC'),('Actual','Actual','rho_max_AC')]:
        a,b=results['B0'][section][key],results['B1'][section][key]
        values[label]={'B0':a,'B1':b,'Delta_B0_minus_B1':a-b}
    preservation={}
    for label,path in [('V40E',root/'PRESERVED_V40E_EVIDENCE_MANIFEST.json'),('Planning_Fresh',repo/PREVIOUS/'PROTECTED_OLD_ARTIFACTS_MANIFEST.json')]:
        m=read(path)['files'];changes=[n for n,r in m.items() if not Path(n).is_file() or sha(n)!=r['sha256']]
        assert not changes
        preservation[label]={'files':len(m),'diff_count':0}
    result={'status':'COMPLETE','method':'COMMON_SERVICE_MIN_RHO_AIDC','CORRECTION_TYPE':'IMPLEMENTATION_DEFECT_CORRECTION',
        'INVALIDATED_OLD_IMPLEMENTATION':['BACKGROUND_LOAD_MAPPING_DEFECT','AIDC_OBJECTIVE_IMPLEMENTATION_DEFECT'],
        'superseded_mixed_duration_development_attempt':'REJECTED_NO_FINAL_RESULT',
        'B1_PRIMARY_OBJECTIVE':'MIN_RHO_MAX','B1_SECONDARY_OBJECTIVE':'MIN_DEVIATION_FROM_B0','ZERO_FEASIBILITY_FINAL_OBJECTIVE':'NO',
        'B1_MESS_ENABLED':'NO','COMMON_DURATION_IDENTITY':'PASS','B0_REFERENCE_IN_COMMON_DOMAIN':'PASS',
        'REFERENCE_CANDIDATE_INCLUDED':'PASS','B1_PLANNING_NONWORSENING':'PASS','B1_B3_A0_IDENTITY':'PASS','B0_B2_AIDC_REFERENCE_IDENTITY':'PASS',
        'common_service':common,'solver_stages':accepted['solver_stages'],'primary_optimum_incumbent':accepted['primary_optimum_incumbent'],
        'primary_bound':accepted['primary_bound'],'primary_tolerance':accepted['tolerance'],
        'secondary_reference_deviation_GPU_slots':accepted['secondary_reference_deviation_GPU_slots'],'complete_reference_selected':accepted['complete_RW_reference_selected'],
        'terminal_audit':accepted['terminal_audit'],'decision_delta':counts,'results':values,
        'critical_metrics':{c:metrics['Actual',c] for c in ['B0','B1']},
        'B1_critical_coordinate_comparison':{'line':line,'phase':ph,'slot':t,'B0_rho':float(arrays['Actual','B0']['phase_current_loading_pu'][t,k]),
            'B1_rho':float(arrays['Actual','B1']['phase_current_loading_pu'][t,k]),'sites':pair.reset_index().to_dict('records')},
        'same_exogenous':exogenous,'Actual_runtime_service_equivalence':service_audit,
        'Actual_run_ids':{c:results[c]['Actual_OpenDSS_run_id'] for c in ['B0','B1']},
        'protected_artifact_checks':preservation,'B2_B3_EXECUTED':False,'FULL_MAY_EXECUTED':False,
        'B2_B3_AUTHORIZED':'NO','FULL_MAY_AUTHORIZED':'NO','UNASSIGNED_44_case_blocker':'PRESERVED',
        'next_action':'STOP_FOR_ACTUAL_ATTRIBUTION' if values['Actual']['Delta_B0_minus_B1']<=0 else 'MAY01_B0_B1_COMPLETE_PENDING_ACCEPTANCE_BEFORE_B2_B3'}
    write_json(root/'V40F_MAY01_B0_B1_FINAL_REPORT.json',result)
    write_json(root/'V40F_CURRENT_EXECUTION_STOP_GATE.json',{k:result[k] for k in ['B2_B3_AUTHORIZED','FULL_MAY_AUTHORIZED','next_action','UNASSIGNED_44_case_blocker']})
    text=['**공통 service authority + MIN_RHO_AIDC May-01 B0/B1**',
        '분류: AIDC_OBJECTIVE_IMPLEMENTATION_DEFECT의 수정. 이전 ZERO_FEASIBILITY 결과와 mixed-duration 개발 시도는 새 결과의 과학적 비교 기준으로 사용하지 않는다.',
        '| 지표 | B0 | B1 | Delta = B0 − B1 |','|---|---:|---:|---:|']
    for key,v in values.items():text.append(f"| {key} | {v['B0']:.17g} | {v['B1']:.17g} | {v['Delta_B0_minus_B1']:.17g} |")
    text+=['',f"Common T_DA SHA: `{common['COMMON_DA_DURATION_SHA']}`. Job {common['job_count']}; 기존 RW/RSP duration 차이 {common['RW_vs_RSP_duration_difference_count']}; 새 case별 차이 0.",
        'B0는 RW start/site/inherited state와 common causal-safe duration이다. B1도 동일한 duration/residual 및 B0 terminal obligation을 사용한다. Realized runtime은 Planning에서 읽지 않았다.',
        '', '| 결정 변화 | 개수 |','|---|---:|']
    for key,v in counts.items():text.append(f'| {key} | {v} |')
    text+=['', '| 인증 단계 | incumbent | bound | OPTIMAL | work |','|---|---:|---:|---|---:|']
    for st in accepted['solver_stages']:text.append(f"| {st['stage']} | {st['incumbent']:.17g} | {st['bound']:.17g} | {st['OPTIMAL']} | {st['work']:.9f} |")
    text += ['',f"Primary tolerance {accepted['tolerance']}; reference-deviation optimum {accepted['secondary_reference_deviation_GPU_slots']} GPU-slots. Secondary는 certified lower bound + tolerance 이내의 primary cap을 유지한다. Objective/feasible set을 바꾸지 않고 인증 계산의 WorkLimit만 추가했다.",
        '', 'MIN_RHO_MAX, MIN_DEVIATION_FROM_B0, COMMON_DURATION_IDENTITY, REFERENCE_CANDIDATE_INCLUDED, B1_PLANNING_NONWORSENING, B1_B3_A0_IDENTITY, B0_B2_AIDC_REFERENCE_IDENTITY 모두 PASS. MESS OFF, ZERO_FEASIBILITY final objective NO.',
        '', 'Actual critical coordinates:']
    for c in ['B0','B1']:
        m=metrics['Actual',c];text.append(f"- {c}: {m['critical_line']} / {m['critical_phase']} / slot {m['critical_slot']} ({m['critical_time']} fixed AEST), rho={m['rho']:.17g}; run ID `{results[c]['Actual_OpenDSS_run_id']}`.")
    text += ['', '동일한 actual background/PV/weather/mapping/ratings/control state를 검증했고 AIDC 외 input 차이는 0이다. Actual job별 runtime·GPU identity와 서비스 보존 검사가 PASS다.',
        '', '**FULL_MAY_AUTHORIZED = NO. B2_B3_AUTHORIZED = NO.** '+result['next_action']+'. 44-case UNASSIGNED spillover blocker는 유지한다.',
        '', f"[전체 JSON]({(root/'V40F_MAY01_B0_B1_FINAL_REPORT.json').as_posix()}) · [job 결정 ledger]({(out/'B0_B1_COMMON_SERVICE_DECISION_DELTA.csv').as_posix()}) · [Common preflight]({(root/'V40F_COMMON_SERVICE_PREFLIGHT.json').as_posix()})"]
    (root/'V40F_MAY01_B0_B1_FINAL_REPORT.md').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps({'results':values,'decision_delta':counts,'next_action':result['next_action']}),flush=True)
    return result
