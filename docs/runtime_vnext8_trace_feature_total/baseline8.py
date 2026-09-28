from common8 import *
import sys,importlib.util,numpy as np,pandas as pd

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def load_baselines():
    sys.path.insert(0,str(LOCAL/'dependencies'))
    # Frozen pickle was written with NumPy2 module names; retain NumPy1.26 numerical
    # implementation and alias import locations only. Exact predictions tested below.
    import numpy.core.numeric,numpy.core.multiarray
    sys.modules.setdefault('numpy._core.numeric',numpy.core.numeric)
    sys.modules.setdefault('numpy._core.multiarray',numpy.core.multiarray)
    sys.path.insert(0,str(V6));b=module('frozen_v6_baseline',V6/'baseline.py');bp,files=b.load()
    c=module('frozen_v6_provider',V6/'RUNTIME_PROVIDER/provider.py').RuntimeProvider(V6/'RUNTIME_PROVIDER',allow_research=True)
    return bp,c,files
def main():
    bp,c,files=load_baselines();f=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet');data=roles(f)
    src=OLD/'predictions/LGBM_180_14/20250314T0800.parquet';prior=pd.read_parquet(src);prior=prior[prior.state.eq('PENDING')]
    pred=bp(prior);error=float(np.max(np.abs(pred-prior[['Q50','Q90']].to_numpy())));assert error<1e-7
    const=c.predict_array(1)[0];expected=np.array(read(V6/'MODEL_SELECTION_FREEZE.json')['calibrated_quantiles']);ce=float(np.max(np.abs(const-expected)));assert ce<1e-7
    out=[]
    for role,g in data.items():
        if role=='TRAIN':continue
        p=bp(g);z=g[['job_id']].copy();z['role']=role;z['B0_Q50']=p[:,0];z['B0_Q90']=p[:,1];z['Bconst_Q50']=const[0];z['Bconst_Q90']=const[1];z['W0']=g.requested_seconds.to_numpy();out.append(z)
    allpred=pd.concat(out,ignore_index=True);allpred.to_parquet(ROOT/'PREAPRIL_BASELINES.parquet',index=False)
    oldpred=pd.read_parquet(V6/'PREAPRIL_B0_PREDICTIONS.parquet');pair=allpred.merge(oldpred,on='job_id',suffixes=('','_old'),validate='one_to_one')
    same=float(np.max(np.abs(pair[['B0_Q50','B0_Q90']].to_numpy()-pair[['B0_Q50_old','B0_Q90_old']].to_numpy())));assert same<1e-7
    write('BASELINE_REPRODUCTION.json',dict(PASS=True,NO_REFIT=True,W0_max_absolute_error=0.,B0_max_absolute_error=error,B0_vNext6_preapril_max_absolute_error=same,Bconst_max_absolute_error=ce,
      B0_features=['requested_seconds','num_nodes_req','num_cores_req','num_gpus_req','requested_memory_mib','partition','qos','user','account'],
      B0_source=record(src),B0_model_files=[record(x) for x in files],Bconst_model_files=[record(V6/'RUNTIME_PROVIDER'/p) for p in ['Q50.txt','Q90.txt','preprocessing.json','runtime_contract.json','provider.py']],
      B0_scope='Previous frozen full-feature LGBM_180_14 at March14T08Z, research-only',Bconst_values=const.tolist(),no_April_read=True))
    print('BASELINES_REPRODUCED',error,same,ce,len(allpred),flush=True)
if __name__=='__main__':main()
