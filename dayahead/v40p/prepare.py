"""Phase A only, then write immutable diagnostic registration. Never fit here."""
from .common import *
import lightgbm as lgb
import re, shutil, yaml

def main():
    fd=pd.read_csv(K5A/'outputs/feature_dictionary.csv')
    td=pd.read_csv(K5A/'outputs/target_dictionary.csv').query("primary_role == 'primary'")
    features=fd.feature_column.tolist()
    config=yaml.safe_load((K5B2/'pipeline_used.yaml').read_text(encoding='utf-8'))
    meta=json.loads((K5B2/'outputs/final_model_metadata.json').read_text())
    receipts={r['relative_path']:r['sha256'] for r in json.loads((K5B2/'manifest.json').read_text())}
    for path in [K5A/'outputs/feature_dictionary.csv',K5A/'outputs/target_dictionary.csv',K5A/'outputs/rolling_origin_folds.csv',K5A/'outputs/split_summary.csv',K5B2/'pipeline_used.yaml',K5B2/'outputs/final_model_metadata.json',K5B2/'outputs/iteration_map.json',K5B2/'metrics/model_selection.csv',K5B2/'metrics/calibration_parameters.csv',K5B2/'reports/dataset_metadata.json',K5B2/'reports/input_metadata.json']:
        dest=OUT/'evidence'/('K5B2' if path.is_relative_to(K5B2) else 'K5A')/path.name
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        record_access(path,'PRE2025_SELECTION_OR_SOURCE_METADATA')
    data=read_pre_may(K5A/'outputs/kestrel_ml_features_global_5min.parquet')
    data=data.loc[data.timestamp_utc.between('2025-01-01', '2025-04-24 14:55:00+00:00')].copy()
    data[features]=data[features].astype(np.float32)
    historical={}
    for family,prefix,file in [('A','flexible','idc_flexible_deterministic_benchmark_2025_long.parquet'),('B','fixed','idc_fixed_forecast_2025_long.parquet')]:
        cols=['timestamp_utc','horizon_steps','idc_id',prefix+'_selected_prediction']
        if family=='B':cols+=['fixed_training_incremental_selected_prediction_kw']
        h=read_pre_may(BASE/'stage_k5c2_20260722_232023/outputs'/file,cols)
        grouped=h.groupby(['timestamp_utc','horizon_steps'])
        counts=grouped.idc_id.nunique();sums=grouped.sum(numeric_only=True)
        historical[family]=sums.loc[counts.eq(12)]
    models=[];reproduction=[];outputs=[];specs=[]
    main_source=OUT/'source_snapshots/kestrel_stage_k5b2_zero_inflated_modular_v101/src/kestrel_k5b2/modeling.py'
    for row in td.itertuples():
        family='B' if row.target_type=='point_at_horizon' else 'A'
        role='fixed_residual' if family=='B' else 'tweedie'
        entries=[m for m in meta if m['target_column']==row.target_column and m['model_role']==role]
        m=entries[0] if entries else {'method':'persistence','n_estimators':0}
        params=dict(config['models']['base_parameters'],random_state=config['resources']['random_seed'],n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True,n_estimators=m['n_estimators'])
        params['objective']='tweedie' if family=='A' else 'regression_l1'
        if family=='A':params.update(tweedie_variance_power=1.7,metric='mae')
        path=K5B2/'models/frozen_selected'/f'{row.target_column}__{m["method"]}.txt'
        if entries:
            text=path.read_text();booster=lgb.Booster(model_str=text)
            assert booster.feature_name()==features
            p1=np.asarray(booster.predict(data[features],num_threads=4))
            p2=np.asarray(booster.predict(data[features],num_threads=4))
            assert np.array_equal(p1,p2)
            pred=np.maximum(p1*float(m.get('scale',1)) if family=='A' else p1+data[row.source_metric].to_numpy(),0)
            dsha=digest(path)
            check=dsha==receipts[path.relative_to(K5B2).as_posix()]
            dest=OUT/'frozen_models'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(path,dest)
            record_access(path,'FROZEN_MODEL')
            serialized_params=dict(re.findall(r'^\[([^:]+): (.*)\]$',text,re.M))
            models.append({'model_id':path.stem,'track':family,'model_family':m['method'],'model_SHA256':dsha,'receipt_SHA256':receipts[path.relative_to(K5B2).as_posix()],'SHA_match':check,'training_script':str(main_source.relative_to(ROOT)),'training_script_SHA256':digest(main_source),'training_timestamp':'2026-07-21 16:46-17:08 Asia/Seoul (run-directory/config evidence; not embedded model timestamp)','training_data':str(K5A/'outputs/kestrel_ml_development_2024.parquet'),'training_date_range':['2024-02-29T23:00:00Z','2024-12-31T19:55:00Z'],'validation_data':'Sep-Dec 2024 expanding OOF reused for family, tree-count and scale selection','test_data':'2025 full-year reported historically; V40P reads physically separated Jan-Apr24 only','target':row.target_column,'target_unit':'GPU-hours' if family=='A' else 'average active GPUs in 5-minute bin','horizon_minutes':row.horizon_minutes,'loss_objective':params['objective'],'hyperparameters':params,'serialized_parameters':serialized_params,'tree_count':booster.num_trees(),'feature_list':features,'feature_order':features,'categorical_handling':'none; numeric float32','random_seed':20260721,'inference_adapter':'nonnegative(0.5*Tweedie)' if family=='A' else 'nonnegative(current fixed bin+residual)','downstream_consumer':'K5C2/K5C3 legacy runtime; not current V37 job-ledger arrival authority','feature_gain':dict(zip(features,booster.feature_importance('gain'))),'feature_split_count':dict(zip(features,booster.feature_importance('split')))} )
        else:
            pred=data[row.source_metric].to_numpy();check=True;dsha=None
        h=historical[family].xs(row.horizon_steps,level=1)
        col=('flexible' if family=='A' else 'fixed')+'_selected_prediction'
        pred_s=pd.Series(pred,index=data.timestamp_utc)
        common=h.index.intersection(pred_s.index)
        diff=np.abs(pred_s.loc[common].to_numpy()-h.loc[common,col].to_numpy())
        reproduction.append({'track':family,'horizon_minutes':row.horizon_minutes,'model_sha256':dsha,'SHA_match':check,'feature_order_exact':True,'deterministic_max_abs_difference':0.,'saved_prediction_comparison_source':'sum of all 12 K5C2 shares, only complete pre-May row-group 0 groups','comparison_rows':len(common),'saved_prediction_max_abs_difference':float(diff.max()),'reproduced_within_1e-9':bool(diff.max()<1e-9)})
        outputs.append(pd.DataFrame({'timestamp_utc':data.timestamp_utc,'track':family,'horizon_minutes':row.horizon_minutes,'target':row.target_column,'model':m['method'],'prediction':pred,'actual':data[row.target_column],'phase':'FROZEN_2025_PREMAY','fold':'FROZEN','training_end':'2024-12-31T19:55:00Z'}))
        specs.append({'track':family,'target':row.target_column,'source_metric':row.source_metric,'horizon_minutes':row.horizon_minutes,'horizon_steps':row.horizon_steps,'method':m['method'],'frozen_model':str(dest.relative_to(ROOT)) if entries else None,'hyperparameters':params,'scale':m.get('scale',1),'target_transform':'none','adapter':'max(0, raw*scale)' if family=='A' else 'persistence or max(0,current+residual)'})
    # Diagnostic event classifiers are audited but are not multiplied into the point forecast.
    for m in [x for x in meta if x['model_role']=='event_classifier_diagnostic']:
        path=K5B2/'models/frozen_selected'/f'{m["target_column"]}__event_classifier.txt'
        record_access(path,'DIAGNOSTIC_MODEL_SHA_ONLY')
        models.append({'model_id':path.stem,'track':'A','role':'independent event diagnostic, not point forecast','model_SHA256':digest(path),'receipt_SHA256':receipts[path.relative_to(K5B2).as_posix()],'SHA_match':digest(path)==receipts[path.relative_to(K5B2).as_posix()],'target':m['target_column']+' > 0','n_estimators':m['n_estimators'],'event_threshold':m['event_threshold'],'feature_order':features})
    pd.concat(outputs).to_parquet(OUT/'frozen_predictions.parquet',index=False)
    dump('V40P_MODEL_SOURCE_CENSUS.json',{'primary_family':'K5B2','models':models,'persistence_h15_has_no_model_file':True,'repository_DayAhead_families':'V28 Tweedie daily; V28R2 P/G/W quantile: separately inventoried in lineage report'})
    dump('V40P_MODEL_SHA_VERIFICATION.json',{'models':[{k:m.get(k) for k in ['model_id','model_SHA256','receipt_SHA256','SHA_match']} for m in models],'all_match':all(m['SHA_match'] for m in models)})
    dump('V40P_FROZEN_INFERENCE_REPRODUCTION.json',{'phase_A_no_fit':True,'results':reproduction})
    spec={'registration_status':'WRITTEN_BEFORE_ANY_DIAGNOSTIC_FIT','models':specs,'feature_order':features,'feature_dictionary_sha256':digest(K5A/'outputs/feature_dictionary.csv'),'modeling_source_sha256':digest(main_source),'original_training_start':'2024-02-29T23:00:00Z','folds':[{'id':'F1_2024_09','evaluation_start':'2024-09-01T00:00:00Z','evaluation_end_exclusive':'2024-10-01T00:00:00Z'},{'id':'F2_2024_11','evaluation_start':'2024-11-01T00:00:00Z','evaluation_end_exclusive':'2024-12-01T00:00:00Z'},{'id':'F3_2025_03','evaluation_start':'2025-03-01T00:00:00Z','evaluation_end_exclusive':'2025-04-01T00:00:00Z'}],'purge':'training row timestamp + 245 minutes < fold start; evaluation row timestamp + 245 minutes < fold end','regime':'FORENSIC DIAGNOSTIC CLONE FIT; expanding train, frozen selected params/tree counts/scale; no early stopping or tuning','causality_caveat':'Original retrospective features preserved, including observed complete-runtime arrival marks and current interval aggregates. Results are conditional diagnostics, not causal deployment evidence. Global final hyperparameters reflect later 2024 selection for F1/F2. No true nested out-of-time model selection claim.','baselines':{'A0_ZERO':'primary A: identically zero, causal','A1_RECENT_RATE':'diagnostic only: previous h bins inclusive current * no new mapping; uses retrospective realized GPU-hours, not proven causal','A2_DAILY_SEASONAL':'diagnostic only: prior local-clock day target; full realized job mark availability unproven; ambiguous/nonexistent DST clock omitted','A3_WEEKLY_SEASONAL':'diagnostic only: previous local weekday-clock target; same availability caveat','B0_PERSISTENCE':'primary B comparator: same current fixed state used by frozen residual adapter; conditional retrospective benchmark, not proven live causal','B1_DAILY_SEASONAL':'prior local-clock day target','B2_WEEKLY_SEASONAL':'prior local weekday-clock target'},'primary_metric':'MAE skill vs A0_ZERO / B0_PERSISTENCE; CI strictly >0 required for superiority, plus causality gate','metrics':['N','actual_sum','predicted_sum','MAE','RMSE','WAPE','bias','median_signed_error','underprediction_rate','shortfall','overreservation','normalized_shortfall','normalized_overreservation','zero_actual_fraction','Tweedie_deviance_p1.7 (A only)','max_abs_error','max_underprediction'],'bootstrap':{'unit':'UTC calendar day; stratify by temporal fold for pooled clone metrics','replicates':2000,'seed':20260906,'confidence':.95,'metrics':['MAE','RMSE','WAPE','bias','normalized_shortfall','normalized_overreservation','skill_MAE','skill_RMSE','skill_WAPE']},'subgroups':{'burst_top10':'strictly above each training fold target q90, ties excluded; thresholds never from evaluation','burst_top5':'strictly above each training fold target q95; zero threshold flagged, positive-only q95 supplemental','shift_continuous':'P5/median/P95 and Wasserstein; fixed preselected source variables','shift_categorical':'TV distance for local hour, weekday, month, and raw job QoS/partition/hardware if raw authority accessible'},'skill_gates':{'superiority':'primary MAE skill lower95>0 and no causal failure','underforecast_alert':'normalized_shortfall>0.25 or abs(negative relative bias)>0.20; descriptive chosen threshold','burst_alert':'top5 recall<0.50','shift_alert':'distribution summaries descriptive; no p-value-only verdict'},'horizon_consistency':'raw point outputs; count adjacent cumulative crossings; never repair','power_equivalent':'only existing frozen K5C2 coefficient recovered from saved GPU-to-power pair; no energy interpretation of cumulative arrival reservation','immutable_after_registration':['model spec','feature set/order','objective','tree counts','scale','folds','baselines','metrics','subgroups','bootstrap seed']}
    dump('V40P_BACKTEST_PREREGISTRATION.json',spec)
    (OUT/'V40P_BACKTEST_PREREGISTRATION.md').write_text('# V40P preregistration\n\nThe JSON is the exact registered specification. Three non-overlapping folds: September 2024, November 2024, March 2025. Freeze the original architecture, 177 features, objectives, fitted tree counts, seeds and 0.5 arrival scale. No result-driven refit changes. Causal failures in the original input construction are retained and reported, not repaired. Diagnostic results do not validate those inputs.\n\nPrimary: MAE skill against zero arrivals and fixed-state persistence. UTC daily block bootstrap, 2,000 replicates, seed 20260906. Burst cutoffs use each fold training targets only.\n',encoding='utf-8')
    print(json.dumps(reproduction,indent=2))

if __name__=='__main__':main()
