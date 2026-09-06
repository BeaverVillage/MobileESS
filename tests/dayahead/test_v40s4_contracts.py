"""S4 binding, protocol and independent numerical regressions. No model fits."""
import ast
import json
import numpy as np
import pandas as pd
import pytest
from dayahead.v40s4.common import *
from dayahead.v40s4.experiment import cap,eta_select,duration,predict
from dayahead.v40s3.contracts import slots,metrics


@pytest.fixture(scope='module')
def data():return panel()


@pytest.fixture(scope='module')
def pre(data):return {t:Preprocess(t).fit(data[data.role=='TRAIN']) for t in ('P','PW')}


def test_s3_scientific_sha_exact():assert get('S3_REFERENCE_FREEZE')['scientific_commit']==S3SCIENCE
def test_s3_receipt_full_sha():assert get('S3_REFERENCE_FREEZE')['receipt_commit']==BASE==git('rev-parse','bfeb9c3')
def test_s3_classification():assert get('S3_REFERENCE_FREEZE')['classification']=='V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT'
def test_isolated_worktree():
    assert ROOT.name=='MobileESS_v40s4_request_state_proxy_runtime_risk'
    assert git('branch','--show-current')=='codex/v40s4-request-state-proxy-runtime-risk'


def test_assumption_preregistered_before_fit():
    assert get('PREREGISTRATION_COMMIT_RECEIPT')['new_fit_before_commit']==0
    assert get('PREREGISTRATION')['assumption']['assumption_id']==ASSUMPTION
    guard_prereg()


@pytest.mark.parametrize('key',['HISTORICAL_D1_SNAPSHOT_PROVENANCE','ORIGINAL_SUBMISSION_VALUE_PROVENANCE'])
def test_unverified_remains_unverified(key):assert get('REQUEST_STATE_PROXY_ASSUMPTION')[key]=='UNVERIFIED'


def test_pending_membership(data):
    assert data.state_at_issue.eq('PENDING').all()
    assert data.submit_time.le(data.issue_time).all() and data.start_time.gt(data.issue_time).all() and data.end_time.gt(data.issue_time).all()
    assert data.issue_time.dt.hour.eq(8).all()


def test_running_redesign_zero():assert get('PROTECTED_SCOPE_DIFF')['RUNNING_redesign']==0


def test_source_identity():
    x=get('POPULATION_AUDIT')
    assert x['source_SHA256']==SOURCE_SHA and x['exact_independent_S3_rebuild']
    assert (x['job_issue_N'],x['unique_jobs'])==(10883,7603)


def test_runtime_label_exact(data):np.testing.assert_array_equal(data.runtime_seconds,(data.end_time-data.start_time).dt.total_seconds())
def test_zero_positive_counts():
    x=get('POPULATION_AUDIT');assert (x['original_N'],x['positive_N'],x['zero_N'],x['negative_N'])==(73504,72292,1212,0)


def test_track_c_exact():assert get('TRACK_C_REFERENCE')['features']==CLOCK and not get('TRACK_C_REFERENCE')['retrained']
def test_track_p_exact():assert get('PROXY_FEATURE_CONTRACT')['tracks']['P']['features']==FEATURES
def test_track_pw_removes_only_walltime():assert selected_features('PW')==[f for f in FEATURES if f!='requested_seconds']


@pytest.mark.parametrize('name',['user','account','job_name','job_id','job_issue_uid','start_time','end_time','runtime_seconds'])
def test_forbidden_predictors_absent(name):assert name not in FEATURES


def test_forbidden_mutation_cannot_change_features(data,pre):
    a=data.iloc[:20].copy();b=a.copy()
    for c in ['job_id','user','account','job_name','runtime_seconds','K0','reference_safe_sec']:b[c]='forbidden mutation'
    b['start_time']=pd.Timestamp('2099-01-01T00:00Z');b['end_time']=pd.Timestamp('2100-01-01T00:00Z')
    for t in pre:np.testing.assert_array_equal(pre[t].transform(a),pre[t].transform(b))


def test_wallclock_covariate_contract():assert 'never clipped' in get('PROXY_FEATURE_CONTRACT')['walltime']


def test_no_output_wallclock_cap(data):
    class Fake:
        def __init__(self,value):self.value=value
        def predict(self,x):return np.full(len(x),self.value)
        def predict_proba(self,x):return np.tile([.2,.8],(len(x),1))
    class Identity:
        def transform(self,x):return np.zeros((len(x),2))
    d=data.iloc[:4].copy();d['requested_seconds']=1.
    models={'B1':[Fake(200),Fake(300)],'B2':[Fake(400),Fake(500)],'B3':np.array([600,700]),'C0':.2,'C1':Fake(.2),'C2':Fake(.2),'C3':Fake(.2)}
    p,_=predict(models,Identity(),d)
    assert (p['B1'][:,1]>d.requested_seconds).all() and (p['B2'][:,1]>d.requested_seconds).all()


