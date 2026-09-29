"""Integrity, causal replay, model parity, and complete gated delivery checks."""
from common13 import *
from model13 import Hazard,matrix,frozen_v9,columns
from train13 import summarize
from finalize13 import SKIPPED_CSV,SKIPPED_JSON
from collect_final13 import EARLY
import subprocess,re

def main():
    verdict=read(ROOT/'FINAL_VERDICT.json');assert verdict['status']=='STOPPED_AFTER_STAGE_B'
    old=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')['prior'];count=0
    for group in old:
        p=Path(group['manifest']['path']);assert sha(p)==group['manifest']['sha256']
        for r in read(p)['files']:assert sha(p.parent/r['relative'])==r['sha256'];count+=1
    for name in ['PREREGISTRATION.json','TRAINING_CODE_FREEZE.json','TOTAL_MODEL_SELECTION_FREEZE.json']:
        for r in read(ROOT/name)['files']:assert sha(r['path'])==r['sha256'],str(r['path'])
    source=read(ROOT/'SOURCE_MANIFEST.json')
    for r in source['roles']+[source['source']]:assert sha(r['path'])==r['sha256']
    for i in range(1,6):
        contract=read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]
        for role in ['TRAIN','CAL','VALID']:assert ids(data(i,role))==contract['membership'][role]
    start=pd.Timestamp(read(ROOT/'TRAINING_STARTED.json')['time'])
    for name in ['PREREGISTRATION.json','TRAINING_CODE_FREEZE.json','CURRENT_STATE_CAUSALITY_AUDIT.json','CURRENT_STATE_REPLAY_AUDIT.json','INDEPENDENT_STATE_AUDIT.json','STAGE_A_VERDICT.json']:
        assert pd.Timestamp(read(ROOT/name)['time'])<start
    audit=read(ROOT/'CURRENT_STATE_CAUSALITY_AUDIT.json');assert audit['PASS'] and audit['N']>=1000
    for key in ['FUTURE_SUBMIT_READS','FUTURE_START_READS','FUTURE_END_READS','CURRENT_JOB_FUTURE_EVENT_READS']:assert audit[key]==0
    assert sha(audit['feature_file']['path'])==audit['feature_file']['sha256']
    replay=read(ROOT/'CURRENT_STATE_REPLAY_AUDIT.json');assert replay['PASS']
    assert replay['continuous_hash']==replay['chunked_restored_hash']==replay['fresh_process_hash']==audit['feature_values_sha256']
    for key in ['state_checkpoint','dispatcher_cursor']:
        r=replay[key];assert sha(r['path'])==r['sha256']
    assert read(ROOT/'INDEPENDENT_STATE_AUDIT.json')['PASS']
    unit=subprocess.run([sys.executable,'-B',str(ROOT/'test_state13.py')],capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert unit.returncode==0,unit.stderr
    guard=subprocess.run([sys.executable,'-B',str(ROOT/'stage_gate13.py')],capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert guard.returncode!=0 and 'NOT_RUN_GATE_FAILED' in guard.stderr
    features=pd.read_parquet(LOCAL/'CURRENT_STATE_FEATURES.parquet').set_index('job_id')
    # Whole-stream semantic invariants, independent of learned model behavior.
    for shorter,longer in zip([300,900,3600,21600],[900,3600,21600,86400]):
        assert features[f'a_{shorter}_count'].le(features[f'a_{longer}_count']).all()
    for prefix in ['p_','r_']:
        present=features[prefix+'count']>0
        assert features.loc[present,prefix+'age_q50'].ge(0).all()
        # Epoch-second linear interpolation can round at sub-microsecond scale.
        assert (features.loc[present,prefix+'age_q90']+1e-6).ge(features.loc[present,prefix+'age_q50']).all()
        assert (features.loc[present,prefix+'age_max']+1e-6).ge(features.loc[present,prefix+'age_q90']).all()
        assert features.loc[~present,prefix+'age_q50'].isna().all()
        label='pending' if prefix=='p_' else 'running'
        for field in ['qos','partition','gpu_bucket','wall_bucket']:
            key=f'c_{label}_{field}_'
            cc=[c for c in features if c.startswith(key+'share_') or c==key+'OTHER']
            total=features[cc].sum(axis=1)
            assert np.allclose(total.to_numpy(),present.astype(float).to_numpy(),rtol=0,atol=1e-12)
            assert features[key+'HHI'].between(0,1+1e-12).all()
    comp=pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv');assert len(comp[comp.calibration.eq('C0')])==6 and not comp.eligible.any()
    primary=comp[comp.calibration.eq('C0')]
    assert primary.proper_score_finite.all() and primary.monotonicity_pass.all() and primary.zero_support_count.sum()==0
    parity=[];importance=[]
    for path in sorted((ROOT/'FOLD_MODELS').glob('fold*/*/model.json')):
        i=int(path.parent.parent.name[4:]);name=path.parent.name;m=Hazard.load(path.parent)
        pre=m.meta['preprocessing'];f=data(i,'VALID').head(100);x=matrix(f,pre,features,m.meta['columns'])
        par=m.parameters(x,threads=1);q=np.column_stack([m.inverse_logsf(par,np.log1p(-p)) for p in [.5,.9]])
        saved=np.load(LOCAL/f'fold{i}'/(name+'_quantiles.npz'))['q'][:100]
        assert np.array_equal(q,saved),name
        changed=f.copy();changed['runtime_seconds']=1e15;changed['end_time']=pd.Timestamp('2099-01-01T00Z');changed['start_time']=pd.Timestamp('2098-01-01T00Z')
        pd.testing.assert_frame_equal(x,matrix(changed,pre,features,m.meta['columns']),check_exact=True)
        assert not set(['job_id','runtime_seconds','end_time','start_time','submit_time'])&set(m.meta['columns'])
        if 'reused_equivalent_arm' in m.meta:
            other=m.meta['reused_equivalent_arm']
            assert np.array_equal(np.load(LOCAL/f'fold{i}'/(name+'_quantiles.npz'))['q'],np.load(LOCAL/f'fold{i}'/(other+'_quantiles.npz'))['q'])
        parity.append(dict(fold=i,arm=name,N=100,bit_identical=True,current_outcomes_ignored=True,model=record(path),booster=record(path.parent/'hazard.txt')))
        for column,gain in zip(m.meta['columns']+['hazard_log_start','hazard_log_end','hazard_log_width','hazard_bin_index'],m.booster.feature_importance('gain')):
            importance.append(dict(fold=i,arm=name,feature=column,gain=float(gain),interpretation='descriptive predictive association; not causal importance'))
    pd.DataFrame(importance).to_csv(ROOT/'DESCRIPTIVE_FEATURE_IMPORTANCE.csv',index=False)
    for i in range(1,6):assert read(ROOT/f'V9_PARITY/fold{i}.json')['parameters_equal']
    # Every trained component must be represented by full saved predictions.
    early=read(ROOT/'EARLY_TERMINATION_RECEIPT.json')
    assert early['EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE'] and not early['additional_training_authorized']
    assert pd.Timestamp(early['scientific_decision_time']) < pd.Timestamp(early['current_jobs_completed'][0]['done'])
    expected=25+early['completed_ablation_folds']
    ab=pd.read_csv(ROOT/'CURRENT_STATE_FEATURE_ABLATION.csv')
    assert ab.group.tolist()==list('ABCDE') and ab.completed_fold_count.tolist()==[5,5,5,5,2]
    for _,r in ab.iterrows():
        if r.group!='E':
            assert r.metrics_available and r.status=='DIAGNOSTIC_ONLY'
        else:
            assert not r.metrics_available and r.status==EARLY
            for key in ['Q90_coverage','min_fold_coverage','gt4h_coverage','Q90_pinball','eligible']:
                assert pd.isna(r[key]), ('unrun full-arm metric fabricated', key)
    for item in early['fold_inventory']:
        if item['metrics_available']:
            for r in item['files']:assert sha(r['path'])==r['sha256']
        else:
            assert item['status']==EARLY and item['group']=='E' and item['fold'] in [3,4,5]
            folder=LOCAL/f"fold{item['fold']}";name=item['arm']
            for suffix in ['.json','.parquet','_quantiles.npz']:assert not (folder/(name+suffix)).exists()
            assert not (ROOT/'FOLD_MODELS'/f"fold{item['fold']}"/name).exists()
    for r in early['preserved_logs']:
        assert sha(r['original']['path'])==r['original']['sha256']==sha(r['archived']['path'])==r['archived']['sha256']
    for slot,blocked in [(0,3),(1,4)]:
        log=(LOCAL/f'ablation_worker{slot}.log').read_text(encoding='utf-8')
        after=log.split(f'FIT {blocked} EXPANDING_S4_ABL_E',1)[1]
        assert 'PermissionError' in after and 'HAZARD_BIN_CONTRACT.json' in after
        assert 'PREDICT' not in after and 'DONE' not in after
    local_evidence=read(ROOT/'LOCAL_EVIDENCE_MANIFEST.json')
    for r in local_evidence['files']:assert sha(r['path'])==r['sha256']
    assert len(parity)==expected,(len(parity),expected)
    af=pd.read_csv(ROOT/'ABLATION_FOLD_METRICS.csv')
    assert len(af)==22 and af[af.arm.str.endswith('_E')].fold.tolist()==[1,2]
    assert af.proper_score_finite.all() and af.monotonicity_pass.all() and af.zero_support_count.sum()==0
    for _,r in ab[ab.metrics_available].iterrows():
        folds=[read(LOCAL/f'fold{i}'/(r.arm+'.json')) for i in range(1,6)]
        parts=[pd.read_parquet(LOCAL/f'fold{i}'/(r.arm+'.parquet')) for i in range(1,6)]
        summary=summarize(r.arm,folds,parts)
        for key in ['Q90_coverage','min_fold_coverage','gt4h_coverage','Q90_pinball','proper_interval_NLL']:
            assert np.isclose(summary[key],r[key],rtol=1e-12), (r.arm,key)
    for arm in primary.arm:
        folds=[read(LOCAL/f'fold{i}'/(arm+'.json')) for i in range(1,6)]
        parts=[pd.read_parquet(LOCAL/f'fold{i}'/(arm+'.parquet')) for i in range(1,6)]
        s=summarize(arm,folds,parts);r=comp[comp.arm.eq(arm)].iloc[0]
        for key in ['Q90_coverage','min_fold_coverage','max_fold_coverage','coverage_std','Q90_pinball','Q50_MAE','reservation_actual_GPUh',
                    'proper_interval_NLL','Q90_actual_ratio_median','Q90_actual_ratio_P90','short_job_reservation_inflation']:
            assert np.isclose(s[key],r[key],rtol=1e-12),key
        for key in ['eligible']+[f'gate_{x}' for x in 'ABCDEFGHI']:assert s[key]==r[key]
    eligibility=read(ROOT/'C1_ELIGIBILITY_AUDIT.json');allowed=primary[(primary.min_fold_coverage>=.8)&(primary.gt4h_coverage>=.8)]
    assert eligibility['C1_ROLLING14_EVALUATED']==bool(len(allowed))
    assert not verdict['STAGE_C_AUTHORIZED'] and verdict['SELECTED_STATE_SET']=='NONE'
    for key in ['TOTAL_RUNTIME_MODEL_VALIDATED','TOTAL_OVERALL_Q90_GATE_PASS','TOTAL_MIN_FOLD_GATE_PASS',
                'TOTAL_GT4H_GATE_PASS','C1_ROLLING14_EVALUATED','STAGE_C_AUTHORIZED','REMAINING_MODEL_RUN',
                'REMAINING_RUNTIME_MODEL_VALIDATED','V42_RESEARCH_RUNTIME_PROVIDER_READY','APRIL_USED_FOR_SELECTION',
                'MAY_PAYLOAD_OPENED','MAY_USED_FOR_SELECTION','MAY_USED_FOR_EVALUATION']:
        assert verdict[key] is False,key
    assert verdict['APRIL_STATUS']=='NOT_RUN_GATE_FAILED' and verdict['EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE'] is True
    assert verdict['DIAGNOSTIC_ANCHOR_RAW_POOLED_Q90_GATE_A_PASS'] is True
    assert bool(primary.set_index('arm').loc['EXPANDING_S4','gate_A'])
    for name in SKIPPED_CSV:
        f=pd.read_csv(ROOT/name);assert f.status.eq('NOT_RUN_GATE_FAILED').all() and not f.metrics_available.any()
    for name in SKIPPED_JSON:
        r=read(ROOT/name);assert r['status']=='NOT_RUN_GATE_FAILED' and not r['executed']
    assert list((ROOT/'RUNTIME_PROVIDER').iterdir())==[ROOT/'RUNTIME_PROVIDER/README.md']
    review=(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(x) for x in re.findall(r'(?m)^## (\d+)\.',review)]==list(range(1,42))
    request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    portion=request.split('41. REQUIRED STAGE-A ARTIFACTS',1)[1].split('45. REQUIRED FINAL',1)[0]
    required=set(re.findall(r'(?m)^([A-Z][A-Z0-9_]*\.(?:json|csv|md))\s*$',portion))
    required.update(['FINAL_REVIEW_KO.md','FINAL_VERDICT.json','TOTAL_MODEL_COMPARISON.csv','TOTAL_FOLD_METRICS.csv',
        'TOTAL_LONG_TAIL_METRICS.csv','CURRENT_STATE_CAUSALITY_AUDIT.json','CURRENT_STATE_REPLAY_AUDIT.json',
        'CURRENT_STATE_FEATURE_ABLATION.csv','SOURCE_MANIFEST.json','DELIVERY_MANIFEST.json','VERIFICATION.json'])
    for name in required-{'DELIVERY_MANIFEST.json','VERIFICATION.json'}:assert (ROOT/name).is_file(),name
    changes=subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO,text=True).splitlines()
    assert all(p.startswith('docs/runtime_vnext13_current_workload_state/') for p in changes)
    # Replay-equivalent rows fed through a saved research fold model also have
    # identical total predictions; this does not construct a final provider.
    piece=pd.read_parquet(LOCAL/'restart_part3.parquet').head(100).set_index('job_id')
    raw=pd.read_parquet(V9/'.local/PREAPRIL_SOURCE.parquet').set_index('job_id').loc[piece.index].reset_index()
    model=Hazard.load(ROOT/'FOLD_MODELS/fold1/EXPANDING_S4');pre=model.meta['preprocessing'];hashes=[]
    for feature in [features,piece]:
        par=model.parameters(matrix(raw,pre,feature,model.meta['columns']),threads=1)
        qq=np.column_stack([model.inverse_logsf(par,np.log1p(-p)) for p in [.5,.9]])
        hashes.append(hashlib.sha256(qq.tobytes()).hexdigest())
    assert hashes[0]==hashes[1]
    write('PREDICTION_REPLAY_AUDIT.json',dict(time=now(),PASS=True,N=100,hashes=hashes,scope='research fold component; not final provider'))
    verification=dict(time=now(),PASS=True,scope='Complete scientific negative-result delivery with user-authorized partial diagnostics, NOT model validation',
        prior_scientific_files_byte_identical=count,prior_manifests_byte_identical=len(old),same_fold_membership=True,
        preregistration_unchanged=True,stage_A_before_training=True,unit_test_output=unit.stdout+unit.stderr,
        fold_model_parity=parity,full_stream_replay=replay,independent_state_audit=read(ROOT/'INDEPENDENT_STATE_AUDIT.json'),
        pooled_metrics_recomputed=True,whole_stream_feature_semantics_verified=True,Stage_C_guard_verified=True,Korean_questions_answered=41,
        required_artifacts_checked=sorted(required),April_payload_evaluated=False,May_payload_opened=False,final_provider_created=False,
        EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE=True,completed_diagnostic_folds=22,unrun_diagnostic_folds=3,
        no_unrun_metrics_fabricated=True,completed_ablation_metrics_recomputed=True,
        execution_logs_byte_identical=True,local_evidence_files_verified=len(local_evidence['files']),
        user_final_flags_verified=True,raw_primary_gate_A_preserved=True)
    write('DELIVERY_VERIFICATION.json',verification)
    write('VERIFICATION.json',verification)
    source.update(final_time=now(),reused_code=[record(V8/'features8.py'),record(V9/'metrics9.py'),record(V10/'hazard10.py')],
        new_code=[record(p) for p in sorted(ROOT.glob('*.py'))],execution_environment=read(ROOT/'EXECUTION_ENVIRONMENT.json'),
        user_request=record(ROOT/'USER_REQUEST.txt'),materialized_features=record(LOCAL/'CURRENT_STATE_FEATURES.parquet'),
        event_schedule=record(LOCAL/'EVENT_SCHEDULE.npz'),projected_requests=record(LOCAL/'REQUESTS.parquet'))
    source.update(early_termination_instruction=record(ROOT/'EARLY_TERMINATION_INSTRUCTION.md'),
        early_termination_receipt=record(ROOT/'EARLY_TERMINATION_RECEIPT.json'),
        local_evidence_manifest=record(ROOT/'LOCAL_EVIDENCE_MANIFEST.json'))
    write('SOURCE_MANIFEST.json',source)
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(x in p.relative_to(ROOT).parts for x in ['.local','__pycache__']) or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scope='docs/runtime_vnext13_current_workload_state only',scientific_status='STOPPED_AFTER_STAGE_B',files=files))
    for r in read(ROOT/'DELIVERY_MANIFEST.json')['files']:assert sha(ROOT/r['relative'])==r['sha256']
    for name in required:assert (ROOT/name).is_file(),name
    print('V13_DELIVERY_PASS',count,'preserved;',len(files),'new;',sum(r['bytes'] for r in files),'bytes',flush=True)
if __name__=='__main__':main()
