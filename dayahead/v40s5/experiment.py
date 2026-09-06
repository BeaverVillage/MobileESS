"""Preregistered historical-only fitting and frozen candidate evaluation."""
import time
import sys
from lightgbm import LGBMRegressor, Booster
from .common import *

def fit_model(frame,pre,target,config,alpha,name):
    assert not (OUT/'V40S5_EXPOSURE_EVENT.json').exists(), 'NO_REFIT_AFTER_EXPOSED'
    assert frame.end_time.lt(CUTOFF).all()
    kw=dict(FIXED,**CONFIGS[config],objective='regression' if alpha is None else 'quantile')
    if alpha is not None: kw['alpha']=alpha
    start=time.perf_counter(); model=LGBMRegressor(**kw).fit(pre.transform(frame),np.asarray(target,float)).booster_
    path=OUT/'models'/f'{name}.txt';path.parent.mkdir(exist_ok=True)
    model.save_model(str(path))
    ledger=read('COMPUTE_LEDGER');ledger['fits'].append(dict(name=name,timestamp=now(),config=config,alpha=alpha,
      fit_N=len(frame),fit_ids=ids(frame.job_uid),max_fit_end=frame.end_time.max(),preprocessing=pre.descriptor(),
      seconds=time.perf_counter()-start,SHA256=file_sha(path),num_trees=model.num_trees()))
    write('COMPUTE_LEDGER',ledger)
    return model

def save_pre(name,pre):
    (OUT/'models'/f'{name}_preprocessing.json').write_text(json.dumps(pre.descriptor(),indent=2)+'\n')

def load_pre(name):
    d=json.loads((OUT/'models'/f'{name}_preprocessing.json').read_text());p=Preprocess(d['track']);p.__dict__.update(d);return p

def tune(lib):
    fit,valid,_=temporal_split(lib);pre=Preprocess().fit(fit);save_pre('HIST_FIT_P',pre)
    results=[]
    for config in CONFIGS:
        raw=[]; row=dict(config=config)
        for a in QUANTILES:
            model=fit_model(fit,pre,fit.runtime_seconds,config,a,f'TUNE_{config}_Q{int(a*100)}')
            pred=model.predict(pre.transform(valid),num_threads=1);raw.append(pred)
            row[f'Q{int(a*100)}_pinball']=pinball(valid.runtime_seconds,pred,a)
        arr=np.column_stack(raw);row['raw_crossing_fraction']=float((np.diff(arr,axis=1)<0).any(axis=1).mean())
        row['mean_normalized_pinball']=float(np.mean([row[f'Q{int(a*100)}_pinball'] for a in QUANTILES])/valid.runtime_seconds.mean())
        results.append(row)
    selected=min(results,key=lambda d:(d['mean_normalized_pinball'],d['Q99_pinball'],d['raw_crossing_fraction'],list(CONFIGS).index(d['config'])))['config']
    pd.DataFrame(results).to_csv(OUT/'V40S5_HYPERPARAMETER_RESULTS.csv',index=False)
    write('HYPERPARAMETER_FREEZE',dict(timestamp=now(),selected=selected,results=results,shared_for_all_final_quantiles=True,
      selection_source='HIST_TUNE only',PENDING_scored=False,HIST_FIT_ids=ids(fit.job_uid),HIST_TUNE_ids=ids(valid.job_uid)))
    print('HIST_TUNE selected '+selected,flush=True)
    return selected

