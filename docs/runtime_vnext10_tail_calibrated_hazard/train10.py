from common10 import *
from hazard10 import Hazard,age_matrix
from features8 import engineer
import numpy as np,pandas as pd,lightgbm as lgb,time,gc,shutil
def matrix(f,pre):return engineer(f,pre['categorical_mappings'])[pre['columns']].astype('float32')
def fit(train,pre,grid,fold,device='cpu'):
    t=time.perf_counter();edges=np.array(read(ROOT/'TAIL_GRID_CANDIDATES.json')['by_fold'][str(fold)][grid],float);k=len(edges)-1
    x=matrix(train,pre);y=train.duration_lower.to_numpy(float);exact=train.event.to_numpy(bool);within=exact&(y<=edges[-1])
    counts=np.minimum(np.where(within,np.searchsorted(edges[1:],y,side='left')+1,np.searchsorted(edges[1:],y,side='right')),k)
    rows=np.repeat(np.arange(len(train)),counts);bins=np.arange(len(rows))-np.repeat(np.cumsum(counts)-counts,counts)
    xx=np.column_stack([x.to_numpy()[rows],age_matrix(edges)[bins]]);target=(within[rows]&(bins==counts[rows]-1)).astype('int8')
    params=read(ROOT/'EXPERIMENT_PROTOCOL.json')['learner'].copy()
    if device=='gpu':params.update(device_type='gpu',gpu_platform_id=0,gpu_device_id=0,verbosity=1,deterministic=False)
    cols=pre['columns'];cats=[cols.index(c) for c in ['qos','partition','account'] if c in cols]
    b=lgb.LGBMClassifier(**params);b.fit(xx,target,categorical_feature=cats)
    tail=read(ROOT/'TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json')['by_fold'][str(fold)]['by_grid'][grid]
    return Hazard(dict(kind='D1',grid=grid,columns=cols,edges=edges.tolist(),tail_exponential_rate=tail['exponential_rate'],
        training_seconds=time.perf_counter()-t,device=device,threads=4,TRAIN_N=len(train),person_period_N=len(rows),exact_above_endpoint_censored_N=int((exact&~within).sum()),fit_cutoff=pre['fit_cutoff']),b.booster_)
def main():
    for r in read(ROOT/'PREREGISTRATION.json')['files']:assert sha(r['path'])==r['sha256']
    if not (ROOT/'TRAINING_STARTED.json').exists():write('TRAINING_STARTED.json',dict(time=now(),preregistration=record(ROOT/'PREREGISTRATION.json'),April_read=False))
    for i in range(1,6):
        train=fold_data(i,'TRAIN');cal=fold_data(i,'CAL');val=fold_data(i,'VALID');pre=prep(i);xt=matrix(train,pre);xc=matrix(cal,pre);xv=matrix(val,pre);folder=LOCAL/f'fold{i}';folder.mkdir(exist_ok=True)
        for grid in ['G0','G1','G2']:
            dest=ROOT/'FOLD_MODELS'/f'fold{i}'/grid
            if (folder/(grid+'.npz')).exists():continue
            print(now(),'TRAIN',i,grid,flush=True)
            if (dest/'model.json').exists():model=Hazard.load(dest)
            elif grid=='G0':
                old=read(V9/'FOLD_MODELS'/f'fold{i}/D1/model.json');old.update(grid=grid,tail_exponential_rate=read(ROOT/'TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json')['by_fold'][str(i)]['by_grid'][grid]['exponential_rate'],reused_frozen_V9=True)
                model=Hazard(old,lgb.Booster(model_str=(V9/'FOLD_MODELS'/f'fold{i}/D1/0.txt').read_text(encoding='utf-8')));model.save(dest)
            else:model=fit(train,pre,grid,i);model.save(dest)
            print(now(),'TRAIN_RISK',i,grid,flush=True);risk=model.train_risk(xt);bounds=np.unique(np.quantile(risk,[1/3,2/3])).tolist()
            groups=np.digitize(risk,bounds,right=True)
            support=[dict(group=int(g),N=int(np.sum(groups==g)),events=int(np.sum(train.event&(groups==g))),long_gt4h=int(np.sum(train.event&train.duration_lower.gt(14400)&(groups==g))),long_gt12h=int(np.sum(train.event&train.duration_lower.gt(43200)&(groups==g)))) for g in np.unique(groups)]
            name=f'RISK_BOUNDARIES/fold{i}_{grid}.json'
            if not (ROOT/name).exists():write(name,dict(time=now(),bounds=bounds,TRAIN_only=True,raw_p4_before_calibration=True,support=support))
            print(now(),'PREDICT',i,grid,flush=True)
            if grid=='G0':
                cached=np.load(V9/'.local'/f'fold{i}/D1.npz');pc=cached['cal_parameters'];pv=cached['val_parameters']
                audit=model.parameters(xv.head(30),threads=4);assert np.max(abs(audit-pv[:30]))<1e-12
            else:pc=model.parameters(xc,threads=4);pv=model.parameters(xv,threads=4)
            np.savez_compressed(folder/(grid+'.npz'),cal_parameters=pc,val_parameters=pv)
            print(now(),'DONE',i,grid,model.meta['training_seconds'],flush=True);del model,pc,pv;gc.collect()
    write('TRAINING_COMPLETED.json',dict(time=now(),folds=5,new_grid_fits=10,G0_frozen_reused=True,backend='CPU4',April_read=False))
if __name__=='__main__':main()
