"""Read-only subgroup diagnostics from existing pre-May predictions and training rows.

No model is instantiated, fitted, calibrated, or used to select a May policy.
Diagnostic margins are reported only; the frozen Q constant is never changed.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import write_json
from .pending_forensic import Evidence, CACHE, HPC, Q, ROOT as PENDING, metrics

ROOT = Path('dayahead/artifacts/v40i_authority_electrical_closure/dual_forensic')
FEATURES = ['num_cores_req','num_gpus_req','num_nodes_req','requested_memory_mib',
            'requested_seconds','account','partition','qos','user']


def positive_quantiles(errors):
    values = np.maximum(np.asarray(errors, dtype=float), 0)
    return {f'q{int(q*100)}':float(np.quantile(values,q,method='linear'))
            for q in [.5,.75,.8,.9,.95,.99]}


def distribution(values):
    x = pd.Series(values,dtype=float); y=x.to_numpy(); median=float(x.median())
    result={'N':len(x),'min':float(x.min()),'median':median,'mean':float(x.mean()),
        **{f'P{q}':float(x.quantile(q/100)) for q in [75,90,95,99]},'max':float(x.max()),
        'population_std':float(np.std(y)),'coefficient_of_variation':float(np.std(y)/x.mean()),
        'sample_skewness':float(x.skew()),'sample_excess_kurtosis':float(x.kurt()),
        'IQR':float(x.quantile(.75)-x.quantile(.25)),
        'P95_over_median':float(x.quantile(.95)/median) if median else None,
        'max_over_median':float(x.max()/median) if median else None,
        'tail_counts':{f'over_{h}h':int((x>h*3600).sum()) for h in [4,6,8,10,12]}}
    return {key:None if isinstance(value,float) and not np.isfinite(value) else value for key,value in result.items()}


def safety_layers(frame):
    x=frame.copy();y=x.actual_runtime_seconds;point=x.point_runtime_seconds
    x['point_plus_q_seconds']=point+Q
    x['capped_safe_seconds']=np.minimum(x.requested_seconds,np.maximum(point+Q,900))
    x['effective_seconds']=np.maximum(1,np.ceil(x.capped_safe_seconds/900))*900
    for name,col in [('point','point_runtime_seconds'),('q_only','point_plus_q_seconds'),
                     ('capped_safe','capped_safe_seconds'),('effective','effective_seconds')]:
        x[name+'_error_seconds']=y-x[col]
    return x


def layer_metrics(x):
    out={}
    for name,col in [('point','point_runtime_seconds'),('q_only','point_plus_q_seconds'),
                     ('capped_safe','capped_safe_seconds'),('effective','effective_seconds')]:
        e=x.actual_runtime_seconds-x[col];p=e.clip(lower=0)
        out[name]={**metrics(x,col),'coverage':float((e<=0).mean()),
            'mean_positive_residual_seconds':float(p.mean()),
            'P90_positive_residual_seconds':float(p.quantile(.9)),
            'P95_positive_residual_seconds':float(p.quantile(.95)),
            'P90_signed_residual_seconds':float(e.quantile(.9)),
            'P95_signed_residual_seconds':float(e.quantile(.95)),
            'maximum_signed_residual_seconds':float(e.max()),
            'maximum_positive_residual_seconds':float(p.max()),
            'positive_residual_quantiles':positive_quantiles(e)}
    return out


def subgroup(frame):
    return frame[frame.partition.astype(str).str.startswith('gpu-h100') & frame.qos.astype(str).eq('standby')].copy()


def group_diagnostics(frame,keys):
    rows=[]
    for key,g in frame.groupby(keys,dropna=False,sort=True):
        values=key if isinstance(key,tuple) else (key,)
        rows.append({**dict(zip(keys,map(str,values))),'N':len(g),
            'runtime_median_seconds':float(g.actual_runtime_seconds.median()),
            'runtime_P90_seconds':float(g.actual_runtime_seconds.quantile(.9)),
            'point_signed_mean_error_seconds':float(g.point_error_seconds.mean()),
            'point_signed_median_error_seconds':float(g.point_error_seconds.median()),
            'post_q_underprediction_rate':float((g.q_only_error_seconds>0).mean()),
            'effective_underprediction_rate':float((g.effective_error_seconds>0).mean())})
    return rows


def percentile(reference,values):
    """Empirical right-continuous CDF; ties count as <=, no fitted distribution."""
    r=np.sort(np.asarray(reference,dtype=float))
    return np.searchsorted(r,np.asarray(values,dtype=float),side='right')/len(r)


def feature_audit(e,out,training):
    paths=[HPC/'src/hpc_oda_commons/models/feature_policy.py',
        HPC/'src/hpc_oda_commons/models/rolling_tabular/base.py',
        HPC/'src/hpc_oda_commons/models/job_runtime_moe_xgboost/model.py',
        HPC/'src/hpc_oda_commons/ingest/jobs_parquet/apply.py',
        e.repo/'dayahead/v37/aidc_materializer.py']
    refs=[e.path(p) for p in paths]
    source_names={'num_cores_req':'processors_req','num_gpus_req':'gpus_requested','num_nodes_req':'nodes_req',
        'requested_memory_mib':'memory_req','requested_seconds':'wallclock_req -> wallclock_seconds',
        'account':'account_hash','partition':'partition','qos':'qos','user':'user_hash'}
    records=[]
    for name in FEATURES:
        categorical=name in ['account','partition','qos','user']
        records.append({'name':name,'source':source_names[name],'model_visible':'YES',
            'transformation':'Categorical one-hot/infrequent grouping then optional SVD' if categorical else
                'SLURM memory to MiB numeric' if name=='requested_memory_mib' else 'Numeric matrix column',
            'H100_tail_relevance':'Partition identifies H100/standby hardware queue' if name=='partition' else
                'QoS identifies standby service' if name=='qos' else
                'Request or identity can condition point estimates; not a conditional uncertainty estimate'})
    for name,note in [('hardware_class_separate','H100 is encoded indirectly in partition string'),
        ('queue_state','D1 PENDING is selected outside predictor; job_state/actual terminal outcome is not a feature'),
        ('submission_hour_day_of_week','submit_time is split metadata, not an input column in the frozen feature_order'),
        ('previous_job_runtime_rolling_statistics','No explicit per-job history aggregate; trees are trained on historical rows'),
        ('job_name','Unavailable in the retained anonymized schema'),
        ('elapsed_running_runtime','Not a PENDING model input')]:
        records.append({'name':name,'model_visible':'NO','source':None,'transformation':None,'H100_tail_relevance':note})
    value={'status':'TRACED','features':records,'H100_standby_identity_model_visible':'YES',
        'standby_vs_ordinary_pending_distinguishable':True,'feature_omission_verdict':'REJECTED',
        'model_misfit_interpretation':'SUBGROUP_VISIBLE_BUT_MODEL_MISFIT',
        'misfit_scope':'Observed subgroup prediction error; the discarded final tree state prevents exact split/leaf attribution.',
        'category_training_counts':{k:training[k].value_counts().to_dict() for k in ['partition','qos']},
        'categorical_grouping_caveat':'Input identity is available. Exact final one-hot/SVD mappings and final tree leaf routing were not persisted.',
        'source_paths':[str(p) for p in refs],'new_predictor_features_created':False}
    write_json(out/'V40I_PENDING_RUNTIME_FEATURE_AUDIT.json',value)
    return value


def run(repo):
    repo=Path(repo).resolve();out=repo/ROOT;out.mkdir(parents=True,exist_ok=True);e=Evidence(repo)
    raw=e.frame(CACHE/'kestrel_preissue_normalized.parquet')
    fit=e.js(CACHE/'issue_fit_audit.json');assert fit['feature_order']==FEATURES
    end=pd.to_datetime(raw.end_time,utc=True);cut=pd.Timestamp('2025-03-31T08:00Z')
    training=raw[(end>=cut-pd.Timedelta(days=120))&(end<cut)&np.isfinite(raw.runtime_seconds)].copy()
    assert len(training)==1288805
    cal=e.frame(CACHE/'calibration_predictions.parquet')
    cal=cal.merge(raw,on='job_id',validate='one_to_one',suffixes=('','_normalized'))
    assert len(cal)==87824 and np.array_equal(cal.actual_runtime_seconds,cal.runtime_seconds)
    assert (pd.to_datetime(cal.end_time,utc=True)<cut).all()
    cal=safety_layers(cal);h=subgroup(cal);tr=subgroup(training)
    assert len(h)==3717 and len(tr)==87319
    np.testing.assert_array_equal(cal.safe_runtime_seconds,cal.capped_safe_seconds)
    h['validation_job_state']='Historical submitted-job prediction; final outcome shown separately, not a predictor feature'
    h['subgroup']='H100_STANDBY';h['requested_GPU']=h.num_gpus_req
    h['actual_runtime_sec']=h.actual_runtime_seconds;h['point_prediction_sec']=h.point_runtime_seconds
    h['safe_prediction_sec']=h.point_plus_q_seconds
    h['point_error_sec']=h.point_error_seconds;h['safe_error_sec']=h.q_only_error_seconds
    for name,col in [('actual','actual_runtime_seconds'),('predicted','point_runtime_seconds')]:
        y=h[col]
        h[name+'_runtime_bucket']=np.select([y<900,y<1800,y<3600,y<7200,y<=14400],
            ['<15m','15-30m','30-60m','1-2h','2-4h'],default='>4h')
    h['runtime_requested_ratio']=h.actual_runtime_seconds/h.requested_seconds
    h['ratio_bucket']=pd.cut(h.runtime_requested_ratio,[-np.inf,.01,.1,.5,.9,1,1.01,np.inf],right=False).astype(str)
    local=pd.to_datetime(h.submit_time,utc=True).dt.tz_convert('Australia/Brisbane')
    h['submission_hour_AEST']=local.dt.hour;h['submission_weekday_AEST']=local.dt.day_name()
    h['submission_date_AEST']=local.dt.strftime('%Y-%m-%d');h['submission_minute_AEST']=local.dt.floor('min').astype(str)
    h.to_csv(out/'V40I_H100_STANDBY_POINT_VS_SAFETY_FORENSIC.csv',index=False,encoding='utf-8-sig')
    comparison={'pooled':layer_metrics(cal),'H100_standby':layer_metrics(h)}
    hm=comparison['H100_standby']['point']
    bias='POINT_PREDICTOR_SYSTEMATIC_UNDERBIAS' if hm['signed_mean_error_seconds']>0 and hm['median_signed_error_seconds']>0 else 'POINT_PREDICTOR_NOT_SYSTEMATICALLY_BIASED'
    point={'status':'PREMAY_OBSERVED_SAMPLE','metrics':comparison,'point_bias_verdict':bias,
        'bias_caveat':'Finite calibration sample: positive mean and median; median is only 86.34s and daily bias changes sign. No iid significance/population-wide constant bias claim.',
        'safety_verdict':'MIXED_CAUSE','global_q_verdict':'GLOBAL_Q_INSUFFICIENT_FOR_H100_STANDBY',
        'layer_definitions':{'point':'T_hat','q_only':'T_hat + frozen q',
            'capped_safe':'min(requested, max(T_hat+q,900))','effective':'max(1,ceil(capped_safe/900))*900'},
        'important_comparison':'28.17% refers to effective ceil duration. H100 q-only underprediction is 28.38%; pooled 88.38% coverage refers to capped-safe seconds, not uncapped q or ceil.',
        'May_training_or_calibration':False,'final_fitted_state_validation':'Unavailable; existing rolling recipe calibration predictions only'}
    write_json(out/'V40I_H100_STANDBY_POINT_MODEL_METRICS.json',point)
    diagnostic={'scope':'PREMAY_DIAGNOSTIC_ONLY_NOT_APPLIED','frozen_pooled_q_seconds':Q,
        'H100_positive_residual_quantiles_seconds':positive_quantiles(h.point_error_seconds),
        'quantile_definition':'numpy linear quantile of max(actual-point,0) over all subgroup jobs, including zero residuals',
        'pooled_positive_residual_quantiles_seconds':positive_quantiles(cal.point_error_seconds),
        'current_q_changed':False,'production_applied':False,'May_rows_used':0,
        'coverage_warning':'Empirical quantiles on calibration rows are not new validated upper bounds; caps, drift and correlation prevent guaranteed future coverage.'}
    write_json(out/'V40I_H100_STANDBY_REQUIRED_MARGIN_DIAGNOSTIC.json',diagnostic)
    grouped={'+'.join(keys):group_diagnostics(h,keys) for keys in [['requested_seconds'],['num_gpus_req'],['account'],['user'],
        ['partition'],['qos'],['job_state'],['submission_hour_AEST'],['submission_weekday_AEST'],['submission_date_AEST'],
        ['ratio_bucket'],['requested_seconds','account']]}
    write_json(out/'V40I_H100_EXISTING_METADATA_GROUPS.json',{'scope':'Forensic metadata only; terminal state/runtime ratio not submitted to predictor','groups':grouped})
    hist={}
    for minutes in [15,30,60]:
        bounds=np.r_[np.arange(0,48*3600+minutes*60,minutes*60),np.inf]
        count,bins=np.histogram(h.actual_runtime_seconds,bounds)
        hist[str(minutes)+'_minute_bins']=[{'lower_seconds':float(a),'upper_seconds':float(b) if np.isfinite(b) else None,'N':int(n)} for a,b,n in zip(bins[:-1],bins[1:],count)]
    dist={'runtime':distribution(h.actual_runtime_seconds),'positive_point_residual':distribution(h.point_error_seconds.clip(lower=0)),
        'histograms':hist,'heavy_tail_status':'EMPIRICAL_LONG_RIGHT_TAIL_CONFIRMED',
        'formal_asymptotic_heavy_tail':'NOT_ESTABLISHED; walltime-capped observations do not identify a mathematical tail family',
        'multimodality_status':'EMPIRICAL_MULTIMODAL_MIXTURE_LIKE',
        'evidence':'Short-runtime mass plus a distinct 15.5-16h concentration, with requested-walltime/account and terminal-outcome regimes. Histograms at 15/30/60min are retained; no mixture model fitted.',
        'metadata_groups':'V40I_H100_EXISTING_METADATA_GROUPS.json'}
    write_json(out/'V40I_H100_STANDBY_RUNTIME_DISTRIBUTION.json',dist)
    feature=feature_audit(e,out,training)
    under=pd.read_csv(e.path(repo/PENDING/'V40I_MAY01_SLOT73_PENDING_RUNTIME_UNDERPREDICTION.csv'),dtype={'job_uid':str})
    snap=e.frame(Path('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet'))
    may=snap[snap.id.astype(str).isin(under.job_uid)].iloc[0]
    assert str(may.memory_req)=='85G'
    exact_query={'num_cores_req':float(may.processors_req),'num_gpus_req':float(may.gpus_requested),
        'num_nodes_req':float(may.nodes_req),'requested_memory_mib':85*1024.,'requested_seconds':float(may.wallclock_seconds),
        'account':str(may.account_hash),'partition':str(may.partition),'qos':str(may.qos),'user':str(may.user_hash)}
    mask=pd.Series(True,index=tr.index)
    for k,v in exact_query.items():mask &= tr[k].astype(str).eq(v) if isinstance(v,str) else tr[k].eq(v)
    exact=tr[mask];wall=tr[tr.requested_seconds.eq(43200)]
    def state_counts(x):return {str(k):{'N':len(g),'fraction':len(g)/len(x),'runtime_median':float(g.runtime_seconds.median())} for k,g in x.groupby('job_state')}
    support={'training_cutoff':cut.isoformat(),'training_range':[(cut-pd.Timedelta(days=120)).isoformat(),cut.isoformat()],
        'total_training_jobs':len(training),'H100_standby_jobs':len(tr),'fraction':len(tr)/len(training),
        'subgroup_runtime':distribution(tr.runtime_seconds),'training_terminal_outcome_mix':state_counts(tr),
        'calibration_terminal_outcome_mix':state_counts(h),
        'same_43200_second_request_jobs':len(wall),'same_43200_second_request_runtime':distribution(wall.runtime_seconds),
        'same_nine_feature_vector_training_jobs':len(exact),
        'same_nine_feature_vector_runtime':distribution(exact.runtime_seconds) if len(exact) else None,
        'same_nine_feature_vector_terminal_outcomes':state_counts(exact) if len(exact) else {},
        'H100_request_43200_validation_jobs':int(h.requested_seconds.eq(43200).sum()),
        'training_support_verdict':'TRAINING_SUPPORT_SUFFICIENT',
        'training_support_sufficient':'YES_AT_BROAD_SUBGROUP_AND_OBSERVED_TAIL_LEVEL',
        'support_limitations':['Availability of 87,319 subgroup rows and many >12h jobs does not prove each final expert/leaf has sufficient effective support.',
            'Completed-before-cutoff means end_time known; FAILED/CANCELLED/TIMEOUT rows were retained, not only job_state COMPLETED.',
            'Final fitted state is discarded; exact learned leaf allocation and lost-at-cutoff long jobs cannot be reconstructed without fitting.',
            'The 7-day H100 calibration has no 43,200s request jobs; it is a broad-tail reference, not matched-family coverage.'],
        'underrepresentation_claim':'Global subgroup share alone is not proof of inadequate learning; broad subgroup/tail absence is rejected.'}
    write_json(out/'V40I_H100_TRAINING_SUPPORT_AUDIT.json',support)
    counts=h.groupby(FEATURES,dropna=False).size().to_numpy()
    cal_support={'calibration_jobs':len(cal),'H100_standby_jobs':len(h),
        'pooled_positive_residual_jobs':int((cal.point_error_seconds>0).sum()),
        'H100_positive_residual_jobs':int((h.point_error_seconds>0).sum()),
        'pooled_residual_above_q_jobs':int((cal.point_error_seconds>Q).sum()),
        'H100_residual_above_q_jobs':int((h.point_error_seconds>Q).sum()),
        'H100_share_of_calibration':len(h)/len(cal),'H100_weekday_counts':h.submission_weekday_AEST.value_counts().to_dict(),
        'H100_day_metrics':grouped['submission_date_AEST'],'pooled_partition_qos_mix':cal.groupby(['partition','qos']).size().reset_index(name='N').to_dict('records'),
        'unique_H100_nine_feature_signatures':len(counts),'largest_repeated_signature_jobs':int(counts.max()),
        'signature_concentration_effective_cluster_count':float(len(h)**2/np.dot(counts,counts)),
        'statistical_effective_sample_size':None,
        'ESS_limitation':'Repeated feature vectors identify clustering, not within-cluster outcome correlation. Concentration count is not a statistical ESS.',
        'verdict':'POOLED_CONDITIONAL_COVERAGE_MISMATCH_CONFIRMED; SIMPLE_SAMPLE_COUNT_INSUFFICIENCY_NOT_ESTABLISHED',
        'calendar_warning':'Seven weekdays are represented, but Thursday and Friday have one H100 job each; support is highly uneven.',
        'May_rows_used':0,'q_changed':False}
    write_json(out/'V40I_H100_CALIBRATION_SUPPORT_AUDIT.json',cal_support)
    tails=under.copy();tails['point_residual_percentile']=percentile(h.point_error_seconds,tails.raw_prediction_error_sec)
    tails['post_q_residual_percentile']=percentile(h.q_only_error_seconds,tails.safety_adjusted_prediction_error_sec)
    tails['actual_runtime_percentile']=percentile(h.actual_runtime_seconds,tails.actual_runtime_sec)
    tails['classification']=np.where(tails.actual_runtime_sec>h.actual_runtime_seconds.max(),'OUT_OF_SUPPORT',
        np.where(tails.actual_runtime_percentile>.99,'EXTREME_BUT_SUPPORTED_TAIL','EXPECTED_HISTORICAL_TAIL'))
    assert len(tails)==29 and tails.slot73_GPU_contribution.sum()==29
    tail={'scope':'May diagnostic rank against preMay reference only; not calibration or selection','rows':tails.to_dict('records'),
        'classification_counts':tails.classification.value_counts().to_dict(),
        'actual_runtime_percentile_range':[float(tails.actual_runtime_percentile.min()),float(tails.actual_runtime_percentile.max())],
        'point_residual_percentile_range':[float(tails.point_residual_percentile.min()),float(tails.point_residual_percentile.max())],
        'reference_limitation':'H100-standby broad reference includes different walltime/account regimes. Zero same-walltime validation jobs prevents a matched-family generalization.',
        'q_applied_or_changed':False}
    write_json(out/'V40I_H100_MAY01_TAIL_POSITION_AUDIT.json',tail)
    classes={
        'point_predictor_systematic_underprediction':('CONFIRMED_PRIMARY','Positive mean error, slightly positive median and severe long-job underprediction; daily signs differ.'),
        'global_pooled_q_insufficiency':('CONFIRMED_PRIMARY','H100 q-only coverage ~71.62%, below pooled 90%; fixed global margin fails conditional tail.'),
        'H100_subgroup_distribution_shift':('CONFIRMED_CONTRIBUTOR','Training-to-calibration terminal-outcome/runtime mixture shifts are observed; exact predictive causal share is not identified.'),
        'heavy_tailed_runtime':('CONFIRMED_CONTRIBUTOR','Empirical long right tail, not a formal asymptotic tail-family claim.'),
        'multimodal_runtime':('CONFIRMED_CONTRIBUTOR','Short-failure and longer service regimes visible in histograms and metadata.'),
        'subgroup_feature_omission':('REJECTED','Partition and qos identify H100/standby; exact final transformed feature attribution unavailable.'),
        'training_subgroup_underrepresentation':('REJECTED','87,319 subgroup jobs and 18,103 >12h cases; absence of broad support is not the cause established here.'),
        'calibration_sample_insufficiency':('INSUFFICIENT_EVIDENCE','3,717 subgroup rows/1,055 beyond q identify conditional mismatch; correlation-adjusted ESS unknown, weekday and request-family support uneven.'),
        '15_minute_temporal_granularity':('REJECTED','As a shortening/primary cause: ceil adds reservation and reduces H100 underprediction; continuous-time policy counterfactual not evaluated.'),
        'rounding_defect':('REJECTED','Conservative ceil; +29 cohort gains 487.25s padding.')}
    final={'classification':{k:{'classification':v[0],'reason':v[1]} for k,v in classes.items()},
        'primary_runtime_root_cause':'Visible subgroup point misfit under changing multimodal outcome mix, combined with pooled q that does not provide H100-standby conditional tail coverage.',
        'exact_final_tree_root_cause':'INSUFFICIENT_EVIDENCE: saved prediction and source trace exist but final fitted trees/encoders do not.',
        'recommendation':'Compare point-model redesign plus subgroup upper-bound calibration and predeclared robust reserve in a separate preMay-only study; no production selection.',
        'new_optimization':False,'retraining':False,'q_changed':False,'May_used_for_tuning':False}
    write_json(out/'V40I_H100_RUNTIME_ROOT_CAUSE_FINAL.json',final)
    q=diagnostic['H100_positive_residual_quantiles_seconds'];pm=comparison['pooled'];sm=comparison['H100_standby']
    lines=['# H100-standby runtime forensic','',final['primary_runtime_root_cause'],'',
        f"검증 N={len(h):,}; point MAE={hm['MAE_seconds']:.3f}s, RMSE={hm['RMSE_seconds']:.3f}s, mean(actual−point)={hm['signed_mean_error_seconds']:.3f}s, median={hm['median_signed_error_seconds']:.3f}s. 과소예측 {hm['underprediction_rate']:.4%}. 평균과 중앙값은 양수지만 일별 bias 부호는 다르다.",'',
        '| 지표 | Pooled | H100-standby |','|---|---:|---:|',
        *[f"| {name} | {pm[layer][key]:.6f} | {sm[layer][key]:.6f} |" for name,layer,key in [
            ('Point underprediction','point','underprediction_rate'),('q-only underprediction','q_only','underprediction_rate'),
            ('q-only coverage','q_only','coverage'),('capped-safe coverage','capped_safe','coverage'),('ceil coverage','effective','coverage'),
            ('q-only mean positive residual, sec','q_only','mean_positive_residual_seconds'),
            ('q-only P90 positive residual, sec','q_only','P90_positive_residual_seconds'),('q-only P95 positive residual, sec','q_only','P95_positive_residual_seconds')]],'',
        f"Frozen pooled q={Q}s. H100 diagnostic q90={q['q90']:.6f}s, q95={q['q95']:.6f}s. 적용·변경하지 않았다. 기존 28.17%는 ceil 후이며 q만 적용하면 {sm['q_only']['underprediction_rate']:.4%}다.",'',
        '학습 subgroup 87,319건 중 FAILED 54,057건(runtime 중앙값 23s), COMPLETED 28,394건(48,917s)이다. 검증에는 FAILED 675/3,717, COMPLETED 2,562/3,717이 포함된다. 절대오차 목적은 평균·상단 분위수가 아닌 조건부 중앙값 중심이며 서로 다른 종료 regime과 tail을 한 point로 나타낸다. 이 mix 변화는 관측 근거이지만 개별 tree/leaf의 원인 기여율을 증명하지 않는다. 종료 상태는 미래 정보이므로 새 feature로 넣지 않았다.','',
        f"학습에는 >12h {support['subgroup_runtime']['tail_counts']['over_12h']:,}건, May cohort와 같은 43,200s 요청 {len(wall)}건, 동일 9-feature vector {len(exact)}건이 있다. broad training support는 YES이나 final expert/leaf support는 미보존이다. 7-day calibration에는 같은 43,200s H100 요청이 0건이고 목·금 표본은 각각 1건이다. 단순히 7일이 짧아서 실패했다고 결론내리지 않는다.",'',
        'H100/standby는 partition/QoS로 모델에 보인다. Feature omission은 기각한다. 실제 runtime은 짧은 mass와 15.5–16h mass가 분리되는 mixture-like이고 긴 우측 tail이 있다. 이는 경험적 분포 진단이며 asymptotic heavy-tail 법칙이나 fitted mixture 모델 주장이 아니다.','',
        f"May +29의 historical rank: runtime {tail['actual_runtime_percentile_range']}, point residual {tail['point_residual_percentile_range']}; {tail['classification_counts']}. Broad preMay tail 범위 안에 있지만 matched walltime validation은 없어 같은 family coverage를 주장하지 않는다.",'',
        '정확한 최종 tree 오차 원인은 INSUFFICIENT_EVIDENCE. 현재 근거는 subgroup point misfit + pooled conditional coverage mismatch이며, 별도 pre-May 연구에서 point redesign/conditional upper bound/robust reserve 조합을 비교할 이유가 된다. 현재 model/q/Planning/May 결과는 변경하지 않았다.','']
    (out/'V40I_H100_RUNTIME_ROOT_CAUSE_FINAL.md').write_text('\n'.join(lines),encoding='utf-8')
    e.verify(out)
    # Reuse the read-only verifier but retain a distinct audit name for each part.
    audit=out/'V40I_ADDITIONAL_FORENSIC_INPUT_HASHES.json'
    (out/'V40I_H100_INPUT_HASHES.json').write_bytes(audit.read_bytes())
    print('H100 forensic complete',len(h),bias,'q90',q['q90'],'q95',q['q95'],'exact training',len(exact),flush=True)


if __name__=='__main__':run(Path.cwd())
