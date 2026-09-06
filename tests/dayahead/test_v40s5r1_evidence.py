import ast
import json
import numpy as np
import pandas as pd
import pytest
from dayahead.v40s5r1.common import *
from dayahead.v40s5r1.data import history
from dayahead.v40s5r1.run import combine

ISSUES=read('PENDING_PANEL_IDENTITY_AUDIT')['issues']

@pytest.fixture(scope='module')
def ledger():return pd.read_parquet(OUT/f'{PREFIX}DAILY_TRAINING_LEDGER.parquet')

def test_parent_and_entire_inherited_tree_unchanged():
    assert ancestor(S5SCIENCE,BASE) and ancestor(BASE,git('rev-parse','HEAD'))
    r=read('S5_REFERENCE_FREEZE')
    assert r['selected_model'] is None and r['CURRENT_RSP_REPLACED']=='NO'
    for p,h in r['verified_SHA256'].items():assert file_sha(ROOT/p)==file_sha(S5ROOT/p)==h
    assert file_sha(S5/'V40S5_FINAL_COMMIT_RECEIPT.json')==r['receipt_SHA256']
    current=tree('HEAD');assert all(current[p]==v for p,v in tree(BASE).items())
    assert git('status','--porcelain',cwd=S5ROOT)=='' and git('rev-parse','HEAD',cwd=S5ROOT)==BASE
    assert file_sha(SOURCE)==SOURCE_SHA

def test_one_expanding_membership_and_one_package_per_issue(ledger):
    assert len(ledger)==len(ISSUES)==36 and not ledger.issue_time.duplicated().any()
    assert ledger.issue_time.is_monotonic_increasing and ledger.training_job_count.is_monotonic_increasing
    assert set(ledger.issue_time)==set(pd.to_datetime([v['issue_time'] for v in ISSUES],utc=True))
    assert len(list((OUT/'models').glob('*/P/package.json')))==len(ISSUES)
    assert len(list((OUT/'models').glob('*/PW/package.json')))==len(ISSUES)
    assert (ledger.cache_reuse=='NO').all()

@pytest.mark.parametrize('v',ISSUES,ids=[key(v['issue_time']) for v in ISSUES])
def test_every_origin_exact_mature_membership_and_ooftime(v,ledger):
    t=pd.Timestamp(v['issue_time']);k=key(t)
    f=pd.read_parquet(OUT/'membership'/f'{k}.parquet');independent=history(t,log=False)
    pd.testing.assert_frame_equal(f,independent)
    row=ledger[ledger.issue_time==t].iloc[0]
    assert len(f)==row.training_job_count and ids(f.job_uid)==row.training_job_uid_SHA256
    assert not f.job_uid.duplicated().any() and f.end_time.lt(t).all()
    assert np.isfinite(f.runtime_seconds).all() and f.runtime_seconds.gt(0).all()
    np.testing.assert_array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    assert file_sha(OUT/'membership'/f'{k}.parquet')==row.training_library_hash
    previous=ledger[ledger.issue_time<t]
    if len(previous):
        pt=previous.iloc[-1].issue_time;p=pd.read_parquet(OUT/'membership'/f'{key(pt)}.parquet',columns=['job_uid'])
        assert set(p.job_uid)<=set(f.job_uid)
        new=f[~f.job_uid.isin(p.job_uid)];assert new.end_time.ge(pt).all()
        assert len(new)==row.new_jobs_added_since_previous_issue
    for track in ['P','PW']:
        directory=OUT/'models'/k/track;pkg=json.loads((directory/'package.json').read_text())
        desc=pkg['preprocessing'];expected=Preprocess(track,t).fit(f).descriptor()
        assert desc==expected and desc['columns']==fields(track)
        assert pkg['config_id']==model_config()[0] and pkg['OOF_config_id']=='L0' and pkg['support_route']==5
        assert pkg['training_ids']==ids(f.job_uid) and pkg['threads']==1 and pkg['seed']==SEED
        for name,h in pkg['files_SHA256'].items():assert file_sha(directory/name)==h
        o=pd.read_parquet(directory/'residual_OOF.parquet')
        assert not o.job_uid.duplicated().any() and (o.fit_max_end<o.end_time).all()
        np.testing.assert_array_equal(o.r2,(o.runtime_seconds-o.Q50_OOF)**2)
        for (n,a,b),audit in zip(folds(f,t),pkg['residual_folds']):
            selected=o[o.fold==n]
            assert set(selected.job_uid)==set(b.job_uid) and not set(a.job_uid)&set(b.job_uid)
            assert a.end_time.max()<b.end_time.min()
            assert audit['fit_ids']==ids(a.job_uid) and audit['validation_ids']==ids(b.job_uid)
            assert audit['preprocessing']==Preprocess(track,b.end_time.min()).fit(a).descriptor()
            assert selected.fit_ids_sha256.eq(ids(a.job_uid)).all()
        for record in pkg['fit_records']:
            assert record['config_id']==('L0' if record['name'].startswith('OOF') else model_config()[0])
            assert pd.Timestamp(record['max_training_end'])<t

