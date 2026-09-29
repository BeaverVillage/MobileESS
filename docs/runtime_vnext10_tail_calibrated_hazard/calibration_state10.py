"""Causal landmark calibration; availability masks precede label access."""
from common10 import *
from calibration10 import *
import pandas as pd,numpy as np
LANDMARKS=np.array([900,1800,3600,7200,14400,28800,43200,86400,172800,259200,604800.])
def raw_landmarks(model,par,continuation):
    return np.column_stack([model.logsf(par,t,continuation) for t in LANDMARKS])
def statuses(pool,day,mode):
    day=pd.Timestamp(day);n=len(pool);known=np.zeros((n,len(LANDMARKS)),bool);positive=np.zeros_like(known)
    completed=pool.event&pool.end_time.lt(day)&pool.submit_time.lt(day)
    eligible_completed=completed.copy()
    effective=pool.observation_cutoff.where(pool.observation_cutoff.lt(day),day)
    unresolved=~completed&pool.start_time.notna()&pool.start_time.lt(effective)&pool.submit_time.lt(day)
    if mode.startswith('ROLLING'):
        lo=day-pd.Timedelta(days=int(mode.replace('ROLLING','')))
        eligible_completed&=pool.end_time.ge(lo);unresolved&=effective.ge(lo)
    ix=np.flatnonzero(eligible_completed);y=pool.loc[eligible_completed,'runtime_seconds'].to_numpy(float)
    known[ix]=True;positive[ix]=y[:,None]<=LANDMARKS
    ix2=np.flatnonzero(unresolved);elapsed=(effective[unresolved]-pool.loc[unresolved,'start_time']).dt.total_seconds().to_numpy()
    known[ix2]=elapsed[:,None]>LANDMARKS
    return known,positive,eligible_completed
def aggregate(bins,known,positive,mask):
    total=np.zeros(len(CENTERS));pos=np.zeros(len(CENTERS))
    for j in range(len(LANDMARKS)):
        m=mask&known[:,j];n=int(m.sum())
        if not n:continue
        total+=np.bincount(bins[m,j],minlength=len(CENTERS))/n
        pos+=np.bincount(bins[m,j],weights=positive[m,j].astype(float),minlength=len(CENTERS))/n
    return total,pos
def fit_state(pool,raw_bins,raw_risk,day,mode,family,conditioned,bounds):
    known,positive,completed=statuses(pool,day,mode);observed=known.any(axis=1)
    total,pos=aggregate(raw_bins,known,positive,np.ones(len(pool),bool))
    pooled=ProbabilityMap.fit(total,pos,family) if observed.sum()>=500 else ProbabilityMap()
    groups=np.digitize(raw_risk,bounds,right=True);mapping={};support=[];completed_y=np.full(len(pool),np.nan)
    completed_y[completed]=pool.loc[completed,'runtime_seconds'].to_numpy()
    for group in range(len(bounds)+1):
        m=groups==group;s=dict(group=group,N=int((m&observed).sum()),completed=int((m&completed).sum()),long_gt4h=int(np.sum(m&(completed_y>14400))),long_gt12h=int(np.sum(m&(completed_y>43200))))
        adequate=s['N']>=500 and s['completed']>=200 and s['long_gt4h']>=100 and s['long_gt12h']>=50
        if conditioned and adequate:
            tt,pp=aggregate(raw_bins,known,positive,m);mapping[str(group)]=ProbabilityMap.fit(tt,pp,family).state;fallback=False
        else:mapping[str(group)]=pooled.state;fallback=conditioned
        s.update(support_sufficient=adequate,pooled_fallback=fallback);support.append(s)
    maxend=pool.loc[completed,'end_time'].max();assert pd.isna(maxend) or maxend<pd.Timestamp(day)
    return dict(day=str(day),mode=mode,family=family,conditioned=conditioned,bounds=bounds,pooled=pooled.state,groups=mapping,support=support,
        known_landmark_pairs=int(known.sum()),unknown_landmark_pairs=int((~known).sum()),max_completion_used=str(maxend),
        FUTURE_CALIBRATION_EVENT_READS=0,FUTURE_CALIBRATION_RESIDUAL_READS=0,completed_N=int(completed.sum()),observed_N=int(observed.sum()))
def group_map(state,group):return ProbabilityMap(state['groups'].get(str(int(group)),state['pooled']))
