"""Independent causal contracts, feature reconstruction, lineage and shift audits."""
from .common import *
from .backtest import registration, metrics
from scipy.stats import wasserstein_distance
import re,lightgbm as lgb,importlib.util

SNAP='dayahead/artifacts/v40p_lightgbm_forecast_forensic/source_snapshots/'
K5AS=SNAP+'kestrel_stage_k5a_ml_dataset_modular_v101/src/kestrel_k5a/'
K35S=SNAP+'kestrel_stage_k35_modular_v102/src/kestrel_k35/'
K5BS=SNAP+'kestrel_stage_k5b2_zero_inflated_modular_v101/src/kestrel_k5b2/'

def evidence(path,needle):
    p=ROOT/path;txt=p.read_text(encoding='utf-8');lines=txt.splitlines()
    return {'path':path,'line':next((i+1 for i,s in enumerate(lines) if needle in s),None),'needle':needle,'file_sha256':digest(p)}

def feature_audit(data):
    fd=pd.read_csv(K5A/'outputs/feature_dictionary.csv');ledger=[];checks=[]
    frame=data.set_index('timestamp_utc').sort_index()
    for r in fd.itertuples():
        name,source,kind,steps=r.feature_column,r.source_metric,r.feature_type,int(r.lookback_steps)
        extra=[]
        if kind=='calendar':
            cls='STATIC_AVAILABLE';window='calendar at t0';avail=True;right=0;rule='Known UTC/Melbourne calendar; DST follows Australia/Melbourne'
        elif kind=='lag':
            right=5-steps*5 if source not in ['queued_job_count','queued_requested_gpus'] else -steps*5
            window=f'bin [t0-{steps*5}m,t0-{steps*5-5}m) or queued point at left edge'
            if source=='arriving_flexible_gpu_hours_F30':
                cls='FUTURE_LEAKAGE';avail=False;rule='Realized full runtime at submission bin; no completion-availability mask, even for lagged marks'
            elif source in ['fixed_avg_active_gpus_F30','flexible_avg_active_gpus_F30']:
                cls='TIMESTAMP_AMBIGUOUS';avail=None;rule='Historical F30 split depends on realized duration/queue and terminal COMPLETED cohort; no available-at ledger'
            else:cls='LAGGED_AVAILABLE';avail=True;rule='Past bin or queue point; conditional on terminal-filtered retrospective cohort'
            ref=frame[source].astype(float).shift(steps)
            valid=ref.notna()&frame[name].notna();error=np.abs(ref[valid]-frame.loc[valid,name])
            checks.append({'feature':name,'rows':int(valid.sum()),'max_abs_difference':float(error.max()),'algorithm_match':bool(np.allclose(ref[valid].to_numpy(float),frame.loc[valid,name].to_numpy(float),rtol=1e-6,atol=1e-4))})
        else:
            window=f'{steps-1} preceding rows through CURRENT ROW';right=0 if source=='queued_requested_gpus' else 5
            if right>0:cls='FUTURE_LEAKAGE';avail=False;rule='Current bin is [t0,t0+5m); complete bin value is after literal forecast origin'
            else:cls='CAUSAL_AVAILABLE';avail=True;rule='Ceil-bucket queue events through t0; conditional on terminal-filtered cohort'
            if source=='arriving_flexible_gpu_hours_F30':extra.append('Unbounded actual-runtime completion dependency in addition to current-bin leak')
            if source in ['fixed_avg_active_gpus_F30','flexible_avg_active_gpus_F30']:extra.append('Retrospective F30 classification and completion-selected population')
            roll=frame[source].rolling(steps,min_periods=1)
            stat=kind.removeprefix('rolling_')
            ref=roll.std(ddof=0) if stat=='stddev_pop' else getattr(roll,stat)()
            if stat=='stddev_pop':ref=ref.fillna(0)
            valid=ref.notna()&frame[name].notna();error=np.abs(ref[valid]-frame.loc[valid,name])
            checks.append({'feature':name,'rows':int(valid.sum()),'max_abs_difference':float(error.max()),'algorithm_match':bool(np.allclose(ref[valid].to_numpy(float),frame.loc[valid,name].to_numpy(float),rtol=1e-5,atol=1e-4))})
        ledger.append({'track':'A and B (all LGBM heads); B15 persistence only uses current state','feature_name':name,'source':source,'raw_timestamp':'submit_time/start_time/end_time or timestamp_utc','available_at_forecast_origin':avail,'aggregation_window':window,'latest_bin_right_edge_minutes_from_t0':right,'future_dependency':cls in ['FUTURE_LEAKAGE','TIMESTAMP_AMBIGUOUS'],'leakage_classification':cls,'rule':rule,'additional_dependencies':'; '.join(extra),'upstream_cohort_caveat':'Only terminal COMPLETED, valid-runtime, non-standby jobs were retained globally; queue/arrival history is not a complete live population','builder':K5AS+'features.py'})
    pd.DataFrame(ledger).to_csv(OUT/'V40P_FEATURE_AVAILABILITY_LEDGER.csv',index=False)
    dump('V40P_FEATURE_AVAILABILITY_LEDGER.json',{'forecast_origin':'timestamp_utc literal left edge','features':ledger,'class_counts':pd.Series([r['leakage_classification'] for r in ledger]).value_counts().to_dict(),'origin_shift_sensitivity':'t0+5 minutes removes interval peeking but does not remove full-runtime arrival-mark or terminal-cohort leakage'})
    dump('feature_reconstruction_checks.json',checks)
    return ledger,checks