@pytest.mark.parametrize('v',ISSUES,ids=[key(v['issue_time']) for v in ISSUES])
def test_every_origin_prediction_hash_precedes_label_and_score(v):
    k=key(v['issue_time']);ev=json.loads((OUT/'events'/f'{k}.json').read_text())
    label=[e for e in ev if e['kind']=='EVALUATION_LABEL_READ'];assert len(label)==1
    label=label[0];hashes=[e for e in ev if e['kind']=='PREDICTION_HASH'];assert len(hashes)==2
    assert set(h['track'] for h in hashes)=={'P','PW'}
    for h in hashes:
        fit=next(e for e in ev if e['kind']=='FIT_COMPLETE' and e['track']==h['track'])
        assert fit['sequence']<h['sequence']<label['sequence']
        assert pd.Timestamp(fit['timestamp'])<=pd.Timestamp(h['timestamp'])<=pd.Timestamp(label['timestamp'])
        assert file_sha(OUT/h['path'])==h['SHA256']
        d=pd.read_parquet(OUT/h['path'])
        assert not set(LABELS)&set(d.columns) and not h['label_columns']
        assert len(d)==v['N'] and ordered_ids(d.job_issue_uid)==v['ordered_ids_SHA256']
    assert label['sequence']<next(e for e in ev if e['kind']=='SCORE_COMPLETE')['sequence']
    assert ev[-1]['kind']=='ISSUE_COMPLETE'
    fr=next(e for e in ev if e['kind']=='FEATURE_READ');assert not set(LABELS)&set(fr['columns'])
    history_read=next(e for e in ev if e['kind']=='HISTORICAL_READ');assert history_read['future_rows_materialized']==0

@pytest.mark.parametrize('track',['P','PW'])
@pytest.mark.parametrize('role',ROLES)
def test_exact_predictions_metrics_daily_support_and_candidates(track,role):
    d=combine(track,[role]);assert len(d)==EXPECTED[role]
    original=pd.read_parquet(PANEL,filters=[('role','==',role)])
    assert d.job_issue_uid.tolist()==original.job_issue_uid.tolist()
    for c in ['runtime_seconds','requested_seconds','num_gpus_req','reference_safe_sec']:
        np.testing.assert_array_equal(d[c],original[c])
    assert (d.runtime_seconds>d.requested_seconds).sum()==(original.runtime_seconds>original.requested_seconds).sum()
    q=d[[f'Q{int(a*100)}' for a in QUANTILES]].to_numpy();raw=d[[f'raw_Q{int(a*100)}' for a in QUANTILES]].to_numpy()
    assert np.isfinite(raw).all() and np.isfinite(q).all() and (q>=0).all()
    np.testing.assert_array_equal(q,repair(raw));np.testing.assert_array_equal(d.sigma,np.sqrt(np.maximum(d.predicted_r2,0)))
    assert np.isfinite(d.sigma).all() and (d.sigma>=0).all()
    result=read('ALL_SPLIT_RESULTS')[track]['results'][role]
    for name,p in candidates(d,q,d.sigma).items():
        np.testing.assert_array_equal(d[name],p);np.testing.assert_array_equal(d[name+'_slots'],np.ceil(p/900))
        y=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy();u=np.maximum(y-p,0);o=np.maximum(p-y,0);m=result[name]
        assert m['coverage']==np.mean(y<=p) and m['GPU_coverage']==np.sum(g*(y<=p))/g.sum()
        assert m['under_sec']==u.sum() and m['GPU_under_sec']==pytest.approx(np.sum(g*u))
        assert m['over_sec']==o.sum() and m['GPU_over_h']==pytest.approx(np.sum(g*o)/3600)
        for t,f in d.groupby('issue_time'):
            report=json.loads((OUT/'daily'/f'{key(t)}_{track}.json').read_text())['results'][name]
            daily=metrics(f,f[name]);assert report==daily
            if track=='P':
                audit=read('DAILY_SAFETY_AUDIT')['splits'][role][name][t.strftime('%Y-%m-%d')]
                assert audit['major_day']==(len(f)>=100)
                if len(f)>=100:assert audit['daily_gate_pass']==(daily['coverage']>=.88 and daily['GPU_coverage']>=.88)

