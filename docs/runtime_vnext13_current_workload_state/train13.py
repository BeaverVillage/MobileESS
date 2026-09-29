from common13 import *
from model13 import columns,matrix,fit,frozen_v9,Hazard
from metrics9 import stats
import time,gc,subprocess,concurrent.futures

def sharpness(f):
    positive=f.runtime_seconds>0;ratio=f.loc[positive,'q90']/f.loc[positive,'runtime_seconds']
    short=f[positive & f.runtime_seconds.le(3600)]
    actual=float((short.runtime_seconds*short.num_gpus_req/3600).sum())
    return dict(positive_runtime_N=int(positive.sum()),zero_runtime_N=int(f.runtime_seconds.eq(0).sum()),
        Q90_actual_ratio_median=float(ratio.median()),Q90_actual_ratio_P90=float(ratio.quantile(.9)),
        short_job_N=len(short),short_job_reserved_GPUh=float((np.ceil(short.q90/900)*short.num_gpus_req*.25).sum()),
        short_job_actual_GPUh=actual,short_job_reservation_inflation=float((np.ceil(short.q90/900)*short.num_gpus_req*.25).sum()/actual) if actual else None)

def evaluate(model,par,f):
    q=np.column_stack([model.inverse_logsf(par,np.log1p(-p)) for p in [.5,.9]])
    assert np.isfinite(q).all() and (q>=0).all() and (q[:,1]>=q[:,0]).all()
    event=f.event.to_numpy(bool);cen=f.censored.to_numpy(bool);y=f.runtime_seconds.to_numpy(float);g=f.num_gpus_req.to_numpy(float)
    ll=np.full(len(f),np.nan)
    p=par[event];t=y[event];left=np.maximum(t-.5,0);right=t+.5
    dh=model.interval_hazard(p,left,right)
    ll[event]=model.logsf(p,left)+np.log(-np.expm1(-dh))
    ll[cen]=model.logsf(par[cen],f.duration_lower.to_numpy(float)[cen])
    observed=event|cen;finite=bool(np.isfinite(ll[observed]).all())
    cumulative=model.cumulative(par)
    monotone=bool(np.isfinite(par).all() and (par>0).all() and (np.diff(cumulative,axis=1)>0).all())
    summary=stats(y[event],g[event],q[event,0],q[event,1])
    summary.update(proper_interval_NLL=float(-ll[observed].mean()) if finite else None,proper_NLL_N=int(observed.sum()),
                   proper_score_finite=finite,zero_support_count=int(np.isneginf(ll[event]).sum()),monotonicity_pass=monotone)
    e=f.loc[event,['job_id','runtime_seconds','num_gpus_req','requested_seconds']].reset_index(drop=True)
    e['q50']=q[event,0];e['q90']=q[event,1]
    summary.update(sharpness(e))
    for h in [4,8,12,24]:
        a=y[event]>h*3600;summary[f'gt{h}h_N']=int(a.sum());summary[f'gt{h}h_coverage']=float((y[event][a]<=q[event,1][a]).mean()) if a.any() else None
    return summary,e,q

def summarize(arm,folds,parts):
    f=pd.concat(parts,ignore_index=True);v=pd.DataFrame(folds)
    s=stats(f.runtime_seconds,f.num_gpus_req,f.q50,f.q90)
    s.update(sharpness(f))
    w0=float((np.ceil(f.requested_seconds/900)*f.num_gpus_req*.25).sum())
    s.update(arm=arm,calibration='C0',min_fold_coverage=float(v[v.N>=100].Q90_coverage.min()),max_fold_coverage=float(v.Q90_coverage.max()),coverage_std=float(v.Q90_coverage.std(ddof=0)),
             reservation_to_W0=s['reserved_GPUh']/w0,W0_reserved_GPUh=w0,proper_interval_NLL=float(np.average(v.proper_interval_NLL,weights=v.proper_NLL_N)),
             zero_support_count=int(v.zero_support_count.sum()),proper_score_finite=bool(v.proper_score_finite.all()),monotonicity_pass=bool(v.monotonicity_pass.all()),
             inference_seconds=float(v.inference_seconds.sum()))
    for h in [4,8,12,24]:
        z=f[f.runtime_seconds>h*3600];s[f'gt{h}h_N']=len(z);s[f'gt{h}h_coverage']=float((z.runtime_seconds<=z.q90).mean()) if len(z) else None
    g=dict(A=.88<=s['Q90_coverage']<=.92,B=s['min_fold_coverage']>=.85,C=s['gt4h_coverage']>=.85,
           D=s['gt12h_N']<100 or s['gt12h_coverage']>=.80,E=s['gt24h_N']<100 or s['gt24h_coverage']>=.70,
           F=s['reservation_to_W0']<=.80,G=s['proper_score_finite'] and s['monotonicity_pass'],H=s['zero_support_count']==0,
           I=read(ROOT/'CURRENT_STATE_CAUSALITY_AUDIT.json')['PASS'] and read(ROOT/'CURRENT_STATE_REPLAY_AUDIT.json')['PASS'])
    s.update({f'gate_{k}':bool(value) for k,value in g.items()});s['eligible']=all(g.values())
    return s

