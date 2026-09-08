"""Staged proxy fits, CAL-only eta and read-only runtime replay."""
import pickle
import time
import sys
from .common import *
from dayahead.v40s3.contracts import slots,metrics


def cap(prevalence):return .6 if prevalence<=.6 else min(.8,prevalence+.2)


def eta_select(t,g,q,prob,u,*,role):
    if role!='CALIBRATION':raise ValueError('CALIBRATION_ONLY')
    t,g,q,prob=map(np.asarray,(t,g,q,prob));y=t>u;mass=g*np.maximum(t-q,0)
    if len(t)<100 or y.sum()<100 or mass.sum()<=0:return None
    if not np.isfinite(prob).all() or (prob<0).any() or (prob>1).any():raise ValueError('INVALID_PROBABILITY')
    for eta in np.unique(np.r_[0.,prob,1.])[::-1]:
        flag=prob>=eta
        if flag[y].mean()>=.9 and g[flag&y].sum()/g[y].sum()>=.9 and mass[flag].sum()/mass.sum()>=.8 and flag.mean()<=cap(y.mean()):return float(eta)
    return None


def duration(body,flag,ref,rw,u,policy):
    body,ref,rw=map(np.asarray,(body,ref,rw));flag=np.asarray(flag)
    if flag.dtype!=bool or not (body.shape==ref.shape==rw.shape==flag.shape):raise ValueError('ROW_ALIGNMENT')
    if policy not in ('R0','R1','R2'):raise ValueError('UNREGISTERED_POLICY')
    fallback=ref if policy=='R0' else np.maximum(ref,u) if policy=='R1' else rw
    a=np.where(flag,fallback,body)
    if not np.isfinite(a).all() or (a<=0).any():raise ValueError('INVALID_DURATION')
    return a


def fit_models(track,h,tr,pre,probe):
    import lightgbm as lgb
    import xgboost as xgb
    from sklearn.linear_model import LogisticRegression
    d=tr[tr.runtime_seconds<=h*3600];x=pre.transform(d);y=d.runtime_seconds.to_numpy();probe_x=pre.transform(probe)
    models={};audit=[]
    for name in ('B1','B2'):
        models[name]=[]
        for alpha in (.5,.9):
            def make():return lgb.LGBMRegressor(objective='quantile',alpha=alpha,**LGB) if name=='B1' else xgb.XGBRegressor(objective='reg:quantileerror',quantile_alpha=alpha,**XGB)
            started=time.perf_counter();a=make().fit(x,y);b=make().fit(x,y);fit_time=time.perf_counter()-started
            started=time.perf_counter();pa=a.predict(probe_x);pb=b.predict(probe_x);predict_time=time.perf_counter()-started
            diff=np.abs(pa-pb);assert pa.tobytes()==pb.tobytes(),'REPEAT_MISMATCH_NO_BETTER_REPEAT_SELECTION'
            audit.append(dict(track=track,u_hours=h,model=name,alpha=alpha,train_N=len(d),train_ID_SHA256=ids(d),max_training_end=d.end_time.max().isoformat(),fit_seconds=fit_time,inference_seconds=predict_time,probe_N=len(probe),max_difference=float(diff.max()),mean_difference=float(diff.mean()),byte_equal=True))
            models[name].append(a)
    models['B3']=np.quantile(y,[.5,.9],method='linear')
    x=pre.transform(tr);y=tr.runtime_seconds.gt(h*3600).astype(int).to_numpy()
    models['C0']=float(y.mean())
    for name in ('C1','C2','C3'):
        def make():
            if name=='C1':return LogisticRegression(C=1,solver='lbfgs',max_iter=1000,random_state=SEED)
            if name=='C2':return lgb.LGBMClassifier(objective='binary',**LGB)
            return xgb.XGBClassifier(objective='binary:logistic',eval_metric='logloss',**XGB)
        started=time.perf_counter();a=make().fit(x,y);b=make().fit(x,y);fit_time=time.perf_counter()-started
        started=time.perf_counter();pa=a.predict_proba(probe_x)[:,1];pb=b.predict_proba(probe_x)[:,1];predict_time=time.perf_counter()-started
        diff=np.abs(pa-pb);assert pa.tobytes()==pb.tobytes(),'REPEAT_MISMATCH_NO_BETTER_REPEAT_SELECTION'
        audit.append(dict(track=track,u_hours=h,model=name,train_N=len(tr),train_ID_SHA256=ids(tr),max_training_end=tr.end_time.max().isoformat(),fit_seconds=fit_time,inference_seconds=predict_time,probe_N=len(probe),max_difference=float(diff.max()),mean_difference=float(diff.mean()),byte_equal=True))
        models[name]=a
    return models,audit


