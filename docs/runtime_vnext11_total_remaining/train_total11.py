from common11 import *
from fit11 import *
from metrics11 import *
from queue9 import replay
from concurrent.futures import ThreadPoolExecutor
import numpy as np,pandas as pd
def work(i,win,target,tr,pre,val):
    arm=win+'_'+target;dest=LOCAL/'BASE_MODELS'/f'fold{i}'/arm;path=LOCAL/f'fold{i}'/(arm+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
    exact=tr[tr.event];support=dict(TRAIN_N=len(exact),TRAIN_censored_N=int(tr.censored.sum()),TRAIN_long4_N=int(exact.runtime_seconds.gt(14400).sum()),TRAIN_long12_N=int(exact.runtime_seconds.gt(43200).sum()),TRAIN_highGPU_N=int(exact.num_gpus_req.ge(16).sum()))
    support['support_sufficient']=support['TRAIN_N']>=5000 and support['TRAIN_long4_N']>=200 and support['TRAIN_long12_N']>=100
    if not support['support_sufficient']:raise RuntimeError('STOP_INSUFFICIENT_WINDOW_TAIL_SUPPORT '+str((i,arm,support)))
    if path.exists():model=Quantiles.load(dest);cached=np.load(path);q=cached['quantiles'];rep=int(cached['repairs'])
    else:
        model=Quantiles.load(dest) if (dest/'model.json').exists() else fit_quantiles(exact,pre,target)
        model.save(dest);q,rep=model.predict(val,threads=4);np.savez_compressed(path,quantiles=q,repairs=rep)
    m=val.event.to_numpy();y=val.loc[m,'runtime_seconds'].to_numpy();gpu=val.loc[m,'num_gpus_req'].to_numpy()
    row=dict(fold=i,arm=arm,window=win,target=target,**support,VALID_censored_N=int(val.censored.sum()),quantile_repair_N=rep,fit_seconds=model.meta['fit_seconds'],**stats(y,gpu,q[m]))
    for c in ['account','qos','partition']:row[c+'_unseen_rate']=float(~val[c].astype('string').fillna('__MISSING__').isin(pre['categorical_mappings'][c]).mean()) if False else float((~val[c].astype('string').fillna('__MISSING__').isin(pre['categorical_mappings'][c])).mean())
    tail=[dict(fold=i,arm=arm,**t) for t in tails(y,gpu,q[m])]
    queue=dict(fold=i,arm=arm,**replay(val,q[:,1],read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['queue_day']))
    part=pd.DataFrame(dict(y=y,gpu=gpu,q50=q[m,0],q90=q[m,1]));print(now(),'BASE_DONE',i,arm,round(row['Q90_coverage'],4),round(row['fit_seconds'],2),flush=True)
    receipt=dict(fold=i,arm=arm,files=[record(dest/p) for p in ['model.json','Q50.txt','Q90.txt']])
    return row,tail,queue,part,receipt
def main():
    stage=read(ROOT/'STAGE_A_VERDICT.json');assert stage['stageB_allowed']
    for p in read(ROOT/'TEMPORAL_DRIFT_FREEZE.json')['files']:assert sha(p['path'])==p['sha256']
    for p in read(ROOT/'PREREGISTRATION.json')['files']:assert sha(p['path'])==p['sha256']
    if not (ROOT/'TRAINING_STARTED.json').exists():write('TRAINING_STARTED.json',dict(time=now(),stage_A_complete=record(ROOT/'TEMPORAL_DRIFT_FREEZE.json'),April_read=False,CPU_threads_per_fit=4,concurrent_independent_fits=2))
    rows=[];ts=[];qs=[];parts={};receipts=[]
    for i in range(1,6):
        val=data(i,'VALID');futures=[]
        with ThreadPoolExecutor(max_workers=2) as pool:
            for win in WINDOWS:
                tr=window(i,win);pre=preprocessing(tr,i)
                for target in ['RAW','LOG','REL']:futures.append(pool.submit(work,i,win,target,tr,pre,val))
            for future in futures:
                r,t,q,p,receipt=future.result();rows.append(r);ts.extend(t);qs.append(q);parts.setdefault(r['arm'],[]).append(p);receipts.append(receipt)
        pd.DataFrame(rows).to_csv(ROOT/'TOTAL_BASE_FOLD_METRICS.csv',index=False)
    fd=pd.DataFrame(rows);td=pd.DataFrame(ts);qd=pd.DataFrame(qs);summary,checks=aggregate(parts,fd,td,qd);chosen,n=select(checks)
    summary.to_csv(ROOT/'TOTAL_BASE_MODEL_COMPARISON.csv',index=False);summary.assign(window=summary.arm.str.rsplit('_',n=1).str[0]).to_csv(ROOT/'TOTAL_WINDOW_COMPARISON.csv',index=False)
    td.to_csv(ROOT/'TOTAL_BASE_LONG_TAIL.csv',index=False);qd.to_csv(ROOT/'TOTAL_BASE_QUEUE_REPLAY.csv',index=False);checks.to_csv(ROOT/'TOTAL_BASE_GATES.csv',index=False)
    win,target=chosen['arm'].rsplit('_',1)
    write('BASE_SELECTION_RESULT.json',dict(time=now(),selected=chosen,eligible_candidates=n,window=win,target=target,diagnostic_only=not chosen['eligible'],April_read=False))
    write('BASE_MODEL_FIT_RECEIPTS.json',dict(time=now(),models=receipts,cache_scope='Local hash-pinned candidate bytes; selected fold models copied to delivery namespace',CPU_threads=4))
    print('BASE_SELECTED',chosen,flush=True)
if __name__=='__main__':main()
