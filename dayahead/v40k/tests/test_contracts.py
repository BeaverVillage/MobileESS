import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from dayahead.v40k.common import J,OUT,ROOT,CUTOFF,FEATURES
from dayahead.v40k.protocol import SPLIT,POINT_GATE
from dayahead.v40k.data import allowed_group,timestamp_mask,train_mask,utc,memory
from dayahead.v40k.models import features,causal,normalized_target,normalized_inverse,mixture_cdf,mixture_quantile,stacking_fit,Central
from dayahead.v40k.metrics import point,safety,point_gate

def sample(n=4):
    return pd.DataFrame({'job_id':[str(i) for i in range(n)],'submit_time':pd.to_datetime(['2025-01-01']*n,utc=True),
      'start_time':pd.to_datetime(['2025-01-01']*n,utc=True),'end_time':pd.to_datetime(['2025-01-01 01:00']*n,utc=True),
      'runtime_seconds':np.full(n,3600.),'requested_seconds':np.full(n,43200.),'num_nodes_req':1.,'num_cores_req':4.,'num_gpus_req':1.,
      'requested_memory_mib':1024.,'partition':'h100','qos':'standby','user':'u','account':'a','job_state':'COMPLETED'})
def group(lo='2025-04-01',hi='2025-04-07',end='2025-04-09'):
    return {'bounds':{'submit_time':{'min':lo,'max':hi},'start_time':{'min':lo,'max':hi},'end_time':{'min':lo,'max':end}}}

@pytest.mark.parametrize('bad',['job_state','final_status','runtime_seconds','end_time','start_time','nodelist','queue_wait','state_simple'])
def test_final_status_and_retrospective_rejected(bad):
    x=features(sample());x[bad]=1
    with pytest.raises(ValueError):causal(x)
def test_walltime_inverse():
    y=np.array([0.,1.,300.,43200.,172800.,1000000.]);w=np.array([60.,300.,3600.,43200.,172800.,600.])
    assert np.allclose(normalized_inverse(normalized_target(y,w),w),y,atol=1e-8,rtol=1e-12)
def test_no_walltime_cap():assert normalized_inverse(np.array([2.]),np.array([100.]))[0]>100.
@pytest.mark.parametrize('req',[0,-1,np.nan,np.inf])
def test_invalid_walltime(req):
    with pytest.raises(ValueError):normalized_target([10],[req])
def test_mixture_is_median_not_weighted_mean():
    prob=np.array([.75]);mu=[np.array([np.log1p(10)]),np.array([np.log1p(1000)])];res=[np.array([0.]),np.array([0.])]
    q=mixture_quantile(prob,mu,res)[0]
    assert q==pytest.approx(10,abs=1e-8)
    assert abs(q-(.75*10+.25*1000))>100
def test_mixture_quantile_crossing():
    prob=np.array([.4,.8]);mu=[np.array([1.,1.]),np.array([5.,5.])];r=[np.array([-1.,0.,1.]),np.array([-1.,0.,1.])]
    assert np.all(mixture_quantile(prob,mu,r,.9)>=mixture_quantile(prob,mu,r,.5))
def test_stack_simplex_and_repeat():
    p=np.array([[1,3],[3,5],[10,20],[20,50]],float);y=np.array([2,4,15,35])
    w=stacking_fit(p,y);assert np.all(w>=0) and w.sum()==pytest.approx(1)
    assert w.tobytes()==stacking_fit(p,y).tobytes()
def test_end_known():
    f=sample();f.loc[0,'end_time']=utc('2025-02-02')
    assert not train_mask(f,'2025-02-01').iloc[0]
@pytest.mark.parametrize('column',['submit_time','start_time','end_time'])
def test_may_timestamp_rejection(column):
    f=sample();f.loc[0,column]=utc(CUTOFF);assert not timestamp_mask(f)[0]
def test_group_boundary_before_decode():assert not allowed_group(group(hi='2025-04-08'),SPLIT['point_selection'])
def test_group_future_outcome_before_decode():assert not allowed_group(group(end=CUTOFF),SPLIT['point_selection'])
def test_group_accepted():assert allowed_group(group(),SPLIT['point_selection'])
def test_shadow_group_not_point():assert not allowed_group(group(lo='2025-04-24',hi='2025-04-25'),SPLIT['point_selection'])
def test_residual_self_fit_rejected():
    f=sample();x=features(f)
    with pytest.raises(ValueError,match='SELF_FIT'):
        Central('K1_L1_RESIDUAL').fit(x,f.runtime_seconds,c0=np.zeros(len(f)),c0_fit_times=pd.to_datetime(['2025-02-01']*len(f),utc=True),submit_times=f.submit_time,end_times=f.end_time,fit_before='2025-02-02')