def target_audit(data):
    s=data.set_index('timestamp_utc');rows=[]
    for h in [3,6,12,24,48]:
        for track,src,target in [('A','arriving_flexible_gpu_hours_F30',f'target_cumulative_arriving_flexible_gpu_hours_F30_h{h:02}'),('B','fixed_avg_active_gpus_F30',f'target_fixed_avg_active_gpus_F30_h{h:02}')]:
            reference=sum(s[src].shift(-k) for k in range(1,h+1)) if track=='A' else s[src].shift(-h)
            keep=reference.notna();diff=np.abs(reference[keep]-s.loc[keep,target])
            rows.append({'track':track,'horizon_minutes':h*5,'rows':int(keep.sum()),'max_abs_difference':diff.max(),'reconstruction_pass':np.allclose(reference[keep],s.loc[keep,target],atol=1e-8,rtol=1e-8),'exact_window':f'[t0+5min,t0+{h*5+5}min)' if track=='A' else f'average occupancy in [t0+{h*5}min,t0+{h*5+5}min)','not_conventional_t0_to_horizon':True})
    dump('V40P_TARGET_CONTRACT.json',{'A':{'target':'cumulative realized complete-job GPU-hours for F30 jobs whose submission-bin index is 1..h after origin','unit':'GPU-hours = requested GPUs * (end-start)/3600, not requested walltime','eligibility':'K2 COMPLETED, positive valid-runtime H100 non-standby, then runtime >=30min and observed queue >=15min','known_runtime_overlap':'arrival mark is total job work, not work executed inside horizon','evidence':[evidence(K5AS+'features.py','ROWS BETWEEN 1 FOLLOWING'),evidence(K5AS+'workload.py','time_bucket(INTERVAL'),evidence(K35S+'sql.py','runtime_s >=')]},'B':{'target':'point-at-horizon 5-minute-average active GPUs among non-F30 jobs','unit':'average active GPUs; neither PUE, utilization fraction nor facility power','evidence':evidence(K5AS+'features.py','lead({source}')},'numeric_reconstruction':rows})
    dump('V40P_FORECAST_ORIGIN_CONTRACT.json',{'primary_origin':'t0 = row timestamp_utc, as used in K5C3 origin field','canonical_timezone':'UTC','feature_calendar':'Australia/Melbourne: AEST/AEDT DST','raw_submit_schema':'timestamp[us, tz=UTC]','raw_start_end_schema':'timestamps with numeric UTC offsets; converted to UTC without treating Denver wall-clock as UTC','source_display_timezone':'America/Denver','target_bin_labels':'left edges','alternative_right_edge_origin':'If t0 is redefined as row timestamp+5min, A becomes [t0,t0+h), B is final 5min bin ending t0+h; production timestamp contract does not perform this shift','evidence':[evidence(K5AS+'workload.py','AS timestamp_utc'),evidence(SNAP+'kestrel_stage_k5c3_optimization_ready_modular_v104/src/kestrel_k5c3/trajectory.py','origin_fixed_active_gpus')],'Dayahead_origin':'D-1 18:00 FIXED_AEST_UTC_PLUS_10; distinct from legacy Melbourne DST calendar'})
    dump('V40P_HORIZON_CONTRACT.json',{'legacy_horizons_minutes':[15,30,60,120,240],'steps':[3,6,12,24,48],'step_minutes':5,'A_cumulative_monotonicity_required':True,'B_monotonicity_required':False,'V28_daily':'target operating day [D00:00,D+1 00:00), offset 6..30h from cutoff','V28R2':'P/G 96 15-minute bins on D; W one daily total; no 15/30/60/120/240 cumulative output heads'})

