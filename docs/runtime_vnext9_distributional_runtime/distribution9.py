"""Distribution mathematics; no labels, identifiers or fitting at inference."""
import json
from pathlib import Path
import numpy as np,lightgbm as lgb,xgboost as xgb
from scipy.special import log_ndtr,ndtri_exp
QUANTILES=np.array([.5,.7,.8,.9,.95])
def age_matrix(e):
    return np.column_stack([np.log1p(e[:-1]),np.log1p(e[1:]),np.log1p(np.diff(e)),np.arange(len(e)-1)]).astype('float32')
def dmatrix(x,columns,categoricals):
    return xgb.DMatrix(np.asarray(x,dtype='float32'),feature_names=columns,feature_types=['c' if c in categoricals else 'q' for c in columns],enable_categorical=True,nthread=1)
class Distribution:
    def __init__(self,meta,boosters):self.meta=meta;self.boosters=boosters
    def parameters(self,x):
        a=np.asarray(x[self.meta['columns']],dtype='float32');kind=self.meta['kind']
        if kind=='D1':
            e=np.array(self.meta['edges']);age=age_matrix(e);k=len(age);result=[]
            for start in range(0,len(a),512):
                z=a[start:start+512];xx=np.column_stack([np.repeat(z,k,axis=0),np.tile(age,(len(z),1))])
                h=self.boosters[0].predict(xx,num_threads=1).reshape(len(z),k)
                result.append(-np.log1p(-np.clip(h,1e-7,1-1e-7))/np.diff(e))
            return np.concatenate(result) if result else np.empty((0,k))
        if kind=='D2':return self.boosters[0].predict(dmatrix(a,self.meta['columns'],self.meta['categoricals']),output_margin=True).astype(float)
        return np.maximum.accumulate(np.maximum(np.expm1(np.column_stack([b.predict(a,num_threads=1) for b in self.boosters])),0),axis=1)
    def logsf(self,par,t):
        t=np.broadcast_to(np.asarray(t,dtype=float),len(par))
        if self.meta['kind']=='D1':
            e=np.asarray(self.meta['edges']);idx=np.clip(np.searchsorted(e,t,side='right')-1,0,len(e)-2)
            cum=np.column_stack([np.zeros(len(par)),np.cumsum(par*np.diff(e),axis=1)])
            ans=-cum[np.arange(len(par)),idx]-par[np.arange(len(par)),idx]*(t-e[idx])
        else:
            z=(np.log1p(np.maximum(t,0))-par)/self.meta['scale'];noise=self.meta['noise']
            if noise=='normal':ans=log_ndtr(-z)
            elif noise=='logistic':ans=-np.logaddexp(0,z)
            else:ans=-np.exp(np.minimum(z,700))
        return np.where(t>=0,ans,0.)
    def inverse_logsf(self,par,logp):
        logp=np.broadcast_to(np.asarray(logp,dtype=float),len(par))
        if self.meta['kind']=='D1':
            e=np.asarray(self.meta['edges']);cum=np.cumsum(par*np.diff(e),axis=1);h=-logp
            idx=np.minimum(np.sum(cum<h[:,None],axis=1),len(e)-2)
            prev=np.column_stack([np.zeros(len(par)),cum])[np.arange(len(par)),idx]
            return e[idx]+(h-prev)/par[np.arange(len(par)),idx]
        noise=self.meta['noise']
        if noise=='normal':z=-ndtri_exp(logp)
        elif noise=='logistic':z=-logp+np.log(-np.expm1(logp))
        else:z=np.log(-logp)
        expo=par+self.meta['scale']*z
        if np.any(expo>700):raise FloatingPointError('AFT_QUANTILE_OVERFLOW')
        return np.maximum(np.expm1(expo),0)
    def quantiles(self,par,delta=0,quantiles=QUANTILES):
        delta=np.broadcast_to(np.asarray(delta),len(par))
        if self.meta['kind']=='D3':return np.maximum(par+delta[:,None],0)
        return np.column_stack([np.maximum(self.inverse_logsf(par,np.log1p(-q))+delta,0) for q in quantiles])
    def remaining(self,par,elapsed,delta=0,quantiles=(.5,.9)):
        elapsed=np.broadcast_to(np.asarray(elapsed,dtype=float),len(par));delta=np.broadcast_to(np.asarray(delta,dtype=float),len(par))
        if np.any(~np.isfinite(elapsed)|(elapsed<0)):raise ValueError('INVALID_ELAPSED')
        logs=self.logsf(par,elapsed-delta)
        q=np.column_stack([np.maximum(self.inverse_logsf(par,logs+np.log1p(-tau))+delta-elapsed,0) for tau in quantiles])
        return q,np.exp(logs),logs
    def save(self,path):
        path=Path(path);path.mkdir(parents=True,exist_ok=True)
        (path/'model.json').write_text(json.dumps(self.meta,indent=2),encoding='utf-8')
        for i,b in enumerate(self.boosters):
            if self.meta['kind']=='D2':(path/f'{i}.ubj').write_bytes(bytes(b.save_raw(raw_format='ubj')))
            else:(path/f'{i}.txt').write_text(b.model_to_string(),encoding='utf-8')
    @classmethod
    def load(cls,path):
        path=Path(path);meta=json.loads((path/'model.json').read_text());boosters=[]
        if meta['kind']=='D2':
            b=xgb.Booster();b.load_model(bytearray((path/'0.ubj').read_bytes()));b.set_param({'nthread':1,'device':'cpu'});boosters=[b]
        else:boosters=[lgb.Booster(model_str=p.read_text(encoding='utf-8')) for p in sorted(path.glob('*.txt'))]
        return cls(meta,boosters)