def predict(models,pre,d):
    x=pre.transform(d);out={};cr={}
    out['B0']=np.column_stack([np.maximum(d.K0.to_numpy(),1),d.reference_safe_sec])
    for n in ('B1','B2','B3'):
        a=np.column_stack([m.predict(x) for m in models[n]]) if n!='B3' else np.tile(models[n],(len(d),1))
        assert np.isfinite(a).all()
        cr[n]=dict(raw_crossings=int((a[:,0]>a[:,1]).sum()),nonpositive=int((a<=0).sum()))
        out[n]=np.maximum(np.sort(a,axis=1),1.)
    for c in ('C0','C1','C2','C3'):
        out[c]=np.full(len(d),models[c]) if c=='C0' else models[c].predict_proba(x)[:,1]
    return out,cr


def body_scores(d,pred,h,track):
    rows=[];t=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy()
    masks=[('OVERALL',np.ones(len(d),bool)),*[(day,d.issue_day.eq(day).to_numpy()) for day in sorted(d.issue_day.unique())],
           ('GPU_1',g==1),('GPU_2_4',(g>=2)&(g<=4)),('GPU_5_PLUS',g>=5)]
    for n in ('B0','B1','B2','B3'):
        for group,m in masks:
            m=m & (t<=h*3600)
            if not m.any():continue
            z=metrics(t[m],pred[n][m,1],g[m]);mae=np.abs(t[m]-pred[n][m,0])
            low=.9 if group=='OVERALL' else .88
            upper=.95 if group=='OVERALL' else 1.
            z.update(track=track,role=d.role.iloc[0],u_hours=h,body=n,group=group,Q50_MAE_sec=float(mae.mean()),Q50_WAPE=float(mae.sum()/t[m].sum()),Q50_pinball=float(mae.mean()/2),
               raw_Q90_MAE_sec=z['MAE_sec'],overconservative_warning=z['coverage']>.975,
               coverage_gate='INSUFFICIENT_SUPPORT' if z['N']<100 else 'PASS' if low<=z['coverage']<=upper else 'FAIL',
               GPU_gate='INSUFFICIENT_SUPPORT' if z['N']<100 else 'PASS' if z['GPU_coverage']>=low else 'FAIL',coverage_min=low,coverage_max=upper)
            rows.append(z)
    return rows


def tail_metrics(d,prob,q,h,eta):
    from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
    t=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy();y=t>h*3600
    binid=np.minimum((prob*10).astype(int),9)
    ece=sum(np.mean(binid==i)*abs(prob[binid==i].mean()-y[binid==i].mean()) for i in range(10) if (binid==i).any())
    out=dict(N=len(d),tail_N=int(y.sum()),prevalence=float(y.mean()),ROC_AUC=float(roc_auc_score(y,prob)) if len(np.unique(y))==2 else None,
         PR_AUC=float(average_precision_score(y,prob)) if y.any() else None,Brier=float(brier_score_loss(y,prob)),ECE=float(ece),eta=eta,selectivity_limit=cap(y.mean()))
    if eta is None:
        out.update(recall=None,precision=None,specificity=None,FNR=None,FPR=None,GPU_recall=None,GPU_FNR=None,mass_capture=None,flagged_fraction=None)
    else:
        flag=prob>=eta;mass=g*np.maximum(t-q,0);recall=float(flag[y].mean()) if y.any() else None
        grec=float(g[flag&y].sum()/g[y].sum()) if y.any() else None
        spec=float((~flag[~y]).mean()) if (~y).any() else None
        out.update(recall=recall,precision=float(y[flag].mean()) if flag.any() else None,specificity=spec,FNR=1-recall if recall is not None else None,
                   FPR=1-spec if spec is not None else None,GPU_recall=grec,GPU_FNR=1-grec if grec is not None else None,mass_capture=float(mass[flag].sum()/mass.sum()) if mass.sum() else None,flagged_fraction=float(flag.mean()))
    return out


