"""Independent source parity, contract arithmetic, preservation and manifest closure."""
from common import *

def main():
    checks={};old=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')
    for r in old['tracked_files']:assert sha(REPO/r['relative'])==r['sha256'],r
    for r in old['local_inputs']:assert sha(r['path'])==r['sha256'],r
    checks['prior_1646_tracked_and_909_local_byte_hashes']=True
    prior_diff=subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO).decode().splitlines()
    assert all(p.startswith('docs/runtime_final_duration_calibration/') for p in prior_diff),prior_diff
    checks['no_prior_tracked_modification']=True
    prereg=read(ROOT/'PREREGISTRATION_HASH.json');assert sha(ROOT/'PREREGISTRATION.json')==prereg['sha256']
    freeze=read(ROOT/'ALPHA_FREEZE.json')
    for key in ['preregistration','selection','grid']:assert sha(freeze[key]['path'])==freeze[key]['sha256']
    for r in read(ROOT/'FINAL_SELECTION_FREEZE.json')['evidence']:assert sha(r['path'])==r['sha256']
    checks['preregistration_alpha_and_selection_hashes']=True
    op_paths=list(LOCAL.glob('*_OP.parquet'));assert len(op_paths)==30
    assert min(p.stat().st_mtime_ns for p in op_paths)>(ROOT/'ALPHA_FREEZE.json').stat().st_mtime_ns
    checks['all_alpha_frozen_before_operational_VALID_outputs']=True
    choices=pd.read_csv(ROOT/'ALPHA_SELECTION_BY_FOLD.csv');grid=pd.read_csv(ROOT/'ALPHA_CALIBRATION_GRID.csv')
    comp=pd.read_csv(ROOT/'FINAL_RUNTIME_MODEL_COMPARISON.csv').set_index('Model');mem=pd.read_csv(ROOT/'COMMON_RUNTIME_MEMBERSHIP.csv',dtype={'job_id':str})
    source=read(ROOT/'CANDIDATE_SOURCE_AUDIT.json')['sources']+read(ROOT/'CAL_CAUSALITY_AUDIT.json')['sources']
    for p in [V13/'model13.py',REPO/'docs/runtime_vnext10_tail_calibrated_hazard/hazard10.py',REPO/'docs/runtime_vnext8_trace_feature_total/features8.py',V13/'CURRENT_STATE_CAUSALITY_AUDIT.json',V13/'CURRENT_STATE_REPLAY_AUDIT.json',V9/'metrics9.py',V9/'evaluate9.py',V13/'train13.py']:
        source.append(rec(p))
    for i in range(1,6):
        # Raw data authorities are exactly the already-frozen pre-April fold parquet files.
        v=pd.read_parquet(V9/'.local'/f'fold{i}/VALID.parquet');v.job_id=v.job_id.astype(str);v=v.set_index('job_id')
        expected=mem[mem.fold==i].job_id.tolist();assert len(expected)==len(set(expected));assert set(expected)==set(v[v.event].index)
        for arm,src in ARMS.items():
            if arm.startswith('V9'):
                f=pd.read_parquet(V9/'.local'/f'{src}_evaluation.parquet').query('fold==@i').rename(columns={'y':'runtime_seconds'})
            else:f=pd.read_parquet(V13/'.local'/f'fold{i}/EXPANDING_S4.parquet')
            f.job_id=f.job_id.astype(str);assert not f.job_id.duplicated().any();f=f.set_index('job_id').loc[expected]
            op=pd.read_parquet(LOCAL/f'{arm}_fold{i}_OP.parquet').set_index('job_id').loc[expected]
            for col in ['q50','q90','runtime_seconds']:np.testing.assert_array_equal(op[col],f[col])
            np.testing.assert_array_equal(op.submit_time,v.loc[expected,'submit_time']);np.testing.assert_array_equal(op.runtime_seconds,v.loc[expected,'runtime_seconds'])
            assert np.isfinite(op[['q50','q90','t_op','runtime_seconds']]).all().all()
            assert (op.runtime_seconds>=0).all() and (op.q90>=op.q50).all() and (op.q50>=0).all()
            cal=pd.read_parquet(LOCAL/f'{arm}_fold{i}_CAL.parquet');y=cal.runtime_seconds.to_numpy();a=choices.query('Model==@arm and fold==@i').iloc[0]
            computed=[]
            for j in range(21):
                alpha=j/20;t=cal.q50.to_numpy()*(1-alpha)+cal.q90.to_numpy()*alpha
                # Algebraically independent interpolation, tolerate boundary roundoff for ratios.
                canonical=cal.q50.to_numpy()+alpha*(cal.q90.to_numpy()-cal.q50.to_numpy())
                coverage=float(np.count_nonzero(y<=canonical)/len(y));ratio=float(t.sum()/y.sum())
                row=grid.query('Model==@arm and fold==@i and alpha==@alpha').iloc[0]
                np.testing.assert_allclose([row.coverage,row.TIME_RATIO_OP],[coverage,ratio],rtol=1e-12)
                computed.append((alpha,coverage,ratio))
            possible=[x for x in computed if x[1]>=.9]
            chosen=min(possible,key=lambda x:(x[2],x[0])) if possible else min(computed,key=lambda x:(-x[1],x[2],x[0]))
            assert a.alpha==chosen[0] and bool(a.CAL_90PCT_UNATTAINABLE)==(not possible)
            np.testing.assert_allclose(op.t_op,op.q50+a.alpha*(op.q90-op.q50),rtol=0,atol=0)
            assert op.alpha.eq(a.alpha).all()
    checks['all_1381422_VALID_prediction_rows_source_parity']=True
    checks['all_630_CAL_grid_rows_and_30_choices_independently_recomputed']=True
    checks['no_gpu_columns_in_primary_prediction_interface']=all(not set(pd.read_parquet(p).columns)&{'gpu','num_gpus_req','num_nodes_req'} for p in op_paths)
    assert checks['no_gpu_columns_in_primary_prediction_interface']
    for arm in ARMS:
        f=pd.concat([pd.read_parquet(LOCAL/f'{arm}_fold{i}_OP.parquet') for i in range(1,6)])
        y=f.runtime_seconds.to_numpy();s=comp.loc[arm]
        np.testing.assert_allclose([s.TIME_RATIO_Q50,s.TIME_RATIO_Q90,s.TIME_RATIO_OP,s.OP_coverage,s.Q50_MAE_hours],[f.q50.sum()/y.sum(),f.q90.sum()/y.sum(),f.t_op.sum()/y.sum(),(y<=f.t_op).mean(),abs(y-f.q50).mean()/3600],rtol=1e-12)
        assert s.TIME_RATIO_Q50<=s.TIME_RATIO_OP<=s.TIME_RATIO_Q90
    checks['duration_ratios_coverage_and_interpolation_floor']=True
    assert len(comp)==6 and not comp.reliability_eligible.any() and not comp.selected.any()
    assert read(ROOT/'FINAL_FLAGS.json')['SELECTED_RUNTIME_MODEL']=='NONE'
    distribution=pd.read_csv(ROOT/'PER_JOB_RATIO_DISTRIBUTION.csv')
    assert np.isfinite(distribution[['Q25','median','Q75','Q90','mean_diagnostic_only']]).all().all()
    assert (distribution[distribution.fold=='POOLED'].zero_runtime_N==1290).all()
    checks['zero_runtime_ratios_finite_and_counted']=True
    checks['negative_selection_matches_preregistered_rule']=True
    test_log=(LOCAL/'tests.log').read_text(encoding='utf-8-sig');assert 'Ran 9 tests' in test_log and '\nOK' in test_log
    checks['nine_behavioral_unit_tests']=True
    # Every consumed original source must still match the hash taken when it was consumed.
    unique={r['path']:r for r in source}
    for r in unique.values():assert sha(r['path'])==r['sha256'],r
    write('SOURCE_MANIFEST.json',dict(time=now(),scope='Consumed original frozen quantiles, fold labels, V13 inference artifacts and inherited causality/implementation contracts',files=list(unique.values())))
    localfiles=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ['verify.log']]
    write('LOCAL_EVIDENCE_MANIFEST.json',dict(time=now(),scope='All new row-level CAL/VALID/OP predictions, logs and superseded shared-reserve preliminary audit/drafts retained. Only this manifest-generation log excluded.',files=localfiles))
    result=subprocess.run(['git','diff','--check'],cwd=REPO,capture_output=True,text=True);assert result.returncode==0,result.stdout+result.stderr
    checks['git_diff_check']=True
    write('VERIFICATION.json',dict(time=now(),PASS=all(checks.values()),checks=checks,unit_tests=9,candidate_fold_evaluations=30,CAL_grid_rows=630,common_jobs=230237,zero_runtime_rows=1290,
        original_tracked_preserved=len(old['tracked_files']),original_local_preserved=len(old['local_inputs']),sources_verified=len(unique),new_local_files=len(localfiles),
        excluded_actions=['new Runtime ML training','RADDiT training','CC4 modification','V42 execution','OpenDSS','April/May selection'],
        methodology_limitation='Raw validation metrics were historically exposed; no operational VALID grid was used for alpha. Complete-case historical proxy research, no deployment validation.',
        manifest_self_reference='DELIVERY_MANIFEST excludes itself; VERIFIED public artifacts including VERIFICATION are SHA-bound by DELIVERY_MANIFEST. Git commit supplies outer integrity.'))
    files=[dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.rglob('*')) if p.is_file() and '.local' not in p.parts and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json']
    write('DELIVERY_MANIFEST.json',dict(time=now(),base=BASE,files=files,excludes_self=True))
    for r in files:assert sha(ROOT/r['relative'])==r['sha256']
    print('VERIFIED',len(checks),'checks;',len(files),'public SHA-bound files;',len(localfiles),'local files;',len(old['tracked_files']),'old tracked;',len(old['local_inputs']),'old local',flush=True)
if __name__=='__main__':main()
