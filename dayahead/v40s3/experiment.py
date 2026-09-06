"""Amended strict-clock experiment, staged around committed freezes.

Historical start/end are used only for the user-authorized issue membership,
label availability and service labels. They never enter predictor matrices.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib
import pickle
import time
import sys
import shutil
import importlib.metadata
import numpy as np
import pandas as pd
from .audit import ROOT, REF, OUT, BASE, S2, HOLDS, git, sha, write
from .contracts import U_HOURS, Q, FIELDS, positive, slots, baseline_safe, metrics, select_eta, hybrid

PREFIX='dayahead/artifacts/v40s3_body_tail_runtime_risk/'
SOURCE=REF/'dayahead/artifacts/v40q_regime_conditioned_tail/clean_execution_01/PREPARED_ROWS.parquet'
SOURCE_SHA='fed0270c4e90362bc97b3583d92bfc6e00d6083297ee502b098e08896e086df9'
SEED=4003
BOUNDS={'TRAIN':('2025-03-14T08:00Z','2025-03-22T08:00Z'),
        'DEVELOPMENT':('2025-03-22T08:00Z','2025-04-01T08:00Z'),
        'CALIBRATION':('2025-04-01T08:00Z','2025-04-08T08:00Z'),
        'EXPOSED_EVALUATION':('2025-04-08T08:00Z','2025-04-24T00:00Z')}
LGB=dict(n_estimators=100,num_leaves=7,max_depth=3,learning_rate=.05,min_child_samples=50,
         n_jobs=1,random_state=SEED,deterministic=True,force_col_wise=True,verbosity=-1)
XGB=dict(n_estimators=100,max_depth=3,learning_rate=.05,min_child_weight=20,n_jobs=1,
         random_state=SEED,tree_method='hist',device='cpu',subsample=1.,colsample_bytree=1.)


def get(name):
    return json.loads((OUT/f'V40S3_{name}.json').read_text(encoding='utf-8'))


def idsha(f):
    return sha(('\n'.join(sorted(f.job_issue_uid))+'\n').encode())


def load_panel():
    p=OUT/'V40S3_PENDING_ISSUE_PANEL.parquet'
    expected=get('POPULATION_AUDIT')['panel_SHA256']
    assert sha(p.read_bytes())==expected
    return pd.read_parquet(p)


def prereg_guard():
    receipt=get('PREREGISTRATION_COMMIT_RECEIPT')
    assert git('show',f"{receipt['commit']}:{PREFIX}V40S3_PREREGISTRATION.json",binary=True)==(OUT/'V40S3_PREREGISTRATION.json').read_bytes()
    assert get('PREREGISTRATION')['phase']=='STRICT_CLOCK_EXECUTION_AFTER_USER_AMENDMENT'
    return receipt['commit']


def prepare():
    assert not (OUT/'models').exists(), 'NO_MODEL_RESULTS_BEFORE_AMENDMENT'
    # Preserve the initial, explicitly superseded authority conclusion in full.
    archived=OUT/'superseded_membership_authority_stop'
    archived.mkdir(exist_ok=True)
    for p in OUT.glob('V40S3_*'):
        if p.is_file(): shutil.copy2(p,archived/p.name)
    prior_head=git('rev-parse','HEAD')
    amendment=dict(timestamp=datetime.now(timezone.utc).isoformat(),source='User V40S3 progress correction in this conversation',
      previous_commit=prior_head,original_rule='Missing contemporaneous saved snapshot blocks reconstructed PENDING population',
      corrected_rule='Normative scheduler reconstruction admitted: submit<=issue; pending start>issue or missing; end>issue. Predictor features still only submit_hour/weekday.',
      scientific_impact='Reopens strict causal-clock body/tail experiment. Reconstructed membership is accepted current authority, not claimed to be independently observed.',
      previously_observed='Prior revision reports and V40S3 March archived baseline oracle diagnostics only',
      new_model_fit_count_before_change=0,new_prediction_count_before_change=0,new_candidate_ranking_observed=False,
      final_shadow_opened=False,original_feature_provenance_restrictions_preserved=True,
      original_artifacts='superseded_membership_authority_stop/',
      reason='Explicit user correction, not favorable adaptation to new model results')
    write('PREREGISTRATION_AMENDMENT_01',amendment)
    f=pd.read_parquet(SOURCE,columns=['job_id','submit_time','start_time','end_time','runtime_seconds','num_gpus_req',
                                     'requested_seconds','submit_hour','submit_dow','K0','source_period','nominal_source_SHA'])
    assert sha(SOURCE.read_bytes())==SOURCE_SHA
    for c in ('submit_time','start_time','end_time'):
        f[c]=pd.to_datetime(f[c],utc=True)
        assert f[c].notna().all() and f[c].lt(pd.Timestamp('2025-04-24T00:00Z')).all()
    assert len(f)==73504 and not f.job_id.duplicated().any()
    assert np.array_equal(f.runtime_seconds,(f.end_time-f.start_time).dt.total_seconds())
    assert f.runtime_seconds.eq(0).sum()==1212
    allpositive=f[f.runtime_seconds>0].copy()
    assert len(allpositive)==72292
    parts=[];counts=[]
    for role,(lo,hi) in BOUNDS.items():
        for issue in pd.date_range(pd.Timestamp(lo),pd.Timestamp(hi),freq='D',inclusive='left'):
            pending=allpositive.submit_time.le(issue)&allpositive.start_time.gt(issue)&allpositive.end_time.gt(issue)
            running=allpositive.submit_time.le(issue)&allpositive.start_time.le(issue)&allpositive.end_time.gt(issue)
            assert not (pending & running).any()
            m=pending & allpositive.end_time.lt(pd.Timestamp(hi))
            d=allpositive[m].copy();d['issue_time']=issue;d['role']=role;d['state_at_issue']='PENDING'
            d['job_issue_uid']=d.job_id.astype(str)+'@'+issue.isoformat()
            d['issue_day']=issue.strftime('%Y-%m-%d')
            parts.append(d)
            counts.append(dict(role=role,issue_time=issue.isoformat(),pending_positive_before_end_known=int(pending.sum()),
                               rejected_label_not_known_by_next_stage=int((pending & ~m).sum()),accepted=len(d)))
    p=pd.concat(parts,ignore_index=True)
    assert not p.job_issue_uid.duplicated().any()
    assert np.array_equal(p.submit_hour,p.submit_time.dt.hour) and np.array_equal(p.submit_dow,p.submit_time.dt.dayofweek)
    # Historical C0_F3 and April K0 are read-only current-recipe comparators.
    # They are not falsely identified as the unserialized production Apr01 state.
    p['reference_safe_sec']=baseline_safe(p.K0,p.requested_seconds)
    p['reference_slots']=slots(p.reference_safe_sec)
    p['RW_slots']=slots(p.requested_seconds)
    p.to_parquet(OUT/'V40S3_PENDING_ISSUE_PANEL.parquet',index=False)
    oldpop=get('POPULATION_AUDIT')
    oldpop.update(PENDING_N=len(p),PENDING_unique_jobs=int(p.job_id.nunique()),
                  PENDING_N_reason='Accepted normative historical issue reconstruction; repeated jobs at distinct daily issues retained',
                  membership_authority='PASS_NORMATIVE_RECONSTRUCTION_USER_CONFIRMED',
                  panel_SHA256=sha((OUT/'V40S3_PENDING_ISSUE_PANEL.parquet').read_bytes()),
                  source_SHA256=SOURCE_SHA,issue_counts=counts,
                  block_population={r:dict(N=len(d),unique_jobs=int(d.job_id.nunique()),ID_SHA256=idsha(d),max_label_end=d.end_time.max().isoformat()) for r,d in p.groupby('role')},
                  cohort_limit='Only previously exposed terminal-event positive-service source; missing/incomplete jobs and raw-rowgroup exclusions remain. No full-cluster PENDING census claim.')
    write('POPULATION_AUDIT',oldpop)
    fa=get('FEATURE_AUTHORITY_AUDIT');fa.update(status='PASS_STRICT_CLOCK_ONLY',historical_PENDING_count=len(p),
       independent_D1_PENDING_snapshot='NOT_REQUIRED_FOR_USER_AUTHORIZED_NORMATIVE_RECONSTRUCTION',
       causal_training_population='RECONSTRUCTED_PENDING_JOB_ISSUE_ROWS',
       finding='Membership reconstruction admitted by current normative authority; resource-feature edit provenance remains absent.')
    for r in fa['features']:
        if r['feature'] in ('submit_hour','weekday'):
            r.update(admission_decision='ADMITTED_STRICT_CAUSAL_CLOCK',current_D1_authority='recorded submit<=issue, UTC hour/day derived exactly')
    write('FEATURE_AUTHORITY_AUDIT',fa)
    write('CAUSAL_FEATURE_CONTRACT',dict(status='PASS_STRICT_CLOCK_ONLY',admitted_model_features=['submit_hour','weekday'],
       predictor_matrix_columns=['submit_hour','submit_dow'],
       available_at='recorded submission episode; submit_time <= issue_time verified',
       membership_only=['submit_time','start_time','end_time'],
       labels_only=['runtime_seconds','end_time-start_time'],
       evaluation_weights_only=['num_gpus_req'],existing_comparators_only=['K0','requested_seconds'],
       rejected_predictors=[r['feature'] for r in fa['features'] if r['feature'] not in ('submit_hour','weekday')],
       original_submit_vs_episode='Recorded episode clock; no promotion of unproven request versions or first-attempt linkage',
       support_calculation='No support predictor used',new_proxy_track=False))
    write('RUNTIME_LABEL_CONTRACT',dict(target='end-start seconds',exact_S2_identity=True,original_N=73504,positive_N=72292,
       zero_N=1212,negative_N=0,missing_start_end_N=0,duplicate_job_id_N=0,
       zero_rule='Retained in original identity audit, explicitly excluded from all new candidate rows',
       terminal_status='UNAVAILABLE success status; terminal service events, not COMPLETED-only',
       membership='start/end permitted only for normative historical issue membership and label availability',
       train_rule='end_time strictly before stage cutoff; all training ends < every DEV/CAL/EVAL issue time',
       censoring='No censored rows fabricated; incomplete terminal-source population caveat remains'))
    write('TEMPORAL_SPLIT_CONTRACT',dict(timezone='fixed AEST UTC+10; issue 18:00 local =08:00 UTC',
       blocks=BOUNDS,split_axis='issue_time half-open interval; end_time strictly before next stage cutoff',
       rows='one job per daily issue; repeated issue exposure retained, no random split',
       final_shadow_cutoff='2025-04-24T00:00:00Z',canonical_preMay_local='2025-05-01T00:00:00+10:00',
       canonical_preMay_UTC='2025-04-30T14:00:00Z',
       block_counts=oldpop['block_population'],no_random_split=True,
       selection='DEV+CAL only; freeze method before EXPOSED_EVALUATION scoring; no refit after selection'))
    # Phase A on reconstructed PENDING rows, only TRAIN and DEVELOPMENT.
    train=p[p.role=='TRAIN'];dev=p[p.role=='DEVELOPMENT'];rows=[];bm=[]
    t=dev.runtime_seconds.to_numpy();s=dev.reference_safe_sec.to_numpy();g=dev.num_gpus_req.to_numpy();e=np.maximum(t-s,0);mass=g*e
    for h in U_HOURS:
        b=t<=h*3600;tail=~b
        z=metrics(t[b],s[b],g[b])
        r=dict(u_hours=h,u_sec=h*3600,TRAIN_N=len(train),TRAIN_percentile=float(train.runtime_seconds.le(h*3600).mean()*100),
          DEVELOPMENT_N=len(dev),tail_N=int(tail.sum()),body_N=int(b.sum()),tail_prevalence=float(tail.mean()),
          tail_requested_GPU_fraction=float(g[tail].sum()/g.sum()),tail_runtime_hours_fraction=float(t[tail].sum()/t.sum()),
          tail_positive_error_mass_fraction=float(e[tail].sum()/e.sum()),tail_GPU_positive_error_mass_fraction=float(mass[tail].sum()/mass.sum()),
          body_reference_safe_coverage=z['coverage'],body_reference_GPU_coverage=z['GPU_coverage'],body_reference_safe_MAE_sec=z['MAE_sec'],
          body_reference_safe_WAPE=z['WAPE'],body_reference_underprediction_rate=z['underprediction_rate'],body_GPU_underprediction_sec=z['GPU_underprediction_sec'])
        for pct in (1,5,10):
            n=int(np.ceil(len(t)*pct/100))
            for label,v in [('positive',e),('GPU_positive',mass)]:
                ix=np.argsort(-v,kind='stable')[:n]
                r[f'worst_{pct}pct_{label}_mass_fraction']=float(v[ix].sum()/v.sum())
                r[f'tail_share_within_worst_{pct}pct_{label}_mass']=float(v[ix][tail[ix]].sum()/v[ix].sum())
        rows.append(r)
        for day,d in dev.groupby('issue_day'):
            q=d[d.runtime_seconds<=h*3600]
            if len(q):bm.append(dict(u_hours=h,day=day,**metrics(q.runtime_seconds,q.reference_safe_sec,q.num_gpus_req)))
    ranges=[]
    for lo,hi in [(0,4),(4,6),(6,8),(8,12),(12,24),(24,float('inf'))]:
        m=(t>lo*3600)&(t<=hi*3600)
        if m.any():ranges.append(dict(range_hours=f'({lo},{hi}]',N=int(m.sum()),GPU_mass_fraction=float(mass[m].sum()/mass.sum()),
            residual_SD_sec=float(np.std(t[m]-s[m])),residual_variance_sec2=float(np.var(t[m]-s[m]))))
    pd.DataFrame(rows).to_csv(OUT/'V40S3_THRESHOLD_FORENSIC.csv',index=False)
    write('THRESHOLD_FORENSIC',dict(status='RECONSTRUCTED_PENDING_TRAIN_DEVELOPMENT_ONLY',thresholds=rows,runtime_ranges=ranges,
          population=oldpop['block_population'],oracle_membership=True,baseline='Frozen current recipe C0_F3 historical / K0 April; not exact production final-state identity',
          q_caveat='Existing frozen q includes later March calibration; reference is descriptive, not new causal calibration evidence'))
    write('BODY_PREDICTABILITY_REPORT',dict(status='ORACLE_DIAGNOSTIC_BEFORE_NEW_FIT',thresholds=rows,by_temporal_block=bm,
          oracle_only=True,continuation_authority='User correction explicitly requests strict-clock D/E/F/G before concluding information insufficiency; baseline oracle failure does not stop this amended experiment'))
    write('PREREGISTRATION',dict(phase='STRICT_CLOCK_EXECUTION_AFTER_USER_AMENDMENT',timestamp=datetime.now(timezone.utc).isoformat(),
       amendment='V40S3_PREREGISTRATION_AMENDMENT_01.json',supersedes=prior_head,
       new_fit_before_commit=0,new_prediction_before_commit=0,new_candidate_ranking_observed=False,
       population=oldpop,feature_contract=get('CAUSAL_FEATURE_CONTRACT'),threshold_hours=U_HOURS,temporal_splits=get('TEMPORAL_SPLIT_CONTRACT'),
       body_registry=dict(B0='Archived current recipe reference ONLY; cannot win as new strict-clock body',
                          B1=dict(library='lightgbm',quantiles=[.5,.9],params=LGB),
                          B2=dict(library='xgboost',objective='reg:quantileerror',quantiles=[.5,.9],params=XGB),
                          B3='Global empirical linear TRAIN body quantiles Q50/Q90'),
       body_train='TRAIN T<=u only, no refit; predict every DEV/CAL/EVAL row; actual body filter used for oracle safety only',
       crossing_rule='Sort each new Q50/Q90 pair before use; disclose raw crossings; reference B0 unchanged',
       positivity='Numerical nonpositive new quantiles clipped to 1 second; positive labels only; no scheduler-floor in regression',
       tail_registry=dict(C0='TRAIN tail prevalence',C1='LogisticRegression C=1, lbfgs max_iter=1000; fixed one-hot hour24+weekday7; seed4003 n_jobs1',
                          C2=dict(library='lightgbm',objective='binary',params=LGB),
                          C3=dict(library='xgboost',objective='binary:logistic',params=XGB)),
       feature_matrix='Only recorded UTC submit_hour and weekday; fixed calendar one-hot for logistic; numeric for trees',
       calibration='Body C0: none. No reuse of old q in B1/B2/B3; classifier probabilities uncalibrated, ECE assessed.',
       eta='Largest CAL unique probability or 0/1 meeting recall and requested-GPU recall >=90%; tail N>=100,total N>=100; 95% sensitivity reported',
       eta_support_failure='No eta selected; R0/R1 replay metric null, never silently use .5 or all-tail fallback',
       robust_policies=dict(R0='Existing reference_safe_sec',R1='Existing requested_seconds; comparator only, not hard bound'),
       duration_alignment='ceil(seconds/900) exactly once for scheduler replay; raw coverage and 15min coverage separate',
       gates=dict(N_min=100,body_overall=.9,body_GPU=.9,body_daily=.88,body_upper_warning=.975,
                  tail_recall=.9,tail_GPU_recall=.9,mass_capture=.8,ECE_max=.05,
                  max_flagged_fraction=.8,hybrid_GPU_mass_ratio_strict_max=1.,major_daily_GPU_mass_ratio_max=1.05,
                  overreservation_ratio_max=2.,daily_overreservation_ratio_max=2.),
       overreservation_zero_rule='If current reserve=0, candidate reserve must be0; ratio not smoothed',
       ECE='10 equal-width probability bins [0,.1),...,[.9,1]; weighted by job-issue count; absolute bin mean error',
       metric_definitions='ROC-AUC, PR average_precision, Brier; threshold recall/precision/specificity/FNR and GPU recall/FNR; mass from g*max(T-bodyQ90,0)',
       selection='Gate every DEV/CAL pooled and major day; eta CAL only, apply fixed eta to DEV too. Only B1/B2/B3 eligible. Min pooled GPU-underprediction ratio, then overreservation, then larger u, then B3/B1/B2 and C0/C1/C2/C3, then R0/R1.',
       EVAL_rule='Commit selection before evaluation scoring; if no eligible method, freeze NONE and compute exposed diagnostic comparisons only. No reselection.',
       classification='If no DEV/CAL eligible method: V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT. If frozen selected method fails eval hybrid/body: V40S3_HYBRID_RUNTIME_SAFETY_FAIL; tail-only fail: V40S3_TAIL_RISK_DETECTION_FAIL; all pass maximum PREVALIDATED.',
       compute=dict(device='CPU',threads=1,seed=SEED,determinism='independent repeat fit/prediction byte check per model',
                    packages={'lightgbm':'4.6.0','xgboost':'3.2.0','numpy':'2.2.6','pandas':'2.2.3','sklearn':'1.6.1'},
                    extra_package_path='C:/codex_mobileess_workspace/v40s3_runtime_packages',GPU_used=False),
       holds=HOLDS,shadow='SEALED',May_scientific_reads=0))
    evidence=get('EXISTING_RUNTIME_EVIDENCE_AUDIT');evidence.update(classification='PENDING_NEW_STRICT_CLOCK_EXECUTION',
       authority_correction='Missing saved snapshot no longer blocks normative reconstructed membership; feature provenance remains separate',
       amended_threshold_forensic='V40S3_THRESHOLD_FORENSIC.json; original all-job March study retained only in superseded directory')
    write('EXISTING_RUNTIME_EVIDENCE_AUDIT',evidence)
    print(json.dumps(dict(status='AMENDED_PREREG_READY',blocks=oldpop['block_population'],thresholds=rows),default=str))


def predictor_x(d, logistic=False):
    x=d[['submit_hour','submit_dow']].to_numpy(dtype=float)
    assert np.isfinite(x).all()
    if logistic:
        return np.column_stack([np.eye(24)[x[:,0].astype(int)],np.eye(7)[x[:,1].astype(int)]])
    return x


def build_models(h, tr):
    import lightgbm as lgb
    import xgboost as xgb
    from sklearn.linear_model import LogisticRegression
    b=tr[tr.runtime_seconds<=h*3600]
    assert len(b)>=100
    models={}; audits=[]
    x=predictor_x(b);y=b.runtime_seconds.to_numpy()
    for name in ('B1','B2'):
        pairs=[]
        for alpha in (.5,.9):
            make=(lambda:lgb.LGBMRegressor(objective='quantile',alpha=alpha,**LGB)) if name=='B1' else (lambda:xgb.XGBRegressor(objective='reg:quantileerror',quantile_alpha=alpha,**XGB))
            start=time.perf_counter();m=make().fit(x,y);repeat=make().fit(x,y)
            p=m.predict(x);q=repeat.predict(x)
            assert p.tobytes()==q.tobytes(), 'DETERMINISM_FAIL'
            audits.append(dict(model=name,u_hours=h,quantile=alpha,train_N=len(b),max_training_end=b.end_time.max().isoformat(),
              time_sec=time.perf_counter()-start,independent_repeat_equal=True,max_difference=float(np.max(np.abs(p-q))),train_ID_SHA256=idsha(b)))
            pairs.append(m)
        models[name]=pairs
    models['B3']=np.quantile(y,[.5,.9],method='linear')
    audits.append(dict(model='B3',u_hours=h,train_N=len(b),time_sec=0,train_ID_SHA256=idsha(b),max_training_end=b.end_time.max().isoformat()))
    y=(tr.runtime_seconds>h*3600).astype(int).to_numpy();models['C0']=float(y.mean())
    for name in ('C1','C2','C3'):
        make={'C1':lambda:LogisticRegression(C=1,max_iter=1000,solver='lbfgs',random_state=SEED),
              'C2':lambda:lgb.LGBMClassifier(objective='binary',**LGB),
              'C3':lambda:xgb.XGBClassifier(objective='binary:logistic',eval_metric='logloss',**XGB)}[name]
        x=predictor_x(tr,logistic=name=='C1')
        assert len(np.unique(y))==2
        start=time.perf_counter();m=make().fit(x,y);r=make().fit(x,y)
        a=m.predict_proba(x)[:,1];b=r.predict_proba(x)[:,1]
        assert a.tobytes()==b.tobytes(),'DETERMINISM_FAIL'
        models[name]=m
        audits.append(dict(model=name,u_hours=h,train_N=len(tr),tail_train_N=int(y.sum()),max_training_end=tr.end_time.max().isoformat(),
                           time_sec=time.perf_counter()-start,independent_repeat_equal=True,max_difference=float(np.max(np.abs(a-b))),train_ID_SHA256=idsha(tr)))
    return models,audits


def predictions(models,d):
    x=predictor_x(d);res={};cross={}
    res['B0']=np.column_stack([np.maximum(d.K0.to_numpy(),1),d.reference_safe_sec])
    for n in ('B1','B2','B3'):
        a=np.column_stack([m.predict(x) for m in models[n]]) if n!='B3' else np.tile(models[n],(len(d),1))
        cross[n]=dict(raw_crossings=int((a[:,0]>a[:,1]).sum()),nonpositive=int((a<=0).sum()))
        assert np.isfinite(a).all()
        res[n]=np.maximum(np.sort(a,axis=1),1.)
    for n in ('C0','C1','C2','C3'):
        res[n]=np.full(len(d),models[n]) if n=='C0' else models[n].predict_proba(predictor_x(d,logistic=n=='C1'))[:,1]
    return res,cross


def body_score(d,p,h):
    records=[]
    for n in ('B0','B1','B2','B3'):
        for grp,mask in [('OVERALL',np.ones(len(d),bool)),*[(v,d.issue_day.eq(v).to_numpy()) for v in sorted(d.issue_day.unique())],
                         ('GPU_1',d.num_gpus_req.eq(1).to_numpy()),('GPU_2_4',d.num_gpus_req.between(2,4).to_numpy()),('GPU_5_PLUS',d.num_gpus_req.ge(5).to_numpy())]:
            m=mask & d.runtime_seconds.le(h*3600).to_numpy()
            if not m.any():continue
            z=metrics(d.runtime_seconds.to_numpy()[m],p[n][m,1],d.num_gpus_req.to_numpy()[m])
            z.update(candidate=n,u_hours=h,subgroup=grp,role=str(d.role.iloc[0]),Q50_MAE_sec=float(np.abs(d.runtime_seconds.to_numpy()[m]-p[n][m,0]).mean()),
                     scheduler_coverage=float(np.mean(slots(d.runtime_seconds.to_numpy()[m])<=slots(p[n][m,1]))),upper_warning=z['coverage']>.975)
            threshold=.9 if grp=='OVERALL' or grp.startswith('GPU') else .88
            z.update(gate_threshold=threshold,coverage_gate='INSUFFICIENT_SUPPORT' if z['N']<100 else 'PASS' if z['coverage']>=threshold else 'FAIL',
                     GPU_coverage_gate='INSUFFICIENT_SUPPORT' if z['N']<100 else 'PASS' if z['GPU_coverage']>=threshold else 'FAIL')
            records.append(z)
    return records


def tail_score(d,prob,eta,h,body_safe):
    from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
    y=d.runtime_seconds.gt(h*3600).to_numpy();g=d.num_gpus_req.to_numpy();t=d.runtime_seconds.to_numpy()
    bins=np.minimum((prob*10).astype(int),9)
    ece=sum(np.mean(bins==i)*abs(float(prob[bins==i].mean())-float(y[bins==i].mean())) for i in range(10) if (bins==i).any())
    z=dict(N=len(d),tail_N=int(y.sum()),prevalence=float(y.mean()),ROC_AUC=float(roc_auc_score(y,prob)) if len(np.unique(y))==2 else None,
           PR_AUC=float(average_precision_score(y,prob)) if y.any() else None,Brier=float(brier_score_loss(y,prob)),ECE=float(ece),eta=eta)
    if eta is None:
        z.update(recall=None,GPU_recall=None,mass_capture=None,precision=None,specificity=None,FNR=None,GPU_FNR=None,flagged_fraction=None)
    else:
        flag=prob>=eta;mass=g*np.maximum(t-body_safe,0)
        recall=float(flag[y].mean()) if y.any() else None
        gr=float(g[flag & y].sum()/g[y].sum()) if y.any() else None
        z.update(recall=recall,GPU_recall=gr,mass_capture=float(mass[flag].sum()/mass.sum()) if mass.sum() else None,
                 precision=float(y[flag].mean()) if flag.any() else None,specificity=float((~flag[~y]).mean()) if (~y).any() else None,
                 FNR=1-recall if recall is not None else None,GPU_FNR=1-gr if gr is not None else None,flagged_fraction=float(flag.mean()))
    return z


def replay_score(d,body,prob,eta,policy):
    if eta is None:return None
    flag=prob>=eta
    seconds=hybrid(body,flag,d.reference_safe_sec,d.requested_seconds,policy,state='PENDING')
    aligned=slots(seconds)*900
    z=metrics(d.runtime_seconds,aligned,d.num_gpus_req)
    ref=metrics(d.runtime_seconds,slots(d.reference_safe_sec)*900,d.num_gpus_req)
    rw=metrics(d.runtime_seconds,slots(d.requested_seconds)*900,d.num_gpus_req)
    def ratio(a,b):return a/b if b else (0. if a==0 else None)
    z.update(raw_coverage=float(np.mean(d.runtime_seconds<=seconds)),full_denominator=len(d),flagged_N=int(flag.sum()),
       reference=ref,RW=rw,GPU_mass_ratio=ratio(z['GPU_underprediction_sec'],ref['GPU_underprediction_sec']),
       overreservation_ratio=ratio(z['overreservation_GPU_hours'],ref['overreservation_GPU_hours']),
       GPU_mass_delta_vs_current=z['GPU_underprediction_sec']-ref['GPU_underprediction_sec'],
       GPU_mass_delta_vs_RW=z['GPU_underprediction_sec']-rw['GPU_underprediction_sec'],
       overreservation_delta_vs_current=z['overreservation_GPU_hours']-ref['overreservation_GPU_hours'],
       body_flag_underprediction_rate=float(np.mean(d.runtime_seconds.to_numpy()[~flag]>aligned[~flag])) if (~flag).any() else None,
       tail_flag_underprediction_rate=float(np.mean(d.runtime_seconds.to_numpy()[flag]>aligned[flag])) if flag.any() else None)
    return z


def gates(bodyrows,tail,replay,day_replays):
    b=[r for r in bodyrows if r['subgroup']=='OVERALL' or (not r['subgroup'].startswith('GPU') and r['N']>=100)]
    body_ok=bool(b) and all(r['coverage_gate']=='PASS' and r['GPU_coverage_gate']=='PASS' for r in b)
    tail_ok=tail['tail_N']>=100 and tail['eta'] is not None and tail['recall']>=.9 and tail['GPU_recall']>=.9 and tail['mass_capture'] is not None and tail['mass_capture']>=.8 and tail['ECE']<=.05
    flag_ok=tail['eta'] is not None and tail['flagged_fraction']<=.8
    hybrid_ok=replay is not None and replay['GPU_mass_ratio'] is not None and replay['GPU_mass_ratio']<1 and replay['overreservation_ratio'] is not None and replay['overreservation_ratio']<=2
    temporal_ok=all(z['GPU_mass_ratio'] is not None and z['GPU_mass_ratio']<=1.05 and z['overreservation_ratio'] is not None and z['overreservation_ratio']<=2 for z in day_replays)
    return dict(body=body_ok,tail=tail_ok,nontrivial_flagging=flag_ok,hybrid=hybrid_ok,temporal=temporal_ok,
                PASS=body_ok and tail_ok and flag_ok and hybrid_ok and temporal_ok)


def run(stage):
    prereg=prereg_guard();p=load_panel();models_dir=OUT/'models';models_dir.mkdir(exist_ok=True)
    results=[];bodyrows=[];tailrows=[];audits=[];crossings=[];etas=[]
    tr=p[p.role=='TRAIN'].reset_index(drop=True)
    if stage=='fit':
        assert not (OUT/'V40S3_DEV_CAL_RESULTS.json').exists(),'NO_UNREGISTERED_RETRAIN'
        roles=['DEVELOPMENT','CALIBRATION']
    else:
        sel=get('METHOD_SELECTION');receipt=get('METHOD_SELECTION_COMMIT_RECEIPT')
        assert git('show',f"{receipt['commit']}:{PREFIX}V40S3_METHOD_SELECTION.json",binary=True)==(OUT/'V40S3_METHOD_SELECTION.json').read_bytes()
        roles=['EXPOSED_EVALUATION']
        assert not (OUT/'V40S3_EXPOSED_RESULTS.json').exists(),'NO_EVALUATION_REUSE'
    for h in U_HOURS:
        if stage=='fit':
            model,audit=build_models(h,tr);audits.extend(audit)
            (models_dir/f'u{h}.pkl').write_bytes(pickle.dumps(model,protocol=5))
        else:
            expected=get('MODEL_FREEZE')['model_SHA256'][f'u{h}.pkl']
            assert sha((models_dir/f'u{h}.pkl').read_bytes())==expected
            model=pickle.loads((models_dir/f'u{h}.pkl').read_bytes())
        cal=p[p.role=='CALIBRATION'].reset_index(drop=True)
        if stage=='fit':
            cp,_=predictions(model,cal)
            thresholds={c:select_eta(cal.runtime_seconds,h*3600,cp[c],cal.num_gpus_req,cp['B3'][:,1],role='CALIBRATION') for c in ('C0','C1','C2','C3')}
            eta95={c:select_eta(cal.runtime_seconds,h*3600,cp[c],cal.num_gpus_req,cp['B3'][:,1],role='CALIBRATION',target=.95) for c in thresholds}
            etas.extend([dict(u_hours=h,classifier=c,eta=v,eta95=eta95[c],source_role='CALIBRATION',N=len(cal),tail_N=int(cal.runtime_seconds.gt(h*3600).sum()),cal_ID_SHA256=idsha(cal)) for c,v in thresholds.items()])
        else:thresholds={r['classifier']:r['eta'] for r in get('ETA_SELECTION')['rows'] if r['u_hours']==h}
        for role in roles:
            d=p[p.role==role].reset_index(drop=True);pred,cr=predictions(model,d)
            crossings.append(dict(u_hours=h,role=role,counts=cr))
            df=d[['job_issue_uid','job_id','issue_time','role']].copy()
            for n in ('B0','B1','B2','B3'):
                df[n+'_Q50']=pred[n][:,0];df[n+'_Q90']=pred[n][:,1]
            for c in thresholds:df[c+'_p_tail']=pred[c]
            df.to_parquet(OUT/f'V40S3_PREDICTIONS_u{h}_{role}.parquet',index=False)
            br=body_score(d,pred,h);bodyrows.extend(br)
            for b in ('B0','B1','B2','B3'):
                for c,eta in thresholds.items():
                    ts=tail_score(d,pred[c],eta,h,pred[b][:,1]);tailrows.append(dict(u_hours=h,body=b,classifier=c,role=role,**ts))
                    for policy in ('R0','R1'):
                        rs=replay_score(d,pred[b][:,1],pred[c],eta,policy)
                        daily=[]
                        if eta is not None:
                            for day,idx in d.groupby('issue_day').groups.items():
                                ix=np.asarray(list(idx))
                                if len(ix)>=100:
                                    dr=replay_score(d.iloc[ix],pred[b][ix,1],pred[c][ix],eta,policy)
                                    dr['day']=day;daily.append(dr)
                        gs=gates([r for r in br if r['candidate']==b],ts,rs,daily)
                        if b=='B0':gs['PASS']=False;gs['reference_only']=True
                        results.append(dict(u_hours=h,body=b,classifier=c,policy=policy,role=role,tail=ts,replay=rs,day_replays=daily,gates=gs))
        print(f'{stage}: u={h} complete',flush=True)
    name='DEV_CAL' if stage=='fit' else 'EXPOSED'
    write(name+'_RESULTS',dict(preregistration_commit=prereg,results=results,body_metrics=bodyrows,tail_metrics=tailrows,crossings=crossings))
    if stage=='fit':
        write('ETA_SELECTION',dict(rule='Largest CAL-only eta satisfying 90% job/GPU recall; 95% sensitivity separate',rows=etas))
        write('TRAINING_AUDIT',dict(device='CPU',threads=1,seed=SEED,models=audits,total_training_seconds=sum(r['time_sec'] for r in audits),
              substantive_fit_count=35,independent_repeat_fit_count=35,empirical_body_fits=5,base_rate_fits=5,
              causal_predictors=['submit_hour','weekday'],resource_predictor_count=0,new_proxy_track=False))
        write('MODEL_FREEZE',dict(status='TRAIN_ONLY_FROZEN',model_SHA256={p.name:sha(p.read_bytes()) for p in models_dir.glob('*.pkl')},
              preregistration_commit=prereg,new_models_production_integrated=False,refit_after_selection=False))
        eligible=[]
        for h in U_HOURS:
            for b in ('B1','B2','B3'):
                for c in ('C0','C1','C2','C3'):
                    for policy in ('R0','R1'):
                        rr=[r for r in results if (r['u_hours'],r['body'],r['classifier'],r['policy'])==(h,b,c,policy)]
                        if len(rr)==2 and all(r['gates']['PASS'] for r in rr):
                            numerator=sum(r['replay']['GPU_underprediction_sec'] for r in rr);denom=sum(r['replay']['reference']['GPU_underprediction_sec'] for r in rr)
                            over=sum(r['replay']['overreservation_GPU_hours'] for r in rr)
                            eligible.append(dict(u_hours=h,body=b,classifier=c,policy=policy,GPU_mass_ratio=numerator/denom,overreservation_GPU_hours=over))
        eligible.sort(key=lambda x:(x['GPU_mass_ratio'],x['overreservation_GPU_hours'],-x['u_hours'],['B3','B1','B2'].index(x['body']),x['classifier'],x['policy']))
        winner=eligible[0] if eligible else None
        write('METHOD_SELECTION',dict(selected=winner,eligible_count=len(eligible),eligible=eligible,selection_roles=['DEVELOPMENT','CALIBRATION'],
          EXPOSED_EVALUATION_scored=False,shadow='SEALED',classification='PENDING_EXPOSED_CHECK' if winner else 'V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT',
          reason='All gates required; no rescue by flagging nearly all jobs or tuning after evaluation',feature_authority='PASS_STRICT_CLOCK_ONLY',membership_authority='PASS_NORMATIVE_RECONSTRUCTION'))
        write('TAIL_THRESHOLD_SELECTION',dict(selected_u_hours=winner['u_hours'] if winner else None,candidates=U_HOURS,source_roles=['DEVELOPMENT','CALIBRATION'],winner=winner))
    print(name,'DONE',flush=True)


if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    else:run(sys.argv[1])
