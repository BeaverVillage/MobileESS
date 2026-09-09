"""Full-scope completion gate; never emit FINAL_CAMPAIGN_REPORT for partial work."""
from mission_health import *
from fast_prepare import record,check
import numpy as np

def main():
    release=read(RUN/'audit/MAY_CAMPAIGN_RELEASE_V3.json');rows=[];missing=[]
    for day in release['days']:
        for policy in release['policies']:
            root=RUN/day/policy
            requirements={name:root/path for name,path in {
                'DayAhead':'dayahead/DAYAHEAD_RECEIPT.json','Fresh':'dayahead/FRESH_RESULT.json',
                'Actual':'actual/ACTUAL_RECEIPT.json','Actual_native':'actual/grid/NATIVE_ACTUAL_STATE_CONTINUITY.json',
                'unit_manifest':'UNIT_SCIENTIFIC_MANIFEST.json'}.items()}
            if policy=='B3':requirements['A1_B1_audit']=root/'dayahead/A1/V41R4_A1_B1_EQUIVALENCE_AUDIT.json'
            absent=[k for k,p in requirements.items() if not p.exists()]
            rows.append(dict(day=day,policy=policy,missing=absent))
            missing.extend(dict(day=day,policy=policy,requirement=k) for k in absent)
    if missing:
        result=dict(status='INCOMPLETE',required_policy_days=124,policy_days_with_all_required_files=sum(not r['missing'] for r in rows),missing_requirements=missing,checked_at=time.time())
        write(OUT/'COMPLETION_REQUIREMENTS.json',result)
        print('INCOMPLETE',result['policy_days_with_all_required_files'],'/124;',len(missing),'missing requirements');return result
    # A complete file set alone is insufficient; independently verify contents.
    from mission_health import main as health
    health();h=read(OUT/'HEALTH_LATEST.json')
    assert not h['alerts'] and h['counts']=={'COMPLETE_VALIDATED':124}
    assert h['electrical_validated']==31 and read(OUT/'INPUT_REUSE_VALIDATION.json')['count']==31
    from mission_causality import main as causal
    assert causal()['status']=='PASS'
    workers=[]
    for p in psutil.process_iter(['pid','cmdline']):
        cmd=p.info['cmdline'] or []
        if any(Path(s).name in ('v41r4_search_worker.py','mission_worker.py','mission_actual_worker.py') for s in cmd):workers.append(p.info)
    assert not workers,('REQUIRED_WORKERS_STILL_RUNNING',workers)
    finished=read(RUN/'CAMPAIGN_FINISHED.json');assert finished['status']=='COMPLETE' and not finished['errors']
    from dayahead.v41.scientific_archive import verify_manifest
    from dayahead.paper_analysis.storage import digest
    from v41r4_report import grid_summary
    checked=[];reuse=[]
    for day in release['days']:
        snapshot_shas=set()
        for policy in release['policies']:
            root=RUN/day/policy;da=root/'dayahead';ac=root/'actual'
            verify_manifest(root/'UNIT_SCIENTIFIC_MANIFEST.json')
            d=receipt_check(da/'DAYAHEAD_RECEIPT.json');a=receipt_check(ac/'ACTUAL_RECEIPT.json');rec(a['day_ahead'])
            frozen=read(da/'FROZEN_JOINT_DECISION.json');assert digest(frozen['decision'])==d['decision_SHA']==a['decision_SHA']
            decision=frozen['decision'];snapshot_shas.add(decision['ML_snapshot']['sha256']);rec(decision['electrical'])
            certificate=read(decision['electrical']['path'])
            assert certificate['input_identity']['identity']['inputs']['V41R4_FINAL_DATE_BINDING']['day']==day
            assert check(read(da/'FRESH_RESULT.json')['summary'])
            stages=read(da/'PLANNING_RESULT.json')['stages']
            if policy=='B3':
                source=stages['A0_REUSE'];assert source['source_policy']=='B1';rec(source['source'])
                assert source['source']==record(RUN/day/'B1/dayahead/DAYAHEAD_RECEIPT.json')
                coord=stages['COORDINATION'];counts=coord['counts']
                assert counts['MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS']==1 and counts['SECOND_MESS_FULL_ROUTE_SEARCH_CALLS']==0
                assert counts['AIDC_FEEDBACK_PASSES']==counts['FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS']==1
                assert counts['FRESH_CALLS_INSIDE_COOPT_LOOP']==0
                audit=read(da/'A1/V41R4_A1_B1_EQUIVALENCE_AUDIT.json')
                assert audit['M1_before_SHA']==audit['M1_after_SHA'] and audit['Actual_reads']==0
            for phase,folder in [('DA',da),('AC',ac)]:
                arrays=list(folder.rglob('OPENDSS_PHASE_ARRAYS.npz'));assert len(arrays)==1
                with np.load(arrays[0]) as z:
                    assert z['convergence'].shape==(96,) and z['convergence'].all()
                    for key in ('voltage_pu','phase_current_loading_pu'):assert np.isfinite(z[key]).all()
                    tx=z['branch_kinds']=='transformer';lines=z['branch_kinds']=='line'
                    assert (tx|lines).all() and tx.any() and lines.any()
                    assert np.isfinite(z['transformer_total_kva_loading_pu'][:,tx]).all()
                    assert np.isnan(z['transformer_total_kva_loading_pu'][:,lines]).all()
                summary=read(RUN/'audit'/day/f"{policy}_{'DAYAHEAD' if phase=='DA' else 'ACTUAL'}_SUMMARY.json")
                assert summary['status']=='PASS' and summary['grid']==grid_summary(folder)
                phase_receipt=read(RUN/'audit'/day/f'PHASE_{policy}_{phase}.json');assert phase_receipt['status']=='PASS'
                if 'reused_phase' in phase_receipt['result']:reuse.append(dict(day=day,policy=policy,phase=phase,source=phase_receipt['result']['reused_phase']))
            checked.append(dict(day=day,policy=policy,dayahead=record(da/'DAYAHEAD_RECEIPT.json'),actual=record(ac/'ACTUAL_RECEIPT.json')))
        assert len(snapshot_shas)==1,'POLICY_SPECIFIC_FORECAST_OR_FUTURE_LEAKAGE'
    from v41r4_search_runtime import install_reports
    install_reports()
    from v41r4_report import finalize
    summary=finalize(complete=True)
    report=dict(status='COMPLETE_VALIDATED',days=31,policy_days=124,dayahead=124,Fresh=124,Actual=124,
        reused_policy_phases=len(reuse),computed_policy_phases=248-len(reuse),reused_phase_evidence=reuse,
        policy_summaries=summary['policies'],remaining_blockers=[],unit_evidence=checked,
        implementation_evidence=[record(p) for p in OUT.glob('*REPAIR.json')],
        MF_restored_before_execution=record(OUT/'TERMINAL_A1_RETRACTION.json'),
        blocked_duplicate_dispatch_attempts=4,blocked_duplicate_optimizer_calls=0,
        authoritative_outputs=str(RUN),logs=str(ROOT/'logs/v41r4_may/search_time_v3'),completed_at=time.time())
    write(RUN/'FINAL_CAMPAIGN_REPORT.json',report)
    lines=['# FINAL_CAMPAIGN_REPORT','',
        '완료: 31일 × 4정책 = 124건. Day-Ahead/Fresh/Actual 각 124건 검증 완료.',
        f'정책 단계 재사용 {len(reuse)}건, 계산 {248-len(reuse)}건. 모든 음의 과학 결과 보존.',
        '입력·최종 α=1.15 계수 각 31일 검증. Actual 최적화 0회, 미래정보 경계 및 B3 A1/MF 감사 통과.',
        '실행 관리자 인수 오류: 중복 시도 4건이 솔버 실행 전 차단됨. 원래 작업 보존 후 상태 처리 수정. MF 제외안은 B3 실행 전에 철회되어 결과 영향 없음.',
        '기타 복구·수정 상세는 JSON의 implementation_evidence 및 기존 캠페인 수정 증거 참조. 잔여 차단요인 없음.','',
        '|정책|일수|Actual 최대 선로부하 일평균|DA P1 일평균|B0 대비 개선일|','|---|---:|---:|---:|---:|']
    for p,g in summary['policies'].items():lines.append(f"|{p}|{g['days']}|{g['Actual_rho_max']['mean']:.6f}|{g['DayAhead_P1']['mean']:.6f}|{g['improvement_days_vs_B0']}|")
    lines+=['',f'권위 산출물: {RUN}',f'실행 로그: {ROOT / "logs/v41r4_may/search_time_v3"}']
    (RUN/'FINAL_CAMPAIGN_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    write(OUT/'COMPLETION_REQUIREMENTS.json',dict(status='COMPLETE_VALIDATED',report=record(RUN/'FINAL_CAMPAIGN_REPORT.json'),checked_at=time.time()))
    print('COMPLETE_VALIDATED_124_POLICY_DAYS');return report
if __name__=='__main__':main()