def shift_audit(data):
    rows=[];categories=[]
    tr=data.loc[data.timestamp_utc.between('2024-02-29T23:00:00Z','2024-12-31T19:55:00Z')]
    for month in ['2025-01','2025-02','2025-03','2025-04']:
        te=data.loc[data.timestamp_utc.dt.strftime('%Y-%m').eq(month)]
        for c in ['arriving_job_count','arriving_requested_gpus','arriving_flexible_gpu_hours_F30','fixed_avg_active_gpus_F30','total_avg_active_gpus','queued_job_count','queued_requested_gpus']:
            a,b=tr[c].to_numpy(),te[c].to_numpy();threshold=np.quantile(a,.95)
            rows.append({'comparison':month,'variable':c,'training_N':len(a),'evaluation_N':len(b),'training_P5_median_P95':np.quantile(a,[.05,.5,.95]),'evaluation_P5_median_P95':np.quantile(b,[.05,.5,.95]),'training_mean':a.mean(),'evaluation_mean':b.mean(),'wasserstein':wasserstein_distance(a,b),'training_q95':threshold,'training_exceedance_rate':np.mean(a>threshold),'evaluation_exceedance_rate':np.mean(b>threshold)})
        for c in ['melbourne_hour','melbourne_day_of_week','melbourne_month']:
            a=tr[c].value_counts(normalize=True);b=te[c].value_counts(normalize=True)
            categories.append({'comparison':month,'variable':c,'TV':a.subtract(b,fill_value=0).abs().sum()/2})
    raw=json.loads((OUT/'raw_job_temporal_shift.json').read_text(encoding='utf-8'))
    dump('V40P_TEMPORAL_SHIFT_REPORT.json',{'continuous':rows,'categorical':categories,'raw_job_diagnostics':raw,'no_significance_only_conclusion':True,'evaluation_coverage_end':data.timestamp_utc.max(),'time_and_facility':'UTC timeline with Melbourne display; synthetic 12-site assignment of Kestrel HPC trace'})