def ratio(a,b):return a/b if b else (0. if a==0 else None)


def replay(d,q,prob,h,eta,policy):
    if eta is None:return None
    flag=prob>=eta
    raw=duration(q,flag,d.reference_safe_sec,d.requested_seconds,h*3600,policy)
    aligned=slots(raw)*900;t=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy()
    m=metrics(t,aligned,g);ref=metrics(t,slots(d.reference_safe_sec)*900,g);rw=metrics(t,slots(d.requested_seconds)*900,g)
    m.update(raw_coverage=float(np.mean(t<=raw)),underpredicted_job_count=int((t>aligned).sum()),flagged_fraction=float(flag.mean()),fallback_use_rate=float(flag.mean()),full_denominator=len(d),
       body_miss_sec=float(np.maximum(t-aligned,0)[~flag].sum()),tail_miss_sec=float(np.maximum(t-aligned,0)[flag].sum()),
       reference=ref,RW=rw,GPU_mass_ratio=ratio(m['GPU_underprediction_sec'],ref['GPU_underprediction_sec']),overreservation_ratio=ratio(m['overreservation_GPU_hours'],ref['overreservation_GPU_hours']),
       GPU_mass_delta_vs_reference=m['GPU_underprediction_sec']-ref['GPU_underprediction_sec'],GPU_mass_delta_vs_RW=m['GPU_underprediction_sec']-rw['GPU_underprediction_sec'],
       overreservation_delta_vs_reference=m['overreservation_GPU_hours']-ref['overreservation_GPU_hours'])
    return m


def evaluate_gate(bodyrows,tail,hybrid,daily):
    relevant=[r for r in bodyrows if r['group']=='OVERALL' or (not r['group'].startswith('GPU') and r['N']>=100)]
    body=bool(relevant) and all(r['coverage_gate']=='PASS' and r['GPU_gate']=='PASS' for r in relevant)
    detection=tail['eta'] is not None and tail['N']>=100 and tail['tail_N']>=100 and tail['recall']>=.9 and tail['GPU_recall']>=.9 and tail['mass_capture'] is not None and tail['mass_capture']>=.8
    selectivity=tail['eta'] is not None and tail['flagged_fraction']<=tail['selectivity_limit']
    hs=hybrid is not None and hybrid['coverage']>=.9 and hybrid['GPU_coverage']>=.9
    improve=hybrid is not None and hybrid['GPU_mass_ratio'] is not None and hybrid['GPU_mass_ratio']<1.
    reserve=hybrid is not None and hybrid['overreservation_ratio'] is not None and hybrid['overreservation_ratio']<=3.
    temporal=bool(daily) and all(z['coverage']>=.85 and z['GPU_coverage']>=.85 and z['overreservation_ratio'] is not None and z['overreservation_ratio']<=3. for z in daily)
    return dict(body=body,tail=detection,selectivity=selectivity,hybrid_coverage=hs,underprediction_improvement=improve,overreservation=reserve,temporal=temporal,
       PASS=body and detection and selectivity and hs and improve and reserve and temporal)


