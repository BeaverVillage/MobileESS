"""Registered diagnostic fits and conditional predictive-error assessment."""
from .common import *
from lightgbm import LGBMRegressor
import lightgbm as lgb
from sklearn.metrics import mean_tweedie_deviance
from scipy.stats import wasserstein_distance
import time

PREREG='f0af75759bda4611734d44d4627bc84e0d76f164'

def registration():
    rel='dayahead/artifacts/v40p_lightgbm_forecast_forensic/V40P_BACKTEST_PREREGISTRATION.json'
    obj=json.loads((ROOT/rel).read_text(encoding='utf-8'))
    saved=json.loads(git('show',PREREG+':'+rel))
    assert obj==saved,'PREREG_CHANGED'
    assert subprocess.run(['git','merge-base','--is-ancestor',PREREG,'HEAD'],cwd=ROOT).returncode==0
    return obj

def metrics(y,p,track='A'):
    y,p=np.asarray(y,float),np.asarray(p,float)
    e=p-y;ae=np.abs(e);short=np.maximum(-e,0);over=np.maximum(e,0);den=y.sum()
    result={'N':len(y),'actual_sum':den,'predicted_sum':p.sum(),'MAE':ae.mean(),'RMSE':np.sqrt((e*e).mean()),'WAPE':ae.sum()/den if den>0 else None,'bias':e.mean(),'median_signed_error':np.median(e),'underprediction_rate':np.mean(e<0),'shortfall':short.sum(),'overreservation':over.sum(),'normalized_shortfall':short.sum()/den if den>0 else None,'normalized_overreservation':over.sum()/den if den>0 else None,'zero_actual_fraction':np.mean(y==0),'max_abs_error':ae.max(),'max_underprediction':short.max(),'relative_bias':e.sum()/den if den>0 else None}
    if track=='A':
        # Tweedie domain mu>0. Zeros are declared rather than silently epsilon-clipped.
        result['Tweedie_deviance_p1_7']=mean_tweedie_deviance(y,p,power=1.7) if np.all(p>0) else None
        result['Tweedie_domain']='VALID' if np.all(p>0) else 'UNDEFINED_PREDICTION_NOT_STRICTLY_POSITIVE'
        result['GPUh_shortfall']=short.sum();result['GPUh_overreservation']=over.sum()
    return clean(result)

def attach_baselines(frame,source,spec):
    f=frame.copy();ts=pd.DatetimeIndex(f.timestamp_utc)
    src=source.set_index('timestamp_utc');h=int(spec['horizon_steps']);track=spec['track']
    if track=='A':
        f['A0_ZERO']=0.
        f['A1_RECENT_RATE']=src[spec['source_metric']].rolling(h,min_periods=h).sum().reindex(ts).to_numpy()
        names=['A2_DAILY_SEASONAL','A3_WEEKLY_SEASONAL']
    else:
        f['B0_PERSISTENCE']=src[spec['source_metric']].reindex(ts).to_numpy()
        names=['B1_DAILY_SEASONAL','B2_WEEKLY_SEASONAL']
    local=ts.tz_convert('Australia/Melbourne').tz_localize(None)
    for days,name in zip([1,7],names):
        previous=(local-pd.Timedelta(days=days)).tz_localize('Australia/Melbourne',ambiguous='NaT',nonexistent='NaT').tz_convert('UTC')
        vals=src[spec['target']].reindex(previous).to_numpy()
        vals[np.asarray(previous.isna())]=np.nan
        f[name]=vals
    return f

