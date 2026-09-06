"""FIT -> PREDICT -> HASH -> SCORE at each observed issue, in time order."""
import sys
import time
from .common import *
from .data import history,features,labels,event,check_membership
from .models import build,predict,historical_permutation

def stage_issues(stage):
    rows=read('PENDING_PANEL_IDENTITY_AUDIT')['issues']
    return [v for v in rows if (v['role']=='EXPOSED_EVALUATION')==(stage=='exposed')]

def current_training():
    p=OUT/f'{PREFIX}DAILY_TRAINING_LEDGER.parquet'
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()

def save_prediction(t,track,f,package):
    start=time.perf_counter();raw,q,sigma,r2=predict(package,f)
    cols=['job_id','job_uid','job_issue_uid','issue_time','issue_day','role','panel_row_order','requested_seconds','num_gpus_req','reference_safe_sec']
    out=f[cols].copy()
    for i,a in enumerate(QUANTILES):out[f'raw_Q{int(a*100)}']=raw[:,i];out[f'Q{int(a*100)}']=q[:,i]
    out['sigma']=sigma;out['predicted_r2']=r2
    for name,p in candidates(f,q,sigma).items():out[name]=p;out[name+'_slots']=np.ceil(p/900).astype('int64')
    path=OUT/'predictions'/f'{key(t)}_{track}.parquet';path.parent.mkdir(exist_ok=True)
    assert not path.exists();out.to_parquet(path,index=False)
    digest=file_sha(path)
    event(t,'PREDICTION_HASH',track=track,path=str(path.relative_to(OUT)).replace('\\','/'),SHA256=digest,
      columns=out.columns.tolist(),label_columns=[],N=len(out),inference_seconds=time.perf_counter()-start)
    assert not set(LABELS)&set(out.columns)
    return out

def score_issue(t,track,pred,y,membership):
    d=pred.merge(y[['job_issue_uid',*LABELS]],on='job_issue_uid',validate='one_to_one',how='left',sort=False)
    assert ordered_ids(d.job_issue_uid)==ordered_ids(pred.job_issue_uid) and d.runtime_seconds.notna().all()
    assert d.start_time.gt(pd.Timestamp(t)).all()
    result={c:metrics(d,d[c]) for c in CANDIDATES}
    quantiles={f'Q{int(a*100)}':dict(raw_pinball=pinball(d.runtime_seconds,d[f'raw_Q{int(a*100)}'],a),
       corrected_pinball=pinball(d.runtime_seconds,d[f'Q{int(a*100)}'],a),metrics=metrics(d,d[f'Q{int(a*100)}'])) for a in QUANTILES}
    raw=d[[f'raw_Q{int(a*100)}' for a in QUANTILES]].to_numpy();q=d[[f'Q{int(a*100)}' for a in QUANTILES]].to_numpy()
    aa=.2*d.Q99;bb=.5*d.sigma
    crossing=dict(raw_N=int((np.diff(raw,axis=1)<0).any(axis=1).sum()),raw_fraction=float((np.diff(raw,axis=1)<0).any(axis=1).mean()),
      corrected_N=int((np.diff(q,axis=1)<0).any(axis=1).sum()),raw_negative_values=int((raw<0).sum()),correction_sec=distribution((q-raw).ravel()))
    report=dict(issue_time=pd.Timestamp(t),role=d.role.iloc[0],track=track,N_eval_jobs=len(d),N_training_jobs=membership['training_job_count'],
      new_training_jobs=membership['new_jobs_added_since_previous_issue'],results=result,quantiles=quantiles,crossing=crossing,
      sigma=distribution(d.sigma),negative_r2_N=int((d.predicted_r2<0).sum()),
      margin=dict(A_ge_B_fraction=float((aa>=bb).mean()),B_gt_A_fraction=float((bb>aa).mean()),A=distribution(aa),B=distribution(bb),margin=distribution(np.maximum(aa,bb))),
      actual_gt_request_N=int((d.runtime_seconds>d.requested_seconds).sum()),runtime=distribution(d.runtime_seconds),
      actual_request_ratio=distribution(d.runtime_seconds/d.requested_seconds))
    dump(OUT/'daily'/f'{key(t)}_{track}.json',report)
    (OUT/'scored').mkdir(exist_ok=True);d.to_parquet(OUT/'scored'/f'{key(t)}_{track}.parquet',index=False)
    return report

