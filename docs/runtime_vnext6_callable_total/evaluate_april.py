from paths import *
import sys
import numpy as np,pandas as pd
from metrics import compare,stats,gate,uncertainty
sys.path.insert(0,str(ROOT/'RUNTIME_PROVIDER'))
from provider import RuntimeProvider,running_proxy

def main():
    freeze=read(ROOT/'PROVIDER_BUNDLE_FREEZE.json')
    for r in freeze['files']:assert sha(ROOT/r['relative'])==r['sha256']
    provider=RuntimeProvider(allow_research=True)
    f=pd.read_parquet(ROOT/'APRIL_JOBS.parquet');b=pd.read_parquet(ROOT/'APRIL_B0_PREDICTIONS.parquet')
    f=f[f.label_valid].merge(b,on='job_id',validate='one_to_one')
    p=provider.predict_array(len(f));pred={'W0':np.column_stack([f.requested_seconds]*2),'B0_RESEARCH':f[['B0_Q50','B0_Q90']].to_numpy(),'STRICT_SELECTED':p}
    rows,groups=compare(f,pred,'APRIL_LOCKED');pd.DataFrame(rows).to_csv(ROOT/'APRIL_LOCKED_RUNTIME_METRICS.csv',index=False)
    pd.DataFrame(groups).to_csv(ROOT/'APRIL_STRATIFIED_METRICS.csv',index=False)
    cis=[]
    for name in ['W0','B0_RESEARCH']:cis+=uncertainty(f,p,pred[name],'APRIL_LOCKED','STRICT_SELECTED - '+name)
    pd.DataFrame(cis).to_csv(ROOT/'APRIL_PAIRED_UNCERTAINTY.csv',index=False)
    caps=[]
    for period,path in [('PREAPRIL','PREAPRIL_JOBS.parquet'),('APRIL','APRIL_JOBS.parquet')]:
        z=pd.read_parquet(ROOT/path);z=z[z.label_valid]
        if period=='PREAPRIL':z=z[z.role.isin(['DEV','CAL_FIT','CAL_VALID'])]
        q=provider.predict_array(len(z));c=q.copy();c[:,1]=np.minimum(c[:,1],z.requested_seconds)
        # Cap both to retain monotonic outputs; diagnostic only, never reselect.
        c[:,0]=np.minimum(c[:,0],c[:,1])
        for label,v in [('NO_CAP',q),('ARCHIVED_WALLTIME_CAP_DIAGNOSTIC',c)]:caps.append(dict(period=period,arm=label,**stats(z,v[:,0],v[:,1])))
    pd.DataFrame(caps).to_csv(ROOT/'WALLTIME_CAP_DIAGNOSTIC.csv',index=False)
    y=f.runtime_seconds.to_numpy();gpu=f.num_gpus_req.to_numpy();q=p[:,1]
    over=np.maximum(y-q,0);audit=f[['job_id','submit_time','num_gpus_req','runtime_seconds']].copy();audit['q90_seconds']=q;audit['overrun_seconds']=over;audit['overrun_GPUh']=over*gpu/3600
    audit['overrun_job']=y>q;audit.to_csv(ROOT/'OVERRUN_AUDIT.csv',index=False)
    checkpoint=[]
    for r,predq in zip(f.itertuples(),q):
        elapsed=np.arange(1800,r.runtime_seconds,1800)
        if not len(elapsed):continue
        remaining=r.runtime_seconds-elapsed;proxy=np.maximum(predq-elapsed,0);overrun=elapsed>=predq
        one=pd.DataFrame(dict(job_id=r.job_id,elapsed_seconds=elapsed,actual_remaining_seconds=remaining,proxy_remaining_seconds=proxy,num_gpus_req=r.num_gpus_req,OVERRUN=overrun))
        checkpoint.append(one)
    c=pd.concat(checkpoint,ignore_index=True);c.to_parquet(ROOT/'APRIL_RUNNING_CHECKPOINTS.parquet',index=False)
    def describe(z,scope):
        ae=np.abs(z.proxy_remaining_seconds-z.actual_remaining_seconds);g=z.num_gpus_req
        d=dict(scope=scope,N=len(z),unique_jobs=z.job_id.nunique(),remaining_MAE_seconds=float(ae.mean()),GPU_weighted_remaining_MAE_seconds=float(np.average(ae,weights=g)),overrun_checkpoint_fraction=float(z.OVERRUN.mean()),GPU_weighted_overrun_checkpoint_fraction=float(np.average(z.OVERRUN,weights=g)))
        for h in [900,1800,3600]:
            truth=z.actual_remaining_seconds>h;est=z.proxy_remaining_seconds>h
            d[f'accuracy_gt_{h}s']=float((truth==est).mean());d[f'false_negative_gt_{h}s']=int((truth&~est).sum());d[f'false_positive_gt_{h}s']=int((~truth&est).sum())
        return d
    diagnostics=[describe(c,'ALL_CHECKPOINTS')]
    for label,ids in [('HIGH_GPU',f.loc[f.num_gpus_req>=16,'job_id']),('LONG_ACTUAL_GT4H',f.loc[f.runtime_seconds>14400,'job_id'])]:
        z=c[c.job_id.isin(ids)]
        if len(z):diagnostics.append(describe(z,label))
    pd.DataFrame(diagnostics).to_csv(ROOT/'CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv',index=False)
    d=diagnostics[0];adequate=d['overrun_checkpoint_fraction']<=.15 and d['remaining_MAE_seconds']<=3600 and all(d[f'accuracy_gt_{h}s']>=.8 for h in [900,1800,3600])
    write('APRIL_EVALUATION_RECEIPT.json',dict(PASS_EXECUTION=True,promotion_gate=gate(f,p,[pred['W0'],pred['B0_RESEARCH']]),
      checkpoint_adequate=adequate,checkpoint_metrics=d,overrun_duration_seconds=dict(p50=float(np.quantile(over[over>0],.5)),p90=float(np.quantile(over[over>0],.9)),p95=float(np.quantile(over[over>0],.95))),
      checkpoint_conditional_population='Only ended-before-May1 jobs surviving to each checkpoint; right-censored jobs excluded and counted in APRIL_OPEN_RECEIPT. Not an all-arrival unbiased estimate.',
      fixed_residual_is_not_survival_quantile=True,separate_remaining_runtime_model_needed='INCONCLUSIVE: total featureless model failed; subtraction failure does not establish need for second system',survival_model_trained=False,
      model_modified=False,May_outcomes_used=False,provider_freeze=record(ROOT/'PROVIDER_BUNDLE_FREEZE.json')))
    print('APRIL_METRICS',len(f),'CHECKPOINTS',len(c),'ADEQUATE',adequate,flush=True)
if __name__=='__main__':main()
