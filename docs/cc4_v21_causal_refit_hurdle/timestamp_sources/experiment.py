"""CC4-v2.1: staged causal temporal, architecture and calibration comparison."""
from common import *
import argparse
import gzip
import time
import lightgbm as lgb

BASE=ROOT.parent/'cc4_v2_hourly_future_workload'
GRID=np.array([.01,.05,.10,.25,.50,.70,.80,.90,.95,.99])
POLICIES=['fixed','rolling90','rolling180','expanding','weighted']
PARAMS=dict(num_leaves=15,learning_rate=.03,n_estimators=400,min_child_samples=50,n_jobs=1,
            deterministic=True,force_col_wise=True,random_state=20260924,verbosity=-1)
Z=np.load(BASE/'DATA.npz')
L=pd.read_csv(BASE/'DAY_LEDGER.csv')
DAYS=Z['days'].astype(str)
AV=pd.to_datetime(L.label_matured_at,utc=True)
ISS=pd.to_datetime(L.issue_time,utc=True)
TRAIN=np.flatnonzero(L.split.eq('TRAIN')&L.eligible)
DEV=np.flatnonzero(L.split.eq('DEVELOPMENT')&L.eligible)
CAL=np.flatnonzero(L.split.eq('CALIBRATION')&L.eligible)
OOS=np.flatnonzero(DAYS>='2024-09-01')
BURST=json.loads((BASE/'TARGET_RECONSTRUCTION_AUDIT.json').read_text(encoding='utf-8'))['TRAIN_positive_Q95_burst_threshold_GPUh']


def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))


def register():
    require(not (ROOT/'PROTOCOL.json').exists(),'immutable registration exists')
    sources={p.name:sha(p) for p in [BASE/'DATA.npz',BASE/'DAY_LEDGER.csv',BASE/'FEATURE_MATURITY_PROOF.parquet',
        BASE/'TARGET_RECONSTRUCTION_AUDIT.json',BASE/'POPULATION_COMPARISON.json',BASE/'LEAKAGE_AUDIT.json',
        BASE/'MODEL_SELECTION_FREEZE.json',BASE/'CALIBRATION_FREEZE.json',BASE/'PREDICTIONS.parquet']}
    dump('SOURCE_MANIFEST.json',dict(base_commit='742d5b6b21badcf35eecc6931fda747ea9ec84a4',PR=63,
        parent_namespace=str(BASE),hashes=sources,target_population='unchanged PR63 raw-audited population'))
    dump('PROTOCOL.json',dict(registered_at=now(),version='CC4-v2.1-v1',target='PR63 unchanged hourly arrival GPUh',
        temporal_policies=POLICIES,cadences_days=[1,7,28],weighted_half_life_days=30,
        temporal_selection='DEVELOPMENT raw Q90 pinball, tie calibration error then requirement ratio; fixed is reference, best causal refit advances to Stage B',
        architecture=['LGBM','HURDLE','BURST_EXPERT','TFT','DEEPAR'],positive_quantile_grid=GRID,
        hurdle='q=0 when tau<=1-p_positive; otherwise interpolate Qpositive((tau-1+p_positive)/p_positive)',
        burst_expert='causal classifier P(W>TRAIN-positive-Q95 | W>0); mixture of body/tail conditional quantile CDFs, then unconditional zero-mass inversion',
        minimum_expert_rows=100,sparse_expert='back off to pooled positive quantile model; no exclusions',
        neural=dict(source='PR63 compact TFT/DeepAR',seeds=SEEDS,lr=.001,TFT_epochs=8,DEEPAR_epochs=18,
                    epochs_source='PR63 selected-epoch median; no new architecture/epoch search',concurrent_GPU_jobs=1),
        model_selection='DEVELOPMENT raw Q90 pinball; research candidate only until all success gates evaluated',
        calibration_windows_days=[28,56,'expanding'],calibration='per-hour signed original-unit residual finite-sample rank ceil(.9*(n_days+1)); min20 mature days; no scale/cap',
        calibration_selection='DEVELOPMENT warmup-eligible and CALIBRATION equally weighted: band 88..92 first, then pinball; freeze before exposed predictions',
        residual_sources='chronological OOS predictions at historical issues; only full-day matured labels strictly before current issue',
        evaluation_update='prequential: earlier evaluation labels enter only after maturity, with all rules fixed; not used for tuning',
        history='all available days since 2024-03-15; omit historical PURGE dates; formerly immature days may enter only after maturity',
        May_history='include mature Mar-Apr and earlier mature May days under fixed policy; no May selection or tuning',
        units='split and statistical unit: target day',bootstrap=dict(draws=2000,block_days=7,paired=True,seed=20260926),
        gates=dict(overall=[.88,.92],positive_min=.85,burst_min=.70,requirement_max_exclusive=2.,requirement_target=1.8,
                   preferred_pinball_improvement=.05,robust='paired 95% upper delta <0 in both Dec-Feb and May'),
        parameters=PARAMS,NO_UNTOUCHED_CONFIRMATION=True,OPTIMIZER_CHANGED=False,GRID_CAMPAIGN_EXECUTIONS=0,PRODUCTION_MODEL_PROMOTED=False),exclusive=True)
    proof=pd.read_parquet(BASE/'FEATURE_MATURITY_PROOF.parquet')
    require((pd.to_datetime(proof.feature_available_at,utc=True)<=pd.to_datetime(proof.issue_time,utc=True)).all(),'inherited feature leak')
    dump('LEAKAGE_AUDIT.json',dict(status='PASS',feature_count=71,dates=DAYS.tolist(),N_days=len(DAYS),
        feature_hour_checks=len(proof)*24,proof_sha256=sha(BASE/'FEATURE_MATURITY_PROOF.parquet'),
        inherited_source_verified=True,refit_rule='label_matured_at < refit_issue <= forecast_issue',
        evaluation_tuning=False,request_snapshot_limit='event-time causal reconstruction; actual ingestion latency not certified'))
    for role in ROLES:
        f=L[L.split.eq(role)&L.eligible]
        f.to_csv(ROOT/f'{role}_MEMBERSHIP.csv',index=False)
    dump('CODE_FREEZE.json',dict(time=now(),files={p.name:sha(p) for p in ROOT.glob('*.py')},protocol_sha256=sha(ROOT/'PROTOCOL.json')),exclusive=True)


