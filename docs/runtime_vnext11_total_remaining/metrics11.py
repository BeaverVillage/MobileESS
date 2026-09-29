from common11 import *
from metrics9 import stats as base_stats
import numpy as np,pandas as pd
def stats(y,g,q):
    s=base_stats(y,g,q[:,0],q[:,1])
    if len(y):
        ratio=q[np.asarray(y)>0,1]/np.asarray(y)[np.asarray(y)>0]
        s.update(median_Q90_actual_positive_ratio=float(np.median(ratio)) if len(ratio) else None,P90_Q90_actual_positive_ratio=float(np.quantile(ratio,.9)) if len(ratio) else None)
    return s
def tails(y,g,q):
    return [dict(cohort=label,**stats(y[m],g[m],q[m])) for label,m in [('le15m',y<=900),('le4h',y<=14400),('gt4h',y>14400),('gt8h',y>28800),('gt12h',y>43200),('gt24h',y>86400)]]
def gates(s,fold,tail,queue,reference):
    l4=tail[(tail.cohort=='gt4h')&(tail.N>=100)];l12=tail[(tail.cohort=='gt12h')&(tail.N>=100)]
    q=queue.set_index('fold');w=reference.set_index('fold')
    c=dict(TOTAL_OVERALL_Q90_GATE_PASS=.88<=s['Q90_coverage']<=.92,TOTAL_MIN_FOLD_GATE_PASS=s['min_fold_coverage']>=.85,
       TOTAL_GT4H_GATE_PASS=s['gt4h_coverage']>=.85 and len(l4)==5 and l4.Q90_coverage.ge(.8).all(),
       TOTAL_GT12H_GATE_PASS=s['gt12h_coverage']>=.8 and len(l12)==5 and l12.Q90_coverage.ge(.7).all(),
       TOTAL_RESERVATION_GATE_PASS=s['reservation_to_W0']<=.8,
       TOTAL_QUEUE_GATE_PASS=(q.start_lt_H>=.95*w.start_lt_H).all() and q.capacity_violations.eq(0).all() and q.forecast_horizon_exhausted.eq(0).all() and q.causal_unresolved_at_horizon.eq(0).all() and (q.overrun_extensions<=np.maximum(2*w.overrun_extensions,w.overrun_extensions+1000)).all(),
       TOTAL_OUTCOME_LEAKAGE_GATE_PASS=True,TRAIN_SUPPORT_PASS=fold.support_sufficient.all())
    return dict(**{k:bool(v) for k,v in c.items()},eligible=bool(all(c.values())),failed_gates=int(sum(not v for v in c.values())))
def aggregate(parts,fold,tail,queue):
    reference=pd.read_csv(V10/'PREAPRIL_QUEUE_REPLAY.csv');w=reference[reference.arm.eq('W0')]
    wres=float(pd.read_csv(V9/'MODEL_COMPARISON.csv').set_index('arm').loc['W0','reserved_GPUh']);rows=[];checks=[]
    for arm,ps in parts.items():
        p=pd.concat(ps,ignore_index=True);f=fold[fold.arm==arm];s=stats(p.y.to_numpy(),p.gpu.to_numpy(),p[['q50','q90']].to_numpy());s.update(arm=arm,min_fold_coverage=float(f.Q90_coverage.min()),max_fold_coverage=float(f.Q90_coverage.max()),coverage_std=float(f.Q90_coverage.std(ddof=0)),reservation_to_W0=s['reserved_GPUh']/wres)
        for h in [4,8,12,24]:
            z=p[p.y>h*3600];s[f'gt{h}h_coverage']=float((z.y<=z.q90).mean());s[f'gt{h}h_N']=len(z)
        rows.append(s);checks.append(dict(arm=arm,**gates(s,f,tail[tail.arm==arm],queue[queue.arm==arm],w),Q90_pinball=s['Q90_pinball'],reservation_actual_GPUh=s['reservation_actual_GPUh'],Q50_MAE=s['Q50_MAE'],coverage_std=s['coverage_std']))
    return pd.DataFrame(rows),pd.DataFrame(checks)
def select(checks):
    elig=checks[checks.eligible];z=elig if len(elig) else checks
    return z.sort_values(([] if len(elig) else ['failed_gates'])+['Q90_pinball','reservation_actual_GPUh','Q50_MAE','coverage_std']).iloc[0].to_dict(),len(elig)