def fit_family(lib,config,track,prefix,diagnostic=False):
    pre=Preprocess(track).fit(lib);save_pre(prefix,pre)
    for a in QUANTILES:
        fit_model(lib,pre,lib.runtime_seconds,config,a,f'{prefix}_Q{int(a*100)}')
    rows=[];fold_reports=[]
    for k,train,valid in temporal_folds(lib):
        assert not set(train.job_uid)&set(valid.job_uid) and train.end_time.max()<valid.end_time.min()
        fp=Preprocess(track).fit(train);save_pre(f'{prefix}_OOF{k}',fp)
        model=fit_model(train,fp,train.runtime_seconds,'L0',.5,f'{prefix}_OOF{k}_Q50')
        pred=np.maximum(model.predict(fp.transform(valid),num_threads=1),0.)
        d=valid[['job_uid','end_time','runtime_seconds']].copy();d['fold']=k;d['Q50_OOF']=pred
        d['residual']=valid.runtime_seconds.to_numpy()-pred;d['r2']=d.residual**2
        d['fit_max_end']=train.end_time.max();d['valid_min_end']=valid.end_time.min();d['fit_ids_sha256']=ids(train.job_uid)
        rows.append(d)
        fold_reports.append(dict(fold=k,fit_N=len(train),valid_N=len(valid),fit_ids=ids(train.job_uid),valid_ids=ids(valid.job_uid),
          max_fit_end=train.end_time.max(),min_valid_end=valid.end_time.min(),job_overlap=0,preprocessing=fp.descriptor(),
          config='L0',num_trees=model.num_trees(),constant_model=bool(model.num_trees()==1)))
    oof=pd.concat(rows).sort_values(['end_time','job_uid']).reset_index(drop=True)
    assert not oof.job_uid.duplicated().any() and (oof.fit_max_end<oof.end_time).all()
    residual_rows=lib.set_index('job_uid').loc[oof.job_uid].reset_index()
    fit_model(residual_rows,pre,oof.r2,config,None,f'{prefix}_RESIDUAL')
    oof.to_parquet(OUT/f'V40S5_{prefix}_RESIDUAL_OOF.parquet',index=False)
    report=dict(timestamp=now(),prefix=prefix,OOF_N=len(oof),warmup_excluded=len(lib)-len(oof),folds=fold_reports,
      OOF_config='L0 fixed independently of HIST_TUNE selection',final_residual_config=config,in_sample_residuals=0,
      model_training_job_overlap_with_its_OOF_predictions=0,r2_distribution=distribution(oof.r2),OOF_Q50_MAE=float(oof.residual.abs().mean()),
      all_labels_mature=True,strict_expanding_end_time=True)
    write(f'{prefix}_RESIDUAL_CROSSFIT_AUDIT',report)
    if prefix=='P':
        write('RESIDUAL_CROSSFIT_AUDIT',report)
        write('RESIDUAL_MODEL_REPORT',dict(model='LightGBM regression on chronological OOF squared errors',config=config,
          OOF_N=len(oof),sigma_formula='sqrt(max(predicted_r2,0))',SHA256=file_sha(OUT/'models/P_RESIDUAL.txt'),
          squared_residual_distribution=distribution(oof.r2),uncertainty_is_not_calibrated_interval=True))
    if diagnostic:
        hf,ht,boundary=temporal_split(lib)
        od=oof[oof.end_time<boundary];r=lib.set_index('job_uid').loc[od.job_uid].reset_index()
        dp=Preprocess(track).fit(hf);save_pre('DIAGNOSTIC_RESIDUAL_P',dp)
        fit_model(r,dp,od.r2,config,None,'DIAGNOSTIC_RESIDUAL_P')
    return report

def predict(prefix,f):
    start=time.perf_counter();pre=load_pre(prefix);x=pre.transform(f)
    raw=np.column_stack([Booster(model_file=str(OUT/'models'/f'{prefix}_Q{int(a*100)}.txt')).predict(x,num_threads=1) for a in QUANTILES])
    r2=Booster(model_file=str(OUT/'models'/f'{prefix}_RESIDUAL.txt')).predict(x,num_threads=1)
    q=repair(raw);sigma=np.sqrt(np.maximum(r2,0))
    assert np.isfinite(sigma).all()
    ledger=read('COMPUTE_LEDGER');ledger['inference'].append(dict(prefix=prefix,N=len(f),seconds=time.perf_counter()-start,timestamp=now()))
    write('COMPUTE_LEDGER',ledger)
    return raw,q,sigma,r2

