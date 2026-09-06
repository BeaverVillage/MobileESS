"""Frozen S5 estimators instantiated against each issue's mature history."""
import gzip
import time
from lightgbm import LGBMRegressor,Booster
from .common import *

def load_model(path):return Booster(model_str=gzip.decompress(Path(path).read_bytes()).decode('utf-8'))

def fit_one(f,pre,y,config_id,alpha,path,records):
    assert f.end_time.lt(pre.cutoff).all() and len(f)==len(y)
    args={**FIXED,**CONFIGS[config_id],'objective':'regression' if alpha is None else 'quantile'}
    if alpha is not None:args['alpha']=alpha
    start=time.perf_counter()
    model=LGBMRegressor(**args).fit(pre.transform(f),np.asarray(y,float)).booster_
    fit_seconds=time.perf_counter()-start
    text=model.model_to_string().encode('utf-8')
    path.write_bytes(gzip.compress(text,compresslevel=6,mtime=0))
    records.append(dict(name=path.name,config_id=config_id,alpha=alpha,N=len(f),fit_ids_sha256=ids(f.job_uid),
      max_training_end=f.end_time.max(),preprocessing_fit_ids=pre.fit_ids_sha256,
      model_text_SHA256=sha(text),compressed_SHA256=file_sha(path),num_trees=model.num_trees(),fit_seconds=fit_seconds,seconds=time.perf_counter()-start))
    return model

def build(hist,t,track,directory):
    directory=Path(directory);assert not directory.exists(),'NO_UNREGISTERED_REBUILD'
    directory.mkdir(parents=True)
    started=now();clock=time.perf_counter();records=[]
    config_id,_=model_config();pre=Preprocess(track,t).fit(hist);dump(directory/'preprocessing.json',pre.descriptor())
    for a in QUANTILES:fit_one(hist,pre,hist.runtime_seconds,config_id,a,directory/f'Q{int(a*100)}.txt.gz',records)
    oofparts=[];fold_reports=[]
    oof_id=s5('PREREGISTRATION')['residual']['OOF_Q50_config']
    for k,train,valid in folds(hist,t):
        assert not set(train.job_uid)&set(valid.job_uid)
        fp=Preprocess(track,valid.end_time.min()).fit(train)
        model=fit_one(train,fp,train.runtime_seconds,oof_id,.5,directory/f'OOF{k}_Q50.txt.gz',records)
        prediction=np.maximum(model.predict(fp.transform(valid),num_threads=1),0.)
        v=valid[['job_uid','end_time','runtime_seconds']].copy();v['Q50_OOF']=prediction
        v['residual']=v.runtime_seconds-prediction;v['r2']=v.residual**2;v['fold']=k
        v['fit_max_end']=train.end_time.max();v['fit_ids_sha256']=ids(train.job_uid)
        oofparts.append(v)
        fold_reports.append(dict(fold=k,fit_N=len(train),validation_N=len(valid),fit_ids=ids(train.job_uid),validation_ids=ids(valid.job_uid),
          max_fit_end=train.end_time.max(),min_validation_end=valid.end_time.min(),overlap=0,preprocessing=fp.descriptor(),
          OOF_config=oof_id,constant_model=model.num_trees()==1))
    oof=pd.concat(oofparts).sort_values(['end_time','job_uid']).reset_index(drop=True)
    assert not oof.job_uid.duplicated().any() and (oof.fit_max_end<oof.end_time).all()
    residual_rows=hist.set_index('job_uid').loc[oof.job_uid].reset_index()
    fit_one(residual_rows,pre,oof.r2,config_id,None,directory/'RESIDUAL.txt.gz',records)
    oof.to_parquet(directory/'residual_OOF.parquet',index=False)
    deployment_files=['preprocessing.json','Q50.txt.gz','Q90.txt.gz','Q95.txt.gz','Q99.txt.gz','RESIDUAL.txt.gz']
    file_hashes={p.name:file_sha(p) for p in sorted(directory.iterdir()) if p.is_file()}
    package_hash=sha(json.dumps({n:file_hashes[n] for n in deployment_files},sort_keys=True).encode())
    gain={}
    for name in ['Q50','Q90','Q95','Q99','RESIDUAL']:
        m=load_model(directory/f'{name}.txt.gz');values=m.feature_importance(importance_type='gain')
        grouped={c:float(sum(v for v,g in zip(values,pre.groups) if g==c)) for c in fields(track)}
        total=sum(grouped.values())
        gain[name]=dict(grouped_gain=grouped,grouped_gain_fraction={c:v/total if total else 0. for c,v in grouped.items()})
    report=dict(issue_time=pd.Timestamp(t).isoformat(),track=track,started=started,finished=now(),N_train=len(hist),
      training_ids=ids(hist.job_uid),config_id=config_id,OOF_config_id=oof_id,seed=SEED,threads=1,
      preprocessing=pre.descriptor(),residual_folds=fold_reports,OOF_N=len(oof),warmup_N=len(hist)-len(oof),
      in_sample_residuals=0,residual_MAE=float(oof.residual.abs().mean()),r2_distribution=distribution(oof.r2),
      fit_records=records,files_SHA256=file_hashes,package_SHA256=package_hash,grouped_gain=gain,
      support_route=fold_count(len(hist)),seconds=time.perf_counter()-clock,cache_reuse=False)
    dump(directory/'package.json',report)
    return report

