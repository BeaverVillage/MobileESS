from common11 import *
from fit11 import *
from checkpoint11 import *
from metrics11 import stats
import numpy as np,pandas as pd,gc
def evaluate(arm,i,g,ix,e,y,q,totalq):
    rows=[];gpu=g.num_gpus_req.to_numpy()[ix];total=g.runtime_seconds.to_numpy()[ix]
    for typ,name,m in masks(e,y,total):
        if not m.any():continue
        s=stats(y[m],gpu[m],q[m]);s.update(phase='PREAPRIL',fold=i,arm=arm,stratum_type=typ,stratum=name,unique_jobs=int(np.unique(ix[m]).size),overrun_checkpoint_fraction=float((e[m]>=totalq[ix[m],1]).mean()))
        for t in [900,1800,3600,7200,14400]:
            a=y[m]>t;p=q[m,1]>t;s[f'accuracy_gt_{t}s']=float((a==p).mean());s[f'TP_gt_{t}s']=int((a&p).sum());s[f'FP_gt_{t}s']=int((~a&p).sum());s[f'FN_gt_{t}s']=int((a&~p).sum())
        rows.append(s)
    return rows
def main():
    total=read(ROOT/'TOTAL_SELECTION_RESULT.json')
    if not total['tail_classifier_meaningful']:raise RuntimeError('V11_STOP_CONDITION_TAIL_CLASSIFIER_TEMPORAL_DISCRIMINATION_FAILED; Stage C must not train')
    win=total['window'];rows=[];audits=[];splits=[];fits=[]
    for i in range(1,6):
        tr=window(i,win);val=data(i,'VALID');cal=data(i,'CAL');pre=Quantiles.load(ROOT/'FOLD_MODELS'/f'fold{i}/total_base').pre
        identities={role:set(f.job_id) for role,f in [('TRAIN',tr),('CAL',cal),('VALID',val)]}
        cross={a+'_'+b:len(identities[a]&identities[b]) for a,b in [('TRAIN','VALID'),('TRAIN','CAL'),('CAL','VALID')]};assert sum(cross.values())==0
        splits.append(dict(fold=i,job_episode_intersections=cross,assignment_before_expansion=True,scope='within each chronological fold'))
        gt,it,et,yt=checkpoints(tr);gv,iv,ev,yv=checkpoints(val);train_records=gt.iloc[it][RAW].reset_index(drop=True);valid_records=gv.iloc[iv][RAW].reset_index(drop=True)
        for role,f,g,ix,e,y in [('TRAIN',tr,gt,it,et,yt),('VALID',val,gv,iv,ev,yv)]:
            audits.append(dict(fold=i,role=role,window=win if role=='TRAIN' else 'inherited VALID',job_N=len(f),completed_N=len(g),checkpoint_N=len(ix),checkpoint_job_N=int(np.unique(ix).size),
                excluded_censored_job_N=int(f.censored.sum()),pending_job_N=int((~(f.event|f.censored)).sum()),post_completion_rows=0,checkpoint_target_positive=bool((y>0).all()),future_checkpoint_count_used_as_feature=False,
                max_checkpoint=str((pd.DatetimeIndex(g.start_time.iloc[ix])+pd.to_timedelta(e,unit='s')).max())))
        outputs,totalq=references(i,gv,iv,ev)
        for arm,target,noe in [('R3_RAW','RAW',False),('R4_LOG','LOG',False),('R3_NO_ELAPSED','RAW',True)]:
            folder=ROOT/'FOLD_MODELS'/f'fold{i}'/arm;cache=LOCAL/f'fold{i}'/(arm+'_REMAINING.npz')
            model=Quantiles.load(folder) if (folder/'model.json').exists() else fit_quantiles(train_records,pre,target,y=yt,elapsed=et,no_elapsed=noe)
            model.save(folder)
            if cache.exists():saved=np.load(cache);q=saved['quantiles'];rep=int(saved['repairs'])
            else:q,rep=model.predict(valid_records,elapsed=ev,threads=4);np.savez_compressed(cache,quantiles=q,repairs=rep)
            fits.append(dict(fold=i,arm=arm,TRAIN_checkpoint_N=len(it),VALID_checkpoint_N=len(iv),fit_seconds=model.meta['fit_seconds'],quantile_repair_N=rep,CPU_threads=4))
            outputs[arm]=q;print(now(),'REMAINING_FIT',i,arm,len(it),round(model.meta['fit_seconds'],2),flush=True)
            del model;gc.collect()
        for arm,q in outputs.items():rows.extend(evaluate(arm,i,gv,iv,ev,yv,q,totalq))
        pd.DataFrame(rows).to_csv(ROOT/'REMAINING_ALL_STRATA.csv',index=False)
        del train_records,valid_records,outputs;gc.collect()
    allr=pd.DataFrame(rows);fold=allr[allr.stratum_type.eq('ALL')];elapsed=allr[allr.stratum_type.eq('ELAPSED')];remaining=allr[allr.stratum_type.eq('ACTUAL_REMAINING')];long=allr[allr.stratum_type.eq('LONG_RUNNING')]
    fold.to_csv(ROOT/'REMAINING_FOLD_METRICS.csv',index=False);elapsed.to_csv(ROOT/'REMAINING_ELAPSED_STRATA.csv',index=False);remaining.to_csv(ROOT/'REMAINING_ACTUAL_STRATA.csv',index=False);long.to_csv(ROOT/'REMAINING_LONG_RUNNING_METRICS.csv',index=False);pd.DataFrame(fits).to_csv(ROOT/'REMAINING_FIT_TIMINGS.csv',index=False)
    pool=[]
    for (arm,typ,name),z in allr.groupby(['arm','stratum_type','stratum']):
        r=dict(arm=arm,stratum_type=typ,stratum=name,N=int(z.N.sum()))
        for col in ['Q50_MAE','Q90_MAE','Q90_coverage','Q90_pinball','overrun_checkpoint_fraction']+[f'accuracy_gt_{t}s' for t in [900,1800,3600,7200,14400]]:r[col]=float(np.average(z[col],weights=z.N))
        if typ=='ALL':r.update(min_fold_coverage=float(z.Q90_coverage.min()),max_fold_coverage=float(z.Q90_coverage.max()),coverage_std=float(z.Q90_coverage.std(ddof=0)))
        pool.append(r)
    pooled=pd.DataFrame(pool);pooled.to_csv(ROOT/'REMAINING_POOLED_STRATA.csv',index=False);summary=pooled[pooled.stratum_type=='ALL'];summary.to_csv(ROOT/'REMAINING_MODEL_COMPARISON.csv',index=False)
    baseline=summary.set_index('arm').loc['R1_TOTAL_MINUS'];checks=[]
    for arm in ['R3_RAW','R4_LOG']:
        s=summary.set_index('arm').loc[arm];ages=elapsed[(elapsed.arm==arm)&(elapsed.N>=1000)];l=pooled[(pooled.arm==arm)&(pooled.stratum=='elapsed_gt12h')].iloc[0]
        c=dict(REMAINING_Q90_GATE_PASS=.88<=s.Q90_coverage<=.92,REMAINING_TEMPORAL_STABILITY_PASS=s.min_fold_coverage>=.85 and s.max_fold_coverage<=.95,
            REMAINING_ELAPSED_STABILITY_PASS=bool(ages.Q90_coverage.between(.8,.97).all()),REMAINING_LONG_RUNNING_PASS=l.Q90_coverage>=.85,
            REMAINING_PINBALL_PASS=s.Q90_pinball<=baseline.Q90_pinball,REMAINING_Q50_MAE_PASS=s.Q50_MAE<=1.05*baseline.Q50_MAE)
        checks.append(dict(arm=arm,**{k:bool(v) for k,v in c.items()},eligible=all(c.values()),failed_gates=sum(not v for v in c.values()),Q90_pinball=s.Q90_pinball,Q50_MAE=s.Q50_MAE,coverage_std=s.coverage_std))
    gate=pd.DataFrame(checks);gate.to_csv(ROOT/'REMAINING_GATES.csv',index=False);eligible=gate[gate.eligible];rank=eligible if len(eligible) else gate
    chosen=rank.sort_values(([] if len(eligible) else ['failed_gates'])+['Q90_pinball','Q50_MAE','coverage_std']).iloc[0].to_dict()
    write('REMAINING_SELECTION_RESULT.json',dict(time=now(),selected=chosen,eligible_candidates=len(eligible),window=win,target='RAW' if chosen['arm']=='R3_RAW' else 'LOG',diagnostic_only=not chosen['eligible'],total_prediction_features=False,April_read=False))
    write('CHECKPOINT_SAMPLE_AUDIT.json',dict(time=now(),checkpoint_seconds=1800,rows=audits,all_mature_surviving_checkpoints=True,unit_checkpoint_weights=True,no_future_features=True,unresolved_remaining_labels_not_fabricated=True))
    write('CHECKPOINT_SPLIT_AUDIT.json',dict(time=now(),folds=splits,CHECKPOINT_EPISODE_LEAKAGE=0,JOB_EPISODE_CROSS_SPLIT_LEAKAGE=0,scope='Within fold TRAIN/CAL/VALID episode sets. Earlier VALID jobs can enter later expanding TRAIN after completion; no job crosses roles inside any held-out evaluation.'))
    write('OOF_TOTAL_FEATURE_AUDIT.json',dict(time=now(),TOTAL_PREDICTION_FEATURE_USED=False,OOF_TOTAL_PREDICTION_LEAKAGE=0,reason='Optional initial-total prediction features omitted; remaining consumes request descriptors and observed elapsed only'))
    print('REMAINING_SELECTED',chosen,flush=True)
if __name__=='__main__':main()