def lineage():
    # Inventory all 24 repo frozen daily/slot LGBM artifacts; no refit and no May outcomes.
    paths=[]
    for root in ['dayahead/artifacts/v28_final_dayahead_actual/V28_FINAL_LIGHTGBM_FORECAST_MODELS','dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL_MODELS']:
        paths.extend(sorted((ROOT/root).glob('*.txt')))
    sha_maps={}
    for p in ['dayahead/artifacts/v28_final_dayahead_actual/V28_FINAL_LIGHTGBM_SHA256.json','dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL_MODELS_SHA256.json']:
        sha_maps.update(json.loads((ROOT/p).read_text(encoding='utf-8'))['files'])
    records=[]
    for p in paths:
        text=p.read_text(encoding='utf-8');m=lgb.Booster(model_str=text)
        channel='V28_DAILY_GPUH' if 'V28_FINAL' in str(p) else p.name.split('_APRIL')[0].split('_GENERAL')[0]
        param=dict(re.findall(r'^\[([^:]+): (.*)\]$',text,re.M))
        features=m.feature_name();script='tools/final_campaign/build_v28_ml_authority.py' if channel=='V28_DAILY_GPUH' else 'tools/final_campaign/train_v28r2_optimizer_channels.py'
        records.append({'model_id':p.stem,'path':p.relative_to(ROOT),'model_family':m.dump_model()['objective'],'model_SHA256':digest(p),'receipt_SHA256':sha_maps.get(p.relative_to(ROOT).as_posix()),'SHA_match':digest(p)==sha_maps.get(p.relative_to(ROOT).as_posix()),'training_script':script,'training_script_SHA256_working_copy':digest(ROOT/script),'training_script_SHA256_git_blob':hashlib.sha256(subprocess.check_output(['git','show',START+':'+script],cwd=ROOT)).hexdigest(),'training_timestamp':'not embedded; V28 source seed 20260901 is not proof of actual fit time','training_start':'2024-08-19','training_end':'2025-03-30' if 'APRIL_01' in p.name else '2025-03-31','validation_data':'V28 inherited V25 OOF; V28R2 does not publish independent test evaluation in training script','test_data':'no untouched block proven','target':channel,'target_unit':'GPU-hours' if channel=='V28_DAILY_GPUH' else 'node-hours' if channel=='W_FULLNODE_DAILY' else 'kW' if channel=='P_REF' else 'average H100 GPUs','horizon':'operating-day total or 96 slots from D-1 18 fixed AEST','hyperparameters':param,'feature_list':features,'feature_order':features,'categorical_handling':'none','random_seed':param.get('seed'),'inference_adapter':'dayahead/v28/forecast.py' if channel=='V28_DAILY_GPUH' else 'dayahead/v28r2/lightgbm_channels.py','downstream_consumer':'historical V28/V28R2 formulation; replaced by submitted-job ledger plus static site power in current V40A planning context','frozen_metric_assessment':'not substituted for K5B2 15-240min forecast results'})
    dump('V40P_MODEL_LINEAGE.json',{'primary':'K5B2 5 arrival Tweedie + 4 residual point models + persistence h15 + 5 event classifiers','repository_historical_models':records,'authority_paths':[evidence('dayahead/v28r2/formulation.py','p_quantiles, g_quantiles'),evidence('dayahead/v40a/context.py','from dayahead.v39a.power'),evidence('dayahead/v37/aidc_materializer.py','running = submit.le(cutoff)')],'current_K5B2_DayAhead_consumption':'NOT_FOUND in V40A planning context and V37 job construction; legacy runtime artifacts do consume K5C2/K5C3'})
    original=json.loads((OUT/'V40P_MODEL_SHA_VERIFICATION.json').read_text())
    original['repository_models']=[{k:r[k] for k in ['model_id','model_SHA256','receipt_SHA256','SHA_match']} for r in records]
    original['all_match']=original['all_match'] and all(r['SHA_match'] for r in records);original['total_model_count']=len(original['models'])+len(records)
    dump('V40P_MODEL_SHA_VERIFICATION.json',original)
    census=json.loads((OUT/'V40P_MODEL_SOURCE_CENSUS.json').read_text(encoding='utf-8'))
    for r in census['models']:
        if 'event_classifier' not in r['model_id']:
            continue
        parent=next(x for x in census['models'] if x['target']==r['model_id'].split('__')[0] and 'event_classifier' not in x['model_id'])
        for key in ['training_script','training_script_SHA256','training_timestamp','training_data','training_date_range','validation_data','test_data','feature_list','categorical_handling','random_seed','horizon_minutes']:
            r[key]=parent[key]
        path=OUT/'frozen_models'/(r['model_id']+'.txt')
        if not path.exists():
            original=K5B2/'models/frozen_selected'/path.name
            assert digest(original)==r['model_SHA256']
            path.write_bytes(original.read_bytes())
            record_access(original,'FROZEN_DIAGNOSTIC_EVENT_MODEL_COPY')
        text=path.read_text(encoding='utf-8');booster=lgb.Booster(model_str=text)
        params=dict(re.findall(r'^\[([^:]+): (.*)\]$',text,re.M))
        r.update(model_family='binary event classifier',loss_objective='binary',target_unit='probability of positive future GPU-hours',target_definition='indicator(primary cumulative arrival target > 0)',hyperparameters=params,tree_count=booster.num_trees(),inference_adapter='native binary sigmoid probability; separate diagnostic event threshold',downstream_consumer='K5C2 event probability/scenario input, never multiplied into selected Tweedie point forecast',feature_gain=dict(zip(booster.feature_name(),booster.feature_importance('gain'))),feature_split_count=dict(zip(booster.feature_name(),booster.feature_importance('split'))))
    for r in records:
        r['training_data']='V28: cutoff-conditioned daily event dataset; V28R2: source_labels.py pre-April daily/slot labels'
        r['training_date_range']=[r['training_start'],r['training_end']]
        r['training_script_SHA256']=r['training_script_SHA256_git_blob']
        r['loss_objective']=r['model_family']
    census['historical_repository_models']=records
    dump('V40P_MODEL_SOURCE_CENSUS.json',census)