def fit_or_evaluate(stage):
    preg=guard_prereg();p=panel();tr=p[p.role=='TRAIN'].reset_index(drop=True)
    fit=stage=='fit';roles=['DEVELOPMENT','CALIBRATION'] if fit else ['EXPOSED_EVALUATION']
    if fit:assert not (OUT/'V40S4_DEV_CAL_RESULTS.json').exists(),'NO_RETRAIN'
    else:
        receipt=get('METHOD_SELECTION_COMMIT_RECEIPT');c=receipt['commit'];s='dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_METHOD_SELECTION.json'
        assert git('show',f'{c}:{s}',binary=True)==(ROOT/s).read_bytes()
        assert not (OUT/'V40S4_EXPOSED_RESULTS.json').exists(),'NO_EXPOSED_REUSE'
    modeldir=OUT/'models';modeldir.mkdir(exist_ok=True)
    records=[];brows=[];trows=[];audits=[];etas=[];cross=[];times=[]
    for track in ('P','PW'):
        pre=Preprocess(track).fit(tr)
        assert pre.descriptor()==get('PROXY_FEATURE_PREPROCESSING_CONTRACT')['descriptors'][track]
        for h in U:
            path=modeldir/f'{track}_u{h}.pkl'
            if fit:
                probe=p[p.role.isin(['TRAIN','DEVELOPMENT','CALIBRATION'])]
                model,audit=fit_models(track,h,tr,pre,probe);audits.extend(audit)
                path.write_bytes(pickle.dumps(dict(model=model,preprocess=pre),protocol=5))
            else:
                assert sha(path.read_bytes())==get('MODEL_FREEZE')['model_SHA256'][path.name]
                obj=pickle.loads(path.read_bytes());model=obj['model'];pre=obj['preprocess']
            if fit:
                cal=p[p.role=='CALIBRATION'].reset_index(drop=True);started=time.perf_counter();cp,_=predict(model,pre,cal)
                times.append(dict(track=track,u_hours=h,role='CALIBRATION_ETA_PREDICTION',N=len(cal),seconds=time.perf_counter()-started))
                eta_values={}
                for body in ('B0','B1','B2','B3'):
                    for c in ('C0','C1','C2','C3'):
                        eta=eta_select(cal.runtime_seconds,cal.num_gpus_req,cp[body][:,1],cp[c],h*3600,role='CALIBRATION')
                        eta_values[body,c]=eta
                        etas.append(dict(track=track,u_hours=h,body=body,classifier=c,eta=eta,source_role='CALIBRATION',cal_ID_SHA256=ids(cal),
                                         metrics=tail_metrics(cal,cp[c],cp[body][:,1],h,eta)))
            else:eta_values={(r['body'],r['classifier']):r['eta'] for r in get('ETA_SELECTION')['rows'] if r['track']==track and r['u_hours']==h}
            for role in roles:
                d=p[p.role==role].reset_index(drop=True);started=time.perf_counter();pred,cr=predict(model,pre,d);times.append(dict(track=track,u_hours=h,role=role,N=len(d),seconds=time.perf_counter()-started))
                cross.append(dict(track=track,u_hours=h,role=role,counts=cr));bp=body_scores(d,pred,h,track);brows.extend(bp)
                df=d[['job_issue_uid','job_id','issue_time','role']].copy()
                for b in ('B0','B1','B2','B3'):df[b+'_Q50']=pred[b][:,0];df[b+'_Q90']=pred[b][:,1]
                for c in ('C0','C1','C2','C3'):df[c+'_p_tail']=pred[c]
                df.to_parquet(OUT/f'V40S4_PREDICTIONS_{track}_u{h}_{role}.parquet',index=False)
                for body in ('B0','B1','B2','B3'):
                    for c in ('C0','C1','C2','C3'):
                        eta=eta_values[body,c];tail=tail_metrics(d,pred[c],pred[body][:,1],h,eta)
                        trows.append(dict(track=track,u_hours=h,body=body,classifier=c,role=role,**tail))
                        for policy in ('R0','R1','R2'):
                            m=replay(d,pred[body][:,1],pred[c],h,eta,policy);days=[]
                            if eta is not None:
                                for day,idx in d.groupby('issue_day').groups.items():
                                    ix=np.asarray(list(idx))
                                    if len(ix)>=100:
                                        daym=replay(d.iloc[ix],pred[body][ix,1],pred[c][ix],h,eta,policy);daym['issue_day']=day;days.append(daym)
                            gs=evaluate_gate([r for r in bp if r['body']==body],tail,m,days)
                            if body=='B0':gs['PASS']=False;gs['reference_only']=True
                            records.append(dict(track=track,u_hours=h,body=body,classifier=c,policy=policy,role=role,tail=tail,hybrid=m,daily=days,gates=gs))
            print(stage,track,h,'done',flush=True)
    name='DEV_CAL_RESULTS' if fit else 'EXPOSED_RESULTS'
    write(name,dict(preregistration_commit=preg,records=records,body=brows,tail=trows,crossings=cross,inference_times=times,
                   role='ASSUMPTION_BASED_OPERATIONAL_PROXY / WALLTIME_DEPENDENCE_SENSITIVITY',not_historical_snapshot_ground_truth=True))
    if fit:
        write('ETA_SELECTION',dict(rule=get('PREREGISTRATION')['eta_rule'],rows=etas,selected_eta=None))
        write('COMPUTE_LEDGER',dict(timestamp=now(),Python=sys.version,device='CPU',threads=1,seed=SEED,
           libraries=get('PREREGISTRATION')['compute']['versions'],fits=audits,primary_fits=70,independent_repeat_fits=70,
           constant_body_fits=10,constant_classifier_fits=10,total_fit_seconds=sum(r['fit_seconds'] for r in audits),inference_times=times,optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0))
        write('REPRODUCIBILITY_AUDIT',dict(status='PASS',independent_same_seed_pairs=len(audits),all_byte_equal=all(r['byte_equal'] for r in audits),
           max_prediction_difference=max(r['max_difference'] for r in audits),mean_prediction_difference=0.,probe_scope='TRAIN+DEV+CAL only, no exposed scoring before selection',rows=audits))
        write('MODEL_FREEZE',dict(preregistration_commit=preg,model_SHA256={v.name:sha(v.read_bytes()) for v in modeldir.glob('*.pkl')},refit_after_selection=False))
        choose(records,brows)
    print(name,'COMPLETE',flush=True)


