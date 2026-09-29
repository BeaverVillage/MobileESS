from common11 import *
import pandas as pd,numpy as np
def checkpoints(f):
    g=f.loc[f.event].reset_index(drop=True);y=g.runtime_seconds.to_numpy(float);counts=np.maximum(np.ceil(y/1800).astype(int)-1,0)
    ix=np.repeat(np.arange(len(g)),counts);elapsed=(np.arange(len(ix))-np.repeat(np.cumsum(counts)-counts,counts)+1)*1800;remaining=y[ix]-elapsed
    times=pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(elapsed,unit='s')
    assert np.all(remaining>0) and (times<pd.DatetimeIndex(g.end_time.iloc[ix])).all()
    assert (times<pd.DatetimeIndex(g.observation_cutoff.iloc[ix])).all()
    return g,ix,elapsed,remaining
def masks(elapsed,actual,total):
    out=[('ALL','ALL',np.ones(len(elapsed),bool))]
    for name,lo,hi in [('0.5_1h',0,3600),('1_2h',3600,7200),('2_4h',7200,14400),('4_8h',14400,28800),('8_12h',28800,43200),('12_24h',43200,86400),('gt24h',86400,np.inf)]:out.append(('ELAPSED',name,(elapsed>lo)&(elapsed<=hi)))
    for name,lo,hi in [('le30m',0,1800),('30m_1h',1800,3600),('1_2h',3600,7200),('2_4h',7200,14400),('gt4h',14400,np.inf)]:out.append(('ACTUAL_REMAINING',name,(actual>lo)&(actual<=hi)))
    out.extend([('LONG_RUNNING','elapsed_gt4h',elapsed>14400),('LONG_RUNNING','elapsed_gt12h',elapsed>43200),('LONG_RUNNING','total_gt4h',total>14400)])
    return out
def references(i,g,ix,elapsed):
    from distribution9 import Distribution
    from metrics9 import correction
    from hazard10 import Hazard
    from calibration10 import ProbabilityMap,maps_remaining
    f=data(i,'VALID');cal=data(i,'CAL');m=f.event.to_numpy();out={}
    b=pd.read_parquet(V9/'.local/B0_evaluation.parquet');b=b[b.fold.eq(i)]
    b=g[['job_id']].merge(b[['job_id','q50','q90']],on='job_id',validate='one_to_one');assert len(b)==len(g)
    out['R0_B0']=np.maximum(b[['q50','q90']].to_numpy()[ix]-elapsed[:,None],0)
    selected=np.load(LOCAL/f'fold{i}/SELECTED_TOTAL.npz')['quantiles'][m]
    out['R1_TOTAL_MINUS']=np.maximum(selected[ix]-elapsed[:,None],0)
    path=LOCAL/f'fold{i}/REMAINING_REFERENCES.npz'
    if path.exists():
        z=np.load(path);out.update(R2_V9=z['V9'],R2_V10=z['V10']);return out,selected
    saved=np.load(V9/'.local'/f'fold{i}/D1.npz');model=Distribution.load(V9/'FOLD_MODELS'/f'fold{i}/D1');par=saved['val_parameters'][m]
    pool=pd.concat([cal,f],ignore_index=True);rawq=np.r_[saved['cal_quantiles'][:,3],saved['val_quantiles'][:,3]]
    days=(pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(elapsed,unit='s')).floor('D');delta=np.zeros(len(ix))
    for day in days.unique():
        eligible=pool.event&pool.end_time.lt(day)&pool.end_time.ge(day-pd.Timedelta(days=14));delta[days==day]=correction(pool.loc[eligible,'runtime_seconds'].to_numpy()-rawq[eligible])
    v9=np.zeros((len(ix),2))
    for start in range(0,len(ix),4000):
        sl=slice(start,start+4000);v9[sl],_,_=model.remaining(par[ix[sl]],elapsed[sl],delta[sl])
    model10=Hazard.load(V10/'FOLD_MODELS'/f'fold{i}/G1');par10=np.load(V10/'.local'/f'fold{i}/G1.npz')['val_parameters'][m]
    state=read(V10/'CALIBRATION_STATES'/f'fold{i}_LOGISTIC_STATIC.json')['states']['STATIC'];groups=np.digitize(np.exp(model10.logsf(par10,14400)),state['bounds'],right=True);v10=np.zeros_like(v9)
    for group in np.unique(groups):
        positions=np.flatnonzero(groups[ix]==group);mapping=ProbabilityMap(state['groups'][str(group)])
        for start in range(0,len(positions),4000):
            pos=positions[start:start+4000];v10[pos],_=maps_remaining(model10,par10[ix[pos]],elapsed[pos],mapping,'LAST_RATE')
    np.savez_compressed(path,V9=v9,V10=v10);out.update(R2_V9=v9,R2_V10=v10);return out,selected