def test_first_origin_is_exact_static_s5_package_behavior():
    t=pd.Timestamp(ISSUES[0]['issue_time']);d=pd.read_parquet(OUT/'predictions'/f'{key(t)}_P.parquet')
    s=pd.read_parquet(S5/'V40S5_P_TRAIN_PREDICTIONS.parquet',filters=[('issue_time','==',t.to_pydatetime())])
    assert d.job_issue_uid.tolist()==s.job_issue_uid.tolist()
    for c in ['Q50','Q90','Q95','Q99','sigma',*CANDIDATES]:np.testing.assert_array_equal(d[c],s[c])

def test_safety_efficiency_selection_independent_recomputation():
    allr=read('ALL_SPLIT_RESULTS')['P'];eligible=[]
    for c in CANDIDATES[2:]:
        pre=[]
        for role in ROLES[1:]:
            m=allr['results'][role][c];ds=read('DAILY_SAFETY_AUDIT')['splits'][role][c]
            safety=m['coverage']>=.9 and m['GPU_coverage']>=.9 and m['GPU_under_sec']<allr['results'][role][CANDIDATES[0]]['GPU_under_sec']
            safety=safety and all(v['coverage']>=.88 and v['GPU_coverage']>=.88 for v in ds.values() if v['N']>=100)
            eff=m['GPU_over_h']<allr['results'][role][CANDIDATES[1]]['GPU_over_h']
            assert allr['gates'][role][c]['safety']==safety and allr['gates'][role][c]['efficiency']==eff
            if role!='EXPOSED_EVALUATION':pre.append(safety and eff)
        if all(pre):eligible.append(c)
    selected=choose(allr['results'],allr['gates'])
    assert selected==read('SELECTION_FREEZE')['selected_candidate']==read('EXPOSED_RESULTS')['selected_candidate']
    assert (selected is None)==(len(eligible)==0)
    assert read('SELECTION_FREEZE')['selection_roles']==['DEVELOPMENT','CALIBRATION']
    assert not read('EXPOSED_RESULTS')['candidate_reselection']

def test_prereg_and_selection_commits_precede_their_stages():
    pr=guard('PREREGISTRATION_COMMIT_RECEIPT');sel=guard('SELECTION_FREEZE_COMMIT_RECEIPT')
    assert ancestor(pr,sel)
    pt=pd.Timestamp(git('show','-s','--format=%cI',pr));st=pd.Timestamp(git('show','-s','--format=%cI',sel))
    for v in ISSUES:
        ev=json.loads((OUT/'events'/f"{key(v['issue_time'])}.json").read_text())
        assert pd.Timestamp(ev[0]['timestamp'])>=(st if v['role']=='EXPOSED_EVALUATION' else pt)
        if v['role']=='EXPOSED_EVALUATION':assert ev[0]['candidate_frozen']==read('SELECTION_FREEZE')['selected_candidate']