def test_actual_above_request_retained(data):
    assert int(data.runtime_seconds.gt(data.requested_seconds).sum())==309


def test_preprocessing_train_only(data):
    with pytest.raises(ValueError):Preprocess('P').fit(data[data.role=='CALIBRATION'])


def test_median_uses_train_only(data,pre):
    tr=data[data.role=='TRAIN']
    for c,median in pre['P'].medians.items():assert median==float(numeric_valid(tr[c],c).median())


def test_unknown_category(pre,data):
    a=data.iloc[:1].copy();a['partition']='not in train';a['qos']='never observed'
    b=a.copy();b['partition']=None;b['qos']=None
    np.testing.assert_array_equal(pre['P'].transform(a),pre['P'].transform(b))


def test_missing_indicator_and_median(pre,data):
    a=data.iloc[:1].copy();a['requested_seconds']=None
    x=pre['P'].transform(a)
    assert x[0,0]==np.log1p(pre['P'].medians['requested_seconds']) and x[0,1]==1


def test_no_target_encoding(data,pre):
    a=data[data.role=='TRAIN'].copy();a['runtime_seconds']=np.arange(len(a))*99999.
    assert Preprocess('P').fit(a).descriptor()==pre['P'].descriptor()


def test_pw_encoded_difference_exact(data,pre):
    mask=np.asarray(pre['P'].groups)!='requested_seconds'
    np.testing.assert_array_equal(pre['P'].transform(data)[:,mask],pre['PW'].transform(data))


@pytest.mark.parametrize('role',BOUNDS)
def test_exact_s3_splits(data,role):
    d=data[data.role==role];lo,hi=map(pd.Timestamp,BOUNDS[role])
    assert d.issue_time.ge(lo).all() and d.issue_time.lt(hi).all() and d.end_time.lt(hi).all()
    assert ids(d)==get('POPULATION_AUDIT')['blocks'][role]['ID_SHA256']
    if role!='TRAIN':assert data[data.role=='TRAIN'].end_time.max()<d.issue_time.min()


def test_s3_thresholds_exact():assert tuple(get('PREREGISTRATION')['threshold_hours'])==U==(4,6,8,12,24)


@pytest.mark.parametrize('track',['P','PW'])
@pytest.mark.parametrize('h',U)
def test_quantiles_positive_ordered_and_labels(data,track,h):
    for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']:
        f=pd.read_parquet(OUT/f'V40S4_PREDICTIONS_{track}_u{h}_{role}.parquet')
        d=data[data.role==role]
        assert f.job_issue_uid.tolist()==d.job_issue_uid.tolist()
        for b in ['B1','B2','B3']:
            assert np.isfinite(f[[b+'_Q50',b+'_Q90']]).all().all()
            assert f[b+'_Q50'].gt(0).all() and f[b+'_Q50'].le(f[b+'_Q90']).all()
        target=d.runtime_seconds.gt(h*3600).to_numpy()
        assert target.sum()+d.runtime_seconds.le(h*3600).sum()==len(d)


def test_15min_ceiling():assert slots([1,900,900.001,1799,1800]).tolist()==[1,1,2,2,2]


def test_eta_cal_only():
    with pytest.raises(ValueError):eta_select([20000]*200,[1]*200,[1000]*200,[.5]*200,14400,role='EXPOSED_EVALUATION')


@pytest.mark.parametrize('prevalence,expected',[(.2,.6),(.6,.6),(.61,.8),(.9,.8)])
def test_selectivity_gate_exact(prevalence,expected):assert cap(prevalence)==expected


def test_eta_synthetic_largest_joint_safety():
    t=np.r_[np.repeat(20000,100),np.repeat(1000,100)];g=np.ones(200);p=np.r_[np.repeat(.8,90),np.repeat(.2,10),np.repeat(.1,100)]
    assert eta_select(t,g,np.ones(200)*500,p,14400,role='CALIBRATION')==.8
    g[90:100]=10
    assert eta_select(t,g,np.ones(200)*500,p,14400,role='CALIBRATION')==.2


def test_eta_selectivity_can_block_perfect_recall():
    assert eta_select([20000]*100+[1000]*100,[1]*200,[500]*200,[.5]*200,14400,role='CALIBRATION') is None