def power_errors():
    source=BASE/'stage_k5c2_20260722_232023/outputs/idc_fixed_forecast_2025_long.parquet'
    f=read_pre_may(source,['timestamp_utc','fixed_selected_prediction','fixed_training_incremental_selected_prediction_kw'])
    mask=f.fixed_selected_prediction>1e-8
    ratios=f.loc[mask,'fixed_training_incremental_selected_prediction_kw']/f.loc[mask,'fixed_selected_prediction']
    coef=float(ratios.median());assert np.max(np.abs(ratios-coef))<1e-12
    path=ROOT/(SNAP+'kestrel_stage_k5c2_final_dc_inputs_modular_v103/src/kestrel_k5c2/synthesis.py')
    module_spec=importlib.util.spec_from_file_location('v40p_frozen_power_adapter',path);module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    metrics_B=pd.read_csv(OUT/'V40P_FIXED_LOAD_METRICS.csv').query("method=='prediction' and fold=='POOLED'")
    transformed=module.add_power_to_fixed_forecast(pd.DataFrame({'fixed_selected_prediction':metrics_B.MAE}),coef,[])
    results=[]
    for i,r in enumerate(metrics_B.itertuples()):
        results.append({'phase':r.phase,'horizon_minutes':r.horizon_minutes,'MAE_active_GPU':r.MAE,'MAE_incremental_IT_kW':transformed.iloc[i]['fixed_training_incremental_selected_prediction_kw'],'maximum_absolute_error_incremental_IT_kW':r.max_abs_error*coef,'worst_underprediction_incremental_IT_kW':r.max_underprediction*coef})
    dump('power_equivalent_error.json',{'coefficient_kW_per_GPU':coef,'coefficient_source':source,'coefficient_pair_count':int(mask.sum()),'coefficient_max_deviation':float(np.max(np.abs(ratios-coef))),'frozen_adapter':path.relative_to(ROOT),'adapter_SHA256':digest(path),'results':results,'A_power_error':'NOT_COMPUTABLE_FROM_CUMULATIVE_GPUH_WITHOUT_EXECUTION_TIME_PROFILE; no new GPU-to-kW mapping','current_V40_power_formula':'different frozen site formula; legacy coefficient is not transplanted into V40 physics'})

