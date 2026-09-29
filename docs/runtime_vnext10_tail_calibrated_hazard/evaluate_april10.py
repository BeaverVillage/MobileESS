"""Single exposed regression after six freezes. No recalibration or training."""
from common10 import *
from finalize10 import assert_freeze,load_provider,FREEZES
from train10 import matrix
from metrics10 import *
import numpy as np,pandas as pd
def remaining_diagnostics(f,pred,provider,par):
    m=f.label_valid.to_numpy();g=f.loc[m].reset_index(drop=True);p=pred.loc[m].reset_index(drop=True);pp=par[m];y=g.runtime_seconds.to_numpy();gpu=g.num_gpus_req.to_numpy()
    counts=np.maximum(np.ceil(y/1800).astype(int)-1,0);ix=np.repeat(np.arange(len(g)),counts);elapsed=(np.arange(len(ix))-np.repeat(np.cumsum(counts)-counts,counts)+1)*1800;actual=y[ix]-elapsed
    times=pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(elapsed,unit='s');assert (times<pd.Timestamp('2025-05-01T00Z')).all()
    old=np.load(V9/'.local/APRIL_CHECKPOINTS.npz');assert np.array_equal(old['job_index'],ix) and np.array_equal(old['elapsed'],elapsed) and np.array_equal(old['actual_remaining'],actual)
    v10=np.zeros((len(ix),2));logs=np.zeros(len(ix))
    for start in range(0,len(ix),4000):
        sl=slice(start,start+4000);v10[sl],logs[sl]=provider.remaining_from_parameters(pp[ix[sl]],elapsed[sl])
    rows=[];overs=[]
    arms={a:np.maximum(p[[a+'_Q50',a+'_Q90']].to_numpy()[ix]-elapsed[:,None],0) for a in ['Bconst','B0','V8']}
    arms.update(V9=old['V9_quantiles'],V10=v10)
    for arm,q in arms.items():
        over=elapsed>=p[arm+'_Q90'].to_numpy()[ix]
        for scope,mask in [('ALL',np.ones(len(ix),bool)),('ELAPSED_GT4H',elapsed>14400),('ELAPSED_GT12H',elapsed>43200),('TOTAL_GT4H',y[ix]>14400)]:
            yy=actual[mask];qq=q[mask];s=stats(yy,gpu[ix][mask],qq[:,0],qq[:,1]);s.update(phase='APRIL_EXPOSED',arm=arm,scope=scope,unique_jobs=int(np.unique(ix[mask]).size),overrun_checkpoint_fraction=float(over[mask].mean()))
            for t in [900,1800,3600,7200,14400]:
                truth=yy>t;pr=qq[:,1]>t;tp=int((truth&pr).sum());fp=int((~truth&pr).sum());fn=int((truth&~pr).sum())
                s.update({f'accuracy_gt_{t}s':float((truth==pr).mean()),f'TP_gt_{t}s':tp,f'FP_gt_{t}s':fp,f'FN_gt_{t}s':fn,f'precision_gt_{t}s':tp/(tp+fp) if tp+fp else None,f'recall_gt_{t}s':tp/(tp+fn) if tp+fn else None})
            rows.append(s)
        overs.append(dict(phase='APRIL_EXPOSED',arm=arm,checkpoint_N=len(ix),overrun_checkpoint_N=int(over.sum()),overrun_checkpoint_fraction=float(over.mean()),mature_job_N=len(g),total_overrun_fraction=float((y>p[arm+'_Q90']).mean()),GPU_retained=True,force_completion=False,extension_seconds=900,migration='STAY'))
    new=pd.DataFrame(rows);oldmetrics=pd.read_csv(V9/'CONDITIONAL_REMAINING_DIAGNOSTIC.csv');reference=oldmetrics[(oldmetrics.arm=='R3_V9')&(oldmetrics.scope=='ALL')].iloc[0];actualref=new[(new.arm=='V9')&(new.scope=='ALL')].iloc[0]
    for col in ['N','Q50_MAE','Q90_MAE','Q90_coverage','Q90_pinball']:assert abs(reference[col]-actualref[col])<1e-7
    pre=pd.read_csv(ROOT/'PREAPRIL_REMAINING_POOLED.csv');preref=pd.read_csv(ROOT/'PREAPRIL_V9_REMAINING_POOLED.csv')
    pd.concat([pre,preref,new],ignore_index=True).to_csv(ROOT/'CONDITIONAL_REMAINING_DIAGNOSTIC.csv',index=False)
    new.to_csv(ROOT/'APRIL_CONDITIONAL_REMAINING.csv',index=False)
    pd.DataFrame(overs).to_csv(ROOT/'OVERRUN_DIAGNOSTIC.csv',index=False)
    np.savez_compressed(LOCAL/'APRIL_CHECKPOINTS.npz',job_index=ix,elapsed=elapsed,actual_remaining=actual,V10_quantiles=v10,log_survival=logs)
    r=new[(new.arm=='V10')&(new.scope=='ALL')].iloc[0]
    return dict(checkpoint_N=len(ix),unique_jobs=int(np.unique(ix).size),V9_cached_reference_reproduced=True,V10_coverage=float(r.Q90_coverage),coverage_gate=bool(.88<=r.Q90_coverage<=.92),scope='Mature-before-May1 only; all strictly surviving 30min checkpoints, length-biased checkpoint weighting; unresolved labels excluded')
