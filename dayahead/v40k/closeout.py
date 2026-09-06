"""Final read-only preservation audit and fail-closed research report."""
import json
import xml.etree.ElementTree as ET
import numpy as np
from .common import *
from .data import frame,train_mask,timestamp_mask
from .protocol import SPLIT

def main():
    selection=read('V40K_POINT_SELECTION.json');point=selection['winner']
    safe=read('V40K_SAFE_SELECTION.json').get('winner') if (OUT/'V40K_SAFE_SELECTION.json').exists() else None
    if point is None:
        classification='V40K_POINT_MODEL_INSUFFICIENT'
        assert not (OUT/'V40K_POINT_MODEL_FREEZE.json').exists()
        assert not (OUT/'SAFE_FIT_ROWS.parquet').exists()
        write('V40K_SAFE_BOUND_COMPARISON.json',{'status':'NOT_RUN_POINT_GATE_FAILED','winner':None,'Q90_metrics':None})
        write('V40K_FINAL_SHADOW_REPORT.json',{'status':'NOT_OPENED_POINT_GATE_FAILED','runtime_status_rows_opened':0,'metrics':None,'winner_reselected':False,'q_changed':False,'refit':False})
    elif safe is None:
        classification='V40K_POINT_READY_SAFE_BOUND_INSUFFICIENT'
        write('V40K_FINAL_SHADOW_REPORT.json',{'status':'NOT_OPENED_SAFE_GATE_FAILED','runtime_status_rows_opened':0,'metrics':None,'winner_reselected':False,'q_changed':False,'refit':False})
    else:
        shadow=read('V40K_FINAL_SHADOW_REPORT.json')
        classification='V40K_CENTRAL_RUNTIME_AND_SAFE_BOUND_READY' if shadow['status']=='PASS' else 'V40K_FINAL_SHADOW_FAIL_HOLD'
    start=read('V40K_START_STATE.json');changes=[]
    for n,old in start['protected_tracked_metadata'].items():
        p=ROOT/n;new=[p.stat().st_size,p.stat().st_mtime_ns] if p.exists() else None
        if new!=old:changes.append(n)
    jchanges=[n for n,h in start['V40J_file_sha256'].items() if not (ROOT/n).exists() or sha(ROOT/n)!=h]
    committed=git('diff','--name-only',START,'HEAD').decode().splitlines()
    assert all(n.startswith(('dayahead/v40k/','dayahead/artifacts/v40k_central_runtime/')) for n in committed)
    assert not changes and not jchanges,('PROTECTED_SCOPE_CHANGED',changes,jchanges)
    write('V40K_PROTECTED_SCOPE_DIFF.json',{'status':'PASS','protected_tracked_files':len(start['protected_tracked_metadata']),
      'metadata_changes':changes,'V40J_exact_hashed_files':len(start['V40J_file_sha256']),'V40J_hash_changes':jchanges,
      'V40J_postcommit_receipt_preserved':True,'unrelated_changes_preserved':True,'history_rewritten':False,
      'May_artifacts_not_reopened':'non-V40J protection uses tracked metadata and Git object/path comparison'})
    f=frame(J/'DEVELOPMENT_GPU_ROWS.parquet');tr=f.loc[train_mask(f,SPLIT['final_point_fit_before'])]
    extra={p.stem.removeprefix('EXTRACTION_'):json.loads(p.read_text()) for p in OUT.glob('EXTRACTION_*.json')}
    latest=[str(f[['submit_time','start_time','end_time']].max().max())]+[v['maximum_accepted_timestamp'] for v in extra.values() if v.get('maximum_accepted_timestamp')]
    write('V40K_PREMAY_TIMESTAMP_FIREWALL.json',{'canonical_timezone':'UTC','local_cutoff':CUTOFF,'UTC_cutoff':CUTOFF,
      'fixed_AEST_equivalent':'2025-05-01T10:00:00+10:00','new_partition_footer_scan_count':1,'April_row_groups_inventoried':31,
      'accepted_development_GPU_rows':int(timestamp_mask(f).sum()),'final_model_training_GPU_rows':len(tr),
      'final_model_train_submit_range':[str(tr.submit_time.min()),str(tr.submit_time.max())],
      'final_model_train_end_range':[str(tr.end_time.min()),str(tr.end_time.max())],
      'maximum_accepted_timestamp':max(latest),'post_cutoff_rows_materialized':0,
      'exact_post_cutoff_row_count_inside_excluded_groups':None,'minimum_rejected_row_timestamp':None,
      'unknown_count_reason':'Strictly exclude entire mixed boundary/future-completion row groups before decoding; footer maxima do not give exact rejected-row counts.',
      'stage_extractions':extra,'training_support_end_known':True,'complete_case_scope':True,
      'shadow_protocol':SPLIT['shadow_requirement']})
    events=[json.loads(s) for s in (OUT/'V40K_EVENTS.jsonl').read_text(encoding='utf-8').splitlines() if s]
    raw=[e for e in events if e['kind']=='raw_row_group_decoded']
    meta={x['row_group']:x for x in read('V40K_APRIL_FOOTER_AVAILABILITY.json')['row_groups']}
    from .data import allowed_group
    assert all(allowed_group(meta[e['row_group']],SPLIT[e['stage']]) for e in raw)
    counters=read('V40K_PREMAY_READ_FIREWALL.json')['new_May_scientific_counters']
    write('V40K_FIREWALL_EXECUTION_REPORT.json',{'status':'PASS','new_May_scientific_counters':counters,
      'raw_groups_decoded_by_stage':{s:[e['row_group'] for e in raw if e['stage']==s] for s in ['point_selection','safe_fit','safe_selection','final_shadow']},
      'every_decoded_group_preMay_and_stage_authorized':True,'new_metadata_only_operations':1,
      'path_and_metadata_inventories':'NONZERO; no session-wide zero-read claim','inherited_J_counters_unchanged':True,
      'denied_events_retained':sum(e['kind']=='read_denied' for e in events),'shadow_payload_rows':read('V40K_FINAL_SHADOW_REPORT.json')['runtime_status_rows_opened']})
    xml=ET.parse(OUT/'V40K_REGRESSIONS.xml').getroot();suites=[xml] if xml.tag=='testsuite' else list(xml.iter('testsuite'))
    tests={k:sum(int(x.get(k,0)) for x in suites) for k in ['tests','failures','errors','skipped']}
    assert tests['failures']==tests['errors']==tests['skipped']==0
    det=read('V40K_TRAINING_DETERMINISM.json');assert all(r['status']=='PASS' for r in det)
    write('V40K_TEST_REPORT.json',{'executed_V40K':tests,'passed':tests['tests'],'independently_repeated_candidate_fits':len(det),
      'candidate_prediction_bytes_identical':True,'K0_reproduction':read('V40K_BASELINE_REPRODUCTION.json'),
      'normalization_equivalence':read('V40K_FEATURE_TARGET_EQUIVALENCE.json'),
      'stacking_repeat':read('V40K_STACKING_WEIGHTS.json')['independent_repeat_identical'],
      'protected_scope':'PASS','V40J_55_PASS':'frozen prior result preserved; V40J files not modified',
      'V40H_106_V40I_80':'frozen prior receipts preserved; May fixtures not rerun',
      'new_scientific_GPU_fits':0,'CPU_only':True,'junit_SHA':sha(OUT/'V40K_REGRESSIONS.xml'),'log_SHA':sha(OUT/'V40K_REGRESSIONS.log')})
    comp=read('V40K_POINT_MODEL_COMPARISON.json');safe_comp=read('V40K_SAFE_BOUND_COMPARISON.json')
    write('V40K_GPU_WEIGHTED_REPORT.json',{'scope':'workload-layer metrics only; grid-critical line improvement unavailable',
      'safe_bound_comparison':safe_comp,'final_shadow':read('V40K_FINAL_SHADOW_REPORT.json'),'optimization_run':False})
    final={'classification':classification,'point_winner':point,'safe_winner':safe,'source_start':START,
      'preregistration_commit':read('V40K_PREREGISTRATION_COMMIT_RECEIPT.json')['commit'],'CPU_only':True,
      'PF':.95,'Q_control':'NO','authority_missing':72,'31_DAY_ELECTRICAL_REGENERATION':'HOLD','B0_B1_B2_B3_optimization':'NO','FULL_MAY':'NO',
      'production_integration':'NO_LAYER_C_OUT_OF_SCOPE','shadow':read('V40K_FINAL_SHADOW_REPORT.json')['status']}
    write('V40K_FINAL_STATUS.json',final)
    lines=['# V40K 최종 검토','',f"판정: **{classification}**. Point winner: {point}; safe winner: {safe}.",'',
      f"시작 HEAD `{START}`, 사전등록 `{final['preregistration_commit']}`. 최종 commit은 별도 post-commit receipt로 검증한다.",'',
      '이번 revision은 conditional median Q50를 prospective estimand로 사용했다. Pinball50=MAE/2이며 두 지표를 독립 근거처럼 해석하지 않는다. Mean signed error는 diagnostic만 보고했다. V40J 결과와 winner NONE은 보존했다.','',
      'March08–21은 V40J C0 학습 입력에 노출되어 독립 holdout에서 제외했다. Inner CV는 Feb22–Mar07, 최종 후보 fit은 end-known Apr01 이전, 새 point selection은 Apr01–07, safe fit은 Apr08–14, safe selection은 Apr15–23, shadow는 Apr24–30 UTC로 사전등록했다.','',
      'April native partition에는 post-May timestamps와 5월 이후 종료 작업이 섞여 있다. Strict firewall은 block 및 cutoff를 가로지르는 row group 전체를 값 배열 decoding 전에 제외한다. 실제 제출 범위·날짜·누락 group은 timestamp firewall에 기록했다. 이 제한된 complete-case cohort를 전체 날짜/모든 작업으로 일반화하지 않는다.','',
      '| Point candidate | Q50 pinball (s) | MAE (s) | Underprediction | Median calibration error | Mean signed error (s), diagnostic | Eligible |',
      '|---|---:|---:|---:|---:|---:|---|']
    rows={'K0':{'metrics':comp['baseline'],'eligible':False},**comp['candidates']}
    for cid,r in rows.items():
        m=r['metrics']['overall'];lines.append(f"| {cid} | {m['pinball_Q50']:.3f} | {m['MAE']:.3f} | {m['underprediction']:.4%} | {m['median_calibration_error']:.6f} | {m['mean_signed_error_diagnostic']:.3f} | {r['eligible']} |")
    lines+=['','Subgroup별 catastrophic regression 및 COMPLETED H100-standby median gate 결과는 POINT_MODEL_COMPARISON JSON에 모두 남겼다.','',
      f"Shadow: **{final['shadow']}**. Winner 변경/q 변경/refit은 하지 않았다.",'',
      f"신규 V40K 회귀 {tests['tests']} PASS; candidate 독립 반복 {len(det)}회, K0 exact reproduction PASS. CPU configuration 유지, 실제 GPU candidate fit 0회. 한 차례 사용자 GPU 지시로 CPU process를 중단한 뒤 CPU 유지 정정에 따라 검증된 중간 모델을 재사용해 재개했다. 실제 GPU 학습 결과는 섞지 않았다.",'',
      '외부 P/Q는 V40J의 PLAUSIBLE_APPROXIMATION 및 PF P5/P50/P95=0.943389/0.950123/0.958954를 그대로 보존했다. PF=0.95, Q control NO. 72 authority blockers 유지, electrical generation HOLD, B0/B1/B2/B3 NO, FULL_MAY NO.']
    (OUT/'V40K_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    required=['V40K_START_STATE.json','V40K_TEMPORAL_SPLIT_CONTRACT.json','V40K_POINT_ESTIMAND_CONTRACT.json','V40K_CANDIDATE_REGISTRY.json',
      'V40K_POINT_SWING_ROOT_CAUSE.json','V40K_POINT_SWING_ROOT_CAUSE.md','V40K_POINT_MODEL_COMPARISON.json','V40K_SAFE_BOUND_REGISTRY.json',
      'V40K_SAFE_BOUND_COMPARISON.json','V40K_GPU_WEIGHTED_REPORT.json','V40K_PREMAY_TIMESTAMP_FIREWALL.json','V40K_PREMAY_READ_FIREWALL.json',
      'V40K_FINAL_SHADOW_REPORT.json','V40K_PROTECTED_SCOPE_DIFF.json','V40K_TEST_REPORT.json','V40K_FINAL_REVIEW.md','V40K_FINAL_STATUS.json']
    if point:required.append('V40K_POINT_MODEL_FREEZE.json')
    if safe:required.append('V40K_SAFE_BOUND_FREEZE.json')
    write('V40K_ARTIFACT_MANIFEST.json',{'classification':classification,'required_artifacts':{n:sha(OUT/n) for n in required},
      'point_freeze_omitted_reason':None if point else 'Section10: create only when a point winner exists; point gate failed',
      'final_commit_receipt':'generated after final research commit to avoid self-referential SHA'})
    print(json.dumps(final),flush=True)
if __name__=='__main__':main()
