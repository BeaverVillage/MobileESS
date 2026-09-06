import ast
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from dayahead.v40s5.common import *

@pytest.fixture(scope='module')
def lib():return library()

def test_exact_lineage_and_isolation():
    a=read('GIT_LINEAGE_AUDIT');s=read('START_STATE')
    assert a['S4_scientific']==SCI4 and a['S4_receipt']==BASE and a['S3_scientific']==SCI3 and a['S3_receipt']==REC3
    assert ancestor(SCI3,REC3) and ancestor(REC3,SCI4) and ancestor(SCI4,BASE)
    assert s['branch']=='codex/v40s5-uncertainty-aware-direct-runtime'
    assert Path(s['worktree']).resolve()==ROOT and ROOT!=S4ROOT
    assert s['isolated'] and s['S4_worktree_clean']

def test_original_s4_and_s3_immutable():
    a=read('S4_REFERENCE_FREEZE');assert a['classification']=='V40S4_PROXY_BODY_RUNTIME_INSUFFICIENT'
    for k in ['selected_track','selected_u','selected_body','selected_classifier','selected_eta','selected_robust_policy']:assert a[k]=='NONE'
    assert a['optimizer_integration']=='NO'
    for p,h in a['owned_SHA256'].items():assert file_sha(ROOT/p)==h and file_sha(S4ROOT/p)==h
    assert len(a['owned_SHA256'])==106
    b=tree(BASE);c=tree('HEAD')
    assert all(c[p]==v for p,v in b.items())
    assert len(read('PROTECTED_SCOPE_START')['S3_preserved_paths'])==109

def test_source_counts_recomputed_independently(lib):
    # Source hash identifies a previously verified pre-Apr24 file. No sealed data read.
    assert file_sha(SOURCE)==SOURCE_SHA
    f=pd.read_parquet(SOURCE,columns=['job_id','start_time','end_time','runtime_seconds'])
    f.end_time=pd.to_datetime(f.end_time,utc=True);f.start_time=pd.to_datetime(f.start_time,utc=True)
    assert len(f)==73504 and f.job_id.nunique()==73504
    assert (f.runtime_seconds>0).sum()==72292 and (f.runtime_seconds==0).sum()==1212
    assert (f.runtime_seconds<0).sum()==0
    np.testing.assert_array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    eligible=f[(f.end_time<CUTOFF)&(f.runtime_seconds>0)]
    assert set(eligible.job_id.astype(str))==set(lib.job_uid)
    assert (f.end_time<CUTOFF).sum()==425 and len(lib)==421

def test_proof_mature_unique_exact_runtime(lib):
    p=pd.read_parquet(OUT/'V40S5_TRAINING_LABEL_AVAILABILITY_PROOF.parquet')
    assert not p.job_uid.duplicated().any() and p.label_available_before_cutoff.all()
    assert (p.end_time<CUTOFF).all() and (p.model_fit_cutoff==CUTOFF).all()
    assert p.source_row_identity.str.startswith(SOURCE_SHA+':row:').all()
    np.testing.assert_array_equal(p.runtime_sec,(p.end_time-p.start_time).dt.total_seconds())
    assert np.isfinite(p.runtime_sec).all() and (p.runtime_sec>0).all()
    assert set(p.job_uid)==set(lib.job_uid)

def test_training_separate_from_exact_s4_panel(lib):
    assert file_sha(S4/'V40S4_PENDING_ISSUE_PANEL.parquet')==PANEL_SHA
    f=pd.read_parquet(S4/'V40S4_PENDING_ISSUE_PANEL.parquet',columns=['job_id','job_issue_uid','role'])
    assert not set(lib.job_uid)&set(f.job_id.astype(str))
    assert f.groupby('role').size().to_dict()==EXPECTED
    for r,d in f.groupby('role'):assert ids(d.job_issue_uid)==read('PANEL_IDENTITY_AUDIT')['blocks'][r]['ID_SHA256']

def test_preprocessing_exact_train_only(lib):
    p=read('PREPROCESSING_CONTRACT');assert p['target_encoding'] is False
    for track in ['P','PW']:
        desc=p['final_'+track]
        assert desc['fit_ids_sha256']==ids(lib.job_uid) and desc['fit_N']==421
        assert desc['columns']==fields(track)
        for c in CAT:assert desc['vocab'][c]==['__UNKNOWN__']+sorted(set(categories(lib[c]))-{'__UNKNOWN__'})
        for c,v in desc['medians'].items():assert v==numeric(lib[c],c).median()

