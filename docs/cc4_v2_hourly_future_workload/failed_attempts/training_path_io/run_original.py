"""Staged immutable training, calibration and historical evaluation."""
from common import *
import argparse
import platform
import sys
import time
import traceback
import lightgbm as lgb
from models_hourly import fit_predict, predict_saved, DEVICE
import torch


def read_data():
    z = np.load(ROOT/'DATA.npz')
    ledger = pd.read_csv(ROOT/'DAY_LEDGER.csv')
    return z, ledger


def indices(ledger, role):
    return np.flatnonzero(ledger.split.eq(role) & ledger.eligible)


def dev_score(y, raw, days, availability):
    calibrated, selected = [], []
    for j, day in enumerate(days):
        pool = np.flatnonzero(availability < issue(day).tz_convert('UTC'))
        pool = pool[pool < j]
        if len(pool) < 20:
            continue
        delta, _ = finite_residual(y[pool], raw[pool,:,1])
        calibrated.append(corrected(raw[j],delta))
        selected.append(j)
    require(len(selected)>0, 'no mature development score days')
    q = np.array(calibrated)
    result = metrics(y[selected], q[...,0], q[...,1])
    result.update(N_days=len(selected), dates=[str(days[j]) for j in selected])
    return result


def selection_key(score):
    in_band = .88 <= score['Q90_coverage'] <= .92
    return (not in_band, 0 if in_band else score['calibration_error'], score['Q90_pinball'], score['requirement_ratio'])


def tree_fit(z, tr, seed, folder):
    folder.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    for tau in [.5,.9]:
        m=lgb.LGBMRegressor(objective='quantile',alpha=tau,num_leaves=15,learning_rate=.03,n_estimators=400,
            min_child_samples=50,n_jobs=1,deterministic=True,force_col_wise=True,random_state=seed,verbosity=-1)
        m.fit(z['X'][tr].reshape(-1,71),np.log1p(z['y'][tr].ravel()))
        m.booster_.save_model(str(folder/f'Q{int(100*tau)}.txt'))
    receipt=dict(family='LGBM',seed=seed,training_seconds=time.perf_counter()-start,N_training_days=len(tr),
                 N_training_rows=len(tr)*24,device='cpu',cpu_threads=1,quantiles=[.5,.9],
                 training_dates=z['days'][tr].tolist(),model_hashes={p.name:sha(p) for p in folder.glob('*.txt')})
    dump(folder.relative_to(ROOT)/'receipt.json',receipt)
    return receipt


def predict(family, folder, z, ids, tr):
    if family=='SEASONAL':
        dow=np.array([pd.Timestamp(str(day)).weekday() for day in z['days']])
        q=[]
        for i in ids:
            pool=tr[dow[tr]==dow[i]]
            if len(pool)<8:
                pool=tr
            q.append(np.quantile(z['y'][pool],[.5,.9],axis=0).T)
        return np.array(q)
    if family=='LGBM':
        q=np.stack([np.expm1(lgb.Booster(model_file=str(folder/f'Q{tau}.txt')).predict(
            z['X'][ids].reshape(-1,71),num_threads=1)).reshape(len(ids),24) for tau in [50,90]],-1)
        require(np.isfinite(q).all() and (q>=0).all(),'invalid LGBM support')
        q[...,1]=np.maximum(q[...,0],q[...,1])
        return q
    return predict_saved(folder,z['past'],z['X'],ids)[0]


