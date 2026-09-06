"""Final conditional-support closure; existing records/predictions only, no fitting."""
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json
from .pending_forensic import Evidence,CACHE,Q,ROOT as PENDING
from .h100_forensic import ROOT,FEATURES,subgroup,distribution,layer_metrics,positive_quantiles

REGIMES=['<=4h','4-8h','8-12h_excluding12','exact12h','12-24h','24-48h_excluding48','exact48h','>48h']


def walltime_regime(seconds):
    h=float(seconds)/3600
    if h<=4:return '<=4h'
    if h<=8:return '4-8h'
    if h<12:return '8-12h_excluding12'
    if h==12:return 'exact12h'
    if h<=24:return '12-24h'
    if h<48:return '24-48h_excluding48'
    if h==48:return 'exact48h'
    return '>48h'


def feature_frame(frame):
    x=frame[FEATURES].copy()
    for col in FEATURES:
        x[col]=x[col].astype(str) if col in ['account','partition','qos','user'] else x[col].astype(float)
    return x


def prior_training(history,split_time):
    cut=pd.Timestamp(split_time);ends=pd.to_datetime(history.end_time,utc=True)
    return history[(ends>=cut-pd.Timedelta(days=120))&(ends<cut)&np.isfinite(history.runtime_seconds)].copy()


def support_bin(count):
    return 'STRONG_OBSERVED_EXACT_SUPPORT' if count>=100 else 'SPARSE_OBSERVED_EXACT_SUPPORT' if count else 'NO_EXACT_SUPPORT_REGIME_MISMATCH_CANDIDATE'


def regime_table(frame,has_predictions):
    x=frame.copy();x['walltime_regime']=x.requested_seconds.map(walltime_regime)
    result=[]
    for regime in REGIMES:
        g=x[x.walltime_regime.eq(regime)]
        r={'regime':regime,'N':len(g),'fraction':len(g)/len(x),'point_prediction_median_seconds':None,
           'point_signed_mean_error_seconds':None,'point_signed_median_error_seconds':None,
           'point_underprediction_rate':None,'post_pooled_q_underprediction_rate':None,'residual_q90':None,'residual_q95':None}
        if len(g):
            r['runtime']=distribution(g.runtime_seconds)
            r['requested_walltime_values_seconds']=sorted(g.requested_seconds.unique().tolist())
            if has_predictions:
                q=positive_quantiles(g.point_error_seconds)
                r.update(point_prediction_median_seconds=float(g.point_runtime_seconds.median()),
                    point_signed_mean_error_seconds=float(g.point_error_seconds.mean()),point_signed_median_error_seconds=float(g.point_error_seconds.median()),
                    point_underprediction_rate=float((g.point_error_seconds>0).mean()),
                    post_pooled_q_underprediction_rate=float((g.q_only_error_seconds>0).mean()),residual_q90=q['q90'],residual_q95=q['q95'])
        else:r['runtime']=None;r['requested_walltime_values_seconds']=[]
        result.append(r)
    return result