def test_mass_capture_exact():
    d=pd.DataFrame({'runtime_seconds':[20000.,40000.,1000.],'num_gpus_req':[1.,4.,1.]})
    from dayahead.v40s4.experiment import tail_metrics
    r=tail_metrics(d,np.array([.8,.2,.9]),np.array([10000.,10000.,2000.]),4,.5)
    assert r['recall']==.5 and r['GPU_recall']==.2 and r['mass_capture']==pytest.approx(1/13)


def test_all_saved_eta_independently_unavailable(data):
    d=data[data.role=='CALIBRATION'];t=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy()
    for track in ['P','PW']:
        for h in U:
            p=pd.read_parquet(OUT/f'V40S4_PREDICTIONS_{track}_u{h}_CALIBRATION.parquet');y=t>h*3600
            for b in ['B1','B2','B3']:
                mass=g*np.maximum(t-p[b+'_Q90'].to_numpy(),0)
                for c in ['C0','C1','C2','C3']:
                    saved=next(r for r in get('ETA_SELECTION')['rows'] if (r['track'],r['u_hours'],r['body'],r['classifier'])==(track,h,b,c))
                    assert saved['eta'] is None
                    if y.sum()<100:continue
                    prob=p[c+'_p_tail'].to_numpy()
                    feasible=[]
                    for eta in np.unique(np.r_[0.,prob,1.]):
                        f=prob>=eta
                        feasible.append(f[y].mean()>=.9 and g[f&y].sum()/g[y].sum()>=.9 and mass[f].sum()/mass.sum()>=.8 and f.mean()<=cap(y.mean()))
                    assert not any(feasible)


def test_r0_current_reference():np.testing.assert_array_equal(duration([100,200],np.array([False,True]),[500,600],[700,800],14400,'R0'),[100,600])
def test_r1_threshold_floor():np.testing.assert_array_equal(duration([100,200],np.array([False,True]),[500,600],[700,800],14400,'R1'),[100,14400])
def test_r2_walltime():np.testing.assert_array_equal(duration([100,200],np.array([False,True]),[500,600],[700,800],14400,'R2'),[100,800])
def test_no_invented_policy():
    with pytest.raises(ValueError):duration([100],np.array([True]),[500],[700],14400,'Q99')
def test_r2_no_hard_bound_claim():assert not get('R2_REPORT')['guaranteed_runtime_bound']


def test_full_denominator_or_explicit_unavailable():
    for name in ['DEV_CAL_RESULTS','EXPOSED_RESULTS']:
        for r in get(name)['records']:
            if r['hybrid'] is not None:assert r['hybrid']['full_denominator']==r['tail']['N']
            else:assert r['tail']['eta'] is None


def test_numerical_coverage_gpu_miss_overreserve():
    x=metrics([1000,5000],[1800,2700],[2,4])
    assert x['coverage']==.5 and x['GPU_coverage']==pytest.approx(1/3)
    assert x['GPU_underprediction_sec']==9200 and x['positive_error_sec']==2300
    assert x['overreservation_GPU_hours']==pytest.approx(1600/3600)


def test_exact_actual_body_coverage(data):
    for track in ['P','PW']:
        d=data[data.role=='EXPOSED_EVALUATION'];t=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy()
        for h in U:
            p=pd.read_parquet(OUT/f'V40S4_PREDICTIONS_{track}_u{h}_EXPOSED_EVALUATION.parquet');m=t<=h*3600
            for b in ['B1','B2','B3']:
                r=next(r for r in get('EXPOSED_RESULTS')['body'] if (r['track'],r['role'],r['u_hours'],r['body'],r['group'])==(track,'EXPOSED_EVALUATION',h,b,'OVERALL'))
                covered=t[m]<=p[b+'_Q90'].to_numpy()[m]
                assert r['coverage']==covered.mean() and r['GPU_coverage']==pytest.approx(g[m][covered].sum()/g[m].sum())


def test_three_times_cap_exact():assert get('PREREGISTRATION')['hybrid_gates']['overreservation_ratio_max']==3.


def test_body_upper_95_is_hard_gate():
    for r in get('DEV_CAL_RESULTS')['body']:
        if r['group']=='OVERALL' and r['N']>=100 and r['coverage']>.95:assert r['coverage_gate']=='FAIL'


def test_p_vs_pw_comparison_exact():
    a=pd.read_csv(OUT/'V40S4_TRACK_P_BODY_RESULTS.csv');b=pd.read_csv(OUT/'V40S4_TRACK_PW_BODY_RESULTS.csv')
    key=['role','u_hours','body','group'];a=a.set_index(key);b=b.set_index(key)
    for r in get('WALLTIME_DEPENDENCE_ANALYSIS')['matched_comparisons']:
        if r['kind']=='body':
            k=(r['role'],r['u_hours'],r['body'],r['group'])
            assert r['coverage_P_minus_PW']==pytest.approx(a.loc[k,'coverage']-b.loc[k,'coverage'])