def train():
    require(not (ROOT/'MODEL_SELECTION_FREEZE.json').exists(), 'model selection already frozen')
    for name in ['POPULATION_COMPARISON','TARGET_RECONSTRUCTION_AUDIT','LEAKAGE_AUDIT','DATA_SPLITS_AND_MATURITY','RAW_PR57_BRIDGE']:
        require(json.loads((ROOT/f'{name}.json').read_text(encoding='utf-8'))['status']=='PASS',name)
    dump('PRETRAIN_CODE_FREEZE.json',dict(time=now(),files={p.name:sha(p) for p in ROOT.glob('*.py')},
         protocol_sha256=sha(ROOT/'EXPERIMENT_PROTOCOL.json')),exclusive=True)
    dump('ENVIRONMENT.json',dict(time=now(),python=sys.version,executable=sys.executable,platform=platform.platform(),
         torch=torch.__version__,lightgbm=lgb.__version__,numpy=np.__version__,pandas=pd.__version__,
         device=DEVICE,GPU=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
         cuda=torch.version.cuda,concurrent_GPU_jobs=1,CPU_threads=1,dataloader_workers=0))
    z, ledger=read_data();tr=indices(ledger,'TRAIN');dev=indices(ledger,'DEVELOPMENT')
    av=pd.to_datetime(ledger.label_matured_at,utc=True)
    require((av.iloc[tr]<issue(str(z['days'][dev[0]])).tz_convert('UTC')).all(),'TRAIN maturity')
    # Only TRAIN/DEVELOPMENT labels are even passed to neural fitting.
    fit_ids=np.r_[tr,dev]
    p=z['past'][fit_ids];x=z['X'][fit_ids];y=z['y'][fit_ids]
    ti=np.arange(len(tr));di=np.arange(len(tr),len(fit_ids))
    runs=[];scores=[];failures=[]
    for family,seeds in [('SEASONAL',[0]),('LGBM',SEEDS)]:
        for seed in seeds:
            tag=f'{family}_{seed}';folder=ROOT/'fits'/tag
            if family=='LGBM':
                tree_fit(z,tr,seed,folder)
            else:
                folder.mkdir(parents=True,exist_ok=False)
            q=predict(family,folder,z,dev,tr)
            np.save(folder/'development_prediction.npy',q)
            score=dev_score(z['y'][dev],q,z['days'][dev],av.iloc[dev].reset_index(drop=True))
            scores.append(dict(family=family,seed=seed,tag=tag,**score))
            runs.append(dict(family=family,seed=seed,tag=tag))
    dump('BASELINE_VALIDATION.json',dict(status='PASS',time=now(),N_train=len(tr),N_dev=len(dev),
         predictions_finite=True,prediction_shape=[len(dev),24,2],prediction_upper_cap=None,
         raw_original_unit_metrics=[dict(family=r['family'],seed=r['seed'],**metrics(z['y'][dev],
             np.load(ROOT/'fits'/r['tag']/'development_prediction.npy')[...,0],
             np.load(ROOT/'fits'/r['tag']/'development_prediction.npy')[...,1])) for r in runs]))
    print('BASELINE PIPELINE PASS; sequential neural jobs begin',flush=True)
    for family in ['TFT','DEEPAR']:
        trials=[]
        for lr in [.001,.0003]:
            tag=f'{family}_{SEEDS[0]}_lr{lr}';folder=ROOT/'fits'/tag
            try:
                q,meta,_=fit_predict(family,p,x,y,ti,di,di,SEEDS[0],lr,folder)
                score=dev_score(z['y'][dev],q,z['days'][dev],av.iloc[dev].reset_index(drop=True))
                trials.append((selection_key(score),tag,lr,q,meta,score))
            except Exception:
                failures.append(dict(family=family,seed=SEEDS[0],lr=lr,traceback=traceback.format_exc()))
                dump('FAILURES.json',failures)
                if torch.cuda.is_available():torch.cuda.empty_cache()
        if not trials:
            continue
        _,tag,lr,q,meta,score=min(trials,key=lambda row:row[0])
        np.save(ROOT/'fits'/tag/'development_prediction.npy',q)
        runs.append(dict(family=family,seed=SEEDS[0],tag=tag,lr=lr,epoch=meta['selected_epoch']))
        scores.append(dict(family=family,seed=SEEDS[0],tag=tag,**score))
        dump(f'{family}_DEVELOPMENT_SEARCH.json',[dict(tag=t[1],lr=t[2],selected_epoch=t[4]['selected_epoch'],score=t[5]) for t in trials])
        for seed in SEEDS[1:]:
            tag=f'{family}_{seed}_lr{lr}';folder=ROOT/'fits'/tag
            try:
                q,meta,_=fit_predict(family,p,x,y,ti,di,di,seed,lr,folder)
                np.save(folder/'development_prediction.npy',q)
                score=dev_score(z['y'][dev],q,z['days'][dev],av.iloc[dev].reset_index(drop=True))
                runs.append(dict(family=family,seed=seed,tag=tag,lr=lr,epoch=meta['selected_epoch']))
                scores.append(dict(family=family,seed=seed,tag=tag,**score))
            except Exception:
                failures.append(dict(family=family,seed=seed,lr=lr,traceback=traceback.format_exc()))
                dump('FAILURES.json',failures)
                if torch.cuda.is_available():torch.cuda.empty_cache()
    dump('FAILURES.json',failures)
    numeric=['Q90_coverage','calibration_error','Q90_pinball','requirement_ratio']
    df=pd.DataFrame([{k:v for k,v in s.items() if k!='dates'} for s in scores])
    df.to_csv(ROOT/'DEVELOPMENT_METRICS.csv',index=False)
    agg=df.groupby('family')[numeric].mean().to_dict('index')
    candidates=[fam for fam in ['LGBM','TFT','DEEPAR'] if sum(r['family']==fam for r in runs)==3]
    chosen=min(candidates,key=lambda fam:selection_key(agg[fam]))
    dump('MODEL_SELECTION_FREEZE.json',dict(time=now(),selected_family=chosen,selection_split='DEVELOPMENT',
        family_scores=agg,runs=runs,failures=failures,TRAIN_dates=z['days'][tr].tolist(),
        development_scoring_dates=scores[0]['dates'],evaluation_results_accessed=False,
        code_freeze_sha256=sha(ROOT/'PRETRAIN_CODE_FREEZE.json'),protocol_sha256=sha(ROOT/'EXPERIMENT_PROTOCOL.json')),
        exclusive=True)
    print('MODEL FROZEN',chosen,flush=True)


