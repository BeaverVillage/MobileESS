"""Prospective Q50 candidates; public prediction input is causal features only."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.optimize import linprog
from scipy.sparse import csr_matrix,eye,hstack,vstack
from .common import FEATURES,FEATURES9,CATS
from .protocol import LGB,HAZARD_EDGES

def features(f):
    x=f[FEATURES9].copy();t=pd.to_datetime(f.submit_time,utc=True)
    x['submit_hour']=t.dt.hour.astype(float);x['submit_dow']=t.dt.dayofweek.astype(float);x['submit_week']=t.dt.isocalendar().week.astype(float)
    x['hardware']=np.where(x.partition.astype(str).str.contains('h100',case=False),'H100','OTHER_GPU')
    x['standby']=x.qos.astype(str).str.lower().eq('standby').astype(float)
    for c in CATS:x[c]=x[c].fillna('__MISSING__').astype(str)
    for c in set(FEATURES)-set(CATS):x[c]=pd.to_numeric(x[c],errors='coerce')
    return x[FEATURES]
def causal(x):
    if list(x.columns)!=FEATURES:raise ValueError('NONCAUSAL_OR_UNKNOWN_FEATURES')
    return x
def normalized_target(y,req):
    y,req=np.asarray(y,float),np.asarray(req,float)
    if np.any(~np.isfinite(req)) or np.any(req<=0):raise ValueError('INVALID_WALLTIME')
    return np.log((y+1)/(req+1))
def normalized_inverse(z,req):return np.maximum(0,np.exp(z)*(np.asarray(req,float)+1)-1)
def valid_prediction(p):
    if not np.isfinite(p).all() or (p<0).any():raise ValueError('INVALID_PREDICTION')
    return p
def mixture_cdf(logt,prob,mu,residuals):
    return prob*np.searchsorted(residuals[0],logt-mu[0],side='right')/len(residuals[0])+(1-prob)*np.searchsorted(residuals[1],logt-mu[1],side='right')/len(residuals[1])
def mixture_quantile(prob,mu,residuals,alpha=.5):
    low=np.zeros(len(prob));high=np.maximum(0,np.maximum(mu[0]+residuals[0][-1],mu[1]+residuals[1][-1]))+1e-10
    for _ in range(64):
        mid=(low+high)/2;at=mixture_cdf(mid,prob,mu,residuals)
        high=np.where(at>=alpha,mid,high);low=np.where(at>=alpha,low,mid)
    return valid_prediction(np.expm1(high))

class Central:
    def __init__(self,kind):self.kind=kind;self.categories={};self.models=[]
    def encode(self,x,fit=False):
        causal(x);z=x.copy()
        for c in CATS:
            if fit:self.categories[c]=sorted(x[c].unique().tolist())
            z[c]=pd.Categorical(z[c],categories=self.categories[c])
        return z
    def fit(self,x,y,*,early=None,times=None,end_times=None,fit_before=None,c0=None,c0_fit_times=None,submit_times=None):
        z=self.encode(x,True);y=np.asarray(y,float)
        assert np.isfinite(y).all() and (y>=0).all()
        self.training_rows=len(y)
        if self.kind.startswith('K1_'):
            if c0_fit_times is None or submit_times is None:raise ValueError('OOF_PROVENANCE_REQUIRED')
            if not (pd.DatetimeIndex(submit_times)>=pd.DatetimeIndex(c0_fit_times)).all():raise ValueError('SELF_FIT_RESIDUAL')
            if not (pd.DatetimeIndex(end_times)<pd.Timestamp(fit_before,tz='UTC')).all():raise ValueError('FUTURE_RESIDUAL_LABEL')
            target=(y-np.asarray(c0,float))/3600
            obj='huber' if 'HUBER' in self.kind else 'quantile' if 'Q50' in self.kind else 'regression_l1'
            kw={'alpha':.9} if obj=='huber' else {'alpha':.5} if obj=='quantile' else {}
            self.models=[lgb.LGBMRegressor(**LGB,objective=obj,**kw).fit(z,target)]
        elif self.kind=='K2_NORMALIZED_Q50':
            target=normalized_target(y,x.requested_seconds)
            self.models=[lgb.LGBMRegressor(**LGB,objective='quantile',alpha=.5).fit(z,target)]
        elif self.kind=='K3_SOFT_CDF_MEDIAN':
            split=pd.Timestamp(fit_before,tz='UTC')-pd.Timedelta(days=7)
            fit=np.asarray(pd.DatetimeIndex(end_times)<split)
            cal=np.asarray((pd.DatetimeIndex(times)>=split)&(pd.DatetimeIndex(end_times)<pd.Timestamp(fit_before,tz='UTC')))
            early=np.asarray(early,bool)
            if any((fit & k).sum()<100 or (cal & k).sum()<30 for k in [early,~early]):raise ValueError('CDF_COMPONENT_SUPPORT_UNAVAILABLE')
            self.gate=lgb.LGBMClassifier(**LGB).fit(z.loc[fit],early[fit].astype(int))
            self.residuals=[]
            for k in [early,~early]:
                a=fit&k;b=cal&k
                m=lgb.LGBMRegressor(**LGB,objective='regression').fit(z.loc[a],np.log1p(y[a]))
                self.models.append(m);self.residuals.append(np.sort(np.log1p(y[b])-m.predict(z.loc[b])))
            self.CDF_population={'fit':int(fit.sum()),'calibration':int(cal.sum()),'internal_boundary':str(split),'component_residual_rows':[len(x) for x in self.residuals]}
        elif self.kind=='K4_INTERVAL_HAZARD':
            zs=[];targets=[];lower=0
            for i,upper in enumerate(HAZARD_EDGES):
                risk=(y>=0) if i==0 else (y>lower)
                zz=z.loc[risk].copy();zz['hazard_interval']=float(i);zs.append(zz);targets.append((y[risk]<=upper).astype(int));lower=upper
            expanded=pd.concat(zs,ignore_index=True)
            params={**LGB,'n_estimators':160}
            self.models=[lgb.LGBMClassifier(**params).fit(expanded,np.concatenate(targets))]
            excess=y[y>HAZARD_EDGES[-1]]-HAZARD_EDGES[-1]
            self.tail_scale=float(excess.mean()) if len(excess) else HAZARD_EDGES[-1]
            self.expanded_rows=len(expanded)
        else:raise ValueError(self.kind)
        return self
    def predict(self,x,c0=None,alpha=.5):
        z=self.encode(x)
        if self.kind.startswith('K1_'):
            if c0 is None:raise ValueError('C0_REQUIRED')
            p=np.maximum(0,np.asarray(c0)+3600*self.models[0].predict(z))
        elif self.kind=='K2_NORMALIZED_Q50':p=normalized_inverse(self.models[0].predict(z),x.requested_seconds)
        elif self.kind=='K3_SOFT_CDF_MEDIAN':
            prob=self.gate.predict_proba(z)[:,1];mu=[m.predict(z) for m in self.models]
            p=mixture_quantile(prob,mu,self.residuals,alpha)
        else:
            survival=np.ones(len(z));p=np.full(len(z),np.nan);lower=0.
            for i,upper in enumerate(HAZARD_EDGES):
                zz=z.copy();zz['hazard_interval']=float(i)
                h=np.clip(self.models[0].predict_proba(zz)[:,1],1e-8,1-1e-8)
                old=1-survival;mass=survival*h;hit=np.isnan(p)&(old+mass>=alpha)
                p[hit]=lower+(upper-lower)*(alpha-old[hit])/mass[hit]
                survival*=1-h;lower=upper
            tail=np.isnan(p);p[tail]=lower+self.tail_scale*np.log(survival[tail]/(1-alpha))
        return valid_prediction(p)

def stacking_fit(predictions,y):
    p=np.asarray(predictions,float);y=np.asarray(y,float);n,k=p.shape
    # Scale seconds for numerical stability; optimize exact pinball/absolute loss with sparse constraints.
    z=csr_matrix(p/3600);identity=eye(n,format='csr')
    A=vstack([hstack([z,-identity]),hstack([-z,-identity])],format='csr')
    b=np.concatenate([y/3600,-y/3600]);c=np.concatenate([np.zeros(k),np.full(n,.5/n)])
    eq=csr_matrix(np.concatenate([np.ones(k),np.zeros(n)])[None,:])
    opt=linprog(c,A_ub=A,b_ub=b,A_eq=eq,b_eq=[1.],bounds=[(0,None)]*(k+n),method='highs')
    if not opt.success:raise ValueError('STACKING_OPTIMIZATION_FAILED:'+opt.message)
    w=opt.x[:k];w=w/w.sum()
    assert np.all(w>=0) and abs(w.sum()-1)<1e-10
    return w
