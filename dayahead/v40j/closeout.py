"""Close research under HOLD when the registered selection yields no winner."""
import json
import subprocess
from pathlib import Path
from .contracts import ROOT, OUT, START, PF, FEATURES, SPLIT
from .firewall import sha, write

def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))

def main():
    selection=read('V40J_SELECTION_FREEZE.json')
    if selection['winner'] is not None:
        raise RuntimeError('WINNER_REQUIRES_FINAL_SHADOW_BEFORE_CLOSEOUT')
    comparisons=read('V40J_CONDITIONAL_CALIBRATION_REPORT.json')['comparisons']
    point=read('V40J_POINT_MODEL_COMPARISON.json')
    point_pass=any(r['gates']['point'] for r in comparisons)
    bound_pass=any(r['gates']['coverage'] for r in comparisons)
    if point_pass and not bound_pass:
        classification='V40J_POINT_MODEL_IMPROVED_CALIBRATION_INSUFFICIENT'
    elif bound_pass and not point_pass:
        classification='V40J_CALIBRATION_IMPROVED_POINT_MODEL_INSUFFICIENT'
    elif point_pass and bound_pass:
        classification='V40J_ROBUSTNESS_INSUFFICIENT'
    else:
        classification='V40J_RUNTIME_REDESIGN_FAIL'
    for label in ['V40J_PREMAY_FINAL_SHADOW_REPORT.json']:
        write(label,{'status':'NOT_RUN_NO_ELIGIBLE_WINNER','shadow':SPLIT['final_shadow'],
          'shadow_row_payload_opened':False,'metadata_only_census':True,'winner_reselected':False,
          'point_metrics':None,'coverage':None,'GPU_weighted_miss':None,'overreservation':None,
          'B0_B1_shadow':'NOT_AUTHORIZED_RUNTIME_GATES_NOT_ALL_PASS','production_campaign':'NO'})
    write('V40J_SUPPORT_GUARD_REPORT.json',{'definitions':'V40J_MODEL_SELECTION_HIERARCHY.json',
       'candidate_support_counts':{r['id']:r['support_counts'] for r in comparisons},
       'fallback':'exact/near causal support only; sparse and regime mismatch skip leaf calibration and take conservative parent maximum',
       '12h_rule':'no dedicated threshold or model; 12h passes through standard wall bucket and exact/other8 support rules',
       'no_status_in_support':True,'test_status':'see V40J_TEST_REPORT.json'})
    write('V40J_GPU_WEIGHTED_SAFETY_REPORT.json',{'metrics':{r['id']:r['metrics'] for r in comparisons},
       'baseline':comparisons[0]['baseline'],'GPU_miss_gate_pass_count':sum(r['gates']['GPU'] for r in comparisons),
       'grid_authority_status':'UNAVAILABLE_NOT_INFERRED_FROM_PLANNING_SITE',
       'critical_slot_proxy':'all active-miss GPU slots; not actual critical-line ground truth',
       'GRID_RELEVANT_RUNTIME_MISS_RATE':None})
    start=read('V40J_START_STATE.json')
    changed=[]
    for name,expected in start['protected_worktree_stat_inventory'].items():
        p=ROOT/name
        actual=[p.stat().st_size,p.stat().st_mtime_ns] if p.exists() else None
        if actual!=expected: changed.append({'path':name,'before':expected,'after':actual})
    tree={p:subprocess.check_output(['git','rev-parse','HEAD:'+p],cwd=ROOT,text=True).strip() for p in start['protected_tree_hashes']}
    protected_pass=not changed and tree==start['protected_tree_hashes']
    write('V40J_PROTECTED_SCOPE_DIFF.json',{'status':'PASS' if protected_pass else 'FAIL',
       'tree_hashes_before':start['protected_tree_hashes'],'tree_hashes_after':tree,
       'tracked_worktree_metadata_changes_outside_V40J':changed,
       'tracked_files_compared':len(start['protected_worktree_stat_inventory']),
       'unrelated_start_changes_preserved':True,
       'old_artifact_content_not_reread':'Git tree object hashes plus unchanged size/mtime inventory; guarded research writes only V40J',
       'PF':PF,'authority_missing':72,'31_DAY_ELECTRICAL_REGENERATION':'HOLD','B2_B3':'NO','FULL_MAY':'NO'})
    stages={p.name:json.loads(p.read_text(encoding='utf-8')) for p in OUT.glob('READS_*.json') if 'test' not in p.name}
    count=sum(r['may_payload_reads'] for r in stages.values())
    denied=[v for r in stages.values() for v in r['denied']]
    nondata_denied=[d for d in denied if d.get('path','').endswith('python311.zip') or 'nul' in d.get('path','').lower()]
    data_denied=[d for d in denied if d not in nondata_denied]
    write('V40J_FIREWALL_EXECUTION_REPORT.json',{'model_building_May_payload_read_count':count,
       'model_building_May_source_or_artifact_read_count':0,
       'counters':read('V40J_FIREWALL_COUNTERS.json')['counters'],
       'guarded_stages':{k:{'events':len(v['events']),'denied':v['denied']} for k,v in stages.items()},
       'guarded_status':'PASS' if count==0 and not data_denied else 'FAIL',
       'nondata_runtime_probe_denials_retained':nondata_denied,
       'denial_note':'Pinned Python probed its optional stdlib ZIP and Windows NUL device. These denied nondata probes did not expose data; exact baseline output still reproduced. All original denial events are retained.',
       'session_wide_zero_read_claim':False,'discovery_exception':start['discovery_exception'],
       'motivation_authority_documents':'explicitly requested read-only V40I documents; never imported by model-building processes',
       'legacy_tests_scope':'May row/outcome fixtures not reopened; previous 106+80 PASS receipt retained and protected sources verified unchanged',
       'April_footer_only_read':True,'April_shadow_row_payload_read':False,
       'raw_partition_timezone_warning':'April native-time partition footer extends to 2025-05-01 UTC. No April row was decoded; any future shadow extractor must filter UTC row timestamps as well as partition names.',
       'interrupted_evaluator':'Stopped before aggregate selection to repair Q90 gate separation; confined to V40J development files, see implementation repair log.'})
    write('V40J_RUNTIME_METHOD_FREEZE.json',{'classification':classification,'status':'NO_WINNER_FAIL_CLOSED',
       'winner':None,'production_integration_recommendation':'NO','retained_runtime':'unchanged current MoE-XGBoost + q=5576.44921875s + existing ceil/fallback',
       'source_start_commit':START,'preregistration_commit':'570c653','amendment_commit':read('V40J_AMENDMENT_01_COMMIT_RECEIPT.json')['commit'],
       'feature_contract':FEATURES,'source_files_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'dayahead/v40j').glob('*.py')},
       'training_input_hash':read('V40J_PREMAY_RUNTIME_ROW_CENSUS.json')['source_sha256'],
       'split_sha256':sha(OUT/'V40J_TEMPORAL_SPLIT_CONTRACT.json'),
       'registry_sha256':sha(OUT/'V40J_CANDIDATE_REGISTRY.json'),
       'model_artifacts_sha256':{p.name:sha(p) for p in (OUT/'models').glob('*.pkl')},
       'calibration_artifacts_sha256':{p.name:sha(p) for p in OUT.glob('CALIBRATION_*.json')},
       'selection_reason':'No candidate satisfies every preregistered gate. No final calibration or shadow outcome used to replace winner.',
       'data_scope_limitation':'GPU normalized cache submitted 2024-10-27 through 2025-03-31; earliest end-known label 2024-10-31. Early folds have less than a full 120 days of available cached history. Raw older partitions were inventoried, not added after outcomes.',
       'point_gate_any_PASS':point_pass,'conditional_coverage_gate_any_PASS':bound_pass,
       'protected_scope_PASS':protected_pass,'shadow':'SEALED_NO_WINNER',
       'robust_envelope_selected':None,'support_fallback':'implemented and regression-tested; no production integration',
       'authority_missing':72,'PF':PF,'Q_control':'NO','31_DAY_ELECTRICAL_REGENERATION':'HOLD','B2_B3':'NO','FULL_MAY':'NO'})
    external=read('V40J_EXTERNAL_DATACENTER_PQ_AUDIT.json')
    lines=['# V40J 최종 연구 검토','',f'판정: **{classification}**. Winner는 없으며 production integration recommendation은 **NO**다.',
      '',f'시작 HEAD `{START}`, 사전등록 커밋 `570c653`. 최종 커밋은 별도 git receipt에서 확인한다.',
      '', 'May runtime/status row, Actual outcome artifact, model-building, training, calibration, model-selection 읽기 횟수는 각각 0이다. 초기 path/code 탐색과 metadata 읽기는 별도 NONZERO 카운터로 공개했다. 정확한 전체 횟수는 주장하지 않는다. V40I 문서는 요청된 motivation/claim-boundary로만 읽었다. Amendment 커밋 69d8425 이후에만 winner selection을 수행했다.',
      '', '원자료 footer census는 21개 pre-May native-time 월 파티션과 7,325,307행을 확인했다. 실제 후보 개발 입력은 기존 pre-issue normalized cache의 GPU 233,999행이다. CPU 전용 작업이나 unobserved/censored jobs에 대한 성능을 주장하지 않는다. April partition은 UTC 기준 May-01 일부 시간까지 걸치므로 metadata와 row payload를 구분했다.',
      '', '실제 GPU cache의 submit 범위는 2024-10-27–2025-03-31, end-known 범위는 2024-10-31–2025-03-31이다. 최대 120일 lookback을 적용했지만 cache 시작일 때문에 초기 fold의 실제 historical support는 120일보다 짧다. 더 오래된 raw 자료 전체를 학습한 실험으로 주장하지 않는다.',
      '', '검증: F1 2025-02-15–21, F2 02-22–28, F3 03-01–07. 학습마다 end_time-known을 적용했다. Calibration에는 별도 앞선 블록만 사용했다. 최종 03-08–31 calibration과 04-24–30 shadow는 winner가 없으므로 실행하지 않았다.',
      '', '현재 baseline은 고정된 3월 22일 예측과 byte-identical, 최대 차이 0초로 재현했다. 새 후보는 L1, log1p, Huber, Q50, causal early-termination mixture, 직접 Q50/Q90/Q95다. C4는 candidate 환경에 필요한 survival dependency가 없어 사전등록대로 제외했다.',
      '', '| Point candidate | COMPLETED H100-standby underprediction | Mean actual-point (s) | MAE (s) |',
      '|---|---:|---:|---:|']
    for cid,report in point.items():
        m=report['pooled']['COMPLETED H100-standby']
        lines.append(f"| {cid} | {m['underprediction_rate']:.4%} | {m['mean_signed_error_seconds']:.3f} | {m['MAE_seconds']:.3f} |")
    lines+=['','조건부 native Q90 coverage는 point·reserve와 분리해 판정했다. 아래는 후보별 N=100, R3 진단이며 winner를 의미하지 않는다. 전체 N=100/200/500 및 R0–R3 결과는 JSON에 있다.','',
       '| Candidate | Native Q90 coverage | H100-standby | Active-miss GPU-slots | Overreserved GPU-h | Gates |',
       '|---|---:|---:|---:|---:|---|']
    for r in comparisons:
        if r['minimum_support']==100 and r['envelope']=='R3':
            group=r['coverage_by_fold_critical_group'].get('pooled/H100-standby',{})
            lines.append(f"| {r['candidate']} | {r['native_upper90_metrics']['coverage']:.4%} | {group.get('coverage',0):.4%} | {r['metrics']['CRITICAL_SLOT_MISS_GPU_SLOTS']:,.0f} | {r['metrics']['overreserved_GPU_hours']:,.2f} | {r['gates']} |")
    lines+=['', 'R0는 nominal 점유, R1은 Q90 hard 점유, R2는 nominal 점유에 Q90까지의 capacity/grid reserve, R3는 Q90 hard 점유에 Q95까지 reserve다. Offline duration-aligned workload replay만 수행했다. 실제 grid-critical line metric은 독립 pre-May authority가 연결되지 않아 NOT_EVALUATED로 남겼다. 다른 site를 actual site로 대체하지 않았다.',
       '', '12h 전용 규칙은 없다. exact9/other8, hardware, walltime, regime support를 반환하며 sparse/regime mismatch는 leaf를 건너뛰고 보수적인 parent calibration으로 fallback한다. OUT_OF_SUPPORT는 requested-walltime 이상으로 확장하고 요청값이 잘못되면 abstain한다. 이러한 fallback의 reservation 비용도 gate에 포함했다.',
       '', f"외부 P/Q 판정: **{external['classification']}**. 총 PF P5/P50/P95 = {external['PF_magnitude']['P5']:.6f}/{external['PF_magnitude']['P50']:.6f}/{external['PF_magnitude']['P95']:.6f}. SHA 일치·원본 불변. 극성 반전 때문에 leading/lagging은 조건부 해석이다. 상세 출처와 계산은 별도 외부 감사 문서에 있다.",
       '', 'Protected scope, current q/model, PF=0.95를 보존한다. 72 authority blockers 유지, 31-day electrical regeneration HOLD, B2/B3 NO, FULL_MAY NO, Q control NO. Optional B0/B1 shadow도 gate 미통과로 실행하지 않았다.',
       '', '테스트 실행 수와 로그·hash는 V40J_TEST_REPORT.json에 기록한다. 기존 V40H 106/V40I 80 PASS는 frozen receipt와 소스 보존으로 유지하며 May outcome/row fixtures를 다시 열어 재실행하지 않았다. 새 V40J 회귀는 실제 실행했다. Shadow를 열거나 cutoff·후보·support threshold를 바꿔 실패를 보정하지 않았다.']
    (OUT/'V40J_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(classification)

if __name__=='__main__':main()