def score(prefix,role):
    f=panel(role);raw,q,sigma,r2=predict(prefix,f)
    preds=f[['job_uid','job_issue_uid','role','issue_day','issue_time','runtime_seconds','requested_seconds','num_gpus_req','reference_safe_sec']].copy()
    for i,a in enumerate(QUANTILES):preds[f'raw_Q{int(a*100)}']=raw[:,i];preds[f'Q{int(a*100)}']=q[:,i]
    preds['sigma']=sigma;preds['predicted_r2']=r2
    vals=candidates(f,q,sigma)
    results={};days={};g={}
    for c,p in vals.items():
        preds[c]=p;preds[c+'_slots']=np.ceil(p/900).astype('int64')
        results[c]=metrics(f,p);days[c]=daily_metrics(f,p)
    for c in CANDIDATES[2:]:g[c]=gates(results[c],days[c],results[CANDIDATES[0]],results[CANDIDATES[1]])
    qreport={f'Q{int(a*100)}':dict(raw_pinball=pinball(f.runtime_seconds,raw[:,i],a),corrected_pinball=pinball(f.runtime_seconds,q[:,i],a),
                  metrics=metrics(f,q[:,i])) for i,a in enumerate(QUANTILES)}
    report=dict(prefix=prefix,role=role,results=results,daily=days,gates=g,quantiles=qreport)
    write(f'{prefix}_{role}_REPORT',report)
    preds.to_parquet(OUT/f'V40S5_{prefix}_{role}_PREDICTIONS.parquet',index=False)
    if prefix=='P':
        short=dict(TRAIN='TRAIN',DEVELOPMENT='DEV',CALIBRATION='CAL',EXPOSED_EVALUATION='EXPOSED')[role]
        pd.DataFrame([dict(candidate=c,**{k:v for k,v in results[c].items() if not isinstance(v,dict)}) for c in CANDIDATES]).to_csv(OUT/f'V40S5_CANDIDATE_RESULTS_{short}.csv',index=False)
    return report

def importance(lib,config):
    fit,tune,_=temporal_split(lib);reports={};oof=pd.read_parquet(OUT/'V40S5_P_RESIDUAL_OOF.parquet')
    for name,a in [(f'Q{int(a*100)}',a) for a in QUANTILES]+[('RESIDUAL',None)]:
        final=Booster(model_file=str(OUT/'models'/f'P_{name}.txt'));fp=load_pre('P')
        gain=final.feature_importance(importance_type='gain')
        grouped={c:float(sum(v for v,g in zip(gain,fp.groups) if g==c)) for c in FEATURES}
        dp=load_pre('HIST_FIT_P' if a is not None else 'DIAGNOSTIC_RESIDUAL_P')
        dm=Booster(model_file=str(OUT/'models'/(f'TUNE_{config}_{name}.txt' if a is not None else 'DIAGNOSTIC_RESIDUAL_P.txt')))
        if a is not None: val=tune.copy();target=val.runtime_seconds.to_numpy()
        else:
            od=oof[oof.job_uid.isin(tune.job_uid)];val=lib.set_index('job_uid').loc[od.job_uid].reset_index();target=od.r2.to_numpy()
        def loss(pred): return pinball(target,pred,a) if a is not None else float(np.mean((target-pred)**2))
        base_loss=loss(dm.predict(dp.transform(val),num_threads=1));perm={}
        for c in FEATURES:
            delta=[]
            for k in range(3):
                v=val.copy();rng=np.random.default_rng(SEED+k);v[c]=v[c].to_numpy()[rng.permutation(len(v))]
                delta.append(loss(dm.predict(dp.transform(v),num_threads=1))-base_loss)
            perm[c]=dict(mean_loss_increase=float(np.mean(delta)),values=delta)
        reports[name]=dict(grouped_gain=grouped,grouped_gain_fraction={c:v/sum(grouped.values()) if sum(grouped.values()) else 0. for c,v in grouped.items()},
          permutation_HIST_TUNE=perm,baseline_loss=base_loss,loss='pinball' if a is not None else 'MSE of OOF squared error',
          permutation_model='HIST_FIT-only auxiliary instance',in_sample_permutation=False,feature_selection=False)
    write('FEATURE_IMPORTANCE_DIAGNOSTIC',reports)

