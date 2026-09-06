import numpy as np
import pandas as pd
import pytest
from dayahead.v40l.common import OUT,K,F9,FEATURES,Q,verify_k0,Firewall
from dayahead.v40l.protocol import SPLIT,PARAMS,REGISTRY,EXCESS_ALPHAS
from dayahead.v40l.data import Support,utc,train_mask,allowed_group,base_features
from dayahead.v40l.models import repair,order_quantile,exceedance_quantile,aft_bounds,aft_quantile,signed_target,causal,Hierarchy,fit_cqr
from dayahead.v40l.metrics import safety,choose

def jobs(n=120):
    f=pd.DataFrame({'job_id':['j'+str(i) for i in range(n)],'requested_seconds':3600.,'num_nodes_req':1.,'num_cores_req':8.,'num_gpus_req':2.,'requested_memory_mib':1024.,'partition':'h100','qos':'standby','user':'u','account':'a','job_state':'COMPLETED','runtime_seconds':600.})
    f['submit_time']=pd.Timestamp('2025-02-01',tz='UTC');f['start_time']=f.submit_time;f['end_time']=f.start_time+pd.Timedelta(seconds=600)
    return f

def test_k0_sha():assert len(verify_k0())==3
def test_cpu():assert PARAMS['device']=='cpu' and PARAMS['nthread']==1
def test_alpha_contract():assert REGISTRY['T1']['alphas']==[.9,.95] and REGISTRY['T2']['alphas']==[.5,.9,.95]
def test_frozen_legacy_margin():assert Q==5576.44921875
def test_signed_population():assert signed_target([0,5],[2,1],provenance=True).tolist()==[-2/3600,4/3600]
def test_positive_misuse():
    with pytest.raises(ValueError,match='POSITIVE_ONLY'):signed_target([5],[1],provenance=True,positive_only=True)
def test_oof_required():
    with pytest.raises(ValueError,match='OOF'):signed_target([5],[1],provenance=False)
def test_status_not_feature():
    with pytest.raises(ValueError,match='NONCAUSAL'):causal(pd.DataFrame(columns=FEATURES+['job_state']))
@pytest.mark.parametrize('a',[0,1,-.1,1.1])
def test_alpha_reject(a):
    with pytest.raises(ValueError):order_quantile([1,2],a)
def test_order_rank():assert order_quantile(np.arange(100),.9)==90
def test_order_small_no_false_finite():assert np.isinf(order_quantile([1],.95))
def test_empty_calibration():
    with pytest.raises(ValueError):order_quantile([],.9)
@pytest.mark.parametrize('raw',[(5,3),(1,8),(4,4)])
def test_monotonic_repair(raw):
    p,c=repair([4],[raw[0]],[raw[1]]);p2,_=repair([4],[raw[0]],[raw[1]])
    assert p[0,1]>=p[0,0]>=4 and p.tobytes()==p2.tobytes()
def test_crossing_count():assert repair([4],[5],[3])[1]['raw_Q95_below_Q90']==1
def test_cqr_separation():
    with pytest.raises(ValueError,match='CALIBRATION_BLOCK_ONLY'):fit_cqr([5],np.array([[1.,2.]]),block='selection')
def test_cqr_signed():assert np.all(fit_cqr(np.zeros(100),np.ones((100,2)),block='calibration')==-1)
def test_support_future_end_excluded():
    h=jobs();q=h.iloc[:1].copy();q.submit_time=pd.Timestamp('2025-02-01 00:05',tz='UTC')
    assert Support(h).transform(q).exact_count.iloc[0]==0
def test_support_end_strict():
    h=jobs();q=h.iloc[:1].copy();q.submit_time=h.end_time.iloc[0]
    assert Support(h).transform(q).exact_count.iloc[0]==0
def test_support_numeric_equivalence():
    h=jobs();q=h.iloc[:1].copy();q.submit_time=pd.Timestamp('2025-03-01',tz='UTC');q['num_gpus_req']=2
    assert Support(h).transform(q).exact_count.iloc[0]==120
def test_training_self_fit_chronology():
    h=jobs();h.loc[0,'end_time']=pd.Timestamp('2025-01-31',tz='UTC')
    assert not train_mask(h).iloc[0]
def test_training_future_completion():
    h=jobs();h.loc[0,'end_time']=pd.Timestamp('2025-04-01',tz='UTC')
    assert not train_mask(h).iloc[0]
