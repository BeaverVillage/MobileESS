"""Single locked April opening after all freezes; no fit or reselection."""
from common8 import *
from baseline8 import load_baselines,module
from features8 import RAW_MAP
from metrics8 import compare,gate,uncertainty
import zipfile,io,sys,numpy as np,pandas as pd,time

def assert_freeze():
    for name in ['MODEL_SELECTION_FREEZE.json','FEATURE_CONTRACT_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json']:assert (ROOT/name).is_file()
    for r in read(ROOT/'PROVIDER_BUNDLE_FREEZE.json')['files']:assert sha(ROOT/r['relative'])==r['sha256']
    for r in read(ROOT/'FEATURE_CONTRACT_FREEZE.json')['files']:assert sha(r['path'])==r['sha256']

def open_april_once():
    assert_freeze();assert not (ROOT/'APRIL_OPEN_RECEIPT.json').exists(),'APRIL_ALREADY_OPENED; never reselect'
    cols=['id','submit_time','start_time','end_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','partition','qos','user_hash','account_hash','name_hash','submit_line_hash','submit_script_hash','work_dir_hash','array_pos']
    write('APRIL_OPEN_RECEIPT.json',dict(time=now(),mode='ONE_LOCKED_RAW_PARTITION_READ',raw=record(RAW),provider_freeze=record(ROOT/'PROVIDER_BUNDLE_FREEZE.json'),feature_freeze=record(ROOT/'FEATURE_CONTRACT_FREEZE.json'),selection_freeze=record(ROOT/'MODEL_SELECTION_FREEZE.json'),May_partition_reads=0,no_selection_after_open=True))
    sys.path.insert(0,str(V6));normalizer=module('frozen_v6_normalizer',V6/'prepare_strict.py')
    with zipfile.ZipFile(RAW) as z:
        members=[x for x in z.namelist() if 'year=2025/month=4/' in x and x.endswith('.parquet')];assert len(members)==1
        raw=pd.read_parquet(io.BytesIO(z.read(members[0])),columns=cols)
    raw=raw[pd.to_numeric(raw.gpus_requested,errors='coerce').gt(0)].copy();f=normalizer.normalize(raw,pd.Timestamp('2025-05-01T00Z'))
    for src,dst in RAW_MAP.items():
        if dst in ['job_name_token','submitline_token','script_token','workdir_token','array_index']:f[dst]=raw[src].to_numpy()
    f=f[f.submit_time.ge(pd.Timestamp('2025-04-01T00Z'))&f.submit_time.lt(pd.Timestamp('2025-05-01T00Z'))].reset_index(drop=True);assert f.job_id.is_unique
    f.to_parquet(ROOT/'APRIL_JOBS.parquet',index=False)
    write('APRIL_POPULATION_AUDIT.json',dict(N=len(f),mature=int(f.label_valid.sum()),unresolved=int((~f.label_valid).sum()),zero_mature=int((f.runtime_seconds.eq(0)&f.label_valid).sum()),
      May_ends_masked_before_runtime_arithmetic=True,member=members[0],cohort=ids(f),mature_cohort=ids(f[f.label_valid]),data=record(ROOT/'APRIL_JOBS.parquet')))
    return f

def checkpoints(f,pred,constant):
    y=f.runtime_seconds.to_numpy();counts=np.maximum(np.ceil(y/1800).astype(int)-1,0);ix=np.repeat(np.arange(len(f)),counts)
    starts=np.repeat(np.cumsum(counts)-counts,counts);elapsed=(np.arange(len(ix))-starts+1)*1800;actual=y[ix]-elapsed
    assert (actual>0).all();out=[]
    for arm,values in [('V8',pred[:,1]),('Bconst',np.full(len(f),constant))]:
        proxy=np.maximum(values[ix]-elapsed,0);over=elapsed>=values[ix];gpu=f.num_gpus_req.to_numpy()[ix]
        for scope,mask in [('ALL',np.ones(len(ix),bool)),('ACTUAL_GT4H',y[ix]>14400),('ELAPSED_GT4H',elapsed>14400),('HIGH_GPU',gpu>=16)]:
            if not mask.any():continue
            ae=np.abs(proxy[mask]-actual[mask]);g=gpu[mask];row=dict(arm=arm,scope=scope,N=int(mask.sum()),unique_jobs=int(np.unique(ix[mask]).size),remaining_MAE_seconds=float(ae.mean()),GPU_remaining_MAE_seconds=float(np.average(ae,weights=g)),overrun_checkpoint_fraction=float(over[mask].mean()),GPU_overrun_fraction=float(np.average(over[mask],weights=g)))
            for t in [900,1800,3600,7200,14400]:
                yes=actual[mask]>t;guess=proxy[mask]>t;tp=int((yes&guess).sum());fn=int((yes&~guess).sum());fp=int((~yes&guess).sum())
                row.update({f'accuracy_gt_{t}s':float((yes==guess).mean()),f'false_negative_gt_{t}s':fn,f'false_positive_gt_{t}s':fp,f'recall_gt_{t}s':tp/(tp+fn) if tp+fn else None})
            out.append(row)
    pd.DataFrame(out).to_csv(ROOT/'CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv',index=False)
    pd.DataFrame(dict(job_id=f.job_id.to_numpy()[ix],elapsed_seconds=elapsed,actual_remaining_seconds=actual,V8_remaining_proxy=np.maximum(pred[ix,1]-elapsed,0),Bconst_remaining_proxy=np.maximum(constant-elapsed,0))).to_parquet(ROOT/'APRIL_RUNNING_CHECKPOINTS.parquet',index=False)
    return out

