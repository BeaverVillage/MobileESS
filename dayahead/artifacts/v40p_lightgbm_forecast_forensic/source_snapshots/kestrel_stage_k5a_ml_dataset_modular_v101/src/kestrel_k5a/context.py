from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class PipelineContext:
    config: dict[str, Any]
    package_root: Path
    config_path: Path
    run_tag: str
    run_dir: Path
    input_dir: Path
    output_dir: Path
    report_dir: Path
    log_dir: Path
    publish_dir: Path
    review_root: Path
    stage_k35_source_dir: Path | None = None
    stage_k4b_source_dir: Path | None = None
    jobs_path: Path | None = None
    dense_path: Path | None = None
    k4b_training_power_path: Path | None = None

    @classmethod
    def create(cls, config: dict[str, Any], package_root: Path, config_path: Path) -> 'PipelineContext':
        run_tag = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = Path(config['paths']['wsl_work_root']) / f'stage_k5a_{run_tag}'
        ctx = cls(
            config=config,
            package_root=package_root,
            config_path=config_path,
            run_tag=run_tag,
            run_dir=run_dir,
            input_dir=run_dir/'input',
            output_dir=run_dir/'outputs',
            report_dir=run_dir/'reports',
            log_dir=run_dir/'logs',
            publish_dir=Path(config['paths']['publish_root']) / f'stage_k5a_{run_tag}',
            review_root=Path(config['paths']['review_root']),
        )
        for p in [ctx.input_dir, ctx.output_dir, ctx.report_dir, ctx.log_dir, ctx.review_root]:
            p.mkdir(parents=True, exist_ok=True)
        return ctx