def main():
    assert_freeze()
    write('APRIL_EVALUATION_STARTED.json',dict(time=now(),APRIL_STATUS='EXPOSED_REGRESSION_ONLY',freezes=[record(ROOT/n) for n in FREEZES],May_payload_opened=False))
    f=pd.read_parquet(V8/'APRIL_JOBS.parquet');old=pd.read_parquet(V9/'APRIL_PREDICTIONS.parquet');pred=f[['job_id']].merge(old,on='job_id',validate='one_to_one');assert np.array_equal(pred.job_id,f.job_id)
    provider=load_provider();par=provider.model.parameters(matrix(f,provider.prep),threads=4);q=provider.quantiles_from_parameters(par,(.5,.7,.8,.9,.95))
    pred['V10_Q50']=q[:,0];pred['V10_Q90']=q[:,3];pred.to_parquet(ROOT/'APRIL_PREDICTIONS.parquet',index=False);np.savez_compressed(LOCAL/'APRIL_PARAMETERS.npz',parameters=par,quantiles=q)
    m=f.label_valid.to_numpy();y=f.loc[m,'runtime_seconds'].to_numpy();gpu=f.loc[m,'num_gpus_req'].to_numpy();rows=[];tails=[];curves=[];high=[]
    for arm in ['W0','B0','Bconst','V8','V9','V10']:
        aq=q[m] if arm=='V10' else np.full((sum(m),5),np.nan)
        if arm=='W0':aq[:]=f.loc[m,'requested_seconds'].to_numpy()[:,None]
        elif arm!='V10':aq[:,0]=pred.loc[m,arm+'_Q50'];aq[:,3]=pred.loc[m,arm+'_Q90']
        s=stats(y,gpu,aq[:,0],aq[:,3]);rows.append(dict(arm=arm,APRIL_STATUS='EXPOSED_REGRESSION_ONLY',**s))
        tails.extend(dict(arm=arm,**r) for r in tail_rows(y,gpu,aq))
        for j,tau in enumerate([.5,.7,.8,.9,.95]):
            if np.isfinite(aq[:,j]).all():curves.append(dict(arm=arm,nominal=tau,N=len(y),empirical_coverage=float((y<=aq[:,j]).mean())))
        for threshold in [16,64]:
            gm=gpu>=threshold;s=stats(y[gm],gpu[gm],aq[gm,0],aq[gm,3]);s['status']='INSUFFICIENT_SUPPORT' if s['N']<100 else 'PASS' if s['Q90_coverage']>=.85 else 'FAIL';high.append(dict(arm=arm,GPU_min=threshold,**s))
    observed=f.loc[m].copy();observed['event']=True;observed['censored']=False;observed['duration_lower']=observed.runtime_seconds
    _,groups=provider.risk_groups(par[m]);assign=[(groups==g,provider.mapping(g)) for g in np.unique(groups)]
    score=distribution_metrics(score_inputs(provider.model,par[m],observed,provider.continuation),assign)
    for r in rows:
        r.update(proper_interval_NLL=score['proper_interval_NLL'] if r['arm']=='V10' else None,proper_score_status='EXACT_FINITE_ONE_SECOND_CELLS' if r['arm']=='V10' else 'V9_PRESERVED_INFINITE_SUPPORT_FAILURE_DIFFERENT_COARSENING' if r['arm']=='V9' else 'NOT_DEFINED_QUANTILE_ONLY')
    pd.DataFrame(rows).to_csv(ROOT/'APRIL_EXPOSED_RUNTIME_METRICS.csv',index=False);pd.DataFrame(tails).to_csv(ROOT/'APRIL_EXPOSED_LONG_TAIL.csv',index=False)
    pd.DataFrame(curves).to_csv(ROOT/'APRIL_DISTRIBUTIONAL_CALIBRATION.csv',index=False);pd.DataFrame(high).to_csv(ROOT/'APRIL_HIGH_GPU.csv',index=False)
    write('APRIL_DISTRIBUTION_SCORES.json',dict(**score,scope='Exact mature April cohort only; unresolved labels excluded',V9_reference=record(V9/'APRIL_DISTRIBUTION_SCORES.json')))
    # Reproduce all legacy headline statistics without changing old artifacts.
    legacy=pd.read_csv(V9/'APRIL_EXPOSED_RUNTIME_METRICS.csv').set_index('arm')
    for r in rows[:-1]:
        for c in ['N','Q50_MAE','Q90_coverage','Q90_pinball','reservation_actual_GPUh']:assert abs(r[c]-legacy.loc[r['arm'],c])<1e-7
    print('APRIL_TOTAL_COMPLETE',rows[-1],flush=True)
    rem=remaining_diagnostics(f,pred,provider,par)
    write('APRIL_EVALUATION_RECEIPT.json',dict(time=now(),mature_N=int(sum(m)),unresolved_N=int(sum(~m)),remaining=rem,APRIL_USED_FOR_SELECTION=False,APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,April_calibration_updates=False,MAY_PAYLOAD_OPENED=False,sources=[record(V8/'APRIL_JOBS.parquet'),record(V9/'APRIL_PREDICTIONS.parquet'),record(V9/'.local/APRIL_CHECKPOINTS.npz')]))
    assert_freeze();print('APRIL_COMPLETE',rem,flush=True)
if __name__=='__main__':main()