def one(i,arm,regime,ablation=None):
    name=arm if ablation is None else arm+'_ABL_'+ablation
    folder=LOCAL/f'fold{i}';folder.mkdir(exist_ok=True)
    result=folder/(name+'.json');part=folder/(name+'.parquet')
    if result.exists() and part.exists():return read(result),pd.read_parquet(part)
    train=data(i,'TRAIN');valid=data(i,'VALID');pre=prep(i)
    assert not set(train.job_id)&set(valid.job_id)
    assert train.loc[train.event,'end_time'].lt(pd.Timestamp(pre['fit_cutoff'])).all()
    if arm.startswith('D90'):
        train=train[train.submit_time.ge(pd.Timestamp(pre['fit_cutoff'])-pd.Timedelta(days=90))].reset_index(drop=True)
        # D90 descriptor mappings also use D90 TRAIN only.
        maps={}
        for col in ['qos','partition','account']:
            n=train[col].astype('string').fillna('__MISSING__').value_counts()
            maps[col]={v:k+1 for k,v in enumerate(sorted(n[n>= (20 if col=='account' else 1)].index))}
        pre={**pre,'categorical_mappings':maps}
    cols=columns(arm,pre['columns'],regime.columns,ablation)
    dest=ROOT/'FOLD_MODELS'/f'fold{i}'/name
    print(now(),'FIT',i,name,'features',len(cols),'rows',len(train),flush=True)
    if arm.endswith('S0'):model=frozen_v9(i)
    elif (dest/'model.json').exists():model=Hazard.load(dest)
    else:
        equivalent=None
        if ablation:
            for other in read(ROOT/'EXPERIMENT_PROTOCOL.json')['arms']:
                if other!=arm and other.split('_')[0]==arm.split('_')[0] and columns(other,pre['columns'],regime.columns)==cols:
                    equivalent=other;break
        if equivalent:
            src=ROOT/'FOLD_MODELS'/f'fold{i}'/equivalent
            if equivalent.endswith('S0'):
                model=frozen_v9(i);model.meta.update(preprocessing=pre,TRAIN_N=len(train))
                booster=V9/'FOLD_MODELS'/f'fold{i}/D1/0.txt'
            else:
                model=Hazard.load(src);booster=src/'hazard.txt'
            assert model.meta['columns']==cols and model.meta['preprocessing']==pre and model.meta['TRAIN_N']==len(train)
            model.meta.update(arm=arm,ablation=ablation,reused_equivalent_arm=equivalent,
                              equivalent_source_booster=record(booster),training_seconds=0.)
            model.save(dest)
        else:
            x=matrix(train,pre,regime,cols);model=fit(train,x,pre,arm,ablation);model.save(dest);del x
    print(now(),'PREDICT',i,name,'fit_seconds',model.meta['training_seconds'],flush=True)
    xv=matrix(valid,pre,regime,cols);start=time.perf_counter();par=model.parameters(xv,threads=4);inference=time.perf_counter()-start
    if arm.endswith('S0'):
        cached=np.load(V9/'.local'/f'fold{i}/D1.npz')['val_parameters']
        assert np.array_equal(par,cached),float(np.max(abs(par-cached)))
        write(f'V9_PARITY/fold{i}.json',dict(fold=i,all_VALID_rows=len(valid),parameters_equal=True,max_abs_error=0,
            booster=record(V9/'FOLD_MODELS'/f'fold{i}/D1/0.txt'),train_membership=ids(train),valid_membership=ids(valid)))
    s,p,q=evaluate(model,par,valid)
    s.update(fold=i,arm=name,calibration='C0',training_seconds=model.meta['training_seconds'],inference_seconds=inference,
             TRAIN_N=len(train),features=len(cols),VALID_N=len(valid))
    np.savez_compressed(folder/(name+'_quantiles.npz'),q=q)
    p.to_parquet(part,index=False);write(result,s)
    print(now(),'DONE',i,name,'coverage',s['Q90_coverage'],'gt4h',s['gt4h_coverage'],flush=True)
    del model,xv,par;gc.collect()
    return s,p