def fit_clones(spec,data):
    data=data.loc[data.timestamp_utc>=pd.Timestamp(spec['original_training_start'])].copy()
    data[spec['feature_order']]=data[spec['feature_order']].astype(np.float32)
    frames=[];receipts=[]
    saved=json.loads((OUT/'clone_fit_progress.json').read_text()) if (OUT/'clone_fit_progress.json').exists() else []
    for fold in spec['folds']:
        start,end=pd.Timestamp(fold['evaluation_start']),pd.Timestamp(fold['evaluation_end_exclusive'])
        train=data.loc[data.timestamp_utc+pd.Timedelta(minutes=245)<start]
        test=data.loc[(data.timestamp_utc>=start)&(data.timestamp_utc+pd.Timedelta(minutes=245)<end)]
        for model in spec['models']:
            t0=time.monotonic();target=model['target'];source=model['source_metric']
            y=train[target].to_numpy(float);current=test[source].to_numpy(float)
            if model['method']=='persistence':p=current;sha=None;trees=0
            else:
                modelpath=OUT/'diagnostic_models'/fold['id']/f'{target}.txt'
                modelpath.parent.mkdir(parents=True,exist_ok=True)
                prior=[r for r in saved if r['fold']==fold['id'] and r['track']==model['track'] and r['horizon_minutes']==model['horizon_minutes']]
                if modelpath.exists() and prior:
                    assert digest(modelpath)==prior[0]['model_sha256']
                    assert prior[0]['params']==model['hyperparameters']
                    booster=lgb.Booster(model_str=modelpath.read_text())
                else:
                    est=LGBMRegressor(**model['hyperparameters'])
                    est.fit(train[spec['feature_order']],y if model['track']=='A' else y-train[source].to_numpy(float))
                    booster=est.booster_
                    modelpath.write_text(booster.model_to_string(),encoding='utf-8',newline='\n')
                raw=booster.predict(test[spec['feature_order']],num_threads=4)
                p=np.maximum(raw*model['scale'] if model['track']=='A' else current+raw,0)
                sha=digest(modelpath);trees=booster.num_trees()
            f=pd.DataFrame({'timestamp_utc':test.timestamp_utc,'track':model['track'],'horizon_minutes':model['horizon_minutes'],'target':target,'model':model['method'],'prediction':p,'actual':test[target],'phase':'DIAGNOSTIC_CLONE','fold':fold['id'],'training_end':train.timestamp_utc.max(),'q90_train':np.quantile(y,.9),'q95_train':np.quantile(y,.95),'q95_positive_train':np.quantile(y[y>0],.95) if np.any(y>0) else 0})
            frames.append(attach_baselines(f,data,model))
            receipt={'fold':fold['id'],'track':model['track'],'horizon_minutes':model['horizon_minutes'],'train_rows':len(train),'test_rows':len(test),'train_start':train.timestamp_utc.min(),'train_end':train.timestamp_utc.max(),'train_max_target_window_end':train.timestamp_utc.max()+pd.Timedelta(minutes=245),'test_start':test.timestamp_utc.min(),'test_end':test.timestamp_utc.max(),'chronology_pass':train.timestamp_utc.max()+pd.Timedelta(minutes=245)<test.timestamp_utc.min(),'model_sha256':sha,'trees':trees,'params':model['hyperparameters'],'elapsed_seconds':time.monotonic()-t0}
            receipts.append(receipt);dump('clone_fit_progress.json',receipts)
            print(f'{fold["id"]} {model["track"]} {model["horizon_minutes"]}m train={len(train)} test={len(test)} {time.monotonic()-t0:.1f}s',flush=True)
    registration()
    return pd.concat(frames,ignore_index=True),receipts

def block_bootstrap(g,base,seed=20260906,n=2000):
    y=g.actual.to_numpy();p=g.prediction.to_numpy();b=g[base].to_numpy()
    z=pd.DataFrame({'fold':g.fold.to_numpy(),'day':g.timestamp_utc.dt.floor('D').to_numpy(),'n':1,'y':y,'a':np.abs(p-y),'s':(p-y)**2,'bias':p-y,'short':np.maximum(y-p,0),'over':np.maximum(p-y,0),'ba':np.abs(b-y),'bs':(b-y)**2})
    daily=z.groupby(['fold','day']).sum(numeric_only=True)
    rng=np.random.default_rng(seed);reps=np.zeros((n,daily.shape[1]))
    for _,f in daily.groupby(level=0):
        a=f.to_numpy();indices=rng.integers(0,len(a),size=(n,len(a)))
        reps+=a[indices].sum(axis=1)
    r=pd.DataFrame(reps,columns=daily.columns)
    values={'MAE':r.a/r.n,'RMSE':np.sqrt(r.s/r.n),'WAPE':r.a/r.y.replace(0,np.nan),'bias':r.bias/r.n,'normalized_shortfall':r.short/r.y.replace(0,np.nan),'normalized_overreservation':r.over/r.y.replace(0,np.nan),'skill_MAE':1-r.a/r.ba.replace(0,np.nan),'skill_RMSE':1-np.sqrt(r.s/r.bs.replace(0,np.nan)),'skill_WAPE':1-r.a/r.ba.replace(0,np.nan)}
    est=metrics(y,p);bm=metrics(y,b)
    estimates={**est,'skill_MAE':1-est['MAE']/bm['MAE'] if bm['MAE'] else None,'skill_RMSE':1-est['RMSE']/bm['RMSE'] if bm['RMSE'] else None,'skill_WAPE':1-est['WAPE']/bm['WAPE'] if bm['WAPE'] else None}
    out=[]
    for name,v in values.items():
        valid=np.asarray(v.dropna())
        out.append({'metric':name,'estimate':estimates[name],'lower95':np.quantile(valid,.025) if len(valid) else None,'upper95':np.quantile(valid,.975) if len(valid) else None,'valid_replicates':len(valid)})
    return clean({'block':'UTC day, stratified by fold','days':len(daily),'replicates':n,'seed':seed,'results':out})

