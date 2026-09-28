from common8 import *
from features8 import engineer,groups
from model8 import Predictor
from train8 import fit_model
from metrics8 import stats,compare
import numpy as np,pandas as pd,time,traceback

def main():
    select=read(ROOT/'PRELIMINARY_SELECTION.json');name=select['selected'];model=Predictor.load(ROOT/'DEVELOPMENT_MODELS'/name)
    data=roles(pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet'));pp=read(ROOT/'PREPROCESSING.json');maps=pp['categorical_mappings']
    inputs=['num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib','requested_seconds','array_index']+list(maps)
    xs={r:engineer(g[inputs].to_dict('records'),maps) for r,g in data.items()}
    reference=model.predict(xs['DEV']);base=stats(data['DEV'],reference);bench=[];trained={};params=read(ROOT/'EXPERIMENT_PROTOCOL.json')['lgbm']
    for backend,threads,device in [('CPU_SINGLE',1,'cpu'),('CPU_4_THREADS',4,'cpu'),('RTX4060_OpenCL_GPU',4,'gpu')]:
        cfg=dict(params,n_jobs=threads,device_type=device)
        if device=='gpu':cfg.update(gpu_use_dp=True)
        start=time.perf_counter()
        try:
            if model.meta['kind']=='M5':
                members=[fit_model(name+'_'+backend+str(i),m.meta['kind'],m.meta['columns'],data['TRAIN'],xs['TRAIN'],cfg,maps) for i,m in enumerate(model.members)]
                fitted=Predictor(dict(model.meta),{},members)
            else:fitted=fit_model(name+'_'+backend,model.meta['kind'],model.meta['columns'],data['TRAIN'],xs['TRAIN'],cfg,maps)
            elapsed=time.perf_counter()-start;p=fitted.predict(xs['DEV']);s=stats(data['DEV'],p);diff=float(np.max(np.abs(p-reference)));rel=abs(s['Q90_pinball']/base['Q90_pinball']-1);cov=abs(s['Q90_coverage']-base['Q90_coverage'])
            eq=diff<=.1 and rel<=.001 and cov<=.001;fitted.save(LOCAL/'benchmark_models'/backend);trained[backend]=fitted
            bench.append(dict(backend=backend,status='MEASURED',fit_seconds=elapsed,max_absolute_prediction_difference_seconds=diff,relative_pinball_difference=rel,coverage_difference=cov,numerically_equivalent=eq,threads=threads,N=len(data['TRAIN']),error=''))
        except Exception as e:bench.append(dict(backend=backend,status='UNSUPPORTED_OR_FAILED',fit_seconds=time.perf_counter()-start,numerically_equivalent=False,threads=threads,N=len(data['TRAIN']),error=repr(e)))
        print('BENCH',bench[-1],flush=True)
    cpu=[r for r in bench if r['numerically_equivalent'] and r['backend'].startswith('CPU')];assert cpu
    best=min(cpu,key=lambda r:r['fit_seconds']);gpu=next(r for r in bench if r['backend'].startswith('RTX'))
    if gpu['numerically_equivalent'] and gpu['fit_seconds']*1.2<=best['fit_seconds']:best=gpu
    # CPU text model is identical to original within numerical tolerance; benchmark
    # refits are comparisons only. Original selected development bytes remain authority.
    pd.DataFrame(bench).to_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv',index=False)
    write('COMPUTE_BACKEND_SELECTION.json',dict(recommended=best['backend'],production_backend='CPU inference always',selected_development_training_backend='CPU_4_THREADS',
      selected_original_bytes_retained=True,reason='Benchmark equivalent refits do not replace selected predictor; future repeat fits can use measured recommendation.',measurements=bench))
    # Selected-family conditional ablations, whenever main search reference differs.
    rows=[];receipts=[]
    if model.meta['kind'] not in ['M2','M5'] or model.meta['columns']!=pp['feature_sets']['F2']:
        for group in ['walltime','resource_shape','scheduler','identity']:
            drop=groups(model.meta['columns']).get(group,[])
            if not drop:
                receipts.append(dict(group=group,status='ALREADY_ABSENT'));continue
            kind=model.meta['kind']
            if kind=='M5':receipts.append(dict(group=group,status='ENSEMBLE_MEMBERSHIP_FIXED; M2_F2 reference ablation available'));continue
            if kind=='M3' and group=='walltime':kind='M2'
            cols=[c for c in model.meta['columns'] if c not in drop]
            ab=fit_model('SELECTED_MINUS_'+group,kind,cols,data['TRAIN'],xs['TRAIN'],params,maps);ab.save(ROOT/'ABLATION_MODELS'/group)
            for role in ['DEV','CAL_VALID']:rows.append(dict(role=role,model='SELECTED_MINUS_'+group,reference=name,kind=kind,**stats(data[role],ab.predict(xs[role]))))
            receipts.append(dict(group=group,status='MEASURED',kind=kind,fit_seconds=ab.meta['fit_seconds']))
    pd.DataFrame(rows,columns=list(rows[0]) if rows else ['role','model','reference','status']).to_csv(ROOT/'SELECTED_FAMILY_ABLATION.csv',index=False)
    write('SELECTED_ABLATION_RECEIPT.json',dict(selected=name,diagnostic_only_no_reselection=True,reference_M2_F2_available=True,groups=receipts,
      M3_walltime_removal='M2 target required when walltime normalization removed; not claimed a pure single-column ablation'))
    print('BENCHMARK_COMPLETE',best['backend'],flush=True)
if __name__=='__main__':main()