def run(repo):
    repo=Path(repo).resolve();out=repo/ROOT;e=Evidence(repo)
    history=e.frame(CACHE/'kestrel_preissue_normalized.parquet')
    h=feature_frame(history);assert len(h)==len(history)
    training=prior_training(history,'2025-03-31T08:00Z');tr=subgroup(training);tc=tr[tr.job_state.eq('COMPLETED')]
    cal=pd.read_csv(e.path(ROOT/'V40I_H100_STANDBY_POINT_VS_SAFETY_FORENSIC.csv'))
    completed=cal[cal.job_state.eq('COMPLETED')].copy();assert len(completed)==2562
    tw=tc[tc.requested_seconds.eq(43200)];cw=completed[completed.requested_seconds.eq(43200)]
    wall={'status':'READ_ONLY_WALLTIME_SUPPORT_CLOSED','training_COMPLETED':regime_table(tc,False),
        'calibration_COMPLETED_stored_predictions':regime_table(completed,True),
        'training_prediction_limitation':'No saved in-sample predictions recovered; prediction/error columns for training are null, never fabricated or refitted.',
        'regime_definition':'Mutually exclusive exact-second bins; 12h and48h are separate, no overlapping double counts or arbitrary approximate-12h bandwidth.',
        'twelve_hour_training_completed_N':len(tw),'twelve_hour_fraction_of_training_COMPLETED':len(tw)/len(tc),
        'twelve_hour_validation_completed_N':len(cw),'twelve_hour_training_accounts':tw.account.value_counts().to_dict(),
        'twelve_hour_training_users':int(tw.user.nunique()),'twelve_hour_training_GPU_distribution':tw.num_gpus_req.value_counts().to_dict(),
        '12H_SUPPORT':'12H_SUPPORT_SPARSE',
        'support_rule':'274 training COMPLETED examples across4 users/3 accounts,271 in one account; <1% of H100 COMPLETED. No12h calibration samples or exact May query-family matches. Sparse conditional evidence, not zero broad support.',
        'no_new_training':True}
    assert len(tw)==274 and len(cw)==0
    write_json(out/'V40I_H100_COMPLETED_WALLTIME_REGIME_AUDIT.json',wall)
    write_json(out/'V40I_H100_WALLTIME_CONDITIONAL_SUPPORT.json',wall)
    under=pd.read_csv(e.path(PENDING/'V40I_MAY01_SLOT73_PENDING_RUNTIME_UNDERPREDICTION.csv'),dtype={'job_uid':str})
    snap=e.frame('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet')
    snap=snap[snap.id.astype(str).isin(under.job_uid)]
    train_features=feature_frame(tr);records=[]
    for row in snap.itertuples():
        assert row.memory_req=='85G'
        query={'num_cores_req':float(row.processors_req),'num_gpus_req':float(row.gpus_requested),'num_nodes_req':float(row.nodes_req),
            'requested_memory_mib':87040.,'requested_seconds':float(row.wallclock_seconds),'account':str(row.account_hash),
            'partition':str(row.partition),'qos':str(row.qos),'user':str(row.user_hash)}
        same=train_features.eq(pd.Series(query));count=same.sum(axis=1)
        eight_other=same.drop(columns='requested_seconds').all(axis=1)
        nearest=tr[eight_other];exact=int((count==9).sum());eight=int((count==8).sum());seven=int((count==7).sum())
        rec={'job_uid':str(row.id),'feature_space':'Frozen nine causal input features; reference=H100-standby preissue training; no outcome matching',
            'exact_full_feature_match_count':exact,'exactly_8_of_9_feature_match_count':eight,'at_least_8_of_9_match_count':eight+exact,
            'exactly_7_of_9_feature_match_count':seven,'at_least_7_of_9_match_count':seven+eight+exact,
            'eight_other_inputs_excluding_walltime_match_count':int(eight_other.sum()),
            'nearest_walltime_regime_with_other_eight_inputs_fixed':'exact48h','nearest_training_sample_count':len(nearest),
            'nearest_requested_walltime_seconds':172800,'query_requested_walltime_seconds':43200,
            'walltime_absolute_distance_hours':36,'training_to_query_walltime_ratio':4,
            'any_H100_12h_training_support_exists':True,'any_H100_12h_training_samples':int(tr.requested_seconds.eq(43200).sum()),
            'same_other_eight_inputs_12h_support_exists':False,
            'same_hardware_partition_qos_regime_exists':True,'same_partition_qos_training_samples':int((tr.partition.eq(row.partition)&tr.qos.eq(row.qos)).sum()),
            'support_classification':'REGIME_MISMATCH','RUNTIME_VALUE_SUPPORT':'WELL_SUPPORTED_BROAD_HISTORICAL_RANGE',
            'FEATURE_CONDITIONAL_SUPPORT':'EXACT_MATCH_ABSENT; NEAREST_SAME_8_INPUTS_DIFFERENT_WALLTIME',
            'distance_definition':'Unweighted number of exact matching existing input fields, then absolute walltime distance with eight others fixed. No learned distance or May-tuned weights.'}
        assert exact==0 and len(nearest)==1501 and set(nearest.requested_seconds)=={172800}
        records.append(rec)
    assert len(records)==29
    pd.DataFrame(records).to_csv(out/'V40I_MAY01_29JOB_CONDITIONAL_SUPPORT.csv',index=False,encoding='utf-8-sig')
    # Each cached prediction is compared only with labels available before its own rolling split.
    histories=subgroup(history);support_rows=[];windows=[]
    for split,g in completed.groupby('split_time'):
        prior=prior_training(histories,split);keys=feature_frame(prior)
        all_counts=keys.groupby(FEATURES,dropna=False).size().to_dict()
        complete_counts=keys[prior.job_state.eq('COMPLETED')].groupby(FEATURES,dropna=False).size().to_dict()
        assert not set(prior.job_id.astype(str)) & set(g.job_id.astype(str))
        querykeys=feature_frame(g)
        for idx,row in g.iterrows():
            key=tuple(querykeys.loc[idx,FEATURES]);n=int(all_counts.get(key,0));nc=int(complete_counts.get(key,0))
            support_rows.append({'job_id':str(row.job_id),'split_time':split,'exact_prior_training_rows_all_status':n,
                'exact_prior_training_rows_COMPLETED':nc,'support_group':support_bin(n),
                'point_error_seconds':row.point_error_seconds,'point_runtime_seconds':row.point_runtime_seconds,
                'actual_runtime_seconds':row.actual_runtime_seconds,'q_only_error_seconds':row.q_only_error_seconds})
        windows.append({'split':split,'prior_H100_rows':len(prior),'prediction_rows':len(g),
            'training_max_end_time':str(pd.to_datetime(prior.end_time,utc=True).max()),'self_support_UID_overlap':0})
    sf=pd.DataFrame(support_rows);assert len(sf)==2562
    groups=[]
    for name,g in sf.groupby('support_group'):
        err=g.point_error_seconds
        groups.append({'group':name,'N':len(g),'point_MAE_seconds':float(err.abs().mean()),
            'point_signed_mean_error_seconds':float(err.mean()),'point_signed_median_error_seconds':float(err.median()),
            'point_underprediction_rate':float((err>0).mean()),'post_q_underprediction_rate':float((g.q_only_error_seconds>0).mean()),
            'prior_exact_support_range':[int(g.exact_prior_training_rows_all_status.min()),int(g.exact_prior_training_rows_all_status.max())]})
    sf.to_csv(out/'V40I_H100_SUPPORT_CONDITIONED_ERROR_ROWS.csv',index=False)
    conditioned={'status':'CAUSAL_PRE_SPLIT_SUPPORT_ASSOCIATION_ONLY','groups':groups,'windows':windows,
        'group_rule':'Exact nine-feature count>=100,1-99,0.100 is inherited min_expert_rows, used only as a transparent descriptive support bin, not a claim that a fitted leaf is statistically strong.',
        'reference_statuses':'All terminal statuses used because frozen training retained them; COMPLETED count also recorded without filtering training for prediction.',
        'no_self_or_future_support':True,'association_is_fitted_causal_effect':False,
        'association_interpretation':'Point underprediction persists with >=100 exact prior matches (65.57%), so support absence does not alone explain point misfit. Post-q underprediction is55.70% at zero exact matches versus26.70% at >=100; association only, not monotonic or causal fitted-effect proof. Sparse group N5 is too small for a stable comparison.',
        'limitation':'Feature exact-match counts are not learned tree/encoder support. Existing prediction windows and right-truncated historical archive limits are inherited; no fitted-state attribution.',
        'new_model_fit':False}
    write_json(out/'V40I_H100_SUPPORT_CONDITIONED_ERROR.json',conditioned)
    point=e.js(ROOT/'V40I_H100_COMPLETED_POINT_MODEL_METRICS.json');quant=e.js(ROOT/'V40I_H100_COMPLETED_DIAGNOSTIC_RESIDUAL_QUANTILES.json')
    split={'classification':'DUAL_PREDICTOR_AND_CALIBRATION_FAILURE','POINT_MODEL_DEFECT':'CONFIRMED_PRIMARY',
        'GLOBAL_Q_DEFECT':'CONFIRMED_CONTRIBUTOR','point_completed_metrics':point['layers']['point'],
        'q_completed_diagnostic':quant,'completed_safety_layers':point['layers'],
        'important_population_distinction':'28.38/28.17% are ALL H100. COMPLETED q/ceil underprediction32.98/32.67%. Pooled q-only population underprediction10%.',
        'FAILED_SHORT_SAMPLE_DIRECT_CAUSAL_EFFECT_ON_PREDICTION':'PLAUSIBLE_NOT_PROVEN',
        'TRAIN_DEPLOYMENT_STATUS_MIX_MISMATCH':'CONFIRMED_FOR_TRAIN_VS_PREMAY_VALIDATION',
        'no_error_double_counting':'Point error and insufficient q affect the same jobs, not two additive +29 GPU populations.'}
    write_json(out/'V40I_H100_POINT_VS_Q_FINAL.json',split)
    shape=e.js(ROOT/'V40I_H100_COMPLETED_DISTRIBUTION_SHAPE.json')
    dist={'RUNTIME_DISTRIBUTION':'MULTI_REGIME','POSITIVE_RESIDUAL_DISTRIBUTION':'EMPIRICALLY_HEAVY_TAILED',
        'mathematical_asymptotic_heavy_tail':'INSUFFICIENT_EVIDENCE','evidence':shape,
        'interpretation':'Metadata-linked runtime regimes confirmed. Actual runtime skew0.721/excess kurtosis−0.054 does not support an unqualified formal heavy-tail claim. Positive residual skew3.071/excess kurtosis12.784 is markedly right-tailed.'}
    write_json(out/'V40I_H100_RUNTIME_DISTRIBUTION_FINAL.json',dist)
    reactive=e.js(ROOT/'V40I_AIDC_REACTIVE_MODEL_LINEAGE.json');qa=e.js(ROOT/'V40I_AIDC_REACTIVE_AUTHORITY_FINAL.json')
    sens=e.js(ROOT/'V40I_AIDC_PQ_SENSITIVITY_FORENSIC.json')
    write_json(out/'V40I_AIDC_REACTIVE_LINEAGE_FINAL.json',reactive)
    write_json(out/'V40I_AIDC_Q_AUTHORITY_FINAL.json',{**qa,'INDEPENDENT_AIDC_Q_AUTHORITY':'NO','AIDC_Q_CONTROL_AUTHORIZED':'NO',
        'NO_scope':'No verified independent AIDC Q source in documented repository/raw/source search; limits retained in time-varying PF forensic.'})
    write_json(out/'V40I_FIXED_PF_DIRECTIONAL_SENSITIVITY_FINAL.json',{**sens,
        'required_term':'constant-PF coupled P-Q directional sensitivity',
        'FIXED_PF_ASSUMPTION_PRIMARY_CAUSE_OF_REVERSAL':'NO',
        'primary_cause_scope':'No separate PF-change mechanism is needed to reproduce this frozen replay reversal; not a causal exclusion under arbitrary alternative physical PF.',
        'FIXED_PF_MODEL_FIDELITY':'INSUFFICIENT_AUTHORITY','fidelity_status':'OPEN_LIMITATION'})
    classes={
        'completed_H100_point_underprediction':('CONFIRMED_PRIMARY','Stored preMay COMPLETED prediction bias; May +29 uses same frozen recipe and exhibits uncovered errors.'),
        'pooled_q_insufficiency':('CONFIRMED_CONTRIBUTOR','Subgroup conditional coverage fails; q90 diagnostic5.346x current margin.'),
        'conditional_feature_support_mismatch':('PLAUSIBLE_NOT_PROVEN','Mismatch itself CONFIRMED: exact0,other8inputs1501 at48h. Its causal share of point error cannot be identified without fitted state; support-conditioned association reported.'),
        'FAILED_short_training_mixture_direct_effect':('PLAUSIBLE_NOT_PROVEN','Status-mix mismatch observed; final trees not persisted.'),
        'heavy_tail':('CONFIRMED_CONTRIBUTOR','Empirical positive-residual tail only; actual-runtime asymptotic tail not established.'),
        'multi_regime':('CONFIRMED_CONTRIBUTOR','Requested-walltime/account regimes and runtime histograms differ.'),
        '15_min_ceil':('REJECTED','As a primary worsening cause: rounding adds service reservation; reduces ALL-H100 underprediction0.215227pp.'),
        'admission_delay':('CONFIRMED_CONTRIBUTOR','Offsetting−3 downstream GPU in the separate admission cohort.'),
        'spatial_downstream_relocation':('CONFIRMED_PRIMARY','Fixed spatial intervention+9 GPU;14 of the+29 move upstream→downstream.'),
        'migration':('REJECTED','As primary worsening cause: net−1 GPU.'),
        'low_controllable_penetration':('CONFIRMED_CONTRIBUTOR','Consistent with limited magnitude; not a quantified causal share or solver failure.'),
        'fixed_PF_reactive_model':('REJECTED','As additional primary cause in current frozen replay; coupled P-Q gradient reproduces current delta; physical fidelity remains open.'),
        'missing_time_varying_Q_authority':('INSUFFICIENT_EVIDENCE','Missing verified source is an authority/fidelity limitation, not a demonstrated cause of occupancy/current reversal.')}
    classify={'status':'FINAL_FORENSIC_CLOSURE','items':{k:{'classification':v[0],'reason':v[1]} for k,v in classes.items()},
        'conditional_support_presence':'CONFIRMED_REGIME_MISMATCH','conditional_support_fitted_effect':'PLAUSIBLE_NOT_PROVEN',
        'RUNTIME_NEXT_REVISION':'HYBRID_PREDICTOR_CALIBRATION_ROBUST',
        'REACTIVE_NEXT_REVISION':'RETAIN_FIXED_PF',
        'reactive_decision_boundary':'Retain current reproducible baseline; time-varying exogenous PF requires data, controllable Q requires equipment authority; current physical PF fidelity not claimed.',
        'new_method_implemented':False,'new_optimization':False,'model_retraining':False,'q_changed':False,'PF_changed':False,'Q_control_added':False,
        '31_DAY_ELECTRICAL_REGENERATION':'HOLD','B2_B3':'NO','FULL_MAY':'NO'}
    write_json(out/'V40I_FINAL_CAUSAL_CLASSIFICATION.json',classify)
    m=point['layers']['point'];p=read(e.path(PENDING/'V40I_AIDC_CONTROLLABLE_PENETRATION.json'))['cases']['B1']['critical_slot73']
    statement=('May-01 B1의 Actual 악화는 frozen PENDING runtime 과소예측과 spatial placement의 결합으로 재현됐다. '
        'Pre-May COMPLETED H100에서 체계적 point 과소예측과 pooled q의 conditional coverage 부족이 확인된다. '
        'May cohort의12h 요청 조합은 동일한 나머지 입력의48h 학습 regime과 달랐다. 이 support mismatch의 존재는 확정되지만 개별 예측에 대한 직접 인과 기여는 미입증이다. '
        'Actual occupancy의 sw2 하류+2GPU와 constant-PF coupled P-Q directional sensitivity가 저장된 전류 증가를 가깝게 재현했다. '
        '작은 절대 grid 효과는 제어 가능한 부하가 slot73 feeder의 약0.895%라는 규모와도 일치한다.')
    lines=['# V40I final forensic closure','',statement,'',
        f"필수 수치: COMPLETED N=2,562, point underprediction{m['underprediction_rate']:.4%}, mean error+{m['signed_mean_error_seconds']:.3f}s, median+{m['median_signed_error_seconds']:.3f}s. q={Q:.8f}s, COMPLETED diagnostic q90={quant['positive_residual_quantiles_seconds']['q90']:.8f}s, ratio={quant['completed_q90_divided_by_pooled_q']:.6f}. DUAL_PREDICTOR_AND_CALIBRATION_FAILURE.",'',
        '12h COMPLETED training274개는4user/3account에 속하며271개가 한 account다. 전체 COMPLETED 중0.965%이고 calibration12h는0개다. 12H_SUPPORT_SPARSE. May29개 모두 exact9-match0, 같은 other8-match1501(모두48h)로 REGIME_MISMATCH다. Runtime 값의 범위 support와 feature-conditional support는 같은 판정이 아니다.','',
        '| 당시 exact feature support | N | MAE s | mean signed error s | point under | post-q under |','|---|---:|---:|---:|---:|---:|',
        *[f"| {g['group']} | {g['N']} | {g['point_MAE_seconds']:.3f} | {g['point_signed_mean_error_seconds']:.3f} | {g['point_underprediction_rate']:.4%} | {g['post_q_underprediction_rate']:.4%} |" for g in groups],'',
        'Support는 각 prediction split 이전120일 end_time-known 학습 자료에서 계산했다. 자기 UID와 미래 종료는 제외했다.100개 기준은 기존 min_expert_rows를 투명한 descriptive bin으로 사용한 것이며 실제 fitted leaf support를 증명하지 않는다. 그룹 간 association으로 fitted causal effect를 주장하지 않는다.','',
        '동일 input support가100개 이상인군도 point underprediction65.57%다. 따라서 support 부족만으로 point misfit를 설명할 수 없다. q 적용 후에는 exact support0군55.70%,100개 이상군26.70%로 차이가 있지만 이는 association이며 sparse군N5는 비교 근거가 약하다.','',
        'TRAIN_DEPLOYMENT_STATUS_MIX_MISMATCH=CONFIRMED(학습 대 pre-May 검증). FAILED_SHORT_SAMPLE_DIRECT_CAUSAL_EFFECT_ON_PREDICTION=PLAUSIBLE_NOT_PROVEN. Final COMPLETED/FAILED는 retrospective label이고 D-1 feature가 아니다.','',
        'Runtime distribution=MULTI_REGIME; positive residual은 경험적 heavy right tail. Formal asymptotic heavy-tail law는 미입증. ALL H10028.38%/28.17%와 COMPLETED32.98%/32.67%를 구분한다.15-min ceil은 주원인이 아니다.','',
        'UID reconciliation PASS: under+29, over−3, admission−3. Frozen effects−2+9−4−1=+2GPU. Migration은 주원인이 아니다.','',
        f"전기: constant-PF coupled P-Q directional sensitivity ΔI={sens['predicted_coupled_delta_current_A']:.12f}A, 저장Actual={sens['observed_delta_current_A']:.12f}A, 절대차이={sens['absolute_mismatch_A']:.12f}A, 상대오차={sens['relative_mismatch_to_observed']:.6%}. 순수 P 미분으로 부르지 않는다. FIXED_PF_ASSUMPTION_PRIMARY_CAUSE_OF_REVERSAL=NO(현재 frozen replay에서 별도 primary mechanism 불필요), 물리 fidelity=INSUFFICIENT_AUTHORITY/OPEN_LIMITATION.",'',
        'AIDC Q는 fixed PF0.95 파생값이며 P와 함께 시간에 따라 변한다. 독립 AIDC Q authority=NO(검색 범위 내 미확인), Q control authorization=NO. 별도 MESS PCC Q gradient는 진단 proxy이고 AIDC Q partial/capability가 아니다.','',
        f"slot73: feeder{p['feeder_gross_load_kW']:.6f}kW, AIDC{p['total_AIDC_PCC_kW']:.6f}kW, controllable{p['B1_controllable_load_kW']:.6f}kW, fixed{p['fixed_noncontrollable_AIDC_PCC_kW']:.6f}kW; controllable/feeder{p['CONTROLLABLE_FEEDER_PENETRATION']:.4%}, controllable/AIDC{p['FLEXIBLE_AIDC_SHARE']:.4%}. 작은 효과가 optimizer failure임을 뜻하지 않는다. Primary Planning 최적성 근거는 유지되어 있다.",'',
        '최종 연구 방향: RUNTIME_NEXT_REVISION=HYBRID_PREDICTOR_CALIBRATION_ROBUST; REACTIVE_NEXT_REVISION=RETAIN_FIXED_PF. Conditional calibration만으로 충분하다고 판단할 근거는 없다. Causal point model, condition-aware upper tail, optimization-side reserve/envelope를 별도 pre-May 프로토콜에서 비교한다. Exogenous PF는 독립 자료, controllable Q는 장비 authority가 필요하다.','',
        '새 fit/재학습/q적용/parameter tuning/optimization/PF/Qcontrol 변경 없음. May-01은 이미 진단에 사용됐으므로 새 방법의 blind confirmatory test라고 주장하지 않는다. May fitting/calibration은 금지한다. Conditional source까지 포함한 최종 회귀 결과와 commit SHA는 최종 checkpoint receipt에 기록한다. Commit 이후에도31일 재생성HOLD, B2/B3 NO, full-May NO.','']
    for name in ['V40I_FINAL_FORENSIC_REVIEW.md','V40I_RUNTIME_ROOT_CAUSE_FINAL.md']:(out/name).write_text('\n'.join(lines),encoding='utf-8')
    decision=['# 최종 다음 revision 결정','',
        'RUNTIME_NEXT_REVISION = HYBRID_PREDICTOR_CALIBRATION_ROBUST','REACTIVE_NEXT_REVISION = RETAIN_FIXED_PF','',
        '근거: COMPLETED point underprediction64.13%, mean+7,064s; subgroup q90/current q5.346배;12h conditional regime mismatch; metadata-linked multiple runtime regimes와 heavy positive-residual tail. Point redesign + condition-aware upper bound + robust reserve/envelope를 연구 대상으로 결합한다.','',
        'Missing authority: final encoder/tree state와 leaf별 인과 attribution,12h matched-family validation, correlation-aware coverage 검증. Raw status mix와 support count만으로 FAILED effect를 증명하지 않았다. COMPLETED/FAILED를 feature로 사용하지 않는다.','',
        'Reactive baseline은 fixed PF0.95 유지. 이것이 물리적으로 충분히 정확하다는 판정은 아니다. TIME_VARYING_EXOGENOUS_PF_REQUIRES_DATA; CONTROLLABLE_Q_REQUIRES_EQUIPMENT_AUTHORITY. 독립 facility P/Q와 UPS/STATCOM P-Q capability/control interval 전에는 자유 Q 변수 금지.','',
        '이 결정은 다음 연구 방향이며 model/q/PF/도메인/정책 변경이나 실행 승인이 아니다. May Actual fitting/calibration/tuning NO. May-01은 더 이상 untouched blind evaluation으로 주장하지 않는다.','',
        '31_DAY_ELECTRICAL_REGENERATION=HOLD; B2_B3=NO; FULL_MAY=NO; MODEL_RETRAINING=NO. Final forensic commit 이후에도 자동 재개하지 않는다.','']
    (out/'V40I_NEXT_REVISION_DECISION.md').write_text('\n'.join(decision),encoding='utf-8')
    e.verify(out)
    (out/'V40I_CONDITIONAL_INPUT_HASHES.json').write_bytes((out/'V40I_ADDITIONAL_FORENSIC_INPUT_HASHES.json').read_bytes())
    print('FINAL conditional closure',len(records),'May rows','8match',records[0]['exactly_8_of_9_feature_match_count'],
          '7match',records[0]['exactly_7_of_9_feature_match_count'],'groups',groups,flush=True)


if __name__=='__main__':run(Path.cwd())