def bursts(g):
    y,p=g.actual.to_numpy(),g.prediction.to_numpy();out=[]
    for name,col in [('top10','q90_train'),('top5','q95_train'),('positive_top5_supplement','q95_positive_train')]:
        thresh=g[col].to_numpy();actual=y>thresh;pred=p>thresh;tp=np.sum(actual&pred)
        out.append({'subgroup':name,'thresholds_by_fold':{k:float(x[col].iloc[0]) for k,x in g.groupby('fold')},'strict_greater_tie_rule':True,'zero_threshold':bool(np.any(thresh==0)),'actual_burst_windows':int(actual.sum()),'predicted_burst_windows':int(pred.sum()),'true_positive':int(tp),'recall':float(tp/actual.sum()) if actual.any() else None,'precision':float(tp/pred.sum()) if pred.any() else None,'burst_MAE':float(np.abs(p[actual]-y[actual]).mean()) if actual.any() else None,'burst_bias':float((p[actual]-y[actual]).mean()) if actual.any() else None,'burst_shortfall':float(np.maximum(y[actual]-p[actual],0).sum()),'missed_windows':int(np.sum(actual&~pred))})
    return out

def streaks(g):
    g=g.sort_values(['fold','timestamp_utc']);u=(g.actual>g.prediction).to_numpy();ts=g.timestamp_utc.to_numpy();fold=g.fold.to_numpy()
    run=maxrun=0
    for i,on in enumerate(u):
        continuous=i>0 and fold[i]==fold[i-1] and (ts[i]-ts[i-1])==pd.Timedelta(minutes=5)
        run=(run+1 if continuous else 1) if on else 0;maxrun=max(maxrun,run)
    worst=g.assign(under=g.actual-g.prediction).nlargest(10,'under')[['timestamp_utc','fold','actual','prediction','under']]
    return {'underprediction_forecast_origins':int(u.sum()),'duration_minutes_on_origin_grid':int(u.sum()*5),'longest_consecutive_origin_streak':maxrun,'longest_streak_minutes':maxrun*5,'duration_warning':'overlapping forecast origins; not physical service duration or unique energy','worst_10_windows':clean(worst.to_dict('records'))}

