"""Independent population, target, maturity, feature, shift and holdout audits."""
from .causal_snapshot import *
from scipy.stats import wasserstein_distance

def split(day):
    if day<='2024-08-30':return 'TRAIN'
    if day=='2024-08-31':return 'PURGE'
    if day<='2024-10-30':return 'DEVELOPMENT'
    if day=='2024-10-31':return 'PURGE'
    if day<='2024-11-29':return 'CALIBRATION'
    if day=='2024-11-30':return 'PURGE'
    return 'EXPOSED_EVALUATION'

def stats(a):
    a=np.asarray(a,float);a=a[np.isfinite(a)]
    return {'N':len(a),'mean':float(a.mean()) if len(a) else None,'median':float(np.median(a)) if len(a) else None,
      'P90_P95_P99':np.quantile(a,[.9,.95,.99]) if len(a) else None,'max':float(a.max()) if len(a) else None}

def run_lengths(mask):
    d=np.diff(np.r_[False,mask,False].astype(int))
    return (np.flatnonzero(d==-1)-np.flatnonzero(d==1))*30

def main():
    assert not (OUT/'V40R3_PREREGISTRATION.json').exists()
    jobs=pd.read_parquet(OUT/'GPU_related_candidates_preMay.parquet')
    bins=pd.read_parquet(OUT/'all_raw_submission_bins_preMay.parquet')
    receipt=read('V40R3_RAW_INGESTION_RECEIPT.json')
    cohort=jobs.loc[jobs.model_cohort]
    bybin=cohort.groupby('arrival_bin').agg(work_GPUh=('work_GPUh','sum'),modeled_job_count=('id','size'),modeled_end_max=('end_time','max'))
    bins=bins.join(bybin);bins[['work_GPUh','modeled_job_count']]=bins[['work_GPUh','modeled_job_count']].fillna(0)
    bins.to_parquet(OUT/'arrival_bins_with_maturity.parquet')
    days=pd.date_range('2024-03-15','2025-02-26').strftime('%Y-%m-%d').tolist()
    records=[]; xp=[]; xf=[]; yy=[]; proofs=[];checks=[]
    train_cutoff=day_contract('2024-09-01')[0]
    selection_cutoff=day_contract('2024-11-01')[0]
    calibration_cutoff=day_contract('2024-12-01')[0]
    for day in days:
        origin,begin,end=day_contract(day)
        assert end<pd.Timestamp(receipt['complete_submission_coverage_before_UTC']) and end<MAY
        past,future,proof=snapshot(bins,day)
        y,available=incremental_target(jobs,day)
        target_index=pd.date_range(begin,periods=K,freq='30min')
        independently_grouped=bins.loc[target_index,'work_GPUh'].to_numpy()
        diff=float(np.max(np.abs(y-independently_grouped)))
        assert np.allclose(y,independently_grouped,rtol=1e-12,atol=1e-8)
        label=split(day)
        cutoff={'TRAIN':train_cutoff,'DEVELOPMENT':selection_cutoff,'CALIBRATION':calibration_cutoff}.get(label)
        eligible=(available<=cutoff) if cutoff is not None else label=='EXPOSED_EVALUATION'
        records.append({'operating_day':day,'forecast_origin':origin,'target_start':begin,'target_end':end,
          'target_label_available_at':available,'role':label,'stage_cutoff':cutoff,'stage_maturity_eligible':eligible,
          'modeled_jobs':int(bins.loc[target_index,'modeled_job_count'].sum()),'total_GPUh':float(y.sum()),
          'history_mature_fraction':float(past[:,2].mean()),'empty_target_day':bool(y.sum()==0)})
        xp.append(past);xf.append(future);yy.append(y);proofs.append(proof)
        checks.append({'day':day,'independent_reconstruction_max_abs_difference':diff,'cumulative_monotonic':bool((np.diff(np.cumsum(y))>=-1e-10).all())})
    info=pd.DataFrame(records); past=np.asarray(xp); future=np.asarray(xf); targets=np.asarray(yy)
    np.savez_compressed(OUT/'causal_dataset.npz',past=past,future=future,target=targets,days=np.asarray(days))
    info.to_parquet(OUT/'V40R3_LABEL_MATURITY_LEDGER.parquet',index=False)
    proof=pd.concat(proofs,ignore_index=True);proof.to_parquet(OUT/'feature_available_at_proofs.parquet',index=False)
    assert (proof.available_at<=proof.forecast_origin).all()
    assert (proof.loc[~proof.mature,'published_GPUh']==0).all()
    monthly=[]
    for month,g in jobs.groupby(jobs.submit_time.dt.strftime('%Y-%m')):
        m=g.loc[g.model_cohort]
        monthly.append({'month':month,'GPU_candidates':len(g),'GPU_authorized':int(g.GPU_quantity_authorized.sum()),
          'missing_GPU':int(g.gpus_requested.isna().sum()),'modeled_jobs':len(m),'modeled_candidate_fraction':len(m)/len(g),
          'runtime_seconds_modeled':stats(m.runtime_seconds),'authorized_GPU_quantity':stats(m.gpus_requested),
          'modeled_partition_distribution':m.partition.value_counts(normalize=True).to_dict(),
          'missing_GPU_partition_distribution':g.loc[g.gpus_requested.isna(),'partition'].value_counts(normalize=True).to_dict(),
          'modeled_QoS_distribution':m.qos.value_counts(normalize=True).to_dict(),
          'missing_GPU_QoS_distribution':g.loc[g.gpus_requested.isna(),'qos'].value_counts(normalize=True).to_dict(),
          'submission_hour_UTC_modeled':m.submit_time.dt.hour.value_counts(normalize=True).sort_index().to_dict(),
          'missing_GPU_by_hour_UTC':g.assign(missing=g.gpus_requested.isna()).groupby(g.submit_time.dt.hour).missing.mean().to_dict()})
    dump('V40R3_TARGET_POPULATION_CONTRACT.json',{'name':'GPU_QUANTITY_AUTHORIZED_WORKLOAD_COHORT',
       'definition':'Finite explicit gpus_requested>0, valid submit/start/end, end>start and start>=submit; observed GPU-service proxy assigned by submit interval',
       'F30_removed':True,'runtime_duration_threshold':None,'queue_wait_threshold':None,'status_filter':None,'H100_filter':False,'standby_filter':False,
       'missing_GPU':'Excluded from explicitly scoped estimand; never imputed to zero/nodes/partition',
       'valid_positive_service':'Physical label validity only, not a >=30-min flexibility classifier',
       'scope_limit':'Does not represent all Kestrel GPUh; missing-resource work mass is not identifiable. No claim all members have operational delay permission.',
       'resource_authority':'Official datacard names gpus_requested as ReqTRES; used as observed label-side resource quantity, not assumed immutable submit-time feature'})
    dump('V40R3_TARGET_POPULATION_COVERAGE_AUDIT.json',{'total_raw_jobs':receipt['unique_raw_jobs'],'GPU_related_candidates':len(jobs),
       'GPU_quantity_authorized_jobs':int(jobs.GPU_quantity_authorized.sum()),'GPU_quantity_missing_jobs':int(jobs.gpus_requested.isna().sum()),
       'modeled_jobs':len(cohort),'modeled_fraction_of_candidates':len(cohort)/len(jobs),'modeled_fraction_of_raw_jobs':len(cohort)/receipt['unique_raw_jobs'],
       'total_GPUh_coverage_fraction':None,'GPUh_coverage_reason':'Unknown GPU counts prevent identifying denominator',
       'invalid_or_nonpositive_service_among_authorized':int((jobs.GPU_quantity_authorized&~jobs.model_cohort).sum()),
       'authorized_missing_end':int((jobs.GPU_quantity_authorized&jobs.end_time.isna()).sum()),
       'operating_days':len(days),'days_with_modeled_arrivals':int((info.modeled_jobs>0).sum()),'monthly':monthly,
       'selection_bias':'Resource missingness and observed-service validity define a selected population; no total-facility generalization',
       'all_candidate_partitions':jobs.partition.value_counts().to_dict()})
    dump('V40R3_INCREMENTAL_GPUH_TARGET_CONTRACT.json',{'unit':'GPUh','formula':'Delta_W[k]=sum(gpus_requested*(end-start).total_seconds()/3600) for cohort jobs with submit in [bin_start,bin_end)',
       'K':K,'interval_minutes':STEP,'forecast_origin':'D-1 18:00 fixed AEST','target_window':'Next operating day [00:00,24:00) fixed AEST',
       'assignment':'Entire service demand to submission interval, never historical execution slots','cumulative':'cumsum of nonnegative increments',
       'cumulative_uncertainty_warning':'Sum of marginal Q90 increments is a derived conservative scenario, not generally the Q90 of the cumulative random total',
       'compatibility_horizons_minutes':[30,60,120,240,1440],'compatibility_horizon_anchor':'Operating-day start, not issue time; first target begins 360 minutes after issue',
       'no_GPU_to_power_conversion':True})
    dump('V40R3_TARGET_RECONSTRUCTION_VERIFICATION.json',{'status':'PASS','origins':len(days),'intervals':targets.size,
       'methods':['Direct per-day numpy bincount of job GPUh by submission index','Independent pandas aggregate of job GPUh by absolute submission bin'],
       'max_abs_difference':max(c['independent_reconstruction_max_abs_difference'] for c in checks),'checks':checks,
       'horizon_crossings':0,'service_timing_as_target':False})
    maturity_counts=info.groupby('role').agg(days=('operating_day','size'),eligible=('stage_maturity_eligible','sum')).to_dict('index')
    dump('V40R3_LABEL_MATURITY_AUDIT.json',{'definition':'max(interval/day right edge, max end of every contributing modeled job); empty-bin knowledge cannot precede bin close',
       'history_guard':'max right edge/all raw job ENDs, no unresolved ENDs; stricter than modeled-label maturity and calculable from observed event completion counts',
       'training_cutoff':train_cutoff,'development_selection_cutoff':selection_cutoff,'calibration_cutoff':calibration_cutoff,
       'counts':maturity_counts,'excluded_before_fit':int(((info.role=='TRAIN')&~info.stage_maturity_eligible).sum()),
       'history_mature_fraction':stats(info.history_mature_fraction),'unmature_workload_published':False})
    features=[]
    for stream,names in [('PAST',PAST_NAMES),('FUTURE_CONTEXT',FUTURE_NAMES)]:
        for name in names:
            iswork='GPUh' in name; ismaturity='mature' in name or 'maturity' in name
            evidence='Bin closed and every raw submission END observed <=t0' if iswork or ismaturity else ('SUBMIT events inside closed historical interval' if name=='submission_count' else 'Calendar/index computed at t0')
            features.append({'feature_name':f'{stream}.{name}','source':'NLR sacct event prefix' if iswork or ismaturity or name=='submission_count' else 'Fixed AEST calendar',
             'value_time':'Observed closed interval or deterministic computation at t0','available_at':'Observed closure time <=t0; masked placeholders and calendar computed at t0',
             'forecast_origin':'D-1 18:00 fixed AEST','eligibility':True,'classification':'CAUSAL_AVAILABLE','authority_evidence':evidence})
    for name in FORBIDDEN:
        features.append({'feature_name':name,'source':'Excluded','value_time':'Future/unproven','available_at':'Future/unproven','forecast_origin':'t0','eligibility':False,
          'classification':'TIMESTAMP_AMBIGUOUS' if name.startswith('request_') or name.startswith('partition_') else 'FUTURE_LEAKAGE','authority_evidence':'Explicit prohibition or no submit-time version authority'})
    pd.DataFrame(features).to_csv(OUT/'V40R3_FEATURE_AVAILABILITY_LEDGER.csv',index=False)
    dump('V40R3_FEATURE_AVAILABILITY_LEDGER.json',{'features':features,'admitted_feature_types':len(PAST_NAMES)+len(FUTURE_NAMES),'rejected_feature_types':len(FORBIDDEN),
       'tree_flattened_input_columns':HISTORY*len(PAST_NAMES)+len(FUTURE_NAMES),'past_shape':[HISTORY,len(PAST_NAMES)],'future_shape':[K,len(FUTURE_NAMES)],
       'per_origin_proof':'feature_available_at_proofs.parquet','legacy_177_features_inherited':0})
    dump('V40R3_CAUSAL_SNAPSHOT_CONTRACT.json',{'implementation':'dayahead/v40r3/causal_snapshot.py','source_SHA256':sha(ROOT/'dayahead/v40r3/causal_snapshot.py'),
      'past_names':PAST_NAMES,'future_names':FUTURE_NAMES,'history_intervals':HISTORY,
      'rolling_boundary':'[t0-L,t0), all right edges <=t0','mature_history':'Unmature values are zero placeholders with explicit mask=0; future completion timestamp and immature GPUh never encoded',
      'resources':'No retrospective request-resource/QoS/partition fields admitted as features','normalization':'Training-only after preregistration; never include immature GPUh in scaler fit',
      'telemetry_limit':'Logical event-time historical contract; periodic sacct export lacks physical ingestion/latency history, so no production telemetry certification',
      'V40R2_code_reused':False,'V40R2_estimator_reused':False})
    tr=(info.role=='TRAIN')&info.stage_maturity_eligible; yt=targets[tr]; q95=float(np.quantile(yt[yt>0],.95))
    flatten=targets.ravel(); burst=targets>=q95
    byweekday=[{'weekday':d,'GPUh':stats(targets[pd.to_datetime(info.operating_day).dt.dayofweek==d])} for d in range(7)]
    dump('V40R3_TARGET_STATISTICS.json',{'intervals':targets.size,'zero_fraction':float((targets==0).mean()),'positive_fraction':float((targets>0).mean()),
      'GPUh':stats(targets),'daily_total_GPUh':stats(targets.sum(axis=1)),'training_positive_Q95':q95,'threshold_training_days':int(tr.sum()),
      'burst_frequency':float(burst.mean()),'burst_count':int(burst.sum()),'burst_duration_minutes':stats(np.concatenate([run_lengths(x) for x in burst])),
      'autocorrelation':{str(lag):float(np.corrcoef(flatten[:-lag],flatten[lag:])[0,1]) for lag in [1,2,12,48,336]},
      'weekday':byweekday,'slot_of_day':[{'slot':k,'GPUh':stats(targets[:,k])} for k in range(K)],
      'fit_results_seen':False,'hurdle_justification':'Occurrence/magnitude candidate assessed after these target statistics; not inherited from active-GPU estimand'})
    shifts=[]
    for role,g in info.groupby('role'):
        idx=g.index.to_numpy();a=targets[idx];pos=a[a>0]
        shifts.append({'role':role,'days':len(g),'GPUh':stats(a),'target_mass':float(a.sum()),'zero_probability':float((a==0).mean()),
          'positive_magnitude':stats(pos),'daily_total':stats(a.sum(axis=1)),'Wasserstein_to_train':wasserstein_distance(yt.ravel(),a.ravel())})
    rawtrain=cohort.loc[cohort.submit_time.ge(day_contract('2024-03-15')[1])&cohort.submit_time.lt(day_contract('2024-08-31')[1])]
    composition=[]
    for month,g in cohort.groupby(cohort.submit_time.dt.strftime('%Y-%m')):
        record={'month':month,'runtime_Wasserstein_to_train':wasserstein_distance(rawtrain.runtime_seconds,g.runtime_seconds)}
        for c in ['partition','qos']:
            record[c+'_TV_to_train']=float(rawtrain[c].value_counts(normalize=True).subtract(g[c].value_counts(normalize=True),fill_value=0).abs().sum()/2)
        composition.append(record)
    dump('V40R3_TEMPORAL_SHIFT_REPORT.json',{'before_fit':True,'target_periods':shifts,'composition':composition,'descriptive_only':True,'PSI':'Not used; Wasserstein/TV are reported'})
    dump('V40R3_UNTOUCHED_HOLDOUT_AUDIT.json',{'before_fit':True,'TRUE_CONFIRMATORY_AVAILABLE':'NO',
      'periods':[{'period':'Kestrel 2024-02..2024-08','classes':['TRAINING_EXPOSED','DIAGNOSTIC_EXPOSED'],'evidence':'K5 original training; V40P/R/R2 diagnostics'},
       {'period':'Kestrel 2024-09..2024-12','classes':['TRAINING_EXPOSED','CALIBRATION_EXPOSED','SELECTION_EXPOSED','DIAGNOSTIC_EXPOSED'],'evidence':'K5 OOF/final fit; V40P Sep/Nov; V40R/R2'},
       {'period':'Kestrel 2025-01..2025-04-24','classes':['DIAGNOSTIC_EXPOSED'],'evidence':'V40P evaluation including March; V40R/R2 through Feb26'},
       {'period':'Earlier Kestrel / other facilities / later April','classes':['INSUFFICIENT_LINEAGE_AUTHORITY'],'evidence':'No verified zero exposure or identical population; no confirmatory data opened'}],
      'role_ranges':{'TRAIN':['2024-03-15','2024-08-30'],'DEVELOPMENT':['2024-09-01','2024-10-30'],'CALIBRATION':['2024-11-01','2024-11-29'],'EXPOSED_EVALUATION':['2024-12-01','2025-02-26']},
      'maturity_exclusions':'Per-origin exact ledger, same exclusions for every model','purged_days':['2024-08-31','2024-10-31','2024-11-30'],
      'maximum_positive_claim':'PREVALIDATED','V40R2_scientific_status':'SUPERSEDED_BY_V40R3; referenced for exposure census only, no code/data reuse'})
    print(json.dumps({'days':len(days),'target_intervals':targets.size,'zero_fraction':float((targets==0).mean()),'training_Q95':q95,'maturity':maturity_counts},indent=2))

if __name__=='__main__':main()
