"""Separate causal nominal prediction, conditional bounds and reserve envelopes."""
from collections import Counter
import math
import numpy as np
import pandas as pd
import lightgbm as lgb
from .contracts import FEATURES, FEATURES9, CATEGORICAL, LGB, WALL_BUCKETS, Q
from .firewall import causal_matrix

def ceil_seconds(values, unit=900):
    a=np.asarray(values,dtype=float)
    if np.any(~np.isfinite(a)) or np.any(a<0) or unit<=0:
        raise ValueError('INVALID_DURATION')
    return np.ceil(a/unit).astype(np.int64)*unit

def occupancy_slots(start, duration, unit=300):
    """Every grid cell intersecting the half-open interval [start,start+duration)."""
    if not np.isfinite(start) or not np.isfinite(duration) or duration<0 or unit<=0:
        raise ValueError('INVALID_INTERVAL')
    if duration==0:
        return np.array([],dtype=np.int64)
    return np.arange(math.floor(start/unit), math.ceil((start+duration)/unit),dtype=np.int64)

def raw_features(frame):
    """Training adapter deliberately projects a separate feature-only frame."""
    x=frame[FEATURES9].copy()
    t=pd.to_datetime(frame.submit_time,utc=True)
    x['submit_hour']=t.dt.hour.astype(float)
    x['submit_dow']=t.dt.dayofweek.astype(float)
    x['submit_week']=t.dt.isocalendar().week.astype(float)
    x['hardware']=np.where(x.partition.astype(str).str.lower().str.contains('h100'), 'H100', 'OTHER_GPU')
    x['standby']=(x.qos.astype(str).str.lower()=='standby').astype(int)
    for c in CATEGORICAL:
        x[c]=x[c].fillna('__MISSING__').astype(str)
    for c in set(FEATURES)-set(CATEGORICAL):
        x[c]=pd.to_numeric(x[c],errors='coerce')
    return x[FEATURES]

class CausalModel:
    def __init__(self, kind):
        self.kind=kind
        self.categories={}
        self.models=[]
        self.smearing=[]

    def encode(self, x, fit=False):
        causal_matrix(x)
        z=x.copy()
        for c in CATEGORICAL:
            if fit:
                self.categories[c]=sorted(set(x[c].astype(str)))
            z[c]=pd.Categorical(x[c],categories=self.categories[c])
        return z

    def fit(self, x, y, *, early_target=None):
        z=self.encode(x,True)
        y=np.asarray(y,dtype=float)
        if not np.isfinite(y).all() or np.any(y<0):
            raise ValueError('BAD_TRAINING_LABEL')
        if self.kind=='C3_QUANTILE':
            for alpha in [.5,.9,.95]:
                m=lgb.LGBMRegressor(**LGB,objective='quantile',alpha=alpha).fit(z,y)
                self.models.append(m)
        elif self.kind=='C2_MIXTURE':
            early=np.asarray(early_target,dtype=bool)
            if len(early)!=len(y) or early.all() or not early.any():
                raise ValueError('MIXTURE_REQUIRES_TWO_HISTORICAL_REGIMES')
            self.gate=lgb.LGBMClassifier(**LGB).fit(z,early.astype(int))
            for mask in [early,~early]:
                model=lgb.LGBMRegressor(**LGB,objective='regression').fit(z.loc[mask],np.log1p(y[mask]))
                smear=float(np.mean(np.exp(np.log1p(y[mask])-model.predict(z.loc[mask]))))
                self.models.append(model)
                self.smearing.append(smear)
        else:
            objective={'C1_L1':'regression_l1','C1_LOG':'regression','C1_HUBER':'huber','C1_Q50':'quantile'}[self.kind]
            target=np.log1p(y) if self.kind=='C1_LOG' else y/3600 if self.kind=='C1_HUBER' else y
            kw={'alpha':.5} if self.kind=='C1_Q50' else {'alpha':.9} if self.kind=='C1_HUBER' else {}
            self.models=[lgb.LGBMRegressor(**LGB,objective=objective,**kw).fit(z,target)]
        return self

    def predict(self,x):
        z=self.encode(x)
        if self.kind=='C2_MIXTURE':
            prob=self.gate.predict_proba(z)[:,1]
            comp=[np.maximum(0,np.exp(m.predict(z))*s-1) for m,s in zip(self.models,self.smearing)]
            p=prob*comp[0]+(1-prob)*comp[1]
            return np.column_stack([p,p,p])
        raw=np.column_stack([m.predict(z) for m in self.models])
        if self.kind=='C1_LOG': raw=np.expm1(raw)
        if self.kind=='C1_HUBER': raw=raw*3600
        raw=np.maximum(raw,0)
        if raw.shape[1]==1: raw=np.repeat(raw,3,axis=1)
        return np.maximum.accumulate(raw,axis=1)

