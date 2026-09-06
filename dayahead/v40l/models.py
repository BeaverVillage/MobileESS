import math
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.special import ndtri
from .common import FEATURES,CATS
from .protocol import PARAMS,HIERARCHY,EXCESS_ALPHAS
from .data import keys

def causal(x):
    if list(x.columns)!=FEATURES:raise ValueError('NONCAUSAL_OR_UNKNOWN_FEATURES')
def signed_target(y,k0,*,provenance,positive_only=False):
    if not provenance:raise ValueError('OOF_PROVENANCE_REQUIRED')
    if positive_only:raise ValueError('POSITIVE_ONLY_NOT_UNCONDITIONAL_QUANTILE')
    return (np.asarray(y,float)-np.asarray(k0,float))/3600
def repair(k0,q90,q95):
    k0=np.asarray(k0,float);a=np.asarray(q90,float);b=np.asarray(q95,float)
    stats={'raw_Q95_below_Q90':int(np.sum(b<a)),'raw_Q90_below_K0':int(np.sum(a<k0)),'raw_Q95_below_K0':int(np.sum(b<k0))}
    a=np.maximum(k0,a);b=np.maximum(a,b)
    return np.column_stack([a,b]),stats
def order_quantile(score,alpha):
    v=np.asarray(score,float)
    if not 0<alpha<1:raise ValueError('INVALID_ALPHA')
    if not len(v) or not np.isfinite(v).all():raise ValueError('EMPTY_OR_INVALID_SCORES')
    k=math.ceil((len(v)+1)*alpha)
    return float(np.sort(v)[k-1]) if k<=len(v) else math.inf
def aft_bounds(lower,upper):
    lo=np.asarray(lower,float);up=np.asarray(upper,float)
    if np.any(~np.isfinite(lo)) or np.any(lo<=0) or np.any(np.isnan(up)) or np.any(up<lo):raise ValueError('INVALID_CENSOR_BOUNDS')
    return lo,up
def aft_quantile(mu,alpha,scale=1.):return np.exp(np.asarray(mu)+scale*ndtri(alpha))
def exceedance_quantile(p,conditional_q,alpha):
    p=np.asarray(p,float);q=np.maximum.accumulate(np.maximum(0,conditional_q),axis=1)
    if q.shape!=(len(p),len(EXCESS_ALPHAS)) or np.any((p<0)|(p>1)):raise ValueError('INVALID_EXCEEDANCE_CDF')
    result=np.zeros(len(p));active=alpha>1-p
    u=np.divide(alpha-1+p,p,out=np.zeros_like(p),where=p>0)
    for i in np.flatnonzero(active):result[i]=np.interp(u[i],[0.]+EXCESS_ALPHAS,np.r_[0.,q[i]])
    return result

class Quantile:
    def __init__(self,alphas,rounds=400,binary=False):
        self.alphas=list(alphas);self.rounds=rounds;self.binary=binary;self.categories={}
    def encode(self,x,fit=False):
        causal(x);z=x.copy()
        for c in CATS:
            if fit:self.categories[c]=sorted(z[c].astype(str).unique())
            z[c]=pd.Categorical(z[c].astype(str),categories=self.categories[c])
        return z
    def fit(self,x,y):
        z=self.encode(x,True);y=np.asarray(y,float)
        assert len(y)==len(z) and np.isfinite(y).all()
        params={**PARAMS,'objective':'binary:logistic' if self.binary else 'reg:quantileerror'}
        if not self.binary:
            assert all(0<a<1 for a in self.alphas)
            params['quantile_alpha']=self.alphas
        self.booster=xgb.train(params,xgb.DMatrix(z,label=y,enable_categorical=True,nthread=1),num_boost_round=self.rounds)
        self.n=len(y);return self
    def predict(self,x):
        z=self.encode(x);p=self.booster.predict(xgb.DMatrix(z,enable_categorical=True,nthread=1))
        return np.asarray(p,float).reshape(len(x),-1)

class Hierarchy:
    def __init__(self,minimum):self.minimum=minimum;self.tables=[]
    def fit(self,x,residual,*,block):
        if block!='calibration':raise ValueError('CALIBRATION_BLOCK_ONLY')
        if len(x)<100:raise ValueError('INSUFFICIENT_CALIBRATION')
        r=np.asarray(residual,float)
        for cols in HIERARCHY:
            ix={}
            for i,k in enumerate(keys(x,cols)):ix.setdefault(k,[]).append(i)
            self.tables.append({k:{'n':len(v),'q':np.array([order_quantile(r[v],a) for a in [.9,.95]])} for k,v in ix.items()})
        return self
    def predict(self,x,k0,hybrid=False,ml=None):
        kk=[keys(x,c) for c in HIERARCHY];raw=np.zeros((len(x),2));levels=np.zeros(len(x),int);counts=np.zeros(len(x),int)
        for i,state in enumerate(x.support_class):
            if hybrid and state=='STRONG_SUPPORT':raw[i]=ml[i];levels[i]=-1;counts[i]=int(x.exact_count.iloc[i]);continue
            if hybrid and state=='OUT_OF_SUPPORT':raw[i]=np.nan;levels[i]=-2;continue
            opts=[]
            for level,table in enumerate(self.tables):
                v=table.get(kk[level][i])
                if hybrid and state!='STRONG_SUPPORT' and level==0:continue
                if v and (v['n']>=self.minimum or level==3):opts.append((level,v))
            if not opts:raise ValueError('EMPTY_POOLED_FALLBACK')
            chosen=opts if hybrid and state=='REGIME_MISMATCH' else opts[:1]
            raw[i]=k0[i]+np.maximum(0,np.max([v['q'] for _,v in chosen],axis=0))
            levels[i]=chosen[0][0];counts[i]=chosen[0][1]['n']
        out,stats=repair(k0,raw[:,0],raw[:,1])
        return out,{'levels':{str(k):int((levels==k).sum()) for k in np.unique(levels)},'minimum':self.minimum,'crossing':stats}

def fit_cqr(y,raw,*,block):
    if block!='calibration':raise ValueError('CALIBRATION_BLOCK_ONLY')
    return np.array([order_quantile(np.asarray(y)-raw[:,i],alpha) for i,alpha in enumerate([.9,.95])])
