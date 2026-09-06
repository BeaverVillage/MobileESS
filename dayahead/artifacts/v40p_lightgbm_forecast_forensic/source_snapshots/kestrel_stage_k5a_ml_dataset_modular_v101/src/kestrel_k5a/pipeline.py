from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .context import PipelineContext
from .features import build_ml_feature_tables
from .lineage import audit_lineage
from .locate import locate_inputs
from .paired_power import build_paired_power_scenarios
from .splits import build_split_tables
from .utils import (
    dataframe_to_markdown,
    sha256_file,
    write_json,
    zip_review,
)
from .validate import validate_stage
from .workload import build_workload_tables


def write_report(
    ctx: PipelineContext,
    validation: dict[str, Any],
    lineage: pd.DataFrame,
    split_summary: pd.DataFrame,
    folds: pd.DataFrame,
    paired_power: pd.DataFrame,
) -> None:
    metrics = validation["metrics"]
    lines = [
        "# Kestrel Stage K5-A ML Dataset Report",
        "",
        f"- Run tag: `{ctx.run_tag}`",
        f"- Status: `{validation['status']}`",
        f"- Analysis start: `{metrics['analysis_start_utc']}`",
        f"- Analysis end: `{metrics['analysis_end_utc']}`",
        f"- Global 5-minute rows: `{metrics['global_workload_rows']:,}`",
        f"- 12-IDC workload rows: `{metrics['site_workload_rows']:,}`",
        f"- IDC count: `{metrics['idc_count']}`",
        f"- Cropped GPU-hour relative error: `{metrics['gpu_hour_relative_error']:.3e}`",
        f"- Fixed+flexible maximum identity error: `{metrics['maximum_fixed_flexible_identity_error']:.3e}`",
        "",
        "## Timestamp lineage",
        "",
        dataframe_to_markdown(lineage, max_rows=10),
        "",
        "## Train, validation, and test splits",
        "",
        dataframe_to_markdown(split_summary, max_rows=10),
        "",
        "## Rolling-origin folds",
        "",
        dataframe_to_markdown(folds, max_rows=10),
        "",
        "## Paired H100 power scenarios",
        "",
        dataframe_to_markdown(
            paired_power[
                [
                    "scenario",
                    "paired_run_id",
                    "model_family",
                    "gross_it_kw_per_gpu",
                    "idle_it_kw_per_gpu",
                    "incremental_it_kw_per_gpu",
                ]
            ]
            if not paired_power.empty
            else paired_power,
            max_rows=10,
        ),
        "",
        "## Primary forecasting targets",
        "",
        "1. Future F30 fixed average active GPUs at 15, 30, 60, 120, and 240 minutes.",
        "2. Cumulative F30 flexible GPU-hour arrivals over the next 15, 30, 60, 120, and 240 minutes.",
        "3. Total and flexible active GPUs are retained as comparison targets.",
        "",
        "## Leakage controls",
        "",
        "1. All feature lags and rolling windows use current or historical observations only.",
        "2. Four hours are purged at every train, validation, and test boundary.",
        "3. The 2025 holdout is not used for hyperparameter selection.",
        "4. Feature scaling is deferred to Stage K5-B and must be fitted on training rows only.",
        "",
        "## Data interpretation",
        "",
        "The primary ML dataset represents one Kestrel H100 workload trace. The 12-IDC table is a deterministic multi-site partition and is not twelve independent measured data centers.",
        "",
    ]
    (ctx.report_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def publish(ctx: PipelineContext, logger: logging.Logger) -> None:
    if ctx.publish_dir.exists():
        raise FileExistsError(ctx.publish_dir)
    ctx.publish_dir.mkdir(parents=True)
    for name in ["outputs", "reports", "logs"]:
        source = ctx.run_dir / name
        if source.exists():
            shutil.copytree(source, ctx.publish_dir / name)
    shutil.copy2(ctx.config_path, ctx.publish_dir / "pipeline_used.yaml")

    manifest = []
    for path in sorted(ctx.publish_dir.rglob("*")):
        if path.is_file():
            manifest.append(
                {
                    "relative_path": str(path.relative_to(ctx.publish_dir)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    write_json(ctx.publish_dir / "manifest.json", manifest)
    review_zip = ctx.review_root / f"stage_k5a_kestrel_ml_review_{ctx.run_tag}.zip"
    zip_review(ctx.publish_dir, review_zip)
    logger.info("Published: %s", ctx.publish_dir)
    logger.info("Review ZIP: %s", review_zip)


def run_pipeline(ctx: PipelineContext, logger: logging.Logger) -> None:
    started = time.time()
    stage_times: dict[str, float] = {}
    try:
        stage_started = time.time()
        locate_inputs(ctx, logger)
        stage_times["locate"] = round(time.time() - stage_started, 3)

        stage_started = time.time()
        bounds, lineage = audit_lineage(ctx, logger)
        paired_power = build_paired_power_scenarios(ctx, logger)
        stage_times["lineage_and_power"] = round(time.time() - stage_started, 3)

        stage_started = time.time()
        global_workload_path, site_workload_path = build_workload_tables(
            ctx, bounds, logger
        )
        stage_times["workload_tables"] = round(time.time() - stage_started, 3)

        stage_started = time.time()
        (
            global_feature_path,
            site_feature_path,
            feature_dictionary,
            target_dictionary,
        ) = build_ml_feature_tables(
            ctx, global_workload_path, site_workload_path, logger
        )
        stage_times["feature_and_target_tables"] = round(
            time.time() - stage_started, 3
        )

        stage_started = time.time()
        split_paths, split_summary, folds = build_split_tables(
            ctx, global_feature_path, bounds, logger
        )
        stage_times["splits"] = round(time.time() - stage_started, 3)

        stage_started = time.time()
        validation = validate_stage(
            ctx,
            bounds,
            global_workload_path,
            site_workload_path,
            global_feature_path,
            split_paths,
            feature_dictionary,
            target_dictionary,
            paired_power,
            logger,
        )
        write_report(
            ctx, validation, lineage, split_summary, folds, paired_power
        )
        stage_times["validate_and_report"] = round(
            time.time() - stage_started, 3
        )

        write_json(
            ctx.report_dir / "run_timing.json",
            {
                "run_tag": ctx.run_tag,
                "stage_seconds": stage_times,
                "elapsed_seconds_before_publish": round(time.time() - started, 3),
                "site_ml_features_created": site_feature_path is not None,
            },
        )

        stage_started = time.time()
        publish(ctx, logger)
        stage_times["publish"] = round(time.time() - stage_started, 3)
        write_json(
            ctx.run_dir / "run_complete.json",
            {
                "status": "success",
                "run_tag": ctx.run_tag,
                "elapsed_seconds": round(time.time() - started, 3),
                "stage_seconds": stage_times,
                "publish_dir": str(ctx.publish_dir),
            },
        )
    except Exception as error:
        write_json(
            ctx.run_dir / "run_failed.json",
            {
                "status": "failed",
                "run_tag": ctx.run_tag,
                "elapsed_seconds": round(time.time() - started, 3),
                "stage_seconds": stage_times,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        logger.exception("Stage K5-A failed")
        try:
            failure_zip = (
                ctx.review_root / f"stage_k5a_kestrel_ml_failure_{ctx.run_tag}.zip"
            )
            zip_review(ctx.run_dir, failure_zip)
            logger.info("Failure ZIP: %s", failure_zip)
        except Exception:
            logger.exception("Failure ZIP creation failed")
        raise