def test_historical_split_and_tuning(lib):
    a,b,t=temporal_split(lib);d=read('HISTORICAL_INTERNAL_SPLIT')
    assert len(a)==332 and len(b)==89 and len(a)+len(b)==len(lib)
    assert a.end_time.max()<b.end_time.min() and not set(a.job_uid)&set(b.job_uid)
    assert d['HIST_FIT_ids']==ids(a.job_uid) and d['HIST_TUNE_ids']==ids(b.job_uid)
    results=read('HYPERPARAMETER_FREEZE')['results'];assert len(results)==3
    for v in results:
        expected=np.mean([v[f'Q{int(q*100)}_pinball'] for q in QUANTILES])/b.runtime_seconds.mean()
        assert v['mean_normalized_pinball']==pytest.approx(expected)
    winner=min(results,key=lambda r:(r['mean_normalized_pinball'],r['Q99_pinball'],r['raw_crossing_fraction'],list(CONFIGS).index(r['config'])))
    assert winner['config']==read('HYPERPARAMETER_FREEZE')['selected']

def test_all_fits_preregistered_and_historical():
    pr=read('PREREGISTRATION');assert pr['configs']==CONFIGS and pr['fixed_parameters']==FIXED
    commit=guard_receipt('PREREGISTRATION_COMMIT_RECEIPT')
    ct=pd.Timestamp(git('show','-s','--format=%cI',commit))
    event=pd.Timestamp(read('EXPOSURE_EVENT')['timestamp'])
    for fit in read('COMPUTE_LEDGER')['fits']:
        assert fit['config'] in CONFIGS and fit['alpha'] in [None,*QUANTILES]
        assert pd.Timestamp(fit['max_fit_end'])<CUTOFF
        assert ct<=pd.Timestamp(fit['timestamp'])<event
        assert fit['SHA256']==file_sha(OUT/'models'/f"{fit['name']}.txt")
    assert len([v for v in read('COMPUTE_LEDGER')['fits'] if v['name'].startswith('TUNE_')])==12

@pytest.mark.parametrize('track',['P','PW','REPEAT_P'])
def test_residual_oof_row_level_evidence(track,lib):
    o=pd.read_parquet(OUT/f'V40S5_{track}_RESIDUAL_OOF.parquet')
    assert not o.job_uid.duplicated().any() and (o.fit_max_end<o.end_time).all()
    assert np.isfinite(o.Q50_OOF).all() and (o.Q50_OOF>=0).all()
    np.testing.assert_array_equal(o.r2,(o.runtime_seconds-o.Q50_OOF)**2)
    fold_pairs={k:(a,b) for k,a,b in temporal_folds(lib)}
    from lightgbm import Booster
    from dayahead.v40s5.experiment import load_pre
    for k,d in o.groupby('fold'):
        a,b=fold_pairs[k];assert not set(a.job_uid)&set(d.job_uid)
        assert set(d.job_uid)==set(b.job_uid) and d.fit_ids_sha256.eq(ids(a.job_uid)).all()
        pre=load_pre(f'{track}_OOF{k}');assert pre.fit_ids_sha256==ids(a.job_uid)
        model=Booster(model_file=str(OUT/'models'/f'{track}_OOF{k}_Q50.txt'))
        v=lib.set_index('job_uid').loc[d.job_uid].reset_index()
        np.testing.assert_array_equal(d.Q50_OOF,np.maximum(model.predict(pre.transform(v),num_threads=1),0))

@pytest.mark.parametrize('track',['P','PW'])
@pytest.mark.parametrize('role',ROLES)
def test_saved_predictions_exact_metrics_and_comparators(track,role):
    original=panel(role);d=pd.read_parquet(OUT/f'V40S5_{track}_{role}_PREDICTIONS.parquet')
    assert list(d.job_issue_uid)==list(original.job_issue_uid)
    for c in ['runtime_seconds','reference_safe_sec','requested_seconds','num_gpus_req']:
        np.testing.assert_array_equal(d[c],original[c])
    raw=d[[f'raw_Q{int(q*100)}' for q in QUANTILES]].to_numpy();q=d[[f'Q{int(a*100)}' for a in QUANTILES]].to_numpy()
    assert np.isfinite(raw).all() and np.isfinite(q).all() and (q>=0).all()
    np.testing.assert_array_equal(q,repair(raw))
    np.testing.assert_array_equal(d.sigma,np.sqrt(np.maximum(d.predicted_r2,0)))
    assert np.isfinite(d.sigma).all() and (d.sigma>=0).all()
    vals=candidates(d,q,d.sigma)
    report=read(f'{track}_{role}_REPORT')
    for c,p in vals.items():
        np.testing.assert_array_equal(d[c],p)
        np.testing.assert_array_equal(d[c+'_slots'],np.ceil(p/900))
        y=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy();under=np.maximum(y-p,0);over=np.maximum(p-y,0)
        m=report['results'][c]
        assert m['coverage']==np.mean(y<=p) and m['GPU_coverage']==np.sum(g*(y<=p))/g.sum()
        assert m['under_sec']==under.sum() and m['GPU_under_sec']==pytest.approx(np.sum(g*under))
        assert m['over_sec']==over.sum() and m['GPU_over_h']==pytest.approx(np.sum(g*over)/3600)
        for day,dd in d.assign(pred=p).groupby('issue_day'):
            saved=report['daily'][c][day];assert saved['major_day']==(len(dd)>=100)
            assert saved['coverage']==np.mean(dd.runtime_seconds<=dd.pred)
            if len(dd)>=100:
                assert saved['daily_gate_pass']==(saved['coverage']>=.88 and saved['GPU_coverage']>=.88)
    assert len(d[d.runtime_seconds>d.requested_seconds])==len(original[original.runtime_seconds>original.requested_seconds])

