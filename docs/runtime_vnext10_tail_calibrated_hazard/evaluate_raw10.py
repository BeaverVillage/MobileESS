from common10 import *
from hazard10 import Hazard
from calibration10 import *
from metrics10 import *
from metrics9 import calibration as v9calibration
from queue9 import replay
import numpy as np,pandas as pd
def main():
    assert (ROOT/'TRAINING_COMPLETED.json').exists();folds=[];tails=[];queues=[];parts={};audits=[]
    prior=pd.read_csv(V9/'MODEL_COMPARISON.csv').set_index('arm');w0reservation=float(prior.loc['W0','reserved_GPUh'])
    wq=pd.read_csv(V9/'PREAPRIL_QUEUE_REPLAY.csv');wq=wq[wq.arm.eq('W0')]
    for i in range(1,6):
        val=fold_data(i,'VALID');cal=fold_data(i,'CAL');m=val.event.to_numpy(bool);y=val.loc[m,'runtime_seconds'].to_numpy();gpu=val.loc[m,'num_gpus_req'].to_numpy()
        v9saved=np.load(V9/'.local'/f'fold{i}/D1.npz');delta,_=v9calibration(cal,val,v9saved['cal_quantiles'],v9saved['val_quantiles'],'ROLLING14');v9q=np.maximum(v9saved['val_quantiles']+delta[:,None],0)
        old=pd.read_parquet(V9/'.local/D1__ROLLING14_evaluation.parquet');old=old[old.fold.eq(i)]
        assert np.array_equal(old.job_id.to_numpy(),val.loc[m,'job_id'].to_numpy())
        error=float(np.max(abs(old[['q50','q90']].to_numpy()-v9q[m][:,[0,3]])));assert error<1e-7
        audits.append(dict(fold=i,N=int(m.sum()),V9_prediction_max_error=error))
        for grid in ['G0','G1','G2']:
            model=Hazard.load(ROOT/'FOLD_MODELS'/f'fold{i}'/grid);saved=np.load(LOCAL/f'fold{i}'/(grid+'.npz'));par=saved['val_parameters']
            for cont in ['LAST_RATE','TRAIN_EXPONENTIAL']:
                arm='T1_'+grid+'_'+cont;mapping=ProbabilityMap();q=maps_quantiles(model,par,mapping,cont)
                score=distribution_metrics(score_inputs(model,par,val,cont),[(np.ones(len(val),bool),mapping)])
                s=stats(y,gpu,q[m,0],q[m,3]);folds.append(dict(fold=i,arm=arm,censored_N=int(val.censored.sum()),**s,**score))
                tails.extend(dict(fold=i,arm=arm,**r) for r in tail_rows(y,gpu,q[m]))
                day=read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['queue_day']
                queues.append(dict(fold=i,arm=arm,**replay(val,q[:,3],day)))
                parts.setdefault(arm,[]).append(pd.DataFrame(dict(y=y,gpu=gpu,q50=q[m,0],q90=q[m,3])))
                np.savez_compressed(LOCAL/f'fold{i}'/(arm+'.npz'),quantiles=q)
        print(now(),'RAW_FOLD_COMPLETE',i,flush=True)
    fd=pd.DataFrame(folds);td=pd.DataFrame(tails);qd=pd.DataFrame(queues)
    fd.to_csv(ROOT/'RAW_GRID_FOLD_METRICS.csv',index=False);td.to_csv(ROOT/'RAW_GRID_LONG_TAIL.csv',index=False);qd.to_csv(ROOT/'RAW_GRID_QUEUE.csv',index=False)
    summaries=[];gg=[]
    for arm,p in parts.items():
        s=pooled(arm,p,fd,w0reservation);summaries.append(s)
        checks=gates(s,fd[fd.arm.eq(arm)],td[td.arm.eq(arm)],qd[qd.arm.eq(arm)],wq)
        gg.append(dict(arm=arm,**checks,Q90_pinball=s['Q90_pinball'],reservation_actual_GPUh=s['reservation_actual_GPUh'],Q50_MAE=s['Q50_MAE'],coverage_std=s['coverage_std']))
    pd.DataFrame(summaries).to_csv(ROOT/'TAIL_GRID_COMPARISON.csv',index=False);rank=pd.DataFrame(gg);rank.to_csv(ROOT/'RAW_GRID_GATES.csv',index=False)
    eligible=rank[rank.eligible];z=eligible if len(eligible) else rank
    ordering=([] if len(eligible) else ['failed_gates'])+['Q90_pinball','reservation_actual_GPUh','Q50_MAE','coverage_std'];chosen=z.sort_values(ordering).iloc[0].to_dict()
    fields=chosen['arm'].split('_');grid=fields[1];cont='_'.join(fields[2:])
    write('RAW_GRID_SELECTION.json',dict(time=now(),selected=chosen,grid=grid,continuation=cont,before_calibration_comparison=True,April_read=False,method='preregistered sequential raw-grid stage; no exhaustive grid/calibration interaction search'))
    write('V9_REPRODUCTION.json',dict(time=now(),PASS=True,folds=audits,V9_model_bytes_preserved=True,V9_published_proper_NLL='INFINITE, never reinterpret as passed',model_selection_eligible=False,April_payload_read=False))
    write('TAIL_EXTRAPOLATION_AUDIT.json',dict(time=now(),training=read(ROOT/'TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json'),selected_grid=grid,selected_continuation=cont,
        reason='preregistered five-fold safety-first raw-stage ranking',gt24h_effect=[dict(arm=s['arm'],coverage=s['gt24h_coverage'],N=s['gt24h_N']) for s in summaries],
        finite_truncation=False,T4_implemented=False,T4_reason='No additional parametric family needed to execute bounded comparison; terminal handling remains explicit last-rate versus TRAIN exponential only'))
    print('RAW_SELECTED',grid,cont,chosen,flush=True)
if __name__=='__main__':main()