def main():
    registration();data=read_pre_may(K5A/'outputs/kestrel_ml_features_global_5min.parquet')
    # DuckDB DECIMAL source columns arrive through Arrow as Decimal objects.
    # Reconstruct arithmetic in float64; original model inputs remain float32.
    numeric = [c for c in data if c not in ['timestamp_utc','timestamp_melbourne'] and
               (pd.api.types.is_numeric_dtype(data[c]) or
                (len(data[c].dropna()) and isinstance(data[c].dropna().iloc[0], __import__('decimal').Decimal)))]
    for c in numeric:
        data[c] = data[c].astype(float)
    ledger,checks=feature_audit(data);target_audit(data);shift_audit(data);lineage();power_errors()
    counts=pd.Series([x['leakage_classification'] for x in ledger]).value_counts().to_dict()
    late=json.loads((OUT/'job_identity_and_availability_evidence.json').read_text(encoding='utf-8'))
    census=json.loads((OUT/'V40P_MODEL_SOURCE_CENSUS.json').read_text(encoding='utf-8'))
    offending={x['feature_name'] for x in ledger if x['leakage_classification']=='FUTURE_LEAKAGE'}
    used=[{'model_id':m['model_id'],'leaky_features_used_in_splits':sum(m.get('feature_split_count',{}).get(x,0)>0 for x in offending),'leaky_feature_total_splits':sum(m.get('feature_split_count',{}).get(x,0) for x in offending)} for m in census['models'] if 'feature_split_count' in m]
    dump('V40P_LEAKAGE_AUDIT.json',{'track_A':'FUTURE_ARRIVAL_FORECAST_LEAKAGE_FOUND','track_B':'FIXED_LOAD_FORECAST_LEAKAGE_FOUND','feature_class_counts':counts,'models_using_leaky_features':used,'findings':[{'id':'L1','severity':'FAIL','finding':'Realized GPUh of future-completing jobs is attached to their submission bucket and used as past input without availability mask','evidence':[evidence(K5AS+'workload.py','THEN gpu_hours ELSE 0 END'),evidence(K5AS+'features.py','CURRENT ROW')],'raw_safe_job_witness_count':late['late_lag1_mark_jobs']},{'id':'L2','severity':'FAIL','finding':'60 rolling features include nonqueue current bin [t0,t0+5min), and B persistence/residual add-back directly uses the same completed current bin','evidence':[evidence(K5AS+'features.py','PRECEDING AND CURRENT ROW'),evidence(K5BS+'modeling.py',"current=evalf[source]")]},{'id':'L3','severity':'FAIL_OR_AUTHORITY_MISSING','finding':'Global COMPLETED filtering and F30 based on realized runtime/observed queue are retrospective; historical fixed/flex labels are not live eligibility','evidence':[evidence(SNAP+'kestrel_stage_k2_modular_v202/src/kestrel_pipeline/sql.py',"AND state_simple ="),evidence(K35S+'sql.py','runtime_s >=')]},{'id':'L4','severity':'FAIL_HISTORICAL_V28_DAILY','finding':'V28 18 macro features: D1 complete calendar-day requested_GPU_h and 7/14d summaries include D-1 18:00..24:00 after issue','affected_features':['requested_GPU_h_D1','requested_GPU_h_mean_7d','requested_GPU_h_std_7d','requested_GPU_h_mean_14d'],'evidence':[evidence('dayahead/ml/c_mass_tpp/data.py','macro_features=_macro_features(input_events'),evidence('dayahead/ml/c_mass_tpp/data.py','_proxy_for_day(events, target_day')]},{'id':'L5','severity':'AUTHORITY_MISSING','finding':'V28R2 W daily lag2/lag7 and rolling statistics use full realized runtime labels without completion mask; P/G use completed-derived labels and fixed historical recursion; slot timestamps alone do not prove data availability','evidence':[evidence('dayahead/v28r2/source_labels.py','float(row.nodes) * float(row.runtime_hours)'),evidence('dayahead/v28r2/lightgbm_channels.py','frame["lag_2d"]')]}],'leakage_fixed':False})
    dump('V40P_PREPROCESSING_LEAKAGE_AUDIT.json',{'primary_models':{'normalizer':'none','scaler':'none','imputation':'no bfill/interpolation; native LightGBM missing handling','categorical_encoder':'none, all 177 inputs numeric float32','target_transform':'identity; A frozen scale=0.5 from validation calibration, B subtract current/add current','clipping':'fixed nonnegative output floor','feature_selection':'configured feature dictionary, no fitted feature selector','clipping_threshold_fit':'none'},'selection_calibration':'Same Sep-Dec OOF chooses objective, family, scale and median early-stop iterations; post-selection OOF scores are not independent','historical_V28':'log1p deterministic transform; pd.Categorical whole-data codes exist in micro branch but do NOT enter the 18 LightGBM macro inputs; not falsely classified as LightGBM encoder leakage','downstream_power_preprocessing':'K5C2 representative utilization uses whole provided site-workload mean (includes evaluation year); power scaling is not train-only. This is outside the primary GPU forecast model, and not repaired.','evidence':[evidence(K5BS+'modeling.py','scale=choose_scale'),evidence(SNAP+'kestrel_stage_k5c2_final_dc_inputs_modular_v103/src/kestrel_k5c2/power.py','mean_active = float(site_workload')]})
    split=pd.read_csv(K5A/'outputs/split_summary.csv');folds=pd.read_csv(K5A/'outputs/rolling_origin_folds.csv')
    dump('V40P_TEMPORAL_SPLIT_AUDIT.json',{'original_split_summary':split.to_dict('records'),'original_folds':folds.to_dict('records'),'final_production_fit':'train + validation concatenation through 2024-12-31 19:55 UTC; 88,044 rows','validation_reused_for_fit':True,'random_split':False,'temporal_order_on_origin_timestamps':'PASS; horizon purge=240min, but interval right edge and completion-availability need separate tests','label_availability_chronology':'FAIL_OR_UNPROVEN: complete job GPUh can become available long after label origin','V28R2_fit_period':['2024-08-19','2025-03-30 or 31'],'V28R2_independent_split_evidence':'no independent calibration/test split in fit_all; training-only quantile-integrity status is not forecast accuracy validation'})
    dump('V40P_TRUE_HOLDOUT_AUDIT.json',{'A':{'TRUE_FROZEN_HOLDOUT_AVAILABLE':'NO','reason':'2024 OOF was used for model family/objective/scale/iterations. 2025 was already evaluated by historical frozen and monthly-walkforward pipelines; no chain-of-custody proves zero later family-selection/test reuse.'},'B':{'TRUE_FROZEN_HOLDOUT_AVAILABLE':'NO','reason':'Same provenance limitations; persistence vs residual selection used 2024 OOF; test untouchedness not provable.'},'TEST_REUSE_OR_SELECTION_LEAKAGE':'INDEPENDENCE_UNPROVEN; no direct test-driven K5B2 hyperparameter tuning found in recovered fit script. Do not equate prior evaluation alone with proven tuning.','diagnostic_clones':'retrospective architecture-fixed assessment only; F1/F2 spec selected with later-2024 information; not nested prospective validation'})
    dump('V40P_DATASET_IDENTITY_AUDIT.json',{'A':{'TRAIN_FACILITY':'NLR/NREL ESIF Kestrel H100','VALIDATION_FACILITY':'same Kestrel trace','TARGET_FACILITY':'same Kestrel, 2025 Jan-Apr24 block','DEPLOYMENT_SEMANTICS':'synthetic assignment to 12 IDC sites; forecasting F30 completed/non-standby population, not whole facility','Eagle_trace_used':False},'B':{'TRAIN_FACILITY':'same Kestrel H100 jobs','VALIDATION_FACILITY':'same Kestrel','TARGET_FACILITY':'same Kestrel','DEPLOYMENT_SEMANTICS':'non-F30 Kestrel GPU occupancy, not Eagle power or facility PUE','Eagle_trace_used':False},'historical_DayAhead':{'P_REF':'ESIF combined buildingData PUE dataset it_power_kw column, source facility boundary not uniquely proven to equal Kestrel H100','G_REF':'Kestrel H100 completed occupancy','W':'Kestrel strict full-node arrivals','power_coefficients':'separate NLR D312/GenAI experiment authority','synthetic_inference_load':'BurstGPT token-aware separate trace in legacy K5C2, outside these primary targets'},'primary_source_SHA256':late['source_SHA256']})
    dump('V40P_FACILITY_MIXING_AUDIT.json',{'Eagle_fixed_plus_Kestrel_flex':'NOT_THE_K5B2_IMPLEMENTATION','same_facility_ground_truth_claim_supported':False,'construction':'A: SYNTHETIC_COMPOSITE_AIDC_WORKLOAD_CONSTRUCTION','reason':'12 engineered IDC assignments, separate power/inference data, Melbourne calendar applied to Kestrel source; historical ESIF IT power + H100 subset are distinct measurement boundaries','not_automatic_failure':'Different trace components are permissible as stated modeling assumptions; cannot claim one measured Melbourne facility'})
    dump('V40P_KNOWN_FUTURE_DOUBLECOUNT_AUDIT.json',{'literal_origin_rule':'known submit<=t0 versus A target submit in [t0+5min,t0+h+5min)','identity_overlap_checks':len(late['known_future_checks']),'overlap_total':late['known_future_overlap_total'],'status':'NO_OVERLAP_IN_INDEPENDENT_SAFE_RAW_JOB_CHECKS','gap':'submissions inside (t0,t0+5min) omitted from next-bin target while current feature may already see them','current_DayAhead':'No future arrival component in submitted-job ledger; no numerical May replay read','limitation':'No shared job-ID interface exists between aggregate legacy model and current ledger; end-to-end runtime doublecount cannot be fully certified by aggregate predictions alone','evidence':evidence('dayahead/v37/aidc_materializer.py','pending = submit.le(cutoff)')})
    identity=(data.fixed_avg_active_gpus_F30+data.flexible_avg_active_gpus_F30-data.total_avg_active_gpus).abs()
    dump('V40P_FIXED_FLEXIBLE_SEPARATION_AUDIT.json',{'legacy_F30':'runtime>=30min AND observed queue>=15min; fixed=complement in primary clean cohort','raw_jobs_checked':late['safe_job_count'],'fixed_jobs':late['F30_fixed_count'],'flexible_jobs':late['F30_flexible_count'],'fixed_flexible_job_overlap':late['fixed_flexible_overlap'],'time_series_rows':len(data),'max_abs_fixed_plus_flex_minus_total':identity.max(),'retrospective_identity_pass':identity.max()<1e-8,'causal_partition_pass':False,'current_DayAhead':'RUNNING and protected/unknown QoS fixed; normal/standby pending temporally controllable per submission-side rules; different semantics from retrospective F30','evidence':evidence('dayahead/v37/aidc_materializer.py','def _classify_pending')})
    dump('V40P_DAYAHEAD_INTEGRATION_AUDIT.json',{'legacy_K5B2':'K5A -> K5B2 selected forecast -> K5C2 site shares; deterministic arrival benchmark, event probabilities feed scenario path; K5C3 fixed 48-step interpolation','historical_V28R2':'P_Q90/G_Q90 references minus controlled reference service plus scheduled flexible service; residual decomposition, not independent fixed+flex addition','current_V40A':'V37 known RUNNING/PENDING ledger, V39A synthetic capacity-idle plus active GPU swing, C1 cooling + fixed PF; load_planning_context has no K5B2 or V28R2 forecast invocation','current_total_formula':'site_capacity*idle_W_per_GPU + active_known_job_GPU*CENTER_SWING_W_per_GPU, then C1; future unsubmitted arrival component absent','future_LightGBM_adequacy_validates_current_closed_cohort':'NO','V40N_reads':0,'evidence':[evidence('dayahead/v40a/context.py','from dayahead.v39a.power'),evidence('dayahead/v39a/power.py','Decimal(active) * CENTER_SWING_W_PER_GPU'),evidence('dayahead/v28r2/reference_delta.py','raw_p = mapped_p - p_fixed'),evidence('dayahead/v37/aidc_materializer.py','not_yet_submitted_at_issue_excluded')]})
    dump('audit_execution_summary.json',{'feature_classes':counts,'feature_reconstruction_failures':[r for r in checks if not r['algorithm_match']],'late_jobs':late['late_lag1_mark_jobs'],'model_count_verified':json.loads((OUT/'V40P_MODEL_SHA_VERIFICATION.json').read_text())['total_model_count']})
    print(json.dumps({'class_counts':counts,'feature_reconstruction_failures':sum(not r['algorithm_match'] for r in checks),'all_model_hashes_match':json.loads((OUT/'V40P_MODEL_SHA_VERIFICATION.json').read_text())['all_match']},indent=2))

if __name__=='__main__':main()
