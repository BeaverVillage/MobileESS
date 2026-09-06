from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

@dataclass
class PipelineContext:
    config: dict[str,Any]; package_root: Path; config_path: Path; run_tag: str
    run_dir: Path; input_dir: Path; output_dir: Path; model_dir: Path; prediction_dir: Path
    metric_dir: Path; report_dir: Path; log_dir: Path; publish_dir: Path; review_root: Path
    stage_k5a_source_dir: Path|None=None; stage_k5b_source_dir: Path|None=None
    development_path: Path|None=None; test_path: Path|None=None; feature_dictionary_path: Path|None=None
    target_dictionary_path: Path|None=None; folds_path: Path|None=None; split_summary_path: Path|None=None
    k5a_validation_path: Path|None=None; k5b_validation_predictions_path: Path|None=None
    k5b_test_predictions_path: Path|None=None; k5b_best_params_path: Path|None=None; k5b_metrics_path: Path|None=None

    @classmethod
    def create(cls, config, package_root, config_path):
        tag=datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir=Path(config['paths']['wsl_work_root'])/f'stage_k5b2_{tag}'
        ctx=cls(config,package_root,config_path,tag,run_dir,run_dir/'input',run_dir/'outputs',run_dir/'models',
                run_dir/'predictions',run_dir/'metrics',run_dir/'reports',run_dir/'logs',
                Path(config['paths']['publish_root'])/f'stage_k5b2_{tag}',Path(config['paths']['review_root']))
        for p in [ctx.input_dir,ctx.output_dir,ctx.model_dir,ctx.prediction_dir,ctx.metric_dir,ctx.report_dir,ctx.log_dir,ctx.review_root]: p.mkdir(parents=True,exist_ok=True)
        return ctx
