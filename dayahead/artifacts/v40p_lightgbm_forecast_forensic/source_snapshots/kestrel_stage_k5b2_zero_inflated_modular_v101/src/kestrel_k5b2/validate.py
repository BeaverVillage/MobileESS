from __future__ import annotations
import json, logging
import numpy as np, pandas as pd, pyarrow.parquet as pq
from .context import PipelineContext
from .data import DataBundle
from .modeling import Results
from .utils import write_json

def validate_stage(ctx,data,res,logger):
    vp=pd.read_parquet(res.validation_predictions_path); fr=pd.read_parquet(res.frozen_predictions_path); wf=pd.read_parquet(res.walkforward_predictions_path)
    target_count=len(data.targets); expected_frozen=len(data.test)*target_count
    checks={
      'development_test_overlap_zero':len(set(data.development.timestamp_utc)&set(data.test.timestamp_utc))==0,
      'test_only_2025':sorted(data.test.timestamp_utc.dt.year.unique().tolist())==[2025],
      'feature_target_overlap_zero':not bool(set(data.features)&set(data.targets.target_column)),
      'frozen_rows_complete':len(fr)==expected_frozen,
      'walkforward_rows_complete':len(wf)==expected_frozen,
      'selected_predictions_nonnegative':float(min(fr.selected_prediction.min(),wf.selected_prediction.min()))>=-1e-9,
      'selected_predictions_no_null':int(fr.selected_prediction.isna().sum()+wf.selected_prediction.isna().sum())==0,
      'interval_monotone':bool(((fr.prediction_p10<=fr.prediction_p50)&(fr.prediction_p50<=fr.prediction_p90)).all()),
      'selection_complete':len(res.selection)==target_count,
      'fixed_has_persistence_fallback':all(res.selection.loc[res.selection.family=='fixed','selected_method'].isin(['persistence','residual_l1','residual_l2','residual_huber'])),
      'flexible_selected_from_valid_methods':all(res.selection.loc[res.selection.family=='flexible','selected_method'].isin(['zero','historical_mean','persistence','seasonal_daily','seasonal_weekly','hurdle_log_l1_expected','hurdle_log_l2_expected','hurdle_log_l1_gate','hurdle_log_l2_gate','tweedie_1.1','tweedie_1.3','tweedie_1.5','tweedie_1.7','standard_l1'])),
    }
    failed=[k for k,v in checks.items() if not v]
    payload={'status':'success' if not failed else 'failure','checks':checks,'failed_checks':failed,'metrics':{'feature_count':len(data.features),'target_count':target_count,'validation_rows':len(vp),'frozen_rows':len(fr),'walkforward_rows':len(wf),'frozen_expected_rows':expected_frozen,'selected_methods':res.selection.to_dict(orient='records')}}
    write_json(ctx.report_dir/'validation.json',payload)
    write_json(ctx.report_dir/'leakage_audit.json',{'development_max':data.development.timestamp_utc.max(),'test_min':data.test.timestamp_utc.min(),'frozen_training':'2024 development only','walkforward_training':'expanding history ending before each forecast month with target-horizon purge','test_used_for_frozen_model_selection':False,'2025_prior_months_used_only_in_walkforward_sensitivity':True})
    if failed: raise RuntimeError(f'K5-B2 validation failed: {failed}')
    logger.info('Stage K5-B2 validation passed'); return payload