def key_rows(x, columns):
    if not columns:
        return [()] * len(x)
    return [tuple('__NA__' if pd.isna(v) else str(v) for v in row) for row in x[columns].itertuples(index=False,name=None)]

def groups(x):
    causal_matrix(x)
    g=x[['hardware','standby']].copy()
    g['wall_bucket']=np.searchsorted(WALL_BUCKETS,x.requested_seconds,side='left').astype(str)
    return g

class SupportGuard:
    def __init__(self,x,min_support):
        causal_matrix(x)
        self.minimum=min_support
        self.exact=Counter(key_rows(x,FEATURES9))
        self.near=Counter(key_rows(x,FEATURES9[1:]))
        self.wall=Counter(key_rows(x,['hardware','requested_seconds']))
        self.hw=Counter(key_rows(x,['hardware']))
        self.regime=Counter(key_rows(groups(x),['hardware','standby','wall_bucket']))

    def predict(self,x):
        causal_matrix(x)
        counts=[]
        for table,columns,frame in [(self.exact,FEATURES9,x),(self.near,FEATURES9[1:],x),
           (self.wall,['hardware','requested_seconds'],x),(self.hw,['hardware'],x),
           (self.regime,['hardware','standby','wall_bucket'],groups(x))]:
            counts.append(np.array([table[k] for k in key_rows(frame,columns)],dtype=int))
        exact,near,wall,hw,regime=counts
        label=np.where(exact>=self.minimum,'STRONG_SUPPORT',np.where(exact>0,'SPARSE_SUPPORT',
               np.where(near>=self.minimum,'REGIME_MISMATCH','OUT_OF_SUPPORT')))
        return pd.DataFrame(dict(zip(['exact_count','near_count','walltime_count','hardware_count','regime_count'],counts)),index=x.index).assign(support_class=label)

def conformal_q(residual,coverage):
    a=np.sort(np.maximum(np.asarray(residual,dtype=float),0))
    if not len(a) or not np.isfinite(a).all():
        raise ValueError('EMPTY_OR_NONFINITE_CALIBRATION')
    return float(a[min(len(a),math.ceil((len(a)+1)*coverage))-1])

class ConditionalCalibration:
    levels=[['hardware','standby','wall_bucket'],['hardware','wall_bucket'],['hardware'],[]]
    def __init__(self,minimum):
        self.minimum=minimum
        self.tables=[]

    def fit(self,x,y,pred):
        g=groups(x)
        y=np.asarray(y)
        if pred.shape != (len(x),3): raise ValueError('QUANTILE_SHAPE')
        for cols in self.levels:
            rows={}
            indices={}
            for i,k in enumerate(key_rows(g,cols)):
                indices.setdefault(k,[]).append(i)
            for key, ix in indices.items():
                rows[key]={'n':len(ix),'q90':conformal_q(y[ix]-pred[ix,1],.9),
                           'q95':conformal_q(y[ix]-pred[ix,2],.95)}
            self.tables.append(rows)
        return self

    def predict(self,x,pred,support):
        g=groups(x)
        keys=[key_rows(g,cols) for cols in self.levels]
        output=pred.copy()
        fallback=[]
        for i,state in enumerate(support.support_class):
            eligible=[]
            for level,table in enumerate(self.tables):
                v=table.get(keys[level][i])
                if v and (v['n']>=self.minimum or level==3) and (state=='STRONG_SUPPORT' or level>0):
                    eligible.append((level,v))
            if not eligible: raise ValueError('NO_POOLED_CALIBRATION')
            chosen=eligible[:1] if state=='STRONG_SUPPORT' else eligible
            q90=max(v['q90'] for _,v in chosen)
            q95=max(v['q95'] for _,v in chosen)
            output[i,1]=max(pred[i,0],pred[i,1]+q90)
            output[i,2]=max(output[i,1],pred[i,2]+q95)
            if state=='OUT_OF_SUPPORT':
                req=float(x.requested_seconds.iloc[i])
                if not np.isfinite(req) or req<=0: raise ValueError('ABSTAIN_INVALID_OOD_REQUEST')
                output[i,1:]=np.maximum(output[i,1:],req)
            fallback.append({'level':chosen[0][0],'conservative_parent_max':state!='STRONG_SUPPORT',
                             'calibration_support':chosen[0][1]['n'],'q90':q90,'q95':q95})
        return output,pd.DataFrame(fallback,index=x.index)

    def json(self):
        return {'minimum':self.minimum,'tables':[[{'key':list(k),**v} for k,v in sorted(t.items())] for t in self.tables]}

