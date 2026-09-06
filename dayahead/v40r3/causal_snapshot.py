"""Independent origin-time snapshots for incremental GPUh arrivals.

Only completed historical bins expose their GPUh. Future end values are never
encoded: the conservative bin-closure predicate is equivalent to replaying
all SUBMIT and observed END events through the origin.
"""
from .common import *

HISTORY=336  # Seven days of thirty-minute observations, fixed before fitting.
PAST_NAMES=['submission_count','mature_GPUh','mature_flag','maturity_age_hours',
            'hour_sin','hour_cos','weekday_sin','weekday_cos']
FUTURE_NAMES=['slot_fraction','lead_days','hour_sin','hour_cos','weekday_sin','weekday_cos','weekend']
for lag in [7,14,21,28]:FUTURE_NAMES += [f'seasonal_GPUh_lag{lag}d',f'seasonal_mature_lag{lag}d']
FORBIDDEN=['future_submit','future_start','future_end','future_completion','unfinished_final_runtime',
 'final_queue_wait','final_status','target_day_actual_GPUh','rolling_right_after_origin','retrospective_F30',
 'V40P_prediction','V40R_R2_outcomes','May_outcomes','request_GPU_aggregate','request_walltime','partition_QoS_as_submit_time_state']

def calendar(index):
    t=index.tz_convert(AEST); hour=t.hour.to_numpy()+t.minute.to_numpy()/60; dow=t.dayofweek.to_numpy()
    return np.column_stack([np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24),np.sin(2*np.pi*dow/7),np.cos(2*np.pi*dow/7)])

def history_values(bins,index,origin):
    if not index.isin(bins.index).all():raise ValueError('HISTORY_OUTSIDE_COMPLETE_SOURCE_COVERAGE')
    b=bins.loc[index]
    close=b.max_observed_end.copy()
    right=pd.Series(index+pd.Timedelta(minutes=30),index=index)
    close=close.where(close.notna()&close.gt(right),right)
    mature=(close.le(origin)&b.unresolved_end_count.eq(0)).to_numpy()
    work=np.where(mature,b.work_GPUh.to_numpy(),0.)
    age=np.where(mature,(origin-close).dt.total_seconds().to_numpy()/3600,0.)
    published_at=close.where(mature,origin)
    assert np.isfinite(work).all() and (age>=0).all() and published_at.le(origin).all()
    # A zero placeholder with mask=0 is missing information, not a mature zero label.
    return np.column_stack([b.submit_count.to_numpy(),work,mature.astype(float),age]),published_at,mature

def snapshot(bins,day):
    origin,begin,end=day_contract(day)
    history_index=pd.date_range(origin-pd.Timedelta(minutes=HISTORY*30),periods=HISTORY,freq='30min')
    past_values,available,mature=history_values(bins,history_index,origin)
    past=np.column_stack([past_values,calendar(history_index)])
    target_index=pd.date_range(begin,periods=K,freq='30min')
    cal=calendar(target_index); dow=target_index.tz_convert(AEST).dayofweek.to_numpy()
    future=np.column_stack([np.arange(K)/K,(target_index-origin).total_seconds()/86400,cal,(dow>=5).astype(float)])
    proofs=[pd.DataFrame({'operating_day':day,'forecast_origin':origin,'source_interval':history_index,
      'value_time':history_index+pd.Timedelta(minutes=30),'available_at':available.to_numpy(),
      'mature':mature,'published_GPUh':past_values[:,1],'stream':'PAST'})]
    for lag in [7,14,21,28]:
        idx=target_index-pd.Timedelta(days=lag)
        h,a,m=history_values(bins,idx,origin)
        future=np.column_stack([future,h[:,1],m.astype(float)])
        proofs.append(pd.DataFrame({'operating_day':day,'forecast_origin':origin,'source_interval':idx,
          'value_time':idx+pd.Timedelta(minutes=30),'available_at':a.to_numpy(),'mature':m,'published_GPUh':h[:,1],'stream':f'SEASONAL_{lag}D'}))
    assert past.shape==(HISTORY,len(PAST_NAMES)) and future.shape==(K,len(FUTURE_NAMES))
    assert np.isfinite(past).all() and np.isfinite(future).all()
    return past.astype('float32'),future.astype('float32'),pd.concat(proofs,ignore_index=True)

def incremental_target(jobs,day):
    """Independent direct target, all job service belongs to its submit interval."""
    origin,begin,end=day_contract(day)
    f=jobs.loc[jobs.model_cohort&jobs.submit_time.ge(begin)&jobs.submit_time.lt(end)]
    assert f.submit_time.gt(origin).all()
    idx=((utc_ns(f.submit_time)-begin.value)//pd.Timedelta(minutes=30).value).astype(int)
    y=np.bincount(idx,weights=f.work_GPUh.to_numpy(),minlength=K)
    available=max(end,f.end_time.max()) if len(f) else end
    return y,available

