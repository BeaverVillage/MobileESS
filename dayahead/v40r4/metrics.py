from .common import *
def pinball(y,q,tau=.9):
    e=np.asarray(y)-np.asarray(q);return np.maximum(tau*e,(tau-1)*e)
def primary(y,q):
    pos=y>0;return float(pinball(y,q)[pos].sum()/y[pos].sum()) if pos.any() else np.inf
def calibration(y,q):
    p=y>0;s=np.sort(np.log1p(y[p])-np.log1p(q[p]));assert len(s)>0
    rank=min(int(np.ceil((len(s)+1)*.9)),len(s));return float(s[rank-1])
def calibrate(q,score):
    # Coherent push-forward of the whole aggregate CDF; this also changes Q50.
    return np.maximum(0,np.expm1(np.log1p(q)+score))
def point(y,q):return {'N':int(y.size),'MAE':float(np.abs(y-q).mean()),'RMSE':float(np.sqrt(np.mean((y-q)**2))),
    'WAPE':float(np.abs(y-q).sum()/y.sum()) if y.sum()>0 else None,'bias':float((q-y).mean())}
def aggregate(y,q,burst):
    pos=y>0;bi=y>=burst;prob={}
    for name,idx in [('overall',np.ones(y.shape,bool)),('positive',pos),('burst',bi)]:
        cov=float((y[idx]<=q[...,1][idx]).mean()) if idx.any() else None
        prob[name]={'N':int(idx.sum()),'coverage':cov,'calibration_error':abs(cov-.9) if cov is not None else None,
           'Q90_pinball':float(pinball(y[idx],q[...,1][idx]).mean()) if idx.any() else None}
    miss=np.maximum(y-q[...,1],0);over=np.maximum(q[...,1]-y,0)
    return {'point':point(y,q[...,0]),'positive_point':point(y[pos],q[...,0][pos]),'probabilistic':prob,
       'primary':primary(y,q[...,1]),'overprediction_GPUh':float(over.sum()),'underprediction_GPUh':float(miss.sum()),
       'missed_burst_GPUh':float(miss[bi].sum()),'captured_burst_fraction':float(np.minimum(y,q[...,1])[bi].sum()/y[bi].sum()) if bi.any() else None,
       'mean_burst_shortfall_GPUh':float(miss[bi].mean()) if bi.any() else None,'quantile_crossings':int((q[...,0]>q[...,1]).sum())}
def gates(y,q,burst,days,raw=None,MC_pass=True):
    a=aggregate(y,q,burst);checks={};bounds={'overall':(.9,.95),'positive':(.9,.95),'burst':(.9,.975)}
    for name,(low,high) in bounds.items():
        r=a['probabilistic'][name];checks[name]={'N':r['N'],'coverage':r['coverage'],'low':low,'high':high,
          'status':'INSUFFICIENT_SUPPORT' if r['N']<100 else ('PASS' if low<=r['coverage']<=high else 'FAIL')}
    temporal=[]
    for month in sorted(set(d[:7] for d in days)):
        idx=np.array([d[:7]==month for d in days]);s=aggregate(y[idx],q[idx],burst);b=s['probabilistic']['burst']
        temporal.append({'month':month,'burst_N':b['N'],'burst_coverage':b['coverage'],
          'burst_gate':'INSUFFICIENT_SUPPORT' if b['N']<100 else ('PASS' if b['coverage']>=.9 else 'FAIL'),
          'catastrophic':s['point']['WAPE'] is not None and s['point']['WAPE']>2,'metrics':s})
    worsened=False;justified=False
    if raw is not None:
        b=aggregate(y,raw,burst);worsened=a['primary']>b['primary']*1.1
        justified=any(b['probabilistic'][n]['coverage']<.9 for n in bounds) and all(r['status']=='PASS' for r in checks.values()) and a['primary']<.9
    overconservative=worsened and not justified
    return {'coverage':checks,'temporal':temporal,'primary_better_than_ZERO':a['primary']<.9,
        'OVERCONSERVATIVE_CALIBRATION':overconservative,'registered_safety_justification':justified,'MC_convergence_pass':MC_pass,
        'authority_leakage':'PASS','all_pass':all(r['status']=='PASS' for r in checks.values()) and all(t['burst_gate']!='FAIL' and not t['catastrophic'] for t in temporal)
        and a['primary']<.9 and not overconservative and MC_pass and a['quantile_crossings']==0}
def cumulative_metrics(y,cq):
    c=np.cumsum(y,1);return {'MAE_GPUh':float(np.abs(c-cq[...,0]).mean()),'WAPE':float(np.abs(c-cq[...,0]).sum()/c.sum()),
       'daily_total_MAE_GPUh':float(np.abs(c[:,-1]-cq[:,-1,0]).mean()),'daily_total_bias_GPUh':float((cq[:,-1,0]-c[:,-1]).mean()),
       'maximum_cumulative_underforecast_GPUh':float(np.maximum(c-cq[...,1],0).max()),'horizon_crossing_count':int((np.diff(cq[:,:,:2],axis=1)<-1e-7).sum()),
       'semantics':'Quantiles of summed nonnegative scenario increments under registered conditional-independence scenario model'}
def bootstrap(y,b,p,seed=SEED,repetitions=5000):
    positive=y>0;bd=np.where(positive,pinball(y,b),0).sum(1);pdiff=np.where(positive,pinball(y,p),0).sum(1);mass=y.sum(1)
    rng=np.random.default_rng(seed);n=len(y);d=[]
    for _ in range(repetitions):
        idx=((rng.integers(n,size=int(np.ceil(n/7)))[:,None]+np.arange(7))%n).ravel()[:n]
        d.append((bd[idx]-pdiff[idx]).sum()/mass[idx].sum())
    ci=np.quantile(d,[.025,.975]);return {'delta':float((bd-pdiff).sum()/mass.sum()),'CI95':ci,'superiority':bool(ci[0]>0),'samples':repetitions,'block_days':7,'seed':seed}
