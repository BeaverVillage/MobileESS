import numpy as np
import pandas as pd
import pytest
from dayahead.v40s5.common import (CUTOFF,FEATURES,NUM,CAT,CLOCK,CONFIGS,FIXED,QUANTILES,CANDIDATES,
    Preprocess,repair,uarp,candidates,metrics,daily_metrics,gates,choose,temporal_split,temporal_folds,fields)

def frame(n=12):
    return pd.DataFrame(dict(job_uid=[str(i) for i in range(n)],end_time=pd.date_range('2025-01-01',periods=n,tz='UTC'),
      runtime_seconds=np.arange(1,n+1)*900.,requested_seconds=np.full(n,9000.),reference_safe_sec=np.full(n,900.),
      num_gpus_req=np.ones(n),num_nodes_req=np.ones(n),num_cores_req=np.full(n,8.),requested_memory_mib=np.full(n,1024.),
      partition=['p']*n,qos=['q']*n,submit_hour=np.arange(n)%24,submit_dow=np.arange(n)%7,issue_day=['a']*n))

def test_cutoff_and_configuration_registry():
    assert CUTOFF==pd.Timestamp('2025-03-14T08:00:00Z')
    assert list(CONFIGS)==['L0','L1','L2'] and QUANTILES==[.5,.9,.95,.99]
    assert FIXED['n_jobs']==1 and FIXED['device_type']=='cpu'
    assert len(CANDIDATES)==6

def test_exact_features():
    assert FEATURES==['requested_seconds','num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib','partition','qos','submit_hour','submit_dow']
    assert fields('PW')==[c for c in FEATURES if c!='requested_seconds']

def test_unknown_missing_and_medians():
    f=frame();p=Preprocess().fit(f);v=f.iloc[:2].copy()
    v['partition']=['unseen',None];v['requested_seconds']=[None,-1]
    x=p.transform(v);idx=p.groups.index('partition')
    assert (x[:,idx]==1).all() and (x[:,idx+1]==0).all()
    assert (x[:,0]==np.log1p(9000)).all() and (x[:,1]==1).all()
    assert p.medians['requested_seconds']==9000

@pytest.mark.parametrize('c',['runtime_seconds','reference_safe_sec','job_uid','end_time','start_time','user_id','account','terminal_status','K0'])
def test_excluded_predictors_cannot_change_transform(c):
    f=frame();p=Preprocess().fit(f);v=f.copy();v[c]='FORBIDDEN'
    np.testing.assert_array_equal(p.transform(f),p.transform(v))

def test_preprocess_future_and_duplicate_jobs_rejected():
    f=frame();f.loc[0,'end_time']=CUTOFF
    with pytest.raises(AssertionError):Preprocess().fit(f)
    f=frame();f.loc[1,'job_uid']=f.loc[0,'job_uid']
    with pytest.raises(AssertionError):Preprocess().fit(f)

def test_walltime_removal_preserves_every_other_encoded_column():
    f=frame();p=Preprocess().fit(f);w=Preprocess('PW').fit(f)
    np.testing.assert_array_equal(p.transform(f)[:,2:],w.transform(f))

def test_boundary_timestamp_is_never_split():
    f=frame(10);f.loc[7:9,'end_time']=f.loc[7,'end_time']
    a,b,t=temporal_split(f);assert len(a)==7 and len(b)==3
    assert a.end_time.max()<b.end_time.min() and not set(a.job_uid)&set(b.job_uid)

def test_five_expanding_oof_folds():
    f=frame(60);folds=list(temporal_folds(f));assert len(folds)==5
    seen=set()
    for k,a,b in folds:
        assert a.end_time.max()<b.end_time.min() and not set(a.job_uid)&set(b.job_uid)
        assert not seen&set(b.job_uid);seen.update(b.job_uid)

def test_monotone_repair_and_physical_floor_exact():
    x=np.array([[5,3,4,2],[-1,2,1,3],[1,2,3,4.]])
    np.testing.assert_array_equal(repair(x),[[5,5,5,5],[0,2,2,3],[1,2,3,4]])

def test_uarp_exact_both_terms_and_no_request_cap():
    np.testing.assert_array_equal(uarp([100,100,0],[0,100,10]),[120,150,5])
    f=frame(2);f.requested_seconds=1
    q=np.array([[10,20,30,40],[20,30,40,50.]])
    c=candidates(f,q,np.array([10.,100.]))
    for name,expected in zip(CANDIDATES,[f.reference_safe_sec,f.requested_seconds,q[:,1],q[:,2],q[:,3],[48,100]]):
        np.testing.assert_array_equal(c[name],expected)

def test_metrics_independent_arithmetic():
    f=frame(3);f.runtime_seconds=[899.,900.,1801.];f.num_gpus_req=[1,2,4]
    m=metrics(f,[900,800,901])
    assert m['coverage']==1/3 and m['GPU_coverage']==1/7
    assert m['under_sec']==1000 and m['GPU_under_sec']==3800
    assert m['over_sec']==1 and m['GPU_over_h']==1/3600
    assert m['MAE']==1001/3 and m['WAPE']==1001/3600 and m['bias']==-999/3
    assert m['completion_slot_MAE']==1/3 and m['completion_slot_signed_error']==-1/3
    assert m['ending_at_least_1_slots_early']==1/3 and m['GPU_ending_at_least_1_slots_early']==4/7
    assert m['ending_at_least_4_slots_early']==0 and m['ending_at_least_8_slots_early']==0

@pytest.mark.parametrize('n,major',[(99,False),(100,True),(101,True)])
def test_daily_gate_support_boundary(n,major):
    f=pd.concat([frame(1)]*n,ignore_index=True);v=daily_metrics(f,np.zeros(n))['a']
    assert v['major_day']==major
    assert v['daily_gate_pass'] is (False if major else None)

def test_gate_inclusivity_strict_anchor_improvement_and_no_upper_gate():
    m=dict(coverage=.9,GPU_coverage=.9,GPU_under_sec=99,GPU_over_h=99)
    daily={'d':dict(major_day=True,daily_gate_pass=True)}
    rsp=dict(GPU_under_sec=100);req=dict(GPU_over_h=100)
    assert gates(m,daily,rsp,req)['eligible']
    m['coverage']=1.;m['GPU_coverage']=1.;assert gates(m,daily,rsp,req)['eligible']
    m['GPU_under_sec']=100;assert not gates(m,daily,rsp,req)['safety']
    m['GPU_under_sec']=99;m['GPU_over_h']=100;assert not gates(m,daily,rsp,req)['efficiency']

def test_candidate_selection_uses_dev_cal_minimum_and_never_exposed():
    rs={r:{c:dict(GPU_over_h=10+i,GPU_under_sec=10) for i,c in enumerate(CANDIDATES[2:])} for r in ['DEVELOPMENT','CALIBRATION']}
    gs={r:{c:dict(eligible=True) for c in CANDIDATES[2:]} for r in rs}
    pb={c:1 for c in CANDIDATES[2:]}
    rs['EXPOSED_EVALUATION']=None
    assert choose(rs,gs,pb)=='R2_Q90'
    gs['CALIBRATION']['R2_Q90']['eligible']=False
    assert choose(rs,gs,pb)=='R3_Q95'
    for c in CANDIDATES[2:]:gs['CALIBRATION'][c]['eligible']=False
    assert choose(rs,gs,pb) is None