def choose(records,brows):
    eligible=[];body_exists=False;tail_exists=False
    for track in ('P','PW'):
        for h in U:
            for body in ('B1','B2','B3'):
                rows=[r for r in records if r['track']==track and r['u_hours']==h and r['body']==body]
                byrole={r:any(z['gates']['body'] for z in rows if z['role']==r) for r in ('DEVELOPMENT','CALIBRATION')}
                body_exists |= all(byrole.values())
                for c in ('C0','C1','C2','C3'):
                    for policy in ('R0','R1','R2'):
                        rr=[r for r in rows if r['classifier']==c and r['policy']==policy]
                        tail_exists |= len(rr)==2 and all(r['gates']['body'] and r['gates']['tail'] and r['gates']['selectivity'] for r in rr)
                        if len(rr)==2 and all(r['gates']['PASS'] for r in rr):
                            br=[r for r in brows if r['track']==track and r['u_hours']==h and r['body']==body and r['group']=='OVERALL']
                            eligible.append(dict(track=track,u_hours=h,body=body,classifier=c,policy=policy,
                              overreservation_GPU_hours=sum(r['hybrid']['overreservation_GPU_hours'] for r in rr),
                              body_Q50_MAE=sum(r['Q50_MAE_sec']*r['N'] for r in br)/sum(r['N'] for r in br),
                              eta=next(r['tail']['eta'] for r in rr if r['role']=='CALIBRATION')))
    def key(r):return (r['overreservation_GPU_hours'],r['body_Q50_MAE'],['B3','B1','B2'].index(r['body']),r['classifier'],-r['u_hours'],r['policy'],0 if r['track']=='PW' else 1)
    eligible.sort(key=key)
    winners={t:next((r for r in eligible if r['track']==t),None) for t in ('P','PW')}
    winner=eligible[0] if eligible else None
    failure='V40S4_PROXY_BODY_RUNTIME_INSUFFICIENT' if not body_exists else 'V40S4_PROXY_TAIL_DETECTION_FAIL' if not tail_exists else 'V40S4_PROXY_HYBRID_RUNTIME_SAFETY_FAIL'
    write('METHOD_SELECTION',dict(timestamp=now(),selected=winner,per_track=winners,eligible_count=len(eligible),eligible=eligible,
       body_safe_pair_exists=bool(body_exists),body_tail_selective_pair_exists=bool(tail_exists),classification_before_exposed='PENDING_EXPOSED_SAFETY' if winner else failure,
       selection_roles=['DEVELOPMENT','CALIBRATION'],EXPOSED_EVALUATION_scored=False,shadow='SEALED',S3_result_unchanged=True))
    eta_artifact=get('ETA_SELECTION');eta_artifact['selected_eta']=winner['eta'] if winner else None
    write('ETA_SELECTION',eta_artifact)


if __name__=='__main__':fit_or_evaluate(sys.argv[1])
