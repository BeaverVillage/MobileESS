import json
import numpy as np
import pandas as pd
import pytest
from dayahead.v40s5r1.common import *
from dayahead.v40s5r1.data import check_membership
from dayahead.v40s5 import common as old

def sample(n=12):
    return pd.DataFrame(dict(job_uid=[str(i) for i in range(n)],end_time=pd.date_range('2025-01-01',periods=n,freq='min',tz='UTC'),
      submit_time=pd.date_range('2024-12-31',periods=n,freq='min',tz='UTC'),runtime_seconds=np.arange(1,n+1)*900.,
      requested_seconds=np.full(n,9000.),reference_safe_sec=np.full(n,900.),num_gpus_req=np.ones(n),num_nodes_req=np.ones(n),
      num_cores_req=np.full(n,8.),requested_memory_mib=np.full(n,1024.),partition=['p']*n,qos=['q']*n,
      submit_hour=np.arange(n)%24,submit_dow=np.arange(n)%7,issue_day=['d']*n))

def test_exact_parent_frozen_contract_and_pure_functions():
    assert FEATURES==s5('FEATURE_CONTRACT')['P'] and FIXED==s5('PREREGISTRATION')['fixed_parameters']
    name,params=model_config();assert name==s5('HYPERPARAMETER_FREEZE')['selected']=='L2'
    assert params==s5('PREREGISTRATION')['configs'][name]
    assert s5('PREREGISTRATION')['residual']['OOF_Q50_config']=='L0'
    for name in ['repair','uarp','candidates','metrics','daily_metrics','gates','numeric','categories']:
        assert globals()[name] is getattr(old,name)

def test_parent_closed_before_new_worktree():
    a=read('START_STATE');assert a['parent_fully_closed'] and a['parent_verification']['git_clean']
    assert a['base']==BASE and a['parent_verification']['scientific_commit']==S5SCIENCE
    assert Path(a['worktree']).resolve()==ROOT and ROOT!=S5ROOT
    assert a['branch']=='codex/v40s5r1-rolling-origin-runtime'
    assert read('S5_REFERENCE_FREEZE')['classification']=='V40S5_DIRECT_RUNTIME_SAFETY_FAIL'

def test_exact_panel_identity_metadata_and_timezone():
    a=read('PENDING_PANEL_IDENTITY_AUDIT')
    assert a['total_job_issue']==10883 and a['unique_jobs']==7603 and a['unique_issue_times']==36
    assert {r:v['N'] for r,v in a['blocks'].items()}==EXPECTED
    ts=pd.to_datetime([v['issue_time'] for v in a['issues']],utc=True)
    assert (ts.hour==8).all() and (ts.minute==0).all()
    assert len(set(ts))==len(ts) and ts.is_monotonic_increasing
    assert not a['initial_evaluation_label_columns'] and file_sha(PANEL)==PANEL_SHA

@pytest.mark.parametrize('n,k',[(99,0),(100,3),(249,3),(250,5),(421,5)])
def test_preregistered_support_boundaries(n,k):assert fold_count(n)==k

def test_fold_timestamp_blocks_and_expanding_history():
    f=sample(300);f.loc[48:52,'end_time']=f.loc[48,'end_time']
    fs=list(folds(f,pd.Timestamp('2025-01-02T08:00Z')));assert len(fs)==5
    covered=set();previous=set()
    for k,a,b in fs:
        assert a.end_time.max()<b.end_time.min() and not set(a.job_uid)&set(b.job_uid)
        assert previous<=set(a.job_uid) and not covered&set(b.job_uid)
        previous=set(a.job_uid);covered.update(b.job_uid)
    with pytest.raises(ValueError,match='INSUFFICIENT_SUPPORT'):list(folds(sample(99),pd.Timestamp('2025-01-02T08:00Z')))

def test_strict_cutoff_rejects_equal_end_and_future():
    f=sample();t=f.end_time.max()
    with pytest.raises(AssertionError):Preprocess('P',t).fit(f)
    with pytest.raises(AssertionError):check_membership(t,f)
    assert check_membership(t+pd.Timedelta(seconds=1),f)['training_job_count']==len(f)

def test_expanding_membership_requires_all_old_jobs_and_newly_completed():
    f=sample();t=pd.Timestamp('2025-01-02T08:00Z')
    r=check_membership(t,f);assert r['new_jobs_added_since_previous_issue']==len(f)
    with pytest.raises(AssertionError):check_membership(t,f.iloc[1:],None,[f.iloc[0].job_uid])
    with pytest.raises(AssertionError):check_membership(t,f,pd.Timestamp('2025-01-01T00:05Z'),[])
    r=check_membership(t,f,pd.Timestamp('2025-01-01T00:05Z'),f.iloc[:5].job_uid.tolist())
    assert r['new_jobs_added_since_previous_issue']==7

def test_preprocessing_exact_s5_at_first_origin():
    f=pd.read_parquet(S5/'V40S5_HISTORICAL_TRAINING_LIBRARY.parquet')
    a=Preprocess('P',old.CUTOFF).fit(f);b=old.Preprocess('P').fit(f)
    np.testing.assert_array_equal(a.transform(f),b.transform(f))
    assert a.medians==b.medians and a.vocab==b.vocab and a.groups==b.groups

