"""Explicit event-time windows. Queries are never inserted as observations.

The custom pandas indexer uses searchsorted(end, t, side='left') bounds,
including for duplicate timestamps; no shifted full-data aggregate is used.
No absolute timestamp is returned as a model feature.
"""
import numpy as np
import pandas as pd
from pandas.api.indexers import BaseIndexer

FAMILIES = ['partition', 'qos', 'walltime', 'gpu', 'partition_qos', 'partition_walltime']
GLOBAL_STATS = ['runtime_q25','runtime_q50','runtime_q75','runtime_q90','runtime_q95',
                'gt1h_rate','gt4h_rate','gt8h_rate','gt12h_rate','gt24h_rate',
                'N','total_GPUh','mean_requested_GPU','high_GPU_fraction',
                'ratio_q50','ratio_q75','ratio_q90']
COHORT_STATS = ['N','runtime_q50','runtime_q90','gt4h_rate','gt12h_rate','ratio_q50']
META = ['raw_N','support_N','fallback_depth','newest_age_seconds','oldest_age_seconds','tail_N','ratio_N']

def keys(f):
    p=f.partition.astype('string').fillna('__MISSING__').astype(str)
    q=f.qos.astype('string').fillna('__MISSING__').astype(str)
    w=pd.to_numeric(f.requested_seconds, errors='coerce').to_numpy(float)
    g=pd.to_numeric(f.num_gpus_req, errors='coerce').to_numpy(float)
    wb=np.where(np.isfinite(w)&(w>0),np.searchsorted([3600,14400,43200,86400],w,side='left'),-1).astype(str)
    gb=np.where(np.isfinite(g)&(g>0),np.searchsorted([1,4,8,16],g,side='left'),-1).astype(str)
    return pd.DataFrame(dict(partition=p, qos=q, walltime=wb, gpu=gb,
                             partition_qos=p+'|'+q, partition_walltime=p+'|'+wb),index=f.index)

def completed(source, cutoff):
    # Visibility mask precedes runtime subtraction. April/May outcomes excluded.
    m=source.end_time.notna() & source.end_time.lt(cutoff)
    f=source.loc[m].copy()
    f=f[f.start_time.notna() & f.start_time.ge(f.submit_time) & f.end_time.ge(f.start_time)].copy()
    f['runtime']=(f.end_time-f.start_time).dt.total_seconds()
    assert f.job_id.is_unique
    return f.sort_values(['end_time','job_id'],kind='stable').reset_index(drop=True)

class Bounds(BaseIndexer):
    def __init__(self, times, days):
        self.start=np.searchsorted(times,times-int(days*86400*1e9),side='left')
        self.end=np.searchsorted(times,times,side='left')
        super().__init__(window_size=0)
    def get_window_bounds(self,num_values=0,min_periods=None,center=None,closed=None,step=None):
        return self.start,self.end

def window_stats(events, query_times, days, full=True):
    """Sorted event/query merge with explicit [t-days,t) membership.

    Events are the only non-NaN values; duplicate prediction times coalesce.
    Bounds also compute a provenance witness (latest/oldest contributing end).
    """
    qt=pd.DatetimeIndex(query_times).as_unit('ns').asi8
    unique, inverse=np.unique(qt, return_inverse=True)
    et=pd.DatetimeIndex(events.end_time).as_unit('ns').asi8
    # Unique query insertion avoids source/query order assumptions at ties.
    combined=np.concatenate([et,unique]); order=np.argsort(combined,kind='stable')
    times=combined[order]; positions=np.empty(len(order),int);positions[order]=np.arange(len(order))
    qp=positions[len(et):]
    runtime=events.runtime.to_numpy(float);gpu=events.num_gpus_req.to_numpy(float)
    wall=events.requested_seconds.to_numpy(float)
    ratio=np.divide(runtime,wall,out=np.full(len(wall),np.nan),where=np.isfinite(wall)&(wall>0))
    def roll(v):
        values=np.concatenate([v,np.full(len(unique),np.nan)])[order]
        return pd.Series(values).rolling(Bounds(times,days),min_periods=1)
    def take(v): return v.to_numpy()[qp][inverse]
    rr=roll(runtime); out={'N':np.nan_to_num(take(rr.count()))}
    for q in ([.25,.5,.75,.9,.95] if full else [.5,.9]):out[f'runtime_q{int(q*100)}']=take(rr.quantile(q))
    for h in ([1,4,8,12,24] if full else [4,12]):out[f'gt{h}h_rate']=take(roll((runtime>h*3600).astype(float)).mean())
    out['tail_N']=np.nan_to_num(take(roll((runtime>14400).astype(float)).sum()))
    r=roll(ratio);out['ratio_N']=np.nan_to_num(take(r.count()))
    for q in ([.5,.75,.9] if full else [.5]):out[f'ratio_q{int(q*100)}']=take(r.quantile(q))
    if full:
        out['total_GPUh']=take(roll(runtime*gpu/3600).sum())
        out['mean_requested_GPU']=take(roll(gpu).mean())
        out['high_GPU_fraction']=take(roll((gpu>=16).astype(float)).mean())
    left=np.searchsorted(et,qt-int(days*86400*1e9),side='left')
    right=np.searchsorted(et,qt,side='left');n=right-left
    assert np.array_equal(n,out['N'])
    newest=np.full(len(qt),np.nan);oldest=newest.copy()
    ok=n>0
    newest[ok]=(qt[ok]-et[right[ok]-1])/1e9
    oldest[ok]=(qt[ok]-et[left[ok]])/1e9
    assert (newest[ok]>0).all() and (oldest[ok]<=days*86400).all()
    out.update(newest_age_seconds=newest,oldest_age_seconds=oldest)
    return pd.DataFrame(out)

