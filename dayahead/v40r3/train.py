"""Preregistered stage runner. Each family owns separate logs and checkpoints."""
from .common import *
from .causal_snapshot import HISTORY,PAST_NAMES,FUTURE_NAMES
from .metrics import primary,gates
import argparse,time,importlib.metadata

TREE_NAMES=['LIGHTGBM','HURDLE_LIGHTGBM','XGBOOST']
DEEP_NAMES=['TFT','DEEPAR','NHITS','CMABF']
ALL_NAMES=['ZERO','SEASONAL']+TREE_NAMES+DEEP_NAMES

def authority():
    reg=read('V40R3_PREREGISTRATION.json');receipt=read('V40R3_PREREGISTRATION_COMMIT_RECEIPT.json')
    commit=receipt['preregistration_commit']
    assert reg['execution_authorized'] and git('merge-base','--is-ancestor',commit,'HEAD')==''
    raw=subprocess.check_output(['git','show',commit+':dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/V40R3_PREREGISTRATION.json'],cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest()==sha(OUT/'V40R3_PREREGISTRATION.json')
    for p,s in reg['frozen_source_and_data_SHA256'].items():assert sha(ROOT/p)==s,('REGISTERED_FILE_CHANGED',p)
    return reg,commit

def prepare():
    reg,commit=authority()
    a=np.load(OUT/'causal_dataset.npz');info=pd.read_parquet(OUT/'V40R3_LABEL_MATURITY_LEDGER.parquet')
    train=(info.role=='TRAIN')&info.stage_maturity_eligible
    assert (info.loc[train,'target_label_available_at']<=pd.Timestamp(reg['splits']['training_cutoff'])).all()
    past=a['past'].copy();future=a['future'].copy();y=a['target'].copy()
    scale=reg['burst']['training_positive_Q95_GPUh']
    count_scale=float(np.quantile(np.log1p(past[train,:,0]),.95));count_scale=max(count_scale,1.)
    past[:,:,0]=np.log1p(past[:,:,0])/count_scale
    past[:,:,1]=np.where(past[:,:,2]>0,past[:,:,1]/scale,0)
    past[:,:,3]=np.log1p(past[:,:,3])/np.log1p(24*28)
    for i in [7,9,11,13]:future[:,:,i]=np.where(future[:,:,i+1]>0,future[:,:,i]/scale,0)
    np.savez_compressed(OUT/'prepared_dataset.npz',past=past,future=future,target=y/scale,days=a['days'])
    dump('V40R3_NORMALIZATION.json',{'preregistration_commit':commit,'target_scale_GPUh':scale,'count_log1p_P95_train_scale':count_scale,
        'fit_rows':'mature TRAIN origins only','GPUh_immature_values_seen_by_scaler':0,'age_transform':'log1p(hours)/log1p(672)',
        'prepared_SHA256':sha(OUT/'prepared_dataset.npz')})

def load():
    reg,commit=authority()
    assert sha(OUT/'prepared_dataset.npz')==read('V40R3_NORMALIZATION.json')['prepared_SHA256']
    a=np.load(OUT/'prepared_dataset.npz');info=pd.read_parquet(OUT/'V40R3_LABEL_MATURITY_LEDGER.parquet')
    masks={r:((info.role==r)&info.stage_maturity_eligible).to_numpy() for r in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']}
    return reg,commit,a,info,masks

def monotone_nonnegative(pred):
    p=np.maximum(np.asarray(pred,float),0)
    crosses=int((p[...,0]>p[...,1]).sum())
    p[...,1]=np.maximum(p[...,1],p[...,0])
    return p,crosses

def save_result(name,pred,metadata):
    directory=OUT/'fits'/name;directory.mkdir(parents=True,exist_ok=True)
    raw=np.asarray(pred,float);cleaned,crosses=monotone_nonnegative(raw)
    np.save(directory/'raw_prediction.npy',raw)
    np.save(directory/'prediction.npy',cleaned)
    metadata.update(raw_quantile_crossings=crosses,prediction_SHA256=sha(directory/'prediction.npy'))
    (directory/'result.json').write_text(json.dumps(clean(metadata),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def baselines():
    reg,commit,a,info,m=load();scale=reg['burst']['training_positive_Q95_GPUh'];y=a['target']*scale
    zero=np.zeros((*y.shape,2))
    save_result('ZERO',zero,{'status':'COMPLETE','fits':0,'preregistration_commit':commit,'device':'cpu','definition':'Exactly zero'})
    f=a['future'];out=np.zeros_like(zero)
    for i in range(len(f)):
        for k in range(48):
            vals=[f[i,k,j]*scale for j in [7,9,11,13] if f[i,k,j+1]>0]
            out[i,k]=np.quantile(vals,[.5,.9]) if vals else 0
    save_result('SEASONAL',out,{'status':'COMPLETE','fits':0,'preregistration_commit':commit,'device':'cpu',
      'definition':'Same-slot empirical Q50/Q90 from exactly mature 7/14/21/28-day profiles; no eligible profile -> zero'})

def tree_features(a):
    return np.concatenate([np.repeat(a['past'].reshape(len(a['past']),-1),48,axis=0),a['future'].reshape(-1,len(FUTURE_NAMES))],axis=1)

def positive_mixture(p,grid,levels,tau):
    # Sort monotone envelope frozen before fit; lower endpoint is (0,0).
    grid=np.maximum.accumulate(np.maximum(grid,0),axis=1)
    u=np.divide(tau-(1-p),p,out=np.zeros_like(p),where=p>0)
    values=np.column_stack([np.zeros(len(p)),grid]);knots=np.r_[0.,levels]
    hi=np.clip(np.searchsorted(knots,np.clip(u,0,knots[-1]),side='right'),1,len(knots)-1);lo=hi-1
    rr=np.arange(len(p));t=(np.clip(u,0,knots[-1])-knots[lo])/(knots[hi]-knots[lo])
    q=values[rr,lo]+t*(values[rr,hi]-values[rr,lo])
    return np.where(tau<=1-p,0,q)

def fit_tree_once(name,lr,X,ys,train,levels):
    import lightgbm as lgb
    import xgboost as xgb
    kw=dict(n_estimators=400,learning_rate=lr,num_leaves=31,max_depth=6,min_child_samples=30,
        reg_lambda=1.,max_bin=127,random_state=SEED,n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True)
    heads=[]
    if name=='LIGHTGBM':
        for tau in [.5,.9]:
            heads.append(lgb.LGBMRegressor(objective='quantile',alpha=tau,**kw).fit(X[train],ys[train]))
        pred=np.column_stack([q.predict(X) for q in heads])
    elif name=='HURDLE_LIGHTGBM':
        occur=lgb.LGBMClassifier(objective='binary',**kw).fit(X[train],ys[train]>0)
        pos=train&(ys>0)
        for tau in levels:
            heads.append(lgb.LGBMRegressor(objective='quantile',alpha=float(tau),**kw).fit(X[pos],ys[pos]))
        p=occur.predict_proba(X)[:,1];grid=np.column_stack([q.predict(X) for q in heads])
        pred=np.column_stack([positive_mixture(p,grid,levels,tau) for tau in [.5,.9]])
        heads.insert(0,occur)
    else:
        mod=xgb.XGBRegressor(n_estimators=400,learning_rate=lr,max_depth=6,min_child_weight=10,reg_lambda=1.,max_bin=127,
            objective='reg:quantileerror',quantile_alpha=np.array([.5,.9]),tree_method='hist',device='cpu',n_jobs=4,random_state=SEED)
        mod.fit(X[train],ys[train]);heads=[mod];pred=mod.predict(X)
    return pred,heads

def trees():
    reg,commit,a,info,m=load();X=tree_features(a);ys=a['target'].ravel();scale=reg['burst']['training_positive_Q95_GPUh']
    train=np.repeat(m['TRAIN'],48);dev=m['DEVELOPMENT'];levels=np.asarray(reg['models']['HURDLE_LIGHTGBM']['positive_quantiles'])
    for name in TREE_NAMES:
        directory=OUT/'fits'/name;directory.mkdir(parents=True,exist_ok=True)
        if (directory/'result.json').exists():raise ValueError('FAMILY_ALREADY_COMPLETED:'+name)
        trial_records=[];best=float('inf');bestpred=None;bestmeta=None
        for trial,lr in enumerate(reg['tree_training']['learning_rates']):
            started=time.monotonic()
            dump(f'fits/{name}/trial_{trial}_start.json',{'preregistration_commit':commit,'seed':SEED,'device':'cpu','trial':trial,'lr':lr})
            pred,heads=fit_tree_once(name,lr,X,ys,train,levels)
            pred=pred.reshape(-1,48,2)*scale;post,_=monotone_nonnegative(pred)
            score=primary(a['target'][dev]*scale,post[dev,:,1])
            record={'trial':trial,'learning_rate':lr,'development_primary':score,'training_walltime_seconds':time.monotonic()-started,'seed':SEED,'device':'cpu'}
            trial_records.append(record)
            if score<best:
                best=score;bestpred=pred.copy();bestmeta=record.copy()
                for h,mod in enumerate(heads):
                    if name=='XGBOOST':mod.save_model(directory/f'selected_head{h}.ubj')
                    else:mod.booster_.save_model(str(directory/f'selected_head{h}.txt'))
            dump(f'fits/{name}/trial_{trial}_result.json',record)
            print(name,trial,'dev primary',round(score,6),'seconds',round(record['training_walltime_seconds'],1),flush=True)
        save_result(name,bestpred,{'status':'COMPLETE','preregistration_commit':commit,'trials':trial_records,'selected_trial':bestmeta,
           'seed':SEED,'device':'cpu','framework':importlib.metadata.version('xgboost' if name=='XGBOOST' else 'lightgbm')})

def tree_repeats():
    reg,commit,a,info,m=load();X=tree_features(a);ys=a['target'].ravel();train=np.repeat(m['TRAIN'],48)
    levels=np.asarray(reg['models']['HURDLE_LIGHTGBM']['positive_quantiles']);reports=[]
    for name in TREE_NAMES:
        first=read(f'fits/{name}/result.json');lr=first['selected_trial']['learning_rate'];started=time.monotonic()
        pred,_=fit_tree_once(name,lr,X,ys,train,levels)
        pred=pred.reshape(-1,48,2)*reg['burst']['training_positive_Q95_GPUh']
        original=np.load(OUT/'fits'/name/'raw_prediction.npy');diff=np.abs(pred-original)
        np.save(OUT/'fits'/name/'repeat_prediction.npy',pred)
        report={'name':name,'same_fixed_seed_independent_training_runs':2,'max_prediction_difference_GPUh':float(diff.max()),
           'mean_prediction_difference_GPUh':float(diff.mean()),'byte_identical_prediction_arrays':bool(np.array_equal(pred,original)),
           'repeat_walltime_seconds':time.monotonic()-started,'seed':SEED,'device':'cpu'}
        reports.append(report);print('Independent repeat',name,report['max_prediction_difference_GPUh'],flush=True)
    dump('V40R3_TREE_REPRODUCTION_REPORT.json',{'models':reports})

def fit_neural_once(name,lr,trial_id,a,info,m,reg,commit,reference_epochs=None):
    from .neural import seed_everything,build_model,neural_loss,predict_neural
    import torch
    seed_everything(SEED)
    # NHiTS interpolation may lack a bitwise deterministic CUDA backward kernel.
    # Explicit warnings plus independent repeat measurements replace any guarantee.
    torch.use_deterministic_algorithms(True,warn_only=True)
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    model=build_model(name).to(device)
    optimizer=torch.optim.Adam(model.parameters(),lr=lr,weight_decay=1e-4)
    p=torch.tensor(a['past'],device=device);f=torch.tensor(a['future'],device=device);y=torch.tensor(a['target'],device=device,dtype=torch.float32)
    train=np.flatnonzero(m['TRAIN']);dev=np.flatnonzero(m['DEVELOPMENT']);rng=np.random.default_rng(SEED)
    batch=reg['deep_training']['batch_size'];maximum=reg['deep_training']['epochs'];patience=reg['deep_training']['patience']
    best=float('inf');bestepoch=0;beststate=None;history=[];started=time.monotonic()
    directory=OUT/'fits'/name;directory.mkdir(parents=True,exist_ok=True)
    dump(f'fits/{name}/{trial_id}_start.json',{'preregistration_commit':commit,'seed':SEED,'device':device,'lr':lr,'max_epochs':maximum,'batch_size':batch})
    def predict(indices):
        model.eval();out=[]
        with torch.random.fork_rng(devices=[0] if device.startswith('cuda') else []):
            torch.manual_seed(SEED+1000)
            for k in range(0,len(indices),batch):
                ix=indices[k:k+batch]
                out.append(predict_neural(model,name,p[ix],f[ix],reg['deep_training']['forecast_samples']).cpu().numpy())
        return np.concatenate(out)
    for epoch in range(1,maximum+1):
        model.train();losses=[]
        order=rng.permutation(train)
        for k in range(0,len(order),batch):
            ix=order[k:k+batch];optimizer.zero_grad(set_to_none=True)
            loss=neural_loss(model,name,p[ix],f[ix],y[ix])
            if not torch.isfinite(loss):raise ValueError('NONFINITE_PREREGISTERED_TRAINING_LOSS')
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(float(loss.detach()))
        prediction,_=monotone_nonnegative(predict(dev))
        score=primary(a['target'][dev],prediction[...,1])
        history.append({'epoch':epoch,'train_loss':float(np.mean(losses)),'development_primary':score})
        if score<best-1e-6:
            best=score;bestepoch=epoch;beststate={key:value.detach().cpu().clone() for key,value in model.state_dict().items()}
        if epoch%5==0:print(name,trial_id,'epoch',epoch,'dev',round(score,5),'seconds',round(time.monotonic()-started),flush=True)
        if epoch-bestepoch>=patience:break
        if time.monotonic()-started>reg['deep_training']['max_trial_walltime_seconds']:break
    assert beststate is not None
    model.load_state_dict(beststate);pred=predict(np.arange(len(info)))*reg['burst']['training_positive_Q95_GPUh']
    torch.save(beststate,directory/f'{trial_id}_weights.pt')
    meta={'trial_id':trial_id,'learning_rate':lr,'seed':SEED,'device':device,'framework':torch.__version__,'CUDA':torch.version.cuda,
      'GPU_model':torch.cuda.get_device_name(0) if device.startswith('cuda') else None,'mixed_precision':False,'batch_size':batch,
      'epochs_run':len(history),'selected_epoch':bestepoch,'development_primary':best,'training_walltime_seconds':time.monotonic()-started,
      'deterministic_algorithms':True,'deterministic_warn_only':True,'cudnn_deterministic':True,'cudnn_benchmark':False,'TF32':False,
      'history':history,'early_stopping':'min development positive Q90 normalized pinball, min_delta=1e-6, patience=8',
      'weights_SHA256':sha(directory/f'{trial_id}_weights.pt')}
    dump(f'fits/{name}/{trial_id}_result.json',meta)
    del model,optimizer,p,f,y
    if torch.cuda.is_available():torch.cuda.empty_cache()
    return pred,meta

def deep():
    reg,commit,a,info,m=load()
    for name in DEEP_NAMES:
        directory=OUT/'fits'/name;directory.mkdir(parents=True,exist_ok=True)
        if (directory/'result.json').exists():raise ValueError('FAMILY_ALREADY_COMPLETED:'+name)
        trials=[];bestpred=None;selected=None
        for i,lr in enumerate(reg['deep_training']['learning_rates']):
            pred,meta=fit_neural_once(name,lr,f'trial_{i}',a,info,m,reg,commit);trials.append(meta)
            if selected is None or meta['development_primary']<selected['development_primary']:bestpred=pred;selected=meta
        save_result(name,bestpred,{'status':'COMPLETE','preregistration_commit':commit,'selected_trial':selected,'trials':trials})
        print(name,'search completed; selected',selected['trial_id'],flush=True)

def repeats_and_ablations():
    reg,commit,a,info,m=load();scale=reg['burst']['training_positive_Q95_GPUh'];reports=[]
    for name in DEEP_NAMES:
        first=read(f'fits/{name}/result.json');lr=first['selected_trial']['learning_rate']
        pred,meta=fit_neural_once(name,lr,'repeat_selected',a,info,m,reg,commit)
        original=np.load(OUT/'fits'/name/'raw_prediction.npy');diff=np.abs(pred-original)
        np.save(OUT/'fits'/name/'repeat_prediction.npy',pred)
        post,_=monotone_nonnegative(pred);base,_=monotone_nonnegative(original)
        reports.append({'name':name,'same_fixed_seed_independent_training_runs':2,'max_prediction_difference_GPUh':float(diff.max()),
           'mean_prediction_difference_GPUh':float(diff.mean()),'byte_identical_prediction_arrays':bool(np.array_equal(pred,original)),
           'development_metric_difference':primary(a['target'][m['DEVELOPMENT']]*scale,post[m['DEVELOPMENT'],:,1])-primary(a['target'][m['DEVELOPMENT']]*scale,base[m['DEVELOPMENT'],:,1])})
    lr=read('fits/CMABF/result.json')['selected_trial']['learning_rate']
    for name in ['CMABF_A0','CMABF_A1','CMABF_A2']:
        pred,meta=fit_neural_once(name,lr,'fixed_ablation',a,info,m,reg,commit)
        save_result(name,pred,{'status':'COMPLETE','preregistration_commit':commit,'selected_trial':meta,'secondary_only':True})
        repeat,repmeta=fit_neural_once(name,lr,'repeat_ablation',a,info,m,reg,commit);diff=np.abs(pred-repeat)
        np.save(OUT/'fits'/name/'repeat_prediction.npy',repeat)
        reports.append({'name':name,'same_fixed_seed_independent_training_runs':2,'max_prediction_difference_GPUh':float(diff.max()),
         'mean_prediction_difference_GPUh':float(diff.mean()),'byte_identical_prediction_arrays':bool(np.array_equal(pred,repeat)),
         'development_metric_difference':float(repmeta['development_primary']-meta['development_primary'])})
    dump('V40R3_DEEP_REPRODUCTION_REPORT.json',{'models':reports,'no_bitwise_determinism_assumed':True,'no_repeated_seed_selected_for_better_score':True})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','baselines','trees','deep','repeats','tree_repeats'])
    stage=parser.parse_args().stage
    {'prepare':prepare,'baselines':baselines,'trees':trees,'deep':deep,'repeats':repeats_and_ablations,'tree_repeats':tree_repeats}[stage]()

if __name__=='__main__':main()
