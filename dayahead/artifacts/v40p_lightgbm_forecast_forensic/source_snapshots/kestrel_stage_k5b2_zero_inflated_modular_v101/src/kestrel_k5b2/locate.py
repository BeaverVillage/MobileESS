from __future__ import annotations
from pathlib import Path
from typing import Iterable
import json, logging, psutil
from .context import PipelineContext
from .utils import copy_file, sha256_file, write_json

K5A_REQUIRED={
 'development':'outputs/kestrel_ml_development_2024.parquet','test':'outputs/kestrel_ml_test_2025.parquet',
 'feature_dictionary':'outputs/feature_dictionary.csv','target_dictionary':'outputs/target_dictionary.csv',
 'folds':'outputs/rolling_origin_folds.csv','split_summary':'outputs/split_summary.csv','validation':'reports/validation.json'}
K5B_OPTIONAL={
 'validation_predictions':'predictions/validation_oof_predictions.parquet','test_predictions':'predictions/test_2025_frozen_predictions.parquet',
 'best_params':'metrics/best_hyperparameters.csv','metrics':'metrics/test_2025_metrics.csv','validation':'reports/validation.json'}

def _success(directory: Path, required: dict) -> bool:
    try:
        v=json.loads((directory/required['validation']).read_text(encoding='utf-8'))
        return v.get('status')=='success' and all((directory/r).exists() for r in required.values())
    except Exception: return False

def _latest(root: Path, pattern: str, required: dict) -> Path|None:
    if not root.exists(): return None
    c=[p for p in root.glob(pattern) if p.is_dir() and _success(p,required)]
    return max(c,key=lambda p:p.stat().st_mtime) if c else None

def locate_inputs(ctx: PipelineContext, logger: logging.Logger) -> None:
    explicit=str(ctx.config['paths'].get('stage_k5a_input_dir','')).strip()
    if explicit:
        k5a=Path(explicit)
        if not _success(k5a,K5A_REQUIRED): raise ValueError(f'Invalid Stage K5-A result: {k5a}')
    else:
        k5a=_latest(Path(ctx.config['paths']['stage_search_root']),'stage_k5a_*',K5A_REQUIRED)
        if k5a is None: raise FileNotFoundError('No successful Stage K5-A result found')
    ctx.stage_k5a_source_dir=k5a
    source={k:k5a/r for k,r in K5A_REQUIRED.items()}
    free=psutil.disk_usage(str(ctx.run_dir.parent)).free/(1024**3)
    if free<float(ctx.config['resources'].get('minimum_free_disk_gib',0)): raise OSError(f'Insufficient free disk: {free:.2f} GiB')
    runtime={k:(copy_file(p,ctx.input_dir) if ctx.config['paths'].get('copy_inputs_to_wsl',True) else p) for k,p in source.items()}
    ctx.development_path=runtime['development']; ctx.test_path=runtime['test']; ctx.feature_dictionary_path=runtime['feature_dictionary']
    ctx.target_dictionary_path=runtime['target_dictionary']; ctx.folds_path=runtime['folds']; ctx.split_summary_path=runtime['split_summary']; ctx.k5a_validation_path=runtime['validation']

    k5b_exp=str(ctx.config['paths'].get('stage_k5b_input_dir','')).strip()
    k5b=None
    if k5b_exp:
        p=Path(k5b_exp); k5b=p if _success(p,K5B_OPTIONAL) else None
    else:
        k5b=_latest(Path(ctx.config['paths']['stage_search_root']),'stage_k5b_[0-9]*',K5B_OPTIONAL)
    if k5b:
        ctx.stage_k5b_source_dir=k5b
        ctx.k5b_validation_predictions_path=k5b/K5B_OPTIONAL['validation_predictions']
        ctx.k5b_test_predictions_path=k5b/K5B_OPTIONAL['test_predictions']
        ctx.k5b_best_params_path=k5b/K5B_OPTIONAL['best_params']; ctx.k5b_metrics_path=k5b/K5B_OPTIONAL['metrics']
        logger.info('Selected optional Stage K5-B benchmark: %s',k5b)
    else: logger.warning('No full Stage K5-B result found; standard-L1 benchmark predictions will be omitted.')
    meta={'stage_k5a_source_dir':k5a,'stage_k5b_source_dir':k5b,'disk_free_gib_before_run':round(free,3),'files':{}}
    for k,p in source.items(): meta['files'][k]={'path':p,'size_bytes':p.stat().st_size,'sha256':sha256_file(p)}
    write_json(ctx.report_dir/'input_metadata.json',meta); logger.info('Selected Stage K5-A source: %s',k5a)
