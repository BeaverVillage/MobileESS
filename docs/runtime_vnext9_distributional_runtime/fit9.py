"""Preregistered arms; preparation has masked labels at historical cutoffs."""
from common9 import *
import time,numpy as np,pandas as pd,lightgbm as lgb,xgboost as xgb
from distribution9 import Distribution,age_matrix,dmatrix,QUANTILES
v8path()
from features8 import engineer
def matrix(f,prep):return engineer(f,prep['categorical_mappings'])[prep['columns']].astype('float32')
def fit(f,prep,arm,threads=4,device='cpu'):
    t=time.perf_counter();cols=prep['columns'];cats=[c for c in ['qos','partition','account'] if c in cols]
    meta=dict(kind=arm.split('_')[0],arm=arm,columns=cols,categoricals=cats,provenance_mode='Kestrel_trace_proxy')
    f=f.loc[f.event|f.censored].reset_index(drop=True)
    if arm.endswith('EXACT'):f=f[f.event].reset_index(drop=True)
    x=matrix(f,prep);params=read(ROOT/'EXPERIMENT_PROTOCOL.json')['D1'].copy();rounds=params.pop('n_estimators');params['n_estimators']=rounds
    params['n_jobs']=threads
    if device=='gpu':params.update(device_type='gpu',gpu_platform_id=0,gpu_device_id=0,verbosity=1,deterministic=False)
    if arm=='D1':
        e=np.array(read(ROOT/'HAZARD_BIN_CONTRACT.json')['edges_seconds'],dtype=float);k=len(e)-1
        lower=f.duration_lower.to_numpy(float);exact=f.event.to_numpy(bool);within=exact&(lower<=e[-1])
        counts=np.where(within,np.searchsorted(e[1:],lower,side='left')+1,np.searchsorted(e[1:],lower,side='right'))
        counts=np.minimum(counts,k);rows=np.repeat(np.arange(len(f)),counts);starts=np.repeat(np.cumsum(counts)-counts,counts)
        bins=np.arange(len(rows))-starts;xx=np.column_stack([x.to_numpy()[rows],age_matrix(e)[bins]])
        y=(within[rows]&(bins==counts[rows]-1)).astype('int8')
        b=lgb.LGBMClassifier(**params);b.fit(xx,y,categorical_feature=[cols.index(c) for c in cats])
        meta.update(edges=e.tolist(),person_period_rows=len(y),exact_beyond_endpoint_treated_as_censored=int((exact&~within).sum()),censored_partial_intervals_excluded=True,tail='last interval constant rate extrapolation',zero_event='first bin coarsening')
        model=Distribution(meta,[b.booster_])
    elif arm.startswith('D2'):
        _,noise,scale,*_=arm.split('_');scale=float(scale)
        d=dmatrix(x,cols,cats);d.set_float_info('label_lower_bound',f.duration_lower.to_numpy(float)+1);d.set_float_info('label_upper_bound',f.duration_upper.to_numpy(float)+1)
        config=dict(objective='survival:aft',eval_metric='aft-nloglik',aft_loss_distribution=noise,aft_loss_distribution_scale=scale,tree_method='hist',device='cuda:0' if device=='gpu' else 'cpu',max_depth=6,eta=.05,min_child_weight=100,reg_lambda=2,max_bin=127,seed=4009,nthread=threads,verbosity=2 if device=='gpu' else 0)
        b=xgb.train(config,d,num_boost_round=300)
        meta.update(noise=noise,scale=scale,time_shift=1.,xgboost_config=json.loads(b.save_config()),censored_count=int(f.censored.sum()))
        model=Distribution(meta,[b])
    else:
        exact=f.event.to_numpy(bool);xx=x.loc[exact];y=np.log1p(f.loc[exact,'duration_lower'].to_numpy(float));boosters=[]
        for q in QUANTILES:
            b=lgb.LGBMRegressor(objective='quantile',alpha=float(q),**params);b.fit(xx,y,categorical_feature=cats);boosters.append(b.booster_)
        meta['quantiles']=QUANTILES.tolist();model=Distribution(meta,boosters)
    model.meta.update(training_seconds=time.perf_counter()-t,threads=threads,device=device,TRAIN_N=len(f))
    return model
