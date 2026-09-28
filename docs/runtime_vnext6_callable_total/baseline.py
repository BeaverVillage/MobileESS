"""Inference-only replay of frozen March14 full-feature RESEARCH baseline."""
from paths import *
import sys,gzip,pickle
sys.path.insert(0,str(HPC/'src'))
import numpy as np,pandas as pd,lightgbm as lgb
from hpc_oda_commons.models.job_runtime_moe_xgboost.model import MoEXGBoostConfig,MoEXGBoostModel
FEATURES=['requested_seconds','num_nodes_req','num_cores_req','num_gpus_req','requested_memory_mib','partition','qos','user','account']
def load():
    folder=OLD/'fits/LGBM_180_14/20250314T0800/PENDING'
    prep=OLD/'fits/MOE_180_14/20250314T0800/moe.pkl.gz'
    assert sha(prep)=='a012e5181b38265dbad27f1b479f98871569da174552220f341e35b4826b6073'
    with gzip.open(prep,'rb') as f:art,_=pickle.load(f)
    model=MoEXGBoostModel(MoEXGBoostConfig(n_windows=120,test_window_hours=6,training_lookback_days=120,enable_power_users=False,time_decay_rate=.05,objective='reg:absoluteerror'))
    boosts=[lgb.Booster(model_str=gzip.decompress((folder/f'Q{q}.txt.gz').read_bytes()).decode()) for q in [50,90]]
    def predict(f):
        # Records explicitly restricted: no IDs, truth, saved predictions, or lookup.
        x=model._transform_rows(f[FEATURES].to_dict('records'),art)
        return np.maximum.accumulate(np.maximum(np.column_stack([b.predict(x,num_threads=1) for b in boosts]),0),axis=1)
    return predict,[prep,*[folder/f'Q{q}.txt.gz' for q in [50,90]]]
def main():
    predict,files=load()
    if '--april' not in sys.argv:
        source=OLD/'predictions/LGBM_180_14/20250314T0800.parquet'
        old=pd.read_parquet(source);old=old[old.state.eq('PENDING')]
        p=predict(old);diff=np.max(np.abs(p-old[['Q50','Q90']].to_numpy()),axis=0)
        assert np.max(diff)<1e-7
        write('B0_FROZEN_BASELINE_REPRODUCTION.json',dict(PASS=True,N=len(old),max_absolute_seconds=diff.tolist(),
          target='PENDING total executed runtime Q50/Q90',training_cutoff='2025-03-14T08:00Z',
          no_refit=True,no_prediction_lookup=True,source=record(source),model_files=[record(p) for p in files],
          research_only=True,production_selection_eligible=False,request_version_authority='UNVERIFIED'))
    mode='APRIL' if '--april' in sys.argv else 'PREAPRIL'
    if mode=='APRIL':assert (ROOT/'PROVIDER_BUNDLE_FREEZE.json').exists()
    f=pd.read_parquet(ROOT/f'{mode}_JOBS.parquet')
    if mode=='PREAPRIL':f=f[f.role.isin(['DEV','CAL_FIT','CAL_VALID'])]
    p=predict(f);out=f[['job_id']].copy();out['B0_Q50']=p[:,0];out['B0_Q90']=p[:,1]
    out.to_parquet(ROOT/f'{mode}_B0_PREDICTIONS.parquet',index=False)
    print(mode,'B0_NO_REFIT',len(out),flush=True)
if __name__=='__main__':main()
