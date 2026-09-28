import numpy as np,pandas as pd
def safe(a,b):return float(a/b) if b>0 else None
def stats(f,p):
    y=f.runtime_seconds.to_numpy(float);g=f.num_gpus_req.to_numpy(float);wall=f.requested_seconds.to_numpy(float);a,q=np.asarray(p).T;e=y-q;c=e<=0
    pb=np.maximum(.9*e,-.1*e);res=np.ceil(q/900)*g*.25;wres=np.ceil(wall/900)*g*.25;actual=y*g/3600
    return dict(N=len(f),Q50_MAE=float(np.abs(y-a).mean()),Q90_coverage=float(c.mean()),Q90_pinball=float(pb.mean()),underprediction_rate=float((~c).mean()),
      total_prediction_actual_ratio=safe(q.sum(),y.sum()),mean_prediction_actual_positive_ratio=float(np.mean(q[y>0]/y[y>0])) if (y>0).any() else None,
      zero_runtime_N=int((y==0).sum()),GPU_Q50_MAE=float(np.average(np.abs(y-a),weights=g)),GPU_Q90_coverage=float(np.average(c,weights=g)),GPU_Q90_pinball=float(np.average(pb,weights=g)),GPU_underprediction_rate=float(np.average(~c,weights=g)),
      reservation_GPUh=float(res.sum()),continuous_prediction_GPUh=float((q*g).sum()/3600),actual_GPUh=float(actual.sum()),W0_reservation_GPUh=float(wres.sum()),
      reservation_to_actual_ratio=safe(res.sum(),actual.sum()),reservation_to_W0_ratio=safe(res.sum(),wres.sum()),overrun_GPUh=float((np.maximum(e,0)*g/3600).sum()),
      prediction_unique_Q90=int(np.unique(np.round(q,6)).size))
def strata(f):
    y=f.runtime_seconds;g=f.num_gpus_req
    b=pd.cut(y,[-np.inf,900,1800,3600,7200,14400,np.inf],labels=['T<=15m','15m<T<=30m','30m<T<=1h','1h<T<=2h','2h<T<=4h','T>4h'])
    for val in b.cat.categories:yield 'runtime',str(val),b.eq(val).to_numpy()
    for h in [4,8,12,24]:yield 'long',f'T>{h}h',y.gt(h*3600).to_numpy()
    gb=pd.cut(g,[0,1,4,8,15,np.inf],labels=['1GPU','2-4GPU','5-8GPU','9-15GPU','>=16GPU'])
    for val in gb.cat.categories:yield 'GPU',str(val),gb.eq(val).to_numpy()
    for col in ['qos','partition']:
        for val in sorted(f[col].astype(str).unique()):yield col,val,f[col].astype(str).eq(val).to_numpy()
def compare(f,preds,role):
    rows=[];st=[]
    for name,p in preds.items():
        rows.append(dict(role=role,model=name,**stats(f,p)))
        for dim,val,m in strata(f):
            if m.any():st.append(dict(role=role,model=name,dimension=dim,stratum=val,support_sufficient=int(m.sum())>=100,**stats(f[m],p[m])))
            else:st.append(dict(role=role,model=name,dimension=dim,stratum=val,N=0,support_sufficient=False))
    return rows,st
def gate(f,p,b0):
    s=stats(f,p);bs=stats(f,b0);long=f.runtime_seconds.to_numpy()>14400;hi=f.num_gpus_req.to_numpy()>=16
    checks=dict(calibration=.88<=s['Q90_coverage']<=.92,GPU_calibration=.88<=s['GPU_Q90_coverage']<=.94,sharp_pinball=s['Q90_pinball']<=bs['Q90_pinball']+1e-8,
      reservation=s['reservation_to_W0_ratio'] is not None and s['reservation_to_W0_ratio']<=.8,long=int(long.sum())>=100 and float(np.mean(f.runtime_seconds.to_numpy()[long]<=p[long,1]))>=.85,
      job_specific=s['prediction_unique_Q90']>=10,Q50=s['Q50_MAE']<=bs['Q50_MAE']+1e-8)
    high='INSUFFICIENT_SUPPORT' if int(hi.sum())<100 else 'PASS' if np.mean(f.runtime_seconds.to_numpy()[hi]<=p[hi,1])>=.85 else 'FAIL'
    return dict(PASS=all(bool(x) for x in checks.values()),checks={k:bool(v) for k,v in checks.items()},failed_checks=sum(not bool(x) for x in checks.values()),high_GPU_gate=high,
      high_GPU_N=int(hi.sum()),long_N=int(long.sum()),long_coverage=float(np.mean(f.runtime_seconds.to_numpy()[long]<=p[long,1])) if long.any() else None,metrics=s)
def uncertainty(f,p,b,role):
    day=f.submit_time.dt.strftime('%Y-%m-%d');rows=[]
    for d in sorted(day.unique()):
        m=day.eq(d).to_numpy();y=f.runtime_seconds.to_numpy()[m];g=f.num_gpus_req.to_numpy()[m];long=y>14400
        e=y-p[m,1];eb=y-b[m,1]
        rows.append([len(y),np.sum(np.maximum(.9*e,-.1*e)-np.maximum(.9*eb,-.1*eb)),np.sum(np.abs(y-p[m,0])-np.abs(y-b[m,0])),
          np.sum((np.ceil(p[m,1]/900)-np.ceil(b[m,1]/900))*g*.25),np.sum(y*g/3600),int(long.sum()),np.sum((e[long]>0).astype(int)-(eb[long]>0).astype(int))])
    z=np.array(rows);rng=np.random.default_rng(800928);bs=z[rng.integers(len(z),size=(1000,len(z)))].sum(axis=1);est=z.sum(axis=0);out=[]
    for name,num,den in [('pinball_difference',1,0),('MAE_difference',2,0),('reservation_ratio_difference',3,4),('long_underprediction_difference',6,5)]:
        good=bs[:,den]>0;dist=bs[good,num]/bs[good,den]
        out.append(dict(role=role,comparison='SELECTED - B0',metric=name,estimate=safe(est[num],est[den]),low=float(np.quantile(dist,.025)),high=float(np.quantile(dist,.975)),days=len(z),draws=1000,valid_draws=int(good.sum()),confidence_supported=len(z)>=3,unit='paired UTC submit-day bootstrap; few days and provenance uncertainty limit inference'))
    return out
