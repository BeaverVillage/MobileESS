"""Exposed April regression only; all model and provider bytes must be frozen."""
from common9 import *
from fit9 import matrix
from metrics9 import *
from distribution9 import Distribution
import numpy as np,pandas as pd
FREEZES=['MODEL_SELECTION_FREEZE.json','TEMPORAL_FOLD_FREEZE.json','FEATURE_CONTRACT_FREEZE.json','CALIBRATION_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json']
def assert_freeze():
    for name in FREEZES+(['EXPERIMENT_EVIDENCE_FREEZE.json'] if (ROOT/'EXPERIMENT_EVIDENCE_FREEZE.json').exists() else []):
        for r in read(ROOT/name).get('files',[]):assert sha(r['path'])==r['sha256'],name+' CHANGED'
def april_calibration(model,par,f,rawq,contract):
    mode=contract['calibration_mode'];cutoff=pd.Timestamp(contract['available_from'])
    if mode=='NONE':return np.zeros(len(f)),[],{}
    if mode=='STATIC14':return np.full(len(f),contract['static_delta']),[],{}
    window=int(mode.replace('ROLLING',''));initial=contract['initial_residuals']
    init_end=pd.to_datetime([r['end_time'] for r in initial],utc=True);init_res=np.array([r['residual'] for r in initial])
    days=f.submit_time.dt.floor('D');out=np.zeros(len(f));audit=[];daily={}
    for day in pd.date_range('2025-04-01','2025-04-30',tz='UTC'):
        eligible=f.label_valid&f.end_time.lt(day)&f.end_time.ge(day-pd.Timedelta(days=window))
        past=f.loc[eligible,'runtime_seconds'].to_numpy()-rawq[eligible,3]
        im=(init_end<day)&(init_end>=day-pd.Timedelta(days=window))
        delta=correction(np.r_[init_res[im],past]);out[days.eq(day)]=delta;daily[str(day)]=delta
        latest=f.loc[eligible,'end_time'].max();assert pd.isna(latest) or latest<day
        audit.append(dict(day=str(day),N=len(past)+int(im.sum()),delta=delta,max_April_source_end=str(latest),future_residual_reads=0))
    return out,audit,daily
