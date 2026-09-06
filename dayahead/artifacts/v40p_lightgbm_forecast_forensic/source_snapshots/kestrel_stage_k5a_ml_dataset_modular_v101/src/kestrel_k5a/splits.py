from __future__ import annotations

import calendar
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .context import PipelineContext
from .db import connect, copy_query, quote_path
from .lineage import AnalysisBounds


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _sql_ts(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S%z")


def _effective_bound(value: Any, lower: pd.Timestamp | None = None, upper: pd.Timestamp | None = None) -> pd.Timestamp:
    timestamp = _utc(value)
    if lower is not None:
        timestamp = max(timestamp, lower)
    if upper is not None:
        timestamp = min(timestamp, upper)
    return timestamp


def build_rolling_origin_folds(
    ctx: PipelineContext, bounds: AnalysisBounds
) -> pd.DataFrame:
    interval = pd.Timedelta(minutes=int(ctx.config["analysis"]["interval_minutes"]))
    maximum_horizon = max(int(value) for value in ctx.config["prediction"]["horizon_steps"])
    horizon_delta = maximum_horizon * interval
    validation_start = _utc(ctx.config["analysis"]["validation_start_utc"])
    validation_end = min(
        _utc(ctx.config["analysis"]["validation_end_utc"]), bounds.analysis_end_utc
    )
    rows: list[dict[str, Any]] = []
    current = validation_start.normalize()
    while current <= validation_end:
        month_end_day = calendar.monthrange(current.year, current.month)[1]
        month_end = pd.Timestamp(
            year=current.year,
            month=current.month,
            day=month_end_day,
            hour=23,
            minute=55,
            tz="UTC",
        )
        fold_end = min(month_end, validation_end)
        validation_feature_end = fold_end - horizon_delta
        training_feature_end = current - horizon_delta - interval
        if validation_feature_end >= current and training_feature_end >= bounds.analysis_start_utc:
            rows.append(
                {
                    "fold_id": f"{current.year:04d}-{current.month:02d}",
                    "train_start_utc": bounds.analysis_start_utc,
                    "train_feature_end_utc": training_feature_end,
                    "validation_start_utc": current,
                    "validation_feature_end_utc": validation_feature_end,
                    "validation_calendar_end_utc": fold_end,
                    "maximum_horizon_steps": maximum_horizon,
                    "maximum_horizon_minutes": int(horizon_delta.total_seconds() / 60),
                }
            )
        current = current + pd.offsets.MonthBegin(1)
    return pd.DataFrame(rows)


def build_split_tables(
    ctx: PipelineContext,
    feature_path: Path,
    bounds: AnalysisBounds,
    logger: logging.Logger,
) -> tuple[dict[str, Path], pd.DataFrame, pd.DataFrame]:
    interval = pd.Timedelta(minutes=int(ctx.config["analysis"]["interval_minutes"]))
    max_horizon = max(int(value) for value in ctx.config["prediction"]["horizon_steps"])
    purge = max_horizon * interval

    train_start = bounds.analysis_start_utc
    train_calendar_end = min(
        _utc(ctx.config["analysis"]["train_end_utc"]), bounds.analysis_end_utc
    )
    validation_start = max(
        _utc(ctx.config["analysis"]["validation_start_utc"]), bounds.analysis_start_utc
    )
    validation_calendar_end = min(
        _utc(ctx.config["analysis"]["validation_end_utc"]), bounds.analysis_end_utc
    )
    test_start = max(
        _utc(ctx.config["analysis"]["test_start_utc"]), bounds.analysis_start_utc
    )
    test_calendar_end = min(
        _utc(ctx.config["analysis"]["test_end_utc"]), bounds.analysis_end_utc
    )

    boundaries = {
        "train": (train_start, train_calendar_end - purge, train_calendar_end),
        "validation": (
            validation_start,
            validation_calendar_end - purge,
            validation_calendar_end,
        ),
        "test_2025": (test_start, test_calendar_end - purge, test_calendar_end),
    }

    con = connect(ctx.config)
    output_paths: dict[str, Path] = {}
    rows: list[dict[str, Any]] = []
    try:
        source = quote_path(feature_path)
        for split_name, (start, feature_end, calendar_end) in boundaries.items():
            if feature_end < start:
                raise ValueError(f"No usable rows for split {split_name}: {start} to {feature_end}")
            filename = {
                "train": "kestrel_ml_train.parquet",
                "validation": "kestrel_ml_validation.parquet",
                "test_2025": "kestrel_ml_test_2025.parquet",
            }[split_name]
            target = ctx.output_dir / filename
            query = f"""
                SELECT
                    *,
                    '{split_name}' AS dataset_split
                FROM read_parquet('{source}')
                WHERE
                    feature_history_complete
                    AND timestamp_utc BETWEEN
                        TIMESTAMPTZ '{_sql_ts(start)}'
                        AND TIMESTAMPTZ '{_sql_ts(feature_end)}'
                ORDER BY timestamp_utc
            """
            copy_query(
                con,
                query,
                target,
                str(ctx.config["resources"]["parquet_compression"]),
            )
            output_paths[split_name] = target
            summary = con.execute(
                f"""
                SELECT
                    count(*) AS row_count,
                    min(timestamp_utc) AS minimum_timestamp_utc,
                    max(timestamp_utc) AS maximum_timestamp_utc
                FROM read_parquet('{quote_path(target)}')
                """
            ).fetchdf().iloc[0]
            rows.append(
                {
                    "split": split_name,
                    "calendar_start_utc": start,
                    "calendar_end_utc": calendar_end,
                    "feature_end_after_horizon_purge_utc": feature_end,
                    "row_count": int(summary["row_count"]),
                    "minimum_feature_timestamp_utc": summary["minimum_timestamp_utc"],
                    "maximum_feature_timestamp_utc": summary["maximum_timestamp_utc"],
                    "maximum_horizon_steps": max_horizon,
                    "maximum_horizon_minutes": int(purge.total_seconds() / 60),
                }
            )

        development_path = ctx.output_dir / "kestrel_ml_development_2024.parquet"
        copy_query(
            con,
            f"""
            SELECT * FROM read_parquet('{quote_path(output_paths['train'])}')
            UNION ALL
            SELECT * FROM read_parquet('{quote_path(output_paths['validation'])}')
            ORDER BY timestamp_utc
            """,
            development_path,
            str(ctx.config["resources"]["parquet_compression"]),
        )
        output_paths["development_2024"] = development_path
    finally:
        con.close()

    split_summary = pd.DataFrame(rows)
    split_summary.to_csv(
        ctx.output_dir / "split_summary.csv", index=False, encoding="utf-8-sig"
    )
    folds = build_rolling_origin_folds(ctx, bounds)
    folds.to_csv(
        ctx.output_dir / "rolling_origin_folds.csv",
        index=False,
        encoding="utf-8-sig",
    )
    logger.info("ML split tables generated with %d-minute boundary purge", int(purge.total_seconds()/60))
    return output_paths, split_summary, folds
