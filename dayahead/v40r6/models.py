"""Exactly B0, B1 and CPU single-thread LightGBM quantile family B2."""
from .common import *
from lightgbm import LGBMRegressor, Booster
import time

def inverse(z):
    out=np.expm1(np.asarray(z,dtype=float))
    if np.any(out < -1e-10): raise ValueError('Substantive negative inverse quantile; clipping prohibited')
    out[(out<0)&(out>=-1e-10)]=0
    assert np.isfinite(out).all()
    return out

def repair(q):
    q=np.asarray(q,float).copy(); crossing=q[:,0]>q[:,1]
    q[:,1]=np.maximum(q[:,1],q[:,0])
    return q,{'raw_crossing_count':int(crossing.sum()),'raw_crossing_fraction':float(crossing.mean()),
        'N':len(q),'repair':'Q90=max(Q90_raw,Q50_raw)','post_crossing_count':int((q[:,0]>q[:,1]).sum())}

def fit_model(X,y,config,alpha,destination):
    p=CONFIGS[config]
    model=LGBMRegressor(objective='quantile',alpha=alpha,device_type='cpu',n_jobs=1,
        deterministic=True,force_col_wise=True,random_state=SEED,verbosity=-1,**p)
    start=time.perf_counter(); model.fit(X,np.log1p(y)); seconds=time.perf_counter()-start
    destination.parent.mkdir(parents=True,exist_ok=True); model.booster_.save_model(str(destination))
    return model,{'family':'B2','config':config,'quantile':alpha,'rows':len(y),'features':X.shape[1],
        'seconds':seconds,'device':'cpu','threads':1,'seed':SEED,'target_transform':'log1p',
        'model':destination.relative_to(ROOT).as_posix(),'SHA256':sha(destination),'time_UTC':utc()}

def predict_pair(directory,h,X):
    raw=np.column_stack([inverse(Booster(model_file=str(directory/f'{h}_Q{int(q*100)}.txt')).predict(X,num_threads=1)) for q in [.5,.9]])
    fixed,audit=repair(raw)
    return fixed,raw,audit

def calibrate(y,q90):
    return max(0.,float(np.quantile(np.log1p(y)-np.log1p(q90),.9,method='linear')))

def calibrated(q90,delta): return inverse(np.log1p(q90)+delta)

def baseline(frame,arrays,indices):
    """B1 TRAIN-only sources, additionally mature strictly before each issue."""
    predictions=np.zeros((len(indices),3)); support=[]
    lag_mature=arrays['lag_mature']; lag_values=arrays['lag_values']
    selected=frame.iloc[indices]
    train=frame[role_mask(frame,'TRAIN')].copy()
    for (day,h),g in selected.groupby(['day','horizon'],sort=False):
        origin=g.issue_time.iloc[0]
        pool=train[(train.horizon==h)&(train.target_available_at<origin)]
        assert (pool.target_available_at<origin).all()
        # Pooled horizon fallback retains the horizon unit/duration at every level.
        horizon_values=pool.target_GPUh.to_numpy()
        same_slot={k:p for k,p in pool.groupby('window_start_slot')}
        for row in g.itertuples():
            location=int(np.searchsorted(indices,row.Index))
            slotpool=same_slot.get(row.window_start_slot,pool.iloc[:0])
            weekdaypool=slotpool[slotpool.weekday==row.weekday]
            if len(weekdaypool)>=8: source=weekdaypool; level='horizon_start_weekday'
            elif len(slotpool)>=20: source=slotpool; level='horizon_start'
            elif len(pool)>=50: source=pool; level='horizon'
            elif len(pool)>=1: source=pool; level='global_TRAIN_horizon'
            else: raise ValueError('No causally mature TRAIN source for B1')
            predictions[location,1:]=np.quantile(source.target_GPUh,[.5,.9],method='linear')
            weekly=np.flatnonzero(lag_mature[row.Index])
            if len(weekly):
                predictions[location,0]=lag_values[row.Index,weekly[0]]; b0level=f'weekly_{[7,14,21,28][weekly[0]]}d'
            elif len(slotpool): predictions[location,0]=np.median(slotpool.target_GPUh); b0level='mature_TRAIN_same_window_median'
            elif len(horizon_values): predictions[location,0]=np.median(horizon_values); b0level='mature_TRAIN_horizon_median'
            else: predictions[location,0]=0.; b0level='zero_no_history'
            support.append({'row_id':row.Index,'day':day,'horizon':h,'B1_source_count':len(source),'B1_level':level,
                'B1_latest_source_available_at':source.target_available_at.max(),'issue_time':origin,'source_role':'TRAIN','B0_level':b0level})
    assert np.isfinite(predictions).all()
    return predictions,pd.DataFrame(support)