def test_perturbation_frozen_no_retrain():
    x=get('PROXY_PERTURBATION_SENSITIVITY')
    assert x['post_selection'] and x['refits']==0 and not x['reselection']
    assert {r['walltime_multiplier'] for r in x['records']}=={.9,1.,1.1}


def test_pw_walltime_perturbation_invariance():
    for r in get('PROXY_PERTURBATION_SENSITIVITY')['records']:
        if r['anchor']['track']=='PW':assert r['max_Q90_change_sec']==0 and r['max_probability_change']==0


@pytest.mark.parametrize('key',['optimizer_calls','Gurobi_calls','OpenDSS_calls','Fresh_calls','A0_changes','A1_changes','M1_changes','MF_changes','migration_changes','WAN_changes','terminal_changes','event_trigger_changes','local_repair_changes','rolling_MPC_changes'])
def test_protected_zero(key):assert get('PROTECTED_SCOPE_DIFF')[key]==0


def test_no_optimizer_imports():
    for p in (ROOT/'dayahead/v40s4').glob('*.py'):
        for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(n,ast.Import):assert not any(x.name in ['gurobipy','opendssdirect','dss'] for x in n.names)
            if isinstance(n,ast.ImportFrom):assert not (n.module or '').startswith(('dayahead.v40a','dayahead.v40g','dayahead.v37','dayahead.v38'))


def test_may_scientific_zero(data):
    x=get('MAY_FIREWALL')
    for k,v in x.items():
        if k.startswith('MAY_') and k.endswith('_READS') and 'DISCOVERY' not in k and 'METADATA' not in k:assert v==0
    for c in ['submit_time','start_time','end_time']:assert data[c].lt(pd.Timestamp('2025-04-24T00:00Z')).all()


def test_shadow_sealed():assert get('MAY_FIREWALL')['shadow']=='SEALED' and get('MAY_FIREWALL')['shadow_rows_read']==0


@pytest.mark.parametrize('key,value',list(HOLDS.items()))
def test_holds_unchanged(key,value):assert get('PROTECTED_SCOPE_DIFF')['holds'][key]==value


def test_s3_all_bytes_unchanged():
    for path,h in get('PROTECTED_SCOPE_START')['S3_SHA256'].items():assert sha((ROOT/path).read_bytes())==h and sha((S3ROOT/path).read_bytes())==h


def test_all_inherited_git_blobs_unchanged():
    old=get('PROTECTED_SCOPE_START')['all_existing_Git_entries'];current={r.split('\t')[1]:r.split('\t')[0] for r in git('ls-tree','-r','HEAD').splitlines()}
    assert all(current.get(k)==v for k,v in old.items())
    assert all(allowed(p.decode()) for p in git('diff','--name-only','-z',BASE,binary=True).split(b'\0') if p)


def test_selection_commit_lock():
    r=get('METHOD_SELECTION_COMMIT_RECEIPT');p='dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_METHOD_SELECTION.json'
    assert git('show',f"{r['commit']}:{p}",binary=True)==(ROOT/p).read_bytes()
    assert get('METHOD_SELECTION')['selected'] is None and not r['EXPOSED_EVALUATION_scored_before_freeze']


def test_repeats_exact_and_models_frozen():
    a=get('REPRODUCIBILITY_AUDIT');assert a['independent_same_seed_pairs']==70 and a['all_byte_equal'] and a['max_prediction_difference']==0
    for p,h in get('MODEL_FREEZE')['model_SHA256'].items():assert sha((OUT/'models'/p).read_bytes())==h


def test_bootstrap_safety_stop():assert get('BOOTSTRAP_STATUS')['status']=='NOT_EXECUTED_SAFETY_FAIL'
def test_adapter_no_recommendations():
    x=get('RUNTIME_ADAPTER_PROPOSAL');assert x['recommended_rows']==[] and len(x['candidate_fields'])==12


def test_artifact_presence_before_postcommit_reports():
    import re
    request=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8').split('# 43. REQUIRED ARTIFACTS')[1].split('# 44. RUNTIME ADAPTER')[0]
    pending={'V40S4_FINAL_REVIEW.md','V40S4_TEST_REPORT.json','V40S4_FINAL_COMMIT_RECEIPT.json'}
    for name in re.findall(r'V40S4_[A-Z0-9_]+\.(?:json|csv|md)',request):assert (OUT/name).exists() or name in pending