def membership(policy,cut):
    if policy=='fixed':return TRAIN
    mask=(AV<cut)&(ISS<cut)&~L.split.eq('PURGE')
    if policy.startswith('rolling'):
        mask &= pd.to_datetime(DAYS).to_numpy()>=np.datetime64((cut.tz_convert(TZ).tz_localize(None)-pd.Timedelta(days=int(policy[7:]))).normalize())
    ids=np.flatnonzero(mask)
    require(len(ids)>=20 and (AV.iloc[ids]<cut).all(),'refit support/maturity')
    return ids


def weights(policy,ids,cut):
    age=(cut-pd.to_datetime(DAYS[ids],utc=True)).total_seconds()/86400
    return np.exp2(-np.maximum(age,0)/30) if policy=='weighted' else np.ones(len(ids))


def train_tree(X,y,w,kind='quantile',tau=.9):
    if kind=='binary' and len(np.unique(y))==1:return float(y[0])
    model=(lgb.LGBMClassifier(objective='binary',**PARAMS) if kind=='binary'
           else lgb.LGBMRegressor(objective='quantile',alpha=tau,**PARAMS))
    model.fit(X,y,sample_weight=w)
    return model.booster_


def predict_tree(m,X):return np.full(len(X),m) if isinstance(m,float) else m.predict(X,num_threads=1)


def save_tree(m,p):
    content=json.dumps({'constant':m}) if isinstance(m,float) else m.model_to_string()
    with gzip.GzipFile(filename=str(p),mode='wb',mtime=0) as f:f.write(content.encode())