def test_hierarchy_empty_pooled_key():
    h=jobs();q=h.copy();q.submit_time=pd.Timestamp('2025-03-01',tz='UTC');x=Support(h).transform(q)
    m=Hierarchy(500).fit(x,np.arange(120),block='calibration');a,d=m.predict(x,np.ones(120));b,e=m.predict(x,np.ones(120))
    assert d['levels']=={'3':120} and a.tobytes()==b.tobytes() and () in m.tables[-1]
def test_hierarchy_fit_separation():
    with pytest.raises(ValueError):Hierarchy(100).fit(pd.DataFrame(),[],block='selection')
def test_exceedance_probability_combination():
    cq=np.tile(np.array(EXCESS_ALPHAS)*100,(1,1));v=exceedance_quantile([.5],cq,.9)
    assert np.allclose(v,[80]) and not np.allclose(v,[90])
def test_exceedance_zero_margin():
    assert exceedance_quantile([.05],np.ones((1,19)),.9)[0]==0
def test_exceedance_quantiles_order():
    q=np.tile(np.arange(19)[::-1],(2,1));p=np.array([.3,.8])
    assert np.all(exceedance_quantile(p,q,.95)>=exceedance_quantile(p,q,.9))
@pytest.mark.parametrize('lo,up',[([0],[1]),([2],[1]),([np.inf],[np.inf]),([1],[np.nan])])
def test_aft_invalid(lo,up):
    with pytest.raises(ValueError):aft_bounds(lo,up)
def test_aft_censor_infinity():assert np.isinf(aft_bounds([1],[np.inf])[1][0])
def test_aft_quantile_formula():assert np.allclose(aft_quantile(np.log([10]),.5),[10])
def test_aft_not_run_without_authority():assert REGISTRY['T5']['availability']=='NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE'
def test_april_split_chronology():
    assert SPLIT['visible_development'][1]==SPLIT['calibration'][0] and SPLIT['calibration'][1]==SPLIT['selection'][0] and SPLIT['selection'][1]==SPLIT['shadow'][0]
def test_post_may_group_rejection():
    b={'submit_time':{'min':'2025-04-24','max':'2025-04-25'},'start_time':{'min':'2025-04-24','max':'2025-04-25'},'end_time':{'min':'2025-04-24','max':'2025-05-01'}}
    assert not allowed_group({'bounds':b},'shadow')
def test_mixed_split_group_rejection():
    b={c:{'min':'2025-04-14','max':'2025-04-16'} for c in ['submit_time','start_time','end_time']}
    assert not allowed_group({'bounds':b},'calibration')
def test_firewall_denies_May_before_open():
    with Firewall('synthetic_firewall_test'):
        with pytest.raises(PermissionError):open(OUT/'2025-05-01-outcome.parquet','rb')
def test_native_GPU_metrics():
    f=jobs(2);f['submit_time']=pd.Timestamp('2025-04-01',tz='UTC');f.start_time=f.submit_time;f['runtime_seconds']=[600.,1200.];f['num_gpus_req']=[1.,3.]
    r=safety(f,np.array([300.,300.]),np.array([900.,900.]),'visible_development')
    assert r['coverage']==.5 and r['GPU_weighted_coverage']==.25 and r['active_miss_GPU_5min_slots']==3 and r['GPU_weighted_underprediction_seconds']==900 and r['overreserved_GPU_hours']==300/3600
def test_abstention_not_dropped():
    f=jobs(2);f.submit_time=pd.Timestamp('2025-04-01',tz='UTC');r=safety(f,np.zeros(2),np.array([1000.,np.nan]),'visible_development')
    assert r['coverage']==.5 and r['abstentions']==1
def test_efficiency_order():
    def rec(over,inflate,miss):return {'eligible':True,'metrics':{'overall':{'Q90':{'overreserved_GPU_hours':over,'mean_safe_inflation_seconds':inflate,'active_miss_GPU_5min_slots':miss}}}}
    assert choose({'T1':rec(1,2,3),'T2':rec(1,1,9)})[0]=='T2'
def test_no_coverage_winner():assert choose({'T1':{'eligible':False}})==(None,[])
def test_shadow_requires_winner(monkeypatch):
    from dayahead.v40l import evaluate
    monkeypatch.setattr(evaluate,'read',lambda _: {'winner':None})
    with pytest.raises(AssertionError):evaluate.shadow()
def test_global_holds():
    from dayahead.v40l.common import load
    s=load(K/'V40K_FINAL_STATUS.json');assert s['PF']==.95 and s['Q_control']=='NO' and s['authority_missing']==72