def calibrate():
    require(not (ROOT/'CALIBRATION_FREEZE.json').exists(),'calibration already frozen')
    freeze=json.loads((ROOT/'MODEL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
    z,l=read_data();tr=indices(l,'TRAIN');ids=indices(l,'CALIBRATION')
    av=pd.to_datetime(l.label_matured_at,utc=True)
    first=issue('2024-12-01').tz_convert('UTC')
    require((av.iloc[ids]<first).all(),'calibration maturity')
    corrections={}
    for run in freeze['runs']:
        folder=ROOT/'fits'/run['tag']
        q=predict(run['family'],folder,z,ids,tr)
        delta,rank=finite_residual(z['y'][ids],q[...,1])
        np.save(folder/'calibration_prediction.npy',q)
        corrections[run['tag']]=dict(delta_GPUh=delta,rank=rank,N_days=len(ids),dates=z['days'][ids].tolist(),
            latest_label_maturity=av.iloc[ids].max(),first_evaluation_issue=first,
            residual_sha256=hashlib.sha256((z['y'][ids]-q[...,1]).tobytes()).hexdigest())
    dump('CALIBRATION_FREEZE.json',dict(time=now(),model_freeze_sha256=sha(ROOT/'MODEL_SELECTION_FREEZE.json'),
        method='per-hour signed additive finite-sample residual order statistic; only CALIBRATION',
        corrections=corrections,evaluation_labels_used=False,upper_cap=None),exclusive=True)
    print('CALIBRATION FROZEN',len(ids),'days',flush=True)


def evaluate(role):
    if role=='MAY_HISTORICAL':
        require((ROOT/'EXPOSED_EVALUATION_COMPLETE.json').exists(),'Dec-Feb must finish first')
    require(not (ROOT/f'{role}_COMPLETE.json').exists(),'evaluation immutable; version a new experiment')
    freeze=json.loads((ROOT/'MODEL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
    calibration=json.loads((ROOT/'CALIBRATION_FREEZE.json').read_text(encoding='utf-8'))
    code=json.loads((ROOT/'PRETRAIN_CODE_FREEZE.json').read_text(encoding='utf-8'))
    for name, expected in code['files'].items():
        require(sha(ROOT/name)==expected,'pretraining code freeze changed: '+name)
    z,l=read_data();tr=indices(l,'TRAIN');ids=indices(l,role);parts=[]
    for run in freeze['runs']:
        folder=ROOT/'fits'/run['tag'];start=time.perf_counter()
        raw=predict(run['family'],folder,z,ids,tr)
        q=corrected(raw,np.array(calibration['corrections'][run['tag']]['delta_GPUh']))
        require(raw.shape==(len(ids),24,2) and np.isfinite(q).all(),'evaluation shape/finite')
        parts.append(pd.DataFrame(dict(target_day=np.repeat(z['days'][ids],24),target_hour=np.tile(np.arange(24),len(ids)),
            issue_time=np.repeat([issue(str(day)).isoformat() for day in z['days'][ids]],24),lead_hours=np.tile(np.arange(6,30),len(ids)),
            actual_GPUh=z['y'][ids].ravel(),Q50=q[...,0].ravel(),Q90=q[...,1].ravel(),
            raw_Q50=raw[...,0].ravel(),raw_Q90=raw[...,1].ravel(),model=run['family'],seed=run['seed'],split=role,tag=run['tag'])))
        dump(folder.relative_to(ROOT)/f'{role}_INFERENCE.json',dict(seconds=time.perf_counter()-start,days=len(ids),upper_cap=None))
    frame=pd.concat(parts,ignore_index=True)
    frame.to_parquet(ROOT/f'{role}_PREDICTIONS.parquet',index=False)
    dump(f'{role}_COMPLETE.json',dict(time=now(),N_days=len(ids),N_rows=len(frame),
        prediction_sha256=sha(ROOT/f'{role}_PREDICTIONS.parquet'),calibration_sha256=sha(ROOT/'CALIBRATION_FREEZE.json'),
        MODEL_RESELECTED=False,OPTIMIZER_CHANGED=False,GRID_CAMPAIGN_EXECUTIONS=0,PRODUCTION_MODEL_PROMOTED=False),exclusive=True)
    print(role,'COMPLETE',len(frame),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['train','calibrate','dec-feb','may'])
    phase=parser.parse_args().phase
    if phase=='train':train()
    elif phase=='calibrate':calibrate()
    else:evaluate('EXPOSED_EVALUATION' if phase=='dec-feb' else 'MAY_HISTORICAL')