def load_tree(p):
    content=gzip.decompress(p.read_bytes()).decode()
    return float(json.loads(content)['constant']) if content.startswith('{') else lgb.Booster(model_str=content)


def positive_quantiles(folder,prefix,X,y,w,Xp):
    out=[]
    for q in GRID:
        path=folder/f'{prefix}_{q}.txt.gz'
        if path.exists():m=load_tree(path)
        else:
            m=train_tree(X,np.log1p(y),w,tau=float(q));save_tree(m,path)
        out.append(np.maximum(0,np.expm1(predict_tree(m,Xp))))
    return np.maximum.accumulate(np.stack(out,-1),axis=-1)


def inverse_positive(values,u):
    return np.array([np.interp(t,np.r_[0,GRID],np.r_[0,v]) for v,t in zip(values,u)])


def unconditional(p,values):
    out=[]
    for tau in [.5,.9]:
        u=np.divide(tau-1+p,p,out=np.zeros_like(p),where=p>0)
        out.append(np.where(tau<=1-p,0,inverse_positive(values,np.maximum(u,0))))
    return np.stack(out,-1)


def mixture_quantile(p,pburst,body,tail):
    out=np.zeros((len(p),2))
    for i in range(len(p)):
        support=np.unique(np.r_[0,body[i],tail[i]])
        cb=np.interp(support,np.r_[0,body[i]],np.r_[0,GRID],right=1)
        ct=np.interp(support,np.r_[0,tail[i]],np.r_[0,GRID],right=1)
        cdf=(1-pburst[i])*cb+pburst[i]*ct
        for k,tau in enumerate([.5,.9]):
            if tau>1-p[i]:out[i,k]=np.interp((tau-1+p[i])/p[i],cdf,support)
    return out


def tree_model(family,policy,cut,tr,ids,folder):
    X=Z['X'][tr].reshape(-1,71);y=Z['y'][tr].ravel();w=np.repeat(weights(policy,tr,cut),24)
    Xp=Z['X'][ids].reshape(-1,71)
    if family=='LGBM':
        qs=[]
        for tau in [.5,.9]:
            path=folder/f'Q{int(100*tau)}.txt.gz'
            if policy=='fixed':
                m=lgb.Booster(model_str=(BASE/f'fits/LGBM_20260924/Q{int(100*tau)}.txt').read_text(encoding='utf-8'))
            elif path.exists():m=load_tree(path)
            else:m=train_tree(X,np.log1p(y),w,tau=tau);save_tree(m,path)
            qs.append(np.maximum(0,np.expm1(predict_tree(m,Xp))))
        q=np.stack(qs,-1)
    else:
        pos=y>0;path=folder/'occurrence.txt.gz'
        if path.exists():gate=load_tree(path)
        else:gate=train_tree(X,pos.astype(int),w,'binary');save_tree(gate,path)
        pp=predict_tree(gate,Xp)
        pooled=positive_quantiles(folder,'positive',X[pos],y[pos],w[pos],Xp)
        if family=='HURDLE':q=unconditional(pp,pooled)
        else:
            tail=y>BURST;path=folder/'burst_gate.txt.gz'
            if path.exists():gate=load_tree(path)
            else:gate=train_tree(X[pos],tail[pos].astype(int),w[pos],'binary');save_tree(gate,path)
            pb=predict_tree(gate,Xp)
            bodymask=pos&~tail
            body=positive_quantiles(folder,'body',X[bodymask],y[bodymask],w[bodymask],Xp) if bodymask.sum()>=100 else pooled
            tailq=positive_quantiles(folder,'tail',X[tail],y[tail],w[tail],Xp) if tail.sum()>=100 else pooled
            q=mixture_quantile(pp,pb,body,tailq)
            dump(folder.relative_to(ROOT)/'EXPERT_SUPPORT.json',dict(body_rows=int(bodymask.sum()),tail_rows=int(tail.sum()),fallback_below=100))
    q[:,1]=np.maximum(q[:,0],q[:,1]);require(np.isfinite(q).all(),'nonfinite uncapped forecast')
    return q.reshape(len(ids),24,2)


