from common10 import *
from calibration10 import *
from calibration_state10 import LANDMARKS,group_map
from metrics9 import stats as oldstats,tail_rows
import numpy as np,pandas as pd
def stats(y,g,q50,q90):
    s=oldstats(y,g,q50,q90)
    if len(y):
        positive=np.asarray(y)>0;ratio=np.asarray(q90)[positive]/np.asarray(y)[positive]
        s.update(median_Q90_actual_positive_ratio=float(np.median(ratio)) if len(ratio) else None,P90_Q90_actual_positive_ratio=float(np.quantile(ratio,.9)) if len(ratio) else None,zero_runtime_N=int((~positive).sum()))
    return s
def score_inputs(model,par,f,continuation):
    event=f.event.to_numpy(bool);cen=f.censored.to_numpy(bool);exact=np.flatnonzero(event);ci=np.flatnonzero(cen)
    t=f.loc[event,'runtime_seconds'].to_numpy(float);left=np.maximum(t-.5,0);right=t+.5
    ls=np.zeros(len(f));dh=np.ones(len(f));ls[exact]=model.logsf(par[exact],left,continuation);dh[exact]=model.interval_hazard(par[exact],left,right,continuation)
    cens=np.zeros(len(f));cens[ci]=model.logsf(par[ci],f.loc[cen,'duration_lower'].to_numpy(),continuation)
    landmarks=np.column_stack([model.logsf(par,t,continuation) for t in LANDMARKS])
    known=event[:,None]|(cen[:,None]&(f.duration_lower.to_numpy()[:,None]>LANDMARKS))
    truth=np.ones_like(landmarks);truth[exact]=f.loc[event,'runtime_seconds'].to_numpy()[:,None]>LANDMARKS
    return dict(event=event,censored=cen,ls=ls,dh=dh,cens=cens,landmarks=landmarks,known=known,truth=truth)
def distribution_metrics(inputs,map_assignments):
    n=len(inputs['event']);ll=np.zeros(n);pred=np.zeros_like(inputs['landmarks']);zero=0;monotone=True
    for mask,mapping in map_assignments:
        monotone&=mapping.audit();e=mask&inputs['event'];c=mask&inputs['censored']
        ll[e]=mapping.log_interval(inputs['ls'][e],inputs['dh'][e]);ll[c]=mapping.logsf(inputs['cens'][c])
        pred[mask]=np.exp(mapping.logsf(inputs['landmarks'][mask]))
        zero+=int(np.isneginf(ll[e]).sum())
    observed=inputs['event']|inputs['censored'];score=-ll[observed]
    finite=bool(np.isfinite(score).all());values=[]
    for j in range(len(LANDMARKS)):
        k=inputs['known'][:,j];values.append(float(np.mean((pred[k,j]-inputs['truth'][k,j])**2)) if k.any() else np.nan)
    return dict(proper_interval_NLL=float(np.mean(score)) if finite else None,proper_NLL_N=int(observed.sum()),zero_support_count=zero,proper_score_finite=finite,monotonicity_pass=bool(monotone),
        known_status_integrated_Brier=float(np.trapz(values,LANDMARKS)/(LANDMARKS[-1]-LANDMARKS[0])),Brier_scope='observed status landmarks15m..7d, not IPCW population IBS')
def gates(summary,fold,tail,queue,w0,remaining=None):
    support=tail.N.ge(100);l4=tail[tail.cohort.eq('gt4h')&support];l12=tail[tail.cohort.eq('gt12h')&support]
    q=queue.set_index('fold');w=w0.set_index('fold')
    checks=dict(OVERALL_Q90_GATE_PASS=.88<=summary['Q90_coverage']<=.92,TEMPORAL_STABILITY_GATE_PASS=summary['min_fold_coverage']>=.85,
        LONG_GT4H_GATE_PASS=summary['gt4h_coverage']>=.85 and bool((l4.Q90_coverage>=.80).all()) and len(l4)==5,
        LONG_GT12H_DIAGNOSTIC_PASS=summary['gt12h_coverage']>=.80 and bool((l12.Q90_coverage>=.70).all()) and len(l12)==5,
        PROPER_DISTRIBUTION_SCORE_VALID=bool(fold.proper_score_finite.all() and fold.monotonicity_pass.all() and fold.zero_support_count.sum()==0),
        RESERVATION_SHARPNESS_PASS=summary['reservation_to_W0']<=.8,
        PREAPRIL_QUEUE_GATE_PASS=bool((q.start_lt_H>=.95*w.start_lt_H).all() and q.capacity_violations.sum()==0 and q.forecast_horizon_exhausted.sum()==0 and q.causal_unresolved_at_horizon.sum()==0))
    if remaining is not None:checks['CONDITIONAL_REMAINING_GATE_PASS']=.88<=remaining['Q90_coverage']<=.92
    return {**{k:bool(v) for k,v in checks.items()},'eligible':all(checks.values()),'failed_gates':sum(not bool(v) for v in checks.values())}
def pooled(arm,parts,folds,w0reservation):
    f=pd.concat(parts,ignore_index=True);s=stats(f.y.to_numpy(),f.gpu.to_numpy(),f.q50.to_numpy(),f.q90.to_numpy());v=folds[folds.arm.eq(arm)]
    s.update(arm=arm,min_fold_coverage=float(v.Q90_coverage.min()),max_fold_coverage=float(v.Q90_coverage.max()),coverage_std=float(v.Q90_coverage.std(ddof=0)),
        reservation_to_W0=s['reserved_GPUh']/w0reservation,proper_interval_NLL=float(np.average(v.proper_interval_NLL,weights=v.proper_NLL_N)) if v.proper_score_finite.all() else None)
    for h in [4,8,12,24]:
        z=f[f.y>h*3600];s[f'gt{h}h_coverage']=float((z.y<=z.q90).mean());s[f'gt{h}h_N']=len(z)
    return s