def make_prior(events, cutoff):
    f=events[events.end_time.lt(cutoff)]
    # Small, frozen earliest TRAIN prefix; availability guarded even on TRAIN.
    enough=(np.arange(len(f))+1>=200)&((f.runtime>14400).cumsum().to_numpy()>=20)
    if not enough.any():raise ValueError('No supported causal TRAIN prefix')
    f=f.iloc[:np.flatnonzero(enough)[0]+1]
    available=f.end_time.max()+pd.Timedelta(nanoseconds=1)
    span=(available-f.end_time.min()).total_seconds()/86400+1
    stats=window_stats(f,[available],span).iloc[0].to_dict()
    return dict(stats=stats,available_at=available.isoformat(),oldest_end=f.end_time.min().isoformat(),
                newest_end=f.end_time.max().isoformat(),job_ids_sha256=__import__('hashlib').sha256('\n'.join(f.job_id).encode()).hexdigest())

def prior_frame(prior, times):
    out=pd.DataFrame([prior['stats']]*len(times))
    t=pd.DatetimeIndex(times)
    out['newest_age_seconds']=(t-pd.Timestamp(prior['newest_end'])).total_seconds()
    out['oldest_age_seconds']=(t-pd.Timestamp(prior['oldest_end'])).total_seconds()
    out.loc[t<pd.Timestamp(prior['available_at']),:]=np.nan
    return out

def supported(f, minimum):
    return (f.N>=minimum)&(f.tail_N>=20)&(f.ratio_N>=minimum)

def resolve(chain, columns):
    """Use one supported source for all statistics, never sparse zero filling."""
    raw=chain[0][0]
    out=pd.DataFrame(np.nan,index=raw.index,columns=columns+META)
    out['raw_N']=raw.N
    for depth,(f,minimum) in enumerate(chain):
        use=out.fallback_depth.isna() & supported(f,minimum)
        out.loc[use,columns]=f.loc[use,columns].to_numpy()
        out.loc[use,'support_N']=f.loc[use,'N']
        out.loc[use,'fallback_depth']=depth
        for col in ['newest_age_seconds','oldest_age_seconds','tail_N','ratio_N']:out.loc[use,col]=f.loc[use,col]
    # Missing values retain genuine unavailability; -1 is explicit metadata.
    out['fallback_depth']=out.fallback_depth.fillna(-1)
    return out

def materialize(events, queries, prior, progress=None):
    q=queries.reset_index(drop=True);time=q.prediction_time
    globals_={d:window_stats(events,time,d) for d in [7,14,30]}
    prior_=prior_frame(prior,time);resolved={};frames=[]
    for d in [7,14,30]:
        chain=[(globals_[d],200)]
        if d!=30:chain.append((globals_[30],200))
        chain.append((prior_,200))
        resolved[d]=resolve(chain,GLOBAL_STATS)
        frames.append(resolved[d].add_prefix(f'g{d}__'))
    ek=keys(events);qk=keys(q);raw={}
    for family in FAMILIES:
        if progress:progress(family)
        for d in [14,30]:
            f=pd.DataFrame(np.nan,index=q.index,columns=COHORT_STATS+['tail_N','ratio_N','newest_age_seconds','oldest_age_seconds'])
            eg={str(k):v.to_numpy() for k,v in ek.groupby(family,sort=False).groups.items()}
            for key,indices in qk.groupby(family,sort=False).groups.items():
                ev=events.iloc[eg.get(str(key),np.empty(0,dtype=int))]
                s=window_stats(ev,time.iloc[indices],d,False)
                f.loc[indices,s.columns]=s.to_numpy()
            raw[family,d]=f
            chain=[(f,200 if '_' in family else 100)]
            if '_' in family:chain.append((raw['partition',d],100))
            chain.append((globals_[d],200))
            if d!=30:chain.append((globals_[30],200))
            chain.append((prior_,200))
            frames.append(resolve(chain,COHORT_STATS).add_prefix(f'c_{family}_{d}__'))
    result=pd.concat(frames,axis=1)
    result['trend__q90_7_minus_30']=resolved[7].runtime_q90-resolved[30].runtime_q90
    result['trend__gt4h_7_minus_30']=resolved[7].gt4h_rate-resolved[30].gt4h_rate
    result['trend__median_7_over_30']=resolved[7].runtime_q50/resolved[30].runtime_q50.replace(0,np.nan)
    result['trend__ratio_14_minus_30']=resolved[14].ratio_q50-resolved[30].ratio_q50
    return result.replace([np.inf,-np.inf],np.nan)

class ReplayState:
    """Serializable causal feature state; no model or outcome prediction fitting."""
    def __init__(self, history, prior):self.history=history.copy();self.prior=prior
    def predict(self, queries):return materialize(self.history,queries,self.prior)
    def append_completed(self, rows, observed_at):
        if not rows.end_time.lt(observed_at).all():raise ValueError('Completion not yet observable')
        f=pd.concat([self.history,rows],ignore_index=True)
        if not f.job_id.is_unique:raise ValueError('Duplicate completed episode')
        self.history=f.sort_values(['end_time','job_id'],kind='stable').reset_index(drop=True)
    def save(self,path):
        from pathlib import Path
        import json
        p=Path(path);p.mkdir(parents=True,exist_ok=True)
        self.history.to_parquet(p/'history.parquet',index=False)
        (p/'prior.json').write_text(json.dumps(self.prior),encoding='utf-8')
    @classmethod
    def load(cls,path):
        from pathlib import Path
        import json
        p=Path(path);return cls(pd.read_parquet(p/'history.parquet'),json.loads((p/'prior.json').read_text()))