def _forecast(family,policy,cadence,through,seed=20260924):
    tag=f'{family}_{policy}_c{cadence}_s{seed}'
    path=ROOT/'predictions'/f'{tag}.npz'
    out=np.full((len(DAYS),24,2),np.nan)
    if path.exists():out=np.load(path)['q']
    allids=OOS[DAYS[OOS]<=through]
    daynum=(pd.to_datetime(DAYS)-pd.Timestamp('2024-09-01')).days.to_numpy()
    buckets=daynum//cadence if policy!='fixed' else np.zeros(len(DAYS),int)
    for bucket in np.unique(buckets[allids]):
        ids=allids[buckets[allids]==bucket]
        pending=ids[~np.isfinite(out[ids]).all((1,2))]
        if not len(pending):continue
        startday='2024-09-01' if policy=='fixed' else (pd.Timestamp('2024-09-01')+pd.Timedelta(days=int(bucket)*cadence)).strftime('%Y-%m-%d')
        cut=issue(startday).tz_convert('UTC');tr=membership(policy,cut)
        require((AV.iloc[tr]<cut).all() and (ISS.iloc[pending]>=cut).all(),'causal fit violation')
        folder=ROOT/'fits'/tag/startday;folder.mkdir(parents=True,exist_ok=True)
        receipt=folder/'MEMBERSHIP.json'
        entry=dict(cutoff=cut,train_days=DAYS[tr],N_days=len(tr),latest_maturity=AV.iloc[tr].max(),
                   policy=policy,cadence=cadence,seed=seed,weights=weights(policy,tr,cut),
                   Mar_Apr_2025_days=int(((DAYS[tr]>='2025-03-01')&(DAYS[tr]<='2025-04-30')).sum()),
                   mature_May_days=int((DAYS[tr]>='2025-05-01').sum()),source_sha256=sha(BASE/'DATA.npz'))
        if receipt.exists():require(read(str(receipt.relative_to(ROOT)))['train_days']==DAYS[tr].tolist(),'cache membership changed')
        else:dump(receipt.relative_to(ROOT),entry)
        started=time.perf_counter()
        if family in ['TFT','DEEPAR']:
            from neural import fit_predict,predict_saved
            if (folder/'model.pt').exists():q,_=predict_saved(folder,Z['past'],Z['X'],pending)
            else:
                sub=np.r_[tr,pending];yy=np.zeros((len(sub),24));yy[:len(tr)]=Z['y'][tr]
                q,_,_=fit_predict(family,Z['past'][sub],Z['X'][sub],yy,np.arange(len(tr)),np.array([],int),
                    np.arange(len(tr),len(sub)),seed,.001,folder,epochs=8 if family=='TFT' else 18,
                    sample_weights=weights(policy,tr,cut))
        else:q=tree_model(family,policy,cut,tr,pending,folder)
        out[pending]=q
        path.parent.mkdir(exist_ok=True);np.savez_compressed(path,q=out)
        dump(folder.relative_to(ROOT)/f'PREDICTION_{DAYS[pending[0]]}_{DAYS[pending[-1]]}.json',dict(
            issued_days=DAYS[pending],forecast_sha256=hashlib.sha256(q.tobytes()).hexdigest(),seconds=time.perf_counter()-started,
            evaluation_labels_in_fit=int(((AV.iloc[tr]>=cut)).sum()),upper_cap=None))
    return tag,out


def forecast(family,policy,cadence,through,seed=20260924):
    from cache_locks import file_lock
    with file_lock(f'{family}_{policy}_{cadence}_{seed}'):
        if family in ['TFT','DEEPAR']:
            with file_lock('single_gpu'):
                return _forecast(family,policy,cadence,through,seed)
        return _forecast(family,policy,cadence,through,seed)


def score(q,ids):
    y=Z['y'][ids];pred=q[ids]
    require(np.isfinite(pred).all(),'missing primary population')
    m=metrics(y,pred[...,0],pred[...,1]);m['positive_coverage']=float(np.mean(y[y>0]<=pred[...,1][y>0]))
    m['burst_coverage']=float(np.mean(y[y>BURST]<=pred[...,1][y>BURST]));m['N_days']=len(ids)
    return m


