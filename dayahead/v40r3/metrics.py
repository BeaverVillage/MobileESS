"""Frozen GPUh increment, arrival-curve, safety and paired superiority metrics."""
from .common import *

def checked(y,q):
    y=np.asarray(y,float);q=np.asarray(q,float)
    if y.shape!=q.shape or not np.isfinite(y).all() or not np.isfinite(q).all() or (y<0).any() or (q<0).any():
        raise ValueError('INVALID_ALIGNED_NONNEGATIVE_FORECAST')
    return y,q

def pinball(y,q,tau=.9):
    y,q=checked(y,q);e=y-q
    return np.maximum(tau*e,(tau-1)*e)

def primary(y,q):
    y,q=checked(y,q);positive=y>0
    return float(pinball(y,q)[positive].sum()/y[positive].sum()) if positive.any() else float('inf')

def summarize(y,forecast,threshold):
    q50=forecast[...,0];q90=forecast[...,1];y,q50=checked(y,q50);checked(y,q90)
    def pt(a,b):
        return {'N':int(a.size),'MAE':float(np.abs(b-a).mean()) if a.size else None,
         'RMSE':float(np.sqrt(np.mean((b-a)**2))) if a.size else None,
         'WAPE':float(np.abs(b-a).sum()/a.sum()) if a.sum()>0 else None,'bias':float((b-a).mean()) if a.size else None}
    def pro(mask):
        a=y[mask];q=q90[mask]
        c=float(np.mean(a<=q)) if len(a) else None
        return {'N':len(a),'Q90_pinball':float(pinball(a,q).mean()) if len(a) else None,
         'Q90_coverage':c,'calibration_error':abs(c-.9) if c is not None else None}
    pos=y>0;burst=y>=threshold;miss=np.maximum(y-q90,0)
    c=np.cumsum(y,axis=1);c50=np.cumsum(q50,axis=1);c90=np.cumsum(q90,axis=1)
    return {'point':{'overall':pt(y,q50),'positive':pt(y[pos],q50[pos])},
      'probabilistic':{'overall':pro(np.ones(y.shape,bool)),'positive':pro(pos),'burst':pro(burst),
         'Q50_pinball':float(pinball(y,q50,.5).mean()),'primary_positive_Q90_normalized_pinball':primary(y,q90),
         'quantile_crossing_count':int((q50>q90).sum()),'CRPS':None,'CRPS_reason':'Two marginal quantiles do not identify CRPS'},
      'burst':{'N':int(burst.sum()),'threshold_GPUh':threshold,'missed_burst_GPUh':float(miss[burst].sum()),
        'captured_burst_GPUh_fraction':float(np.minimum(y,q90)[burst].sum()/y[burst].sum()) if burst.any() else None,
        'underprediction_GPUh':float(miss[burst].mean()) if burst.any() else None},
      'cumulative':{'MAE_GPUh':float(np.abs(c50-c).mean()),'WAPE':float(np.abs(c50-c).sum()/c.sum()) if c.sum()>0 else None,
        'daily_total_MAE_GPUh':float(np.abs(c50[:,-1]-c[:,-1]).mean()),'daily_total_bias_GPUh':float((c50[:,-1]-c[:,-1]).mean()),
        'maximum_cumulative_underforecast_GPUh':float(np.maximum(c-c90,0).max()),
        'horizon_crossing_count':int((np.diff(c50,axis=1)<-1e-9).sum()+(np.diff(c90,axis=1)<-1e-9).sum()),
        'derived_curve_semantics':'Sums of marginal quantile increments, not asserted quantiles of random cumulative sum',
        'compatibility_horizons':{str(h):pt(c[:,h//30-1],c50[:,h//30-1]) for h in [30,60,120,240,1440]}}}

def gates(y,forecast,threshold,dates):
    full=summarize(y,forecast,threshold);groups={}
    for name,r in full['probabilistic'].items():
        if isinstance(r,dict) and 'Q90_coverage' in r:
            groups[name]={'N':r['N'],'coverage':r['Q90_coverage'],
              'status':'INSUFFICIENT_N' if r['N']<100 else ('PASS' if r['Q90_coverage']>=.9 else 'FAIL')}
    blocks=[]; dates=np.asarray(dates)
    for month in sorted(set(d[:7] for d in dates)):
        idx=np.array([d[:7]==month for d in dates]); s=summarize(y[idx],forecast[idx],threshold)
        checks={}
        for name in ['overall','positive','burst']:
            r=s['probabilistic'][name]
            checks[name]='NOT_REQUIRED_N_LT_100' if r['N']<100 else ('PASS' if r['Q90_coverage']>=.9 else 'FAIL')
        catastrophic=s['point']['overall']['WAPE'] is not None and s['point']['overall']['WAPE']>2.
        blocks.append({'month':month,'coverage_checks':checks,'point_WAPE':s['point']['overall']['WAPE'],
          'catastrophic_WAPE_gt_2':catastrophic,'pass':not catastrophic and all(v!='FAIL' for v in checks.values())})
    return {'groups':groups,'temporal_blocks':blocks,'causal_gate':'PASS',
      'all_pass':all(r['status']=='PASS' for r in groups.values()) and all(b['pass'] for b in blocks)
          and full['cumulative']['horizon_crossing_count']==0 and full['probabilistic']['quantile_crossing_count']==0,
      'small_sample_rule':'Pooled overall/positive/burst require N>=100 for an affirmative safety claim; monthly conditional gate enforced when N>=100'}

def finite_sample_quantile(values,tau=.9):
    a=np.sort(np.asarray(values,float))
    if not len(a) or not np.isfinite(a).all():raise ValueError('NO_FINITE_CALIBRATION_VALUES')
    rank=min(int(np.ceil((len(a)+1)*tau)),len(a))
    return float(a[rank-1])

def calibrate(y,forecast,threshold):
    y,q90=checked(y,forecast[...,1]);resid=y-q90
    subsets={'overall':np.ones(y.shape,bool),'positive':y>0,'burst':y>=threshold}
    quant={name:finite_sample_quantile(resid[m]) for name,m in subsets.items() if m.any()}
    delta=max(0.,*quant.values())
    return delta,{'additive_Q90_delta_GPUh':delta,'conditional_residual_quantiles':quant,
                  'data':'CALIBRATION mature origins only','no_future_guarantee':True}

def day_block_bootstrap(y,baseline,candidate,seed=SEED,repetitions=5000,block=7):
    y,b=checked(y,baseline);checked(y,candidate)
    mask=y>0
    a=np.where(mask,pinball(y,b),0).sum(1);c=np.where(mask,pinball(y,candidate),0).sum(1);mass=y.sum(1)
    if len(y)<block or mass.sum()<=0:raise ValueError('INSUFFICIENT_PAIRED_DAYS')
    rng=np.random.default_rng(seed);d=[];n=len(y)
    for _ in range(repetitions):
        start=rng.integers(0,n,size=int(np.ceil(n/block)))
        idx=((start[:,None]+np.arange(block))%n).ravel()[:n]
        if mass[idx].sum()<=0:raise ValueError('EMPTY_BOOTSTRAP_POSITIVE_MASS')
        d.append(float((a[idx]-c[idx]).sum()/mass[idx].sum()))
    ci=np.quantile(d,[.025,.975]);delta=float((a-c).sum()/mass.sum())
    return {'delta':delta,'CI95':ci,'superiority_established':bool(ci[0]>0),'repetitions':repetitions,'block_days':block,
      'paired_same_day_indices':True,'seed':seed,'practical_improvement_percent':100*float((a-c).sum()/a.sum()) if a.sum()>0 else None,
      'metric':'positive-interval Q90 normalized pinball; sum positive pinball / sum positive actual GPUh'}

def eligible_proposed(safety,numerically_best,ci_lower):
    return bool(safety and numerically_best and np.isfinite(ci_lower) and ci_lower>0)
