from common8 import *
from features8 import engineer,groups
from model8 import Predictor,ordered
from metrics8 import stats,compare,gate
import numpy as np,pandas as pd,lightgbm as lgb,time

def fit_model(name,kind,columns,tr,x,params,cats):
    y=tr.runtime_seconds.to_numpy(float);boosts={};receipts=[];start=time.perf_counter()
    def fit(key,target,tau,mask=None,binary=False):
        ix=np.ones(len(y),dtype=bool) if mask is None else mask
        cfg=dict(params);cfg.update(objective='binary' if binary else 'quantile')
        if not binary:cfg['alpha']=tau
        cls=lgb.LGBMClassifier if binary else lgb.LGBMRegressor;m=cls(**cfg);t=time.perf_counter()
        m.fit(x.loc[ix,columns],target[ix],categorical_feature=[c for c in cats if c in columns]);boosts[key]=m.booster_
        receipts.append(dict(key=key,N=int(ix.sum()),seconds=time.perf_counter()-t,trees=m.booster_.num_trees(),features=len(columns),objective=cfg['objective'],alpha=None if binary else tau))
    if kind in ['M1','M2','M3']:
        target=y if kind=='M1' else np.log1p(y) if kind=='M2' else np.log((y+1)/(tr.requested_seconds.to_numpy()+1))
        for tau in [.5,.9]:fit('Q'+str(int(tau*100)),target,tau)
    elif kind=='M4':
        long=y>14400;fit('LONG_PROB',long.astype(float),None,binary=True)
        for pref,mask in [('S',~long),('L',long)]:
            for i,q in enumerate([.05,.25,.5,.75,.9,.99]):fit(pref+str(i),np.log1p(y),q,mask)
    meta=dict(name=name,kind=kind,columns=columns,categorical_features=[c for c in cats if c in columns],long_upper=float(y.max()),params=params,fit_seconds=time.perf_counter()-start,fits=receipts)
    return Predictor(meta,boosts)

