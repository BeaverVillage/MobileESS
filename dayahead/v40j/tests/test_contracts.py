import json
import numpy as np
import pandas as pd
import pytest
from dayahead.v40j.contracts import OUT, FEATURES, FEATURES9, FORBIDDEN, SPLIT, EXTERNAL, EXTERNAL_SHA, PF
from dayahead.v40j.firewall import ReadFirewall, causal_matrix, member_allowed, sha
from dayahead.v40j.methods import (raw_features, ceil_seconds, occupancy_slots, SupportGuard,
 ConditionalCalibration, conformal_q, point_metrics, safety_metrics, envelope_durations, CausalModel)
from dayahead.v40j.data import train_mask, block_mask

def example(n=110):
    d={c:[1]*n for c in FEATURES9}
    d.update(requested_seconds=[3600.]*n,partition=['gpu-h100']*n,qos=['standby']*n,user=['anon']*n,account=['project']*n,
             submit_time=pd.date_range('2025-01-01',periods=n,freq='h',tz='UTC'))
    return pd.DataFrame(d)

@pytest.mark.parametrize('field',sorted(FORBIDDEN))
def test_forbidden_production_feature(field):
    x=raw_features(example(1))
    x[field]=0
    with pytest.raises(ValueError):causal_matrix(x)
    with pytest.raises(ValueError):SupportGuard(x,100)
    with pytest.raises(ValueError):CausalModel('C1_L1').predict(x)

@pytest.mark.parametrize('month',[5,6,7,8,9,10,11,12])
def test_future_zip_member_rejected(month):
    assert not member_allowed(f'x/year=2025/month={month}/k.parquet',shadow=True)
    fw=ReadFirewall('unit')
    with pytest.raises(PermissionError):fw.open_member(None,f'x/year=2025/month={month}/k.parquet',shadow=True)

def test_april_sealed():
    assert not member_allowed('x/year=2025/month=4/k.parquet')
    assert member_allowed('x/year=2025/month=4/k.parquet',shadow=True)
    assert member_allowed('x/year=2025/month=3/k.parquet')

def test_filesystem_firewall_rejects_may_even_under_output():
    fw=ReadFirewall('test'); fw.active=True
    with pytest.raises(PermissionError):fw.audit('open',(str(OUT/'2025-05-01.parquet'),'r',0))
    with pytest.raises(PermissionError):fw.audit('open',('C:/unknown/actual.parquet','r',0))
    assert len(fw.denied)==2

def test_unknown_and_order_rejected():
    x=raw_features(example(1))
    with pytest.raises(ValueError):causal_matrix(x[list(reversed(FEATURES))])
    with pytest.raises(ValueError):causal_matrix(x.assign(random_feature=1))

def test_chronology_and_end_known_purge():
    f=example(3)
    f['runtime_seconds']=[100,100,100]
    f['start_time']=f.submit_time+pd.Timedelta(seconds=1)
    f['end_time']=pd.to_datetime(['2025-01-31','2025-02-08','2025-02-09'],utc=True)
    assert train_mask(f,'2025-02-08').tolist()==[True,False,False]
    folds=SPLIT['folds']
    for k in folds:
        assert k['fit_before']<=k['calibration'][0]<k['calibration'][1]<=k['validation'][0]<k['validation'][1]
    for a,b in zip(folds,folds[1:]): assert a['validation'][1]<=b['validation'][0]
    assert SPLIT['final_fit_before']<=SPLIT['final_calibration'][0]<SPLIT['final_calibration'][1]<SPLIT['final_shadow'][0]
    assert (pd.Timestamp(SPLIT['final_shadow'][1])-pd.Timestamp(SPLIT['final_shadow'][0])).days==7

def test_support_all_four_states_and_no_special_twelve_hour_rule():
    x=raw_features(example())
    guard=SupportGuard(x,100)
    assert guard.predict(x).support_class.eq('STRONG_SUPPORT').all()
    query=x.iloc[:1].copy(); query['requested_seconds']=43200.
    assert guard.predict(query).support_class.iloc[0]=='REGIME_MISMATCH'
    query['user']='unseen'
    assert guard.predict(query).support_class.iloc[0]=='OUT_OF_SUPPORT'
    assert SupportGuard(x.iloc[:3],100).predict(x.iloc[:1]).support_class.iloc[0]=='SPARSE_SUPPORT'
    assert guard.predict(x).equals(guard.predict(x))

def test_parent_fallback_uses_larger_parent_margin():
    x=raw_features(example())
    pred=np.zeros((len(x),3)); y=np.arange(len(x))*10.
    c=ConditionalCalibration(100).fit(x,y,pred)
    query=x.iloc[:1].copy(); query['requested_seconds']=43200.
    support=SupportGuard(x,100).predict(query)
    p,meta=c.predict(query,np.zeros((1,3)),support)
    assert meta.level.iloc[0]>=1
    assert meta.conservative_parent_max.iloc[0]
    assert p[0,1]>=conformal_q(y,.9)
    assert np.all(np.diff(p,axis=1)>=0)
    assert c.json()==ConditionalCalibration(100).fit(x,y,pred).json()

def test_ood_requested_reference_and_invalid_abstain():
    x=raw_features(example()); c=ConditionalCalibration(100).fit(x,np.ones(len(x)),np.zeros((len(x),3)))
    q=x.iloc[:1].copy();q['user']='unseen';q['requested_seconds']=43200
    s=SupportGuard(x,100).predict(q)
    p,_=c.predict(q,np.zeros((1,3)),s)
    assert p[0,1]>=43200
    q['requested_seconds']=np.nan
    with pytest.raises(ValueError):c.predict(q,np.zeros((1,3)),s)

