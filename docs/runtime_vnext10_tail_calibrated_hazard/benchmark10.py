from common10 import *
from train10 import fit,matrix
from hazard10 import Hazard
from calibration10 import ProbabilityMap,maps_quantiles
import numpy as np,pandas as pd,time,gc
def main():
    grid=read(ROOT/'RAW_GRID_SELECTION.json')['grid'];cont=read(ROOT/'RAW_GRID_SELECTION.json')['continuation']
    train=fold_data('final','TRAIN');cal=fold_data('final','CAL');pre=prep('final')
    xc=matrix(cal,pre);xt=matrix(train,pre);rows=[];models={}
    folder=LOCAL/'final';folder.mkdir(exist_ok=True)
    for backend in ['cpu','gpu']:
        dest=ROOT/'FINAL_CPU_MODEL' if backend=='cpu' else folder/'GPU_MODEL'
        print(now(),'FINAL_TRAIN',backend,flush=True)
        if (dest/'model.json').exists():model=Hazard.load(dest)
        else:model=fit(train,pre,grid,'final',backend);model.save(dest)
        pc=model.parameters(xc,threads=4);q=maps_quantiles(model,pc,ProbabilityMap(),cont)
        models[backend]=(pc,q)
        rows.append(dict(backend=backend,threads=4,training_seconds=model.meta['training_seconds'],TRAIN_N=len(train),person_period_N=model.meta['person_period_N']))
        if backend=='cpu':
            np.savez_compressed(folder/'CPU_CAL.npz',parameters=pc,quantiles=q)
            risks=model.train_risk(xt);bounds=np.unique(np.quantile(risks,[1/3,2/3])).tolist();groups=np.digitize(risks,bounds,right=True)
            support=[dict(group=int(g),N=int(np.sum(groups==g)),events=int(np.sum(train.event&(groups==g))),long_gt4h=int(np.sum(train.event&train.duration_lower.gt(14400)&(groups==g))),long_gt12h=int(np.sum(train.event&train.duration_lower.gt(43200)&(groups==g)))) for g in np.unique(groups)]
            if not (ROOT/'FINAL_RISK_BOUNDARIES.json').exists():write('FINAL_RISK_BOUNDARIES.json',dict(time=now(),TRAIN_only=True,bounds=bounds,support=support))
        del model;gc.collect()
    a=models['cpu'][1];b=models['gpu'][1];absolute=float(np.max(abs(a-b)));relative=float(np.max(abs(a-b)/np.maximum(abs(a),1e-12)))
    tol=read(ROOT/'EXPERIMENT_PROTOCOL.json')['backend_tolerance'];equal=absolute<=tol['max_absolute_quantile_seconds'] and relative<=tol['max_relative_quantile_error']
    for r in rows:r.update(max_absolute_quantile_difference_seconds=absolute,max_relative_quantile_difference=relative,equivalent_within_preregistered_tolerance=equal,selected_consistently='CPU4')
    pd.DataFrame(rows).to_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv',index=False)
    write('BACKEND_BENCHMARK_RECEIPT.json',dict(time=now(),April_read=False,selected_backend='CPU4 before benchmark',tolerance=tol,equivalent=equal,max_absolute_difference_seconds=absolute,max_relative_difference=relative,device_identity_evidence='benchmark10.log: actual LightGBM GPU trainer device line'))
    print(now(),'BENCHMARK_DONE',absolute,relative,equal,flush=True)
if __name__=='__main__':main()