def primary():
    guard_receipt('PREREGISTRATION_COMMIT_RECEIPT');assert not (OUT/'models').exists()
    lib=library();config=tune(lib);fit_family(lib,config,'P','P',diagnostic=True);importance(lib,config)
    scored={r:score('P',r) for r in ROLES[:3]}
    results={r:v['results'] for r,v in scored.items()};gate_map={r:v['gates'] for r,v in scored.items()}
    pb={c:sum(scored[r]['quantiles'][{'R2_Q90':'Q90','R3_Q95':'Q95','R4_Q99':'Q99','R5_UARP_STYLE':'Q99'}[c]]['raw_pinball'] for r in ROLES[1:3]) for c in CANDIDATES[2:]}
    selected=choose(results,gate_map,pb)
    write('SELECTION_FREEZE',dict(timestamp=now(),selected_model=selected,selected_lightgbm_config=config,track='P',gates=gate_map,
      selection_roles=ROLES[1:3],corresponding_pinball=pb,EXPOSED_scored=False,preprocessing=load_pre('P').descriptor(),
      UARP_coefficients=[.20,.50],model_SHA256={p.name:file_sha(p) for p in sorted((OUT/'models').glob('*'))},
      preregistration_sha256=file_sha(OUT/'V40S5_PREREGISTRATION.json'),evaluation_contract='Preregistered gates, job-issue primary, exposed cannot reselect'))
    print(json.dumps(dict(config=config,selected=selected,gates=gate_map),indent=2),flush=True)

def sensitivity_repeat():
    guard_receipt('PREREGISTRATION_COMMIT_RECEIPT');guard_receipt('SELECTION_FREEZE_COMMIT_RECEIPT')
    assert not (OUT/'models/PW_Q50.txt').exists()
    lib=library();config=read('HYPERPARAMETER_FREEZE')['selected']
    fit_family(lib,config,'PW','PW')
    for r in ROLES[:3]:score('PW',r)
    fit_family(lib,config,'P','REPEAT_P')
    # Repeat rebuilt preprocessing, every median OOF model and residual target independently.
    probe=pd.concat([panel(r) for r in ROLES[:3]],ignore_index=True)
    raw,q,sigma,_=predict('P',probe);rr,rq,rs,_=predict('REPEAT_P',probe)
    compare={}
    pairs={**{f'Q{int(a*100)}':(q[:,i],rq[:,i]) for i,a in enumerate(QUANTILES)},'sigma':(sigma,rs)}
    pairs.update({c:(v,candidates(probe,rq,rs)[c]) for c,v in candidates(probe,q,sigma).items() if c in CANDIDATES[2:]})
    for name,(a,b) in pairs.items():
        delta=np.abs(a-b);compare[name]=dict(max_difference=float(delta.max()),mean_difference=float(delta.mean()),exact_equal=bool(np.array_equal(a,b)))
    o1=pd.read_parquet(OUT/'V40S5_P_RESIDUAL_OOF.parquet');o2=pd.read_parquet(OUT/'V40S5_REPEAT_P_RESIDUAL_OOF.parquet')
    pd.testing.assert_frame_equal(o1,o2)
    write('REPRODUCIBILITY_AUDIT',dict(status='PASS' if all(v['exact_equal'] for v in compare.values()) else 'FAIL',seed=SEED,
      independent_full_P_pipeline_rebuilds=1,probe='TRAIN+DEV+CAL only before EXPOSED',probe_N=len(probe),compare=compare,
      OOF_evidence_exact_equal=True,better_repeat_selected=False,repeat_can_change_selection=False,completed_before_exposed=True))
    assert all(v['exact_equal'] for v in compare.values())
    write('PREEXPOSED_FREEZE',dict(timestamp=now(),primary_selection=read('SELECTION_FREEZE')['selected_model'],
      selection_commit=read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit'],PW_complete=True,repeat_complete=True,
      EXPOSED_scored=False,all_model_SHA256={p.name:file_sha(p) for p in sorted((OUT/'models').glob('*'))}))
    print('P-W sensitivity and independent repeat complete before EXPOSED',flush=True)

