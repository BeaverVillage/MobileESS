"""GPUh metrics; rolling-window sums count overlapping work repeatedly."""
import numpy as np
import pandas as pd

def pinball(y,q,alpha=.9):
    e=np.asarray(y)-np.asarray(q)
    return np.maximum(alpha*e,(alpha-1)*e)

def point(y,q):
    y=np.asarray(y,float); q=np.asarray(q,float); e=q-y
    if not len(y): return {k:None for k in ['N','MAE','RMSE','WAPE','bias','error_sum_GPUh']}
    return {'N':len(y),'MAE':float(np.abs(e).mean()),'RMSE':float(np.sqrt(np.mean(e**2))),
        'WAPE':float(np.abs(e).sum()/y.sum()) if y.sum()>0 else None,'bias':float(e.mean()),'error_sum_GPUh':float(e.sum())}

def central(y,q):
    p=np.asarray(y)>0
    return {'overall':point(y,q),'positive':point(np.asarray(y)[p],np.asarray(q)[p])}

def upper(y,u,days):
    y=np.asarray(y,float); u=np.asarray(u,float); days=np.asarray(days).astype(str); p=y>0
    if not p.any(): raise ValueError('No positive support')
    yp=y[p]; up=u[p]; ratio=up/yp
    day=[]
    for d in np.unique(days):
        m=days==d; mp=m&p
        day.append({'day':d,'month':d[:7],'windows':int(m.sum()),'positive_windows':int(mp.sum()),
            'positive_coverage':float(np.mean(y[mp]<=u[mp])) if mp.any() else None,
            'under_GPUh':float(np.maximum(y[m]-u[m],0).sum()),'over_GPUh':float(np.maximum(u[m]-y[m],0).sum()),
            'positive_under_GPUh':float(np.maximum(y[mp]-u[mp],0).sum()),'positive_over_GPUh':float(np.maximum(u[mp]-y[mp],0).sum())})
    supported=[d['positive_coverage'] for d in day if d['positive_windows']>=1]
    return {'N':len(y),'positive_N':int(p.sum()),'zero_fraction':float(np.mean(~p)), 'positive_fraction':float(p.mean()),
        'positive_coverage':float(np.mean(yp<=up)), 'overall_coverage_DIAGNOSTIC':float(np.mean(y<=u)),
        'positive_pinball':float(pinball(yp,up).mean()),'positive_normalized_pinball':float(pinball(yp,up).sum()/yp.sum()),
        'overall_pinball':float(pinball(y,u).mean()), 'positive_MAE':float(np.abs(up-yp).mean()),
        'positive_WAPE':float(np.abs(up-yp).sum()/yp.sum()), 'overall_MAE':float(np.abs(u-y).mean()),
        'overall_WAPE':float(np.abs(u-y).sum()/y.sum()),'under_GPUh':float(np.maximum(y-u,0).sum()),
        'over_GPUh':float(np.maximum(u-y,0).sum()),'positive_under_GPUh':float(np.maximum(yp-up,0).sum()),
        'positive_over_GPUh':float(np.maximum(up-yp,0).sum()),'safe_actual_ratio':dict(zip(['median','P90','P95','P99'],np.quantile(ratio,[.5,.9,.95,.99]).tolist())),
        'mean_supported_day_coverage':float(np.mean(supported)) if supported else None,
        'supported_days':len(supported),'day_clusters':day}

def monthly(y,q,u,days):
    days=np.asarray(days).astype(str); months=np.array([d[:7] for d in days]); rows=[]
    for month in np.unique(months):
        ix=months==month; m=upper(np.asarray(y)[ix],np.asarray(u)[ix],days[ix])
        supported=m['supported_days']>=5
        rows.append({'month':month,'days':len(np.unique(days[ix])),'positive_windows':m['positive_N'],
            'pooled_positive_coverage':m['positive_coverage'],'mean_day_coverage':m['mean_supported_day_coverage'],
            'under_GPUh':m['under_GPUh'],'over_GPUh':m['over_GPUh'],
            'Q50_WAPE':point(np.asarray(y)[ix],np.asarray(q)[ix])['WAPE'],'upper_WAPE':m['positive_WAPE'],
            'supported_positive_days':m['supported_days'],'sufficient_support':supported,
            'catastrophic_monthly_failure':bool(supported and (m['positive_coverage']<.8 or m['mean_supported_day_coverage']<.8)),
            'monthly_day_coverage_pass':bool(not supported or m['mean_supported_day_coverage']>=.88)})
    return rows

def gates(m,months,anchor_over,skill=True,baseline_under=None,is_B2=False,exposed=False):
    checks={'positive_coverage_lower':m['positive_coverage']>=.9,'positive_coverage_upper':m['positive_coverage']<=.975,
        'supported_days':m['supported_days']>=5,'mean_day_coverage':m['mean_supported_day_coverage']>=.88,
        'supported_month_day_coverage':all(r['monthly_day_coverage_pass'] for r in months),
        'no_catastrophic_month':not any(r['catastrophic_monthly_failure'] for r in months),
        'over_GPUh_below_TRAIN_Q95_anchor':m['over_GPUh']<anchor_over,'positive_upper_WAPE_below_300pct':m['positive_WAPE']<3,
        'development_skill':bool(skill) if is_B2 else True}
    if exposed:
        checks['under_GPUh_vs_B1']=bool(m['under_GPUh']<baseline_under) if is_B2 else bool(np.isclose(m['under_GPUh'],baseline_under,rtol=0,atol=1e-8))
    return {'PASS':all(checks.values()),'checks':checks,'failure_reasons':[k for k,v in checks.items() if not v]}

def choose(results):
    for candidate in ['U1','U2','U0']:
        if results[candidate]['PASS']: return candidate
    return 'NONE'