def test_selection_and_exposed_gates_independently():
    sel=read('SELECTION_FREEZE');assert sel['selection_roles']==['DEVELOPMENT','CALIBRATION'] and not sel['EXPOSED_scored']
    eligible=[]
    for c in CANDIDATES[2:]:
        passes=[]
        for r in ROLES[1:]:
            d=read(f'P_{r}_REPORT');m=d['results'][c];daily=d['daily'][c]
            safe=m['coverage']>=.9 and m['GPU_coverage']>=.9 and m['GPU_under_sec']<d['results'][CANDIDATES[0]]['GPU_under_sec']
            safe=safe and all(v['coverage']>=.88 and v['GPU_coverage']>=.88 for v in daily.values() if v['N']>=100)
            efficiency=m['GPU_over_h']<d['results'][CANDIDATES[1]]['GPU_over_h']
            assert d['gates'][c]['safety']==safe and d['gates'][c]['efficiency']==efficiency
            if r!='EXPOSED_EVALUATION':passes.append(safe and efficiency)
        if all(passes):eligible.append(c)
    assert not eligible and sel['selected_model'] is None
    assert read('EXPOSED_RESULTS')['classification']=='V40S5_DIRECT_RUNTIME_SAFETY_FAIL'

def test_selection_commit_precedes_exposure_and_no_model_changes():
    s=guard_receipt('SELECTION_FREEZE_COMMIT_RECEIPT');p=guard_receipt('PREEXPOSED_COMMIT_RECEIPT')
    assert ancestor(s,p)
    assert pd.Timestamp(git('show','-s','--format=%cI',p))<=pd.Timestamp(read('EXPOSURE_EVENT')['timestamp'])
    assert read('EXPOSED_RESULTS')['no_reselection'] and read('EXPOSED_RESULTS')['no_refit']

def test_pw_and_unique_job_are_diagnostic_only():
    w=read('WALLTIME_DEPENDENCE_ANALYSIS');assert w['removed_features']==['requested_seconds'] and not w['winner_reselection']
    assert w['selected_formula'] is None
    u=read('UNIQUE_JOB_SENSITIVITY');assert u['diagnostic_only'] and u['no_reselection']
    for role in ROLES:
        f=panel(role);assert u['results']['P'][role]['N']==f.job_uid.nunique()

def test_firewalls_and_current_holds():
    m=read('MAY_FIREWALL');assert m['shadow']=='SEALED'
    for k,v in m.items():
        if k.startswith('May_') or k=='shadow_scientific_rows':assert v==0
    c=read('COMPUTE_LEDGER')
    for k in ['optimizer_calls','Gurobi_calls','OpenDSS_calls','Fresh_calls']:assert c[k]==0
    assert c['holds']==HOLDS and read('FINAL_DECISION')['holds']==HOLDS
    a=read('RUNTIME_ADAPTER_PROPOSAL');assert a['proposal_only'] and not a['optimizer_use_allowed'] and a['recommended_rows']==[]
    assert read('FINAL_DECISION')['FURTHER_RUNTIME_MODEL_WORK']=='DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA'

def test_reproducibility_actual_independent_models():
    a=read('REPRODUCIBILITY_AUDIT');assert a['status']=='PASS' and a['independent_full_P_pipeline_rebuilds']==1
    assert a['OOF_evidence_exact_equal'] and not a['better_repeat_selected']
    for v in a['compare'].values():assert v['exact_equal'] and v['max_difference']==0 and v['mean_difference']==0
    for name in ['Q50','Q90','Q95','Q99','RESIDUAL']:
        assert file_sha(OUT/'models'/f'P_{name}.txt')==file_sha(OUT/'models'/f'REPEAT_P_{name}.txt')

def test_scientific_sources_have_no_operational_imports():
    for name in ['common.py','experiment.py','diagnostics.py','prepare.py']:
        t=ast.parse((ROOT/'dayahead/v40s5'/name).read_text())
        imports=[]
        for n in ast.walk(t):
            if isinstance(n,ast.Import):imports.extend(v.name for v in n.names)
            if isinstance(n,ast.ImportFrom):imports.append(n.module or '')
        assert not any(any(x in s.lower() for x in ['gurobi','opendss','v37','v40a','xgboost','survival']) for s in imports)

def test_no_out_of_scope_differences():
    paths=git('diff','--name-only',BASE).splitlines()+git('ls-files','--others','--exclude-standard').splitlines()
    assert all(allowed(p) for p in paths)