def load_features():
    return pd.read_parquet(LOCAL/'CURRENT_STATE_FEATURES.parquet').set_index('job_id')

def worker(slot,phase):
    regime=load_features()
    if phase=='primary': tasks=[(i,arm,None) for arm in read(ROOT/'EXPERIMENT_PROTOCOL.json')['arms'] for i in range(1,6)]
    else:
        arm=read(ROOT/'TOTAL_MODEL_SELECTION_FREEZE.json')['diagnostic_ablation_anchor']
        original=columns(arm,prep(1)['columns'],regime.columns)
        tasks=[(i,arm,g) for g in 'ABCDE' if columns(arm,prep(1)['columns'],regime.columns,g)!=original for i in range(1,6)]
    for n,(i,arm,group) in enumerate(tasks):
        if n%2==slot:one(i,arm,regime,group)

def launch(phase):
    def run(slot):
        with (LOCAL/f'{phase}_worker{slot}.log').open('a',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-B',str(ROOT/'train13.py'),'worker',str(slot),phase],stdout=log,stderr=subprocess.STDOUT,check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,[0,1]))

def collect(arm,group=None):
    name=arm if group is None else arm+'_ABL_'+group
    folds=[read(LOCAL/f'fold{i}'/(name+'.json')) for i in range(1,6)]
    parts=[pd.read_parquet(LOCAL/f'fold{i}'/(name+'.parquet')) for i in range(1,6)]
    return summarize(name,folds,parts),folds,parts

def main():
    if len(sys.argv)>1 and sys.argv[1]=='worker':worker(int(sys.argv[2]),sys.argv[3]);return
    assert read(ROOT/'STAGE_A_VERDICT.json')['PASS']
    for r in read(ROOT/'PREREGISTRATION.json')['files']:assert sha(r['path'])==r['sha256']
    if not (ROOT/'TRAINING_STARTED.json').exists():write('TRAINING_STARTED.json',dict(time=now(),preregistration=record(ROOT/'PREREGISTRATION.json'),stage_A=record(ROOT/'STAGE_A_VERDICT.json')))
    launch('primary')
    arms=read(ROOT/'EXPERIMENT_PROTOCOL.json')['arms'];allfold=[];summary=[];tails=[]
    for arm in arms:
        s,folds,parts=collect(arm);summary.append(s);allfold.extend(folds)
        for i,p in enumerate(parts,1):
            for h in [4,8,12,24]:
                z=p[p.runtime_seconds>h*3600]
                tails.append(dict(arm=arm,fold=i,cohort=f'gt{h}h',**stats(z.runtime_seconds,z.num_gpus_req,z.q50,z.q90)))
    comp=pd.DataFrame(summary);fd=pd.DataFrame(allfold)
    comp.to_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv',index=False)
    fd.to_csv(ROOT/'TOTAL_FOLD_METRICS.csv',index=False)
    pd.DataFrame(tails).to_csv(ROOT/'TOTAL_LONG_TAIL_METRICS.csv',index=False)
    fd[['arm','fold','proper_interval_NLL','proper_NLL_N','zero_support_count','proper_score_finite','monotonicity_pass']].to_csv(ROOT/'TOTAL_DISTRIBUTIONAL_METRICS.csv',index=False)
    fd[['arm','fold','GPU_weighted_coverage','reserved_GPUh','actual_GPUh','reservation_actual_GPUh']].to_csv(ROOT/'TOTAL_GPU_WEIGHTED_METRICS.csv',index=False)
    comp[['arm','Q90_coverage','min_fold_coverage','max_fold_coverage','coverage_std','gt4h_coverage','Q90_pinball','eligible']].to_csv(ROOT/'TEMPORAL_ROBUSTNESS_COMPARISON.csv',index=False)
    rank=read(ROOT/'EXPERIMENT_PROTOCOL.json')['ranking']
    candidates=comp[(comp.min_fold_coverage>=.80)&(comp.gt4h_coverage>=.80)].sort_values(rank)
    write('C1_ELIGIBILITY_AUDIT.json',dict(time=now(),eligible_C0_arms=candidates.arm.tolist(),C1_ROLLING14_EVALUATED=False,
        status='NOT_RUN_PRECONDITION_FAILED' if candidates.empty else 'ELIGIBLE_PENDING_EVALUATION',max_challengers=1))
    if not candidates.empty:
        from calibration13 import run_c1
        extra,extra_folds=run_c1(candidates.iloc[0].arm)
        comp=pd.concat([comp,pd.DataFrame([extra])],ignore_index=True)
        comp.to_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv',index=False)
        fd=pd.concat([fd,pd.DataFrame(extra_folds)],ignore_index=True);fd.to_csv(ROOT/'TOTAL_FOLD_METRICS.csv',index=False)
    passed=comp[comp.eligible].sort_values(rank)
    diagnostic=comp[(comp.arm!='EXPANDING_S0')&(comp.calibration=='C0')].sort_values(rank).iloc[0]
    selected=None if passed.empty else passed.iloc[0].arm
    write('TOTAL_MODEL_SELECTION_FREEZE.json',dict(time=now(),selected_arm=selected,selected_state_set='NONE' if selected is None else selected.split('_')[1],
        TOTAL_RUNTIME_MODEL_VALIDATED=bool(selected),STAGE_C_AUTHORIZED=bool(selected),diagnostic_ablation_anchor=diagnostic.arm,
        diagnostic_anchor_is_not_selected_provider=True,files=[record(ROOT/n) for n in ['TOTAL_MODEL_COMPARISON.csv','TOTAL_FOLD_METRICS.csv','EXPERIMENT_PROTOCOL.json']]))
    write('V9_ANCHOR_REPRODUCTION.json',dict(time=now(),PASS=True,TAIL_GRID_CHANGED_FROM_V9=False,
        folds=[read(ROOT/f'V9_PARITY/fold{i}.json') for i in range(1,6)],calibration='C0; V10 stable log-space support-correct scoring'))
    launch('ablation')
    ablations=[];afolds=[];arm=diagnostic.arm
    statecols=read(ROOT/'CURRENT_STATE_FEATURE_CONTRACT.json')['columns'];static=prep(1)['columns']
    for group in 'ABCDE':
        if columns(arm,static,statecols,group)==columns(arm,static,statecols):
            ablations.append(dict(group=group,arm=arm,status='NOT_APPLICABLE_GROUP_ABSENT',metrics_available=False));continue
        s,folds,parts=collect(arm,group);afolds.extend(folds)
        s.update(group=group,status='DIAGNOSTIC_ONLY',metrics_available=True,anchor=arm,
                 delta_min_fold=s['min_fold_coverage']-diagnostic.min_fold_coverage,
                 delta_pinball=s['Q90_pinball']-diagnostic.Q90_pinball)
        ablations.append(s)
    pd.DataFrame(ablations).to_csv(ROOT/'CURRENT_STATE_FEATURE_ABLATION.csv',index=False)
    pd.DataFrame(afolds).to_csv(ROOT/'ABLATION_FOLD_METRICS.csv',index=False)
    write('TRAINING_COMPLETED.json',dict(time=now(),arms=arms,selected=selected,ablation_anchor=diagnostic.arm,April_opened=False,May_opened=False))
    print(now(),'STAGE_B_COMPLETE','selected',selected,flush=True)

if __name__=='__main__':main()