def test_residual_future_label_rejected():
    f=sample();f['end_time']=utc('2025-03-01')
    with pytest.raises(ValueError,match='FUTURE_RESIDUAL'):
        Central('K1_L1_RESIDUAL').fit(features(f),f.runtime_seconds,c0=np.zeros(len(f)),c0_fit_times=pd.to_datetime(['2024-12-01']*len(f),utc=True),submit_times=f.submit_time,end_times=f.end_time,fit_before='2025-02-01')
def test_pinball_mae_accounting():
    m=point([1,5,10],[2,3,8]);assert m['pinball_Q50']*2==m['MAE'];assert m['median_calibration_error']==pytest.approx(1/6)
def test_GPU_accounting():
    f=sample(2);f['runtime_seconds']=[900.,300.];f['num_gpus_req']=[2.,4.]
    m=safety(f,np.array([300.,900.]));assert m['active_miss_GPU_5min_slots']==4;assert m['overreserved_GPU_hours']==pytest.approx(2/3);assert m['GPU_weighted_coverage']==pytest.approx(4/6)
def test_median_not_mean_gate():
    base={'overall':{'N':100,'pinball_Q50':10.,'MAE':20.,'median_calibration_error':.3},'COMPLETED H100-standby':{'N':100,'MAE':20.,'median_calibration_error':.3}}
    new={'overall':{'N':100,'pinball_Q50':9.,'MAE':18.,'median_calibration_error':.1,'mean_signed_error_diagnostic':10000},'COMPLETED H100-standby':{'N':100,'MAE':18.,'median_calibration_error':.1}}
    assert point_gate(base,new,True)['eligible']
def test_calibration_separation():assert SPLIT['point_selection'][1]==SPLIT['safe_fit'][0] and SPLIT['safe_fit'][1]==SPLIT['safe_selection'][0] and SPLIT['safe_selection'][1]==SPLIT['final_shadow'][0]
@pytest.mark.parametrize('value,expected',[('160G',163840),('90000Mn',90000),('4096',4096),('1.5T',1572864),('bad',np.nan),('4Gc',np.nan),('.5G',512)])
def test_memory_mapping(value,expected):assert memory(value)==expected if np.isfinite(expected) else np.isnan(memory(value))
def test_prior_receipt_and_pf():
    f=json.loads((J/'V40J_RUNTIME_METHOD_FREEZE.json').read_text());assert f['PF']==.95 and f['Q_control']=='NO' and f['winner'] is None
def test_shadow_no_retune_contract():assert 'no retune' in SPLIT['shadow_requirement'] and not SPLIT['point_model_refit_after_selection']
def test_point_freeze_before_safe(monkeypatch):
    import dayahead.v40k.data as data
    monkeypatch.setattr(data,'require_prereg',lambda:'test')
    monkeypatch.setattr(data,'read',lambda n:{'winner':None})
    with pytest.raises(AssertionError,match='POINT_FREEZE_REQUIRED'):data.authorize('safe_fit')
def test_both_freezes_before_shadow(monkeypatch):
    import dayahead.v40k.data as data
    monkeypatch.setattr(data,'require_prereg',lambda:'test')
    monkeypatch.setattr(data,'read',lambda n:{'winner':'K2','models_unchanged_after_selection':True} if 'POINT' in n else {'winner':None})
    with pytest.raises(AssertionError,match='SAFE_FREEZE_REQUIRED'):data.authorize('final_shadow')
def test_safe_hierarchy_deterministic():
    from dayahead.v40k.evaluate import SafeBound
    from dayahead.v40j.methods import SupportGuard
    f=sample(120);x=features(f);p=np.full(120,300.)
    s=SupportGuard(x,100).predict(x);m=SafeBound('S3').fit(x,f.runtime_seconds.to_numpy(),p)
    a,n,levels=m.predict(x,p,s);b,_,_=m.predict(x,p,s)
    assert a.tobytes()==b.tobytes() and (a>=f.runtime_seconds).all()
def test_protected_V40J_hashes():
    from dayahead.v40k.common import sha
    start=json.loads((OUT/'V40K_START_STATE.json').read_text())
    assert all(sha(ROOT/p)==h for p,h in start['V40J_file_sha256'].items())
def test_point_determinism_and_hazard_order():
    f=sample(400);f['runtime_seconds']=np.linspace(0,200000,400);f['requested_seconds']=np.tile([3600.,43200.,172800.,604800.],100)
    x=features(f);m=Central('K2_NORMALIZED_Q50').fit(x,f.runtime_seconds);n=Central('K2_NORMALIZED_Q50').fit(x,f.runtime_seconds)
    assert m.predict(x).tobytes()==n.predict(x).tobytes()
    h=Central('K4_INTERVAL_HAZARD').fit(x,f.runtime_seconds);assert np.all(h.predict(x,alpha=.9)>=h.predict(x))
