"""Inference-only quantiles using frozen request descriptors and observed elapsed."""
from pathlib import Path
import json,numpy as np,pandas as pd,lightgbm as lgb
from features8 import engineer
RAW=['num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib','requested_seconds','array_index','qos','partition','account']
EXTRA=['elapsed_seconds','elapsed_hours','log_elapsed','elapsed_walltime_ratio','walltime_minus_elapsed','checkpoint_index']
def features(records,pre,elapsed=None):
    f=pd.DataFrame(records);x=engineer(f.reindex(columns=RAW),pre['categorical_mappings'])
    if elapsed is not None:
        e=np.broadcast_to(np.asarray(elapsed,float),len(f));w=pd.to_numeric(f.requested_seconds,errors='coerce').to_numpy();w=np.where(np.isfinite(w)&(w>0),w,pre['walltime_fallback'])
        x['elapsed_seconds']=e;x['elapsed_hours']=e/3600;x['log_elapsed']=np.log1p(e);x['elapsed_walltime_ratio']=e/w;x['walltime_minus_elapsed']=w-e;x['checkpoint_index']=np.floor(e/1800)
    return x
def denominator(records,pre):
    f=pd.DataFrame(records);w=pd.to_numeric(f.requested_seconds,errors='coerce').to_numpy();return np.where(np.isfinite(w)&(w>0),w,pre['walltime_fallback'])
def ordered(q):
    q=np.asarray(q,float).copy();count=int(np.sum((q[:,0]<0)|(q[:,1]<q[:,0])|(q[:,1]<0)))
    q[:,0]=np.maximum(q[:,0],0);q[:,1]=np.maximum(q[:,1],q[:,0]);return q,count
class Quantiles:
    def __init__(self,meta,boosters):self.meta=meta;self.boosters=boosters;self.pre=meta['preprocessing']
    def predict(self,records,elapsed=None,threads=1):
        x=features(records,self.pre,elapsed)[self.meta['columns']];q=np.column_stack([self.boosters[k].predict(x,num_threads=threads) for k in ['Q50','Q90']])
        kind=self.meta['target']
        if kind=='LOG':q=np.expm1(q)
        elif kind=='REL':q=np.exp(q)*(denominator(records,self.pre)[:,None]+1)-1
        return ordered(q)
    def save(self,path):
        p=Path(path);p.mkdir(parents=True,exist_ok=True);(p/'model.json').write_text(json.dumps(self.meta,indent=2),encoding='utf-8')
        for k,b in self.boosters.items():(p/(k+'.txt')).write_text(b.model_to_string(),encoding='utf-8')
    @classmethod
    def load(cls,path):
        p=Path(path);m=json.loads((p/'model.json').read_text());return cls(m,{k:lgb.Booster(model_str=(p/(k+'.txt')).read_text(encoding='utf-8')) for k in ['Q50','Q90']})
