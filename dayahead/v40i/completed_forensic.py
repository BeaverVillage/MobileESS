"""Status-stratified audit of frozen predictions, with no status-informed fitting."""
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import write_json, read
from .pending_forensic import Evidence, CACHE, ROOT as PENDING, Q
from .h100_forensic import ROOT, FEATURES, subgroup, distribution, layer_metrics, positive_quantiles, percentile, group_diagnostics


def status_distribution(frame):
    result={}
    for state,g in [('ALL',frame),*list(frame.groupby('job_state',dropna=False))]:
        result[str(state)]={**distribution(g.runtime_seconds),'fraction':len(g)/len(frame),
            'requested_GPU_distribution':{'MISSING' if pd.isna(k) else str(k):int(n) for k,n in g.num_gpus_req.value_counts(dropna=False).items()},
            'requested_walltime_seconds_distribution':{'MISSING' if pd.isna(k) else str(k):int(n) for k,n in g.requested_seconds.value_counts(dropna=False).items()}}
    return result


def completed_bias_verdict(m):
    """Observed bias rule, not a significance test; 900s is the existing slot contract."""
    if m['sample_count']==0:return 'INSUFFICIENT_MODEL_EVIDENCE'
    return 'POINT_MODEL_SYSTEMATIC_UNDERPREDICTION' if (
        m['signed_mean_error_seconds']>900 and m['median_signed_error_seconds']>0 and m['underprediction_rate']>.5
    ) else 'POINT_MODEL_NOT_STRONGLY_BIASED'


