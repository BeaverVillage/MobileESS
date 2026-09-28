from common9 import *
import numpy as np,pandas as pd
v8path()
from baseline8 import load_baselines,module
from model8 import Predictor
from features8 import engineer
def main():
    bp,c,files=load_baselines();const=c.predict_array(1)[0]
    v8=Predictor.load(V8/'RUNTIME_PROVIDER/model');prep=read(V8/'RUNTIME_PROVIDER/preprocessing.json')
    raw=pd.read_parquet(V7/'.local/GPU_PREAPRIL.parquet',columns=['id','user_hash'])
    raw['id']=raw.id.astype(str);assert raw.id.is_unique;users=raw.set_index('id').user_hash
    outputs=[]
    for i in range(1,6):
        f=pd.read_parquet(LOCAL/f'fold{i}/VALID.parquet');f['user']=f.job_id.map(users)
        b=bp(f);v=v8.predict(engineer(f,prep['categorical_mappings']))
        z=f[['job_id']].copy()
        for arm,p in [('B0',b),('Bconst',np.tile(const,(len(f),1))),('V8',v)]:
            z[arm+'_Q50']=p[:,0];z[arm+'_Q90']=p[:,1]
        z.to_parquet(LOCAL/f'fold{i}/baselines.parquet',index=False);outputs.append(z)
    old=pd.read_parquet(V8/'PREAPRIL_BASELINES.parquet');pair=pd.concat(outputs).merge(old,on='job_id',suffixes=('','_old'))
    err=float(np.max(abs(pair[['B0_Q50','B0_Q90']].to_numpy()-pair[['B0_Q50_old','B0_Q90_old']].to_numpy())))
    assert err<1e-7
    write('BASELINE_REPRODUCTION.json',dict(time=now(),B0_overlap_N=len(pair),B0_max_absolute_error=err,Bconst_values=const.tolist(),
        baseline_files=[record(p) for p in files],V8_files=[record(p) for p in (V8/'RUNTIME_PROVIDER').rglob('*') if p.is_file() and '__pycache__' not in p.parts],
        no_refit=True,early_fold_B0='NONCAUSAL_RETROSPECTIVE_REFERENCE until Mar14T08Z',all_fold_V8_Bconst='NONCAUSAL_RETROSPECTIVE_REFERENCE',April_opened=False))
    print('BASELINES_READY',len(pair),err,flush=True)
if __name__=='__main__':main()
