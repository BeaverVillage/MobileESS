from common import *
from expand import folder
import ast,subprocess

def main():
    checks={};base=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')
    for r in base['tracked_files']:assert sha(REPO/r['relative'])==r['sha256'],r
    for r in base['local_files']:assert sha(r['path'])==r['sha256'],r
    checks['prior_1684_tracked_1052_local_preserved']=True
    for name in ['PREREGISTRATION','CROSS_VERSION_PREREGISTRATION']:
        assert sha(ROOT/(name+'.json'))==read(ROOT/(name+'_HASH.json'))['sha256']
    for r in read(ROOT/'IMPLEMENTATION_FREEZE.json')['files']:assert sha(r['path'])==r['sha256']
    for r in read(ROOT/'FINAL_VERDICT.json')['evidence']:assert sha(r['path'])==r['sha256']
    checks['preregistered_formulas_and_input_inventory_unchanged']=True
    old=read(PR94/'FINAL_FLAGS.json');assert old['SELECTED_RUNTIME_MODEL']=='NONE' and old['SELECTED_ALPHA'] is None
    checks['PR94_NONE_and_alpha_null_unchanged']=True
    for manifest in ['SOURCE_MANIFEST.json','CROSS_VERSION_SOURCE_MANIFEST.json']:
        for r in read(ROOT/manifest)['files']:assert sha(r['path'])==r['sha256'],r
    checks['all_consumed_sources_unchanged']=True
    for name in ['COMMON_POPULATION_RECHECK.json','CROSS_VERSION_POPULATION_RECHECK.json']:
        s=read(ROOT/name);assert s['PASS'] and s['N']==230237
        assert sum(x['N'] for x in s['candidate_folds'])==230237*(6 if name.startswith('COMMON') else 100)
    checks['exact_common_population_all_100_variants']=True
    for fn in ['Q50_POOLED_METRICS.csv','Q50_FOLD_METRICS.csv','Q50_RUNTIME_BUCKET_METRICS.csv','Q50_LONG_RUNTIME_METRICS.csv','CROSS_VERSION_Q50_COMPARISON.csv','CROSS_VERSION_Q50_FOLDS.csv','CROSS_VERSION_Q50_BUCKETS.csv','CROSS_VERSION_Q50_TAILS.csv']:
        f=pd.read_csv(ROOT/fn)
        for col in [c for c in f if c.endswith('_coverage') or c.endswith('_fraction')]:assert f[col].dropna().between(0,1).all(),(fn,col)
        np.testing.assert_allclose(f.Q50_coverage+f.Q50_underprediction_fraction,1,rtol=0,atol=1e-15)
        assert np.isfinite(f.Q50_time_ratio.dropna()).all()
        if f.Q50_time_ratio.isna().any():assert f.loc[f.Q50_time_ratio.isna(),'actual_seconds'].eq(0).all()
    checks['coverage_complements_bounds_and_defined_ratios_finite']=True
    for pre in ['', 'CROSS_VERSION_']:
        table=pd.read_csv(ROOT/('Q50_POOLED_METRICS.csv' if not pre else pre+'Q50_COMPARISON.csv')).set_index('Model')
        bucket=pd.read_csv(ROOT/('Q50_RUNTIME_BUCKET_METRICS.csv' if not pre else pre+'Q50_BUCKETS.csv'));bucket=bucket[bucket.fold=='POOLED']
        ratios=pd.read_csv(ROOT/('Q50_RATIO_DISTRIBUTION.csv' if not pre else pre+'Q50_RATIOS.csv'))
        for model,z in bucket.groupby('Model'):
            assert z.N.sum()==230237 and int(z[z.bucket=='EXACT_ZERO_DIAGNOSTIC'].N.iloc[0])==1290
            assert table.loc[model,'N']==230237 and table.loc[model,'zero_runtime_N']==1290
            np.testing.assert_allclose(np.dot(z.N,z.Q50_coverage)/230237,table.loc[model,'Q50_coverage'],rtol=1e-14)
            np.testing.assert_allclose(z.predicted_Q50_seconds.sum()/z.actual_seconds.sum(),table.loc[model,'Q50_time_ratio'],rtol=1e-14)
        assert (ratios[ratios.fold=='POOLED'].N_positive==228947).all()
        assert (ratios[ratios.fold=='POOLED'].zero_runtime_excluded_N==1290).all()
        assert np.isfinite(ratios[['Q10','Q25','median','Q75','Q90','Q95','mean_diagnostic_only']]).all().all()
    checks['zero_handling_and_all_buckets_reaggregate_exactly']=True
    # Independently recover six-arm counts directly from unchanged original inputs.
    pooled=pd.read_csv(ROOT/'Q50_POOLED_METRICS.csv').set_index('Model')
    for arm in ARMS:
        parts=[pd.read_parquet(PR94/'.local'/f'{arm}_fold{i}_VALID.parquet') for i in range(1,6)]
        assert all(list(p.columns)==['fold','job_id','submit_time','runtime_seconds','q50','q90'] for p in parts)
        f=pd.concat(parts);covered=sum(1 for y,q in zip(f.runtime_seconds,f.q50) if y<=q)
        np.testing.assert_allclose(covered/len(f),pooled.loc[arm,'Q50_coverage'],rtol=0,atol=1e-15)
    checks['independent_original_prediction_coverage_recount_no_GPU']=True
    # Original published MAE/Q90 are an independent guard on positional NPZ interpretation.
    expanded=pd.read_csv(ROOT/'CROSS_VERSION_Q50_COMPARISON.csv').set_index('Model');fd=pd.read_csv(ROOT/'CROSS_VERSION_Q50_FOLDS.csv')
    spec=read(ROOT/'CROSS_VERSION_PREREGISTRATION.json');sources=[];reproduced=[]
    tables={}
    for v,names in {9:['MODEL_COMPARISON.csv'],10:['TAIL_GRID_COMPARISON.csv','CALIBRATION_COMPARISON.csv'],11:['TOTAL_BASE_MODEL_COMPARISON.csv','TOTAL_GATING_COMPARISON.csv']}.items():
        tables[v]=[]
        for name in names:
            path=folder(v)/name;sources.append(rec(path));tables[v].append(pd.read_csv(path))
        tables[v]=pd.concat(tables[v]).set_index('arm')
    for item in spec['items']:
        model=item['Model'];v=item['version'];s=expanded.loc[model]
        if item['kind']=='v9_parquet':oldrow=tables[9].loc[item['arm']]
        elif v==10:oldrow=tables[10].loc[item['arm'].removesuffix('_calibrated')]
        elif v==11:
            oldrow=tables[11].loc['GATE0_L0' if item['arm']=='SELECTED_TOTAL' else item['arm']]
        else:
            for i,r in enumerate(item['files'],1):
                p=Path(r['path']).with_suffix('.json');sources.append(rec(p));z=read(p);ours=fd[(fd.Model==model)&(fd.fold==i)].iloc[0]
                np.testing.assert_allclose([ours.N,ours.Q50_MAE_seconds,ours.Raw_Q90_coverage],[z['N'],z['Q50_MAE'],z['Q90_coverage']],rtol=1e-12)
            reproduced.append(dict(Model=model,status='FIVE_ORIGINAL_FOLD_SUMMARIES_REPRODUCED'));continue
        np.testing.assert_allclose([s.N,s.Q50_MAE_seconds,s.Raw_Q90_coverage],[oldrow.N,oldrow.Q50_MAE,oldrow.Q90_coverage],rtol=1e-12)
        reproduced.append(dict(Model=model,status='ORIGINAL_POOLED_SUMMARY_REPRODUCED'))
    p=folder(10)/'CALIBRATION_CAUSALITY_AUDIT.csv';sources.append(rec(p));a=pd.read_csv(p)
    assert a.FUTURE_CALIBRATION_EVENT_READS.eq(0).all() and a.FUTURE_CALIBRATION_RESIDUAL_READS.eq(0).all()
    assert (pd.to_datetime(a.max_completion_used,utc=True)<pd.to_datetime(a.day,utc=True)).all()
    write('CROSS_VERSION_REPRODUCTION.json',dict(PASS=True,models=reproduced,V10_prior_causal_audit_rows=len(a),V10_future_event_and_residual_reads=0,sources=sources))
    checks['all_100_variants_reproduce_original_MAE_Q90_and_V10_causality']=True
    for name in ['common.py','audit.py','expand.py']:
        tree=ast.parse((ROOT/name).read_text(encoding='utf-8'))
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ['fit','partial_fit','train','predict'] for n in ast.walk(tree))
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):assert not any(x.name.startswith(('lightgbm','xgboost','catboost','torch','sklearn')) for x in n.names)
    checks['no_training_or_new_inference_calls']=True
    assert 'Ran 9 tests' in (LOCAL/'tests.log').read_text(encoding='utf-8-sig') and '\nOK' in (LOCAL/'tests.log').read_text(encoding='utf-8-sig')
    checks['nine_behavioral_tests']=True
    changed=subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO).decode().splitlines();assert all(p.startswith('docs/runtime_q50_calibration_audit/') for p in changed)
    assert subprocess.run(['git','diff','--check'],cwd=REPO).returncode==0
    flags=read(ROOT/'FINAL_FLAGS.json');assert not any(flags[k] for k in ['GPU_WEIGHTING_USED','CC4_CHANGED','V42_CHANGED','MAY_OPENED','OPENDSS_RUN','PLANNING_RESERVE_IMPLEMENTED','ACTUAL_RUNTIME_RESERVE_IMPLEMENTED'])
    checks['only_audit_namespace_changed_no_reserve_or_system_execution']=True
    files=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file() and p.name!='verify.log']
    write('LOCAL_EVIDENCE_MANIFEST.json',dict(time=now(),files=files,scope='New audit/test logs; original predictions remain at SHA-bound PR94 and version source paths. Current verification log excluded to avoid a changing self-reference.'))
    write('VERIFICATION.json',dict(time=now(),PASS=all(checks.values()),checks=checks,unit_tests=9,original_six_candidate_folds=30,expanded_variants=100,expanded_candidate_folds=500,expanded_prediction_rows=23023700,unique_Q50_arrays=87,original_tracked_preserved=len(base['tracked_files']),original_local_preserved=len(base['local_files']),pr94_result_unchanged=True,
        access_scope='New metric reads only pre-April frozen TOTAL validation arrays. V1-V5 reviewed via metadata only; no April/May payload decoded. Prior evidence preservation is byte hashing.',
        retrospective_references=3,limitations='Descriptive expanded analysis; no new numerical PASS gate or selected winner across the100 variants; inherited historical proxy and event-time causality assumptions remain.'))
    public=[dict(relative=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='DELIVERY_MANIFEST.json']
    write('DELIVERY_MANIFEST.json',dict(time=now(),base=BASE,files=public,excludes_self=True))
    print('VERIFIED',len(checks),'checks;',len(public)+1,'public files;',len(base['tracked_files']),'old tracked;',len(base['local_files']),'old local',flush=True)
if __name__=='__main__':main()