def evaluate(allf,spec):
    rows=[];skills=[];boots=[];burst=[];under=[];consistency=[]
    for (phase,track,h),g in allf.groupby(['phase','track','horizon_minutes']):
        base='A0_ZERO' if track=='A' else 'B0_PERSISTENCE'
        common={'phase':phase,'track':track,'horizon_minutes':h,'unit':'GPU-hours' if track=='A' else 'average active GPUs','primary_baseline':base,'causal_validity':'FAIL_OR_UNPROVEN_ORIGINAL_FEATURES'}
        for fold,cohort in [('POOLED',g)]+list(g.groupby('fold')):
            for method in ['prediction']+([k for k in spec['baselines'] if k.startswith(track)]):
                valid=cohort.loc[cohort[method].notna()]
                if valid.empty:continue
                met=metrics(valid.actual,valid[method],track)
                bm=metrics(valid.actual,valid[base],track)
                met['skill_MAE']=1-met['MAE']/bm['MAE'] if bm['MAE'] else None
                met['skill_RMSE']=1-met['RMSE']/bm['RMSE'] if bm['RMSE'] else None
                met['skill_WAPE']=1-met['WAPE']/bm['WAPE'] if bm['WAPE'] else None
                rows.append({**common,'fold':fold,'method':method,'missing_baseline_rows':len(cohort)-len(valid),**met})
        boot=block_bootstrap(g,base,seed=spec['bootstrap']['seed'],n=spec['bootstrap']['replicates']);boots.append({**common,**boot})
        sk=next(r for r in boot['results'] if r['metric']=='skill_MAE')
        skills.append({**common,**sk,'positive_CI':sk['lower95'] is not None and sk['lower95']>0,'causal_superiority_claim_allowed':False})
        burst.append({**common,'subgroups':bursts(g)})
        under.append({**common,**streaks(g),**metrics(g.actual,g.prediction,track)})
        # Frozen monthly diagnostics were specified for temporal shift, not for selection.
    for phase,g in allf.loc[allf.track.eq('A')].groupby('phase'):
        p=g.pivot(index=['fold','timestamp_utc'],columns='horizon_minutes',values='prediction').dropna()
        y=g.pivot(index=['fold','timestamp_utc'],columns='horizon_minutes',values='actual').dropna()
        v=np.diff(p.to_numpy(),axis=1)<-1e-9;vy=np.diff(y.to_numpy(),axis=1)<-1e-9
        consistency.append({'phase':phase,'rows':len(p),'theoretical_requirement':'nested cumulative future arrival bins must be nondecreasing','predicted_adjacent_crossings':int(v.sum()),'prediction_rows_with_crossing':int(v.any(axis=1).sum()),'prediction_crossing_rate':float(v.any(axis=1).mean()),'actual_adjacent_crossings':int(vy.sum()),'outputs_repaired':False})
    met=pd.DataFrame(rows)
    for track,name in [('A','FUTURE_ARRIVAL'),('B','FIXED_LOAD')]:
        subset=met.loc[met.track.eq(track)];subset.to_csv(OUT/f'V40P_{name}_METRICS.csv',index=False)
        dump(f'V40P_{name}_METRICS.json',{'rows':subset.to_dict('records'),'sum_warning':'GPU-hour sums for A count overlapping forecast windows; never unique consumed energy. B shortfall is summed GPU-equivalent error, not GPU-hours.'})
    dump('V40P_BASELINE_SKILL_REPORT.json',{'primary_comparisons':skills,'all_comparator_metrics':'V40P_FUTURE_ARRIVAL_METRICS.csv and V40P_FIXED_LOAD_METRICS.csv','baseline_causality_notes':spec['baselines']})
    dump('V40P_BLOCK_BOOTSTRAP_REPORT.json',boots)
    dump('V40P_BURST_FORECAST_REPORT.json',burst)
    dump('V40P_UNDERPREDICTION_RISK_REPORT.json',under)
    dump('V40P_HORIZON_CONSISTENCY_REPORT.json',consistency)
    print(met.loc[met.fold.eq('POOLED')&met.method.eq('prediction'),['phase','track','horizon_minutes','N','MAE','WAPE','bias','normalized_shortfall','skill_MAE']].to_string(index=False))

def main():
    spec=registration()
    data=read_pre_may(K5A/'outputs/kestrel_ml_features_global_5min.parquet')
    dev=read_pre_may(K5A/'outputs/kestrel_ml_development_2024.parquet')
    frozen=pd.read_parquet(OUT/'frozen_predictions.parquet');frames=[]
    for model in spec['models']:
        f=frozen.loc[frozen.target.eq(model['target'])].copy();y=dev[model['target']].to_numpy()
        for col,q in [('q90_train',.9),('q95_train',.95)]:f[col]=np.quantile(y,q)
        f['q95_positive_train']=np.quantile(y[y>0],.95) if np.any(y>0) else 0
        frames.append(attach_baselines(f,data,model))
    clones,receipts=fit_clones(spec,data)
    allf=pd.concat(frames+[clones],ignore_index=True)
    allf['training_end']=pd.to_datetime(allf.training_end,utc=True,format='mixed')
    allf.to_parquet(OUT/'all_predictions.parquet',index=False)
    dump('V40P_ROLLING_BACKTEST_REPORT.json',{'preregistration_commit':PREREG,'no_production_retraining':True,'clone_count':sum(r['model_sha256'] is not None for r in receipts),'folds':spec['folds'],'fits':receipts,'all_chronology_pass':all(r['chronology_pass'] for r in receipts),'causality_caveat':spec['causality_caveat'],'true_frozen_holdout':False,'no_post_prereg_changes':True})
    evaluate(allf,spec)

if __name__=='__main__':main()
