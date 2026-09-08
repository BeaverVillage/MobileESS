"""Positive-window reserve evaluation with calendar-day clusters."""
import numpy as np
import pandas as pd

def metrics(y,u,days):
    y=np.asarray(y,float); u=np.asarray(u,float); days=np.asarray(days).astype(str)
    original_n=len(y); available=np.isfinite(u); y=y[available]; u=u[available]; days=days[available]
    if len(y)==0 or not (y>0).any(): return {'support_complete':False,'N':original_n,'evaluated_N':len(y)}
    positive=y>0; yp=y[positive]; up=u[positive]; miss=np.maximum(y-u,0); over=np.maximum(u-y,0)
    misses=miss[miss>0]; ratio=up/yp; dayrows=[]
    for d in np.unique(days):
        m=days==d; p=m&positive
        dayrows.append({'day':d,'month':d[:7],'N':int(m.sum()),'positive_N':int(p.sum()),
            'positive_coverage':float(np.mean(y[p]<=u[p])) if p.any() else None,
            'under_GPUh':float(miss[m].sum()),'over_GPUh':float(over[m].sum())})
    supported=[r['positive_coverage'] for r in dayrows if r['positive_N']>=1]
    result={'support_complete':bool(available.all()),'N':original_n,'evaluated_N':len(y),'positive_N':int(positive.sum()),
        'positive_coverage':float(np.mean(yp<=up)),'overall_coverage_DIAGNOSTIC':float(np.mean(y<=u)),
        'mean_day_positive_coverage':float(np.mean(supported)),'supported_positive_days':len(supported),
        'zero_fraction':float(np.mean(~positive)),'under_GPUh':float(miss.sum()),'over_GPUh':float(over.sum()),
        'positive_shortfall_ratio':float(miss.sum()/yp.sum()),'positive_upper_WAPE':float(np.abs(yp-up).sum()/yp.sum()),
        'positive_pinball85':float(np.maximum(.85*(yp-up),-.15*(yp-up)).mean()),
        'miss_N':len(misses),'mean_miss_GPUh':float(misses.mean()) if len(misses) else 0.,
        'P90_miss_GPUh':float(np.quantile(misses,.9)) if len(misses) else 0.,
        'P95_miss_GPUh':float(np.quantile(misses,.95)) if len(misses) else 0.,
        'maximum_miss_GPUh':float(misses.max()) if len(misses) else 0.,
        'safe_to_actual_ratio':dict(zip(['median','P90','P95','P99'],np.quantile(ratio,[.5,.9,.95,.99]).tolist())),
        'day_clusters':dayrows}
    return result

def monthly(y,u,days):
    days=np.asarray(days).astype(str); months=np.array([d[:7] for d in days]); rows=[]
    for month in sorted(np.unique(months)):
        ix=months==month; m=metrics(np.asarray(y)[ix],np.asarray(u)[ix],days[ix])
        rows.append({'month':month,**{k:v for k,v in m.items() if k!='day_clusters'},
            'sufficient_support':m.get('supported_positive_days',0)>=5})
    return rows

def gates(m,monthrows,raw_under,anchor_over,static_over):
    if not m.get('support_complete',False): return {'PASS':False,'checks':{'calibration_support':False},'failure_reasons':['INSUFFICIENT_CALIBRATION_SUPPORT']}
    checks={'calibration_support':True,'positive_coverage_lower':m['positive_coverage']>=.85,
        'positive_coverage_upper':m['positive_coverage']<=.925,'supported_positive_days':m['supported_positive_days']>=5,
        'mean_day_coverage':m['mean_day_positive_coverage']>=.80,
        'supported_month_positive_coverage':all(r['positive_coverage']>=.8 for r in monthrows if r['sufficient_support']),
        'supported_month_mean_day_coverage':all(r['mean_day_positive_coverage']>=.8 for r in monthrows if r['sufficient_support']),
        'under_GPUh_below_own_raw_base':m['under_GPUh']<raw_under,
        'over_GPUh_below_TRAIN_Q95':m['over_GPUh']<anchor_over,
        'over_GPUh_below_R6_static_U2':m['over_GPUh']<static_over,
        'positive_upper_WAPE_below_200pct':m['positive_upper_WAPE']<2.}
    return {'PASS':all(checks.values()),'checks':checks,'failure_reasons':[k for k,v in checks.items() if not v]}

def select(candidates):
    eligible=[c for c,r in candidates.items() if r['gates']['PASS']]
    if not eligible: return 'NONE'
    if len(eligible)==1: return eligible[0]
    over={c:candidates[c]['metrics']['over_GPUh'] for c in eligible}; low=min(over.values()); high=max(over.values())
    if high-low<=.02*low: return 'R85_B1'
    return min(eligible,key=lambda c:over[c])