def combine(track,roles):
    paths=[OUT/'scored'/f"{key(v['issue_time'])}_{track}.parquet" for v in read('PENDING_PANEL_IDENTITY_AUDIT')['issues'] if v['role'] in roles]
    assert paths and all(p.exists() for p in paths)
    return pd.concat([pd.read_parquet(p) for p in paths],ignore_index=True).sort_values('panel_row_order').reset_index(drop=True)

def aggregate(track,roles):
    data=combine(track,roles);all_results={};all_gates={};quantiles={}
    for role in roles:
        f=data[data.role==role];assert len(f)==EXPECTED[role]
        result={c:metrics(f,f[c]) for c in CANDIDATES};daily={c:daily_metrics(f,f[c]) for c in CANDIDATES}
        gate={c:gates(result[c],daily[c],result[CANDIDATES[0]],result[CANDIDATES[1]]) for c in CANDIDATES[2:]}
        all_results[role]=result;all_gates[role]=gate
        quantiles[role]={f'Q{int(a*100)}':dict(raw_pinball=pinball(f.runtime_seconds,f[f'raw_Q{int(a*100)}'],a),
          corrected_pinball=pinball(f.runtime_seconds,f[f'Q{int(a*100)}'],a),metrics=metrics(f,f[f'Q{int(a*100)}'])) for a in QUANTILES}
    return dict(track=track,results=all_results,gates=all_gates,quantiles=quantiles)

