from common9 import *
from fit9 import *
import sys,gc
ARMS=['D1']+[f'D2_{d}_{s}' for d in ['normal','logistic','extreme'] for s in [1.0,1.5]]+['D3','D2_normal_1.0_EXACT']
def main():
    prereg=read(ROOT/'TEMPORAL_FOLD_PREREGISTRATION.json')
    for r in prereg['files']:assert sha(r['path'])==r['sha256'],'PREREGISTRATION_CHANGED'
    if not (ROOT/'TRAINING_STARTED.json').exists():write('TRAINING_STARTED.json',dict(time=now(),preregistration_sha256=sha(ROOT/'TEMPORAL_FOLD_PREREGISTRATION.json'),arms=ARMS,April_opened=False))
    for i in range(1,6):
        folder=LOCAL/f'fold{i}';prep=read(ROOT/f'FOLD_{i}_PREPROCESSING.json')
        train=pd.read_parquet(folder/'TRAIN.parquet');cal=pd.read_parquet(folder/'CAL.parquet');val=pd.read_parquet(folder/'VALID.parquet')
        xc=matrix(cal,prep);xv=matrix(val,prep)
        for arm in ARMS:
            dest=ROOT/'FOLD_MODELS'/f'fold{i}'/arm
            if (folder/(arm+'.npz')).exists():continue
            print(now(),'FIT',i,arm,len(train),flush=True)
            model=Distribution.load(dest) if (dest/'model.json').exists() else fit(train,prep,arm)
            if not (dest/'model.json').exists():model.save(dest)
            print(now(),'PREDICT',i,arm,'fitsec',model.meta['training_seconds'],flush=True)
            pc=model.parameters(xc);pv=model.parameters(xv)
            np.savez_compressed(folder/(arm+'.npz'),cal_parameters=pc,val_parameters=pv,cal_quantiles=model.quantiles(pc),val_quantiles=model.quantiles(pv))
            print(now(),'DONE',i,arm,flush=True);del model,pc,pv;gc.collect()
    write('TRAINING_COMPLETED.json',dict(time=now(),folds=5,arms=ARMS,April_opened=False))
if __name__=='__main__':main()