def expose():
    guard_receipt('PREREGISTRATION_COMMIT_RECEIPT');guard_receipt('SELECTION_FREEZE_COMMIT_RECEIPT');guard_receipt('PREEXPOSED_COMMIT_RECEIPT')
    assert not (OUT/'V40S5_EXPOSURE_EVENT.json').exists()
    write('EXPOSURE_EVENT',dict(timestamp=now(),selection_commit=read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit'],preexposed_commit=read('PREEXPOSED_COMMIT_RECEIPT')['commit'],
      no_subsequent_fit_allowed=True,role='EXPOSED_EVALUATION',status='exposed historical evidence, not untouched confirmation'))
    p=score('P','EXPOSED_EVALUATION');score('PW','EXPOSED_EVALUATION')
    selected=read('SELECTION_FREEZE')['selected_model']
    success=selected is not None and p['gates'][selected]['eligible']
    devcal=read('SELECTION_FREEZE')['gates']
    safety_pair=any(all(devcal[r][c]['safety'] for r in ROLES[1:3]) for c in CANDIDATES[2:])
    if success:classification='V40S5_UNCERTAINTY_AWARE_RUNTIME_PREVALIDATED'
    elif selected is not None:
        classification='V40S5_DIRECT_RUNTIME_SAFETY_FAIL' if not p['gates'][selected]['safety'] else 'V40S5_RUNTIME_EFFICIENCY_FAIL'
    else:classification='V40S5_RUNTIME_EFFICIENCY_FAIL' if safety_pair else 'V40S5_DIRECT_RUNTIME_SAFETY_FAIL'
    reductions={c:dict(GPU_under_reduction_vs_RSP=1-p['results'][c]['GPU_under_sec']/p['results'][CANDIDATES[0]]['GPU_under_sec'],
                      GPU_over_reduction_vs_request=1-p['results'][c]['GPU_over_h']/p['results'][CANDIDATES[1]]['GPU_over_h']) for c in CANDIDATES[2:]}
    write('EXPOSED_RESULTS',dict(timestamp=now(),selected=selected,classification=classification,selected_pass=bool(success),results=p['results'],
      gates=p['gates'],reductions=reductions,no_reselection=True,no_refit=True,evidence='EXPOSED HISTORICAL; not untouched confirmation'))
    write('FINAL_DECISION',dict(classification=classification,selected_model=selected,prevalidated=bool(success),
      recommended_operational_runtime='CURRENT_RSP',CURRENT_RSP_REPLACED='NO',optimizer_integration='NO',production_ready='NO',
      FURTHER_RUNTIME_MODEL_PROLIFERATION='NO',FURTHER_RUNTIME_MODEL_WORK='DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA' if not success else 'INTEGRATION_AND_SHADOW_VALIDATION_REQUIRED',holds=HOLDS))
    rows=[]
    if success:
        f=pd.read_parquet(OUT/'V40S5_P_EXPOSED_EVALUATION_PREDICTIONS.parquet').sort_values('issue_time').drop_duplicates('job_uid')
        hashes=read('SELECTION_FREEZE')['model_SHA256']
        for _,v in f.iterrows():
            rows.append(dict(job_uid=v.job_uid,runtime_q50_sec=v.Q50,runtime_q90_sec=v.Q90,runtime_q95_sec=v.Q95,runtime_q99_sec=v.Q99,
              runtime_sigma_sec=v.sigma,runtime_candidate_name=selected,runtime_safe_sec=v[selected],runtime_safe_slots_15min=int(np.ceil(v[selected]/900)),
              request_state_assumption_id=ASSUMPTION,model_sha256=sha(json.dumps(hashes,sort_keys=True).encode()),preprocessing_sha256=file_sha(OUT/'models/P_preprocessing.json')))
    write('RUNTIME_ADAPTER_PROPOSAL',dict(proposal_only=True,optimizer_use_allowed=False,recommended_rows=rows))
    print(json.dumps(dict(classification=classification,selected=selected,gates=p['gates'],reductions=reductions),indent=2),flush=True)

if __name__=='__main__':
    {'primary':primary,'sensitivity':sensitivity_repeat,'expose':expose}[sys.argv[1]]()