def run(stage):
    guard('PREREGISTRATION_COMMIT_RECEIPT')
    if stage=='exposed':guard('SELECTION_FREEZE_COMMIT_RECEIPT')
    issues=stage_issues(stage);done=current_training()
    previous_t=pd.Timestamp(done.iloc[-1].issue_time) if len(done) else None
    previous_ids=pd.read_parquet(OUT/'membership'/f'{key(previous_t)}.parquet',columns=['job_uid']).job_uid.tolist() if len(done) else []
    repeats=set(read('PREREGISTRATION')['repeat_issue_times'])
    for ix,v in enumerate(issues):
        t=pd.Timestamp(v['issue_time']);k=key(t)
        if len(done) and t in set(pd.to_datetime(done.issue_time,utc=True)):
            eventpath=OUT/'events'/f'{k}.json';ev=json.loads(eventpath.read_text())
            assert ev[-1]['kind']=='ISSUE_COMPLETE'
            continue  # Resume an already complete issue, never refit it.
        assert previous_t is None or previous_t<t
        event(t,'ISSUE_BEGIN',stage=stage,candidate_frozen=read('SELECTION_FREEZE')['selected_candidate'] if stage=='exposed' else None)
        f=features(t);hist=history(t);assert not set(hist.job_uid)&set(f.job_uid)
        membership=check_membership(t,hist,previous_t,previous_ids)
        path=OUT/'membership'/f'{k}.parquet';path.parent.mkdir(exist_ok=True);assert not path.exists()
        hist.to_parquet(path,index=False);membership['training_library_hash']=file_sha(path)
        packages={};preds={};issue_clock=time.perf_counter()
        for track in ['P','PW']:
            package=OUT/'models'/k/track
            event(t,'FIT_BEGIN',track=track,training_ids=ids(hist.job_uid),N=len(hist))
            packages[track]=build(hist,t,track,package)
            event(t,'FIT_COMPLETE',track=track,package_hash=packages[track]['package_SHA256'])
            preds[track]=save_prediction(t,track,f,package)
        # Both primary and sensitivity are sealed before a label is materialized.
        if t.isoformat() in repeats:
            rp=OUT/'repeats'/k
            repeat=build(hist,t,'P',rp);rr,rq,rs,_=predict(rp,f)
            comparisons={}
            for i,a in enumerate(QUANTILES):
                diff=np.abs(preds['P'][f'Q{int(a*100)}'].to_numpy()-rq[:,i]);comparisons[f'Q{int(a*100)}']=dict(max_difference=float(diff.max()),mean_difference=float(diff.mean()))
            for name,other in [('sigma',rs),('UARP',uarp(rq[:,3],rs))]:
                expected=preds['P']['sigma' if name=='sigma' else 'R5_UARP_STYLE'].to_numpy();delta=np.abs(expected-other)
                comparisons[name]=dict(max_difference=float(delta.max()),mean_difference=float(delta.mean()))
            assert repeat['package_SHA256']==packages['P']['package_SHA256']
            assert all(v['max_difference']==0 for v in comparisons.values())
            dump(rp/'comparison.json',dict(issue_time=t,status='PASS',compare=comparisons,package_hash_equal=True,better_repeat_selected=False))
            event(t,'REPEAT_VERIFIED',compare=comparisons,package_hash_equal=True)
            historical_permutation(hist,t,OUT/'models'/k/'P',OUT/'permutation'/k)
            event(t,'HISTORICAL_PERMUTATION_COMPLETE',future_labels_used=0)
        y=labels(t)
        for track in ['P','PW']:score_issue(t,track,preds[track],y,membership)
        event(t,'SCORE_COMPLETE',N=len(f),tracks=['P','PW'])
        event(t,'ISSUE_COMPLETE',seconds=time.perf_counter()-issue_clock)
        done=pd.concat([done,pd.DataFrame([membership])],ignore_index=True)
        done.to_parquet(OUT/f'{PREFIX}DAILY_TRAINING_LEDGER.parquet',index=False)
        previous_t=t;previous_ids=hist.job_uid.tolist()
        print(json.dumps(dict(stage=stage,issue=t.isoformat(),N_train=len(hist),new_jobs=membership['new_jobs_added_since_previous_issue'],N_eval=len(f),
          issue_seconds=round(time.perf_counter()-issue_clock,2),completed_total=len(done))),flush=True)
    if stage=='development':
        results={track:aggregate(track,ROLES[:3]) for track in ['P','PW']}
        selected=choose(results['P']['results'],results['P']['gates'])
        write('DEV_CAL_RESULTS',results)
        write('SELECTION_FREEZE',dict(timestamp=now(),selected_candidate=selected,selected_model=selected,track='P',
          config_id=model_config()[0],config=model_config()[1],fixed_parameters=FIXED,UARP_coefficients=[.2,.5],
          selection_roles=['DEVELOPMENT','CALIBRATION'],gates=results['P']['gates'],training_policy='ALL_CAUSALLY_MATURE_EXPANDING_HISTORY',
          preprocessing_policy='Exact S5 transformation, per-origin historical-only fit',residual_policy=read('PREREGISTRATION')['residual'],
          preregistration_SHA256=file_sha(OUT/f'{PREFIX}PREREGISTRATION.json'),EXPOSED_started=False))
        print('SELECTION '+str(selected),flush=True)
    else:
        results={track:aggregate(track,['EXPOSED_EVALUATION']) for track in ['P','PW']}
        selected=read('SELECTION_FREEZE')['selected_candidate'];p=results['P'];g=p['gates']['EXPOSED_EVALUATION']
        selected_pass=selected is not None and g[selected]['eligible']
        dc=read('DEV_CAL_RESULTS')['P']['gates']
        safety_pair=any(all(dc[r][c]['safety'] for r in ['DEVELOPMENT','CALIBRATION']) for c in CANDIDATES[2:])
        if selected_pass:classification='V40S5R1_ROLLING_UNCERTAINTY_RUNTIME_PREVALIDATED'
        elif selected is not None:classification='V40S5R1_ROLLING_DIRECT_RUNTIME_SAFETY_FAIL' if not g[selected]['safety'] else 'V40S5R1_RUNTIME_EFFICIENCY_FAIL'
        else:classification='V40S5R1_RUNTIME_EFFICIENCY_FAIL' if safety_pair else 'V40S5R1_ROLLING_DIRECT_RUNTIME_SAFETY_FAIL'
        write('EXPOSED_RESULTS',dict(timestamp=now(),selected_candidate=selected,selected_pass=bool(selected_pass),classification=classification,
          tracks=results,TRUE_CONFIRMATORY_AVAILABLE='NO',evidence='EXPOSED PREQUENTIAL HISTORICAL EVIDENCE',candidate_reselection=False))
        write('FINAL_DECISION',dict(classification=classification,selected_candidate=selected,prevalidated=bool(selected_pass),CURRENT_RSP_REPLACED='NO',
          optimizer_integration='NO',production_ready='NO',recommended_operational_runtime='CURRENT_RSP',FURTHER_RUNTIME_MODEL_PROLIFERATION='NO',
          FURTHER_RUNTIME_MODEL_WORK='INTEGRATION_AND_SHADOW_VALIDATION_REQUIRED' if selected_pass else 'DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA',holds=HOLDS))
        print(json.dumps(dict(classification=classification,selected=selected,gates=g)),flush=True)

if __name__=='__main__':run(sys.argv[1])