def point_metrics(y,p):
    y,p=np.asarray(y),np.asarray(p)
    d=y-p
    if not len(d): return {'N':0}
    return {'N':len(d),'MAE_seconds':float(abs(d).mean()),'RMSE_seconds':float(np.sqrt(np.mean(d*d))),
            'mean_signed_error_seconds':float(d.mean()),'median_signed_error_seconds':float(np.median(d)),
            'underprediction_rate':float((d>0).mean()),'overprediction_rate':float((d<0).mean())}

def safety_metrics(y,duration,gpu,starts=None):
    y,duration,gpu=map(lambda a:np.asarray(a,dtype=float),(y,duration,gpu))
    if not len(y): return {'N':0}
    if np.any(gpu<=0) or np.any(duration<0) or np.any(~np.isfinite(duration)):
        raise ValueError('BAD_SAFETY_INPUT')
    delta=y-duration
    miss=np.maximum(delta,0)
    over=np.maximum(-delta,0)
    start=np.zeros(len(y)) if starts is None else np.asarray(starts,dtype=float)
    # Grid-overlap counts are independent of the 15-minute decision representation.
    miss_slots=np.maximum(0,np.ceil((start+y)/300)-np.ceil((start+duration)/300))
    realized_slots=np.where(y>0,np.maximum(0,np.ceil((start+y)/300)-np.floor(start/300)),0)
    weighted_slots=float(np.sum(miss_slots*gpu))
    total_slots=float(np.sum(realized_slots*gpu))
    return {'N':len(y),'coverage':float((delta<=0).mean()),'underprediction_rate':float((delta>0).mean()),
        'GPU_WEIGHTED_COVERAGE':float(np.sum(gpu*(delta<=0))/gpu.sum()),
        'GPU_WEIGHTED_UNDERPREDICTION_SECONDS':float(np.sum(gpu*miss)),
        'GPU_WEIGHTED_OVERRESERVATION_SECONDS':float(np.sum(gpu*over)),
        'overreservation_seconds':float(over.sum()),'overreserved_GPU_hours':float(np.sum(gpu*over)/3600),
        'reserved_GPU_hours':float(np.sum(gpu*duration)/3600),
        'PREDICTED_FINISHED_BUT_ACTUALLY_ACTIVE_GPU_SLOTS':weighted_slots,
        'CRITICAL_SLOT_MISS_GPU_SLOTS':weighted_slots,
        'critical_metric_scope':'all active-miss slots conservative proxy; no verified critical-line authority',
        'GRID_RELEVANT_RUNTIME_MISS_RATE':None,
        'grid_metric_status':'NOT_EVALUATED_NO_PREMAY_GRID_AUTHORITY_BOUND',
        'active_miss_GPU_slot_rate':weighted_slots/total_slots if total_slots else 0.}

def envelope_durations(point,upper90,upper95):
    point,upper90,upper95=map(ceil_seconds,[point,upper90,upper95])
    if np.any(upper90<point) or np.any(upper95<upper90): raise ValueError('CROSSING_ENVELOPE')
    return {'R0':(point,point),'R1':(upper90,upper90),'R2':(point,upper90),'R3':(upper90,upper95)}