def remaining_diagnostics(f,pred,model,par,delta,daily,contract):
    m=f.label_valid.to_numpy();g=f.loc[m].reset_index(drop=True);p=pred.loc[m].reset_index(drop=True);par=par[m];y=g.runtime_seconds.to_numpy(float);gpu=g.num_gpus_req.to_numpy(float)
    counts=np.maximum(np.ceil(y/1800).astype(int)-1,0);ix=np.repeat(np.arange(len(g)),counts)
    elapsed=(np.arange(len(ix))-np.repeat(np.cumsum(counts)-counts,counts)+1)*1800;actual=y[ix]-elapsed
    checkpoint=pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(elapsed,unit='s')
    checkpoint=pd.to_datetime(checkpoint,utc=True);assert (checkpoint<pd.Timestamp('2025-05-01T00Z')).all()
    if contract['calibration_mode'].startswith('ROLLING'):
        d=np.array([daily[str(t)] for t in checkpoint.floor('D')])
    elif contract['calibration_mode']=='STATIC14':d=np.full(len(ix),contract['static_delta'])
    else:d=np.zeros(len(ix))
    qparts=[];survivalparts=[]
    for start in range(0,len(ix),10000):
        z=ix[start:start+10000];q,s,ls=model.remaining(par[z],elapsed[start:start+10000],d[start:start+10000]);qparts.append(q);survivalparts.append(s)
    v9=np.concatenate(qparts);rows=[];overrows=[]
    models={'R0_Bconst':np.maximum(p[['Bconst_Q50','Bconst_Q90']].to_numpy()[ix]-elapsed[:,None],0),
            'R1_B0':np.maximum(p[['B0_Q50','B0_Q90']].to_numpy()[ix]-elapsed[:,None],0),
            'R2_V8':np.maximum(p[['V8_Q50','V8_Q90']].to_numpy()[ix]-elapsed[:,None],0),'R3_V9':v9}
    for arm,q in models.items():
        base={'R0_Bconst':'Bconst','R1_B0':'B0','R2_V8':'V8','R3_V9':'V9'}[arm]
        planned=p[base+'_Q90'].to_numpy()[ix];over=elapsed>=planned
        for name,mask in [('ALL',np.ones(len(ix),bool)),('ELAPSED_GT4H',elapsed>14400),('ELAPSED_GT12H',elapsed>43200),('ACTUAL_TOTAL_GT4H',y[ix]>14400)]:
            a=actual[mask];r=q[mask];gg=gpu[ix][mask]
            row=dict(arm=arm,scope=name,unique_jobs=int(np.unique(ix[mask]).size),**stats(a,gg,r[:,0],r[:,1]))
            row.update(remaining_MAE_seconds=row['Q90_MAE'],remaining_Q50_MAE_seconds=row['Q50_MAE'],remaining_Q90_coverage=row['Q90_coverage'],overrun_checkpoint_fraction=float(over[mask].mean()))
            for threshold in [900,1800,3600,7200,14400]:
                actual_positive=a>threshold;prediction=r[:,1]>threshold;tp=int(np.sum(actual_positive&prediction));fp=int(np.sum(~actual_positive&prediction));fn=int(np.sum(actual_positive&~prediction))
                row.update({f'accuracy_gt_{threshold}s':float((actual_positive==prediction).mean()),f'precision_gt_{threshold}s':tp/(tp+fp) if tp+fp else None,f'recall_gt_{threshold}s':tp/(tp+fn) if tp+fn else None})
            rows.append(row)
        overrows.append(dict(arm=base,checkpoint_N=len(ix),overrun_checkpoint_N=int(over.sum()),overrun_checkpoint_fraction=float(over.mean()),
            mature_job_N=len(g),total_prediction_overrun_job_fraction=float((y>p[base+'_Q90']).mean()),GPU_retained=True,force_completion=False,policy='OVERRUN->STAY; conditional V9 + one900s interval'))
    pd.DataFrame(rows).to_csv(ROOT/'CONDITIONAL_REMAINING_DIAGNOSTIC.csv',index=False);pd.DataFrame(overrows).to_csv(ROOT/'OVERRUN_DIAGNOSTIC.csv',index=False)
    np.savez_compressed(LOCAL/'APRIL_CHECKPOINTS.npz',job_index=ix,elapsed=elapsed,actual_remaining=actual,V9_quantiles=v9,survival=np.concatenate(survivalparts))
    r=next(r for r in rows if r['arm']=='R3_V9' and r['scope']=='ALL');b=next(r for r in rows if r['arm']=='R0_Bconst' and r['scope']=='ALL');long=next(r for r in rows if r['arm']=='R3_V9' and r['scope']=='ELAPSED_GT4H')
    return dict(checkpoint_N=len(ix),unique_jobs=int(np.unique(ix).size),coverage_gate=.88<=r['Q90_coverage']<=.92,Q50_MAE_gate=r['Q50_MAE']<=b['Q50_MAE'],long_running_gate=long['Q90_coverage']>=.85,
        validated=bool(.88<=r['Q90_coverage']<=.92 and r['Q50_MAE']<=b['Q50_MAE'] and long['Q90_coverage']>=.85),checkpoint_scope='Mature-before-May1 trace cohort; surviving 30min checkpoints, excludes unresolved labels; length-biased checkpoint weighting')
