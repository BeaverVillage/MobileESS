"""Independent delivery checks; scientific validity is separate from model PASS."""
from common12 import *
from model12 import Hazard,matrix
from train12 import summarize
import subprocess,re

def main():
    verdict=read(ROOT/'FINAL_VERDICT.json');assert verdict['status']=='STOPPED_AFTER_STAGE_B'
    old=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')['prior'];count=0
    for group in old:
        p=Path(group['manifest']['path']);assert sha(p)==group['manifest']['sha256']
        for r in read(p)['files']:assert sha(p.parent/r['relative'])==r['sha256'];count+=1
    for name in ['PREREGISTRATION.json','REGIME_FEATURE_CONTRACT_FREEZE.json','REGIME_SUPPORT_FREEZE.json','TOTAL_MODEL_SELECTION_FREEZE.json']:
        for r in read(ROOT/name)['files']:assert sha(r['path'])==r['sha256'],str(r['path'])
    source=read(ROOT/'SOURCE_MANIFEST.json')
    for r in source['roles']+[source['source']]:assert sha(r['path'])==r['sha256']
    for i in range(1,6):
        contract=read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]
        for role in ['TRAIN','CAL','VALID']:assert ids(data(i,role))==contract['membership'][role]
    assert pd.Timestamp(read(ROOT/'PREREGISTRATION.json')['time'])<pd.Timestamp(read(ROOT/'STAGE_A_VERDICT.json')['time'])<pd.Timestamp(read(ROOT/'TRAINING_STARTED.json')['time'])
    audit=read(ROOT/'REGIME_CAUSALITY_AUDIT.json');assert audit['PASS']
    for k in ['FUTURE_JOB_READS','FUTURE_END_READS','CURRENT_JOB_OUTCOME_READS','FUTURE_CALIBRATION_READS']:assert audit[k]==0
    assert sha(audit['feature_file']['path'])==audit['feature_file']['sha256']
    replay=read(ROOT/'REGIME_STATE_REPLAY_AUDIT.json')
    assert replay['chronological_hash']==replay['chunked_hash']==replay['restarted_process_hash']
    full=read(ROOT/'FULL_STREAM_REPLAY_AUDIT.json');assert full['PASS']
    assert full['chronological_materialization_hash']==full['chunked_restarted_hash']==audit['feature_values_sha256']
    tests=[]
    for name in ['test_regime12.py','test_contracts12.py']:
        r=subprocess.run([sys.executable,'-B',str(ROOT/name)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        assert r.returncode==0,r.stderr
        tests.append(dict(test=name,PASS=True,output=r.stdout+r.stderr))
    guard=subprocess.run([sys.executable,'-B',str(ROOT/'stage_gate12.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert guard.returncode!=0 and 'NOT_RUN_GATE_FAILED' in guard.stderr
    regime=pd.read_parquet(LOCAL/'REGIME_FEATURES.parquet').set_index('job_id');parity=[]
    for path in sorted((ROOT/'FOLD_MODELS').glob('fold*/*/model.json')):
        i=int(path.parent.parent.name[4:]);name=path.parent.name
        m=Hazard.load(path.parent);pre=m.meta['preprocessing'];f=data(i,'VALID').head(100)
        cols=m.meta['columns'];x=matrix(f,pre,regime,cols);par=m.parameters(x,threads=1)
        q=np.column_stack([m.inverse_logsf(par,np.log1p(-a)) for a in [.5,.9]])
        saved=np.load(LOCAL/f'fold{i}'/(name+'_quantiles.npz'))['q'][:100]
        assert np.array_equal(q,saved)
        if 'reused_equivalent_arm' in m.meta:
            equivalent=m.meta['reused_equivalent_arm']
            assert sha(path.parent/'hazard.txt')==m.meta['equivalent_source_booster']['sha256']
            assert np.array_equal(np.load(LOCAL/f'fold{i}'/(name+'_quantiles.npz'))['q'],
                                  np.load(LOCAL/f'fold{i}'/(equivalent+'_quantiles.npz'))['q'])
        # Current outcomes and date identity cannot enter the static matrix.
        altered=f.copy();altered['runtime_seconds']=1e15;altered['end_time']=pd.Timestamp('2099-01-01T00Z');altered['state']='FUTURE'
        xx=matrix(altered,pre,regime,cols);pd.testing.assert_frame_equal(x,xx,check_exact=True)
        assert not any(c in cols for c in ['submit_time','end_time','start_time','job_id','runtime_seconds','day_of_week','submit_hour'])
        parity.append(dict(fold=i,arm=name,N=100,predictions_bit_identical=True,current_outcome_invariance=True,model=record(path),booster=record(path.parent/'hazard.txt')))
    assert len(parity)==40
    ablation_folds=pd.read_csv(ROOT/'ABLATION_FOLD_METRICS.csv')
    assert len(ablation_folds)==20 and ablation_folds.proper_score_finite.all()
    assert ablation_folds.monotonicity_pass.all() and ablation_folds.zero_support_count.sum()==0
    # Feature replay equivalence also implies identical model outputs; exercise
    # that composition with one saved fold component, never a final provider.
    from regime12 import ReplayState,materialize
    from features8 import engineer
    state=ReplayState.load(LOCAL/'replay_state')
    qrows=pd.read_parquet(LOCAL/'replay_queries.parquet')
    replay_features=state.predict(qrows)
    fresh_process_features=pd.read_parquet(LOCAL/'restarted.parquet')
    original_source=pd.read_parquet(V9/'.local/PREAPRIL_SOURCE.parquet').set_index('job_id')
    raw=original_source.loc[qrows.job_id].reset_index()
    component=Hazard.load(ROOT/'FOLD_MODELS/fold1/EXPANDING_R2')
    static=engineer(raw,component.meta['preprocessing']['categorical_mappings'])[component.meta['preprocessing']['columns']]
    hashes=[]
    for features in [replay_features,fresh_process_features]:
        x=pd.concat([static.reset_index(drop=True),features],axis=1)[component.meta['columns']]
        par=component.parameters(x,threads=1)
        quantiles=np.column_stack([component.inverse_logsf(par,np.log1p(-a)) for a in [.5,.9]])
        hashes.append(hashlib.sha256(quantiles.tobytes()).hexdigest())
    assert hashes[0]==hashes[1]
    write('PREDICTION_REPLAY_AUDIT.json',dict(PASS=True,prediction_hashes=hashes,N=len(raw),
        scope='Numerical replay equivalence on saved research fold component; not causal historical evaluation or remaining training'))
    comp=pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv');assert len(comp)==5 and not comp.eligible.any()
    assert comp.proper_score_finite.all() and comp.monotonicity_pass.all() and comp.zero_support_count.sum()==0
    # Recompute pooled scores and gates from saved individual predictions.
    for arm in comp.arm:
        rows=[read(LOCAL/f'fold{i}'/(arm+'.json')) for i in range(1,6)]
        parts=[pd.read_parquet(LOCAL/f'fold{i}'/(arm+'.parquet')) for i in range(1,6)]
        s=summarize(arm,rows,parts);r=comp[comp.arm.eq(arm)].iloc[0]
        for key in ['Q90_coverage','min_fold_coverage','Q90_pinball','reservation_actual_GPUh','proper_interval_NLL']:
            assert np.isclose(s[key],r[key],rtol=1e-12)
        for key in ['eligible']+[f'gate_{x}' for x in 'ABCDEFGHI']:assert s[key]==r[key]
    assert verdict['SELECTED_REGIME_MODEL']=='NONE' and not verdict['STAGE_C_AUTHORIZED']
    assert not (ROOT/'RUNTIME_PROVIDER/provider.py').exists()
    for name in ['PREAPRIL_TOTAL_QUEUE_REPLAY.csv','REMAINING_MODEL_COMPARISON.csv','REMAINING_FOLD_METRICS.csv',
                 'REMAINING_ELAPSED_STRATA.csv','REMAINING_LONG_RUNNING_METRICS.csv','PREAPRIL_CAUSAL_STRESS_REPLAY.csv',
                 'APRIL_EXPOSED_TOTAL_METRICS.csv','APRIL_EXPOSED_REMAINING_METRICS.csv','APRIL2_EXPOSED_QUEUE_REGRESSION.csv']:
        f=pd.read_csv(ROOT/name);assert f.status.eq('NOT_RUN_GATE_FAILED').all() and not f.metrics_available.any()
    review=(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(x) for x in re.findall(r'(?m)^## (\d+)\.',review)]==list(range(1,38))
    request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    portion=request.split('38. REQUIRED ARTIFACTS',1)[1].split('42. REQUIRED FINAL',1)[0]
    required=set(re.findall(r'(?m)^([A-Z][A-Z0-9_]*\.(?:json|csv|md))\s*$',portion))
    for name in required-{'DELIVERY_MANIFEST.json'}:assert (ROOT/name).is_file(),name
    changes=subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO,text=True).splitlines()
    assert all(p.startswith('docs/runtime_vnext12_causal_regime_runtime/') for p in changes)
    write('DELIVERY_VERIFICATION.json',dict(time=now(),PASS=True,scope='Integrity and complete negative-result delivery, NOT model validation',
        prior_scientific_files_byte_identical=count,prior_manifests_byte_identical=len(old),same_fold_membership=True,
        preregistration_unchanged=True,stage_A_before_training=True,unit_tests=tests,fold_model_parity=parity,
        full_stream_restarted_replay=full,
        pooled_metrics_recomputed=True,Stage_C_guard_verified=True,Korean_questions_answered=37,
        April_payload_evaluated=False,May_payload_opened=False,final_provider_created=False,required_artifacts_checked=sorted(required)))
    source.update(time_final=now(),reused_code=[record(V8/'features8.py'),record(V10/'hazard10.py'),record(V9/'metrics9.py')],
                  new_code=[record(p) for p in sorted(ROOT.glob('*.py'))],execution_environment=read(ROOT/'EXECUTION_ENVIRONMENT.json'),
                  user_request=record(ROOT/'USER_REQUEST.txt'),local_materialized_features=record(LOCAL/'REGIME_FEATURES.parquet'))
    write('SOURCE_MANIFEST.json',source)
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(x in p.relative_to(ROOT).parts for x in ['.local','__pycache__']) or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scope='docs/runtime_vnext12_causal_regime_runtime only',scientific_status='STOPPED_AFTER_STAGE_B',files=files))
    print('V12_DELIVERY_PASS',count,'preserved files;',len(files),'new files;',sum(r['bytes'] for r in files),'bytes',flush=True)

if __name__=='__main__':main()
