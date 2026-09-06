from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .context import PipelineContext
from .db import connect, parquet_expr, quote_path
from .lineage import AnalysisBounds
from .utils import write_json


def _sql_ts(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S%z")


def validate_stage(
    ctx: PipelineContext,
    bounds: AnalysisBounds,
    global_workload_path: Path,
    site_workload_path: Path,
    global_feature_path: Path,
    split_paths: dict[str, Path],
    feature_dictionary: pd.DataFrame,
    target_dictionary: pd.DataFrame,
    paired_power: pd.DataFrame,
    logger: logging.Logger,
) -> dict[str, Any]:
    interval_minutes = int(ctx.config["analysis"]["interval_minutes"])
    interval_hours = interval_minutes / 60.0
    interval_seconds = interval_minutes * 60
    cases = [str(value) for value in ctx.config["analysis"]["flexibility_cases"]]
    expected_idcs = int(ctx.config["validation"]["expected_idc_count"])
    tolerance = float(ctx.config["validation"]["maximum_identity_error"])
    energy_tolerance = float(
        ctx.config["validation"]["maximum_energy_relative_error"]
    )
    analysis_end_exclusive = bounds.analysis_end_utc + pd.Timedelta(
        minutes=interval_minutes
    )

    con = connect(ctx.config)
    try:
        site = parquet_expr(site_workload_path)
        global_table = parquet_expr(global_workload_path)
        features = parquet_expr(global_feature_path)
        jobs = parquet_expr(ctx.jobs_path)

        site_row = con.execute(
            f"""
            SELECT
                count(*) AS row_count,
                count(DISTINCT idc_id) AS idc_count,
                count(DISTINCT timestamp_utc) AS timestamp_count,
                min(timestamp_utc) AS minimum_timestamp_utc,
                max(timestamp_utc) AS maximum_timestamp_utc,
                min(least(
                    total_avg_active_gpus,
                    queued_job_count,
                    queued_requested_gpus,
                    arriving_job_count,
                    arriving_requested_gpus,
                    arriving_gpu_hours
                )) AS minimum_core_metric,
                sum(total_avg_active_gpus) * {interval_hours:.17g}
                    AS dense_gpu_hours
            FROM {site}
            """
        ).fetchdf().iloc[0]

        global_count_row = con.execute(
            f"""
            SELECT
                count(*) AS row_count,
                min(timestamp_utc) AS minimum_timestamp_utc,
                max(timestamp_utc) AS maximum_timestamp_utc
            FROM {global_table}
            """
        ).fetchdf().iloc[0]
        global_step_row = con.execute(
            f"""
            SELECT
                min(epoch(timestamp_utc - lag_ts)) AS minimum_step_seconds,
                max(epoch(timestamp_utc - lag_ts)) AS maximum_step_seconds
            FROM (
                SELECT
                    timestamp_utc,
                    lag(timestamp_utc) OVER (ORDER BY timestamp_utc) AS lag_ts
                FROM {global_table}
            )
            WHERE lag_ts IS NOT NULL
            """
        ).fetchdf().iloc[0]
        global_row = {
            "row_count": global_count_row["row_count"],
            "minimum_timestamp_utc": global_count_row["minimum_timestamp_utc"],
            "maximum_timestamp_utc": global_count_row["maximum_timestamp_utc"],
            "minimum_step_seconds": global_step_row["minimum_step_seconds"],
            "maximum_step_seconds": global_step_row["maximum_step_seconds"],
        }

        identity_select = []
        for case in cases:
            identity_select.append(
                f"max(abs(total_avg_active_gpus - fixed_avg_active_gpus_{case} - flexible_avg_active_gpus_{case})) AS identity_{case}"
            )
        identity_row = con.execute(
            f"SELECT {', '.join(identity_select)} FROM {site}"
        ).fetchdf().iloc[0]
        maximum_identity_error = max(float(value) for value in identity_row.tolist())

        job_overlap_row = con.execute(
            f"""
            SELECT
                sum(
                    CAST(gpus_requested AS DOUBLE)
                    * greatest(
                        0.0,
                        epoch(
                            least(
                                CAST(end_time_utc AS TIMESTAMPTZ),
                                TIMESTAMPTZ '{_sql_ts(analysis_end_exclusive)}'
                            )
                            - greatest(
                                CAST(start_time_utc AS TIMESTAMPTZ),
                                TIMESTAMPTZ '{_sql_ts(bounds.analysis_start_utc)}'
                            )
                        )
                    ) / 3600.0
                ) AS cropped_job_gpu_hours
            FROM {jobs}
            WHERE
                end_time_utc > TIMESTAMPTZ '{_sql_ts(bounds.analysis_start_utc)}'
                AND start_time_utc < TIMESTAMPTZ '{_sql_ts(analysis_end_exclusive)}'
            """
        ).fetchdf().iloc[0]
        cropped_job_gpu_hours = float(job_overlap_row["cropped_job_gpu_hours"])
        dense_gpu_hours = float(site_row["dense_gpu_hours"])
        gpu_hour_relative_error = (
            abs(cropped_job_gpu_hours - dense_gpu_hours)
            / abs(cropped_job_gpu_hours)
            if cropped_job_gpu_hours
            else 0.0
        )

        primary_target_columns = target_dictionary.loc[
            target_dictionary["primary_role"].eq("primary"), "target_column"
        ].drop_duplicates().tolist()
        primary_null_expression = " + ".join(
            f"count_if({column} IS NULL)" for column in primary_target_columns
        )
        feature_row = con.execute(
            f"""
            SELECT
                count(*) AS row_count,
                count_if(feature_history_complete) AS history_complete_rows,
                {primary_null_expression if primary_null_expression else '0'}
                    AS primary_target_null_cells
            FROM {features}
            """
        ).fetchdf().iloc[0]

        split_metadata: dict[str, dict[str, Any]] = {}
        for split_name in ["train", "validation", "test_2025"]:
            path = split_paths[split_name]
            row = con.execute(
                f"""
                SELECT
                    count(*) AS row_count,
                    min(timestamp_utc) AS min_ts,
                    max(timestamp_utc) AS max_ts,
                    {primary_null_expression if primary_null_expression else '0'}
                        AS primary_target_null_cells
                FROM read_parquet('{quote_path(path)}')
                """
            ).fetchdf().iloc[0]
            split_metadata[split_name] = {
                "row_count": int(row["row_count"]),
                "minimum_timestamp_utc": str(row["min_ts"]),
                "maximum_timestamp_utc": str(row["max_ts"]),
                "primary_target_null_cells": int(row["primary_target_null_cells"]),
            }

        overlap_counts = {}
        split_pairs = [("train", "validation"), ("train", "test_2025"), ("validation", "test_2025")]
        for left, right in split_pairs:
            count = con.execute(
                f"""
                SELECT count(*)
                FROM read_parquet('{quote_path(split_paths[left])}') a
                INNER JOIN read_parquet('{quote_path(split_paths[right])}') b
                    USING (timestamp_utc)
                """
            ).fetchone()[0]
            overlap_counts[f"{left}_vs_{right}"] = int(count)
    finally:
        con.close()

    expected_timestamp_count = int(
        (bounds.analysis_end_utc - bounds.analysis_start_utc).total_seconds()
        / interval_seconds
    ) + 1
    expected_site_rows = expected_timestamp_count * expected_idcs
    five_minute_grid = (
        float(global_row["minimum_step_seconds"]) == interval_seconds
        and float(global_row["maximum_step_seconds"]) == interval_seconds
    )
    paired_identity_error = (
        float(pd.to_numeric(paired_power["identity_error_kw_per_gpu"], errors="coerce").max())
        if not paired_power.empty
        else None
    )
    feature_types = set(feature_dictionary["feature_type"].astype(str))
    past_only_feature_types = feature_types.issubset(
        {"lag", "calendar", "rolling_mean", "rolling_max", "rolling_stddev_pop"}
    )

    hard_test_end = pd.Timestamp(ctx.config["analysis"]["test_end_utc"])
    if hard_test_end.tzinfo is None:
        hard_test_end = hard_test_end.tz_localize("UTC")
    else:
        hard_test_end = hard_test_end.tz_convert("UTC")
    full_test_coverage = bounds.analysis_end_utc >= hard_test_end

    data_quality = {
        "analysis_start_utc": bounds.analysis_start_utc,
        "analysis_end_utc": bounds.analysis_end_utc,
        "expected_timestamp_count": expected_timestamp_count,
        "global_workload_rows": int(global_row["row_count"]),
        "site_workload_rows": int(site_row["row_count"]),
        "expected_site_rows": expected_site_rows,
        "idc_count": int(site_row["idc_count"]),
        "minimum_core_metric": float(site_row["minimum_core_metric"]),
        "maximum_fixed_flexible_identity_error": maximum_identity_error,
        "cropped_job_gpu_hours": cropped_job_gpu_hours,
        "dense_gpu_hours": dense_gpu_hours,
        "gpu_hour_relative_error": gpu_hour_relative_error,
        "feature_rows": int(feature_row["row_count"]),
        "feature_history_complete_rows": int(feature_row["history_complete_rows"]),
        "paired_power_identity_error_kw_per_gpu": paired_identity_error,
        "full_2025_calendar_coverage": full_test_coverage,
    }
    leakage_audit = {
        "split_metadata": split_metadata,
        "timestamp_overlap_counts": overlap_counts,
        "maximum_forecast_horizon_steps": max(
            int(value) for value in ctx.config["prediction"]["horizon_steps"]
        ),
        "maximum_forecast_horizon_minutes": max(
            int(value) for value in ctx.config["prediction"]["horizon_steps"]
        )
        * interval_minutes,
        "split_boundary_purge_applied": True,
        "all_primary_targets_nonnull_inside_splits": all(
            values["primary_target_null_cells"] == 0
            for values in split_metadata.values()
        ),
        "all_feature_types_are_past_or_calendar": past_only_feature_types,
        "scaling_status": "deferred_to_stage_k5b_train_only_fit",
        "test_2025_used_for_hyperparameter_tuning": False,
    }
    write_json(ctx.report_dir / "data_quality_report.json", data_quality)
    write_json(ctx.report_dir / "leakage_audit.json", leakage_audit)

    checks = {
        "global_timestamp_count_matches": int(global_row["row_count"])
        == expected_timestamp_count,
        "site_row_count_matches": int(site_row["row_count"])
        == expected_site_rows,
        "expected_idc_count": int(site_row["idc_count"]) == expected_idcs,
        "five_minute_grid": five_minute_grid,
        "nonnegative_core_metrics": float(site_row["minimum_core_metric"]) >= -1e-12,
        "fixed_plus_flexible_identity": maximum_identity_error <= tolerance,
        "cropped_gpu_hour_conservation": gpu_hour_relative_error <= energy_tolerance,
        "split_timestamp_disjoint": all(value == 0 for value in overlap_counts.values()),
        "primary_targets_complete_in_splits": leakage_audit[
            "all_primary_targets_nonnull_inside_splits"
        ],
        "past_only_feature_construction": past_only_feature_types,
        "paired_power_identity": (
            paired_identity_error is not None and paired_identity_error <= tolerance
            if bool(ctx.config["paths"].get("require_k4b_power_scenarios", True))
            else True
        ),
        "full_2025_test_coverage": (
            full_test_coverage
            if bool(ctx.config["validation"].get("require_full_2025_test_coverage", True))
            else True
        ),
    }
    payload = {
        "status": "success" if all(checks.values()) else "failed",
        "metrics": data_quality,
        "leakage_metrics": leakage_audit,
        "checks": checks,
        "interpretation": {
            "primary_ml_scope": "global Kestrel H100 workload forecasting before deterministic 12-IDC partitioning",
            "main_flexibility_case": ctx.config["analysis"]["main_flexibility_case"],
            "development_period": "valid H100 start through 2024-12-31 with 2024-09 to 2024-12 rolling validation",
            "final_holdout": "2025 calendar year, never used for hyperparameter selection",
            "time_resolution_minutes": interval_minutes,
            "power_conversion_deferred": "Stage K5-C uses NLR H100 paired power scenarios",
        },
    }
    write_json(ctx.report_dir / "validation.json", payload)
    if payload["status"] != "success":
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError(f"Stage K5-A validation failed: {failed}")
    logger.info(
        "K5-A validation success: %d global rows, %d site rows",
        data_quality["global_workload_rows"],
        data_quality["site_workload_rows"],
    )
    return payload