def main():
    assert_freeze()
    write('APRIL_EVALUATION_STARTED.json',dict(time=now(),APRIL_STATUS='EXPOSED_REGRESSION_ONLY',freezes=[record(ROOT/n) for n in FREEZES],May_payload_opened=False))
    f=pd.read_parquet(V8/'APRIL_JOBS.parquet');pred=pd.read_parquet(V8/'APRIL_PREDICTIONS.parquet')
    pred=f[['job_id']].merge(pred,on='job_id',validate='one_to_one');assert np.array_equal(pred.job_id,f.job_id)
    model=Distribution.load(ROOT/'RUNTIME_PROVIDER/model');prep=read(ROOT/'RUNTIME_PROVIDER/preprocessing.json');contract=read(ROOT/'RUNTIME_PROVIDER/runtime_contract.json')
    par=model.parameters(matrix(f,prep));rawq=model.quantiles(par);delta,audit,daily=april_calibration(model,par,f,rawq,contract)
    q=model.quantiles(par,delta);pred['V9_Q50']=q[:,0];pred['V9_Q90']=q[:,3];pred['V9_delta']=delta
    pred.to_parquet(ROOT/'APRIL_PREDICTIONS.parquet',index=False);np.savez_compressed(LOCAL/'APRIL_PARAMETERS.npz',parameters=par,raw_quantiles=rawq)
    pd.DataFrame(audit,columns=['day','N','delta','max_April_source_end','future_residual_reads']).to_csv(ROOT/'APRIL_CAUSAL_CALIBRATION_AUDIT.csv',index=False)
    m=f.label_valid.to_numpy();y=f.loc[m,'runtime_seconds'].to_numpy(float);gpu=f.loc[m,'num_gpus_req'].to_numpy(float);rows=[];tails=[];curves=[];gp=[]
    for arm in ['W0','B0','Bconst','V8','V9']:
        aq=q[m] if arm=='V9' else np.full((sum(m),5),np.nan)
        if arm=='W0':aq[:]=f.loc[m,'requested_seconds'].to_numpy()[:,None]
        elif arm!='V9':aq[:,0]=pred.loc[m,arm+'_Q50'];aq[:,3]=pred.loc[m,arm+'_Q90']
        rows.append(dict(arm=arm,APRIL_STATUS='EXPOSED_REGRESSION_ONLY',**stats(y,gpu,aq[:,0],aq[:,3])))
        tails.extend(dict(arm=arm,**r) for r in tail_rows(y,gpu,aq))
        for j,tau in enumerate(QUANTILES):
            if np.isfinite(aq[:,j]).all():curves.append(dict(arm=arm,nominal_quantile=tau,N=len(y),empirical_coverage=float(np.mean(y<=aq[:,j]))))
        for threshold in [16,64]:
            mask=gpu>=threshold;s=stats(y[mask],gpu[mask],aq[mask,0],aq[mask,3]);s['status']='INSUFFICIENT_SUPPORT' if s['N']<100 else 'PASS' if s['Q90_coverage']>=.85 else 'FAIL';gp.append(dict(arm=arm,GPU_min=threshold,**s))
    pd.DataFrame(rows).to_csv(ROOT/'APRIL_EXPOSED_RUNTIME_METRICS.csv',index=False);pd.DataFrame(tails).to_csv(ROOT/'APRIL_EXPOSED_LONG_TAIL.csv',index=False)
    pd.DataFrame(curves).to_csv(ROOT/'APRIL_DISTRIBUTIONAL_CALIBRATION.csv',index=False);pd.DataFrame(gp).to_csv(ROOT/'APRIL_HIGH_GPU.csv',index=False)
    observed=f.loc[m].copy();observed['event']=True;observed['censored']=False;observed['duration_lower']=observed.runtime_seconds
    ds=distribution_scores(model,par[m],observed,delta[m],read(ROOT/'HAZARD_BIN_CONTRACT.json')['edges_seconds'])
    write('APRIL_DISTRIBUTION_SCORES.json',dict(**ds,scope='Exact mature April cohort only; unresolved starts are not retrospectively relabeled'))
    rem=remaining_diagnostics(f,pred,model,par,delta,daily,contract)
    write('APRIL_EVALUATION_RECEIPT.json',dict(time=now(),mature_N=int(sum(m)),unresolved_N=int(sum(~m)),remaining=rem,APRIL_USED_FOR_SELECTION=False,
        APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,FUTURE_CALIBRATION_RESIDUAL_READS=0,MAY_PAYLOAD_OPENED=False,source=record(V8/'APRIL_JOBS.parquet')))
    assert_freeze();print('APRIL_COMPLETE',rows,rem,flush=True)
if __name__=='__main__':main()
