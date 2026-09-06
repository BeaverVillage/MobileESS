from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .context import PipelineContext
from .db import connect, copy_query, quote_path


def _calendar_expressions() -> list[tuple[str, str]]:
    return [
        ("utc_hour", "extract(hour FROM timestamp_utc)"),
        ("melbourne_hour", "extract(hour FROM timestamp_melbourne)"),
        (
            "melbourne_day_of_week",
            "cast(strftime(timestamp_melbourne, '%w') AS INTEGER)",
        ),
        ("melbourne_month", "extract(month FROM timestamp_melbourne)"),
        ("melbourne_day_of_year", "extract(doy FROM timestamp_melbourne)"),
        (
            "is_weekend",
            "cast(cast(strftime(timestamp_melbourne, '%w') AS INTEGER) IN (0, 6) AS INTEGER)",
        ),
        (
            "hour_sin",
            "sin(2 * pi() * extract(hour FROM timestamp_melbourne) / 24.0)",
        ),
        (
            "hour_cos",
            "cos(2 * pi() * extract(hour FROM timestamp_melbourne) / 24.0)",
        ),
        (
            "weekday_sin",
            "sin(2 * pi() * cast(strftime(timestamp_melbourne, '%w') AS INTEGER) / 7.0)",
        ),
        (
            "weekday_cos",
            "cos(2 * pi() * cast(strftime(timestamp_melbourne, '%w') AS INTEGER) / 7.0)",
        ),
        (
            "month_sin",
            "sin(2 * pi() * (extract(month FROM timestamp_melbourne) - 1) / 12.0)",
        ),
        (
            "month_cos",
            "cos(2 * pi() * (extract(month FROM timestamp_melbourne) - 1) / 12.0)",
        ),
    ]


