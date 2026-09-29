from common11 import *
from model11 import *
import lightgbm as lgb,time,numpy as np,pandas as pd
def preprocessing(f,i):
    maps={c:{str(v):j+1 for j,v in enumerate(sorted(f[c].astype('string').fillna('__MISSING__').unique()))} for c in ['qos','partition','account']}
    positive=f.requested_seconds[(f.requested_seconds>0)&np.isfinite(f.requested_seconds)]
    return dict(columns=prep(i)['columns'],categorical_mappings=maps,walltime_fallback=float(positive.median()),fit_cutoff=prep(i)['fit_cutoff'])
def fit_quantiles(records,pre,target='RAW',y=None,elapsed=None,no_elapsed=False,weight=None):
    start=time.perf_counter();y=np.asarray(records.runtime_seconds if y is None else y,float)
    cols=pre['columns']+([] if elapsed is None or no_elapsed else EXTRA);x=features(records,pre,None if no_elapsed else elapsed)[cols]
    transformed=y if target=='RAW' else np.log1p(y) if target=='LOG' else np.log((y+1)/(denominator(records,pre)+1))
    boosts={};cfg=read(ROOT/'EXPERIMENT_PROTOCOL.json')['learner']
    for key,tau in [('Q50',.5),('Q90',.9)]:
        m=lgb.LGBMRegressor(**cfg,objective='quantile',alpha=tau);m.fit(x,transformed,sample_weight=weight,categorical_feature=['qos','partition','account']);boosts[key]=m.booster_
    return Quantiles(dict(target=target,columns=cols,preprocessing=pre,fit_seconds=time.perf_counter()-start,TRAIN_N=len(y),CPU_threads=4,no_elapsed=no_elapsed),boosts)
def fit_tail(records,pre,target,weight):
    start=time.perf_counter();y=records.runtime_seconds.to_numpy();x=features(records,pre)[pre['columns']]
    transformed=y if target=='RAW' else np.log1p(y) if target=='LOG' else np.log((y+1)/(denominator(records,pre)+1))
    cfg=read(ROOT/'EXPERIMENT_PROTOCOL.json')['learner'];m=lgb.LGBMRegressor(**cfg,objective='quantile',alpha=.9);m.fit(x,transformed,sample_weight=weight,categorical_feature=['qos','partition','account'])
    return m.booster_,time.perf_counter()-start
def tail_predict(booster,records,pre,target):
    q=booster.predict(features(records,pre)[pre['columns']],num_threads=4)
    if target=='LOG':q=np.expm1(q)
    elif target=='REL':q=np.exp(q)*(denominator(records,pre)+1)-1
    return np.maximum(q,0)
