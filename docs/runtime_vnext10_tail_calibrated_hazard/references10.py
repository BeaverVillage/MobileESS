"""Preserved reference evidence, never selection-eligible or refitted."""
from common10 import *
from metrics10 import stats
from metrics9 import correction,calibration
from distribution9 import Distribution
import numpy as np,pandas as pd
def main():
    refs=['W0','B0','Bconst','V8','D1__ROLLING14'];ren={'D1__ROLLING14':'T0_V9'}
    for filename in ['FOLD_LEVEL_METRICS.csv','LONG_TAIL_METRICS.csv','PREAPRIL_QUEUE_REPLAY.csv']:
        old=pd.read_csv(V9/filename);old=old[old.arm.isin(refs)].copy();old.arm=old.arm.replace(ren)
        old['reference_origin']='frozen V9; exact same fold membership'
        if filename=='FOLD_LEVEL_METRICS.csv':
            old['proper_interval_NLL']=np.nan
            old['proper_score_note']=np.where(old.arm.eq('T0_V9'),'V9 proper score INFINITE from zero-support; old floored/coarse NLL not comparable to V10 one-second-cell NLL','Quantile-only reference; full-distribution score unavailable')
        new=pd.read_csv(ROOT/filename);new['reference_origin']='V10 preApril'
        pd.concat([old,new],ignore_index=True).to_csv(ROOT/filename,index=False)
    old=pd.read_csv(V9/'MODEL_COMPARISON.csv');old=old[old.arm.isin(refs)].copy();old.arm=old.arm.replace(ren)
    old.to_csv(ROOT/'PREAPRIL_REFERENCE_METRICS.csv',index=False)
    remaining=[]
    for i in range(1,6):
        val=fold_data(i,'VALID');cal=fold_data(i,'CAL');saved=np.load(V9/'.local'/f'fold{i}/D1.npz');model=Distribution.load(V9/'FOLD_MODELS'/f'fold{i}/D1')
        m=val.event.to_numpy();g=val.loc[m].reset_index(drop=True);par=saved['val_parameters'][m];y=g.runtime_seconds.to_numpy();gpu=g.num_gpus_req.to_numpy()
        counts=np.maximum(np.ceil(y/1800).astype(int)-1,0);ix=np.repeat(np.arange(len(g)),counts);elapsed=(np.arange(len(ix))-np.repeat(np.cumsum(counts)-counts,counts)+1)*1800;actual=y[ix]-elapsed
        days=(pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(elapsed,unit='s')).floor('D')
        pool=pd.concat([cal,val],ignore_index=True);baseq=np.r_[saved['cal_quantiles'][:,3],saved['val_quantiles'][:,3]]
        delta=np.zeros(len(ix))
        for day in days.unique():
            eligible=pool.event&pool.end_time.lt(day)&pool.end_time.ge(day-pd.Timedelta(days=14))
            delta[days==day]=correction(pool.loc[eligible,'runtime_seconds'].to_numpy()-baseq[eligible])
        out=[]
        for start in range(0,len(ix),5000):
            sl=slice(start,start+5000);q,_,_=model.remaining(par[ix[sl]],elapsed[sl],delta[sl]);out.append(q)
        pred=np.concatenate(out);d,_=calibration(cal,val,saved['cal_quantiles'],saved['val_quantiles'],'ROLLING14');total=model.quantiles(saved['val_parameters'],d)[m,3]
        for scope,mask in [('ALL',np.ones(len(ix),bool)),('ELAPSED_GT4H',elapsed>14400),('ELAPSED_GT12H',elapsed>43200),('TOTAL_GT4H',y[ix]>14400)]:
            yy=actual[mask];q=pred[mask];s=stats(yy,gpu[ix][mask],q[:,0],q[:,1]);s.update(phase='PREAPRIL',fold=i,arm='T0_V9',scope=scope,unique_jobs=int(np.unique(ix[mask]).size),overrun_checkpoint_fraction=float((elapsed[mask]>=total[ix[mask]]).mean()))
            for t in [900,1800,3600,7200,14400]:
                a=yy>t;p=q[:,1]>t;s[f'accuracy_gt_{t}s']=float((a==p).mean())
            remaining.append(s)
        print('V9_REMAINING_REFERENCE',i,len(ix),flush=True)
    r=pd.DataFrame(remaining);r.to_csv(ROOT/'PREAPRIL_V9_REMAINING_FOLD.csv',index=False);pooled=[]
    for scope,z in r.groupby('scope'):
        row=dict(phase='PREAPRIL',arm='T0_V9',scope=scope,N=int(z.N.sum()))
        for col in ['Q50_MAE','Q90_MAE','Q90_coverage','Q90_pinball','overrun_checkpoint_fraction']+[f'accuracy_gt_{t}s' for t in [900,1800,3600,7200,14400]]:row[col]=float(np.average(z[col],weights=z.N))
        pooled.append(row)
    pd.DataFrame(pooled).to_csv(ROOT/'PREAPRIL_V9_REMAINING_POOLED.csv',index=False)
    write('REFERENCE_EVIDENCE_RECEIPT.json',dict(time=now(),references=refs,selection_eligible=False,source=[record(V9/p) for p in ['MODEL_COMPARISON.csv','FOLD_LEVEL_METRICS.csv','LONG_TAIL_METRICS.csv','PREAPRIL_QUEUE_REPLAY.csv']],limitation='B0 historical folds partly predate model training; V8/Bconst are retrospective frozen references, not causal fold training; T0 reproduction only',April_read=False))
if __name__=='__main__':main()