@pytest.mark.parametrize('seconds,expected',[(0,0),(1,900),(899,900),(900,900),(900.001,1800),(1800,1800)])
def test_seconds_ceil(seconds,expected):assert ceil_seconds([seconds])[0]==expected

@pytest.mark.parametrize('start,duration,expected',[(0,900,[0,1,2]),(299,1,[0]),(299,2,[0,1]),(300,300,[1]),(-1,2,[-1,0]),(0,0,[])])
def test_five_minute_boundaries(start,duration,expected):
    assert occupancy_slots(start,duration).tolist()==expected
    safe=ceil_seconds([duration])[0]
    assert set(expected)<=set(occupancy_slots(start,safe))

def test_gpu_weighting_and_active_miss():
    m=safety_metrics([900,900],[300,900],[4,1])
    assert m['coverage']==.5
    assert m['GPU_WEIGHTED_COVERAGE']==.2
    assert m['GPU_WEIGHTED_UNDERPREDICTION_SECONDS']==2400
    assert m['PREDICTED_FINISHED_BUT_ACTUALLY_ACTIVE_GPU_SLOTS']==8
    assert m['GRID_RELEVANT_RUNTIME_MISS_RATE'] is None
    assert safety_metrics([0],[0],[1],[1])['active_miss_GPU_slot_rate']==0

def test_underprediction_sign_and_overreservation():
    p=point_metrics([10,30],[20,20])
    assert p['mean_signed_error_seconds']==0 and p['underprediction_rate']==.5
    s=safety_metrics([10,30],[20,20],[2,1])
    assert s['GPU_WEIGHTED_OVERRESERVATION_SECONDS']==20
    assert s['GPU_WEIGHTED_UNDERPREDICTION_SECONDS']==10

def test_robust_envelope_deterministic_and_separate():
    a=envelope_durations(np.array([100]),np.array([1000]),np.array([2000]))
    assert a['R0'][0][0]==900
    assert a['R2'][0][0]==900 and a['R2'][1][0]==1800
    assert a['R3'][0][0]==1800 and a['R3'][1][0]==2700
    b=envelope_durations(np.array([100]),np.array([1000]),np.array([2000]))
    assert all(np.array_equal(a[k][i],b[k][i]) for k in a for i in [0,1])

def test_baseline_byte_reproduction_receipt():
    report=json.loads((OUT/'V40J_CURRENT_RUNTIME_BASELINE.json').read_text())
    assert report['status']=='PASS' and report['prediction_bytes_identical']
    assert report['prediction_max_abs_difference']==0
    assert report['features']==FEATURES9 and report['q_seconds']==5576.44921875

def test_external_immutable_hash_and_pf():
    r=json.loads((OUT/'V40J_EXTERNAL_DATACENTER_PQ_AUDIT.json').read_text(encoding='utf-8'))
    assert sha(EXTERNAL)==EXTERNAL_SHA==r['source_sha256_before']==r['source_sha256_after']
    assert r['read_only'] and r['mtime_unchanged']
    assert r['AIDC_PF']==PF==.95 and r['AIDC_Q_CONTROL']=='NO'

def test_preregistered_files_unchanged():
    r=json.loads((OUT/'V40J_PREREGISTRATION_REVIEW.json').read_text())
    assert all(sha(OUT/n)==expected for n,expected in r['files'].items())

def test_all_candidate_fits_independently_repeat():
    r=json.loads((OUT/'V40J_TRAINING_DETERMINISM.json').read_text())
    assert len(r)==18
    assert all(v['same_seed_input_independent_refit_prediction_bytes_identical'] for v in r)

def test_native_q90_gate_does_not_use_q95_envelope():
    # A huge reserve can eliminate replay misses while native Q90 still fails.
    q90=np.array([1.,1.]);q95=np.array([100.,100.]);y=np.array([10.,20.])
    assert safety_metrics(y,q90,[1,1])['coverage']==0
    assert safety_metrics(y,q95,[1,1])['coverage']==1

def test_timestamp_boundary_rejects_april_partition_utc_may_rows():
    from dayahead.v40j.timestamp_firewall import premay_mask, timestamp_summary, assert_historical_population
    f=pd.DataFrame({c:pd.to_datetime(['2025-04-30T23:59:59Z','2025-05-01T00:00:00Z'],utc=True) for c in ['submit_time','start_time','end_time']})
    assert premay_mask(f).tolist()==[True,False]
    r=timestamp_summary(f)
    assert r['rejected_post_cutoff_row_count']==1
    assert r['minimum_rejected_timestamp']=='2025-05-01 00:00:00+00:00'
    with pytest.raises(ValueError):assert_historical_population(f,'2025-05-01T00:00:00Z')

def test_start_phase_independent_of_datetime_storage_unit():
    from dayahead.v40j.methods import safety_metrics
    s=pd.Series(pd.to_datetime(['2025-03-01T00:04:59Z'],utc=True))
    for unit in ['us','ns','ms']:
        x=s.dt.as_unit(unit)
        phase=x.dt.as_unit('ns').astype('int64').to_numpy()/1e9%300
        assert phase[0]==299
        assert safety_metrics([2],[1],[4],phase)['CRITICAL_SLOT_MISS_GPU_SLOTS']==4
