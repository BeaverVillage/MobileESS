import numpy as np,pandas as pd
def ratio(a,b):return float(a/b) if b>0 else None
def stats(f,q50,q90):
    y=f.runtime_seconds.to_numpy(float);g=f.num_gpus_req.to_numpy(float);w=f.requested_seconds.to_numpy(float)
    a=np.asarray(q50)+np.zeros(len(y));q=np.asarray(q90)+np.zeros(len(y));e=y-q;c=y<=q
    positive=y>0
    return dict(N=len(y),Q50_MAE=float(np.abs(y-a).mean()),Q50_RMSE=float(np.sqrt(np.mean((y-a)**2))),Q50_median_AE=float(np.median(np.abs(y-a))),Q50_WAPE=ratio(np.abs(y-a).sum(),y.sum()),
        Q90_coverage=float(c.mean()),Q90_calibration_error=float(c.mean()-.9),Q90_pinball=float(np.maximum(.9*e,-.1*e).mean()),
        mean_prediction_actual_ratio=float(np.mean(q[positive]/y[positive])) if positive.any() else None,ratio_zero_actual_excluded=int((~positive).sum()),total_prediction_actual_ratio=ratio(q.sum(),y.sum()),
        underprediction_rate=float((e>0).mean()),overprediction_rate=float((e<0).mean()),GPU_coverage=float(np.average(c,weights=g)),GPU_underprediction_rate=float(np.average(~c,weights=g)),
        reservation_GPUh=float((q*g).sum()/3600),actual_GPUh=float((y*g).sum()/3600),W0_reservation_GPUh=float((w*g).sum()/3600),
        reservation_to_actual_GPUh=ratio((q*g).sum(),(y*g).sum()),reservation_to_W0_GPUh=ratio((q*g).sum(),(w*g).sum()),
        overrun_job_fraction=float((e>0).mean()),GPU_weighted_overrun_job_fraction=float(np.average(e>0,weights=g)),overrun_GPUh=float((np.maximum(e,0)*g).sum()/3600),
        excess_reservation_GPUh=float((np.maximum(-e,0)*g).sum()/3600))
def strata(f):
    wall=pd.cut(f.requested_seconds,[-np.inf,900,1800,3600,7200,14400,np.inf],right=False,labels=['<15m','15-30m','30-60m','1-2h','2-4h','>=4h'])
    gpu=f.num_gpus_req.map(lambda x:str(int(x)) if x in [1,2,4,8] else '16+' if x>=16 else 'other')
    yield 'walltime',wall.astype(str)
    yield 'GPU',gpu
    yield 'QoS',f.qos.fillna('__MISSING__').astype(str)
    yield 'partition',f.partition.fillna('__MISSING__').astype(str)
    yield 'long_actual',pd.Series(np.where(f.runtime_seconds>14400,'>4h','<=4h'),index=f.index)
    yield 'high_GPU',pd.Series(np.where(f.num_gpus_req>=16,'16+','<16'),index=f.index)
def gate(f,p,baselines):
    s=stats(f,p[:,0],p[:,1]);long=f.runtime_seconds.to_numpy()>14400;hi=f.num_gpus_req.to_numpy()>=16
    checks=dict(overall=.88<=s['Q90_coverage']<=.92,gpu=.88<=s['GPU_coverage']<=.94,
      pinball=all(s['Q90_pinball']<=stats(f,b[:,0],b[:,1])['Q90_pinball']+1e-6 for b in baselines),
      sharpness=s['reservation_to_W0_GPUh'] is not None and s['reservation_to_W0_GPUh']<=.8,
      long=len(f[long])>=100 and np.mean(f.runtime_seconds.to_numpy()[long]<=p[long,1])>=.85,
      high_gpu=len(f[hi])>=100 and np.mean(f.runtime_seconds.to_numpy()[hi]<=p[hi,1])>=.85)
    return {'PASS':bool(all(checks.values())),'checks':{k:bool(v) for k,v in checks.items()},'metrics':s,'long_N':int(long.sum()),'high_GPU_N':int(hi.sum())}
def compare(f,preds,role):
    rows=[];groups=[]
    for name,p in preds.items():
        rows.append(dict(role=role,model=name,**stats(f,p[:,0],p[:,1])))
        for dim,values in strata(f):
            for val in sorted(values.unique()):
                mask=values.eq(val).to_numpy()
                groups.append(dict(role=role,model=name,dimension=dim,stratum=val,support_sufficient=int(mask.sum())>=100,**stats(f[mask],p[mask,0],p[mask,1])))
    return rows,groups
def uncertainty(f,p,baseline,role,name):
    day=f.submit_time.dt.strftime('%Y-%m-%d').to_numpy();unique=np.unique(day)
    if len(unique)<3:return []
    y=f.runtime_seconds.to_numpy();g=f.num_gpus_req.to_numpy();rng=np.random.default_rng(60928)
    vals=[]
    for d in unique:
        ix=day==d;e=y[ix]-p[ix,1];eb=y[ix]-baseline[ix,1]
        vals.append([ix.sum(),(e<=0).sum(),g[ix].sum(),(g[ix]*(e<=0)).sum(),(np.maximum(.9*e,-.1*e)-np.maximum(.9*eb,-.1*eb)).sum(),((p[ix,1]-baseline[ix,1])*g[ix]).sum()/3600])
    v=np.array(vals);b=v[rng.integers(len(v),size=(1000,len(v)))].sum(axis=1)
    est=v.sum(axis=0);methods={'coverage':(b[:,1]/b[:,0],est[1]/est[0]),'GPU_coverage':(b[:,3]/b[:,2],est[3]/est[2]),'paired_pinball_delta':(b[:,4]/b[:,0],est[4]/est[0]),'paired_reservation_GPUh_delta':(b[:,5],est[5])}
    return [dict(role=role,comparison=name,metric=k,estimate=float(e),low=float(np.quantile(a,.025)),high=float(np.quantile(a,.975)),days=len(v),draws=1000,unit='UTC submission day; uncertainty ignores unverified request measurement') for k,(a,e) in methods.items()]
