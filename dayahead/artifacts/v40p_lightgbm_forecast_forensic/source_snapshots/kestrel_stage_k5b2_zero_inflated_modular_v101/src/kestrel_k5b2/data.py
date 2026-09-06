from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json, logging
import numpy as np, pandas as pd, pyarrow.parquet as pq
from .context import PipelineContext
from .utils import write_json

@dataclass
class DataBundle:
    development: pd.DataFrame; test: pd.DataFrame; combined: pd.DataFrame; features: list[str]
    targets: pd.DataFrame; folds: pd.DataFrame; source_metrics: list[str]
    k5b_validation: pd.DataFrame|None=None; k5b_test: pd.DataFrame|None=None; k5b_best_params: pd.DataFrame|None=None

def _csv(p): return pd.read_csv(p,encoding='utf-8-sig')
def _schema(p): return set(pq.ParquetFile(p).schema.names)
def _load(p,cols):
    f=pd.read_parquet(p,columns=cols,engine='pyarrow'); f['timestamp_utc']=pd.to_datetime(f['timestamp_utc'],utc=True)
    return f.sort_values('timestamp_utc').reset_index(drop=True)

def load_data(ctx: PipelineContext, logger: logging.Logger) -> DataBundle:
    if json.loads(ctx.k5a_validation_path.read_text(encoding='utf-8')).get('status')!='success': raise ValueError('K5-A not successful')
    fd=_csv(ctx.feature_dictionary_path); td=_csv(ctx.target_dictionary_path); folds=_csv(ctx.folds_path)
    features=fd['feature_column'].drop_duplicates().astype(str).tolist()
    targets=td.loc[td['primary_role'].astype(str).eq('primary')].copy()
    targets['horizon_steps']=pd.to_numeric(targets['horizon_steps']).astype(int); targets['horizon_minutes']=pd.to_numeric(targets['horizon_minutes']).astype(int)
    targets['target_family']=targets['source_metric'].astype(str)+'__'+targets['target_type'].astype(str)
    targets=targets.sort_values(['target_type','horizon_steps']).reset_index(drop=True)
    tcols=targets['target_column'].astype(str).tolist(); sources=targets['source_metric'].drop_duplicates().astype(str).tolist()
    if set(features)&set(tcols): raise ValueError('Target leakage in feature dictionary')
    cols=list(dict.fromkeys(['timestamp_utc','dataset_split']+features+tcols+sources))
    missdev=set(cols)-_schema(ctx.development_path); misstest=set(cols)-_schema(ctx.test_path)
    if missdev or misstest: raise KeyError({'missing_dev':sorted(missdev),'missing_test':sorted(misstest)})
    dev=_load(ctx.development_path,cols); test=_load(ctx.test_path,cols)
    for name,f in [('development',dev),('test',test)]:
        if f['timestamp_utc'].duplicated().any(): raise ValueError(f'Duplicate timestamps in {name}')
        for c in features: f[c]=pd.to_numeric(f[c],errors='coerce').astype(np.float32)
        for c in tcols+sources: f[c]=pd.to_numeric(f[c],errors='coerce').astype(np.float64)
        if np.isinf(f[features].to_numpy(dtype=float)).any(): raise ValueError(f'Infinite feature in {name}')
    for c in ['train_feature_end_utc','validation_start_utc','validation_feature_end_utc']: folds[c]=pd.to_datetime(folds[c],utc=True)
    combined=pd.concat([dev.assign(_origin='development'),test.assign(_origin='test')],ignore_index=True).sort_values('timestamp_utc').reset_index(drop=True)
    kv=kt=bp=None
    if ctx.k5b_validation_predictions_path:
        kv=pd.read_parquet(ctx.k5b_validation_predictions_path,columns=['timestamp_utc','target_column','actual','lgbm_point'])
        kt=pd.read_parquet(ctx.k5b_test_predictions_path,columns=['timestamp_utc','target_column','actual','lgbm_point'])
        kv['timestamp_utc']=pd.to_datetime(kv['timestamp_utc'],utc=True); kt['timestamp_utc']=pd.to_datetime(kt['timestamp_utc'],utc=True)
        bp=pd.read_csv(ctx.k5b_best_params_path)
    write_json(ctx.report_dir/'dataset_metadata.json',{'feature_count':len(features),'target_count':len(targets),'development_rows':len(dev),'test_rows':len(test),'k5b_benchmark_available':kv is not None,'development_start':dev.timestamp_utc.min(),'development_end':dev.timestamp_utc.max(),'test_start':test.timestamp_utc.min(),'test_end':test.timestamp_utc.max()})
    logger.info('Loaded %d features, %d targets, %d development and %d test rows',len(features),len(targets),len(dev),len(test))
    return DataBundle(dev,test,combined,features,targets,folds,sources,kv,kt,bp)