def stage_a():
    require(not (ROOT/'STAGE_A_FREEZE.json').exists(),'Stage A already frozen')
    rows=[]
    for policy in POLICIES:
        for cadence in ([28] if policy=='fixed' else [1,7,28]):
            tag,q=forecast('LGBM',policy,cadence,'2024-10-30')
            rows.append(dict(policy=policy,cadence=cadence,tag=tag,**score(q,DEV)))
            print('A',policy,cadence,rows[-1]['Q90_pinball'],flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(ROOT/'STAGE_A_DEVELOPMENT.csv',index=False)
    winners=[min([r for r in rows if r['policy']==policy],key=lambda r:(r['Q90_pinball'],r['calibration_error'],r['requirement_ratio'])) for policy in POLICIES]
    winner=min([r for r in winners if r['policy']!='fixed'],key=lambda r:(r['Q90_pinball'],r['calibration_error'],r['requirement_ratio']))
    dump('STAGE_A_FREEZE.json',dict(time=now(),winner=winner,policy_cadences=winners,selection_role='DEVELOPMENT',evaluation_accessed=False),exclusive=True)


def stage_b():
    require(not (ROOT/'STAGE_B_FREEZE.json').exists(),'Stage B already frozen')
    a=read('STAGE_A_FREEZE.json')['winner'];rows=[];runs=[]
    for family in ['LGBM','HURDLE','BURST_EXPERT','TFT','DEEPAR']:
        for seed in (SEEDS if family in ['TFT','DEEPAR'] else [20260924]):
            tag,q=forecast(family,a['policy'],a['cadence'],'2024-10-30',seed)
            run=dict(family=family,seed=seed,tag=tag,policy=a['policy'],cadence=a['cadence']);runs.append(run)
            rows.append(dict(**run,**score(q,DEV)));print('B',family,seed,rows[-1]['Q90_pinball'],flush=True)
    f=pd.DataFrame(rows);f.to_csv(ROOT/'STAGE_B_DEVELOPMENT.csv',index=False)
    m=f.groupby('family')[['Q90_pinball','calibration_error','requirement_ratio']].mean()
    winner=sorted(m.index,key=lambda family:tuple(m.loc[family]))[0]
    dump('STAGE_B_FREEZE.json',dict(time=now(),winner=winner,runs=runs,selection_role='DEVELOPMENT',evaluation_accessed=False),exclusive=True)


def calibration(q,window,until):
    out=q.copy();proof=[]
    for i in OOS[DAYS[OOS]<=until]:
        pool=OOS[(AV.iloc[OOS]<ISS.iloc[i]).to_numpy()&np.isfinite(q[OOS]).all((1,2))&(DAYS[OOS]<DAYS[i])]
        pool=pool[~L.iloc[pool].split.eq('PURGE').to_numpy()]
        if window!='expanding':pool=pool[(pd.to_datetime(DAYS[pool])>=pd.Timestamp(str(DAYS[i]))-pd.Timedelta(days=int(window)))]
        if len(pool)<20:
            out[i]=np.nan;continue
        delta,rank=finite_residual(Z['y'][pool],q[pool,:,1]);out[i]=corrected(q[i],delta)
        proof.append(dict(target_day=DAYS[i],issue_time=ISS.iloc[i],source_days=DAYS[pool].tolist(),N_days=len(pool),rank=rank,
            latest_maturity=AV.iloc[pool].max(),delta_GPUh=delta.tolist()))
    return out,proof


def stage_c():
    require(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'selection already frozen')
    b=read('STAGE_B_FREEZE.json');rows=[]
    for run in b['runs']:
        tag,q=forecast(run['family'],run['policy'],run['cadence'],'2024-11-29',run['seed'])
        if run['family']!=b['winner']:continue
        for window in ['28','56','expanding']:
            c,_=calibration(q,window,'2024-11-29')
            for role,ids in [('DEVELOPMENT',DEV),('CALIBRATION',CAL)]:
                ids=ids[np.isfinite(c[ids]).all((1,2))]
                require(len(ids)>0,'calibration candidate has no support')
                rows.append(dict(window=window,split=role,seed=run['seed'],**score(c,ids)))
    f=pd.DataFrame(rows);f.to_csv(ROOT/'STAGE_C_SELECTION.csv',index=False)
    means=f.groupby(['window','split']).mean(numeric_only=True)
    def key(w):
        s=means.loc[w];band=s.Q90_coverage.between(.88,.92).all()
        return (not band,s.Q90_pinball.mean(),s.calibration_error.mean())
    chosen=min(['28','56','expanding'],key=key)
    dump('FINAL_SELECTION_FREEZE.json',dict(time=now(),temporal=read('STAGE_A_FREEZE.json')['winner'],
        model=b['winner'],calibration_window=chosen,runs=b['runs'],evaluation_accessed=False,
        architecture_reselection=False,code_hashes={p.name:sha(p) for p in ROOT.glob('*.py')},
        protocol_sha256=sha(ROOT/'PROTOCOL.json'),PRODUCTION_MODEL_PROMOTED=False),exclusive=True)


def evaluate():
    require(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'immutable evaluation complete')
    freeze=read('FINAL_SELECTION_FREEZE.json')
    for name,digest in freeze['code_hashes'].items():require(sha(ROOT/name)==digest,'post-freeze code drift')
    runs=freeze['runs'].copy()
    for r in read('STAGE_A_FREEZE.json')['policy_cadences']:
        if r['tag'] not in [a['tag'] for a in runs]:runs.append(dict(family='LGBM',seed=20260924,tag=r['tag'],policy=r['policy'],cadence=r['cadence']))
    parts=[]
    for run in runs:
        tag,q=forecast(run['family'],run['policy'],run['cadence'],'2025-05-31',run['seed'])
        c,proof=calibration(q,freeze['calibration_window'],'2025-05-31')
        dump(f'calibration/{tag}.json',proof)
        for role in ROLES[-2:]:
            ids=np.flatnonzero(L.split.eq(role)&L.eligible)
            require(np.isfinite(c[ids]).all(),'no exclusion on calibration insufficiency')
            for variant,pred in [('raw',q),('causal_calibrated',c)]:
                parts.append(pd.DataFrame(dict(target_day=np.repeat(DAYS[ids],24),target_hour=np.tile(np.arange(24),len(ids)),
                    issue_time=np.repeat(ISS.iloc[ids].astype(str),24),lead_hours=np.tile(np.arange(6,30),len(ids)),
                    actual_GPUh=Z['y'][ids].ravel(),Q50=pred[ids,:,0].ravel(),Q90=pred[ids,:,1].ravel(),
                    model=run['family'],seed=run['seed'],policy=run['policy'],cadence=run['cadence'],tag=tag,variant=variant,split=role)))
        print('EVALUATED',tag,flush=True)
    old=pd.read_parquet(BASE/'PREDICTIONS.parquet');old=old[old.model.eq('LGBM')&old.seed.eq(20260924)].copy()
    old['variant']='PR63_frozen_calibration';old['policy']='fixed';old['cadence']=28;old['model']='CURRENT_LGBM';old['tag']='PR63_CURRENT_LGBM'
    parts.append(old[parts[0].columns])
    frame=pd.concat(parts,ignore_index=True);frame.to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
    dump('EVALUATION_COMPLETE.json',dict(time=now(),rows=len(frame),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),
        NO_UNTOUCHED_CONFIRMATION=True,OPTIMIZER_CHANGED=False,GRID_CAMPAIGN_EXECUTIONS=0,PRODUCTION_MODEL_PROMOTED=False),exclusive=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['register','a','b','c','evaluate'])
    globals()[{'register':'register','a':'stage_a','b':'stage_b','c':'stage_c','evaluate':'evaluate'}[parser.parse_args().phase]]()
