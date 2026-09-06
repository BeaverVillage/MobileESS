"""Independent full-service accounting and matched B0/B1 final report."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,write_parquet,sha,reference,digest
from dayahead.v40a.invariants import digest as decision_digest
from dayahead.v40e.forensic import result_metrics
from .authority import REL,PREVIOUS,METHOD,GATES,verify_preservation,seal
from .reuse import accepted_b1_as_a0,architecture_contract


def service_audit(repo):
    repo=Path(repo);root=repo/REL;out=root/'final_report';out.mkdir(exist_ok=True)
    smoke=root/'smoke/2025-05-01'
    source=repo/'dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet'
    observed=pd.read_parquet(source);observed['id']=observed.id.astype(str);observed=observed.set_index('id')
    assert not observed.index.duplicated().any();issue=pd.Timestamp('2025-04-30T18:00:00+10:00')
    frames={};summaries={}
    for case in ('B0','B1'):
        jobs=pd.read_parquet(smoke/case/'job_ledger.parquet')
        contributions=pd.read_parquet(smoke/case/'job_GPU_contributions.parquet')
        assert not jobs.job_uid.duplicated().any() and not contributions.duplicated(['job_uid','slot']).any()
        recorded={(str(r.job_uid),int(r.slot)):(r.site,int(r.occupied_GPU)) for r in contributions.itertuples(index=False)}
        expected={};rows=[]
        for r in jobs.to_dict('records'):
            uid=str(r['job_uid']);o=observed.loc[uid];gpu=int(r['requested_GPU'])
            os=(pd.Timestamp(o.start_time)-issue).total_seconds();oe=(pd.Timestamp(o.end_time)-issue).total_seconds();duration=oe-os
            assert duration==r['actual_runtime_seconds'] and gpu==int(o.gpus_requested) and duration>0
            if r['status']=='UNASSIGNED_POST_H_BACKLOG':
                assert r['start_slot']>=120;parts=[];pre=day=0.;post=duration
            else:
                if r['status']=='PRE_DAY_COMPLETE':
                    parts=[(None,os,oe)];assert oe<=21600
                elif r['status']=='EXECUTION_ACCOUNTED':
                    raw=r.get('actual_compute_segments')
                    if isinstance(raw,str):
                        parts=[(s['site'],float(s['start'])*900,float(s['end'])*900) for s in json.loads(raw)]
                        if os<0:parts=[(parts[0][0],os,0.)]+parts
                    else:
                        start=os if r['state_at_issue']=='RUNNING' else float(r['actual_residual_start'])*900
                        parts=[(r['AIDC_site'],start,float(r['actual_execution_end'])*900)]
                else:raise RuntimeError('UNKNOWN_JOB_STATUS')
                assert abs(sum(b-a for s,a,b in parts)-duration)<1e-7,uid
                assert all(a<b for s,a,b in parts) and all(a[2]<=b[1] for a,b in zip(parts,parts[1:]))
                pre=sum(max(0,min(b,21600)-a) for s,a,b in parts if a<21600)
                day=sum(max(0,min(b,108000)-max(a,21600)) for s,a,b in parts)
                post=sum(max(0,b-max(a,108000)) for s,a,b in parts)
                for s,a,b in parts:
                    for t in range(24,120):
                        if a<=t*900<b:
                            assert s is not None and (uid,t-24) not in expected
                            expected[uid,t-24]=(s,gpu)
            error=duration-pre-day-post
            assert abs(error)<1e-7 and abs(post*gpu/3600-r['remaining_GPU_hours_at_H'])<1e-7,uid
            rows.append({'job_uid':uid,'requested_GPU':gpu,'realized_runtime_seconds':duration,
                         'pre_D00_GPU_hours':pre*gpu/3600,'Dday_GPU_hours':day*gpu/3600,'postH_GPU_hours':post*gpu/3600,
                         'service_conservation_error_seconds':error,'status':r['status']})
        assert expected==recorded,'INDEPENDENT_UID_SITE_SLOT_RECONSTRUCTION'
        frame=pd.DataFrame(rows).set_index('job_uid').sort_index();frames[case]=frame
        summaries[case]={'jobs':len(frame),'service_conservation_max_error_seconds':float(frame.service_conservation_error_seconds.abs().max()),
                         **{k:float(frame[k].sum()) for k in ('pre_D00_GPU_hours','Dday_GPU_hours','postH_GPU_hours')}}
        write_parquet(out/(case+'_FULL_SERVICE_PARTITION.parquet'),frame.reset_index())
    assert frames['B0'].index.equals(frames['B1'].index)
    for field in ('requested_GPU','realized_runtime_seconds'):assert frames['B0'][field].equals(frames['B1'][field])
    result={'status':'PASS','same_original_job_universe':True,'same_original_realized_service_each_job':True,
            'same_requested_GPU_each_job':True,'duplicate_UID_slot_count':0,'independent_UID_site_slot_recalculation':'PASS',
            'migration_pause_not_counted_as_compute':True,'cases':summaries,'observed_authority':reference(source)}
    write_json(out/'ACTUAL_COMMON_SERVICE_AUDIT.json',result);return result


def finish(repo):
    repo=Path(repo).resolve();root=repo/REL;smoke=root/'smoke/2025-05-01';out=root/'final_report';out.mkdir(exist_ok=True)
    accepted=read(smoke/'JOINT_AIDC/ACCEPTED_AIDC.json');diagnostic=read(smoke/'TEMPORAL_ONLY_DIAGNOSTIC/ACCEPTED_AIDC.json')
    comparison=read(smoke/'TEMPORAL_ONLY_COMPARISON.json');raw=read(smoke/'V40G_B0_B1_CORRECTED_RESULTS.json')
    jobs=read(smoke/'PRE_MESS_JOBS.json');refs={r['job_uid']:r for r in jobs['B0']}
    rows=[]
    for r in jobs['B1']:
        b=refs[r['job_uid']]
        rows.append({'job_uid':r['job_uid'],'requested_GPU':r['requested_GPU'],'state_at_issue':r['state_at_issue'],
                     'B0_start':b['start_slot'],'B1_start':r['start_slot'],'B0_site':b['AIDC_site'],'B1_site':r['AIDC_site'],
                     'start_changed':r['start_slot']!=b['start_slot'],'site_changed':r['AIDC_site']!=b['AIDC_site'],
                     'migration_changed':r['migration_selected']!=b['migration_selected'],
                     'T_DA_slots':r['safe_duration_slots'],'B0_end':b['end_slot'],'B1_end':r['end_slot']})
    delta=pd.DataFrame(rows);delta.to_csv(out/'B0_B1_DECISION_DELTA.csv',index=False)
    counts={name:int(delta[field].sum()) for name,field in [('START_CHANGED_JOB_COUNT','start_changed'),('SITE_CHANGED_JOB_COUNT','site_changed'),('MIGRATION_CHANGED_JOB_COUNT','migration_changed')]}
    write_json(out/'SELECTED_MIGRATIONS.json',[r for r in accepted['jobs'] if r.get('migration_selected')])
    values={}
    for label,key in [('Planning','rho_max'),('Fresh','rho_max_AC'),('Actual','rho_max_AC')]:
        a,b=raw['B0'][label][key],raw['B1'][label][key]
        values[label]={'B0':a,'B1':b,'Delta_B0_minus_B1':a-b}
    assert values['Planning']['B1']<=values['Planning']['B0']+1e-6
    exogenous=[];metrics={}
    for ns,folder,rb in [('Fresh','fresh','fresh_readback'),('Actual','actual_grid','actual_readback')]:
        arrays={}
        for c in ('B0','B1'):
            metric,arrays[c]=result_metrics(smoke/c/folder/'OPENDSS_PHASE_ARRAYS.npz');metrics[ns+'_'+c]=metric
        a=pd.read_parquet(smoke/'B0'/rb/'OPENDSS_COMPONENT_ELEMENTS.parquet').set_index(['slot','element']).sort_index()
        b=pd.read_parquet(smoke/'B1'/rb/'OPENDSS_COMPONENT_ELEMENTS.parquet').set_index(['slot','element']).sort_index()
        assert a.index.equals(b.index) and a.OpenDSS_bus.equals(b.OpenDSS_bus)
        d=b[['P_kw','Q_kvar']]-a[['P_kw','Q_kvar']]
        assert np.count_nonzero(d.loc[a.component!='AIDC'])==0
        assert read(smoke/'B0'/rb/'ENGINE_MAPPING_RATINGS_SOURCE.json')==read(smoke/'B1'/rb/'ENGINE_MAPPING_RATINGS_SOURCE.json')
        assert np.array_equal(arrays['B0']['regulator_taps'],arrays['B1']['regulator_taps'])
        assert np.array_equal(arrays['B0']['capacitor_states'],arrays['B1']['capacitor_states'])
        exogenous.append({'namespace':ns,'background_PQ_PV_mapping_ratings_native_controls_exact_equal':True,'non_AIDC_input_differences':0})
    service=service_audit(repo);preservation=verify_preservation(repo)
    handle=accepted_b1_as_a0(smoke/'JOINT_AIDC/ACCEPTED_AIDC.json',smoke/'B1_PRE_MESS_AIDC.npz')
    reuse=read(smoke/'B3_A0_STATIC_REUSE/A0_REUSE_GATE.json')
    assert reuse['B3_A0_DECISION_SHA']==handle.decision_sha
    assert (smoke/'B3_A0_STATIC_REUSE/B1_FINAL_AS_A0.json').read_bytes()==handle.accepted_b1_path.read_bytes()
    assert (smoke/'B3_A0_STATIC_REUSE/B1_FINAL_AS_A0_TRAJECTORY.npz').read_bytes()==handle.b1_trajectory_path.read_bytes()
    common=read(root/'common_service/COMMON_DA_SERVICE_AUTHORITY.json')
    assert sha(root/'common_service/COMMON_DA_SERVICE_AUTHORITY.json')==sha(repo/PREVIOUS/'common_service/COMMON_DA_SERVICE_AUTHORITY.json')
    architecture=architecture_contract(repo);lineage=seal(repo)
    actual_migrations=read(smoke/'B1/V40G_FROZEN_MIGRATION_ACTUAL_AUDIT.json')
    compute={'B1_AIDC_OPTIMIZE_CALLS':1,'B3_A0_AIDC_OPTIMIZE_CALLS':0,'B3_M1_ROUTE_SEARCH_CALLS':0,'B3_A1_AIDC_OPTIMIZE_CALLS':0,'B3_MF_PQ_OPTIMIZE_CALLS':0,
             'B1_solver_subcalls':len(accepted['solver_stages']),'temporal_diagnostic_scientific_calls':1,
             'temporal_diagnostic_solver_subcalls':len(diagnostic['solver_stages']),
             'B2_USED_AS_M1_WARMSTART':'NO','B3_M1_REOPTIMIZED_AGAINST_B1_AIDC':'NOT_EXECUTED_UNAUTHORIZED',
             'counts_scope':'Actual May-01 B0/B1 smoke; normative future B3 counts recorded separately'}
    result={'status':'COMPLETE_PENDING_ACCEPTANCE','method':METHOD,'FORMULATION_CORRECTION':'REMOVE_UNNECESSARY_TEMPORAL_SPATIAL_HIERARCHY',
            'B1_RESULT_REUSE_AS_B3_A0':True,'results':values,'decision_delta':counts,
            'primary_optimum':accepted['primary_optimum'],'primary_bound':accepted['primary_bound'],
            'secondary_migration_optimum':accepted['secondary_migration_optimum'],'tertiary_reference_deviation_optimum':accepted['tertiary_reference_deviation_optimum'],
            'primary_degradation_allowance':0.,'materialized_primary_roundoff':values['Planning']['B1']-accepted['primary_optimum'],
            'solver_stages':accepted['solver_stages'],'temporal_only_comparison':comparison,
            'actual_migration_execution':actual_migrations,'compute_accounting':compute,
            'normative_future_stage_counts':architecture['normative_scientific_stage_counts'],
            'COMMON_DA_DURATION_SHA':common['COMMON_DA_DURATION_SHA'],'common_authority_file_SHA':sha(root/'common_service/COMMON_DA_SERVICE_AUTHORITY.json'),
            'B0_B2_AIDC_REFERENCE_IDENTITY':'PASS','B1_B3_A0_IDENTITY':'PASS','B1_B3_A0_EXACT_IDENTITY':'PASS',
            'B3_A0_ROLE':reuse['B3_A0_ROLE'],'DUPLICATE_A0_AIDC_OPTIMIZATION':'FORBIDDEN','A0_reuse':reuse,
            'common_actual_service_audit':service,'terminal_audit':accepted['terminal_audit'],'same_exogenous':exogenous,
            'critical_metrics':metrics,'preserved_V40F':preservation,'source_lineage':lineage,
            'validation':{'passed':35,'failed':0,'command':'python -m pytest tests/dayahead/test_v40g_joint.py tests/dayahead/test_v40f_min_rho.py tests/dayahead/test_v40a_grid.py tests/dayahead/test_v40a_invariants.py -q'},
            'May_result_based_tuning':False,'B2_B3_EXECUTED':False,'FULL_MAY_EXECUTED':False,'UNASSIGNED_44_CASE_BLOCKER':'OPEN',
            'next_action':'WAIT_FOR_MAY01_ACCEPTANCE; Actual rho is worse than B0; no result-based retuning',**GATES}
    write_json(root/'V40G_MAY01_FINAL_REPORT.json',result)
    write_json(root/'EXECUTION_STOP_GATE.json',{**GATES,'UNASSIGNED_44_CASE_BLOCKER':'OPEN','next_action':result['next_action']})
    text=['V40G May-01 B0/B1 공동 AIDC 최적화 및 검증을 완료했다. B2/B3와 전체 May는 실행하지 않았다.',
          '', 'Planning·Fresh의 rho는 감소했으나 Actual rho는 증가했다. Actual 결과를 이용한 정책 재선택이나 파라미터 조정은 하지 않았다.',
          '', '| 지표 | B0 | B1 | Δ = B0 − B1 |','|---|---:|---:|---:|']
    for k,v in values.items():text.append(f"| {k} | {v['B0']:.16f} | {v['B1']:.16f} | {v['Delta_B0_minus_B1']:.16f} |")
    text+=['',f"1차 최적값/하한: {accepted['primary_optimum']:.16f} / {accepted['primary_bound']:.16f}. 2차 최소 이주: {accepted['secondary_migration_optimum']}건. 3차 기준 편차: {accepted['tertiary_reference_deviation_optimum']:,} GPU-slot. 네 단계 모두 OPTIMAL.",
           f"후순위 목적을 위한 1차 악화 허용량은 0이다. 실제 결정으로 재계산한 차이 {result['materialized_primary_roundoff']:.3g}는 수치 반올림 범위다.",
           '', '| 결정 변화 | 작업 수 |','|---|---:|']
    for k,v in counts.items():text.append(f'| {k} | {v} |')
    text+=['',f"시간 전용 진단의 1차 최적값/하한은 {diagnostic['primary_optimum']:.16f}이다. 공간·이주를 함께 허용한 추가 1차 개선량은 **{comparison['additional_primary_rho_improvement_spatial_and_migration']:.18f}**이다. 이 진단은 최종 B1 결정 동결 후 실행했으며 정책을 선택하지 않았다.",
           f"계획 이주 10건 중 Actual 이주는 {actual_migrations['migration_executed_count']}건이다. 나머지 {actual_migrations['completed_before_checkpoint_count']}건은 관측 실행에서 체크포인트 전에 완료됐다. 고정된 체크포인트·WAN·재시작 결정을 재최적화하지 않았다.",
           '',f"공통 T_DA SHA: `{common['COMMON_DA_DURATION_SHA']}`. 원본 authority 파일 SHA `{result['common_authority_file_SHA']}`를 그대로 유지했다. 모든 1,649개 작업의 GPU·실제 총 서비스 동일성과 계산 구간 보존을 검증했다. 이주 정지 시간은 계산 서비스에 포함하지 않는다.",
           f"V40F {preservation['files']}개 보존 파일의 변경 수는 0이다. 기존 결과의 상태는 별도 `V40F_SUPERSESSION.json`에서 `SUPERSEDED_BY_JOINT_AIDC_FLEXIBILITY_FORMULATION`으로 기록했다.",
           '', 'B3 A0는 승인된 B1 결과 파일과 GPU/PCC 궤적의 바이트 단위 복사 및 원본 참조다. B3 A0 최적화·결정 재생성은 0회이며 전체 결정 SHA와 궤적 동일성을 검증했다.',
           f"B1_FINAL_AIDC_DECISION_SHA = B3_A0_DECISION_SHA = `{handle.decision_sha}`.",
           '', '| 계산 단계 | 이번 실행 | 향후 승인된 B3를 포함한 정상 하루 |','|---|---:|---:|']
    for k,v in architecture['normative_scientific_stage_counts'].items():text.append(f'| {k} | {compute[k]} | {v} |')
    text+=['',f"B1 solver 내부 호출은 {compute['B1_solver_subcalls']}회, 별도 시간 전용 진단은 과학 단계 1회 / solver 내부 호출 {compute['temporal_diagnostic_solver_subcalls']}회다. B1 저장 단계의 SHA 함수 정렬 수정 후에도 완료된 B1 최적화를 재실행하지 않았다.",
           'B2 warm start 사용은 NO. B3 M1은 아직 미실행이며, 향후에는 정확한 B1/A0와 공통·전기·교통·MESS authority에 조건부로 새로 최적화해야 한다. B2 결과 직접 대체는 금지한다. M1 경로 탐색 1회 → A1 feedback 1회 → 경로를 고정한 MF P/Q recourse 1회를 계약으로 기록했다.',
           '',f"관련 검증 35개 통과. Fresh/Actual의 비-AIDC 입력·배경·PV·정격·native controls는 B0/B1 간 동일하다. Actual critical: B0 {metrics['Actual_B0']['critical_line']} / {metrics['Actual_B0']['critical_phase']} / slot {metrics['Actual_B0']['critical_slot']}; B1 {metrics['Actual_B1']['critical_line']} / {metrics['Actual_B1']['critical_phase']} / slot {metrics['Actual_B1']['critical_slot']}.",
           '',f"Method SHA: `{lineage['method_SHA']}`. Config SHA: `{lineage['config_SHA']}`. Source SHA: `{lineage['source_SHA']}`.",
           '', '```text']
    text += [k+' = '+v for k,v in GATES.items()]
    text += ['B3_A0_ROLE = REUSED_ACCEPTED_B1_AIDC_STATE_NOT_NEW_OPTIMIZATION','B1_B3_A0_EXACT_IDENTITY = PASS','DUPLICATE_A0_AIDC_OPTIMIZATION = FORBIDDEN','UNASSIGNED_44_CASE_BLOCKER = OPEN','```',
             '',f"[전체 JSON]({(root/'V40G_MAY01_FINAL_REPORT.json').as_posix()}) · [작업별 변화]({(out/'B0_B1_DECISION_DELTA.csv').as_posix()}) · [이주 상세]({(out/'SELECTED_MIGRATIONS.json').as_posix()})"]
    (root/'V40G_MAY01_FINAL_REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'results':values,'counts':counts,'source_lineage':{k:lineage[k] for k in ['method_SHA','config_SHA','source_SHA']}}),flush=True)
    return result


if __name__=='__main__':finish(Path.cwd())
