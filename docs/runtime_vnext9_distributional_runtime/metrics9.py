import numpy as np,pandas as pd
from distribution9 import QUANTILES
BUCKETS=[('le15min',0,900),('15_30min',900,1800),('30_60min',1800,3600),('1_2h',3600,7200),('2_4h',7200,14400),('4_8h',14400,28800),('8_12h',28800,43200),('12_24h',43200,86400),('gt24h',86400,np.inf)]
def stats(y,gpu,q50,q90):
    y=np.asarray(y,float);gpu=np.asarray(gpu,float);q50=np.asarray(q50,float);q90=np.asarray(q90,float);n=len(y)
    if n==0:return dict(N=0)
    covered=y<=q90;err=y-q90;res=np.ceil(q90/900)*gpu*.25;actual=y*gpu/3600
    return dict(N=n,Q50_MAE=float(np.mean(abs(y-q50))),Q50_pinball=float(np.mean(abs(y-q50))*.5),
        Q90_MAE=float(np.mean(abs(y-q90))),Q90_coverage=float(covered.mean()),Q90_pinball=float(np.maximum(.9*err,-.1*err).mean()),
        underprediction_rate=float((~covered).mean()),GPU_weighted_coverage=float(np.average(covered,weights=gpu)),
        GPU_weighted_underprediction=float(np.average(~covered,weights=gpu)),Q90_predicted_actual_ratio=float(q90.sum()/y.sum()) if y.sum()>0 else None,
        reserved_GPUh=float(res.sum()),actual_GPUh=float(actual.sum()),reservation_actual_GPUh=float(res.sum()/actual.sum()) if actual.sum()>0 else None)
def tail_rows(y,g,q):
    out=[]
    for name,lo,hi in BUCKETS+[('gt4h',14400,np.inf),('gt8h',28800,np.inf),('gt12h',43200,np.inf),('gt24h_aggregate',86400,np.inf)]:
        m=((y>=lo) if lo==0 else (y>lo))&(y<=hi)
        out.append(dict(cohort=name,**stats(y[m],g[m],q[m,0],q[m,3])))
    return out
def correction(res):
    res=np.asarray(res,float);res=res[np.isfinite(res)]
    if len(res)<200:return 0.
    k=min(int(np.ceil(.9*(len(res)+1))),len(res))-1
    return float(np.partition(res,k)[k])
def calibration(cal,val,qcal,qval,mode):
    if mode=='NONE':return np.zeros(len(val)),[]
    start=val.submit_time.min().floor('D')
    if mode=='STATIC14':
        eligible=cal.event&cal.end_time.lt(start)
        # Do not calculate residuals before availability masking.
        residual=cal.loc[eligible,'runtime_seconds'].to_numpy()-qcal[eligible,3]
        delta=correction(residual)
        return np.full(len(val),delta),[dict(day=str(start),mode=mode,N=len(residual),delta=delta,max_source_end=str(cal.loc[eligible,'end_time'].max()),future_residual_reads=0)]
    window=int(mode.replace('ROLLING',''));pool=pd.concat([cal,val],ignore_index=True)
    q=np.concatenate([qcal[:,3],qval[:,3]]);out=np.zeros(len(val));audit=[]
    days=val.submit_time.dt.floor('D')
    for day in sorted(days.unique()):
        eligible=pool.event&pool.end_time.lt(day)&pool.end_time.ge(day-pd.Timedelta(days=window))
        residual=pool.loc[eligible,'runtime_seconds'].to_numpy()-q[eligible]
        delta=correction(residual);out[days.eq(day)]=delta
        latest=pool.loc[eligible,'end_time'].max();assert pd.isna(latest) or latest<day
        audit.append(dict(day=str(day),mode=mode,N=len(residual),delta=delta,max_source_end=str(latest),future_residual_reads=0))
    return out,audit
def distribution_scores(model,par,f,delta,edges):
    # Shared coarsened likelihood: exact event interval or survived complete censor intervals.
    mask=(f.event|f.censored).to_numpy();f=f.loc[mask].reset_index(drop=True);p=par[mask];d=np.asarray(delta)[mask]
    t=f.duration_lower.to_numpy(float);event=f.event.to_numpy(bool);edges=np.asarray(edges)
    idx=np.searchsorted(edges[1:],t,side='left');left=edges[np.minimum(idx,len(edges)-1)]
    right=np.where(idx<len(edges)-1,edges[np.minimum(idx+1,len(edges)-1)],np.inf)
    ls=model.logsf(p,left-d);ls=np.where(idx==0,0.,ls)
    rs=model.logsf(p,np.where(np.isfinite(right),right,0)-d);rs=np.where(np.isfinite(right),rs,-np.inf)
    # Stable log(exp(ls)-exp(rs)); zero-probability cells explicitly floored and counted.
    gap=np.minimum(rs-ls,0);logprob=ls+np.log(np.maximum(-np.expm1(gap),1e-300))
    ci=np.clip(np.searchsorted(edges,t,side='right')-1,0,len(edges)-1);ct=edges[ci]
    censlog=model.logsf(p,ct-d);censlog=np.where(ct==0,0.,censlog)
    likelihood=np.where(event,logprob,censlog)
    grid=np.array([0,900,1800,3600,7200,14400,28800,43200,86400,172800,259200.])
    scores=[]
    for t0 in grid:
        known=event|(f.duration_lower.to_numpy()>=t0)
        target=(f.duration_lower.to_numpy()>t0).astype(float)
        survival=np.exp(model.logsf(p,t0-d));scores.append(float(np.mean((target[known]-survival[known])**2)) if known.any() else 0.)
    hard_zero=event & ((right<=d) if model.meta['kind']=='D1' else (right<d))
    floored=int(np.sum(likelihood<=np.log(1e-300)))
    proper='INFINITE' if hard_zero.any() else 'NUMERICAL_FLOOR_UNRESOLVED' if floored else float(-likelihood.mean())
    return dict(coarsened_survival_NLL=float(-likelihood.mean()),NLL_N=len(f),proper_coarsened_survival_NLL=proper,zero_support_event_N=int(hard_zero.sum()),
        log_probability_floor_N=int(np.sum(likelihood<=np.log(1e-300))),known_status_72h_Brier=float(np.trapz(scores,grid)/grid[-1]),
        Brier_scope='observed-status administrative censoring; not IPCW population IBS',CRPS=None)