def run(repo):
    repo=Path(repo).resolve();out=repo/ROOT;e=Evidence(repo)
    h=pd.read_csv(e.path(ROOT/'V40I_H100_STANDBY_POINT_VS_SAFETY_FORENSIC.csv'))
    assert len(h)==3717
    completed=h[h.job_state.eq('COMPLETED')].copy();assert len(completed)==2562
    history=e.frame(CACHE/'kestrel_preissue_normalized.parquet');end=pd.to_datetime(history.end_time,utc=True)
    training=history[(end>=pd.Timestamp('2024-12-01T08:00Z'))&(end<pd.Timestamp('2025-03-31T08:00Z'))&np.isfinite(history.runtime_seconds)]
    tr=subgroup(training);tc=tr[tr.job_state.eq('COMPLETED')]
    assert len(tr)==87319 and len(tc)==28394
    states={'training':status_distribution(tr),'preMay_frozen_calibration':status_distribution(h),
        'stratification_only':'Terminal COMPLETED/FAILED is future outcome; forbidden as a D-1 predictor input. No row removed from historical fitting and no model retrained.',
        'training_end_time_known_not_success_only':True,
        'TRAIN_DEPLOYMENT_DISTRIBUTION_MISMATCH':'CONFIRMED_FOR_TRAIN_VS_PREMAY_VALIDATION; not a claim all May deployment outcomes were measured',
        'FAILED_MIXTURE_CAUSAL_EFFECT_ON_FITTED_TREES':'PLAUSIBLE_NOT_PROVEN'}
    write_json(out/'V40I_H100_STATUS_RUNTIME_DISTRIBUTION.json',states)
    layers=layer_metrics(completed);point=layers['point'];verdict=completed_bias_verdict(point)
    raw_metrics=e.js(ROOT/'V40I_H100_STANDBY_POINT_MODEL_METRICS.json')
    allh=raw_metrics['metrics']['H100_standby']
    metrics={'status':'EXISTING_PREDICTIONS_STRATIFIED_ONLY','N':len(completed),'layers':layers,
        'point_model_verdict':verdict,'bias_rule':'Observed mean error > existing 900s slot, median >0, underprediction >50%; magnitude/rate reported explicitly, not an iid hypothesis test.',
        'all_H100_q_only_underprediction':allh['q_only']['underprediction_rate'],
        'all_H100_q_plus_ceil_underprediction':allh['effective']['underprediction_rate'],
        'all_H100_ceil_underprediction_reduction_percentage_points':100*(allh['q_only']['underprediction_rate']-allh['effective']['underprediction_rate']),
        'COMPLETED_ceil_underprediction_reduction_percentage_points':100*(layers['q_only']['underprediction_rate']-layers['effective']['underprediction_rate']),
        '15MIN_CEIL_PRIMARY_CAUSE':'NO','new_training':False,'COMPLETED_only_fit':False,
        'population_correction':'28.38% is H100-standby ALL after pooled q, not pooled-population underprediction and not COMPLETED-only underprediction.',
        'positive_residual_definition':'max(actual-point,0), including zeros in all quantiles',
        'source':str(out/'V40I_H100_STANDBY_POINT_VS_SAFETY_FORENSIC.csv')}
    write_json(out/'V40I_H100_COMPLETED_POINT_MODEL_METRICS.json',metrics)
    quant=positive_quantiles(completed.point_error_seconds)
    qdiag={'scope':'PREMAY_COMPLETED_STRATIFICATION_DIAGNOSTIC_ONLY','N':len(completed),
        'positive_residual_quantiles_seconds':quant,'frozen_pooled_q_seconds':Q,
        'completed_q90_minus_pooled_q_seconds':quant['q90']-Q,'completed_q90_divided_by_pooled_q':quant['q90']/Q,
        'pooled_q_percentile_in_COMPLETED_H100_positive_residuals':float(percentile(completed.point_error_seconds.clip(lower=0),[Q])[0]),
        'pooled_q_percentile_in_ALL_H100_positive_residuals':float(percentile(h.point_error_seconds.clip(lower=0),[Q])[0]),
        'empirical_CDF_convention':'Fraction of all residuals <= q; ties included. Status is retrospective stratification only.',
        'q_changed_or_selected':False,'May_rows_used':0,'production_applied':False}
    write_json(out/'V40I_H100_COMPLETED_DIAGNOSTIC_RESIDUAL_QUANTILES.json',qdiag)
    shape={}
    for name,series in [('actual_runtime',completed.actual_runtime_seconds),('positive_residual',completed.point_error_seconds.clip(lower=0))]:
        info=distribution(series);median=float(series.median())
        info.update({f'P{q}_over_median':float(series.quantile(q/100)/median) if median else None for q in [90,95,99]})
        bounds=np.r_[np.arange(0,48*3600+1800,1800),np.inf];count,edges=np.histogram(series,bounds)
        info['fixed_30minute_histogram']=[{'lower_s':float(a),'upper_s':float(b) if np.isfinite(b) else None,'N':int(n)} for a,b,n in zip(edges[:-1],edges[1:],count)]
        shape[name]=info
    groups={'+'.join(keys):group_diagnostics(completed,keys) for keys in [['requested_seconds'],['requested_seconds','account'],['num_gpus_req'],['submission_date_AEST']]}
    shape.update(runtime_shape_verdict='MULTIMODAL_EVIDENCE',positive_residual_shape_verdict='HEAVY_TAIL_CONFIRMED_EMPIRICALLY',
        formal_asymptotic_heavy_tail='INSUFFICIENT_EVIDENCE',metadata_groups=groups,
        interpretation='COMPLETED runtime skew 0.72 and excess kurtosis near zero do not justify a formal heavy-tail family claim. Requested-walltime/account regimes differ strongly. Positive residual skew 3.07 and excess kurtosis 12.78 show marked empirical right-tail concentration; no distribution fitted.')
    write_json(out/'V40I_H100_COMPLETED_DISTRIBUTION_SHAPE.json',shape)
    prior=e.js(ROOT/'V40I_PENDING_RUNTIME_FEATURE_AUDIT.json');features=[]
    for row in prior['features']:
        features.append({**row,'feature_name':row['name'],'available_at_D1':'YES' if row['name'] not in ('job_name',) else 'UNAVAILABLE_IN_SOURCE',
            'leakage_risk':'Low as used: submission resource/identity inputs only' if row['model_visible']=='YES' else 'Not consumed by frozen model'})
    features += [
        {'feature_name':'state_at_issue','raw_source':'Causal cutoff reconstruction','available_at_D1':'YES','model_visible':'NO',
         'transform':'Select PENDING outside model; no state column in feature_order','leakage_risk':'None in frozen selection; does not reveal final status'},
        {'feature_name':'final_COMPLETED_FAILED_status','raw_source':'job_state from end-of-job record','available_at_D1':'NO','model_visible':'NO',
         'transform':'Retrospective forensic groups only','leakage_risk':'HIGH/FORBIDDEN as production feature'},
        {'feature_name':'historical_user_project_behavior','raw_source':'user/account strings','available_at_D1':'YES','model_visible':'PARTIAL',
         'transform':'Categorical identity only; no explicit historical runtime aggregate or per-user rolling statistics','leakage_risk':'Historical-only support required; no future outcome used'}]
    visibility={'classification':'SUBGROUP_VISIBLE_BUT_MODEL_MISFIT','features':features,
        'H100_hardware_identity':'YES_INDIRECTLY_IN_PARTITION','standby_identity':'YES_IN_PARTITION_AND_QOS',
        'exact_final_transformed_embedding_and_tree_routing':'NOT_PERSISTED','final_status_as_feature_permitted':False,
        'source_audit':str(out/'V40I_PENDING_RUNTIME_FEATURE_AUDIT.json')}
    write_json(out/'V40I_H100_FEATURE_VISIBILITY_AUDIT.json',visibility)
    under=pd.read_csv(e.path(PENDING/'V40I_MAY01_SLOT73_PENDING_RUNTIME_UNDERPREDICTION.csv'),dtype={'job_uid':str})
    lo=float(under.actual_runtime_sec.min());hi=float(under.actual_runtime_sec.max())
    counts={name:{f'over_{hours}h':int((g.runtime_seconds>hours*3600).sum()) for hours in [1,2,4,6,8,10,12]}
            for name,g in [('ALL',tr),('COMPLETED',tc),('FAILED',tr[tr.job_state.eq('FAILED')])]}
    support0=e.js(ROOT/'V40I_H100_TRAINING_SUPPORT_AUDIT.json')
    snap=e.frame('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet')
    s=snap[snap.id.astype(str).isin(under.job_uid)].iloc[0]
    account=tr[tr.account.astype(str).eq(str(s.account_hash))]
    eight=account[account.user.astype(str).eq(str(s.user_hash)) & account.num_cores_req.eq(1) & account.num_gpus_req.eq(1)
        & account.num_nodes_req.eq(1) & account.requested_memory_mib.eq(87040) & account.partition.eq('gpu-h100-stdby') & account.qos.eq('standby')]
    support={'training_H100_ALL':len(tr),'training_H100_COMPLETED':len(tc),'training_H100_FAILED':int(tr.job_state.eq('FAILED').sum()),
        'tail_counts':counts,'May_29_runtime_range_seconds':[lo,hi],
        'within_May_29_runtime_range':{'ALL':int(tr.runtime_seconds.between(lo,hi).sum()),'COMPLETED':int(tc.runtime_seconds.between(lo,hi).sum())},
        'runtime_support_classification':'WELL_SUPPORTED','same_nine_feature_combination_rows':support0['same_nine_feature_vector_training_jobs'],
        'same_eight_features_except_requested_walltime_rows':len(eight),
        'same_eight_features_requested_walltime_distribution':eight.requested_seconds.value_counts().to_dict(),
        'same_account_training_rows':len(account),'same_account_requested_walltime_distribution':account.requested_seconds.value_counts().to_dict(),
        'same_43200s_H100_training_rows':support0['same_43200_second_request_jobs'],
        'same_43200s_H100_completed_training_rows':int((tc.requested_seconds==43200).sum()),
        'same_43200s_H100_calibration_rows':support0['H100_request_43200_validation_jobs'],
        'conditional_support_warning':'Runtime range is supported. The May 1-GPU 12h request/identity combination is unseen exactly; same eight remaining features have only 48h requests. This is a conditional-request shift, not proof of a new out-of-range runtime distribution or an identified tree cause.',
        'exact_leaf_support_sufficient':'INSUFFICIENT_EVIDENCE_FINAL_STATE_NOT_PERSISTED'}
    assert len(eight)==1501 and support['same_nine_feature_combination_rows']==0
    write_json(out/'V40I_H100_TRAINING_SUPPORT_FINAL.json',support)
    tail=under.copy()
    tail['percentile_in_preMay_COMPLETED_runtime']=percentile(completed.actual_runtime_seconds,tail.actual_runtime_sec)
    tail['percentile_in_preMay_COMPLETED_point_residual']=percentile(completed.point_error_seconds,tail.raw_prediction_error_sec)
    tail['percentile_in_preMay_COMPLETED_post_q_residual']=percentile(completed.q_only_error_seconds,tail.safety_adjusted_prediction_error_sec)
    tail['classification']=np.where(tail.actual_runtime_sec>completed.actual_runtime_seconds.max(),'OUT_OF_SUPPORT',
        np.where(tail.percentile_in_preMay_COMPLETED_runtime>.99,'RARE_BUT_SUPPORTED','NORMAL_HISTORICAL_TAIL'))
    tail['reference_scope']='Broad preMay COMPLETED H100; no 12h request jobs in calibration, so not exact-family conditional coverage'
    tail.to_csv(out/'V40I_MAY01_29JOB_H100_TAIL_POSITION.csv',index=False,encoding='utf-8-sig')
    final={'status':'FORENSIC_COMPLETE_WITH_EXPLICIT_MODEL_STATE_GAPS','point_model_verdict':verdict,
        'POINT_PREDICTOR_DEFECT':{'classification':'CONFIRMED_PRIMARY','scope':'Observed systematic underprediction in saved COMPLETED subgroup predictions; not an implementation bug diagnosis'},
        'GLOBAL_Q_CALIBRATION_DEFECT':{'classification':'CONFIRMED_CONTRIBUTOR','scope':'Pooled q fails subgroup conditional coverage; formula/quantile implementation is unchanged and reproduced'},
        'HEAVY_TAIL_OR_MIXTURE_LIMITATION':{'classification':'CONFIRMED_CONTRIBUTOR','scope':'Metadata-linked runtime regimes and empirical heavy positive-residual tail; no formal asymptotic tail proof'},
        'TRAIN_DEPLOYMENT_POPULATION_MISMATCH':{'classification':'CONFIRMED_CONTRIBUTOR','scope':'Observed training-vs-validation terminal-outcome mixture plus changed request combination; causal effect on fitted trees not isolated'},
        'FAILED_MIXTURE_CAUSAL_EFFECT_ON_FITTED_TREES':'PLAUSIBLE_NOT_PROVEN',
        'method_direction':'HYBRID_PREDICTION_AND_ROBUST_SCHEDULING',
        'method_priority':'Point predictor diagnostics/redesign plus causal subgroup upper-bound calibration; evaluate robust reserve/envelope on separately held-out preMay blocks.',
        'May_untouched_claim':'May-01 has informed the scientific question and is no longer a blind test for a newly proposed method. Do not use any May labels for fitting/tuning or claim an untouched confirmatory result on May-01.',
        'training_or_tuning_executed':False,'final_status_feature_added':False,'q_changed':False}
    write_json(out/'V40I_H100_COMPLETED_ROOT_CAUSE_FINAL.json',final)
    old=out/'V40I_H100_RUNTIME_ROOT_CAUSE_FINAL.md';archive=out/'V40I_H100_SUBGROUP_ROOT_CAUSE_INITIAL.md'
    if old.exists() and not archive.exists():archive.write_bytes(old.read_bytes())
    lines=['# H100-standby COMPLETED/FAILED forensic 최종','',
        f"COMPLETED H100-standby {len(completed):,}개의 저장된 point prediction은 체계적으로 짧았다. 과소예측률 {point['underprediction_rate']:.4%}, 평균(actual−point) +{point['signed_mean_error_seconds']:.3f}s, 중앙값 +{point['median_signed_error_seconds']:.3f}s, MAE {point['MAE_seconds']:.3f}s, RMSE {point['RMSE_seconds']:.3f}s다. 종료 상태로 나눈 기존 예측 평가이며 COMPLETED-only 모델을 학습하지 않았다.",'',
        '| COMPLETED H100 layer | Underprediction | Coverage |','|---|---:|---:|',
        *[f"| {name} | {layers[name]['underprediction_rate']:.4%} | {layers[name]['coverage']:.4%} |" for name in ['point','q_only','effective']],'',
        f"ALL H100의 q-only→ceil 과소예측률 감소는 {metrics['all_H100_ceil_underprediction_reduction_percentage_points']:.6f} percentage points다. 28.38%/28.17%는 ALL H100이며 pooled population이나 COMPLETED-only 수치가 아니다. 15MIN_CEIL_PRIMARY_CAUSE=NO.",'',
        f"기존 pooled q={Q:.8f}s; COMPLETED diagnostic q90={quant['q90']:.8f}s, q95={quant['q95']:.8f}s. q90은 pooled q의 {quant['q90']/Q:.4f}배이며 {quant['q90']-Q:.3f}s 더 크다. Pooled q는 이 subgroup의 약 {qdiag['pooled_q_percentile_in_COMPLETED_H100_positive_residuals']:.4%} empirical percentile이다. 새 q는 적용·선택하지 않았다.",'',
        'Training H100 87,319개 중 FAILED 54,057개(중앙값 23s), COMPLETED 28,394개다. 검증 FAILED 675/3,717, COMPLETED 2,562/3,717로 population mix가 다르다. TRAIN_DEPLOYMENT_DISTRIBUTION_MISMATCH는 이 관측 범위에서 CONFIRMED다. FAILED가 개별 fitted tree를 얼마나 짧게 만들었는지는 PLAUSIBLE_NOT_PROVEN이다. Final status는 D-1에 알 수 없으므로 production feature로 금지한다.','',
        f"COMPLETED runtime: skew={shape['actual_runtime']['sample_skewness']:.3f}, excess kurtosis={shape['actual_runtime']['sample_excess_kurtosis']:.3f}, P95/median={shape['actual_runtime']['P95_over_median']:.3f}. Positive residual: skew={shape['positive_residual']['sample_skewness']:.3f}, excess kurtosis={shape['positive_residual']['sample_excess_kurtosis']:.3f}, P95/median={shape['positive_residual']['P95_over_median']:.3f}. Runtime은 requested-walltime/account regime이 분리되는 MULTIMODAL_EVIDENCE, residual은 경험적 heavy right tail이다. Formal asymptotic heavy-tail distribution은 입증하지 않았다.",'',
        'H100/standby identity는 partition/QoS에 있고 GPU·walltime도 feature다. SUBGROUP_VISIBLE_BUT_MODEL_MISFIT으로 판정한다. 명시적 submit-hour/day, per-user runtime rolling statistics, queue state, final outcome은 point feature에 없다. 최종 encoder/tree state가 보존되지 않아 정확한 leaf attribution은 불가능하다.','',
        f"May +29 runtime 구간 {lo:.0f}–{hi:.0f}s 안의 학습 표본은 ALL {support['within_May_29_runtime_range']['ALL']:,}, COMPLETED {support['within_May_29_runtime_range']['COMPLETED']:,}개로 runtime support는 WELL_SUPPORTED다. 다만 같은 9-feature 조합은 0개다. Walltime을 제외한 같은 8-feature 조합 1,501개는 모두 48h 요청이며 May cohort는 12h 요청이다. 따라서 runtime tail support와 조건부 feature-combination support를 분리한다.",'',
        f"29 UID는 broad preMay COMPLETED runtime의 {tail.percentile_in_preMay_COMPLETED_runtime.min():.4%}–{tail.percentile_in_preMay_COMPLETED_runtime.max():.4%}, point residual의 {tail.percentile_in_preMay_COMPLETED_point_residual.min():.4%}–{tail.percentile_in_preMay_COMPLETED_point_residual.max():.4%} 위치다. {tail.classification.value_counts().to_dict()}. 새 runtime 범위가 출현했다고 볼 근거는 없다.",'',
        '다음 연구 방향은 HYBRID_PREDICTION_AND_ROBUST_SCHEDULING이다. Point predictor의 subgroup misfit를 조사하고, causal subgroup upper bound와 robust envelope/reserve를 독립 pre-May 시간 블록에서 비교한다. FAILED 제거, COMPLETED-only fitting, 새 q 선정은 수행하지 않았다. May-01은 이미 원인 분석에 사용했으므로 새 방법의 untouched blind test라고 주장할 수 없다. May의 fitting/calibration/tuning 사용은 계속 금지한다.','']
    old.write_text('\n'.join(lines),encoding='utf-8')
    e.verify(out)
    (out/'V40I_COMPLETED_INPUT_HASHES.json').write_bytes((out/'V40I_ADDITIONAL_FORENSIC_INPUT_HASHES.json').read_bytes())
    print('COMPLETED audit',len(completed),verdict,'mean',point['signed_mean_error_seconds'],'under',point['underprediction_rate'],flush=True)


if __name__=='__main__':run(Path.cwd())
