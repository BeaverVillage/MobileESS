"""Compact fitted predictor representation, independent of labels at inference."""
from pathlib import Path
import json,numpy as np,lightgbm as lgb
GRID=np.array([0.,.05,.25,.5,.75,.9,.99,1.])
def ordered(p):return np.maximum.accumulate(np.maximum(np.asarray(p,dtype=float),0),axis=1)
class Predictor:
    def __init__(self,meta,boosters,members=None):self.meta=meta;self.boosters=boosters;self.members=members or []
    def predict(self,x):
        kind=self.meta['kind'];cols=self.meta['columns'];n=len(x)
        if kind=='M5':return ordered(np.mean([m.predict(x) for m in self.members],axis=0))
        a=x[cols];pred=lambda key:self.boosters[key].predict(a,num_threads=1)
        if kind in ['M1','M2','M3']:
            p=np.column_stack([pred('Q50'),pred('Q90')])
            if kind=='M2':p=np.expm1(np.clip(p,-30,30))
            if kind=='M3':
                wall=x.requested_seconds.to_numpy();
                if not (np.isfinite(wall)&(wall>0)).all():raise ValueError('M3_REQUIRES_POSITIVE_REQUESTED_SECONDS')
                p=np.exp(np.clip(p,-30,30))*(wall[:,None]+1)-1
            return ordered(p)
        if kind=='M4':
            prob=np.clip(pred('LONG_PROB'),1e-9,1-1e-9);lo=np.zeros(n);upper=float(self.meta['long_upper'])
            short=ordered(np.column_stack([lo,*[np.clip(np.expm1(pred('S'+str(i))),0,14400) for i in range(6)],np.full(n,14400.)]))
            long=ordered(np.column_stack([np.full(n,14400.),*[np.clip(np.expm1(pred('L'+str(i))),14400,upper) for i in range(6)],np.full(n,upper)]))
            values=[]
            for tau in [.5,.9]:
                isshort=tau<=1-prob;u=np.where(isshort,tau/(1-prob),(tau-1+prob)/prob);u=np.clip(u,0,1)
                knots=np.where(isshort[:,None],short,long);idx=np.clip(np.searchsorted(GRID,u,side='right')-1,0,len(GRID)-2)
                weight=(u-GRID[idx])/(GRID[idx+1]-GRID[idx]);row=np.arange(n);values.append(knots[row,idx]+weight*(knots[row,idx+1]-knots[row,idx]))
            return ordered(np.column_stack(values))
        raise ValueError(kind)
    def save(self,path):
        path=Path(path);path.mkdir(parents=True,exist_ok=True)
        (path/'model.json').write_text(json.dumps(self.meta,indent=2),encoding='utf-8')
        for key,b in self.boosters.items():(path/(key+'.txt')).write_text(b.model_to_string(),encoding='utf-8')
        for i,m in enumerate(self.members):m.save(path/f'member{i}')
    @classmethod
    def load(cls,path):
        path=Path(path);meta=json.loads((path/'model.json').read_text());boosters={p.stem:lgb.Booster(model_str=p.read_text(encoding='utf-8')) for p in path.glob('*.txt')}
        members=[cls.load(p) for p in sorted(path.glob('member*')) if p.is_dir()]
        return cls(meta,boosters,members)