def test_unknown_and_numeric_missing_are_issue_local():
    f=sample();p=Preprocess('P','2025-01-02T08:00Z').fit(f);v=f.iloc[:2].copy()
    v.partition=['new',None];v.requested_seconds=[None,-1]
    x=p.transform(v);i=p.groups.index('partition')
    assert (x[:,i]==1).all() and (x[:,i+1]==0).all()
    assert (x[:,0]==np.log1p(9000)).all() and (x[:,1]==1).all()

@pytest.mark.parametrize('c',['start_time','end_time','runtime_seconds','reference_safe_sec','K0','user','account','job_uid','status'])
def test_forbidden_fields_do_not_affect_predictor_matrix(c):
    f=sample();p=Preprocess('P','2025-01-02T08:00Z').fit(f);v=f.copy();v[c]='FORBIDDEN'
    np.testing.assert_array_equal(p.transform(f),p.transform(v))

def test_pw_exact_single_feature_removal():
    f=sample();p=Preprocess('P','2025-01-02T08:00Z').fit(f);w=Preprocess('PW','2025-01-02T08:00Z').fit(f)
    assert fields('PW')==[c for c in FEATURES if c!='requested_seconds']
    np.testing.assert_array_equal(p.transform(f)[:,2:],w.transform(f))

@pytest.mark.parametrize('events',[[],[dict(kind='PREDICTION_HASH',track='P')]])
def test_label_reader_cannot_open_before_both_hashes(monkeypatch,events):
    from dayahead.v40s5r1 import data
    class FakePath:
        def __truediv__(self,other):return self
        def read_text(self):return json.dumps(events)
    monkeypatch.setattr(data,'OUT',FakePath())
    def forbidden(*args,**kwargs):raise RuntimeError('Parquet reader was called before authorization')
    monkeypatch.setattr(data.pq,'read_table',forbidden)
    with pytest.raises(AssertionError,match='PREDICTIONS_MUST_BE_HASHED'):data.labels('2025-03-14T08:00Z')

def test_prediction_projection_excludes_outcomes():
    assert not set(LABELS)&set(FEATURE_COLUMNS)
    assert set(FEATURES)<=set(FEATURE_COLUMNS)

def test_exact_formula_and_no_requested_cap():
    np.testing.assert_array_equal(repair([[5,3,4,2],[-1,2,1,3]]),[[5,5,5,5],[0,2,2,3]])
    np.testing.assert_array_equal(uarp([100,100],[0,100]),[120,150])
    f=sample(2);f.requested_seconds=1
    q=np.array([[10,20,30,40],[20,30,40,50.]])
    v=candidates(f,q,[10,100]);np.testing.assert_array_equal(v['R5_UARP_STYLE'],[48,100])

def test_metric_arithmetic_and_rounding_once():
    f=sample(3);f.runtime_seconds=[899.,900.,1801.];f.num_gpus_req=[1,2,4]
    m=metrics(f,[900,800,901])
    assert m['coverage']==1/3 and m['GPU_coverage']==1/7
    assert m['GPU_under_sec']==3800 and m['GPU_over_h']==1/3600
    assert m['completion_slot_MAE']==1/3 and m['completion_slot_signed_error']==-1/3
    assert m['GPU_ending_at_least_1_slots_early']==4/7

@pytest.mark.parametrize('n,major',[(99,False),(100,True),(101,True)])
def test_daily_support_rule(n,major):
    f=pd.concat([sample(1)]*n,ignore_index=True);d=daily_metrics(f,np.zeros(n))['d']
    assert d['major_day']==major and d['daily_gate_pass'] is (False if major else None)

def test_safety_efficiency_and_selection_ignore_exposed():
    m=dict(coverage=.9,GPU_coverage=.9,GPU_under_sec=99,GPU_over_h=99)
    d={'x':dict(major_day=True,daily_gate_pass=True)};rsp=dict(GPU_under_sec=100);req=dict(GPU_over_h=100)
    assert gates(m,d,rsp,req)['eligible']
    m['coverage']=1.;m['GPU_coverage']=1.;assert gates(m,d,rsp,req)['eligible']
    m['GPU_under_sec']=100;assert not gates(m,d,rsp,req)['safety']
    m['GPU_under_sec']=99;m['GPU_over_h']=100;assert not gates(m,d,rsp,req)['efficiency']
    rs={r:{c:dict(GPU_over_h=10+i,GPU_under_sec=10) for i,c in enumerate(CANDIDATES[2:])} for r in ROLES[1:3]}
    gs={r:{c:dict(eligible=True) for c in CANDIDATES[2:]} for r in ROLES[1:3]}
    rs['EXPOSED_EVALUATION']=None;assert choose(rs,gs)=='R2_Q90'
    for c in CANDIDATES[2:]:gs['CALIBRATION'][c]['eligible']=False
    assert choose(rs,gs) is None

def test_diagnostic_material_threshold_fixed():
    assert improvement(.10,0,0)=='ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME'
    assert improvement(0,.10,0)=='ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME'
    assert improvement(.099,.099,-1)=='ROLLING_UPDATE_SMALL_EFFECT'
    assert improvement(-.01,-.01,1)=='ROLLING_UPDATE_DEGRADES_RUNTIME'

def test_repeat_dates_predetermined_before_fit():
    p=read('PREREGISTRATION');i=read('PENDING_PANEL_IDENTITY_AUDIT')['issues']
    expected=[next(v['issue_time'] for v in i if v['role']==r) for r in ROLES]+[[v['issue_time'] for v in i if v['role']=='EXPOSED_EVALUATION'][-1]]
    assert p['repeat_issue_times']==expected and p['hyperparameter_tuning'] is False