def main():
    assert read(ROOT/'RUNTIME_TARGET_AUTHORITY_AUDIT.json')['TARGET_RUNTIME_AUTHORITY_PASS']
    assert read(ROOT/'BASELINE_REPRODUCTION.json')['PASS'];assert not (ROOT/'MODEL_SELECTION_FREEZE.json').exists()
    f=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet');data=roles(f);pp=read(ROOT/'PREPROCESSING.json');maps=pp['categorical_mappings'];sets=pp['feature_sets'];params=read(ROOT/'EXPERIMENT_PROTOCOL.json')['lgbm']
    # Pass only raw feature columns to engineer, never labels/time/job IDs.
    inputcols=['num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib','requested_seconds','array_index']+list(maps)
    xs={role:engineer(g[inputcols].to_dict('records'),maps) for role,g in data.items()}
    baseline=pd.read_parquet(ROOT/'PREAPRIL_BASELINES.parquet');models={};pred={r:{} for r in ['DEV','CAL_FIT','CAL_VALID']};allfits=[];permutation=[];exclusions=[]
    def run(name,kind,cols):
        model=fit_model(name,kind,cols,data['TRAIN'],xs['TRAIN'],params,maps);models[name]=model;model.save(ROOT/'DEVELOPMENT_MODELS'/name)
        allfits.append(model.meta)
        for role in pred:pred[role][name]=model.predict(xs[role])
        print('FIT',name,'seconds',round(model.meta['fit_seconds'],2),'DEV',stats(data['DEV'],pred['DEV'][name])['Q90_pinball'],flush=True)
    for kind in ['M1','M2','M3']:
        for family in ['F0','F1','F2']:
            if kind=='M3' and family=='F0':continue
            run(kind+'_'+family,kind,sets[family])
    for family in ['F1','F2']:run('M4_'+family,'M4',sets[family])
    best=min([k for k in models if k.endswith('F2') and k.startswith(('M1','M2','M3'))],key=lambda k:stats(data['DEV'],pred['DEV'][k])['Q90_pinball'])
    dev=data['DEV'];order=np.argsort(dev.submit_time.to_numpy(),kind='stable');halves=[order[:len(order)//2],order[len(order)//2:]];retained=[]
    for group,cols in groups(models[best].meta['columns']).items():
        positives=[]
        for half,ix in enumerate(halves):
            shuffled=xs['DEV'].iloc[ix].copy();rng=np.random.default_rng(800928+half);perm=rng.permutation(len(ix));shuffled.loc[:,cols]=shuffled[cols].iloc[perm].to_numpy()
            changed=models[best].predict(shuffled);delta=stats(dev.iloc[ix],changed)['Q90_pinball']-stats(dev.iloc[ix],pred['DEV'][best][ix])['Q90_pinball']
            permutation.append(dict(reference=best,group=group,half=half,N=len(ix),pinball_increase=delta));positives.append(delta>1e-8)
        if all(positives) or group=='walltime' and models[best].meta['kind']=='M3':retained+=cols
    original=models[best].meta['columns'];retained=[c for c in original if c in retained]
    if retained and len(retained)<len(original):run(models[best].meta['kind']+'_F3',models[best].meta['kind'],retained)
    else:exclusions.append(dict(candidate='F3',reason='No useful reduction satisfying positive importance on both chronological DEV halves'))
    # Independent drop-family ablations use a common M2/F2 reference; if another model
    # is selected later, the report also identifies the reference rather than implying identity.
    for group in ['walltime','resource_shape','scheduler','identity']:
        drop=groups(sets['F2']).get(group,[])
        if drop:run('M2_F2_MINUS_'+group,'M2',[c for c in sets['F2'] if c not in drop])
    core=[k for k in models if '_MINUS_' not in k];rank=sorted(core,key=lambda k:stats(dev,pred['DEV'][k])['Q90_pinball']);left=rank[0]
    right=next(k for k in rank[1:] if models[k].meta['kind']!=models[left].meta['kind'])
    y=dev.runtime_seconds.to_numpy();e1=y-pred['DEV'][left][:,1];e2=y-pred['DEV'][right][:,1];corr=float(np.corrcoef(e1,e2)[0,1]);l1=np.maximum(.9*e1,-.1*e1);l2=np.maximum(.9*e2,-.1*e2)
    if corr<.95 and (l1<l2).mean()>=.2 and (l2<l1).mean()>=.2:
        name='M5_EQUAL_TWO';m=Predictor(dict(name=name,kind='M5',columns=sorted(set(models[left].meta['columns']+models[right].meta['columns'])),members=[left,right],params={},fit_seconds=0),{},[models[left],models[right]]);models[name]=m;m.save(ROOT/'DEVELOPMENT_MODELS'/name)
        for role in pred:pred[role][name]=m.predict(xs[role])
        core.append(name)
    else:exclusions.append(dict(candidate='M5',reason='No preregistered complementarity',pair=[left,right],error_correlation=corr,each_win_fraction=[float((l1<l2).mean()),float((l2<l1).mean())]))
    rows=[];strat=[];calrows=[];scores=[];calibration={};decisions={}
    for role,g in data.items():
        if role=='TRAIN':continue
        base=g[['job_id']].merge(baseline,on='job_id',validate='one_to_one');b0=base[['B0_Q50','B0_Q90']].to_numpy();w=np.column_stack([g.requested_seconds]*2)
        pred[role].update(W0=w,B0=b0,Bconst=base[['Bconst_Q50','Bconst_Q90']].to_numpy())
    for name in models:
        cf=data['CAL_FIT'];res=cf.runtime_seconds.to_numpy()-pred['CAL_FIT'][name][:,1];rankq=min(len(res),int(np.ceil(.9*(len(res)+1))));delta=float(np.sort(res)[rankq-1]);calibration[name]=delta
        for mode in ['NONE','ADDITIVE']:
            z=pred['CAL_VALID'][name].copy()
            if mode=='ADDITIVE':z[:,1]+=delta;z=ordered(z)
            cg=gate(data['CAL_VALID'],z,pred['CAL_VALID']['B0']);dg=gate(dev,pred['DEV'][name],pred['DEV']['B0'])
            calrows.append(dict(model=name,mode=mode,CAL_FIT_N=len(res),signed_delta_seconds=0 if mode=='NONE' else delta,**stats(data['CAL_VALID'],z)))
            if name in core:
                score=(dg['failed_checks']+cg['failed_checks'],.5*(dg['metrics']['Q90_pinball']/stats(dev,pred['DEV']['B0'])['Q90_pinball']+cg['metrics']['Q90_pinball']/stats(data['CAL_VALID'],pred['CAL_VALID']['B0'])['Q90_pinball']),.5*(dg['metrics']['reservation_to_W0_ratio']+cg['metrics']['reservation_to_W0_ratio']),len(models[name].meta['columns']))
                scores.append((score,name,mode));decisions[name+'_'+mode]=dict(DEV_raw=dg,CAL_VALID=cg,score=score)
    score,selected,mode=min(scores);delta=calibration[selected] if mode=='ADDITIVE' else 0
    for role,g in data.items():
        if role=='TRAIN':continue
        z=pred[role][selected].copy();z[:,1]+=delta;pred[role]['SELECTED_CALIBRATED']=ordered(z)
        r,t=compare(g,pred[role],role);rows+=r;strat+=t
        # CAL_FIT-based calibration applied to earlier DEV is a retrospective diagnostic,
        # never the prospective DEV gate (which uses RAW only).
        arr=g[['job_id']].copy()
        for name,value in pred[role].items():arr[name+'_Q50']=value[:,0];arr[name+'_Q90']=value[:,1]
        arr.to_parquet(ROOT/f'{role}_PREDICTIONS.parquet',index=False)
    pd.DataFrame(rows).to_csv(ROOT/'MODEL_COMPARISON.csv',index=False);pd.DataFrame(strat).to_csv(ROOT/'STRATIFIED_RUNTIME_METRICS.csv',index=False)
    pd.DataFrame(strat).query("dimension=='long'").to_csv(ROOT/'LONG_JOB_METRICS.csv',index=False)
    pd.DataFrame(rows).to_csv(ROOT/'GPU_WEIGHTED_METRICS.csv',index=False);pd.DataFrame(calrows).to_csv(ROOT/'CALIBRATION_COMPARISON.csv',index=False)
    pd.DataFrame(rows)[~pd.DataFrame(rows).model.isin(['W0','B0','Bconst'])].to_csv(ROOT/'FEATURE_SET_ABLATION.csv',index=False)
    pd.DataFrame(permutation).to_csv(ROOT/'PREAPRIL_GROUP_IMPORTANCE.csv',index=False)
    write('TRAINING_RECEIPTS.json',dict(models=allfits,baseline_refit_count=0,total_runtime_only=True,TRAIN_membership=ids(data['TRAIN']),no_future_labels=True,exclusions=exclusions))
    write('PRELIMINARY_SELECTION.json',dict(selected=selected,calibration=mode,delta=delta,score=score,decisions=decisions,selection_time=now(),april_opened=False,
      provider_ready=False,selection_for_final_benchmark=True,DEV_calibrated_reporting='Retrospective diagnostic with later CAL_FIT parameters; gate uses raw DEV only',
      ablation_reference='M2_F2 drop groups. If final family differs, selected-family drop ablations must be added before freeze.'))
    print('PRELIMINARY_SELECTED',selected,mode,delta,'SCORE',score,flush=True)
if __name__=='__main__':main()