def predict(directory,features):
    directory=Path(directory);report=json.loads((directory/'package.json').read_text())
    for n,h in report['files_SHA256'].items():assert file_sha(directory/n)==h
    d=json.loads((directory/'preprocessing.json').read_text());pre=Preprocess(d['track'],d['cutoff']);pre.__dict__.update(d)
    pre.cutoff=pd.Timestamp(pre.cutoff)
    x=pre.transform(features)
    raw=np.column_stack([load_model(directory/f'Q{int(a*100)}.txt.gz').predict(x,num_threads=1) for a in QUANTILES])
    r2=load_model(directory/'RESIDUAL.txt.gz').predict(x,num_threads=1)
    sigma=np.sqrt(np.maximum(r2,0));q=repair(raw)
    assert np.isfinite(sigma).all()
    return raw,q,sigma,r2

def historical_permutation(hist,t,package,directory):
    """Predeclared periodic diagnostic only; no hyperparameter selection."""
    from dayahead.v40s5.common import temporal_split
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    train,valid,boundary=temporal_split(hist);pre=Preprocess('P',boundary).fit(train)
    oof=pd.read_parquet(Path(package)/'residual_OOF.parquet')
    otrain=oof[oof.end_time<boundary];ovalid=oof[oof.end_time>=boundary]
    config,_=model_config();records=[];reports={}
    for name,a in [(f'Q{int(a*100)}',a) for a in QUANTILES]+[('RESIDUAL',None)]:
        if a is not None:ft=train;y=train.runtime_seconds;fv=valid;target=valid.runtime_seconds.to_numpy()
        else:
            ft=hist.set_index('job_uid').loc[otrain.job_uid].reset_index();y=otrain.r2
            fv=hist.set_index('job_uid').loc[ovalid.job_uid].reset_index();target=ovalid.r2.to_numpy()
        m=fit_one(ft,pre,y,config,a,directory/f'{name}.txt.gz',records)
        def loss(p):return pinball(target,p,a) if a is not None else float(np.mean((target-p)**2))
        base=loss(m.predict(pre.transform(fv),num_threads=1));delta=[]
        for k in range(3):
            v=fv.copy();rng=np.random.default_rng(SEED+k)
            v['requested_seconds']=v.requested_seconds.to_numpy()[rng.permutation(len(v))]
            delta.append(loss(m.predict(pre.transform(v),num_threads=1))-base)
        reports[name]=dict(base_loss=base,walltime_mean_loss_increase=float(np.mean(delta)),replicates=delta,
          loss='raw pinball' if a is not None else 'MSE of historical OOF squared error',validation_N=len(fv),validation_ids=ids(fv.job_uid),
          max_train_end=ft.end_time.max(),min_validation_end=fv.end_time.min(),max_validation_end=fv.end_time.max(),
          validation_overlap=0,all_before_issue=bool(fv.end_time.lt(pd.Timestamp(t)).all()))
    result=dict(issue_time=pd.Timestamp(t),diagnostic_only=True,feature_selection=False,preprocessing=pre.descriptor(),reports=reports,fit_records=records)
    dump(directory/'diagnostic.json',result);return result