def main():
    f=open_april_once();assert_freeze();provider=module('runtime8_locked_provider',ROOT/'RUNTIME_PROVIDER/provider.py').RuntimeProvider(ROOT/'RUNTIME_PROVIDER',allow_research=True)
    records=f[provider.input_columns].to_dict('records');t=time.perf_counter();p=provider.predict_batch(records);lat=(time.perf_counter()-t)*1000
    bp,c,_=load_baselines();b=bp(f);bc=c.predict_array(len(f));saved=f[['job_id']].copy()
    for name,array in [('V8',p),('B0',b),('Bconst',bc)]:saved[name+'_Q50']=array[:,0];saved[name+'_Q90']=array[:,1]
    saved.to_parquet(ROOT/'APRIL_PREDICTIONS.parquet',index=False)
    m=f.label_valid.to_numpy();g=f[m];preds={'W0':np.column_stack([g.requested_seconds]*2),'B0':b[m],'Bconst':bc[m],'V8':p[m]}
    rows,st=compare(g,preds,'APRIL_LOCKED');pd.DataFrame(rows).to_csv(ROOT/'APRIL_LOCKED_RUNTIME_METRICS.csv',index=False);pd.DataFrame(st).to_csv(ROOT/'APRIL_STRATIFIED_RUNTIME_METRICS.csv',index=False)
    pd.DataFrame(uncertainty(g,p[m],b[m],'APRIL_LOCKED_DESCRIPTIVE_ONLY')).to_csv(ROOT/'APRIL_PAIRED_UNCERTAINTY.csv',index=False)
    unseen=[]
    for col,mapping in provider.prep['categorical_mappings'].items():
        values=f[col].astype('string').fillna('__MISSING__');unseen.append(dict(feature=col,role='APRIL',N=len(f),unseen_rate=float((~values.isin(mapping)).mean()),refit=False))
    pd.DataFrame(unseen).to_csv(ROOT/'APRIL_UNSEEN_CATEGORIES.csv',index=False)
    diagnostics=checkpoints(g,p[m],float(bc[0,1]));d=next(r for r in diagnostics if r['arm']=='V8' and r['scope']=='ALL')
    adequate=d['remaining_MAE_seconds']<=3600 and d['overrun_checkpoint_fraction']<=.15 and all(d[f'accuracy_gt_{t}s']>=.8 for t in [900,1800,3600,7200,14400])
    over=[]
    for name,array in preds.items():
        excess=np.maximum(g.runtime_seconds.to_numpy()-array[:,1],0);mask=excess>0
        over.append(dict(arm=name,N=len(g),overrun_N=int(mask.sum()),overrun_fraction=float(mask.mean()),GPU_weighted_overrun=float(np.average(mask,weights=g.num_gpus_req)),overrun_GPUh=float((excess*g.num_gpus_req/3600).sum()),
          extension_intervals_if_observed_running=int(np.ceil(excess/900).sum()),duration_p50_seconds=float(np.median(excess[mask])) if mask.any() else 0,force_completion=False))
    pd.DataFrame(over).to_csv(ROOT/'OVERRUN_DIAGNOSTIC.csv',index=False)
    old=pd.read_parquet(V6/'APRIL_B0_PREDICTIONS.parquet');pair=saved.merge(old,on='job_id',suffixes=('','_old'),validate='one_to_one');err=float(np.max(np.abs(pair[['B0_Q50','B0_Q90']].to_numpy()-pair[['B0_Q50_old','B0_Q90_old']].to_numpy())));assert err<1e-7
    write('APRIL_EVALUATION_RECEIPT.json',dict(time=now(),executed_once=True,gate=gate(g,p[m],b[m]),checkpoint_adequate=adequate,checkpoint_N=d['N'],checkpoint_scope='Mature-before-May1 positive-GPU archive cohort; all actual surviving 30m checkpoints; excludes unresolved labels, length-biased checkpoint weighting',
      batch_inference_ms=lat,batch_N=len(f),B0_prior_April_reproduction_max_abs_seconds=err,may_outcomes_used=False,model_changed=False,
      no_April_selection=True,subtraction_is_not_survival_quantile=True))
    assert_freeze();print('APRIL_COMPLETE',len(f),'mature',len(g),'checkpoint',adequate,flush=True)
if __name__=='__main__':main()
