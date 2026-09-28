"""CC4-v2.7 isolated, deterministic offline study. No optimizer imports."""
import os
for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[k]='1'
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'cc4_v2_hourly_future_workload'
P26=ROOT.parent/'cc4_v26_distributional_hybrid'
P21=ROOT.parent/'cc4_v21_causal_refit_hurdle'
TZ='Etc/GMT-10'
PARAMS=dict(num_leaves=15,learning_rate=.03,n_estimators=400,min_child_samples=50,n_jobs=1,deterministic=True,force_col_wise=True,random_state=20260924,verbosity=-1)
Z=np.load(BASE/'DATA.npz'); X0=Z['X']; Y0=Z['y']; DAYS=Z['days'].astype(str)
L=pd.read_csv(BASE/'DAY_LEDGER.csv'); ISS=pd.to_datetime(L.issue_time,utc=True)
AV=pd.to_datetime(L.label_matured_at,utc=True)
TRAIN=np.flatnonzero(L.split.eq('TRAIN')&L.eligible)
DEV=np.flatnonzero(L.split.eq('DEVELOPMENT')&L.eligible)
CAL=np.flatnonzero(L.split.eq('CALIBRATION')&L.eligible)
OOS=np.flatnonzero(DAYS>='2024-09-01')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple,np.ndarray,pd.Index)):return [clean(x) for x in v]
    if isinstance(v,(np.integer,np.bool_)):return v.item()
    if isinstance(v,(float,np.floating)):return float(v) if np.isfinite(v) else None
    if isinstance(v,(pd.Timestamp,Path)):return str(v)
    return v
def write(name,v):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(clean(v),f,indent=2,ensure_ascii=False,allow_nan=False)
def csv(name,rows):
    p=ROOT/name;assert not p.exists(),str(p)
    pd.DataFrame(rows).to_csv(p,index=False,lineterminator='\n')
def weights(tr,i):return np.asarray(np.exp2(-np.maximum((ISS.iloc[i]-pd.to_datetime(DAYS[tr],utc=True)).total_seconds()/86400,0)/30))
def member(i,mature=AV):return np.flatnonzero((mature<ISS.iloc[i])&(ISS<ISS.iloc[i])&L.split.ne('PURGE'))
def role_ids(role):
    # Extension was not eligible for the parent's original evaluation; report it
    # separately without altering the ledger's original eligible flag.
    return np.flatnonzero(L.split.eq(role)&(L.eligible if role!='OOS_EXTENSION' else True))
def metrics(y,q,burst,dt=1):
    y=np.asarray(y);q=np.asarray(q);e=y-q[...,0];r=y-q[...,1];total=y.sum();cov=np.mean(r<=0)
    out=dict(N_slots=y.size,actual_target_sum=float(total),actual_integrated_quantity=float(total*dt),Q90_coverage=cov,calibration_error=abs(cov-.9),Q90_pinball=np.maximum(.9*r,-.1*r).mean(),requirement_ratio=q[...,1].sum()/total if total else np.nan,excess_reserve_proxy=np.maximum(-r,0).sum()/total if total else np.nan,positive_coverage=np.mean(r[y>0]<=0) if (y>0).any() else np.nan,burst_coverage=np.mean(r[y>burst]<=0) if (y>burst).any() else np.nan,Q50_MAE=abs(e).mean(),Q50_RMSE=np.sqrt(np.mean(e**2)),Q50_WAPE=abs(e).sum()/total if total else np.nan,Q50_pinball=.5*abs(e).mean())
    if y.ndim==2:
        out.update(peak_magnitude_MAE=np.mean(abs(y.max(1)-q[...,0].max(1))),peak_timing_MAE_hours=np.mean(abs(y.argmax(1)-q[...,0].argmax(1)))*dt,daily_integrated_quantity_MAE=np.mean(abs(e.sum(1)*dt)))
        for frac in [.1,.05]:
            idx=np.argsort(y,axis=1,kind='stable')[:,-int(np.ceil(y.shape[1]*frac)):]
            out[f'top{int(frac*100)}_load_Q90_coverage']=np.mean(np.take_along_axis(r,idx,axis=1)<=0)
    return out
def fit(x,y,tr,i,groups=None):
    import lightgbm as lgb
    n=y.shape[1];q=np.zeros((n,2));imps=[];hashes=[]
    if groups is None:groups=[np.arange(n)]
    for slots in groups:
        a=x[tr][:,slots].reshape(-1,x.shape[-1]);b=np.log1p(y[tr][:,slots].ravel());w=np.repeat(weights(tr,i),len(slots))
        for k,tau in enumerate([.5,.9]):
            m=lgb.LGBMRegressor(objective='quantile',alpha=tau,**PARAMS).fit(a,b,sample_weight=w).booster_
            q[slots,k]=np.maximum(0,np.expm1(m.predict(x[i,slots],num_threads=1)))
            imps.append(np.stack([m.feature_importance('gain'),m.feature_importance('split')]))
            hashes.append(hashlib.sha256(m.model_to_string().encode()).hexdigest())
    q[:,1]=np.maximum(q[:,0],q[:,1]);assert np.isfinite(q).all()
    return q,np.sum(imps,axis=0),hashes