def test_prior_exposed_labels_enter_only_after_maturity():
    metadata=read('PENDING_PANEL_IDENTITY_AUDIT')
    m=pd.DataFrame(dict(job_uid=metadata['job_ids'],role=metadata['roles'],issue_time=pd.to_datetime(metadata['issue_times'],utc=True)))
    counts=[]
    for v in ISSUES:
        if v['role']!='EXPOSED_EVALUATION':continue
        t=pd.Timestamp(v['issue_time']);f=pd.read_parquet(OUT/'membership'/f'{key(t)}.parquet',columns=['job_uid','end_time'])
        prior=set(m[(m.role=='EXPOSED_EVALUATION')&(m.issue_time<t)].job_uid)
        used=f[f.job_uid.isin(prior)];assert used.end_time.lt(t).all()
        counts.append(len(used))
        current=set(m[m.issue_time==t].job_uid);assert not current&set(f.job_uid)
    assert counts[0]==0 and counts[-1]>0
    assert read('EXPOSED_RESULTS')['TRUE_CONFIRMATORY_AVAILABLE']=='NO'

def test_static_comparison_and_pw_do_not_select():
    static=read('STATIC_S5_COMPARISON');assert static['no_refit']
    for role,rows in static['splits'].items():
        for c,v in rows.items():
            for k,delta in v['rolling_minus_static'].items():assert delta==v['rolling'][k]-v['static'][k]
            if c in CANDIDATES[:2]:assert all(x==0 for x in v['rolling_minus_static'].values())
    w=read('WALLTIME_DEPENDENCE_ANALYSIS');assert w['removed']==['requested_seconds'] and not w['PW_winner_search']
    assert read('SELECTION_FREEZE')['track']=='P'

def test_maturity_diagnostic_and_unique_job_denominator():
    m=read('DATA_MATURITY_PERFORMANCE_AUDIT');assert m['diagnostic_only'] and m['no_training_size_threshold']
    u=read('UNIQUE_JOB_SENSITIVITY');assert u['diagnostic_only'] and u['no_reselection']
    for role in ROLES:
        d=combine('P',[role]);assert u['splits'][role]['P']['N']==d.job_uid.nunique()

def test_independent_repeats_all_five_full_packages():
    r=read('REPRODUCIBILITY_AUDIT');assert r['status']=='PASS' and r['independent_rebuilds']==5
    assert r['predetermined_issues']==read('PREREGISTRATION')['repeat_issue_times'] and not r['better_repeat_selected']
    for t in r['predetermined_issues']:
        k=key(t);a=json.loads((OUT/'models'/k/'P/package.json').read_text());b=json.loads((OUT/'repeats'/k/'package.json').read_text())
        assert a['package_SHA256']==b['package_SHA256'] and a['files_SHA256']==b['files_SHA256']
        for v in r['results'][k]['compare'].values():assert v['max_difference']==0 and v['mean_difference']==0

def test_firewalls_holds_adapter_and_no_operational_imports():
    m=read('MAY_FIREWALL');assert m['shadow']=='SEALED' and m['shadow_scientific_rows']==0
    for k,v in m.items():
        if k.startswith('May_'):assert v==0
    c=read('COMPUTE_LEDGER');assert c['holds']==HOLDS and c['primary_packages']==36 and c['PW_packages']==36
    for name in ['optimizer_calls','Gurobi_calls','OpenDSS_calls','Fresh_calls']:assert c[name]==0
    a=read('RUNTIME_ADAPTER_PROPOSAL');assert a['proposal_only'] and not a['optimizer_use_allowed']
    if not read('EXPOSED_RESULTS')['selected_pass']:
        assert not a['recommended_rows'] and read('FINAL_DECISION')['FURTHER_RUNTIME_MODEL_WORK']=='DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA'
    for p in (ROOT/'dayahead/v40s5r1').glob('*.py'):
        imports=[]
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n,ast.Import):imports += [a.name for a in n.names]
            if isinstance(n,ast.ImportFrom):imports.append(n.module or '')
        assert not any(any(bad in s.lower() for bad in ['gurobi','opendss','v37','v40a','xgboost','tensorflow','torch']) for s in imports)
    assert all(allowed(p) for p in git('diff','--name-only',BASE).splitlines())