def _target_expressions(
    horizons: list[int], interval_minutes: int, partition: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    window_order = (
        f"PARTITION BY {partition} ORDER BY timestamp_utc"
        if partition
        else "ORDER BY timestamp_utc"
    )
    point_sources = [
        "fixed_avg_active_gpus_F30",
        "total_avg_active_gpus",
        "flexible_avg_active_gpus_F30",
        "arriving_flexible_gpu_hours_F30",
    ]
    expressions: list[str] = []
    dictionary: list[dict[str, Any]] = []

    for horizon in horizons:
        suffix = f"h{horizon:02d}"
        future_time = f"lead(timestamp_utc, {horizon}) OVER ({window_order})"
        expected = f"timestamp_utc + INTERVAL '{horizon * interval_minutes} minutes'"
        complete = f"{future_time} = {expected}"
        for source in point_sources:
            name = f"target_{source}_{suffix}"
            expressions.append(
                f"CASE WHEN {complete} THEN lead({source}, {horizon}) "
                f"OVER ({window_order}) ELSE NULL END AS {name}"
            )
            dictionary.append(
                {
                    "target_column": name,
                    "source_metric": source,
                    "target_type": "point_at_horizon",
                    "horizon_steps": horizon,
                    "horizon_minutes": horizon * interval_minutes,
                    "primary_role": (
                        "primary"
                        if source == "fixed_avg_active_gpus_F30"
                        else "comparison"
                    ),
                }
            )

        cumulative_name = (
            f"target_cumulative_arriving_flexible_gpu_hours_F30_{suffix}"
        )
        expressions.append(
            f"CASE WHEN {complete} THEN sum(arriving_flexible_gpu_hours_F30) "
            f"OVER ({window_order} ROWS BETWEEN 1 FOLLOWING AND {horizon} FOLLOWING) "
            f"ELSE NULL END AS {cumulative_name}"
        )
        dictionary.append(
            {
                "target_column": cumulative_name,
                "source_metric": "arriving_flexible_gpu_hours_F30",
                "target_type": "cumulative_next_horizon",
                "horizon_steps": horizon,
                "horizon_minutes": horizon * interval_minutes,
                "primary_role": "primary",
            }
        )

    return expressions, dictionary


def _lag_rolling_expressions(
    config: dict[str, Any], partition: str | None, site_compact: bool = False
) -> tuple[list[str], list[dict[str, Any]], int]:
    feature_config = config["features"]
    if site_compact:
        lags = [int(v) for v in feature_config["site_lag_steps"]]
        windows = [int(v) for v in feature_config["site_rolling_windows"]]
        lag_sources = [
            "total_avg_active_gpus",
            "fixed_avg_active_gpus_F30",
            "flexible_avg_active_gpus_F30",
            "arriving_flexible_gpu_hours_F30",
            "queued_requested_gpus",
        ]
        rolling_sources = lag_sources
        statistics = ["mean", "max"]
    else:
        lags = [int(v) for v in feature_config["lag_steps"]]
        windows = [int(v) for v in feature_config["rolling_windows"]]
        lag_sources = [str(v) for v in feature_config["lag_source_columns"]]
        rolling_sources = [
            str(v) for v in feature_config["rolling_source_columns"]
        ]
        statistics = [str(v) for v in feature_config["rolling_statistics"]]

    window_order = (
        f"PARTITION BY {partition} ORDER BY timestamp_utc"
        if partition
        else "ORDER BY timestamp_utc"
    )
    expressions: list[str] = []
    dictionary: list[dict[str, Any]] = []
    for source in lag_sources:
        for lag in lags:
            name = f"lag_{source}_{lag:04d}"
            expressions.append(
                f"lag({source}, {lag}) OVER ({window_order}) AS {name}"
            )
            dictionary.append(
                {
                    "feature_column": name,
                    "source_metric": source,
                    "feature_type": "lag",
                    "lookback_steps": lag,
                    "lookback_minutes": lag
                    * int(config["analysis"]["interval_minutes"]),
                }
            )

    for source in rolling_sources:
        for window in windows:
            frame = (
                f"{window - 1} PRECEDING AND CURRENT ROW"
                if window > 1
                else "CURRENT ROW AND CURRENT ROW"
            )
            for statistic in statistics:
                name = f"roll{window:04d}_{statistic}_{source}"
                expressions.append(
                    f"{statistic}({source}) OVER ({window_order} ROWS BETWEEN {frame}) "
                    f"AS {name}"
                )
                dictionary.append(
                    {
                        "feature_column": name,
                        "source_metric": source,
                        "feature_type": f"rolling_{statistic}",
                        "lookback_steps": window,
                        "lookback_minutes": window
                        * int(config["analysis"]["interval_minutes"]),
                    }
                )

    return expressions, dictionary, max(lags)


def _build_one(
    ctx: PipelineContext,
    source_path: Path,
    target_path: Path,
    targets_only_path: Path,
    partition: str | None,
    site_compact: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    interval = int(ctx.config["analysis"]["interval_minutes"])
    horizons = [int(v) for v in ctx.config["prediction"]["horizon_steps"]]
    lag_expressions, feature_dictionary, max_lag = _lag_rolling_expressions(
        ctx.config, partition, site_compact
    )
    target_expressions, target_dictionary = _target_expressions(
        horizons, interval, partition
    )
    calendar = _calendar_expressions()
    calendar_expressions = [f"{expression} AS {name}" for name, expression in calendar]
    for name, _ in calendar:
        feature_dictionary.append(
            {
                "feature_column": name,
                "source_metric": "timestamp_melbourne",
                "feature_type": "calendar",
                "lookback_steps": 0,
                "lookback_minutes": 0,
            }
        )

    history_window = (
        f"PARTITION BY {partition} ORDER BY timestamp_utc"
        if partition
        else "ORDER BY timestamp_utc"
    )
    history_complete = (
        f"lag(total_avg_active_gpus, {max_lag}) OVER ({history_window}) "
        "IS NOT NULL AS feature_history_complete"
    )

    con = connect(ctx.config)
    try:
        source = quote_path(source_path)
        query = f"""
            SELECT
                source.*,
                {', '.join(calendar_expressions)},
                {', '.join(lag_expressions)},
                {', '.join(target_expressions)},
                {history_complete}
            FROM read_parquet('{source}') source
            ORDER BY timestamp_utc{', ' + partition if partition else ''}
        """
        copy_query(
            con,
            query,
            target_path,
            str(ctx.config["resources"]["parquet_compression"]),
        )
        target_names = [row["target_column"] for row in target_dictionary]
        select_keys = ["timestamp_utc"] + ([partition] if partition else [])
        target_query = (
            "SELECT "
            + ", ".join(select_keys + target_names)
            + f" FROM read_parquet('{quote_path(target_path)}')"
        )
        copy_query(
            con,
            target_query,
            targets_only_path,
            str(ctx.config["resources"]["parquet_compression"]),
        )
    finally:
        con.close()

    return pd.DataFrame(feature_dictionary), pd.DataFrame(target_dictionary)


def build_ml_feature_tables(
    ctx: PipelineContext,
    global_workload_path: Path,
    site_workload_path: Path,
    logger: logging.Logger,
) -> tuple[Path, Path | None, pd.DataFrame, pd.DataFrame]:
    global_feature_path = ctx.output_dir / "kestrel_ml_features_global_5min.parquet"
    global_target_path = ctx.output_dir / "kestrel_ml_targets_global_5min.parquet"
    feature_dictionary, target_dictionary = _build_one(
        ctx,
        global_workload_path,
        global_feature_path,
        global_target_path,
        partition=None,
        site_compact=False,
    )

    site_feature_path: Path | None = None
    if bool(ctx.config["features"].get("generate_site_ml_features", False)):
        site_feature_path = ctx.output_dir / "kestrel_ml_features_12idc_5min.parquet"
        site_target_path = ctx.output_dir / "kestrel_ml_targets_12idc_5min.parquet"
        site_dictionary, site_targets = _build_one(
            ctx,
            site_workload_path,
            site_feature_path,
            site_target_path,
            partition="idc_id",
            site_compact=True,
        )
        site_dictionary["dataset_scope"] = "12idc_compact"
        site_targets["dataset_scope"] = "12idc_compact"
        feature_dictionary["dataset_scope"] = "global_primary"
        target_dictionary["dataset_scope"] = "global_primary"
        feature_dictionary = pd.concat(
            [feature_dictionary, site_dictionary], ignore_index=True
        )
        target_dictionary = pd.concat(
            [target_dictionary, site_targets], ignore_index=True
        )
    else:
        feature_dictionary["dataset_scope"] = "global_primary"
        target_dictionary["dataset_scope"] = "global_primary"

    feature_dictionary.to_csv(
        ctx.output_dir / "feature_dictionary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    target_dictionary.to_csv(
        ctx.output_dir / "target_dictionary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    logger.info("Global ML feature table: %s", global_feature_path)
    if site_feature_path:
        logger.info("12-IDC compact ML feature table: %s", site_feature_path)
    return (
        global_feature_path,
        site_feature_path,
        feature_dictionary,
        target_dictionary,
    )
